"""web_fetch: GET a public web page and return what a reader would see.

The gateway sits on both the agents' network and the outside one, and can reach
the back end and the cloud metadata address. So every URL, and every redirect
hop, is checked: http(s) only, no internal host names, and every address the
host resolves to must be public. Pages are capped at MAX_BYTES and cleaned like mail.

Known limit: DNS is resolved once to check and again by the HTTP client to
connect, so a host that changes its answer in between (DNS rebinding) could
slip through.
"""

import ipaddress
import socket
from collections.abc import Callable

import httpx

from core.firewall import sanitize
from core.firewall.sanitize import Evidence, Untrusted
from core.firewall.tools.files import Denied

MAX_BYTES = 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 10
# Names that point inside Docker or the host, whatever they resolve to.
BLOCKED_HOSTS = {"localhost", "gateway", "host.docker.internal", "gateway.docker.internal", "metadata.google.internal"}
BLOCKED_SUFFIXES = (".localhost", ".internal", ".local")

Resolver = Callable[[str], list[str]]


def resolve(host: str) -> list[str]:
    """Every address the host name resolves to (IPv4 and IPv6)."""
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def check_url(url: str, resolver: Resolver) -> None:
    """Raise Denied unless the URL is http(s) and every address behind it is public."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as error:
        raise Denied("url_not_allowed", "not a valid URL") from error
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise Denied("url_not_allowed", "only http and https URLs can be fetched")
    host = parsed.host.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_SUFFIXES):
        raise Denied("private_address", f"{host} is an internal name")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(address.split("%")[0]) for address in resolver(host)]
        except OSError as error:
            raise Denied("fetch_failed", f"could not resolve {host}") from error
    if not addresses:
        raise Denied("fetch_failed", f"could not resolve {host}")
    for address in addresses:
        # "::ffff:127.0.0.1" is 127.0.0.1 in IPv6 clothing.
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        # is_global is False for loopback, private, link-local (169.254, the metadata address),
        # shared, reserved and documentation ranges.
        if not address.is_global:
            raise Denied("private_address", f"{host} resolves to a non-public address")


async def fetch(url: str, resolver: Resolver, transport: httpx.AsyncBaseTransport | None = None) -> Untrusted:
    """GET the page, following redirects by hand so each hop is checked."""
    async with httpx.AsyncClient(transport=transport, follow_redirects=False, timeout=TIMEOUT_SECONDS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url, resolver)
            try:
                async with client.stream("GET", url, headers={"user-agent": "heimdall-gateway"}) as response:
                    if response.is_redirect:
                        url = str(httpx.URL(url).join(response.headers["location"]))
                        continue
                    if response.status_code >= 400:
                        raise Denied("fetch_failed", f"the site answered {response.status_code}")
                    body = await read_capped(response)
                    return as_untrusted(url, response, body)
            except httpx.HTTPError as error:
                raise Denied("fetch_failed", f"could not fetch the page ({type(error).__name__})") from error
    raise Denied("too_many_redirects", f"more than {MAX_REDIRECTS} redirects")


async def read_capped(response: httpx.Response) -> bytes:
    body = b""
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) > MAX_BYTES:
            raise Denied("page_too_large", f"page is over {MAX_BYTES // 1024} KB")
    return body


def as_untrusted(url: str, response: httpx.Response, body: bytes) -> Untrusted:
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    text = body.decode(response.charset_encoding or "utf-8", errors="replace")
    if "html" in content_type:
        cleaned = sanitize.html(text)
    elif content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        cleaned = sanitize.text(text)
    else:
        raise Denied("not_text", f"not a text page ({content_type or 'unknown type'})")
    source = f"web page {url}"
    return Untrusted(f"Page: {url}\n\n{cleaned.text}", [Evidence(source, removed) for removed in cleaned.removed])

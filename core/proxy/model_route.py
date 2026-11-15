"""The /model/{path} route: the gateway's model proxy.

Agents set their provider base URL to http://gateway:8080/model and send their
fake key. This route checks the key, logs the call, then either answers with the
mock model or relays the request to the real provider with the real key.

The provider follows from the API the agent speaks, which B's agent manager sets
from the provider the user chose: OpenAI-style chat/completions goes to Gemini,
Anthropic-style messages goes to Anthropic, and anything under /model/local goes
to the local model (Ollama, OpenAI style). The agent never picks a host.
Every request is scanned for keys and secrets. Requests to a cloud provider also go
through consent for Confidential file text (core/proxy/consent.py); the local model
skips it, because nothing leaves the machine.
"""

import json
from collections.abc import Awaitable, Callable

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from core.firewall import core_client, permissions, secrets
from core.firewall.config import GatewaySettings
from core.firewall.permissions import NoPermissions
from core.firewall.session import Sessions
from core.proxy import mock_model
from core.proxy.consent import Consent

Handler = Callable[[Request], Awaitable[Response]]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# Paths under this prefix go to the local model. B points an agent at http://gateway:8080/model/local.
LOCAL_PREFIX = "local/"
# Agent headers we pass on to the provider. Everything else, including the agent's key, is dropped.
FORWARDED_HEADERS = ("anthropic-version", "anthropic-beta")
# How much of a provider error to log, so a failed chat can be explained.
ERROR_LOG_CHARS = 500


def sent_key(request: Request) -> str:
    """The key the agent sent: Anthropic style (x-api-key) or OpenAI style (Bearer)."""
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return request.headers.get("x-api-key") or bearer


def upstream_for(path: str, settings: GatewaySettings) -> tuple[str, dict[str, str]] | None:
    """Provider URL and the header carrying the real key, chosen by the API the agent speaks.

    None for any other path: it is not a model call.
    """
    if path.startswith(LOCAL_PREFIX):
        # Ollama needs no key.
        return (settings.ollama_url, {}) if path.endswith("chat/completions") else None
    if path.endswith("chat/completions"):
        return GEMINI_URL, {"authorization": f"Bearer {settings.gemini_key}"}
    if path.endswith("messages"):
        return f"https://api.anthropic.com/{path}", {"x-api-key": settings.anthropic_key}
    return None


def provider_name(path: str) -> str:
    """Who would get the request, in words for the consent question."""
    if path.startswith(LOCAL_PREFIX):
        return "the local model"
    return "Gemini" if path.endswith("chat/completions") else "Anthropic"


def has_real_key(headers: dict[str, str]) -> bool:
    return any(value.removeprefix("Bearer ").strip() for value in headers.values())


def tools_offered(body: dict) -> list[str]:
    """Tool names in an Anthropic style ({name}) or OpenAI style ({function: {name}}) request."""
    return [tool.get("name") or tool.get("function", {}).get("name") for tool in body.get("tools") or []]


def sign_tool_calls(body: dict) -> dict:
    """Gemini rejects a replayed tool call without its thought signature, and OpenClaw drops it.

    Google documents this placeholder value for clients that cannot keep the real one.
    Same fix B's earlier stand-in gateway used.
    """
    for message in body.get("messages") or []:
        for call in (message.get("tool_calls") or []) if isinstance(message, dict) else []:
            google = call.setdefault("extra_content", {}).setdefault("google", {})
            google.setdefault("thought_signature", "skip_thought_signature_validator")
    return body


def make_model_route(
    settings: GatewaySettings,
    transport: httpx.AsyncBaseTransport | None = None,
    consent: Consent | None = None,
    sessions: Sessions | None = None,
) -> Handler:
    """Build the route handler for these settings.

    transport: only for tests, to fake the provider.
    consent, sessions: shared with the tools, so the proxy knows what Confidential text
    files_read served in the agent's current session. Without them there is no consent step.
    """

    async def model_route(request: Request) -> Response:
        path = request.path_params["path"]
        key = sent_key(request)
        # Fail closed: no known fake key, no model access, for any path.
        agent = settings.fake_keys.get(key)
        if agent is None:
            core_client.emit("model_blocked", path=path, reason="missing or unknown fake key")
            return JSONResponse({"error": "Heimdall: unknown key"}, status_code=401)
        upstream = upstream_for(path, settings)
        # Anything that isn't a model call (such as a model list) gets an empty answer.
        if request.method != "POST" or upstream is None:
            core_client.emit("model_other", agent=agent, method=request.method, path=path)
            return JSONResponse({"data": []})
        try:
            body = json.loads(await request.body())
        except ValueError:
            body = None
        if not isinstance(body, dict):
            core_client.emit("model_blocked", agent=agent, path=path, reason="body is not a JSON object")
            return JSONResponse({"error": "Heimdall: body must be a JSON object"}, status_code=400)
        # B's tests read api_key and tools_offered from this line. The key here is
        # always a fake one: we only get this far with a known fake key.
        core_client.emit(
            "model_call", agent=agent, api_key=key, model=body.get("model"), tools_offered=tools_offered(body)
        )
        # Tripwire and secret scan before anything else sees the body, mock included.
        blocked = blocked_for_secrets(body, agent, path, settings)
        if blocked is not None:
            return blocked
        local = path.startswith(LOCAL_PREFIX)
        if not local and consent is not None and sessions is not None:
            await withhold_denied(body, agent, key, path, consent, sessions, settings)
        if settings.mock:
            return mock_model.reply(path, body)
        url, headers = upstream
        if not local and not has_real_key(headers):
            core_client.emit("model_blocked", agent=agent, path=path, reason="no real key for this provider")
            return JSONResponse({"error": "Heimdall: no real key for this provider"}, status_code=502)
        if path.endswith("chat/completions"):
            body = sign_tool_calls(body)
        headers.update({name: request.headers[name] for name in FORWARDED_HEADERS if name in request.headers})
        return await relay(url, headers, body, agent, transport)

    return model_route


async def withhold_denied(
    body: dict, agent: str, key: str, path: str, consent: Consent, sessions: Sessions, settings: GatewaySettings
) -> None:
    """Consent for Confidential text in this request; denied blocks are replaced in `body`."""
    try:
        run = permissions.load(settings.agents_dir, agent, key)
    except NoPermissions:
        return  # no permissions, no file tools: nothing Confidential can have been served
    session = sessions.for_run(agent, run.run_id)
    withheld = await consent.check(body, agent, session.id, provider_name(path))
    if withheld:
        core_client.emit("model_withheld", agent=agent, path=path, rule_id="consent_denied", files=withheld)


def blocked_for_secrets(body: dict, agent: str, path: str, settings: GatewaySettings) -> Response | None:
    """403 if the body carries a fake key (theft) or any other secret; None if it is clean.

    The auth header is not in the body, so an agent's own fake key there is fine.
    Blocking (not stripping) is deliberate: the user should see the attempt.
    """
    findings = secrets.scan_json(body, settings.real_keys(), settings.fake_keys)
    if not findings:
        return None
    theft = any(finding.kind == "fake_key" for finding in findings)
    rule_id = "key_theft_attempt" if theft else "secret_in_request"
    kinds = sorted({finding.kind for finding in findings})
    core_client.emit(
        "model_blocked",
        agent=agent,
        path=path,
        rule_id=rule_id,
        reason=f"request contains {', '.join(kinds)}",
        findings=[{"kind": finding.kind, "preview": finding.preview} for finding in findings],
    )
    return JSONResponse(
        {"error": f"Heimdall blocked this request: it contains {', '.join(kinds)} (rule {rule_id})"}, status_code=403
    )


async def relay(
    url: str, headers: dict[str, str], body: dict, agent: str, transport: httpx.AsyncBaseTransport | None
) -> Response:
    """Send the request to the real provider and stream its reply back to the agent."""
    # The client must outlive this function (the reply is streamed), so it is
    # closed in chunks() below rather than with `async with`.
    client = httpx.AsyncClient(timeout=300, transport=transport)
    try:
        upstream = await client.send(client.build_request("POST", url, headers=headers, json=body), stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        core_client.emit("model_upstream_error", agent=agent, url=url, reason=type(error).__name__)
        return JSONResponse({"error": "Heimdall: model provider unreachable"}, status_code=502)
    # Never log `headers`: they hold the real key.
    core_client.emit("model_forwarded", agent=agent, url=url, model=body.get("model"), status=upstream.status_code)
    if upstream.status_code >= 400:
        # Provider errors are small: read it whole, log the start, pass it on.
        error = await upstream.aread()
        await client.aclose()
        text = error.decode(errors="replace")[:ERROR_LOG_CHARS]
        core_client.emit("model_error", agent=agent, status=upstream.status_code, body=text)
        return Response(error, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))

    async def chunks():
        # Pass bytes through as they arrive so chat replies still stream.
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        chunks(), status_code=upstream.status_code, media_type=upstream.headers.get("content-type")
    )

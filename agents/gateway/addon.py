"""Stand-in for the firewall's model proxy (A builds the real one).

mitmproxy add-on on port 8080. Agents send model calls to the real provider
address through this proxy, carrying only a fake key. The proxy allows only
known provider hosts and swaps the fake key for the real one.
"""

import json
import os

from mitmproxy import http

FAKE_KEY_PREFIX = "sk-fake-"
REAL_KEYS = {
    "generativelanguage.googleapis.com": os.environ.get("GEMINI_API_KEY", ""),
    "api.anthropic.com": os.environ.get("ANTHROPIC_API_KEY", ""),
    "openrouter.ai": os.environ.get("OPENROUTER_API_KEY", ""),
}
KEY_HEADERS = ("authorization", "x-api-key", "x-goog-api-key")


def log(kind: str, **fields) -> None:
    print(json.dumps({"kind": kind, **fields}), flush=True)


def block(flow: http.HTTPFlow, kind: str, reason: str) -> None:
    log(kind, host=flow.request.pretty_host, path=flow.request.path, reason=reason)
    flow.response = http.Response.make(403, f"Heimdall: {reason}", {"content-type": "text/plain"})


def tools_offered(flow: http.HTTPFlow) -> list[str]:
    try:
        body = json.loads(flow.request.get_text() or "{}")
    except ValueError:
        return []
    names = []
    for tool in body.get("tools") or []:
        if "function" in tool:
            names.append(tool["function"]["name"])
        elif "name" in tool:
            names.append(tool["name"])
        names += [f["name"] for f in tool.get("functionDeclarations", [])]
    return names


class ModelProxy:
    def request(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host
        if host not in REAL_KEYS:
            return block(flow, "blocked_egress", "host is not an allowed model provider")
        header = next((h for h in KEY_HEADERS if h in flow.request.headers), None)
        sent = flow.request.headers.get(header, "") if header else ""
        fake = sent.removeprefix("Bearer ")
        if not fake.startswith(FAKE_KEY_PREFIX):
            return block(flow, "model_blocked", "the request does not carry an agent's fake key")
        if not REAL_KEYS[host]:
            return block(flow, "model_blocked", f"no real key for {host} is set in the gateway")
        log("model_call", agent=fake, host=host, path=flow.request.path.split("?")[0], tools_offered=tools_offered(flow))
        flow.request.headers[header] = sent.replace(fake, REAL_KEYS[host])

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        flow.response.stream = True
        log("model_forwarded", host=flow.request.pretty_host, status=flow.response.status_code)


addons = [ModelProxy()]

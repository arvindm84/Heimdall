"""Helpers the two agents' tests share. They talk to real containers."""

import json

from agents import manager

GEMINI_HOST = "generativelanguage.googleapis.com"
MODEL = "gemini-flash-lite-latest"
ASK = {
    "openclaw": lambda message: ("node", "openclaw.mjs", "agent", "--agent", "main", "-m", message, "--timeout", "120"),
    "hermes": lambda message: ("timeout", "200", "hermes", "-z", message),
}


def in_agent(agent: str, *command: str) -> str:
    return manager.compose("exec", "-T", agent, *command)


def gateway_log(kind: str, agent: str) -> list[dict]:
    """What the gateway recorded for this agent, identified by its fake key."""
    lines = manager.compose("logs", "--no-log-prefix", "gateway").splitlines()
    events = [json.loads(line) for line in lines if line.startswith('{"kind"')]
    return [e for e in events if e["kind"] == kind and e.get("agent") == manager.profile(agent).FAKE_KEY]


def ask(agent: str, message: str) -> list[dict]:
    """Send one message and return the model calls it caused, as the gateway saw them."""
    before = len(gateway_log("model_call", agent))
    try:
        in_agent(agent, *ASK[agent](message))
    except Exception:
        pass
    return gateway_log("model_call", agent)[before:]


def http_code(agent: str, *curl_args: str) -> str:
    try:
        return in_agent(agent, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", *curl_args).strip()
    except Exception:
        return "000"


def check_sealed_and_routed(agent: str, opened) -> None:
    """The checks that must hold for every agent."""
    assert manager.chat_status(opened.chat_url, opened.chat_token) == 200
    assert manager.chat_status(opened.chat_url, "wrong-token") == 401

    assert http_code(agent, "-m", "6", "--noproxy", "*", "https://example.com") == "000"
    assert http_code(agent, "-m", "10", "https://example.com") in ("000", "403")

    tools_before = len(gateway_log("tool_call", agent))
    model_calls = ask(agent, "Read notes.txt and tell me what it says.")
    tool_calls = gateway_log("tool_call", agent)[tools_before:]
    assert model_calls and all(call["host"] == GEMINI_HOST for call in model_calls)
    assert any(call["tool"] == "files_read" for call in tool_calls)

"""The firewall's only link to the core: emit events and ask the user.

Today the core is C's Flask back end (POST /raise on main). Everything else in
the firewall goes through these two functions, so moving to a WebSocket later
changes only this file.

Other modules call `core_client.emit(...)` (not `from ... import emit`) so tests
can capture events by patching this module.
"""

import json
import os

import httpx

# The gateway runs in Docker; the back end runs on the host.
CORE_URL = os.environ.get("CORE_URL", "http://host.docker.internal:5000")
# The back end waits 120 s for the user; OpenClaw waits 130 s for a tool.
# 125 s sits between them, so the back end's own deny reaches us first.
ASK_TIMEOUT_SECONDS = 125


def emit(kind: str, **fields) -> None:
    """Print one event as a JSON line on stdout.

    `docker compose logs gateway` and B's runtime tests read these lines. Once C
    has an endpoint for plain events, this also posts there.
    """
    print(json.dumps({"kind": kind, **fields}), flush=True)


async def ask(
    kind: str, agent: str, question: str, details: dict, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """Ask the user through the core and wait. Returns "approve" or "deny".

    kind: "approval" or "consent". details: extra fields shown in the pop-up.
    transport: only for tests, to fake the back end.
    Fail closed: no back end, timeout, error status or an odd reply all mean "deny".
    """
    # Fixed fields go last so `details` can never change who is asking or what.
    body = {**details, "container_id": agent, "question": question, "kind": kind}
    try:
        async with httpx.AsyncClient(timeout=ASK_TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.post(f"{CORE_URL}/raise", json=body)
            response.raise_for_status()
            # ValueError: not JSON. KeyError/TypeError: JSON without a "decision" field.
            decision = response.json()["decision"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        emit("ask_failed", agent=agent, ask_kind=kind, reason=f"{type(error).__name__}: {error}")
        return "deny"
    if decision not in ("approve", "deny"):
        emit("ask_failed", agent=agent, ask_kind=kind, reason=f"unexpected decision {decision!r}")
        return "deny"
    return decision

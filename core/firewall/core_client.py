"""The firewall's only link to the core: emit events and ask the user.

Today the core is C's Flask back end (POST /api/raise on port 8765). Everything else in
the firewall goes through these two functions, so moving to a WebSocket later
changes only this file.

Other modules call `core_client.emit(...)` (not `from ... import emit`) so tests
can capture events by patching this module.
"""

import json
import os
import queue
import threading

import httpx

# The gateway runs in Docker; the back end runs on the host.
CORE_URL = os.environ.get("CORE_URL", "http://host.docker.internal:8765")
# The back end waits 120 s for the user; OpenClaw waits 130 s for a tool.
# 125 s sits between them, so the back end's own deny reaches us first.
ASK_TIMEOUT_SECONDS = 125


def emit(kind: str, **fields) -> None:
    """Print one event as a JSON line on stdout, and send it to the dashboard if set up.

    `docker compose logs gateway` and B's runtime tests read the stdout lines. With
    HEIMDALL_EVENTS_URL set (C's endpoint for plain events), each event is also posted
    there in the background: a slow or missing back end never holds up a tool call.
    """
    event = {"kind": kind, **fields}
    print(json.dumps(event), flush=True)
    if EVENTS_URL:
        _outgoing().put(event)


# The dashboard's endpoint for plain events (POST one JSON event). Empty: stdout only.
EVENTS_URL = os.environ.get("HEIMDALL_EVENTS_URL", "")
EVENTS_TIMEOUT_SECONDS = 2
# Only for tests, to fake the dashboard.
events_transport: httpx.BaseTransport | None = None
_queue: queue.Queue | None = None


def _outgoing() -> queue.Queue:
    """The queue of events waiting to be posted, with its sender thread started on first use."""
    global _queue
    if _queue is None:
        _queue = queue.Queue()
        threading.Thread(target=_send_events, args=(_queue,), daemon=True).start()
    return _queue


def _send_events(pending: queue.Queue) -> None:
    """Post events one by one, in order. A failed post is dropped: stdout keeps the record."""
    with httpx.Client(timeout=EVENTS_TIMEOUT_SECONDS, transport=events_transport) as client:
        while True:
            event = pending.get()
            try:
                client.post(EVENTS_URL, json=event)
            except httpx.HTTPError:
                pass
            finally:
                pending.task_done()


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
            response = await client.post(f"{CORE_URL}/api/raise", json=body)
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

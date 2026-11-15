"""Blocked-request notifications. Used by /api/raise, /api/events and /api/response.

Flow:
    1. Firewall calls /raise. raise_request() adds the request to the pending
       list and then WAITS for the user's decision.
    2. /events sends every pending request to the dashboard, which shows the popup.
       Requests are never "taken" off the list, so a reload or a dead connection
       can't lose one: a new connection simply sends everything still pending.
    3. User clicks Approve/Deny -> /response -> record_response() drops the
       decision into that request's queue, which wakes raise_request() up.
    4. /raise returns the decision to the firewall, which fulfils or denies
       the agent's MCP tool call. The request leaves the pending list.

Consent questions (kind "consent") can carry a scope with an approve:
"once" (allow once) or "folder" (always for this folder). The back end only passes
it on; the gateway decides what it means (core/proxy/consent.py). A gateway that
doesn't know about scope reads only "decision", so adding it changes nothing there.
"""

import queue
import uuid

# How long the firewall waits for the user before we treat it as a deny.
TIMEOUT_SECONDS = 120

# What an approve on a consent question can be limited to.
SCOPES = ("once", "folder")

# Requests waiting on the user: request_id -> {"details": what the dashboard shows,
#                                              "decision": queue the answer gets dropped into}
_waiting: dict[str, dict] = {}


def raise_request(details: dict) -> dict:
    """Add the request to the pending list and wait for the user.

    Returns {"decision": "approve" | "deny"}, plus "scope" if the user gave one.
    {"decision": "deny"} if the user doesn't answer in time.
    """
    request_id = uuid.uuid4().hex
    decision: queue.Queue = queue.Queue()
    # Body as-is, plus the id the dashboard sends back on /response.
    _waiting[request_id] = {"details": {**details, "request_id": request_id}, "decision": decision}

    try:
        # Pause here until record_response() puts the decision in.
        return decision.get(timeout=TIMEOUT_SECONDS)
    except queue.Empty:
        return {"decision": "deny"}
    finally:
        # Answered or timed out: no longer pending (/events tells the dashboard to close the popup).
        del _waiting[request_id]


def list_pending() -> list[dict]:
    """Every request still waiting for the user, as the dashboard should show it."""
    # list() takes a snapshot: other threads may add or remove requests while we read.
    return [w["details"] for w in list(_waiting.values())]


def record_response(request_id: str, decision: str, scope: str | None = None) -> bool:
    """Hand the user's decision to the waiting /raise.

    scope: only with an approve on a consent question ("once" or "folder").
    Returns False if nothing is waiting on that id (unknown or already timed out).
    Raises ValueError for a scope where it doesn't belong.
    """
    waiting = _waiting.get(request_id)
    if waiting is None:
        return False
    answer = {"decision": decision}
    if scope is not None:
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of: {', '.join(SCOPES)}")
        if decision != "approve" or waiting["details"].get("kind") != "consent":
            raise ValueError("scope only goes with an approve on a consent question")
        answer["scope"] = scope
    waiting["decision"].put(answer)
    return True

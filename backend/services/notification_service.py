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
"""

import queue
import uuid

# How long the firewall waits for the user before we treat it as a deny.
TIMEOUT_SECONDS = 120

# Requests waiting on the user: request_id -> {"details": what the dashboard shows,
#                                              "decision": queue the answer gets dropped into}
_waiting: dict[str, dict] = {}


def raise_request(details: dict) -> str:
    """Add the request to the pending list and wait for the user.

    Returns "approve" or "deny" ("deny" if the user doesn't answer in time).
    """
    request_id = uuid.uuid4().hex
    decision: queue.Queue = queue.Queue()
    # Body as-is, plus the id the dashboard sends back on /response.
    _waiting[request_id] = {"details": {**details, "request_id": request_id}, "decision": decision}

    try:
        # Pause here until record_response() puts the decision in.
        return decision.get(timeout=TIMEOUT_SECONDS)
    except queue.Empty:
        return "deny"
    finally:
        # Answered or timed out: no longer pending (/events tells the dashboard to close the popup).
        del _waiting[request_id]


def list_pending() -> list[dict]:
    """Every request still waiting for the user, as the dashboard should show it."""
    # list() takes a snapshot: other threads may add or remove requests while we read.
    return [w["details"] for w in list(_waiting.values())]


def record_response(request_id: str, decision: str) -> bool:
    """Hand the user's decision to the waiting /raise.

    Returns False if nothing is waiting on that id (unknown or already timed out).
    """
    waiting = _waiting.get(request_id)
    if waiting is None:
        return False
    waiting["decision"].put(decision)
    return True

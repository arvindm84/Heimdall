"""Blocked-request notifications. Used by /raise, /events and /response.

Flow:
    1. Firewall calls /raise. raise_request() sends the request to the
       dashboard and then WAITS for the user's decision.
    2. /events streams the request to the dashboard, which shows the popup.
    3. User clicks Approve/Deny -> /response -> record_response() drops the
       decision into that request's queue, which wakes raise_request() up.
    4. /raise returns the decision to the firewall, which fulfils or denies
       the agent's MCP tool call.
"""

import queue
import uuid

# How long the firewall waits for the user before we treat it as a deny.
TIMEOUT_SECONDS = 120

# Raised requests on their way to the dashboard (/raise puts, /events gets).
_outbox: queue.Queue = queue.Queue()

# Requests waiting on the user: request_id -> queue the decision gets dropped into.
_waiting: dict[str, queue.Queue] = {}


def raise_request(details: dict) -> str:
    """Send the request to the dashboard and wait for the user.

    Returns "approve" or "deny" ("deny" if the user doesn't answer in time).
    """
    request_id = uuid.uuid4().hex
    _waiting[request_id] = queue.Queue()

    # Body as-is, plus the id the dashboard sends back on /response.
    _outbox.put({**details, "request_id": request_id})

    try:
        # Pause here until record_response() puts the decision in.
        return _waiting[request_id].get(timeout=TIMEOUT_SECONDS)
    except queue.Empty:
        return "deny"
    finally:
        del _waiting[request_id]


def next_request(timeout: float) -> dict | None:
    """Wait up to `timeout` seconds for the next raised request. None if nothing came."""
    try:
        return _outbox.get(timeout=timeout)
    except queue.Empty:
        return None


def record_response(request_id: str, decision: str) -> bool:
    """Hand the user's decision to the waiting /raise.

    Returns False if nothing is waiting on that id (unknown or already timed out).
    """
    waiting = _waiting.get(request_id)
    if waiting is None:
        return False
    waiting.put(decision)
    return True

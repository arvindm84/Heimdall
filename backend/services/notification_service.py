"""Blocked-request notifications. Used by /raise and /response."""


def raise_request(details: dict) -> str:
    """Store a blocked request so the dashboard can show it. Returns its id."""
    raise NotImplementedError


def record_response(request_id: str, decision: str) -> None:
    """Save the user's decision so the waiting firewall call can continue."""
    raise NotImplementedError

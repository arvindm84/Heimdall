"""Firewall events for the dashboard's activity feed. Used by /api/event and /api/events.

The gateway posts every decision it makes (tool calls, blocked model calls, hidden
instructions...) to /api/event, one JSON object per POST, each with a "kind" field.
See the Events table in firewall-integration.md for every kind and its fields.

We keep the most recent ones in memory, so a dashboard that reloads gets its feed
back. A back-end restart empties the feed (the gateway's log keeps the full record:
`docker compose logs gateway`).

Never log event bodies: `hidden_instruction` events hold text found in an email or page.
"""

from collections import deque
from datetime import datetime

# How many events to keep. The oldest is dropped first.
MAX_EVENTS = 500

_events: deque[dict] = deque(maxlen=MAX_EVENTS)
# No lock: the gateway posts events one at a time, in order, from a single thread,
# so only one add() runs at once.
_last_id = 0


def add(event: dict) -> dict:
    """Keep one event, stamped with an id and the time it arrived. Returns it as stored."""
    global _last_id
    _last_id += 1
    # The gateway's fields first, so it can't overwrite our id or time.
    stored = {**event, "id": _last_id, "time": datetime.now().isoformat(timespec="seconds")}
    _events.append(stored)
    return stored


def since(event_id: int) -> list[dict]:
    """Events with an id above `event_id`, oldest first. since(0) gives every event kept."""
    # list() takes a snapshot: add() may run in another thread while we read.
    return [event for event in list(_events) if event["id"] > event_id]


def clear() -> None:
    """Forget every event (tests use this)."""
    global _last_id
    _events.clear()
    _last_id = 0

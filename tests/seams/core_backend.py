"""Run C's real back end (backend/app.py) in a thread, for seam tests that need /api/raise."""

import json
import queue
import threading

import httpx
from werkzeug.serving import make_server

from backend import app as backend
from backend.services import notification_service


def start(port: int = 0):
    """Start the back end on 127.0.0.1:port (0: any free port).

    Returns (url, notification_service module, server); call server.shutdown() when done.
    """
    server = make_server("127.0.0.1", port, backend.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", notification_service, server


class Dashboard:
    """One /api/events connection kept open for its whole life, like the real dashboard.

    The stream has two kinds of message: a question (plain `data:`), and
    `event: resolved` when one was answered or timed out. Only questions are kept.
    """

    def __init__(self, url: str):
        self.raised: queue.Queue = queue.Queue()
        threading.Thread(target=self.listen, args=(url,), daemon=True).start()

    def listen(self, url: str) -> None:
        event = "message"
        with httpx.stream("GET", f"{url}/api/events", timeout=None) as stream:
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: ") and event == "message":
                    self.raised.put(json.loads(line.removeprefix("data: ")))
                elif not line:
                    event = "message"  # a blank line ends one SSE message

    def next(self, timeout: float = 60) -> dict:
        """The next raised question. Fails the test if none comes in `timeout` seconds."""
        try:
            return self.raised.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError(f"no question reached the dashboard in {timeout} s") from None


def answer(url: str, request_id: str, decision: str) -> int:
    """Click Approve or Deny on the dashboard. Returns the HTTP status."""
    return httpx.post(f"{url}/api/response", json={"request_id": request_id, "decision": decision}).status_code

"""Run C's real back end (backend/app.py) in a thread, for seam tests that need /raise."""

import importlib.util
import json
import queue
import sys
import threading
from pathlib import Path

import httpx
from werkzeug.serving import make_server

BACKEND = Path(__file__).parents[2] / "backend"


def start(port: int = 0):
    """Start the back end on 127.0.0.1:port (0: any free port) with an empty request queue.

    Returns (url, notification_service module, server); call server.shutdown() when done.
    """
    # Import it the way `python backend/app.py` does: with backend/ on the path. A fresh copy
    # each time: an earlier back end's /events threads would otherwise share its queue.
    sys.path.insert(0, str(BACKEND))
    for name in [name for name in sys.modules if name == "services" or name.startswith("services.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("heimdall_backend_app", BACKEND / "app.py")
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    notifications = sys.modules["services.notification_service"]
    server = make_server("127.0.0.1", port, backend.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", notifications, server


class Dashboard:
    """One /events connection kept open for its whole life, like the real dashboard.

    Opening a new connection per question would lose questions: the back end's
    thread for a closed connection still takes the next one off the queue.
    """

    def __init__(self, url: str):
        self.raised: queue.Queue = queue.Queue()
        threading.Thread(target=self.listen, args=(url,), daemon=True).start()

    def listen(self, url: str) -> None:
        with httpx.stream("GET", f"{url}/events", timeout=None) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    self.raised.put(json.loads(line.removeprefix("data: ")))

    def next(self, timeout: float = 60) -> dict:
        """The next raised question. Fails the test if none comes in `timeout` seconds."""
        try:
            return self.raised.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError(f"no question reached the dashboard in {timeout} s") from None


def answer(url: str, request_id: str, decision: str) -> int:
    """Click Approve or Deny on the dashboard. Returns the HTTP status."""
    return httpx.post(f"{url}/response", json={"request_id": request_id, "decision": decision}).status_code

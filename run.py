"""Start Heimdall as a desktop app.

    uv run python run.py      (from the repo root)

1. Starts the Flask back end on 127.0.0.1:8765 (debug off), in the background.
2. Opens a native window (pywebview) showing the UI that Flask serves.
3. Closing the window quits everything.

The UI must be built first: cd frontend && npm run build
For frontend development, use `npm run dev` in frontend/ instead (live reload in the browser).
"""

import sys
import threading
import time
import urllib.request

import webview  # pywebview

from backend.app import FRONTEND_DIST, PORT, app

URL = f"http://127.0.0.1:{PORT}/"


def start_backend() -> None:
    # Only the app window (which loads / and gets the session cookie) may call /api.
    app.config["REQUIRE_TOKEN"] = True
    # threaded=True: /api/raise waits up to 2 minutes and /api/events never ends,
    # so each request needs its own thread. No debug and no reloader in the app.
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True, use_reloader=False)


def wait_until_up(timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    sys.exit(f"Back end did not start on {URL}. Is something else using port {PORT}?")


def main() -> None:
    if not (FRONTEND_DIST / "index.html").exists():
        sys.exit("The UI isn't built yet. Run: cd frontend && npm install && npm run build")

    # Daemon thread: it stops automatically when the window closes and main() returns.
    threading.Thread(target=start_backend, daemon=True).start()
    wait_until_up()

    webview.create_window("Heimdall", URL, width=1280, height=840, min_size=(960, 640), background_color="#111714")
    webview.start()


if __name__ == "__main__":
    main()

"""Flask back end for the dashboard.

Run from the repo root:
    uv run python -m backend.app     development (cd frontend && npm run dev starts this for you)
    uv run python run.py             the desktop app (native window, debug off)

Routes (all under /api):
    GET  /api/agents    Agents and providers the UI can offer, and open chats.   (owner: launch/kill)
    POST /api/launch    Start an agent with the user's permissions and model.    (owner: launch/kill)
    POST /api/stop      Stop an agent's container.                               (owner: launch/kill)
    POST /api/kill      Kill and remove an agent's container.                    (owner: launch/kill)
    POST /api/raise     Firewall reports a blocked request to the dashboard.     (owner: raise/response)
    GET  /api/events    Stream the dashboard listens on for raised requests.     (owner: raise/response)
    POST /api/response  User's answer to a halted-request notification.          (owner: raise/response)

Everything else serves the built frontend (frontend/dist), so the desktop window
loads the UI and the API from one address: http://127.0.0.1:8765

Routes stay thin: read the JSON body, call a service, return JSON.
The real work lives in services/.
"""

import json
import os
import subprocess
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from backend.services import agent_service, notification_service

# Not 5000: macOS AirPlay Receiver uses that port.
PORT = 8765

# Where Docker Desktop usually puts the `docker` command. An app opened from Finder or the Dock
# doesn't load ~/.zprofile, so `docker` may be missing from PATH even when it's installed.
# Appended (not prepended) so a PATH that already finds docker keeps winning.
DOCKER_DIRS = [
    Path.home() / ".docker" / "bin",
    Path("/usr/local/bin"),
    Path("/opt/homebrew/bin"),
    Path("/Applications/Docker.app/Contents/Resources/bin"),
]
os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), *(str(d) for d in DOCKER_DIRS if d.is_dir())])

# The built UI (made by `npm run build` in frontend/). Flask serves these files as-is.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = Flask(__name__, static_folder=str(FRONTEND_DIST), static_url_path="")


# Helper Methods

def missing(body: dict, *fields: str):
    """Return a 400 response if any required field is missing, else None."""
    absent = [f for f in fields if f not in body]
    if absent:
        return jsonify({"error": f"missing fields: {', '.join(absent)}"}), 400
    return None


# Errors raised by the services, turned into JSON the frontend can show.

@app.errorhandler(ValueError)
def bad_request(error):
    # Unknown agent or provider, bad folder, wrong config shape
    # (pydantic's ValidationError is a ValueError too).
    return jsonify({"error": str(error)}), 400


@app.errorhandler(subprocess.CalledProcessError)
def docker_failed(error):
    # A docker compose command failed. Its stderr says why (Docker not running,
    # port in use, build error...), so pass the end of it on.
    detail = (error.stderr or "").strip()[-2000:]
    if "Cannot connect to the Docker daemon" in detail:
        return jsonify({"error": "Docker isn't running. Open Docker Desktop and try again.", "detail": detail}), 503
    return jsonify({"error": "docker compose failed", "detail": detail}), 500


@app.errorhandler(FileNotFoundError)
def program_missing(error):
    # subprocess raises this when the `docker` command itself doesn't exist.
    if error.filename == "docker":
        return jsonify({"error": "Docker isn't installed. Install Docker Desktop, open it, and try again."}), 503
    return jsonify({"error": str(error)}), 500


@app.errorhandler(TimeoutError)
def chat_timeout(error):
    # The container started but its chat never answered.
    return jsonify({"error": str(error)}), 504


@app.get("/api/agents")
def agents():
    # Returns: {"agents": [{"name", "chat"}], "providers": [{"name", "default_model"}]}
    # "chat" holds chat_url / chat_user / chat_token for agents launched from here, else null.
    return jsonify(agent_service.list_agents()), 200


@app.post("/api/launch")
def launch():
    # Body: {"agent": "openclaw" | "hermes", "config": {...}}
    # config (every field optional):
    #   folders     [{"path": "/abs/path", "label": "public"|"private"|"confidential", "write": false}]
    #   tools       ["files_read", "files_list"]
    #   memory      bool (Hermes only)
    #   delegation  bool (Hermes only)
    #   provider    "gemini" | "anthropic"
    #   model       model name; leave out for the provider's default
    # Returns: {"agent", "chat_url", "chat_user", "chat_token"}
    # Slow: answers once the agent's chat is up. Calling it again for a running
    # agent restarts it with the new config (new chat_token).
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent", "config"):
        return err
    if not isinstance(body["config"], dict):
        return jsonify({"error": "config must be an object"}), 400

    result = agent_service.launch_agent(body["agent"], body["config"])
    return jsonify(result), 201


@app.post("/api/stop")
def stop():
    # Body: {"agent": "openclaw" | "hermes"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent"):
        return err

    agent_service.stop_agent(body["agent"])
    return jsonify({"status": "stopped"}), 200


@app.post("/api/kill")
def kill():
    # Body: {"agent": "openclaw" | "hermes"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent"):
        return err

    agent_service.kill_agent(body["agent"])
    return jsonify({"status": "killed"}), 200


@app.post("/api/raise")
def raise_request():
    # Called by the firewall, not the frontend.
    # Body: {"container_id": "...", "question": "...", ...any other details}. Passed through as-is.
    # Waits until the user answers on the dashboard (up to 2 min, then deny).
    # Returns: {"decision": "approve" | "deny"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "container_id", "question"):
        return err

    decision = notification_service.raise_request(body)
    return jsonify({"decision": decision}), 200


@app.get("/api/events")
def events():
    # Called by the frontend once, and kept open: new EventSource("/api/events")
    # Two kinds of message:
    #   source.onmessage                       -> a request to show: the firewall's body + request_id
    #   source.addEventListener("resolved", …) -> {"request_id"}: answered or timed out, close its popup
    # Every new connection (e.g. after a reload) first gets all requests still pending.
    def stream():
        sent = set()  # request_ids this connection has shown
        last_write = time.monotonic()
        # Send something right away so the browser sees the stream open (Flask waits for the first yield).
        yield ": connected\n\n"

        while True:
            pending = {r["request_id"]: r for r in notification_service.list_pending()}

            # New requests -> show a popup. SSE format: "data: <json>" then a blank line.
            for request_id, req in pending.items():
                if request_id not in sent:
                    sent.add(request_id)
                    yield f"data: {json.dumps(req)}\n\n"
                    last_write = time.monotonic()

            # Requests that were shown but are no longer pending -> close their popup.
            for request_id in sent - pending.keys():
                sent.discard(request_id)
                yield f"event: resolved\ndata: {json.dumps({'request_id': request_id})}\n\n"
                last_write = time.monotonic()

            # Quiet for 15s: send an SSE comment so the connection isn't dropped as idle.
            if time.monotonic() - last_write >= 15:
                yield ": keepalive\n\n"
                last_write = time.monotonic()

            time.sleep(0.5)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache"})


@app.post("/api/response")
def response():
    # Called by the frontend when the user clicks Approve / Deny.
    # Body: {"request_id": "...", "decision": "approve" | "deny"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "request_id", "decision"):
        return err
    if body["decision"] not in ("approve", "deny"):
        return jsonify({"error": "decision must be 'approve' or 'deny'"}), 400

    # Wakes up the /raise call that's waiting on this request_id.
    if not notification_service.record_response(body["request_id"], body["decision"]):
        return jsonify({"error": "no request waiting with that id (unknown or timed out)"}), 404
    return jsonify({"status": "recorded"}), 200


@app.get("/")
def index():
    # The UI's entry page. Its JS/CSS/fonts are served automatically from FRONTEND_DIST.
    if not (FRONTEND_DIST / "index.html").exists():
        return "Frontend not built yet. Run: cd frontend && npm run build", 503
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    # Development only. The desktop app uses run.py, with debug off.
    # 127.0.0.1 only: the back end must never be reachable from the network.
    # threaded: /api/raise waits up to 2 minutes and /api/events never ends.
    app.run(host="127.0.0.1", port=PORT, debug=True, threaded=True)

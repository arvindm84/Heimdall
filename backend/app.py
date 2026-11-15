"""Flask back end for the dashboard.

Routes (all under /api):
    POST /api/launch    Start an agent's container from the frontend's config.   (owner: launch/kill)
    POST /api/kill      Kill a specific agent container.                          (owner: launch/kill)
    POST /api/raise     Firewall reports a blocked request to the dashboard.      (owner: raise/response)
    GET  /api/events    Stream the dashboard listens on for raised requests.      (owner: raise/response)
    POST /api/response  User's answer to a halted-request notification.           (owner: raise/response)

Everything else serves the built frontend (frontend/dist), so the desktop window
loads the UI and the API from one address: http://127.0.0.1:8765

Routes stay thin: read the JSON body, call a service, return JSON.
The real work lives in services/.
"""

import json
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from services import docker_service, notification_service

# Not 5000: macOS AirPlay Receiver uses that port.
PORT = 8765

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


@app.post("/api/launch")
def launch():
    # Body: {"agent": "openclaw" | "hermes", "config": {...}}
    # config holds folders, tools, network access, model, etc.
    # Returns: container id and the address of the agent's chat UI.
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent", "config"):
        return err

    result = docker_service.launch_agent(body["agent"], body["config"])
    return jsonify(result), 201


@app.post("/api/kill")
def kill():
    # Body: {"container_id": "..."}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "container_id"):
        return err

    docker_service.kill_agent(body["container_id"])
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
    # Development only (npm run dev starts this). The desktop app uses run.py, with debug off.
    # 127.0.0.1 only: the back end must never be reachable from the network.
    app.run(host="127.0.0.1", port=PORT, debug=True)

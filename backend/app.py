"""Flask back end for the dashboard.

Routes:
    POST /launch    Start an agent's container from the frontend's config.   (owner: launch/kill)
    POST /kill      Kill a specific agent container.                          (owner: launch/kill)
    POST /raise     Firewall reports a blocked request to the dashboard.      (owner: raise/response)
    GET  /events    Stream the dashboard listens on for raised requests.      (owner: raise/response)
    POST /response  User's answer to a halted-request notification.           (owner: raise/response)

Routes stay thin: read the JSON body, call a service, return JSON.
The real work lives in services/.
"""

import json

from flask import Flask, Response, jsonify, request

from services import docker_service, notification_service

app = Flask(__name__)


# Helper Methods

def missing(body: dict, *fields: str):
    """Return a 400 response if any required field is missing, else None."""
    absent = [f for f in fields if f not in body]
    if absent:
        return jsonify({"error": f"missing fields: {', '.join(absent)}"}), 400
    return None


@app.post("/launch")
def launch():
    # Body: {"agent": "openclaw" | "hermes", "config": {...}}
    # config holds folders, tools, network access, model, etc.
    # Returns: container id and the address of the agent's chat UI.
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent", "config"):
        return err

    result = docker_service.launch_agent(body["agent"], body["config"])
    return jsonify(result), 201


@app.post("/kill")
def kill():
    # Body: {"container_id": "..."}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "container_id"):
        return err

    docker_service.kill_agent(body["container_id"])
    return jsonify({"status": "killed"}), 200


@app.post("/raise")
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


@app.get("/events")
def events():
    # Called by the frontend once, and kept open: new EventSource(".../events")
    # Each raised request is sent down this stream as one SSE message.
    def stream():
        while True:
            req = notification_service.next_request(timeout=15)
            if req is None:
                # Nothing raised for 15s: send an SSE comment so the connection isn't dropped as idle.
                yield ": keepalive\n\n"
            else:
                # SSE message format: "data: <json>" followed by a blank line.
                yield f"data: {json.dumps(req)}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache"})


@app.post("/response")
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


if __name__ == "__main__":
    # 127.0.0.1 only: the back end must never be reachable from the network.
    app.run(host="127.0.0.1", port=5000, debug=True)

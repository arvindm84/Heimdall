"""Flask back end for the dashboard.

Run from the repo root:  uv run python -m backend.app

Routes:
    GET  /agents    Agents and providers the UI can offer, and open chats.   (owner: launch/kill)
    POST /launch    Start an agent with the user's permissions and model.    (owner: launch/kill)
    POST /stop      Stop an agent's container.                               (owner: launch/kill)
    POST /kill      Kill and remove an agent's container.                    (owner: launch/kill)
    POST /raise     Firewall reports a blocked request to the dashboard.     (owner: raise/response)
    GET  /events    Stream the dashboard listens on for raised requests.     (owner: raise/response)
    POST /response  User's answer to a halted-request notification.          (owner: raise/response)

Routes stay thin: read the JSON body, call a service, return JSON.
The real work lives in services/.
"""

import json
import subprocess

from flask import Flask, Response, jsonify, request

from backend.services import agent_service, notification_service

app = Flask(__name__)


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
    return jsonify({"error": "docker compose failed", "detail": detail}), 500


@app.errorhandler(TimeoutError)
def chat_timeout(error):
    # The container started but its chat never answered.
    return jsonify({"error": str(error)}), 504


@app.get("/agents")
def agents():
    # Returns: {"agents": [{"name", "chat"}], "providers": [{"name", "default_model"}]}
    # "chat" holds chat_url / chat_user / chat_token for agents launched from here, else null.
    return jsonify(agent_service.list_agents()), 200


@app.post("/launch")
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


@app.post("/stop")
def stop():
    # Body: {"agent": "openclaw" | "hermes"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent"):
        return err

    agent_service.stop_agent(body["agent"])
    return jsonify({"status": "stopped"}), 200


@app.post("/kill")
def kill():
    # Body: {"agent": "openclaw" | "hermes"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "agent"):
        return err

    agent_service.kill_agent(body["agent"])
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
    app.run(host="127.0.0.1", port=5050, debug=True)

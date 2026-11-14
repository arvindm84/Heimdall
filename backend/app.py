"""Flask back end for the dashboard.

Routes:
    POST /launch    Start an agent's container from the frontend's config.   (owner: launch/kill)
    POST /kill      Kill a specific agent container.                          (owner: launch/kill)
    POST /raise     Firewall reports a blocked request to the dashboard.      (owner: raise/response)
    POST /response  User's answer to a halted-request notification.           (owner: raise/response)

Routes stay thin: read the JSON body, call a service, return JSON.
The real work lives in services/.
"""

from flask import Flask, jsonify, request

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
    # Body: what was blocked (agent, action, destination, reason). Passed through as-is.
    # Returns: a request id the firewall can wait on for the user's decision.
    body = request.get_json(silent=True) or {}

    request_id = notification_service.raise_request(body)
    return jsonify({"request_id": request_id}), 201


@app.post("/response")
def response():
    # Called by the frontend when the user clicks Approve / Deny.
    # Body: {"request_id": "...", "decision": "approve" | "deny"}
    body = request.get_json(silent=True) or {}
    if err := missing(body, "request_id", "decision"):
        return err

    notification_service.record_response(body["request_id"], body["decision"])
    return jsonify({"status": "recorded"}), 200


if __name__ == "__main__":
    # 127.0.0.1 only: the back end must never be reachable from the network.
    app.run(host="127.0.0.1", port=5000, debug=True)

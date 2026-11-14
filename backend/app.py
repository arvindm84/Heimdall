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


@app.post("/launch")
def launch():
    # Body: agent name plus its config from the frontend
    # (folders, tools, network access, model, etc.).
    # Returns: container id and the address of the agent's chat UI.
    # TODO: validate body, call docker_service.launch_agent(...)
    return jsonify({"error": "not implemented"}), 501


@app.post("/kill")
def kill():
    # Body: container id (or agent name) to kill.
    # TODO: call docker_service.kill_agent(...)
    return jsonify({"error": "not implemented"}), 501


@app.post("/raise")
def raise_request():
    # Called by the firewall, not the frontend.
    # Body: what was blocked (agent, action, destination, reason).
    # Returns: a request id the firewall can wait on for the user's decision.
    # TODO: call notification_service.raise_request(...)
    return jsonify({"error": "not implemented"}), 501


@app.post("/response")
def response():
    # Called by the frontend when the user clicks Approve / Deny.
    # Body: request id and the decision.
    # TODO: call notification_service.record_response(...)
    return jsonify({"error": "not implemented"}), 501


if __name__ == "__main__":
    # 127.0.0.1 only: the back end must never be reachable from the network.
    app.run(host="127.0.0.1", port=5000, debug=True)

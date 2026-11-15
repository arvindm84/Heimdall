"""Starting and stopping agents. Used by /launch, /stop, /kill and /agents.

This is a thin layer over agents/manager.py, which does the real work:
it writes each agent's config, tells the gateway about its permissions and
runs the containers with docker compose.

There is one container per agent. Launching an agent that is already running
recreates it with the new config, which is how permission changes are applied.

Launch agents one at a time: two launches at once would both run docker
compose and rewrite the same gateway config file.
"""

import subprocess
from pathlib import Path

from agents import manager
from backend.services import folder_service, key_service
from core.contracts.agents import AgentPermissions

# Agents we've launched: name -> what /launch returned (chat address and login).
# Lets the dashboard get the chat details back after a page reload.
_opened: dict[str, dict] = {}


def launch_agent(agent: str, config: dict) -> dict:
    """Start `agent` with the user's choices and return how to reach its chat.

    config:
        folders     [{"path": "/abs/path", "label": "public" | "private" | "confidential", "write": false}]
                    Left out (as the app does): the folders this agent's user labelled in the
                    folder-access popup (folder_service.granted_folders). [] means no folders.
        tools       any of files_list, files_read, files_write, gmail_read, gmail_draft, gmail_send, web_fetch
        skills      names of installed skills, OpenClaw only
        memory      bool, Hermes only
        delegation  bool, Hermes only
        provider    "gemini" | "anthropic" (default "gemini")
        model       model name, or leave out for the provider's default

    Returns {"agent", "chat_url", "chat_user", "chat_token"}.
    Raises ValueError (also pydantic's ValidationError) for anything invalid.
    """
    config = dict(config)
    provider = config.pop("provider", None) or "gemini"
    model = config.pop("model", None)

    # No folder list in the request: use what the user chose for this agent in the popup.
    if "folders" not in config:
        config["folders"] = folder_service.granted_folders(agent)

    # Checks the shape: unknown labels, wrong types, etc.
    permissions = AgentPermissions(**config)

    # Catch bad folders here, before they're written into the gateway's config.
    for folder in permissions.folders:
        path = Path(folder.path)
        if not path.is_absolute():
            raise ValueError(f"folder path must be absolute: {folder.path}")
        if not path.is_dir():
            raise ValueError(f"folder does not exist: {folder.path}")

    # Keys saved in the app go to the gateway (only) when compose starts it.
    key_service.put_in_environment()

    # Slow: waits until the agent's chat answers (minutes on the first build).
    opened = manager.open_agent(agent, permissions, provider, model)
    _opened[agent] = opened.model_dump()
    return _opened[agent]


def stop_agent(agent: str) -> None:
    """Stop the agent's container but keep it, so it can be started again."""
    manager.stop_agent(agent)
    _opened.pop(agent, None)


def kill_agent(agent: str) -> None:
    """Kill and remove the agent's container (the kill switch)."""
    manager.kill_agent(agent)
    _opened.pop(agent, None)


def kill_all() -> None:
    """Kill and remove every Heimdall container: both agents, their chat UIs and the gateway.

    Called by run.py when the app window closes, so no agent keeps running with nobody
    watching. Covers agents started by an earlier run of the app too. Never raises:
    closing the app must work even when Docker is stopped or missing.
    """
    _opened.clear()
    try:
        # --timeout 0: kill at once instead of waiting 10 seconds for each container.
        manager.compose("down", "--timeout", "0")
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Couldn't stop the agents' containers: {error}")


def list_agents() -> dict:
    """What the UI can offer: agents, providers, and which agents are open now."""
    return {
        "agents": [
            # "chat" is None unless this back end launched the agent.
            {"name": name, "chat": _opened.get(name)}
            for name in manager.AGENTS
        ],
        "providers": [
            {"name": name, "default_model": default_model}
            for name, default_model in manager.PROVIDERS.items()
        ],
    }

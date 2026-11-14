"""Starting and stopping agent containers. Used by /launch and /kill."""


def launch_agent(agent: str, config: dict) -> dict:
    """Build/start the container for `agent` with the given config.

    Should return the container id and the chat UI address.
    """
    raise NotImplementedError


def kill_agent(container_id: str) -> None:
    """Kill and remove the given container."""
    raise NotImplementedError

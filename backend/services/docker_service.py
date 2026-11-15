"""Starting and stopping agent containers. Used by /launch and /kill.

Each agent has a folder under images/<agent>/ holding its Dockerfile.
Launching builds that image the first time, then runs a new container from it.

TODO: we still need a way to map containers to agents (which container is
which agent, its chat UI port, etc.). For now launch just starts the container.
"""

from pathlib import Path

import docker
from docker.errors import ImageNotFound

# images/ lives at the repo root, two levels up from backend/services/.
IMAGES_DIR = Path(__file__).resolve().parents[2] / "images"

# Agents we can launch. The name is also the folder under images/.
AGENTS = {"openclaw"}


def _image_tag(agent: str) -> str:
    """Name we build each agent's image under, e.g. heimdall-openclaw."""
    return f"heimdall-{agent}"


def launch_agent(agent: str, config: dict) -> dict:
    """Start a new container for `agent`. Every call starts a new container.

    `config` isn't used yet; later it will carry folders, tools, model, etc.
    Returns the new container's id.
    """
    if agent not in AGENTS:
        raise ValueError(f"unknown agent: {agent}")

    client = docker.from_env()
    tag = _image_tag(agent)

    # Build the image only if it doesn't exist yet.
    # (After editing a Dockerfile, delete the old image to force a rebuild:
    #  docker rmi heimdall-<agent>)
    try:
        client.images.get(tag)
    except ImageNotFound:
        client.images.build(path=str(IMAGES_DIR / agent), tag=tag, rm=True)

    # detach=True returns right away and leaves the container running.
    container = client.containers.run(tag, detach=True)

    return {"container_id": container.id}


def kill_agent(container_id: str) -> None:
    """Kill and remove the given container.

    Raises docker.errors.NotFound if no container has that id.
    """
    client = docker.from_env()
    container = client.containers.get(container_id)

    # force=True kills the container first if it's still running.
    container.remove(force=True)

"""Hermes: what it is allowed to do and how its config is built."""

import json
from pathlib import Path

from core.contracts.agents import AgentPermissions

PORT = 7682
FAKE_KEY = "sk-fake-hermes-01"
# The gateway's route to the local model (Ollama on the host); nothing leaves the computer.
LOCAL_URL = "http://gateway:8080/model/local"


def build_config(permissions: AgentPermissions, provider: str, model: str) -> dict:
    if permissions.skills:
        raise ValueError("hermes does not support skills yet")
    config = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    config["model"] = {"default": model, "provider": provider}
    if provider == "local":
        # Hermes's own name for any OpenAI-style server. The gateway passes it on to Ollama.
        config["model"] = {"default": model, "provider": "custom", "base_url": LOCAL_URL, "api_key": FAKE_KEY}
    # Memory is the gateway's labelled notes (memory_read, memory_write), not Hermes's own:
    # its own notes go into the prompt without passing the firewall, so they carry no label.
    memory_tools = ["memory_read", "memory_write"] if permissions.memory else []
    config["mcp_servers"]["heimdall"]["tools"]["include"] = [*permissions.tools, *memory_tools]
    toolsets = config["platform_toolsets"]["cli"]
    if permissions.delegation:
        toolsets.append("delegation")
    return config

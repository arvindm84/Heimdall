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
    config["mcp_servers"]["heimdall"]["tools"]["include"] = list(permissions.tools)
    toolsets = config["platform_toolsets"]["cli"]
    if permissions.memory:
        toolsets.append("memory")
        config["memory"]["memory_enabled"] = True
    if permissions.delegation:
        toolsets.append("delegation")
    return config

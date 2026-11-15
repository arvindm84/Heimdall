"""Hermes: what it is allowed to do and how its config is built."""

import json
from pathlib import Path

from agents.permissions import AgentPermissions

PORT = 7682
FAKE_KEY = "sk-fake-hermes-01"


def build_config(permissions: AgentPermissions, provider: str, model: str) -> dict:
    config = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    config["model"] = {"default": model, "provider": provider}
    config["mcp_servers"]["heimdall"]["tools"]["include"] = list(permissions.tools)
    toolsets = config["platform_toolsets"]["cli"]
    if permissions.memory:
        toolsets.append("memory")
        config["memory"]["memory_enabled"] = True
    if permissions.delegation:
        toolsets.append("delegation")
    return config

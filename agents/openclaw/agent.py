"""OpenClaw: what it is allowed to do and how its config is built."""

import json
from pathlib import Path

from core.contracts.agents import AgentPermissions

PORT = 7681
FAKE_KEY = "sk-fake-openclaw-01"
# The API OpenClaw speaks to the gateway's /model route for each provider.
MODEL_API = {"gemini": "openai-completions", "anthropic": "anthropic-messages", "local": "openai-completions"}
# The local model (Ollama on the host) has its own route on the gateway; nothing leaves the computer.
LOCAL_URL = "http://gateway:8080/model/local"


def build_config(permissions: AgentPermissions, provider: str, model: str) -> dict:
    if permissions.memory or permissions.delegation:
        raise ValueError("openclaw does not support memory or delegation yet")
    config = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    entry = config["models"]["providers"]["heimdall"]
    entry["api"] = MODEL_API[provider]
    if provider == "local":
        entry["baseUrl"] = LOCAL_URL
    entry["models"][0]["id"] = entry["models"][0]["name"] = model
    config["agents"]["defaults"]["model"]["primary"] = f"heimdall/{model}"
    config["tools"]["alsoAllow"] = [f"heimdall__{tool}" for tool in permissions.tools]
    return config

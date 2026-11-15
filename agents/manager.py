"""Shared by every agent: start, stop and kill containers, and tell the gateway about them."""

import base64
import importlib
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from agents.permissions import AgentPermissions, OpenedAgent

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
GATEWAY_CONFIG = DATA_DIR / "gateway" / "gateway.yaml"
CHAT_USER = "heimdall"
AGENTS = ("openclaw", "hermes")
# provider -> (host the gateway proxy allows, default model)
PROVIDERS = {
    "gemini": ("generativelanguage.googleapis.com", "gemini-flash-lite-latest"),
    "anthropic": ("api.anthropic.com", "claude-haiku-4-5"),
}


def profile(agent: str):
    """The agent's own module: PORT, FAKE_KEY and build_config()."""
    if agent not in AGENTS:
        raise ValueError(f"unknown agent: {agent}")
    return importlib.import_module(f"agents.{agent}.agent")


def build_gateway_config(current: dict, agent: str, permissions: AgentPermissions, provider: str) -> dict:
    """The interim gateway.yaml the firewall reads: folders, agents, allowed provider hosts."""
    folders = {folder["path"]: folder for folder in current.get("folders", [])}
    for folder in permissions.folders:
        folders[folder.path] = {"path": folder.path, "label": folder.label, "writable": folder.write}
    entries = {entry["name"]: entry for entry in current.get("agents", [])}
    entries[agent] = {
        "name": agent,
        "fake_key": profile(agent).FAKE_KEY,
        "folders": [folder.path for folder in permissions.folders],
        "tools": list(permissions.tools),
        "provider": provider,
    }
    return {
        "providers": {"allow": [host for host, _ in PROVIDERS.values()]},
        "folders": list(folders.values()),
        "agents": list(entries.values()),
    }


def open_agent(
    agent: str, permissions: AgentPermissions, provider: str = "gemini", model: str | None = None
) -> OpenedAgent:
    module = profile(agent)
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    model = model or PROVIDERS[provider][1]
    config_path = DATA_DIR / "agents" / f"{agent}.json"
    _write_json(config_path, module.build_config(permissions, provider, model))
    current = json.loads(GATEWAY_CONFIG.read_text(encoding="utf-8")) if GATEWAY_CONFIG.exists() else {}
    _write_json(GATEWAY_CONFIG, build_gateway_config(current, agent, permissions, provider))
    token = secrets.token_urlsafe(24)
    env = {
        f"HEIMDALL_{agent.upper()}_TOKEN": token,
        f"HEIMDALL_{agent.upper()}_CONFIG": str(config_path),
    }
    compose("up", "-d", "--build", "gateway", env=env)
    compose("up", "-d", "--build", "--no-deps", "--force-recreate", agent, f"{agent}-ui", env=env)
    opened = OpenedAgent(
        agent=agent, chat_url=f"http://127.0.0.1:{module.PORT}/", chat_user=CHAT_USER, chat_token=token
    )
    _wait_for_chat(opened)
    return opened


def stop_agent(agent: str) -> None:
    profile(agent)
    compose("stop", agent, f"{agent}-ui")


def kill_agent(agent: str) -> None:
    profile(agent)
    compose("kill", agent, f"{agent}-ui")
    compose("rm", "-f", agent, f"{agent}-ui")


def chat_status(chat_url: str, token: str) -> int | None:
    request = urllib.request.Request(chat_url)
    basic = base64.b64encode(f"{CHAT_USER}:{token}".encode()).decode()
    request.add_header("Authorization", f"Basic {basic}")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return None


def compose(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout + result.stderr


def _write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def _wait_for_chat(opened: OpenedAgent, timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if chat_status(opened.chat_url, opened.chat_token) == 200:
            return
        time.sleep(1)
    raise TimeoutError(f"{opened.agent} chat did not come up")

import base64
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.contracts.agents import AgentPermissions, OpenedAgent

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "agents"
MCP_SERVER = "heimdall"
CHAT_USER = "heimdall"
PROVIDERS = ("gemini", "anthropic")
GEMINI_BASE_URL = "http://gateway:8080/gemini/v1beta"


def build_openclaw_config(permissions: AgentPermissions, provider: str = "gemini") -> dict:
    if permissions.memory or permissions.delegation:
        raise ValueError("openclaw does not support memory or delegation yet")
    config = _template("openclaw", "openclaw.json")
    if provider == "gemini":
        model = config["models"]["providers"][MCP_SERVER]
        model["baseUrl"] = GEMINI_BASE_URL
        model["api"] = "google-generative-ai"
    config["tools"]["alsoAllow"] = [f"{MCP_SERVER}__{tool}" for tool in permissions.tools]
    return config


def build_hermes_config(permissions: AgentPermissions, provider: str = "gemini") -> dict:
    config = _template("hermes", "config.json")
    config["model"]["provider"] = provider
    config["mcp_servers"][MCP_SERVER]["tools"]["include"] = list(permissions.tools)
    toolsets = config["platform_toolsets"]["cli"]
    if permissions.memory:
        toolsets.append("memory")
        config["memory"]["memory_enabled"] = True
    if permissions.delegation:
        toolsets.append("delegation")
    return config


@dataclass(frozen=True)
class AgentProfile:
    port: int
    config_file: str
    build_config: Callable[[AgentPermissions, str], dict]

    @property
    def chat_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


PROFILES = {
    "openclaw": AgentProfile(7681, "openclaw.json", build_openclaw_config),
    "hermes": AgentProfile(7682, "config.yaml", build_hermes_config),
}


def open_agent(agent: str, permissions: AgentPermissions, provider: str = "gemini") -> OpenedAgent:
    profile = _profile(agent)
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    config_path = DATA_DIR / agent / profile.config_file
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(profile.build_config(permissions, provider), indent=2), encoding="utf-8")
    token = secrets.token_urlsafe(24)
    env = {
        f"HEIMDALL_{agent.upper()}_TOKEN": token,
        f"HEIMDALL_{agent.upper()}_CONFIG": str(config_path),
    }
    _compose("up", "-d", "--build", "gateway", env=env)
    _compose("up", "-d", "--build", "--no-deps", "--force-recreate", *_services(agent), env=env)
    opened = OpenedAgent(agent=agent, chat_url=profile.chat_url, chat_user=CHAT_USER, chat_token=token)
    _wait_for_chat(opened)
    return opened


def restart_with(agent: str, permissions: AgentPermissions, provider: str = "gemini") -> OpenedAgent:
    return open_agent(agent, permissions, provider)


def stop_agent(agent: str) -> None:
    _profile(agent)
    _compose("stop", *_services(agent))


def kill_agent(agent: str) -> None:
    _profile(agent)
    _compose("kill", *_services(agent))
    _compose("rm", "-f", *_services(agent))


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


def _profile(agent: str) -> AgentProfile:
    if agent not in PROFILES:
        raise ValueError(f"unknown agent: {agent}")
    return PROFILES[agent]


def _services(agent: str) -> list[str]:
    return [agent, f"{agent}-ui"]


def _template(agent: str, name: str) -> dict:
    return json.loads((ROOT / "images" / agent / name).read_text(encoding="utf-8"))


def _compose(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_for_chat(opened: OpenedAgent, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if chat_status(opened.chat_url, opened.chat_token) == 200:
            return
        time.sleep(1)
    raise TimeoutError(f"{opened.agent} chat did not come up")

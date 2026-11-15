import base64
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.contracts.agents import AgentPermissions, OpenedAgent

ROOT = Path(__file__).resolve().parents[2]
CONFIG_TEMPLATE = ROOT / "images" / "openclaw" / "openclaw.json"
DATA_DIR = ROOT / "data" / "agents"
SERVICES = ["openclaw", "openclaw-ui"]
MCP_SERVER = "heimdall"
CHAT_URL = "http://127.0.0.1:7681/"
CHAT_USER = "heimdall"


def build_config(permissions: AgentPermissions) -> dict:
    config = json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8"))
    config["tools"]["alsoAllow"] = [f"{MCP_SERVER}__{tool}" for tool in permissions.tools]
    return config


def open_agent(agent: str, permissions: AgentPermissions) -> OpenedAgent:
    _check_agent(agent)
    config_path = DATA_DIR / agent / "openclaw.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(build_config(permissions), indent=2), encoding="utf-8")
    token = secrets.token_urlsafe(24)
    env = {"HEIMDALL_CHAT_TOKEN": token, "HEIMDALL_OPENCLAW_CONFIG": str(config_path)}
    _compose("up", "-d", "--build", "gateway", env=env)
    _compose("up", "-d", "--build", "--no-deps", "--force-recreate", *SERVICES, env=env)
    _wait_for_chat(token)
    return OpenedAgent(agent=agent, chat_url=CHAT_URL, chat_user=CHAT_USER, chat_token=token)


def restart_with(agent: str, permissions: AgentPermissions) -> OpenedAgent:
    return open_agent(agent, permissions)


def stop_agent(agent: str) -> None:
    _check_agent(agent)
    _compose("stop", *SERVICES)


def kill_agent(agent: str) -> None:
    _check_agent(agent)
    _compose("kill", *SERVICES)
    _compose("rm", "-f", *SERVICES)


def chat_status(token: str) -> int | None:
    request = urllib.request.Request(CHAT_URL)
    basic = base64.b64encode(f"{CHAT_USER}:{token}".encode()).decode()
    request.add_header("Authorization", f"Basic {basic}")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return None


def _check_agent(agent: str) -> None:
    if agent != "openclaw":
        raise ValueError(f"unknown agent: {agent}")


def _compose(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_for_chat(token: str, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if chat_status(token) == 200:
            return
        time.sleep(1)
    raise TimeoutError("agent chat did not come up")

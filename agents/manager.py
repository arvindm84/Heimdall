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

from agents import skills
from core.contracts.agents import AgentPermissions, OpenedAgent

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "data" / "agents"
# Compose override the manager writes: user folders mounted into the gateway.
FOLDER_MOUNTS = ROOT / "data" / "gateway" / "compose.folders.yaml"
CHAT_USER = "heimdall"
AGENTS = ("openclaw", "hermes")
TOOLS = ("files_list", "files_read", "files_write", "gmail_read", "gmail_draft", "gmail_send", "web_fetch")
# provider -> default model
PROVIDERS = {"gemini": "gemini-flash-lite-latest", "anthropic": "claude-haiku-4-5"}


def profile(agent: str):
    """The agent's own module: PORT, FAKE_KEY and build_config()."""
    if agent not in AGENTS:
        raise ValueError(f"unknown agent: {agent}")
    return importlib.import_module(f"agents.{agent}.agent")


def gateway_folder_mounts(permission_sets: list[AgentPermissions]) -> list[dict]:
    """Compose volumes that put every allowed folder in the gateway at /data/folders/<folder name>.

    Agents never get these folders; they read files only through the gateway's tools.
    """
    mounts: dict[str, dict] = {}
    for folder in (folder for permissions in permission_sets for folder in permissions.folders):
        source = Path(folder.path).expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"not a folder: {folder.path}")
        mount = mounts.setdefault(
            source.name,
            {"type": "bind", "source": str(source), "target": f"/data/folders/{source.name}", "read_only": True},
        )
        if mount["source"] != str(source):
            raise ValueError(f"two allowed folders are both named {source.name}")
        if folder.write:
            mount["read_only"] = False
    return list(mounts.values())


def write_permissions(agent: str, permissions: AgentPermissions, provider: str = "gemini") -> None:
    """What the gateway reads: this agent's permissions.json, and the folder mounts for all agents."""
    others = [
        AgentPermissions(**json.loads(path.read_text(encoding="utf-8"))["permissions"])
        for path in AGENTS_DIR.glob("*/permissions.json")
        if path.parent.name != agent
    ]
    # Another agent's folder that was deleted since can't be mounted; drop it instead of
    # refusing to open this agent. This agent's own folders must still exist.
    others = [
        other.model_copy(update={"folders": [f for f in other.folders if Path(f.path).expanduser().is_dir()]})
        for other in others
    ]
    mounts = gateway_folder_mounts([*others, permissions])
    # Store each folder's resolved path: its last part is the name it is mounted under,
    # which is how the gateway finds the folder ("." or "~/docs" would not match).
    resolved = [
        folder.model_copy(update={"path": str(Path(folder.path).expanduser().resolve())})
        for folder in permissions.folders
    ]
    # A new run_id each open tells the gateway to start a fresh session for this agent.
    content = {
        "provider": provider,
        "run_id": secrets.token_hex(8),
        "fake_key": profile(agent).FAKE_KEY,
        "permissions": permissions.model_copy(update={"folders": resolved}).model_dump(),
    }
    _write_json(AGENTS_DIR / agent / "permissions.json", content)
    _write_json(FOLDER_MOUNTS, {"services": {"gateway": {"volumes": mounts}}})


def open_agent(
    agent: str, permissions: AgentPermissions, provider: str = "gemini", model: str | None = None
) -> OpenedAgent:
    module = profile(agent)
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    config_path = AGENTS_DIR / agent / "config.json"
    _write_json(config_path, module.build_config(permissions, provider, model or PROVIDERS[provider]))
    write_permissions(agent, permissions, provider)
    token = secrets.token_urlsafe(24)
    env = {
        f"HEIMDALL_{agent.upper()}_TOKEN": token,
        f"HEIMDALL_{agent.upper()}_CONFIG": str(config_path),
    }
    if agent == "openclaw":
        env["HEIMDALL_OPENCLAW_SKILLS"] = str(skills.stage(agent, permissions.skills))
    compose("up", "-d", "--build", "gateway", env=env)
    compose("up", "-d", "--build", "--no-deps", "--force-recreate", agent, f"{agent}-ui", env=env)
    opened = OpenedAgent(
        agent=agent, chat_url=f"http://127.0.0.1:{module.PORT}/", chat_user=CHAT_USER, chat_token=token
    )
    _wait_for_chat(opened)
    return opened


def stop_agent(agent: str) -> None:
    profile(agent)
    if agent == "hermes":
        try:
            memory("hermes", "snapshot")
        except subprocess.CalledProcessError:
            pass
    compose("stop", agent, f"{agent}-ui")


def kill_agent(agent: str) -> None:
    profile(agent)
    compose("kill", agent, f"{agent}-ui")
    compose("rm", "-f", agent, f"{agent}-ui")


def memory(agent: str, *args: str) -> str:
    """Hermes memory snapshots: memory(agent, "list" | "show" | "snapshot" | "rollback", [id])."""
    if agent != "hermes":
        raise ValueError(f"{agent} has no memory")
    return compose("exec", "-T", agent, "heimdall-memory", *args)


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
    files = ["-f", "compose.yaml"]
    if FOLDER_MOUNTS.exists():
        files += ["-f", str(FOLDER_MOUNTS)]
    result = subprocess.run(
        ["docker", "compose", *files, *args],
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

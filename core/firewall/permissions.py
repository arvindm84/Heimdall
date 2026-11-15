"""Reads an agent's permissions.json, which B's agent manager writes when it opens the agent.

Shape: {"run_id": "...", "fake_key": "...", "provider": "gemini", "model": "...", "permissions": AgentPermissions}.
"provider" is the model provider the user chose ("gemini", "anthropic" or "local") and
"model" the model; when present, the model proxy refuses calls to any other cloud
provider, or to another model at the chosen provider.
Read on every tool call: the file is small, and a reopen (new permissions, new
run_id) takes effect at once.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from pydantic import ValidationError

from core.contracts.agents import AgentPermissions

# "C:\..." or "C:/...": a Windows path, because the user's host may be Windows.
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class NoPermissions(Exception):
    """The agent was not opened by Heimdall, or its permissions file doesn't match its key."""


@dataclass(frozen=True)
class AgentRun:
    agent: str
    run_id: str
    permissions: AgentPermissions
    provider: str | None = None
    model: str | None = None


def load(agents_dir: Path, agent: str, key: str) -> AgentRun:
    """This agent's current run. Raises NoPermissions if anything is off (fail closed)."""
    path = agents_dir / agent / "permissions.json"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        permissions = AgentPermissions.model_validate(stored["permissions"])
        run_id, fake_key = str(stored["run_id"]), stored["fake_key"]
        provider, model = stored.get("provider"), stored.get("model")
        if any(value is not None and not isinstance(value, str) for value in (provider, model)):
            raise TypeError("provider and model must be strings")
    except FileNotFoundError as error:
        raise NoPermissions(f"no permissions file for {agent}") from error
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
        raise NoPermissions(f"unreadable permissions file for {agent}") from error
    # A second check on identity: the key on the call must be the one the manager gave this agent.
    if fake_key != key:
        raise NoPermissions(f"permissions file for {agent} names a different key")
    return AgentRun(agent=agent, run_id=run_id, permissions=permissions, provider=provider, model=model)


def folder_name(host_path: str) -> str:
    """The name a folder is mounted under in the gateway: the last part of its host path.

    B's manager mounts each folder at /data/folders/<that name>. The host may be
    Windows or POSIX, so parse the path the way that host would.
    """
    windows = "\\" in host_path or WINDOWS_DRIVE.match(host_path)
    return (PureWindowsPath(host_path) if windows else PurePosixPath(host_path)).name

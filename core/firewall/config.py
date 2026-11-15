"""Gateway settings, read from the gateway container's environment.

Each agent's permissions are not here: they are read from
<agents_dir>/<agent>/permissions.json on every tool call (core/firewall/permissions.py).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GatewaySettings:
    """Everything the gateway needs to know at start-up. Real keys live only here, never in agents."""

    # Fake key -> agent name. The fake key is how we tell agents apart.
    fake_keys: dict[str, str] = field(default_factory=dict)
    # True: answer model calls with a scripted reply (no network, no key). For tests and offline demos.
    mock: bool = False
    gemini_key: str = ""
    anthropic_key: str = ""
    # Where B's agent manager mounts permissions.json files and the user's folders.
    agents_dir: Path = Path("/config/agents")
    folders_dir: Path = Path("/data/folders")


def parse_fake_keys(text: str) -> dict[str, str]:
    """Turn 'openclaw:sk-fake-openclaw-01,hermes:sk-fake-hermes-01' into {key: agent}.

    Items without a colon are skipped.
    """
    pairs = (item.split(":", 1) for item in text.split(",") if ":" in item)
    return {key.strip(): agent.strip() for agent, key in pairs}


def load_settings(env: dict[str, str] | None = None) -> GatewaySettings:
    """Build settings from the environment (or a given dict, for tests).

    B's agents/gateway/compose.yaml sets HEIMDALL_FAKE_KEYS; the real keys come from .env.
    """
    env = dict(os.environ) if env is None else env
    return GatewaySettings(
        fake_keys=parse_fake_keys(env.get("HEIMDALL_FAKE_KEYS", "")),
        mock=env.get("HEIMDALL_PROVIDER") == "mock",
        gemini_key=env.get("GEMINI_API_KEY", ""),
        anthropic_key=env.get("ANTHROPIC_API_KEY", ""),
        agents_dir=Path(env.get("HEIMDALL_AGENTS_DIR", "/config/agents")),
        folders_dir=Path(env.get("HEIMDALL_FOLDERS_DIR", "/data/folders")),
    )

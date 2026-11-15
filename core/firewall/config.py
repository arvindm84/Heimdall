"""Gateway settings.

Step 0 reads everything from the gateway container's environment. Step 1 adds
/config/gateway.json (folder labels, providers) and each agent's
AgentPermissions from core/contracts/agents.py.
"""

import os
from dataclasses import dataclass, field
from typing import Literal

# Where the gateway sends an agent's model calls. "mock" answers locally with a
# scripted reply, so tests and B's container checks need no network or key.
Provider = Literal["mock", "anthropic", "openrouter"]


@dataclass(frozen=True)
class GatewaySettings:
    """Everything the gateway needs to know at start-up. Real keys live only here, never in agents."""

    # Fake key -> agent name. The fake key is how we tell agents apart.
    fake_keys: dict[str, str] = field(default_factory=dict)
    provider: Provider = "mock"
    anthropic_key: str = ""
    # The gateway, not the agent, chooses the model. Defaults match the fake gateway.
    anthropic_model: str = "claude-sonnet-5-5"
    openrouter_key: str = ""
    openrouter_model: str = "anthropic/claude-haiku-4.5"


def parse_fake_keys(text: str) -> dict[str, str]:
    """Turn 'openclaw:sk-fake-openclaw-01,hermes:sk-fake-hermes-01' into {key: agent}.

    Items without a colon are skipped.
    """
    pairs = (item.split(":", 1) for item in text.split(",") if ":" in item)
    return {key.strip(): agent.strip() for agent, key in pairs}


def pick_provider(env: dict[str, str]) -> Provider:
    """Use HEIMDALL_PROVIDER if it names a known provider.

    Otherwise follow the fake gateway's rule: OpenRouter if its key is set, then
    Anthropic, else the mock.
    """
    chosen = env.get("HEIMDALL_PROVIDER", "")
    if chosen in ("mock", "anthropic", "openrouter"):
        return chosen
    if env.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if env.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "mock"


def load_settings(env: dict[str, str] | None = None) -> GatewaySettings:
    """Build settings from the environment (or a given dict, for tests)."""
    env = dict(os.environ) if env is None else env
    defaults = GatewaySettings()
    return GatewaySettings(
        # Default matches HEIMDALL_FAKE_KEY in compose.yaml, so B's setup works unchanged.
        fake_keys=parse_fake_keys(env.get("HEIMDALL_FAKE_KEYS", "openclaw:sk-fake-openclaw-01")),
        provider=pick_provider(env),
        anthropic_key=env.get("ANTHROPIC_API_KEY", ""),
        # `or` so an empty line in .env (OPENROUTER_MODEL=) still gets the default.
        anthropic_model=env.get("ANTHROPIC_MODEL") or defaults.anthropic_model,
        openrouter_key=env.get("OPENROUTER_API_KEY", ""),
        openrouter_model=env.get("OPENROUTER_MODEL") or defaults.openrouter_model,
    )

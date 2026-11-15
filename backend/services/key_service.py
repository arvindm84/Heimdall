"""The user's real model API keys. Used by /api/keys and by agent_service before a launch.

Keys live in the system's key store (macOS Keychain, Windows Credential Manager) via
`keyring`, never in a file in the repo. They go to one place only: the gateway
container, which swaps each agent's fake key for the real one. Never into an agent,
an event, a log line or an API response.

How a saved key reaches the gateway: before a launch, put_in_environment() copies the
saved keys into this process's environment. agents/manager.py passes that environment
to `docker compose`, and agents/gateway/compose.yaml hands GEMINI_API_KEY and
ANTHROPIC_API_KEY to the gateway. A key saved in the app wins over one in .env.
The gateway reads its keys when it starts, so a changed key needs the gateway recreated
(the next launch does that).
"""

import os

import keyring

# Name the keys are filed under in the key store.
SERVICE = "heimdall"
# provider -> the environment variable the gateway reads. The local model needs no key.
KEY_ENV = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def _check(provider: str) -> None:
    if provider not in KEY_ENV:
        raise ValueError(f"provider must be one of: {', '.join(KEY_ENV)}")


def set_key(provider: str, key: str) -> None:
    """Save (or replace) the key for a provider. An empty key removes it."""
    _check(provider)
    key = key.strip()
    if not key:
        remove_key(provider)
        return
    keyring.set_password(SERVICE, provider, key)


def remove_key(provider: str) -> None:
    _check(provider)
    try:
        keyring.delete_password(SERVICE, provider)
    except keyring.errors.PasswordDeleteError:
        pass  # nothing saved


def saved() -> dict[str, bool]:
    """Which providers have a key saved in the app, e.g. {"gemini": True, "anthropic": False}."""
    return {provider: bool(keyring.get_password(SERVICE, provider)) for provider in KEY_ENV}


# Variables put_in_environment() set, so a key removed in the app stops being passed on.
_set_here: set[str] = set()


def put_in_environment() -> None:
    """Copy every saved key into this process's environment, for docker compose to pass on."""
    for provider, variable in KEY_ENV.items():
        key = keyring.get_password(SERVICE, provider)
        if key:
            os.environ[variable] = key
            _set_here.add(variable)
        elif variable in _set_here:
            # Removed since the last launch. Compose then falls back to .env, if it has one.
            del os.environ[variable]
            _set_here.discard(variable)

"""Shared fixtures for the firewall tests. All keys here are made up."""

import pytest

from core.firewall import core_client
from core.firewall.config import GatewaySettings

FAKE_KEY = "sk-fake-openclaw-01"


@pytest.fixture
def anyio_backend():
    """Async tests run on asyncio, the same loop the gateway uses."""
    return "asyncio"


@pytest.fixture
def events(monkeypatch):
    """Capture events instead of printing them. Returns the list they land in."""
    captured: list[dict] = []
    monkeypatch.setattr(core_client, "emit", lambda kind, **fields: captured.append({"kind": kind, **fields}))
    return captured


@pytest.fixture
def mock_settings():
    """One agent (openclaw) using the mock provider: no network, no real key."""
    return GatewaySettings(fake_keys={FAKE_KEY: "openclaw"}, provider="mock")

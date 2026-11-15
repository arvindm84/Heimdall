"""Closing the app kills every Heimdall container (agent_service.kill_all, called by run.py)."""

import subprocess
import threading
import time

from agents import manager
from backend.services import agent_service


def test_kill_all_takes_everything_down_at_once_and_forgets_open_chats(monkeypatch):
    commands = []
    monkeypatch.setattr(manager, "compose", lambda *args, **kwargs: commands.append(args) or "")
    agent_service._opened["openclaw"] = {"agent": "openclaw"}

    agent_service.kill_all()

    assert commands == [("down", "--timeout", "0")]
    assert agent_service._opened == {}


def test_kill_all_does_not_raise_when_docker_is_missing_or_stopped(monkeypatch):
    # Closing the app must never crash or hang because Docker isn't there.
    def no_docker(*args, **kwargs):
        raise FileNotFoundError(2, "No such file", "docker")

    def daemon_down(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "docker", stderr="Cannot connect to the Docker daemon")

    for failure in (no_docker, daemon_down):
        monkeypatch.setattr(manager, "compose", failure)
        agent_service.kill_all()  # no exception


def test_kill_all_gives_up_waiting_on_a_stuck_docker(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(manager, "compose", lambda *args, **kwargs: release.wait(5))

    started = time.monotonic()
    agent_service.kill_all(timeout=0.2)

    assert time.monotonic() - started < 2
    release.set()

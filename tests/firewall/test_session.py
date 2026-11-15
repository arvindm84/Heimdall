"""Sessions: one per agent run; a new run starts clean."""

from core.firewall.labels import Label
from core.firewall.session import Sessions


def test_same_run_gives_the_same_session():
    sessions = Sessions()
    first = sessions.for_run("openclaw", "run-1")
    first.raise_label(Label.CONFIDENTIAL)
    assert sessions.for_run("openclaw", "run-1") is first


def test_new_run_starts_a_fresh_session():
    sessions = Sessions()
    old = sessions.for_run("openclaw", "run-1")
    old.raise_label(Label.CONFIDENTIAL)
    old.mark_untrusted()
    new = sessions.for_run("openclaw", "run-2")
    assert new.label == Label.PUBLIC
    assert new.untrusted is False
    assert new.delimiter != old.delimiter


def test_agents_have_separate_sessions():
    sessions = Sessions()
    assert sessions.for_run("openclaw", "run-1") is not sessions.for_run("hermes", "run-1")

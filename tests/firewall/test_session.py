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


def test_a_restarted_gateway_picks_the_session_back_up(tmp_path):
    before = Sessions(tmp_path / "gateway.db")
    session = before.for_run("openclaw", "run-1")
    session.raise_label(Label.CONFIDENTIAL)
    session.mark_untrusted()
    before.save(session)
    after = Sessions(tmp_path / "gateway.db").for_run("openclaw", "run-1")  # a new process
    assert (after.label, after.untrusted, after.delimiter) == (Label.CONFIDENTIAL, True, session.delimiter)


def test_a_new_run_after_a_restart_still_starts_clean(tmp_path):
    before = Sessions(tmp_path / "gateway.db")
    session = before.for_run("openclaw", "run-1")
    session.mark_untrusted()
    before.save(session)
    assert Sessions(tmp_path / "gateway.db").for_run("openclaw", "run-2").untrusted is False

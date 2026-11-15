"""Labels: an ordered scale that a session can only move up."""

from core.firewall.labels import Label, from_contract, join
from core.firewall.session import Session


def test_join_takes_the_higher_label():
    assert join(Label.PUBLIC, Label.CONFIDENTIAL) == Label.CONFIDENTIAL
    assert join(Label.CONFIDENTIAL, Label.PRIVATE) == Label.CONFIDENTIAL


def test_contract_strings_map_to_labels():
    assert from_contract("public") == Label.PUBLIC
    assert from_contract("private") == Label.PRIVATE
    assert from_contract("confidential") == Label.CONFIDENTIAL


def test_session_label_never_goes_down():
    session = Session(agent="openclaw", run_id="run-1")
    session.raise_label(Label.CONFIDENTIAL)
    session.raise_label(Label.PUBLIC)
    assert session.label == Label.CONFIDENTIAL

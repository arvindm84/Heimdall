"""The placeholder vault: typed, consistent, reversible placeholders per session (PAPILLON-style)."""

import pytest

from core.firewall.vault import Vault


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "gateway.db")


def test_same_value_gets_the_same_placeholder(vault):
    text, counts = vault.redact("Mail sam@example.com, then cc sam@example.com.", "openclaw:run-1")
    assert text == "Mail {{EMAIL_1}}, then cc {{EMAIL_1}}."
    assert counts == {"EMAIL": 2}


def test_numbering_continues_across_calls_in_a_session(vault):
    vault.redact("sam@example.com", "openclaw:run-1")
    text, _ = vault.redact("ana@example.com and sam@example.com", "openclaw:run-1")
    assert text == "{{EMAIL_2}} and {{EMAIL_1}}"


def test_values_match_ignoring_formatting(vault):
    # The same phone or email written differently is the same person's data.
    text, _ = vault.redact("Call (608) 555-0142 or 608-555-0142. Mail Sam@Example.com, sam@example.com.", "s")
    assert text == "Call {{PHONE_1}} or {{PHONE_1}}. Mail {{EMAIL_1}}, {{EMAIL_1}}."


def test_each_session_has_its_own_numbering(vault):
    vault.redact("sam@example.com", "openclaw:run-1")
    text, _ = vault.redact("ana@example.com", "openclaw:run-2")
    assert text == "{{EMAIL_1}}"


def test_fill_restores_the_original(vault):
    redacted, _ = vault.redact("Write to Sam@Example.com at 608-555-0142.", "openclaw:run-1")
    filled, unknown = vault.fill(redacted, "openclaw:run-1")
    assert filled == "Write to Sam@Example.com at 608-555-0142."
    assert unknown == []


def test_fill_leaves_another_sessions_placeholder_and_reports_it(vault):
    vault.redact("sam@example.com", "openclaw:run-1")
    filled, unknown = vault.fill("Send to {{EMAIL_1}}", "hermes:run-9")
    assert filled == "Send to {{EMAIL_1}}"
    assert unknown == ["{{EMAIL_1}}"]


def test_redact_with_nothing_personal_changes_nothing(vault):
    assert vault.redact("The garden opens at nine.", "s") == ("The garden opens at nine.", {})


def test_vault_survives_reopening_the_database(tmp_path):
    Vault(tmp_path / "gateway.db").redact("sam@example.com", "openclaw:run-1")
    filled, _ = Vault(tmp_path / "gateway.db").fill("{{EMAIL_1}}", "openclaw:run-1")
    assert filled == "sam@example.com"

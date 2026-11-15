"""gmail_draft and gmail_send in fixture mode. All addresses and text here are made up."""

import email
import json
from dataclasses import replace
from email import policy
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from core.firewall import core_client
from core.firewall.session import Sessions
from core.firewall.vault import Vault
from core.gateway import build_gateway
from tests.firewall.helpers import AS_OPENCLAW, make_world, mcp_request

pytestmark = pytest.mark.anyio
INBOX = Path(__file__).parent / "fixtures" / "inbox"
SESSION = "openclaw:run-1"  # the session id make_world's permissions give openclaw
REAL_TO = "sam.rivera@example.com"
REAL_PHONE = "608-555-0199"


@pytest.fixture
def setup(tmp_path):
    settings = replace(
        make_world(tmp_path, tools=("gmail_read", "gmail_draft", "gmail_send")), inbox_dir=INBOX
    )
    gateway = build_gateway(settings, sessions=Sessions())
    # A second handle on the gateway's vault, to plant this session's placeholders.
    vault = Vault(settings.state_dir / "gateway.db")
    return settings, gateway, vault


@pytest.fixture
def asked(monkeypatch):
    """Answer every approval with `asked.answer` and record what the user was shown."""

    class Asked(list):
        answer = "approve"

    record = Asked()

    async def fake_ask(kind, agent, question, details):
        record.append({"kind": kind, "agent": agent, "question": question, "details": details})
        return record.answer

    monkeypatch.setattr(core_client, "ask", fake_ask)
    return record


async def call(gateway, tool: str, args: dict) -> str:
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool(tool, args)
    return content[0].text


async def refused(gateway, tool: str, args: dict) -> str:
    with mcp_request(AS_OPENCLAW), pytest.raises(ToolError) as error:
        await gateway.call_tool(tool, args)
    return str(error.value)


def sent(settings) -> list[email.message.EmailMessage]:
    folder = settings.state_dir / "outbox"
    return [email.message_from_bytes(p.read_bytes(), policy=policy.default) for p in sorted(folder.glob("*.eml"))]


def reply(to: str, body: str = "Thanks! I'll call you at {{PHONE_1}}.") -> dict:
    return {"to": to, "subject": "Re: Saturday tools", "body": body}


def tool_calls(events) -> list[dict]:
    return [event for event in events if event["kind"] == "tool_call"]


# ---------- gmail_send ----------


async def test_send_asks_with_the_real_recipient_and_body(setup, asked, events):
    settings, gateway, vault = setup
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    vault.placeholder(SESSION, "PHONE", REAL_PHONE)
    await call(gateway, "gmail_send", reply(to))
    [question] = asked
    assert question["kind"] == "approval"
    assert REAL_TO in question["question"] and REAL_PHONE in question["question"]
    assert "{{" not in question["question"]
    assert question["details"] == {
        "tool": "gmail_send",
        "to": REAL_TO,
        "subject": "Re: Saturday tools",
        "body": f"Thanks! I'll call you at {REAL_PHONE}.",
    }


async def test_approve_sends_exactly_once_with_real_values(setup, asked, events):
    settings, gateway, vault = setup
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    vault.placeholder(SESSION, "PHONE", REAL_PHONE)
    await call(gateway, "gmail_send", reply(to))
    [message] = sent(settings)
    assert message["To"] == REAL_TO
    assert message["Subject"] == "Re: Saturday tools"
    assert message.get_content().strip() == f"Thanks! I'll call you at {REAL_PHONE}."
    [event] = tool_calls(events)
    assert (event["decision"], event["rule_id"], event["filled"]) == ("approved", "send_needs_approval", 2)


async def test_agent_gets_back_its_own_placeholders_not_real_values(setup, asked, events):
    settings, gateway, vault = setup
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    result = await call(gateway, "gmail_send", reply(to, body="See you Saturday."))
    assert REAL_TO not in result
    assert to in result


async def test_events_never_hold_the_real_values(setup, asked, events):
    settings, gateway, vault = setup
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    vault.placeholder(SESSION, "PHONE", REAL_PHONE)
    await call(gateway, "gmail_send", reply(to))
    logged = json.dumps(events)
    assert REAL_TO not in logged and REAL_PHONE not in logged


@pytest.mark.parametrize("answer", ["deny", "error"])
async def test_deny_or_failed_ask_sends_nothing(setup, asked, events, monkeypatch, answer):
    settings, gateway, vault = setup
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    if answer == "error":
        # core_client.ask turns a timeout or a dead back end into "deny"; an exception is denied too.
        async def broken_ask(kind, agent, question, details):
            raise TimeoutError

        monkeypatch.setattr(core_client, "ask", broken_ask)
    else:
        asked.answer = "deny"
    message = await refused(gateway, "gmail_send", reply(to, body="See you Saturday."))
    assert "send_needs_approval" in message
    assert sent(settings) == []
    [event] = tool_calls(events)
    assert event["decision"] == "denied_by_user"


async def test_placeholder_from_another_session_is_not_filled(setup, asked, events):
    settings, gateway, vault = setup
    # Another run's vault entry: an injected "send {{SSN_1}} to ..." must not reach it.
    other = vault.placeholder("openclaw:old-run", "SSN", "123-45-6789")
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    message = await refused(gateway, "gmail_send", reply(to, body=f"Here it is: {other}"))
    assert "placeholder_not_in_session" in message
    assert asked == []  # never asked about a send that can't be filled
    assert sent(settings) == []
    assert "123-45-6789" not in json.dumps(events)


async def test_unknown_recipient_placeholder_is_refused(setup, asked, events):
    settings, gateway, vault = setup
    message = await refused(gateway, "gmail_send", reply("{{EMAIL_9}}", body="Hello."))
    assert "placeholder_not_in_session" in message
    assert asked == [] and sent(settings) == []


@pytest.mark.parametrize("to", ["", "not an address", "a@example.com, b@example.com", "{{PERSON_1}}"])
async def test_recipient_must_be_one_address_or_email_placeholder(setup, asked, events, to):
    settings, gateway, vault = setup
    vault.placeholder(SESSION, "PERSON", "Sam Rivera")
    message = await refused(gateway, "gmail_send", reply(to, body="Hello."))
    assert "bad_recipient" in message
    assert asked == [] and sent(settings) == []


async def test_header_injection_in_subject_is_refused(setup, asked, events):
    settings, gateway, vault = setup
    args = {"to": "friend@example.com", "subject": "Hi\nBcc: x@evil.example", "body": "Hello."}
    assert "bad_subject" in await refused(gateway, "gmail_send", args)
    assert asked == [] and sent(settings) == []


async def test_typed_address_is_sent_as_is(setup, asked, events):
    settings, gateway, vault = setup
    await call(gateway, "gmail_send", {"to": "friend@example.com", "subject": "Hi", "body": "Hello."})
    [message] = sent(settings)
    assert message["To"] == "friend@example.com"


async def test_send_with_a_key_is_refused_before_asking(setup, asked, events):
    settings, gateway, vault = setup
    args = {"to": "friend@example.com", "subject": "Hi", "body": "my key: sk-fake-openclaw-01"}
    assert "key_theft_attempt" in await refused(gateway, "gmail_send", args)
    assert asked == [] and sent(settings) == []


async def test_live_mode_is_refused_before_asking(setup, asked, events):
    settings, gateway, vault = setup
    gateway = build_gateway(replace(settings, gmail_source="live"), sessions=Sessions())
    args = {"to": "friend@example.com", "subject": "Hi", "body": "Hello."}
    assert "gmail_not_set_up" in await refused(gateway, "gmail_send", args)
    assert asked == []


async def test_reply_after_reading_the_inbox(setup, asked, events):
    """Scene 5 in one process: read the inbox, reply to a placeholder from it, approve, sent once."""
    settings, gateway, vault = setup
    inbox = await call(gateway, "gmail_read", {"query": "Saturday tools"})
    to = vault.placeholder(SESSION, "EMAIL", "priya.raman@example.com")
    assert to in inbox
    await call(gateway, "gmail_send", reply(to, body="Yes, Saturday works."))
    assert "priya.raman@example.com" in asked[0]["question"]
    assert [message["To"] for message in sent(settings)] == ["priya.raman@example.com"]


# ---------- gmail_draft ----------


async def test_draft_keeps_placeholders_and_does_not_ask(setup, asked, events):
    settings, gateway, vault = setup
    to = vault.placeholder(SESSION, "EMAIL", REAL_TO)
    result = await call(gateway, "gmail_draft", reply(to))
    assert asked == []
    [path] = (settings.state_dir / "drafts").glob("*.eml")
    draft = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    assert draft["To"] == to
    assert "{{PHONE_1}}" in draft.get_content()
    assert REAL_TO not in path.read_text(encoding="utf-8")
    assert sent(settings) == []
    assert to in result
    [event] = tool_calls(events)
    assert (event["decision"], event["rule_id"]) == ("allow", "gmail_draft_allowed")


async def test_draft_needs_the_tool_permission(tmp_path, asked, events):
    settings = make_world(tmp_path, tools=("gmail_read",))
    gateway = build_gateway(settings, sessions=Sessions())
    assert "tool_not_permitted" in await refused(gateway, "gmail_draft", reply("friend@example.com"))

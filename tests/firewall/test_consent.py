"""Consent before Confidential file text goes to a cloud model (Step 6). All data is made up.

The agent reads a file from the Confidential folder `taxes` through the real tool,
then the test sends model requests holding that tool result to /model, the way
OpenClaw (OpenAI style) and an Anthropic-style agent would. Providers are faked.
"""

import json
from dataclasses import replace

import httpx
import pytest

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall import core_client
from core.firewall.confidential import ConfidentialStore, files_in
from core.firewall.session import Sessions
from core.gateway import build_gateway
from core.proxy.consent import WITHHELD
from tests.firewall.helpers import AS_OPENCLAW, FAKE_KEY, make_world, mcp_request, write_permissions

pytestmark = pytest.mark.anyio
RETURN = "Made-up 2025 return for Jordan Lee.\nAdjusted gross income: 71,250.\nRefund due: 1,140.\n"
HEADERS = {"authorization": f"Bearer {FAKE_KEY}"}
OLLAMA = "http://ollama.test/v1/chat/completions"


@pytest.fixture
def world(tmp_path, monkeypatch):
    settings = make_world(tmp_path, tools=("files_read", "gmail_send", "web_fetch"))
    (settings.folders_dir / "taxes" / "return.txt").write_text(RETURN, encoding="utf-8")
    settings = replace(settings, mock=False, gemini_key="AIza-test-not-real", anthropic_key="sk-ant-test-not-real",
                       ollama_url=OLLAMA)  # fmt: skip
    seen: list[httpx.Request] = []

    def provider(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    sessions = Sessions()
    gateway = build_gateway(settings, transport=httpx.MockTransport(provider), sessions=sessions)
    return settings, gateway, seen, sessions


@pytest.fixture
def asked(monkeypatch):
    """Answer every question with `asked.answer`; record (kind, details)."""

    class Asked(list):
        answer = "approve"
        scope = None

    record = Asked()

    async def fake_ask(kind, agent, question, details):
        record.append((kind, details, question))
        return record.answer

    async def fake_answer(kind, agent, question, details):
        record.append((kind, details, question))
        return core_client.Answer(record.answer, record.scope if record.answer == "approve" else None)

    monkeypatch.setattr(core_client, "ask", fake_ask)
    monkeypatch.setattr(core_client, "answer", fake_answer)
    return record


async def read(gateway, path="taxes/return.txt") -> str:
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool("files_read", {"path": path})
    return content[0].text


def openai_request(result: str) -> dict:
    """OpenClaw's shape: the assistant's tool call, then the tool message with its result."""
    return {
        "model": "gemini-flash-lite-latest",
        "messages": [
            {"role": "user", "content": "What is my refund?"},
            {"role": "assistant", "tool_calls": [{"id": "call_1", "type": "function",
             "function": {"name": "heimdall__files_read", "arguments": "{\"path\": \"taxes/return.txt\"}"}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": result},
        ],
    }  # fmt: skip


def anthropic_request(result: str) -> dict:
    return {
        "model": "claude-haiku-4-5",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "What is my refund?"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "heimdall__files_read",
             "input": {"path": "taxes/return.txt"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
             "content": [{"type": "text", "text": result}]}]},
        ],
    }  # fmt: skip


async def post(gateway, path: str, body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=gateway.streamable_http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        return await client.post(f"/model/{path}", json=body, headers=HEADERS)


def forwarded(seen: list[httpx.Request]) -> dict:
    return json.loads(seen[-1].content)


# ---------- markers ----------


async def test_confidential_text_comes_back_in_markers(world, asked):
    settings, gateway, seen, sessions = world
    text = await read(gateway)
    assert text.startswith("<<confidential:") and text.rstrip().endswith(">>")
    assert "Refund due: 1,140." in text


async def test_private_text_has_no_markers(world, asked):
    settings, gateway, seen, sessions = world
    assert "<<confidential:" not in await read(gateway, "docs/notes.txt")


# ---------- consent on model calls ----------


async def test_cloud_request_asks_once_and_approve_lets_it_through(world, asked, events):
    settings, gateway, seen, sessions = world
    result = await read(gateway)
    assert (await post(gateway, "chat/completions", openai_request(result))).status_code == 200
    [(kind, details, question)] = asked
    assert kind == "consent"
    assert details == {"file": "taxes/return.txt", "folder": "taxes", "provider": "Gemini"}
    assert "taxes/return.txt" in question and "Gemini" in question
    assert "Refund due: 1,140." in forwarded(seen)["messages"][2]["content"]
    # Later calls in the same session: no new question, still let through.
    await post(gateway, "chat/completions", openai_request(result))
    assert len(asked) == 1 and len(seen) == 2
    assert [e["decision"] for e in events if e["kind"] == "consent"] == ["approve"]


async def test_deny_withholds_the_block_and_still_forwards(world, asked, events):
    settings, gateway, seen, sessions = world
    asked.answer = "deny"
    result = await read(gateway)
    assert (await post(gateway, "chat/completions", openai_request(result))).status_code == 200
    body = forwarded(seen)
    assert body["messages"][2] == {"role": "tool", "tool_call_id": "call_1", "content": WITHHELD}
    # Still a valid request: the tool call and its result are both there.
    assert body["messages"][1]["tool_calls"][0]["id"] == "call_1"
    assert "1,140" not in seen[-1].content.decode()
    [withheld] = [e for e in events if e["kind"] == "model_withheld"]
    assert (withheld["rule_id"], withheld["files"]) == ("consent_denied", ["taxes/return.txt"])
    # The deny is remembered: the next call is withheld without asking again.
    await post(gateway, "chat/completions", openai_request(result))
    assert len(asked) == 1 and "1,140" not in seen[-1].content.decode()


async def test_anthropic_style_tool_result_is_withheld_too(world, asked):
    settings, gateway, seen, sessions = world
    asked.answer = "deny"
    result = await read(gateway)
    await post(gateway, "v1/messages", anthropic_request(result))
    block = forwarded(seen)["messages"][2]["content"][0]
    assert block == {"type": "tool_result", "tool_use_id": "toolu_1", "content": WITHHELD}
    assert asked[0][1]["provider"] == "Anthropic"
    assert str(seen[-1].url) == "https://api.anthropic.com/v1/messages"


async def test_stripped_markers_are_caught_by_the_text(world, asked):
    settings, gateway, seen, sessions = world
    asked.answer = "deny"
    await read(gateway)
    # The agent dropped the markers and kept one line of the file.
    await post(gateway, "chat/completions", openai_request("From the file: adjusted gross income: 71,250."))
    assert forwarded(seen)["messages"][2]["content"] == WITHHELD
    assert len(asked) == 1


async def test_unrelated_tool_results_are_left_alone(world, asked):
    settings, gateway, seen, sessions = world
    asked.answer = "deny"
    await read(gateway)
    await post(gateway, "chat/completions", openai_request("Made-up notes. The garden opens at nine."))
    assert asked == []
    assert forwarded(seen)["messages"][2]["content"] == "Made-up notes. The garden opens at nine."


async def test_local_model_is_never_asked(world, asked, events):
    settings, gateway, seen, sessions = world
    asked.answer = "deny"
    result = await read(gateway)
    assert (await post(gateway, "local/chat/completions", openai_request(result))).status_code == 200
    assert asked == []
    assert str(seen[-1].url) == OLLAMA
    assert "Refund due: 1,140." in forwarded(seen)["messages"][2]["content"]
    # The real keys never go to the local model either.
    assert "authorization" not in seen[-1].headers and "x-api-key" not in seen[-1].headers


async def test_local_model_requests_are_still_scanned_for_keys(world, asked):
    settings, gateway, seen, sessions = world
    response = await post(gateway, "local/chat/completions", openai_request("key: sk-fake-openclaw-01"))
    assert response.status_code == 403 and seen == []


async def test_a_new_run_starts_without_old_markers_or_answers(world, asked):
    settings, gateway, seen, sessions = world
    result = await read(gateway)
    await post(gateway, "chat/completions", openai_request(result))
    # B reopens the agent: new run_id, new session. Text from the old run isn't this session's.
    write_permissions(settings.agents_dir, AgentPermissions(tools=["files_read"], folders=[
        FolderAccess(path="/x/taxes", label="confidential")]), run_id="run-2")  # fmt: skip
    await post(gateway, "chat/completions", openai_request(result))
    assert len(asked) == 1


async def test_failed_ask_is_a_remembered_deny(world, monkeypatch, events):
    settings, gateway, seen, sessions = world
    calls = []

    async def broken_answer(kind, agent, question, details):
        calls.append(kind)
        raise RuntimeError("core down")

    monkeypatch.setattr(core_client, "answer", broken_answer)
    result = await read(gateway)
    await post(gateway, "chat/completions", openai_request(result))
    await post(gateway, "chat/completions", openai_request(result))
    assert calls == ["consent"]
    assert forwarded(seen)["messages"][2]["content"] == WITHHELD


async def test_mock_mode_asks_too(world, asked):
    """Offline demos use the mock model; consent still runs before it answers."""
    settings, gateway, seen, sessions = world
    gateway = build_gateway(replace(settings, mock=True), sessions=Sessions())
    result = await read(gateway)
    assert (await post(gateway, "chat/completions", openai_request(result))).status_code == 200
    assert [kind for kind, _, _ in asked] == ["consent"]


# ---------- tools after a Confidential read ----------


async def test_send_after_confidential_read_asks_for_consent(world, asked):
    settings, gateway, seen, sessions = world
    await read(gateway)
    with mcp_request(AS_OPENCLAW):
        await gateway.call_tool("gmail_send", {"to": "friend@example.com", "subject": "Hi", "body": "Hello."})
    [(kind, details, question)] = asked
    assert kind == "consent" and details["to"] == "friend@example.com"
    assert "Confidential" in question


async def test_fetch_after_confidential_read_asks_for_consent(world, asked):
    settings, gateway, seen, sessions = world
    await read(gateway)
    asked.answer = "deny"
    with mcp_request(AS_OPENCLAW), pytest.raises(Exception, match="fetch_with_confidential"):
        await gateway.call_tool("web_fetch", {"url": "https://example.com/"})
    assert [kind for kind, _, _ in asked] == ["consent"]


# ---------- matching on its own ----------


def test_short_lines_do_not_match_on_their_own(tmp_path):
    store = ConfidentialStore(tmp_path / "db")
    store.mark("s", "taxes/a.txt", "Total:\nYes\nAdjusted gross income: 71,250.")
    served = store.served("s")
    assert files_in("Total: Yes", served) == set()
    assert files_in("ADJUSTED   gross income: 71,250.", served) == {"taxes/a.txt"}


def test_markers_from_another_session_count_for_nothing(tmp_path):
    store = ConfidentialStore(tmp_path / "db")
    wrapped = store.mark("other", "taxes/a.txt", "x")
    assert files_in(wrapped, store.served("mine")) == set()


# ---------- only the provider the user chose ----------


def choose(settings, provider: str, model: str | None = None) -> None:
    """Add the user's provider (and model) choice to openclaw's permissions.json, as B's manager would."""
    path = settings.agents_dir / "openclaw" / "permissions.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    choice = {"provider": provider} | ({"model": model} if model else {})
    path.write_text(json.dumps({**stored, **choice}), encoding="utf-8")


@pytest.mark.parametrize(
    "chosen, path, allowed",
    [
        ("gemini", "chat/completions", True),
        ("gemini", "v1/messages", False),
        ("anthropic", "chat/completions", False),
        ("gemini", "local/chat/completions", True),  # the local model keeps data on the machine
        ("local", "chat/completions", False),
        ("local", "local/chat/completions", True),
    ],
)
async def test_only_the_chosen_provider_is_reached(world, asked, events, chosen, path, allowed):
    settings, gateway, seen, sessions = world
    choose(settings, chosen)
    body = anthropic_request("hi") if path.endswith("messages") else openai_request("hi")
    response = await post(gateway, path, body)
    assert (response.status_code != 403) is allowed
    assert bool(seen) is allowed
    if not allowed:
        [blocked] = [e for e in events if e["kind"] == "model_blocked"]
        assert blocked["rule_id"] == "provider_not_chosen"


@pytest.mark.parametrize(
    "sent, allowed",
    [("gemini-flash-lite-latest", True), ("models/gemini-flash-lite-latest", True), ("gemini-2.5-pro", False)],
)
async def test_only_the_chosen_model_is_reached(world, asked, events, sent, allowed):
    settings, gateway, seen, sessions = world
    choose(settings, "gemini", "gemini-flash-lite-latest")
    response = await post(gateway, "chat/completions", {**openai_request("hi"), "model": sent})
    assert (response.status_code != 403) is allowed
    assert bool(seen) is allowed
    if not allowed:
        [blocked] = [e for e in events if e["kind"] == "model_blocked"]
        assert blocked["rule_id"] == "model_not_chosen"


async def test_the_model_check_leaves_the_local_model_alone(world, asked):
    # Chose Gemini, but the local model is always allowed, whatever its name.
    settings, gateway, seen, sessions = world
    choose(settings, "gemini", "gemini-flash-lite-latest")
    response = await post(gateway, "local/chat/completions", {**openai_request("hi"), "model": "llama3.2:3b"})
    assert response.status_code == 200


async def test_no_provider_in_permissions_keeps_the_old_behaviour(world, asked):
    settings, gateway, seen, sessions = world
    assert (await post(gateway, "v1/messages", anthropic_request("hi"))).status_code == 200


# ---------- allow this file, or the whole folder ----------


async def two_files(settings, gateway) -> tuple[str, str]:
    (settings.folders_dir / "taxes" / "w2.txt").write_text("Made-up W-2. Wages: 64,000.\n", encoding="utf-8")
    return await read(gateway, "taxes/return.txt"), await read(gateway, "taxes/w2.txt")


@pytest.mark.parametrize("scope, questions", [("folder", 1), ("once", 2), (None, 2)])
async def test_always_for_this_folder_covers_its_other_files(world, asked, scope, questions):
    settings, gateway, seen, sessions = world
    asked.scope = scope
    first, second = await two_files(settings, gateway)
    await post(gateway, "chat/completions", openai_request(first))
    await post(gateway, "chat/completions", openai_request(second))
    assert len(asked) == questions
    assert WITHHELD not in json.dumps(json.loads(seen[-1].content))


async def test_allowing_a_folder_does_not_allow_another_agent_run(world, asked):
    settings, gateway, seen, sessions = world
    asked.scope = "folder"
    first = await read(gateway)
    await post(gateway, "chat/completions", openai_request(first))
    write_permissions(settings.agents_dir, AgentPermissions(tools=["files_read"], folders=[
        FolderAccess(path="/x/taxes", label="confidential")]), run_id="run-2")  # fmt: skip
    again = await read(gateway)
    await post(gateway, "chat/completions", openai_request(again))
    assert len(asked) == 2


async def test_one_file_spelled_two_ways_is_asked_about_once(world, asked):
    settings, gateway, seen, sessions = world
    first = await read(gateway, "taxes/return.txt")
    second = await read(gateway, "taxes/./return.txt")
    await post(gateway, "chat/completions", openai_request(first + second))
    assert [details["file"] for _, details, _ in asked] == ["taxes/return.txt"]

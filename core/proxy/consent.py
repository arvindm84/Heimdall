"""Consent before Confidential file text goes to a cloud model.

The model proxy runs this on every request to a cloud provider. It finds the
tool-result blocks holding text the gateway served from a Confidential folder in
this session (core/firewall/confidential.py), asks the user once per file per
session, and on deny replaces those blocks with a short note. The user can allow one
file ("once") or every file in its folder ("folder"); both last for this agent's run. The request is still
forwarded and stays valid: every tool call keeps its tool result, only the text
inside changes. Requests to the local model skip this: nothing leaves the machine.
"""

import asyncio
from collections import defaultdict

from core.firewall import core_client
from core.firewall.confidential import ConfidentialStore, files_in

WITHHELD = "[withheld by Heimdall: Confidential content, consent denied]"


def result_blocks(body: dict) -> list[dict]:
    """The tool results in a request, as dicts whose "content" holds the text.

    Anthropic style: {"type": "tool_result", "content": ...} inside a user message.
    OpenAI style: a message with "role": "tool".
    """
    blocks = []
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "tool":
            blocks.append(message)
        content = message.get("content")
        if isinstance(content, list):
            blocks += [part for part in content if isinstance(part, dict) and part.get("type") == "tool_result"]
    return blocks


def text_of(block: dict) -> str:
    """A tool result's text: a plain string, or the text parts of a list."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


class Consent:
    def __init__(self, store: ConfidentialStore):
        self.store = store
        # One question at a time per session, so two calls in flight don't both ask about one file.
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def check(self, body: dict, agent: str, session: str, provider: str) -> list[str]:
        """Ask about new Confidential files in `body`, withhold denied ones (in place).

        Returns the files withheld from this request.
        """
        served = self.store.served(session)
        if not served:
            return []
        holders = [(block, files_in(text_of(block), served)) for block in result_blocks(body)]
        files = sorted(set().union(*(held for _, held in holders)))
        async with self.locks[session]:
            for file in files:
                if self.decision(session, file) is None:
                    decision, scope = await self.ask(agent, file, provider)
                    # "Always for this folder": one answer for every file in it, for this run.
                    self.store.record(session, folder_key(file) if scope == "folder" else file, decision)
        denied = {file for file in files if self.decision(session, file) != "approve"}
        for block, held in holders:
            if held & denied:
                block["content"] = WITHHELD
        return sorted(denied)

    def decision(self, session: str, file: str) -> str | None:
        """This file's answer, or its folder's, or None if the user hasn't been asked."""
        return self.store.decision(session, file) or self.store.decision(session, folder_key(file))

    async def ask(self, agent: str, file: str, provider: str) -> tuple[str, str | None]:
        """Ask the user once. Returns (decision, scope). A failed ask is a deny, and is
        remembered like one, so a missing back end doesn't make every model call wait."""
        question = f"{agent} wants to send text from the Confidential file {file} to {provider}."
        details = {"file": file, "folder": folder_of(file), "provider": provider}
        try:
            answer = await core_client.answer("consent", agent, question, details)
        except Exception:  # noqa: BLE001 - fail closed on any error while asking
            answer = core_client.Answer("deny")
        decision = "approve" if answer.decision == "approve" else "deny"
        scope = answer.scope if decision == "approve" else None
        core_client.emit("consent", agent=agent, file=file, provider=provider, decision=decision, scope=scope)
        return decision, scope


def folder_of(file: str) -> str:
    """"taxes/2025/return.txt" -> "taxes": files are named <folder>/<path in it>."""
    return file.split("/", 1)[0]


def folder_key(file: str) -> str:
    """Where a whole-folder answer is kept: "taxes/" can't be a file's name (a file has a path after the slash)."""
    return f"{folder_of(file)}/"

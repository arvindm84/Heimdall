"""Consent before Confidential file text goes to a cloud model.

The model proxy runs this on every request to a cloud provider. It finds the
tool-result blocks holding text the gateway served from a Confidential folder in
this session (core/firewall/confidential.py), asks the user once per file per
session, and on deny replaces those blocks with a short note. The request is still
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
                if self.store.decision(session, file) is None:
                    self.store.record(session, file, await self.ask(agent, file, provider))
        denied = {file for file in files if self.store.decision(session, file) != "approve"}
        for block, held in holders:
            if held & denied:
                block["content"] = WITHHELD
        return sorted(denied)

    async def ask(self, agent: str, file: str, provider: str) -> str:
        """Ask the user once. A failed ask is a deny, and is remembered like one, so a
        missing back end doesn't make every model call wait for a timeout."""
        question = (
            f"{agent} wants to send text from the Confidential file {file} to {provider}. "
            "Allow it for this session?"
        )
        details = {"file": file, "folder": file.split("/", 1)[0], "provider": provider}
        try:
            answer = await core_client.ask("consent", agent, question, details)
        except Exception:  # noqa: BLE001 - fail closed on any error while asking
            answer = "deny"
        decision = "approve" if answer == "approve" else "deny"
        core_client.emit("consent", agent=agent, file=file, provider=provider, decision=decision)
        return decision

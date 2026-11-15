"""gmail_read: the user's mail, cleaned of hidden text before the agent sees it.

Fixture mode reads .eml files from a folder, so the demo works offline and tests
are repeatable. Live mode (the test Gmail account) is not built yet.
"""

import email
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

from core.firewall import injection, sanitize
from core.firewall.sanitize import Evidence, Removed, Untrusted

MAX_LIMIT = 20


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    date: datetime
    subject: str
    body: str  # what a reader would see
    removed: list[Removed]  # what was hidden in it


def read(inbox: Path, query: str, limit: int) -> list[Message]:
    """Newest first. `query` matches sender, subject or body, ignoring case."""
    messages = sorted((parse(path) for path in inbox.glob("*.eml")), key=lambda m: m.date, reverse=True)
    needle = query.casefold().strip()
    if needle:
        messages = [m for m in messages if needle in f"{m.sender}\n{m.subject}\n{m.body}".casefold()]
    return messages[: max(1, min(limit, MAX_LIMIT))]


def parse(path: Path) -> Message:
    message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    # Prefer the HTML part: that is what a mail client shows, and where hidden text lives.
    part = message.get_body(preferencelist=("html", "plain"))
    content = part.get_content() if part else ""
    cleaned = sanitize.html(content) if part and part.get_content_type() == "text/html" else sanitize.text(content)
    try:
        date = parsedate_to_datetime(message["Date"])
    except (TypeError, ValueError):
        date = datetime.fromtimestamp(0, tz=timezone.utc)
    return Message(
        id=path.stem,
        sender=sanitize.text(str(message["From"] or "")).text,
        date=date,
        subject=sanitize.text(str(message["Subject"] or "")).text,
        body=cleaned.text,
        removed=cleaned.removed,
    )


def as_untrusted(messages: list[Message]) -> Untrusted:
    """The text the agent gets, plus the hidden parts as evidence for the guard."""
    blocks, evidence = [], []
    for number, message in enumerate(messages, start=1):
        source = f"email '{message.subject}' from {message.sender}"
        evidence += [Evidence(source, removed) for removed in message.removed]
        lines = [
            f"Email {number} of {len(messages)}",
            f"From: {message.sender}",
            f"Date: {message.date:%Y-%m-%d %H:%M} UTC",
            f"Subject: {message.subject}",
        ]
        # Tell the agent something was taken out, so it can tell the user, without showing it.
        if injection.flag(message.removed):
            lines.append("[Heimdall removed hidden text from this email that looked like instructions.]")
        elif message.removed:
            lines.append(f"[Heimdall removed {len(message.removed)} hidden parts from this email.]")
        blocks.append("\n".join([*lines, "", message.body]))
    return Untrusted("\n\n---\n\n".join(blocks) or "(no emails match)", evidence)

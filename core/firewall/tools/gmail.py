"""Mail tools: gmail_read cleans the user's mail of hidden text before the agent sees
it; gmail_draft and gmail_send write mail out.

Fixture mode reads .eml files from a folder and writes drafts and sent mail as .eml
files in the gateway's state folder, so the demo works offline and shows what was
sent. Live mode (the test Gmail account) is not built yet.
"""

import email
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

from core.firewall import injection, sanitize
from core.firewall.sanitize import Evidence, Removed, Untrusted
from core.firewall.tools.files import Denied

MAX_LIMIT = 20
# One plain address, or one email placeholder the gateway fills in after approval.
RECIPIENT = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[^@\s,;<>\"]+|\{\{EMAIL_\d+\}\}")
# Who fixture-mode mail is from: a reserved name that can never be delivered.
FIXTURE_SENDER = "you@fixture.invalid"


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


# ---------- writing mail out ----------


def check_message(source: str, to: str, subject: str) -> None:
    """Up-front checks for gmail_draft and gmail_send, run before the user could be asked.

    source: settings.gmail_source. The recipient is one address or one {{EMAIL_n}}
    placeholder (a {{PERSON_n}} can't be mailed); the subject is one line, so the
    agent can't add headers such as Bcc.
    """
    if source != "fixture":
        raise Denied("gmail_not_set_up", "live Gmail is not set up yet")
    if not RECIPIENT.fullmatch(to.strip()):
        raise Denied("bad_recipient", "send to one email address or one {{EMAIL_n}} placeholder")
    if "\n" in subject or "\r" in subject:
        raise Denied("bad_subject", "the subject must be one line")


def save(folder: Path, to: str, subject: str, body: str) -> Path:
    """Write one email as an .eml file in `folder` (drafts or the fixture outbox). Returns its path."""
    message = EmailMessage(policy=policy.default)
    message["From"] = FIXTURE_SENDER
    message["To"] = to.strip()
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message.set_content(body)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.eml"
    try:
        path.write_bytes(message.as_bytes())
    except OSError as error:
        raise Denied("send_failed", f"could not save the email ({type(error).__name__})") from error
    return path

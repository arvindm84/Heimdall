"""The placeholder vault: personal data out, typed placeholders in, and back again.

Placeholders are typed and numbered per session ({{EMAIL_1}}, {{PERSON_2}}), and the
same value always gets the same placeholder within a session, so the agent's text
stays usable (PAPILLON). Real values stay here; agents only ever see placeholders.
`fill` is used only at an approved gmail_send (Step 5), with this session's values.

Stored in SQLite so a gateway restart keeps each run's numbering. The file holds real
personal data, so it lives in the gateway's own state folder, never in an agent.
"""

import re
import sqlite3
from pathlib import Path

from core.firewall import pii

PLACEHOLDER = re.compile(r"\{\{([A-Z]+)_(\d+)\}\}")


def match_key(kind: str, value: str) -> str:
    """What makes two values "the same": formatting differences don't count."""
    if kind in ("PHONE", "CARD", "SSN"):
        return "".join(char for char in value if char.isdigit())
    if kind == "EMAIL":
        return value.lower()
    return " ".join(value.split())


class Vault:
    def __init__(self, path: Path):
        self.path = path
        self._db: sqlite3.Connection | None = None

    def db(self) -> sqlite3.Connection:
        """Open the database on first use, so settings that never redact never touch disk."""
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.path)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS placeholders ("
                " session TEXT NOT NULL, kind TEXT NOT NULL, n INTEGER NOT NULL,"
                " key TEXT NOT NULL, value TEXT NOT NULL,"
                " PRIMARY KEY (session, kind, n), UNIQUE (session, kind, key))"
            )
        return self._db

    def redact(self, text: str, session: str) -> tuple[str, dict[str, int]]:
        """Replace personal data with placeholders. Returns the text and how many of each kind were replaced."""
        pieces, counts, last = [], {}, 0
        for span in pii.find(text):
            pieces += [text[last : span.start], self.placeholder(session, span.kind, span.value)]
            counts[span.kind] = counts.get(span.kind, 0) + 1
            last = span.end
        return "".join([*pieces, text[last:]]), counts

    def placeholder(self, session: str, kind: str, value: str) -> str:
        """This value's placeholder in this session, creating the next number if it's new."""
        db, key = self.db(), match_key(kind, value)
        row = db.execute(
            "SELECT n FROM placeholders WHERE session = ? AND kind = ? AND key = ?", (session, kind, key)
        ).fetchone()
        if row is None:
            (highest,) = db.execute(
                "SELECT COALESCE(MAX(n), 0) FROM placeholders WHERE session = ? AND kind = ?", (session, kind)
            ).fetchone()
            row = (highest + 1,)
            with db:
                db.execute("INSERT INTO placeholders VALUES (?, ?, ?, ?, ?)", (session, kind, row[0], key, value))
        return f"{{{{{kind}_{row[0]}}}}}"

    def fill(self, text: str, session: str) -> tuple[str, list[str]]:
        """Put this session's real values back. Placeholders it doesn't know stay as they are and are reported."""
        unknown: list[str] = []

        def real_value(match: re.Match) -> str:
            row = self.db().execute(
                "SELECT value FROM placeholders WHERE session = ? AND kind = ? AND n = ?",
                (session, match.group(1), int(match.group(2))),
            ).fetchone()
            if row is None:
                unknown.append(match.group())
                return match.group()
            return row[0]

        return PLACEHOLDER.sub(real_value, text), unknown

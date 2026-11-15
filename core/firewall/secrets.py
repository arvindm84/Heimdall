"""Finds secrets in text that is about to leave: model requests and outbound tool arguments.

Precise checks first, the way leaked-key scanners on GitHub work (Meli et al.,
NDSS 2019): exact matches for the gateway's own real keys and for any agent's fake
key, then the published formats of high-impact keys. Randomness (entropy) is only
checked on the value side of a `NAME=value` line whose name says it is a secret,
because entropy on its own flags too much ordinary text.

The fake keys are tripwires (honeytokens): they have no use anywhere except in an
agent's auth header to the gateway, so seeing one anywhere else is a theft attempt.

Findings carry a masked preview only. A secret must never end up in an event or log.
"""

import base64
import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

# Fake keys have one fixed shape (B's agents use sk-fake-<agent>-01), so any of them counts.
FAKE_KEY = re.compile(r"sk-fake-[A-Za-z0-9_-]+")
FORMATS = [
    ("anthropic_key", re.compile(r"(?<![\w-])sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"(?<!\w)(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})")),
    ("aws_access_key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")),
    ("google_api_key", re.compile(r"(?<![\w-])AIza[0-9A-Za-z_-]{35}")),
    # OpenAI: sk-..., sk-proj-...; not our fake keys and not Anthropic's sk-ant-.
    ("openai_key", re.compile(r"(?<![\w-])sk-(?!ant-|fake-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}")),
]
ENV_LINE = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?([A-Z][A-Z0-9_]*)[ \t]*=[ \t]*(\S.*?)[ \t]*$")
SECRET_NAME = re.compile(r"(?i)key|secret|token|passw(?:or)?d|pwd|credential")
# Three or more NAME=value lines read as a pasted .env file.
ENV_MIN_LINES = 3
# A value this long and this random under a secret-sounding name looks like a real secret.
ENTROPY_MIN_LENGTH = 16
ENTROPY_MIN_BITS = 3.5


@dataclass(frozen=True)
class Finding:
    kind: str  # fake_key | real_key | <format>_key/token | secret_assignment | env_file
    start: int
    end: int
    preview: str  # masked: never the whole secret


def mask(secret: str) -> str:
    """First 6 and last 4 characters only: enough to recognize, not enough to use."""
    return f"{secret[:6]}…{secret[-4:]}" if len(secret) > 12 else "…"


def scan(text: str, real_keys: Iterable[str], fake_keys: Iterable[str]) -> list[Finding]:
    """Every secret in `text`. Where findings overlap, the most specific one is kept."""
    candidates: list[Finding] = []
    for fake in {*fake_keys, *(m.group() for m in FAKE_KEY.finditer(text))}:
        candidates += exact(text, fake, "fake_key")
    # Skip empty or tiny values: an unset key must not match everywhere.
    for real in (key for key in real_keys if len(key) >= 8):
        candidates += exact(text, real, "real_key")
    for kind, pattern in FORMATS:
        candidates += [Finding(kind, m.start(), m.end(), mask(m.group())) for m in pattern.finditer(text)]
    candidates += secret_assignments(text)
    return [*without_overlaps(candidates), *env_file(text)]


def exact(text: str, secret: str, kind: str) -> list[Finding]:
    """One of our own keys, as it is or thinly disguised.

    We know these keys exactly, so cheap disguises can be matched without guessing:
    split up with spaces or line breaks, reversed, in hex, or in base64. Anything
    cleverer (encrypted, spread over several calls) still gets through.
    """
    spaced = r"\s*".join(re.escape(char) for char in secret)
    # Hex can be written in either case, so the disguised forms are matched ignoring case.
    disguised = "|".join(re.escape(form) for form in sorted(disguises(secret)))
    matches = [*re.finditer(spaced, text), *re.finditer(disguised, text, re.IGNORECASE)]
    return [Finding(kind, m.start(), m.end(), mask(secret)) for m in matches]


def disguises(secret: str) -> set[str]:
    """The secret reversed, in hex, and in base64 (standard and URL-safe)."""
    raw = secret.encode()
    forms = {secret[::-1], raw.hex()}
    # Inside a longer base64 blob the secret can start at any of three byte positions,
    # and each gives different characters. Keep the characters that depend on the secret alone.
    for shift in range(3):
        encoded = base64.b64encode(b"\0" * shift + raw).decode().rstrip("=")
        start = (shift * 8 + 5) // 6
        end = len(encoded) - (1 if (shift + len(raw)) % 3 else 0)
        forms.add(encoded[start:end])
        forms.add(encoded[start:end].replace("+", "-").replace("/", "_"))
    return forms


def secret_assignments(text: str) -> list[Finding]:
    """`STRIPE_SECRET=Zx81...`: a random-looking value under a name that says it is secret."""
    findings = []
    for match in ENV_LINE.finditer(text):
        name, value = match.groups()
        value = value.strip("'\"")
        if SECRET_NAME.search(name) and len(value) >= ENTROPY_MIN_LENGTH and entropy(value) >= ENTROPY_MIN_BITS:
            start = match.start(2)
            findings.append(Finding("secret_assignment", start, start + len(value), mask(value)))
    return findings


def entropy(value: str) -> float:
    """Shannon entropy in bits per character: about 4+ for random keys, under 3 for words."""
    counts = Counter(value)
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def env_file(text: str) -> list[Finding]:
    lines = list(ENV_LINE.finditer(text))
    if len(lines) < ENV_MIN_LINES:
        return []
    # The preview shows how many lines, never their values.
    return [Finding("env_file", lines[0].start(), lines[-1].end(), f"{len(lines)} NAME=value lines")]


# Earlier kinds win an overlap: our own keys are the most specific evidence.
ORDER = ["fake_key", "real_key", *(kind for kind, _ in FORMATS), "secret_assignment"]


def without_overlaps(findings: list[Finding]) -> list[Finding]:
    kept: list[Finding] = []
    for finding in sorted(findings, key=lambda f: (ORDER.index(f.kind), f.start)):
        if all(finding.end <= other.start or other.end <= finding.start for other in kept):
            kept.append(finding)
    return sorted(kept, key=lambda f: f.start)


def scan_json(value, real_keys: Iterable[str], fake_keys: Iterable[str]) -> list[Finding]:
    """Scan every string inside a decoded JSON body, so escaped newlines count as real lines."""
    real_keys, fake_keys = list(real_keys), list(fake_keys)
    if isinstance(value, str):
        return scan(value, real_keys, fake_keys)
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return [finding for child in children for finding in scan_json(child, real_keys, fake_keys)]

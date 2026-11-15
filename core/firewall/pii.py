"""Finds personal data in text, so the vault can swap it for placeholders.

Regex for formats that have a fixed shape (email, US phone, SSN, card with a
Luhn check), run first because they are precise and fast. spaCy's small English
model for person names, which have no fixed shape. Everything runs locally: no
network, so the demo works offline.
"""

import re
from dataclasses import dataclass
from functools import cache

# Placeholders the vault already put in, like {{EMAIL_1}}. Never treat them as data.
PLACEHOLDER = re.compile(r"\{\{[A-Z]+_\d+\}\}")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# US numbers with separators: (608) 555-0142, 608-555-0142, 608.555.0142, +1 608 555 0142.
# A bare run of ten digits is too often an order number or ID, so it is left alone.
PHONE = re.compile(r"(?<![\d+])(?:\+1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\d)")
SSN = re.compile(r"(?<!\d)(\d{3})-(\d{2})-(\d{4})(?!\d)")
# 13 to 19 digits, optionally grouped with spaces or dashes.
CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
# Lower numbers win when two kinds cover the same text equally.
PRIORITY = {"EMAIL": 0, "CARD": 1, "SSN": 2, "PHONE": 3, "PERSON": 4}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str  # EMAIL | PHONE | SSN | CARD | PERSON
    value: str


def find(text: str) -> list[Span]:
    """All personal data in `text`, in order, with no two spans overlapping."""
    protected = [(match.start(), match.end()) for match in PLACEHOLDER.finditer(text)]
    candidates = [
        span
        for span in [*regex_spans(text), *name_spans(text)]
        if not any(span.start < end and start < span.end for start, end in protected)
    ]
    return without_overlaps(candidates)


def regex_spans(text: str) -> list[Span]:
    spans = [Span(m.start(), m.end(), "EMAIL", m.group()) for m in EMAIL.finditer(text)]
    spans += [Span(m.start(), m.end(), "PHONE", m.group()) for m in PHONE.finditer(text)]
    spans += [Span(m.start(), m.end(), "SSN", m.group()) for m in SSN.finditer(text) if ssn_possible(*m.groups())]
    spans += [Span(m.start(), m.end(), "CARD", m.group()) for m in CARD.finditer(text) if luhn_ok(m.group())]
    return spans


def ssn_possible(area: str, group: str, serial: str) -> bool:
    """SSA never issues area 000, 666 or 900-999, group 00 or serial 0000."""
    return area not in ("000", "666") and not area.startswith("9") and group != "00" and serial != "0000"


def luhn_ok(number: str) -> bool:
    """The checksum every real card number passes; random digit runs mostly fail it."""
    digits = [int(char) for char in number if char.isdigit()]
    total = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2 == 1:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


@cache
def nlp():
    """spaCy's small English model, loaded once (about a second) and kept.

    Only the named-entity recognizer is needed, so the other pipes are skipped for speed.
    """
    import spacy  # imported here so modules that never look for names don't pay for it

    return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "attribute_ruler", "tagger"])


def name_spans(text: str) -> list[Span]:
    names = set()
    for entity in nlp()(text).ents:
        if entity.label_ != "PERSON":
            continue
        # "Priya's" -> "Priya": the possessive is grammar, not part of the name.
        value = entity.text.removesuffix("'s").removesuffix("’s").strip()
        if len(value) > 1:
            names.add(value)
    return mentions(text, names)


def mentions(text: str, names: set[str]) -> list[Span]:
    """Every mention of each found name, and of each part of it, as whole words.

    The small model often finds "Priya Raman" but misses a later "Priya" on its own.
    Once a name is known to be a person in this text, all its mentions are.
    Parts shorter than three letters (initials) are skipped.
    """
    words = names | {part for name in names for part in name.split() if len(part) > 2}
    spans = []
    for word in words:
        for match in re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", text):
            spans.append(Span(match.start(), match.end(), "PERSON", word))
    return spans


def without_overlaps(spans: list[Span]) -> list[Span]:
    """Where spans overlap, keep the longest (then the more specific kind)."""
    kept: list[Span] = []
    for span in sorted(spans, key=lambda s: (-(s.end - s.start), PRIORITY[s.kind], s.start)):
        if all(span.end <= other.start or other.end <= span.start for other in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)

"""Removes text a person can't see before an agent reads it, and keeps it as evidence.

Indirect prompt injection hides instructions in content an agent reads (Greshake
et al. 2023): HTML styled to be invisible, comments, or invisible Unicode, such as
Tag characters that spell out ASCII ("ASCII smuggling") and bidi controls (Trojan
Source). The agent gets only what a person would see; everything removed comes back
as a `Removed` finding so the injection check and the dashboard can show it.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, Tag

# Elements laid out as blocks: a line break before and after when turned into text.
BLOCKS = {
    "p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "table",
    "ul", "ol", "section", "article", "header", "footer", "blockquote", "pre", "hr",
}  # fmt: skip
# Moved this far off the page, text is out of sight.
OFF_SCREEN_PX = -1000
ZERO_WIDTH = {"​", "‌", "‍", "⁠", "﻿", "᠎"}
BIDI = {"‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩", "‎", "‏", "؜"}
TAGS_START, TAGS_END = 0xE0000, 0xE007F
NAMED_COLORS = {"white": "#ffffff", "black": "#000000"}


@dataclass(frozen=True)
class Removed:
    kind: str  # where it was hidden: display_none, html_comment, unicode_tags, ...
    text: str  # what was hidden (decoded for Tag characters)


@dataclass
class Cleaned:
    text: str  # what a person would see
    removed: list[Removed] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    source: str  # where it came from, for the event: "email 'Invoice 4821' from ..."
    removed: Removed


@dataclass
class Untrusted:
    """A tool result from outside (an email, a web page): visible text plus what was hidden in it.

    The guard marks the session untrusted, reports the evidence, swaps personal data
    for placeholders and wraps the text in the session's delimiter.
    """

    text: str
    evidence: list[Evidence] = field(default_factory=list)


def html(markup: str) -> Cleaned:
    """Visible text of an HTML document, one line per block, plus everything hidden."""
    soup = BeautifulSoup(markup, "lxml")
    removed: list[Removed] = []
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        if comment.strip():
            removed.append(Removed("html_comment", comment.strip()))
        comment.extract()
    # Not text anyone reads: dropped without a finding.
    for element in soup.find_all(["style", "head", "meta", "link"]):
        element.decompose()
    for element in soup.find_all(True):
        if element.decomposed:
            continue  # inside something already removed
        reason = "script" if element.name == "script" else hidden_reason(element)
        if reason:
            hidden = element.get_text(" ", strip=True)
            if hidden:
                removed.append(Removed(reason, hidden))
            element.decompose()
    cleaned = text(visible_text(soup))
    return Cleaned(cleaned.text, removed + cleaned.removed)


def visible_text(soup: BeautifulSoup) -> str:
    for element in soup.find_all(BLOCKS):
        element.insert_before("\n")
        element.insert_after("\n")
    lines = (" ".join(line.split()) for line in soup.get_text().splitlines())
    return "\n".join(line for line in lines if line)


def hidden_reason(element: Tag) -> str | None:
    """Why this element is invisible to a reader, or None if it isn't."""
    if element.has_attr("hidden"):
        return "hidden_attribute"
    css = style(element)
    if css.get("display") == "none":
        return "display_none"
    if css.get("visibility") in ("hidden", "collapse"):
        return "visibility_hidden"
    if number(css.get("opacity")) == 0:
        return "opacity_zero"
    if number(css.get("font-size")) == 0:
        return "font_size_zero"
    sizes = (css.get(name) for name in ("height", "max-height", "width", "max-width"))
    if css.get("overflow") == "hidden" and any(number(size) == 0 for size in sizes):
        return "zero_size"
    positioned = css.get("position") in ("absolute", "fixed")
    offsets = [number(css.get(name)) for name in ("left", "top")] if positioned else []
    offsets.append(number(css.get("text-indent")))
    if any(offset is not None and offset <= OFF_SCREEN_PX for offset in offsets):
        return "off_screen"
    color = parse_color(css.get("color"))
    if color and color == background(element):
        return "same_color"
    return None


def style(element: Tag) -> dict[str, str]:
    """Inline style as {property: value}, lowercased, without !important."""
    css = {}
    for declaration in element.get("style", "").split(";"):
        name, _, value = declaration.partition(":")
        if value:
            css[name.strip().lower()] = value.replace("!important", "").strip().lower()
    return css


def number(value: str | None) -> float | None:
    """The leading number of a CSS value ("-9999px" -> -9999.0), or None."""
    match = re.match(r"^(-?\d*\.?\d+)", value or "")
    return float(match.group(1)) if match else None


def parse_color(value: str | None) -> str | None:
    """A color as #rrggbb, for the common forms (#fff, #ffffff, white, rgb(255,255,255))."""
    if not value:
        return None
    value = NAMED_COLORS.get(value, value)
    if re.fullmatch(r"#[0-9a-f]{3}", value):
        return "#" + "".join(char * 2 for char in value[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", value):
        return value
    rgb = re.fullmatch(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)", value)
    if rgb:
        return "#" + "".join(f"{int(part):02x}" for part in rgb.groups())
    return None


def background(element: Tag) -> str:
    """The nearest background color set on this element or its parents; white if none (as in mail clients)."""
    for node in [element, *element.parents]:
        if not isinstance(node, Tag):
            continue
        css = style(node)
        for value in (css.get("background-color"), *css.get("background", "").split()):
            color = parse_color(value)
            if color:
                return color
    return "#ffffff"


def text(raw: str) -> Cleaned:
    """Plain text without invisible characters, NFKC-normalized so look-alike letters become plain ones."""
    removed: list[Removed] = []
    # Tag characters mirror ASCII (U+E0041 is "A"), so a run of them is hidden text: decode it.
    for run in re.findall(f"[{chr(TAGS_START)}-{chr(TAGS_END)}]+", raw):
        decoded = "".join(chr(ord(char) - TAGS_START) for char in run if 0x20 <= ord(char) - TAGS_START < 0x7F)
        removed.append(Removed("unicode_tags", decoded.strip()))
    raw = re.sub(f"[{chr(TAGS_START)}-{chr(TAGS_END)}]", "", raw)
    for kind, chars in (("zero_width", ZERO_WIDTH), ("bidi_control", BIDI)):
        count = sum(raw.count(char) for char in chars)
        if count:
            removed.append(Removed(kind, f"{count} invisible characters"))
            raw = "".join(char for char in raw if char not in chars)
    return Cleaned(unicodedata.normalize("NFKC", raw), removed)

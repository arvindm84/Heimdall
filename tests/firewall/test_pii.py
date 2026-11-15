"""Finding personal data: regex for emails, phones, SSNs and cards; spaCy for names.

Everything here is made up. Card numbers are standard test numbers.
"""

import time

import pytest

from core.firewall import pii


def kinds(text: str) -> list[tuple[str, str]]:
    return [(span.kind, span.value) for span in pii.find(text)]


def test_finds_an_email():
    assert ("EMAIL", "sam.rivera@example.com") in kinds("Write to sam.rivera@example.com today.")


@pytest.mark.parametrize("phone", ["(608) 555-0142", "608-555-0199", "608.555.0123", "+1 608 555 0177"])
def test_finds_us_phone_numbers(phone):
    assert ("PHONE", phone) in kinds(f"Call {phone} after five.")


def test_plain_ten_digit_run_is_not_a_phone():
    # Order numbers and IDs look like this; without separators we don't guess.
    assert kinds("Order 6085550142 shipped.") == []


def test_finds_an_ssn():
    assert ("SSN", "123-45-6789") in kinds("SSN 123-45-6789 on file.")


@pytest.mark.parametrize("ssn", ["000-12-3456", "666-12-3456", "912-34-5678", "123-00-4567", "123-45-0000"])
def test_impossible_ssns_are_ignored(ssn):
    assert kinds(f"Ref {ssn}.") == []


@pytest.mark.parametrize("card", ["4111 1111 1111 1111", "5500-0000-0000-0004", "378282246310005"])
def test_finds_cards_that_pass_luhn(card):
    assert ("CARD", card) in kinds(f"Card {card} expires soon.")


def test_card_failing_luhn_is_ignored():
    assert kinds("Card 4111 1111 1111 1112 expires soon.") == []


def test_finds_a_person_name():
    assert ("PERSON", "Priya Raman") in kinds("I talked with Priya Raman yesterday about the garden.")


def test_later_mentions_of_a_found_name_are_caught_too():
    # The small model often misses a lone first name after the full name; we don't rely on it.
    text = "I talked with Priya Raman yesterday. Priya can bring the tools. Ask Raman about seeds."
    names = [value for kind, value in kinds(text) if kind == "PERSON"]
    assert names == ["Priya Raman", "Priya", "Raman"]


def test_name_parts_only_match_whole_words():
    text = "I talked with Ana Lee yesterday. The banana bread was great."
    assert [value for kind, value in kinds(text) if kind == "PERSON"] == ["Ana Lee"]


def test_placeholders_are_left_alone():
    assert kinds("Reply to {{EMAIL_1}} and {{PERSON_2}} by Friday.") == []


def test_overlapping_spans_keep_the_longest():
    spans = pii.find("Contact sam.rivera@example.com now.")
    assert [(span.kind, span.value) for span in spans] == [("EMAIL", "sam.rivera@example.com")]


def test_spans_come_back_in_order_and_do_not_overlap():
    spans = pii.find("Priya Raman, priya@example.com, 608-555-0142.")
    assert [span.start for span in spans] == sorted(span.start for span in spans)
    assert all(first.end <= second.start for first, second in zip(spans, spans[1:]))


EMAIL_300_WORDS = " ".join(
    [
        "Hi Jordan, thanks for the quick reply about the spring volunteer schedule.",
        "I talked with Priya Raman and Marcus Oyelaran yesterday and we agreed the Saturday shifts",
        "should start at nine instead of eight. Priya can bring the extra tools from her garage.",
        "Reach me at jordan.fake.contact@example.com or on my cell at (608) 555-0142.",
        "The treasurer asked for the last four digits only, so do not send 4111 1111 1111 1111 again.",
    ]
    * 6
)


def test_a_300_word_email_takes_under_300_ms_after_warm_up():
    pii.find(EMAIL_300_WORDS)
    start = time.perf_counter()
    pii.find(EMAIL_300_WORDS)
    assert time.perf_counter() - start < 0.3

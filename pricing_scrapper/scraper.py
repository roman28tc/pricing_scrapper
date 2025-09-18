"""Utility helpers for scraping price data from web pages using stdlib tools."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable, List

PRICE_PATTERN = re.compile(
    r"""
    (?:(?:[$€£₴]|USD|EUR|GBP|UAH)\s?\d{1,3}(?:[\d.,\s]\d{3})*(?:[\d.,]\d{2})?)
    |
    (?:\d{1,3}(?:[\d.,\s]\d{3})*(?:[\d.,]\d{2})?\s?(?:USD|EUR|GBP|UAH|₴))
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class PriceResult:
    """Representation of an extracted price and its surrounding context."""

    description: str
    price: str


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)


def _gather_visible_text(
    text: str, *, start: int, direction: int, limit: int
) -> str:
    """Return up to *limit* visible characters from *text*.

    The function walks the string either backwards (``direction=-1``) or forwards
    (``direction=1``) starting from *start* and skips over HTML tags so that the
    returned snippet only contains text that would be rendered to the user.
    """

    assert direction in {-1, 1}

    step = direction
    idx = start
    end = len(text)
    buffer: list[str] = []
    collected = 0
    in_tag = False

    while 0 <= idx < end and collected < limit:
        char = text[idx]

        if char == "<":
            if direction == 1:
                in_tag = True
            else:
                in_tag = False
            idx += step
            continue
        if char == ">":
            if direction == 1:
                in_tag = False
            else:
                in_tag = True
            idx += step
            continue

        if not in_tag:
            if not buffer and char.isspace():
                idx += step
                continue
            buffer.append(char)
            collected += 1

        idx += step

    if direction == -1:
        buffer.reverse()

    return "".join(buffer)


def _visible_text_window(text: str, start: int, end: int, context: int) -> str:
    left = _gather_visible_text(text, start=start - 1, direction=-1, limit=context)
    right = _gather_visible_text(text, start=end, direction=1, limit=context)
    return f"{left}{text[start:end]}{right}"


def _clean_snippet(snippet: str) -> str:
    text = _TAG_RE.sub(" ", snippet)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def extract_prices(html_text: str, *, context: int = 60) -> List[PriceResult]:
    """Extract probable prices from raw HTML and provide textual context."""

    search_text = _SCRIPT_STYLE_RE.sub(" ", html_text)
    search_text = html.unescape(search_text)

    results: List[PriceResult] = []
    seen: set[tuple[str, str]] = set()

    for match in PRICE_PATTERN.finditer(search_text):
        snippet = _clean_snippet(
            _visible_text_window(
                search_text,
                max(match.start(), 0),
                min(match.end(), len(search_text)),
                context,
            )
        )
        price = match.group().strip()

        if not snippet:
            snippet = price

        if len(snippet) > 160:
            snippet = f"{snippet[:157]}..."

        key = (snippet, price)
        if key in seen:
            continue
        seen.add(key)
        results.append(PriceResult(description=snippet, price=price))

    return results


def iter_prices(html_text: str) -> Iterable[str]:
    """Yield raw price strings from *html_text*."""

    search_text = _SCRIPT_STYLE_RE.sub(" ", html_text)
    search_text = html.unescape(search_text)

    for match in PRICE_PATTERN.finditer(search_text):
        yield match.group().strip()


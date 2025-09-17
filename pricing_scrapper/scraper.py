"""Utility helpers for scraping price data from web pages using stdlib tools."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable, List

PRICE_PATTERN = re.compile(
    r"""
    (?:(?:[$€£]|USD|EUR|GBP)\s?\d{1,3}(?:[\d.,\s]\d{3})*(?:[\d.,]\d{2})?)
    |
    (?:\d{1,3}(?:[\d.,\s]\d{3})*(?:[\d.,]\d{2})?\s?(?:USD|EUR|GBP))
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


def _clean_snippet(snippet: str) -> str:
    text = _TAG_RE.sub(" ", snippet)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def extract_prices(html_text: str, *, context: int = 60) -> List[PriceResult]:
    """Extract probable prices from raw HTML and provide textual context."""

    search_text = _SCRIPT_STYLE_RE.sub(" ", html_text)

    results: List[PriceResult] = []
    seen: set[tuple[str, str]] = set()

    for match in PRICE_PATTERN.finditer(search_text):
        start = max(match.start() - context, 0)
        end = min(match.end() + context, len(search_text))
        snippet = _clean_snippet(search_text[start:end])
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

    for match in PRICE_PATTERN.finditer(search_text):
        yield match.group().strip()


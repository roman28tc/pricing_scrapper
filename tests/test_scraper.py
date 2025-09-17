"""Tests for the generic price extraction helper."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pricing_scrapper.scraper import PRICE_PATTERN, PriceResult, extract_prices, iter_prices


def test_price_pattern_matches_common_formats():
    samples = [
        "$19.99",
        "€99,95",
        "GBP 12.00",
        "1,299.00 USD",
    ]
    for sample in samples:
        assert PRICE_PATTERN.search(sample)


def test_iter_prices_yields_matches():
    html = "<span>$12.50</span><div>Now only €9,99 for a limited time!</div>"
    prices = list(iter_prices(html))
    assert prices == ["$12.50", "€9,99"]


def test_extract_prices_returns_snippets():
    html = """
    <html>
        <body>
            <div class="product">Widget A - $12.50 only today!</div>
            <div class="product">Widget B - €9,99 only today!</div>
        </body>
    </html>
    """

    results = extract_prices(html)
    assert [r.price for r in results] == ["$12.50", "€9,99"]
    assert all(isinstance(result, PriceResult) for result in results)
    assert any("Widget A" in result.description for result in results)

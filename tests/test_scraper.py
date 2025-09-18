"""Tests for the generic price extraction helper."""

import html
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
        "1 200 ₴",
        html.unescape("1&nbsp;200 ₴"),
        html.unescape("2&#160;500 USD"),
    ]
    for sample in samples:
        match = PRICE_PATTERN.search(sample)
        assert match
        assert match.group() == sample


def test_iter_prices_yields_matches():
    html_text = (
        "<span>$12.50</span>"
        "<div>Now only €9,99 for a limited time!</div>"
        "<p>Special 1&nbsp;200 ₴ deal</p>"
        "<p>Bundle 2&#160;500 USD offer</p>"
    )
    prices = list(iter_prices(html_text))
    assert prices == [
        "$12.50",
        "€9,99",
        html.unescape("1&nbsp;200 ₴"),
        html.unescape("2&#160;500 USD"),
    ]


def test_extract_prices_returns_snippets():
    page = """
    <html>
        <body>
            <div class="product">Widget A - $12.50 only today!</div>
            <div class="product">Widget B - €9,99 only today!</div>
            <div class="product">Widget C - 1&nbsp;200 ₴ only today!</div>
            <div class="product">Widget D - 2&#160;500 USD only today!</div>
        </body>
    </html>
    """

    results = extract_prices(page)
    assert [r.price for r in results] == [
        "$12.50",
        "€9,99",
        html.unescape("1&nbsp;200 ₴"),
        html.unescape("2&#160;500 USD"),
    ]
    assert all(isinstance(result, PriceResult) for result in results)
    assert any("Widget A" in result.description for result in results)


def test_extract_prices_ignores_script_and_style_content():
    html = """
    <html>
        <head>
            <style>
                .price::after { content: "$999.99"; }
            </style>
        </head>
        <body>
            <script>
                const fallback = "Only €199,95!";
            </script>
            <div>Actual offer – $49.99 today only!</div>
        </body>
    </html>
    """

    results = extract_prices(html)

    assert [r.price for r in results] == ["$49.99"]
    assert results[0].description.startswith("Actual offer")


def test_iter_prices_skips_script_and_style_content():
    html = """
    <style>
        .promo { content: "$75.00"; }
    </style>
    <div>Deal price €120,00</div>
    <script>
        const cached = "$15.00";
    </script>
    """

    assert list(iter_prices(html)) == ["€120,00"]

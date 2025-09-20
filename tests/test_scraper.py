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
    assert all(result.availability is None for result in results)


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


def test_extract_prices_prefers_visible_text_over_markup():
    html = """
    <div class="b-product-gallery__item">
        <a class="b-product-gallery__title" href="/p123-hario-v60">
            Крапельна кава Hario V60-02, біла
        </a>
        <div class="b-product-gallery__price">
            <span class="b-goods-price__value b-goods-price__value_type_current">
                1 675 ₴
            </span>
            <span class="b-product-gallery__sku">Артикул 12345</span>
        </div>
    </div>
    """

    results = extract_prices(html)

    assert results
    assert results[0].price == "1 675 ₴"
    assert "Hario V60-02" in results[0].description
    assert "b-goods-price" not in results[0].description


def test_extract_prices_removes_interface_noise_from_titles():
    html = """
    <div class="controls">
        <button>Галерея</button>
        <button>Список</button>
    </div>
    <div class="product-card">
        <a class="title">Кавомолка ручна Hario Coffee Mill DOME</a>
        <div class="details">
            <span class="price">1 675 ₴</span>
            <span class="status">Готово до відправки Оптом і в роздріб</span>
        </div>
    </div>
    <div class="product-card">
        <span class="badge">роздріб</span>
        <span class="action">Купити</span>
        <div class="name">Електропривод для ручних кавомолок Hario EMS-1B</div>
        <div class="price">3 476 ₴</div>
    </div>
    """

    results = extract_prices(html)
    descriptions = {result.price: result.description for result in results}

    assert descriptions["1 675 ₴"] == "Кавомолка ручна Hario Coffee Mill DOME"
    assert (
        descriptions["3 476 ₴"]
        == "Електропривод для ручних кавомолок Hario EMS-1B"
    )


def test_extract_prices_detects_availability_status():
    html_text = """
    <div class="product">
        <span class="name">Кавомолка</span>
        <span class="status">В наявності</span>
        <span class="price">1 675 ₴</span>
    </div>
    <div class="product">
        <span class="name">Еспресо машина</span>
        <span class="status">Немає в наявності</span>
        <span class="price">25 000 ₴</span>
    </div>
    <div class="product">
        <span class="name">Кавомолка-друг</span>
        <span class="meta">Наявність: немає</span>
        <span class="price">3 000 ₴</span>
    </div>
    """

    results = extract_prices(html_text)
    availability = {result.price: result.availability for result in results}

    assert availability["1 675 ₴"] == "В наявності"
    assert availability["25 000 ₴"] == "Немає в наявності"
    assert availability["3 000 ₴"] == "Немає в наявності"


def test_extract_prices_skips_attribute_only_matches():
    html = """
    <div class="product-card"
         data-product-id="123"
         data-product-price="1 675 ₴"
         data-product-name="Кавомолка Hario Skerton Plus">
        <a class="name" href="/p123">Кавомолка Hario Skerton Plus</a>
        <div class="price">1 675 ₴</div>
    </div>
    """

    results = extract_prices(html)

    assert results
    assert [result.price for result in results] == ["1 675 ₴"]
    assert results[0].description == "Кавомолка Hario Skerton Plus"

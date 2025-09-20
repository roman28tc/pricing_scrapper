"""Tests for the knbk.in.ua specific category scraper."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pricing_scrapper.knbk import (
    Category,
    Product,
    parse_category_products,
    scrape_category_products,
    scrape_category_hierarchy_products,
)


def test_parse_category_products_extracts_all_groups():
    html = """
    <section class="b-products-group" data-qaid="catalog_group">
        <div class="b-products-group__header">
            <h2 class="b-products-group__title">
                <a href="/ua/c123-hario" data-qaid="group_title">
                    Ручні кавомолки Hario
                </a>
            </h2>
        </div>
        <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
                <a class="b-product-gallery__title" href="/p123-hario-skerton">
                    Кавомолка Hario Skerton Plus
                </a>
                <div class="b-product-gallery__price">
                    <span class="b-goods-price__value b-goods-price__value_type_current"
                          data-qaid="product_price">
                        1 675 ₴
                    </span>
                </div>
            </div>
            <div class="b-product-gallery__item" data-qaid="product_block">
                <a class="b-product-gallery__title" href="/p456-ems-1b">
                    Електропривод для ручних кавомолок Hario EMS-1B
                </a>
                <div class="b-product-gallery__price">
                    <span class="b-goods-price__value b-goods-price__value_type_current">
                        3 476 ₴
                    </span>
                </div>
            </div>
        </div>
    </section>
    <section class="b-products-group" data-qaid="catalog_group">
        <header class="b-products-group__header">
            <h3 class="b-products-group__title">Запасні жорна та аксесуари</h3>
        </header>
        <div class="b-products-group__body">
            <div class="b-product-gallery__item">
                <div class="b-product-gallery__title" itemprop="name">
                    Комплект жорен для Hario Skerton Pro
                </div>
                <div class="b-product-gallery__price">
                    <span class="b-goods-price__value b-goods-price__value_type_current">
                        989 ₴
                    </span>
                    <span class="b-goods-price__value b-goods-price__value_type_old">
                        1 050 ₴
                    </span>
                </div>
            </div>
        </div>
    </section>
    """

    categories = parse_category_products(html)

    assert [category.name for category in categories] == [
        "Ручні кавомолки Hario",
        "Запасні жорна та аксесуари",
    ]

    assert categories[0].products == [
        Product(
            name="Кавомолка Hario Skerton Plus",
            price="1 675 ₴",
            url="/p123-hario-skerton",
        ),
        Product(
            name="Електропривод для ручних кавомолок Hario EMS-1B",
            price="3 476 ₴",
            url="/p456-ems-1b",
        ),
    ]

    assert categories[1].products == [
        Product(
            name="Комплект жорен для Hario Skerton Pro",
            price="989 ₴",
            url=None,
        )
    ]


def test_parse_category_products_generates_placeholder_when_missing_title():
    html = """
    <div class="b-products-group" data-qaid="catalog_group">
        <div class="b-products-group__body">
            <div class="b-product-gallery__item">
                <a class="b-product-gallery__title" href="/p111">Test product</a>
                <span class="b-goods-price__value">1 111 ₴</span>
            </div>
        </div>
    </div>
    """

    categories = parse_category_products(html)
    assert len(categories) == 1
    assert categories[0].name == "Category 1"
    assert categories[0].products == [Product(name="Test product", price="1 111 ₴", url="/p111")]


def test_scrape_category_products_follows_pagination():
    page_1 = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Ручні кавомолки</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/p1">Кавомолка 1</a>
              <span class="b-goods-price__value">100 ₴</span>
            </div>
          </div>
        </section>
        <nav class="pagination">
          <a data-qaid="pagination_next" href="?page=2">Next</a>
        </nav>
      </body>
    </html>
    """

    page_2 = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Ручні кавомолки</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/p2">Кавомолка 2</a>
              <span class="b-goods-price__value">200 ₴</span>
            </div>
          </div>
        </section>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Аксесуари</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/a1">Щітка</a>
              <span class="b-goods-price__value">50 ₴</span>
            </div>
          </div>
        </section>
        <nav class="pagination">
          <a class="pager__next" href="?page=3"><span>›</span></a>
        </nav>
      </body>
    </html>
    """

    page_3 = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Аксесуари</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/a2">Колір</a>
              <span class="b-goods-price__value">75 ₴</span>
            </div>
          </div>
        </section>
      </body>
    </html>
    """

    pages = {
        "https://example.com/cat/": page_1,
        "https://example.com/cat/?page=2": page_2,
        "https://example.com/cat/?page=3": page_3,
    }

    visited: list[str] = []

    def fake_fetch(url: str) -> str:
        visited.append(url)
        return pages[url]

    categories = scrape_category_products("https://example.com/cat/", fetch=fake_fetch)

    assert visited == [
        "https://example.com/cat/",
        "https://example.com/cat/?page=2",
        "https://example.com/cat/?page=3",
    ]

    assert categories == [
        Category(
            name="Ручні кавомолки",
            products=[
                Product(name="Кавомолка 1", price="100 ₴", url="/p1"),
                Product(name="Кавомолка 2", price="200 ₴", url="/p2"),
            ],
        ),
        Category(
            name="Аксесуари",
            products=[
                Product(name="Щітка", price="50 ₴", url="/a1"),
                Product(name="Колір", price="75 ₴", url="/a2"),
            ],
        ),
    ]


def test_scrape_category_products_uses_data_url_when_href_placeholder():
    page_1 = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Турки</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/t1">Турка 1</a>
              <span class="b-goods-price__value">300 ₴</span>
            </div>
          </div>
        </section>
        <nav class="pagination">
          <a data-qaid="pagination_next" href="#" data-url="?page=2">Далі</a>
        </nav>
      </body>
    </html>
    """

    page_2 = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Турки</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/t2">Турка 2</a>
              <span class="b-goods-price__value">350 ₴</span>
            </div>
          </div>
        </section>
      </body>
    </html>
    """

    pages = {
        "https://example.com/cat/": page_1,
        "https://example.com/cat/?page=2": page_2,
    }

    visited: list[str] = []

    def fake_fetch(url: str) -> str:
        visited.append(url)
        return pages[url]

    categories = scrape_category_products("https://example.com/cat/", fetch=fake_fetch)

    assert visited == [
        "https://example.com/cat/",
        "https://example.com/cat/?page=2",
    ]

    assert categories == [
        Category(
            name="Турки",
            products=[
                Product(name="Турка 1", price="300 ₴", url="/t1"),
                Product(name="Турка 2", price="350 ₴", url="/t2"),
            ],
        )
    ]


def test_scrape_category_hierarchy_products_traverses_nested_structure():
    root_page = """
    <html>
      <body>
        <section class="b-category-sections" data-qaid="category_groups">
          <div class="b-category-sections__item">
            <h2 class="b-category-sections__title">
              <a class="b-category-sections__link" data-qaid="category_link" href="/ua/g1-coffee">
                Coffee makers
              </a>
            </h2>
          </div>
          <div class="b-category-sections__item">
            <h2 class="b-category-sections__title">
              <a class="b-category-sections__link" href="/ua/g2-kettles">
                Kettles
              </a>
            </h2>
          </div>
        </section>
        <nav class="breadcrumbs">
          <a class="breadcrumbs__link" href="/ua/">Home</a>
          <a class="breadcrumbs__link" href="/ua/groot">Current</a>
        </nav>
        <footer class="footer">
          <a class="footer__link" href="/ua/g999-ignore">Ignore me</a>
        </footer>
      </body>
    </html>
    """

    coffee_page = """
    <html>
      <body>
        <section class="catalog-section" data-qaid="category_groups">
          <div class="catalog-section__item">
            <a class="catalog-section__title" href="/ua/c10-manual">Manual grinders</a>
          </div>
          <div class="catalog-section__item">
            <a class="catalog-section__title" data-qaid="category_link" href="/ua/c20-accessories">
              Accessories
            </a>
          </div>
        </section>
        <div class="info-block">
          <a class="info-block__link" href="/ua/p999">Not a category</a>
        </div>
      </body>
    </html>
    """

    manual_page = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Manual grinders</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/p1">Hand Grinder A</a>
              <span class="b-goods-price__value">100 ₴</span>
            </div>
          </div>
        </section>
      </body>
    </html>
    """

    accessories_page = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Accessories</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/p2">Cleaning Brush</a>
              <span class="b-goods-price__value">50 ₴</span>
            </div>
          </div>
        </section>
      </body>
    </html>
    """

    kettles_page = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Electric kettles</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/p3">Kettle X</a>
              <span class="b-goods-price__value">500 ₴</span>
            </div>
          </div>
        </section>
        <nav class="pagination">
          <a class="pagination__next" href="?page=2">Next</a>
        </nav>
      </body>
    </html>
    """

    kettles_page_2 = """
    <html>
      <body>
        <section class="b-products-group" data-qaid="catalog_group">
          <div class="b-products-group__header">
            <h2 class="b-products-group__title">Electric kettles</h2>
          </div>
          <div class="b-products-group__body">
            <div class="b-product-gallery__item" data-qaid="product_block">
              <a class="b-product-gallery__title" href="/p4">Kettle Y</a>
              <span class="b-goods-price__value">550 ₴</span>
            </div>
          </div>
        </section>
      </body>
    </html>
    """

    pages = {
        "https://example.com/ua/groot": root_page,
        "https://example.com/ua/g1-coffee": coffee_page,
        "https://example.com/ua/c10-manual": manual_page,
        "https://example.com/ua/c20-accessories": accessories_page,
        "https://example.com/ua/g2-kettles": kettles_page,
        "https://example.com/ua/g2-kettles?page=2": kettles_page_2,
    }

    visited: list[str] = []

    def fake_fetch(url: str) -> str:
        visited.append(url)
        return pages[url]

    categories = scrape_category_hierarchy_products(
        "https://example.com/ua/groot", fetch=fake_fetch
    )

    assert visited == [
        "https://example.com/ua/groot",
        "https://example.com/ua/groot",
        "https://example.com/ua/g1-coffee",
        "https://example.com/ua/g1-coffee",
        "https://example.com/ua/c10-manual",
        "https://example.com/ua/c10-manual",
        "https://example.com/ua/c20-accessories",
        "https://example.com/ua/c20-accessories",
        "https://example.com/ua/g2-kettles",
        "https://example.com/ua/g2-kettles",
        "https://example.com/ua/g2-kettles?page=2",
    ]

    assert categories == [
        Category(
            name="Coffee makers / Manual grinders",
            products=[Product(name="Hand Grinder A", price="100 ₴", url="/p1")],
        ),
        Category(
            name="Coffee makers / Accessories",
            products=[Product(name="Cleaning Brush", price="50 ₴", url="/p2")],
        ),
        Category(
            name="Kettles / Electric kettles",
            products=[
                Product(name="Kettle X", price="500 ₴", url="/p3"),
                Product(name="Kettle Y", price="550 ₴", url="/p4"),
            ],
        ),
    ]


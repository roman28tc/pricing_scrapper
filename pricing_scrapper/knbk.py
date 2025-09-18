"""Utilities for scraping category and product data from knbk.in.ua pages."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable, List, Optional


@dataclass(slots=True)
class Product:
    """Representation of a single product listed under a category."""

    name: str
    price: Optional[str] = None
    url: Optional[str] = None


@dataclass(slots=True)
class Category:
    """Grouping of products that share a common heading on the page."""

    name: str
    products: List[Product] = field(default_factory=list)


@dataclass(slots=True)
class _Element:
    tag: str
    attrs: dict[str, str]

    @property
    def classes(self) -> Iterable[str]:
        raw = self.attrs.get("class")
        if not raw:
            return ()
        return tuple(part for part in re.split(r"\s+", raw) if part)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.attrs.get(key, default)


@dataclass(slots=True)
class _ProductContext:
    element: _Element
    name: Optional[str] = None
    price: Optional[str] = None
    url: Optional[str] = None


@dataclass(slots=True)
class _CategoryContext:
    element: _Element
    name: Optional[str] = None
    products: List[Product] = field(default_factory=list)


@dataclass(slots=True)
class _TextCapture:
    role: str
    depth: int
    buffer: List[str]
    context: object


_CATEGORY_CONTAINER_CLASS_KEYWORDS = (
    "products-group",
    "products_group",
    "subcategory",
    "catalog-section",
    "catalog_section",
    "category-section",
    "category_section",
)

_CATEGORY_CONTAINER_DATA_QAID_KEYWORDS = (
    "group",
    "subcategory",
)

_CATEGORY_TITLE_CLASS_KEYWORDS = (
    "products-group__title",
    "group__title",
    "category__title",
    "subcategory__title",
    "section__title",
    "group-title",
    "category-title",
)

_CATEGORY_TITLE_DATA_QAID_KEYWORDS = (
    "group_title",
    "subcategory_title",
)

_PRODUCT_CONTAINER_CLASS_KEYWORDS = (
    "product-card",
    "product_card",
    "product-item",
    "product_tile",
    "product-tile",
    "product-list__item",
    "product-gallery__item",
    "b-product-gallery__item",
)

_PRODUCT_CONTAINER_DATA_QAID_KEYWORDS = (
    "product",
)

_PRODUCT_TITLE_CLASS_KEYWORDS = (
    "product-card__title",
    "product__title",
    "product-title",
    "product__name",
    "product-name",
    "b-product-gallery__title",
    "b-product-gallery__name",
    "title",
    "name",
)

_PRODUCT_PRICE_CLASS_KEYWORDS = (
    "price__value",
    "price-value",
    "price_current",
    "price__current",
    "product-price__value",
    "product-price",
    "b-goods-price__value",
    "goods-price__value",
    "price",
    "value",
)

_EXCLUDED_PRICE_CLASS_KEYWORDS = (
    "old",
    "was",
    "strike",
    "compare",
    "cross",
)


def _normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _class_matches(element: _Element, keywords: Iterable[str]) -> bool:
    classes = element.classes
    for cls in classes:
        lowered = cls.casefold()
        for keyword in keywords:
            if keyword in lowered:
                return True
    return False


def _dataqaid_matches(element: _Element, keywords: Iterable[str]) -> bool:
    value = element.get("data-qaid")
    if not value:
        return False
    lowered = value.casefold()
    return any(keyword in lowered for keyword in keywords)


def _is_category_container(element: _Element) -> bool:
    if element.tag not in {"div", "section", "article"}:
        return False
    if _dataqaid_matches(element, _CATEGORY_CONTAINER_DATA_QAID_KEYWORDS):
        return True
    for cls in element.classes:
        lowered = cls.casefold()
        if "__" in lowered:
            continue
        for keyword in _CATEGORY_CONTAINER_CLASS_KEYWORDS:
            if keyword in lowered:
                return True
    return False


def _is_product_container(element: _Element) -> bool:
    if element.tag not in {"div", "li", "article", "section"}:
        return False
    if _class_matches(element, _PRODUCT_CONTAINER_CLASS_KEYWORDS):
        return True
    if _dataqaid_matches(element, _PRODUCT_CONTAINER_DATA_QAID_KEYWORDS):
        return True
    return False


def _is_category_title(element: _Element) -> bool:
    if _dataqaid_matches(element, _CATEGORY_TITLE_DATA_QAID_KEYWORDS):
        return True
    if element.tag in {"h1", "h2", "h3", "h4"}:
        return _class_matches(element, _CATEGORY_TITLE_CLASS_KEYWORDS)
    if element.tag == "a":
        return _class_matches(element, _CATEGORY_TITLE_CLASS_KEYWORDS)
    return False


def _is_product_title(element: _Element) -> bool:
    if element.tag not in {"a", "div", "span"}:
        return False
    if element.get("itemprop") == "name":
        return True
    if _class_matches(element, _PRODUCT_TITLE_CLASS_KEYWORDS):
        return True
    return False


def _is_product_price(element: _Element) -> bool:
    if element.get("itemprop") == "price":
        return True
    if _class_matches(element, _PRODUCT_PRICE_CLASS_KEYWORDS):
        if _class_matches(element, _EXCLUDED_PRICE_CLASS_KEYWORDS):
            return False
        return True
    data_role = element.get("data-qaid", "").casefold()
    if "price" in data_role and "old" not in data_role:
        return True
    return False


class _KNBKPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._elements: List[_Element] = []
        self._captures: List[_TextCapture] = []
        self._category_stack: List[_CategoryContext] = []
        self._product_stack: List[_ProductContext] = []
        self._categories: List[Category] = []

    # HTMLParser API -----------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        element = _Element(tag=tag, attrs=dict(attrs))
        self._elements.append(element)
        depth = len(self._elements)

        if _is_category_container(element):
            self._category_stack.append(_CategoryContext(element=element))

        current_category = self._category_stack[-1] if self._category_stack else None

        if current_category and _is_product_container(element):
            self._product_stack.append(_ProductContext(element=element))

        current_product = self._product_stack[-1] if self._product_stack else None

        if current_category and _is_category_title(element):
            if current_category.name is None:
                self._captures.append(
                    _TextCapture(
                        role="category_name",
                        depth=depth,
                        buffer=[],
                        context=current_category,
                    )
                )

        if current_product and _is_product_title(element):
            if current_product.name is None:
                href = element.get("href")
                if href:
                    current_product.url = href.strip()
                self._captures.append(
                    _TextCapture(
                        role="product_name",
                        depth=depth,
                        buffer=[],
                        context=current_product,
                    )
                )

        if current_product and _is_product_price(element):
            if current_product.price is None:
                self._captures.append(
                    _TextCapture(
                        role="product_price",
                        depth=depth,
                        buffer=[],
                        context=current_product,
                    )
                )

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if not self._elements:
            return
        element = self._elements.pop()
        self._finalize_captures()
        self._finalize_product(element)
        self._finalize_category(element)

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[override]
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if not data:
            return
        for capture in self._captures:
            capture.buffer.append(data)

    # Internal helpers ---------------------------------------------------
    def _finalize_captures(self) -> None:
        current_depth = len(self._elements)
        while self._captures and self._captures[-1].depth > current_depth:
            capture = self._captures.pop()
            text = _normalize_text("".join(capture.buffer))
            if not text:
                continue
            if capture.role == "category_name":
                context = capture.context  # type: ignore[assignment]
                assert isinstance(context, _CategoryContext)
                if context.name is None:
                    context.name = text
            elif capture.role == "product_name":
                context = capture.context  # type: ignore[assignment]
                assert isinstance(context, _ProductContext)
                if context.name is None:
                    context.name = text
            elif capture.role == "product_price":
                context = capture.context  # type: ignore[assignment]
                assert isinstance(context, _ProductContext)
                if context.price is None:
                    context.price = text

    def _finalize_product(self, element: _Element) -> None:
        if not self._product_stack:
            return
        current = self._product_stack[-1]
        if current.element is not element:
            return
        self._product_stack.pop()
        if not current.name:
            return
        product = Product(name=current.name, price=current.price, url=current.url)
        if self._category_stack:
            self._category_stack[-1].products.append(product)

    def _finalize_category(self, element: _Element) -> None:
        if not self._category_stack:
            return
        current = self._category_stack[-1]
        if current.element is not element:
            return
        self._category_stack.pop()
        if not current.products:
            return
        name = current.name or f"Category {len(self._categories) + 1}"
        self._categories.append(Category(name=name, products=current.products))

    # Public API ---------------------------------------------------------
    @property
    def categories(self) -> List[Category]:
        return list(self._categories)


def parse_category_products(html_text: str) -> List[Category]:
    """Parse *html_text* and return categories with their products.

    The function targets the structure used on knbk.in.ua catalog pages. It tries
    to be resilient by matching elements via common class and ``data-qaid``
    patterns observed on the site.
    """

    parser = _KNBKPageParser()
    parser.feed(html_text)
    parser.close()
    return parser.categories


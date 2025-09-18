"""Utilities for scraping category and product data from knbk.in.ua pages."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Dict, Iterable, List, Optional

from urllib.parse import urldefrag, urljoin, urlparse


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


_NEXT_TEXT_SYMBOLS = {">", ">>", "»", "›", "→"}
_NEXT_TEXT_KEYWORDS = {
    "next",
    "next page",
    "следующая",
    "следующая страница",
    "вперед",
    "вперёд",
    "далее",
    "далі",
}
_NEXT_ATTR_KEYWORDS = (
    "next",
    "pagination_next",
    "pager_next",
)
_NEXT_CLASS_HINTS = (
    "pagination__next",
    "pagination-next",
    "pagination_next",
    "pager__next",
    "pager-next",
    "page__next",
    "page-next",
    "nav__next",
    "nav-next",
    "arrow-next",
    "btn-next",
)
_PLACEHOLDER_CATEGORY_RE = re.compile(r"^Category \d+$")


def _text_looks_like_next(text: str) -> bool:
    if not text:
        return False
    normalized = text.strip()
    if not normalized:
        return False
    lowered = normalized.casefold()
    if lowered in _NEXT_TEXT_KEYWORDS:
        return True
    if lowered.startswith("наступ"):
        return True
    if lowered.startswith("следующ"):
        return True
    if lowered.startswith("дал"):
        return True
    if lowered.startswith("далі"):
        return True
    if lowered.startswith("вперёд") or lowered.startswith("вперед"):
        return True
    if normalized in _NEXT_TEXT_SYMBOLS:
        return True
    return False


def _split_classes(value: str) -> Iterable[str]:
    return (part for part in re.split(r"\s+", value) if part)


def _link_attrs_look_like_next(attrs: Dict[str, str]) -> bool:
    href = attrs.get("href", "").strip()
    if not href or href in {"#", "javascript:void(0)", "javascript:;", "void(0)"}:
        return False

    rel = attrs.get("rel")
    if rel and any(part.casefold() == "next" for part in re.split(r"\s+", rel)):
        return True

    for key in ("data-qaid", "data-role", "data-action", "data-direction"):
        value = attrs.get(key)
        if value and any(keyword in value.casefold() for keyword in _NEXT_ATTR_KEYWORDS):
            return True

    aria_label = attrs.get("aria-label")
    if aria_label and _text_looks_like_next(aria_label):
        return True

    title = attrs.get("title")
    if title and _text_looks_like_next(title):
        return True

    classes = attrs.get("class")
    if classes:
        for cls in _split_classes(classes):
            lowered = cls.casefold()
            if lowered in _NEXT_CLASS_HINTS:
                return True
            if "next" in lowered and any(
                hint in lowered for hint in ("pag", "pager", "page", "nav", "arrow")
            ):
                return True

    return False


class _PaginationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.next_href: Optional[str] = None
        self._current_anchor: Optional[Dict[str, str]] = None
        self._anchor_depth = 0
        self._buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if self.next_href is not None:
            if tag == "a" and self._current_anchor is not None:
                self._anchor_depth += 1
            return

        attrs_dict: Dict[str, str] = dict(attrs)

        if tag == "link":
            href = attrs_dict.get("href")
            if href and _link_attrs_look_like_next(attrs_dict):
                self.next_href = href
            return

        if tag != "a":
            if self._current_anchor is not None:
                self._anchor_depth += 1
            return

        href = attrs_dict.get("href")
        if not href:
            return

        if _link_attrs_look_like_next(attrs_dict):
            self.next_href = href
            return

        self._current_anchor = attrs_dict
        self._buffer = []
        self._anchor_depth = 0

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if self._current_anchor is None:
            return

        if tag != "a":
            if self._anchor_depth:
                self._anchor_depth -= 1
            return

        if self._anchor_depth:
            self._anchor_depth -= 1
            return

        href = self._current_anchor.get("href")
        text = _normalize_text("".join(self._buffer))
        if href and _text_looks_like_next(text):
            self.next_href = href

        self._current_anchor = None
        self._buffer = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self.next_href is not None:
            return
        if self._current_anchor is not None:
            self._buffer.append(data)


def _find_next_page_url(html_text: str, base_url: str) -> Optional[str]:
    parser = _PaginationParser()
    parser.feed(html_text)
    parser.close()

    href = parser.next_href
    if not href:
        return None

    joined = urljoin(base_url, href)
    if not joined:
        return None

    joined, _ = urldefrag(joined)
    if not joined:
        return None

    parsed = urlparse(joined)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None

    return parsed._replace(fragment="").geturl()


def scrape_category_products(
    url: str, *, fetch: Callable[[str], str]
) -> List[Category]:
    """Fetch *url* and follow pagination links to collect all products."""

    aggregated: Dict[str, Category] = {}
    placeholder_counter = 0
    ordered_keys: List[str] = []
    seen_urls: set[str] = set()

    next_url: Optional[str] = url

    while next_url and next_url not in seen_urls:
        seen_urls.add(next_url)
        html_text = fetch(next_url)
        page_categories = parse_category_products(html_text)

        for category in page_categories:
            if _PLACEHOLDER_CATEGORY_RE.match(category.name):
                key = f"__placeholder_{placeholder_counter}"
                placeholder_counter += 1
            else:
                key = category.name

            existing = aggregated.get(key)
            if existing is None:
                aggregated[key] = Category(
                    name=category.name, products=list(category.products)
                )
                ordered_keys.append(key)
            else:
                existing.products.extend(category.products)

        next_url = _find_next_page_url(html_text, next_url)
        if next_url in seen_urls:
            break

    return [aggregated[key] for key in ordered_keys]


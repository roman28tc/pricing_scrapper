"""Utility helpers for scraping price data from web pages using stdlib tools."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable, List, Optional, Sequence, Tuple

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
    availability: Optional[str] = None


@dataclass
class _TextNode:
    """Representation of visible text extracted from the HTML document."""

    text: str
    path: Tuple[Tuple[str, int], ...]


class _StackEntry:
    """Internal helper representing a tag currently open in the parser."""

    __slots__ = ("tag", "index", "child_counts")

    def __init__(self, tag: str, index: int) -> None:
        self.tag = tag
        self.index = index
        self.child_counts: Counter[str] = Counter()

    @property
    def identity(self) -> Tuple[str, int]:
        return (self.tag, self.index)


class _VisibleTextParser(HTMLParser):
    """Collect visible text nodes while preserving a structural path."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[_StackEntry] = []
        self._root_counts: Counter[str] = Counter()
        self.nodes: list[_TextNode] = []

    # HTMLParser API -----------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if self._stack:
            parent = self._stack[-1]
            index = parent.child_counts[tag]
            parent.child_counts[tag] += 1
        else:
            index = self._root_counts[tag]
            self._root_counts[tag] += 1
        self._stack.append(_StackEntry(tag, index))

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if not data:
            return
        if any(entry.tag in {"script", "style"} for entry in self._stack):
            return
        text = data.strip()
        if not text:
            return
        text = html.unescape(text)
        path = tuple(entry.identity for entry in self._stack)
        self.nodes.append(_TextNode(text=text, path=path))


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)

_NOISE_PREFIXES_RAW = [
    "Галерея",
    "Список",
    "Роздріб",
    "Роздрiб",
    "Оптом",
    "Купити",
    "Купить",
    "Готово",
    "Артикул",
    "В наявності",
    "В наявност",
    "В наличии",
    "Наявність",
    "Наявні",
    "Наявн",
    "Наявн.",
    "Наличие",
    "Наличии",
    "Замовити",
    "Замовлення",
    "Заказать",
    "Заказ",
    "Кошик",
    "Корзина",
]
_NOISE_PREFIXES = tuple(
    sorted({prefix.casefold() for prefix in _NOISE_PREFIXES_RAW}, key=len, reverse=True)
)
_NOISE_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(prefix) for prefix in _NOISE_PREFIXES) + r")",
    re.IGNORECASE,
)


def _compile_availability_markers(
    markers: Sequence[tuple[str, Optional[str]]]
) -> tuple[tuple[re.Pattern[str], Optional[str]], ...]:
    compiled: list[tuple[re.Pattern[str], Optional[str]]] = []
    for pattern, label in markers:
        compiled.append((re.compile(pattern, re.IGNORECASE), label))
    return tuple(compiled)


_AVAILABILITY_OUT_OF_STOCK_MARKERS = _compile_availability_markers(
    (
        (r"нема(?:є)?\s+в\s+наявн\w*", "Немає в наявності"),
        (r"нема(?:є)?\s+на\s+склад\w*", "Немає на складі"),
        (r"нет\s+в\s+налич\w*", "Нет в наличии"),
        (r"нет\s+на\s+склад[еe]\w*", "Нет на складе"),
        (r"наявн(?:ість|iсть)\s*:\s*нема(?:є)?", "Немає в наявності"),
        (r"наличие\s*:\s*нет", "Нет в наличии"),
        (r"відсут\w*", None),
        (r"отсутств\w*", None),
        (r"закінч\w*", None),
        (r"законч\w*", None),
        (r"під\s+замовлен\w*", "Під замовлення"),
        (r"под\s+заказ", "Под заказ"),
        (r"очікуєт\w*", "Очікується"),
        (r"ожидает\w*", "Ожидается"),
        (r"sold\s*out", "Sold out"),
        (r"out\s+of\s+stock", "Out of stock"),
    )
)

_AVAILABILITY_IN_STOCK_MARKERS = _compile_availability_markers(
    (
        (r"в\s+наявн\w*", "В наявності"),
        (r"у\s+наявн\w*", "В наявності"),
        (r"є\s+в\s+наявн\w*", "В наявності"),
        (r"є\s+у\s+наявн\w*", "В наявності"),
        (r"наявн(?:ість|iсть)\s*:\s*є", "В наявності"),
        (r"наличие\s*:\s*есть", "В наличии"),
        (r"є\s+на\s+склад\w*", "Є на складі"),
        (r"есть\s+на\s+склад[еe]\w*", "Есть на складе"),
        (r"в\s+налич\w*", "В наличии"),
        (r"есть\s+в\s+налич\w*", "В наличии"),
        (r"готово?\s+до\s+відправк\w*", "Готово до відправки"),
        (r"готово?\s+к\s+отправк\w*", "Готов к отправке"),
        (r"готов\s+до\s+відправк\w*", "Готово до відправки"),
        (r"готов\s+к\s+отправк\w*", "Готов к отправке"),
    )
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


def _is_inside_html_tag(text: str, index: int) -> bool:
    """Return ``True`` if *index* is positioned within an HTML tag."""

    lt_index = text.rfind("<", 0, index)
    if lt_index == -1:
        return False
    gt_index = text.rfind(">", 0, index)
    if gt_index > lt_index:
        return False
    return True


def _visible_text_window(text: str, start: int, end: int, context: int) -> str:
    left = _gather_visible_text(text, start=start - 1, direction=-1, limit=context)
    right = _gather_visible_text(text, start=end, direction=1, limit=context)
    return f"{left}{text[start:end]}{right}"


def _clean_snippet(snippet: str) -> str:
    text = _TAG_RE.sub(" ", snippet)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _collect_text_nodes(html_text: str) -> list[_TextNode]:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    parser.close()
    return parser.nodes


def _common_prefix_length(
    left: Sequence[Tuple[str, int]], right: Sequence[Tuple[str, int]]
) -> int:
    length = 0
    for l_item, r_item in zip(left, right):
        if l_item != r_item:
            break
        length += 1
    return length


def _strip_noise_prefix(text: str) -> str:
    text = text.lstrip(" \t\r\n-–—:;|•·,/")
    while text:
        match = _NOISE_PREFIX_RE.match(text)
        if not match:
            break
        text = text[match.end():]
        text = text.lstrip(" \t\r\n-–—:;|•·,/")
    return text


def _prepare_candidate_text(text: str) -> str:
    text = _WHITESPACE_RE.sub(" ", text)
    text = text.strip()
    text = _strip_noise_prefix(text)
    text = text.strip(" \t\r\n-–—:;|•·,/")
    text = _strip_noise_prefix(text)
    return text


def _looks_like_noise(text: str) -> bool:
    if not text:
        return True
    if _NOISE_PREFIX_RE.match(text):
        return True
    lowered = text.casefold()
    return lowered in {"", "-", "—"}


def _is_valid_candidate(text: str) -> bool:
    if not text:
        return False
    if _looks_like_noise(text):
        return False
    return any(char.isalpha() for char in text)


def _text_quality(text: str) -> int:
    length = len(text)
    letters = sum(char.isalpha() for char in text)
    digits = sum(char.isdigit() for char in text)
    spaces = text.count(" ")
    extras = sum(char in "-_/." for char in text)
    score = length + letters * 2 + digits
    if spaces:
        score += 5
    score += extras
    return score


def _score_candidate_from_text(
    text: str,
    candidate_path: Sequence[Tuple[str, int]],
    price_path: Sequence[Tuple[str, int]],
    distance: int,
) -> int:
    if not _is_valid_candidate(text):
        return 0
    prefix_len = _common_prefix_length(candidate_path, price_path)
    score = _text_quality(text)
    if prefix_len == 0:
        score -= 25
    else:
        score += prefix_len * 40
    score -= distance * 5
    return score


def _select_best_neighbor_description(
    nodes: Sequence[_TextNode], price_index: int, price: str
) -> Optional[str]:
    if not nodes:
        return None

    price_node = nodes[price_index]
    price_path = price_node.path

    if price in price_node.text:
        before, after = price_node.text.split(price, 1)
        for candidate in (before, after):
            candidate_text = _prepare_candidate_text(candidate)
            if _is_valid_candidate(candidate_text):
                return candidate_text

    best_text: Optional[str] = None
    best_score = 0

    for distance, idx in enumerate(range(price_index - 1, -1, -1), start=1):
        candidate_node = nodes[idx]
        candidate_text = _prepare_candidate_text(candidate_node.text)
        if not candidate_text:
            continue
        score = _score_candidate_from_text(
            candidate_text, candidate_node.path, price_path, distance
        )
        if score > best_score:
            best_score = score
            best_text = candidate_text
        if distance >= 8 and best_score > 0:
            break
        if _common_prefix_length(candidate_node.path, price_path) == 0 and distance >= 4:
            if best_score > 0:
                break

    if best_text:
        return best_text

    for distance, idx in enumerate(range(price_index + 1, len(nodes)), start=1):
        candidate_node = nodes[idx]
        candidate_text = _prepare_candidate_text(candidate_node.text)
        if not candidate_text:
            continue
        score = _score_candidate_from_text(
            candidate_text, candidate_node.path, price_path, distance + 2
        )
        if score > best_score:
            best_score = score
            best_text = candidate_text
        if distance >= 6 and best_score > 0:
            break

    return best_text


def _locate_node_for_price(
    nodes: Sequence[_TextNode],
    price: str,
    consumed: list[int],
    start_index: int,
) -> Optional[int]:
    node_count = len(nodes)
    if node_count == 0:
        return None

    for idx in range(start_index, node_count):
        text = nodes[idx].text
        pos = text.find(price, consumed[idx])
        if pos != -1:
            consumed[idx] = pos + len(price)
            return idx

    for idx in range(0, node_count):
        text = nodes[idx].text
        pos = text.find(price, consumed[idx])
        if pos != -1:
            consumed[idx] = pos + len(price)
            return idx

    return None


def _normalize_availability_value(value: str) -> str:
    value = _WHITESPACE_RE.sub(" ", value)
    return value.strip(" :.,;-–—")


def _match_availability_patterns(
    text: str, patterns: Sequence[tuple[re.Pattern[str], Optional[str]]]
) -> Optional[str]:
    for pattern, label in patterns:
        match = pattern.search(text)
        if match:
            matched = label if label is not None else match.group(0)
            return _normalize_availability_value(matched)
    return None


def _collect_availability_texts(
    nodes: Sequence[_TextNode],
    price_index: Optional[int],
    snippet: str,
    description: Optional[str],
) -> tuple[list[str], list[str]]:
    primary: list[str] = []
    fallback: list[str] = []
    seen_primary: set[str] = set()
    seen_fallback: set[str] = set()

    def add(target: list[str], seen: set[str], text: Optional[str]) -> None:
        if not text:
            return
        normalized = _WHITESPACE_RE.sub(" ", text).strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        target.append(normalized)

    add(primary, seen_primary, description)

    if price_index is not None:
        price_path = nodes[price_index].path
        min_prefix = max(1, len(price_path) - 1) if price_path else 1
        start = max(0, price_index - 3)
        end = min(len(nodes), price_index + 4)
        for idx in range(start, end):
            candidate_node = nodes[idx]
            if _common_prefix_length(candidate_node.path, price_path) < min_prefix:
                continue
            add(primary, seen_primary, candidate_node.text)

    add(fallback, seen_fallback, snippet)

    return primary, fallback


def _detect_availability(
    nodes: Sequence[_TextNode],
    price_index: Optional[int],
    snippet: str,
    description: Optional[str],
) -> Optional[str]:
    if not nodes and not snippet and not description:
        return None

    primary, fallback = _collect_availability_texts(nodes, price_index, snippet, description)
    if not primary and not fallback:
        return None

    for text in primary:
        result = _match_availability_patterns(text, _AVAILABILITY_OUT_OF_STOCK_MARKERS)
        if result:
            return result

    for text in primary:
        result = _match_availability_patterns(text, _AVAILABILITY_IN_STOCK_MARKERS)
        if result:
            return result

    for text in fallback:
        result = _match_availability_patterns(text, _AVAILABILITY_OUT_OF_STOCK_MARKERS)
        if result:
            return result

    for text in fallback:
        result = _match_availability_patterns(text, _AVAILABILITY_IN_STOCK_MARKERS)
        if result:
            return result

    return None


def _refine_snippet(snippet: str, price: str) -> str:
    if not snippet:
        return snippet

    candidate = snippet
    if price:
        idx = snippet.find(price)
        if idx != -1:
            before = _prepare_candidate_text(snippet[:idx])
            if _is_valid_candidate(before):
                candidate = before
            else:
                after = _prepare_candidate_text(snippet[idx + len(price) :])
                if _is_valid_candidate(after):
                    candidate = after
        else:
            candidate = _prepare_candidate_text(snippet)
    else:
        candidate = _prepare_candidate_text(snippet)

    if not candidate:
        return snippet.strip()
    return candidate


def extract_prices(html_text: str, *, context: int = 60) -> List[PriceResult]:
    """Extract probable prices from raw HTML and provide textual context."""

    stripped_html = _SCRIPT_STYLE_RE.sub(" ", html_text)
    search_text = html.unescape(stripped_html)
    nodes = _collect_text_nodes(stripped_html)
    consumed_positions = [0] * len(nodes)
    node_cursor = 0

    results: List[PriceResult] = []
    seen: set[tuple[str, str]] = set()

    for match in PRICE_PATTERN.finditer(search_text):
        if _is_inside_html_tag(search_text, match.start()):
            continue
        snippet = _clean_snippet(
            _visible_text_window(
                search_text,
                max(match.start(), 0),
                min(match.end(), len(search_text)),
                context,
            )
        )
        price = match.group().strip()

        description: Optional[str] = None
        node_index = _locate_node_for_price(nodes, price, consumed_positions, node_cursor)
        if node_index is not None:
            node_cursor = node_index
            description = _select_best_neighbor_description(nodes, node_index, price)

        if not description:
            description = _refine_snippet(snippet, price)

        if not description:
            description = price

        if len(description) > 160:
            description = f"{description[:157]}..."

        availability = _detect_availability(nodes, node_index, snippet, description)

        key = (description, price)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            PriceResult(description=description, price=price, availability=availability)
        )

    return results


def iter_prices(html_text: str) -> Iterable[str]:
    """Yield raw price strings from *html_text*."""

    search_text = _SCRIPT_STYLE_RE.sub(" ", html_text)
    search_text = html.unescape(search_text)

    for match in PRICE_PATTERN.finditer(search_text):
        if _is_inside_html_tag(search_text, match.start()):
            continue
        yield match.group().strip()


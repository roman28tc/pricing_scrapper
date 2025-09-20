"""Simple HTTP server that scrapes prices from a provided URL."""

from __future__ import annotations

import argparse
import html
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:  # pragma: no cover - optional dependency that may not be installed in tests
    from playwright.sync_api import (
        Error as PlaywrightError,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError:  # pragma: no cover - keep fallback behaviour when Playwright is absent
    sync_playwright = None
    PlaywrightError = PlaywrightTimeoutError = Exception

from pricing_scrapper.scraper import PriceResult, extract_prices

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT_SECONDS = 20
REQUEST_TIMEOUT_MS = REQUEST_TIMEOUT_SECONDS * 1000

MAX_PAGINATION_PAGES = 20


@dataclass
class _PaginationLink:
    href: str
    text: str
    attrs: dict[str, str]


class _PaginationLinkParser(HTMLParser):
    """Collect anchors from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[_PaginationLink] = []
        self._current_attrs: dict[str, str] | None = None
        self._current_text_parts: list[str] = []
        self._nested_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag == "a":
            attr_dict = {name.lower(): value for name, value in attrs if value is not None}
            href = attr_dict.get("href")
            if not href:
                self._current_attrs = None
                self._current_text_parts = []
                self._nested_depth = 0
                return
            self._current_attrs = attr_dict
            self._current_text_parts = []
            self._nested_depth = 0
        elif self._current_attrs is not None:
            self._nested_depth += 1

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if self._current_attrs is None:
            return
        if tag == "a" and self._nested_depth == 0:
            href = self._current_attrs.get("href")
            if href:
                text = "".join(self._current_text_parts).strip()
                self.links.append(
                    _PaginationLink(href=href, text=text, attrs=self._current_attrs.copy())
                )
            self._current_attrs = None
            self._current_text_parts = []
        elif tag == "a":
            if self._nested_depth > 0:
                self._nested_depth -= 1
        elif self._nested_depth > 0:
            self._nested_depth -= 1

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._current_attrs is not None and data:
            self._current_text_parts.append(data)

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag == "a":
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)


_PAGINATION_TEXT_HINTS = {
    "next",
    "next page",
    "следующая",
    "следующая страница",
    "след.",
    "weiter",
    "suivant",
    "далі",
}

_PAGINATION_ARROW_TEXTS = {">", "»", "›", "→"}

_PAGINATION_HREF_HINTS = (
    "page=",
    "paged=",
    "pagination",
    "per_page=",
    "p=",
    "offset=",
    "start=",
    "page/",
)


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url)
    normalized = parsed._replace(fragment="")
    # Ensure that paths like ``""`` and ``"/"`` normalise consistently
    path = normalized.path or "/"
    return urlunsplit((normalized.scheme, normalized.netloc, path, normalized.query, ""))


def _looks_like_pagination_link(link: _PaginationLink, absolute_url: str) -> bool:
    text_lower = link.text.strip().casefold()
    attrs_lower = " ".join(link.attrs.get(name, "") for name in ("rel", "class", "aria-label", "title"))
    attrs_lower = attrs_lower.casefold()

    if text_lower in _PAGINATION_TEXT_HINTS:
        return True

    if text_lower in _PAGINATION_ARROW_TEXTS and (
        "next" in attrs_lower or "page" in attrs_lower or "pagination" in attrs_lower
    ):
        return True

    href_lower = link.href.casefold()
    if any(marker in href_lower for marker in _PAGINATION_HREF_HINTS):
        return True

    if "next" in attrs_lower:
        return True

    compact_text = text_lower.replace(" ", "")
    if compact_text.isdigit():
        if any(marker in href_lower for marker in _PAGINATION_HREF_HINTS):
            return True
        if "page" in attrs_lower or "pagination" in attrs_lower:
            return True
        parsed = urlsplit(absolute_url)
        path_parts = [segment for segment in parsed.path.split("/") if segment]
        if any(part.casefold().startswith("page") for part in path_parts):
            return True
        query_params = parse_qs(parsed.query)
        for values in query_params.values():
            if any(value.isdigit() for value in values):
                return True

    return False


def _discover_pagination_urls(html_text: str, page_url: str) -> list[str]:
    parser = _PaginationLinkParser()
    parser.feed(html_text)
    parser.close()

    base = urlsplit(page_url)
    base_netloc = base.netloc.casefold()
    base_scheme = base.scheme
    base_normalized = _normalize_url(page_url)

    discovered: list[str] = []
    seen: set[str] = set()

    for link in parser.links:
        href = link.href.strip()
        if not href or href.startswith("#"):
            continue
        href_lower = href.casefold()
        if href_lower.startswith(("javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.casefold() != base_netloc:
            continue
        if not parsed.scheme:
            parsed = parsed._replace(scheme=base_scheme)
        normalized = _normalize_url(urlunsplit(parsed))
        if normalized == base_normalized:
            continue
        if normalized in seen:
            continue
        if not _looks_like_pagination_link(link, normalized):
            continue
        seen.add(normalized)
        discovered.append(normalized)

    return discovered


def _collect_paginated_pages(start_url: str, *, limit: int = MAX_PAGINATION_PAGES) -> list[tuple[str, str]]:
    queue: deque[str] = deque([start_url])
    queued: set[str] = {_normalize_url(start_url)}
    visited: set[str] = set()
    pages: list[tuple[str, str]] = []

    while queue and len(visited) < limit:
        current = queue.popleft()
        normalized_current = _normalize_url(current)
        queued.discard(normalized_current)
        if normalized_current in visited:
            continue

        html_text = fetch(current)
        pages.append((current, html_text))
        visited.add(normalized_current)

        if len(visited) >= limit:
            continue

        for candidate in _discover_pagination_urls(html_text, current):
            normalized_candidate = _normalize_url(candidate)
            if normalized_candidate in visited or normalized_candidate in queued:
                continue
            if len(visited) + len(queued) >= limit:
                continue
            queue.append(candidate)
            queued.add(normalized_candidate)

    return pages


def scrape_site(url: str, *, limit: int = MAX_PAGINATION_PAGES) -> tuple[list[PriceResult], int]:
    pages = _collect_paginated_pages(url, limit=limit)
    results: list[PriceResult] = []
    seen: set[tuple[str, str]] = set()

    for _page_url, html_text in pages:
        for item in extract_prices(html_text):
            key = (item.description, item.price)
            if key in seen:
                continue
            seen.add(key)
            results.append(item)

    return results, len(pages)


def _format_summary(product_count: int, page_count: int) -> str:
    page_word = "page" if page_count == 1 else "pages"
    return f"{product_count} products have been scrapped from {page_count} {page_word}"


def fetch(url: str) -> str:
    if sync_playwright is not None:
        try:
            return _fetch_with_playwright(url)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            raise URLError(f"Playwright failed to fetch {url}: {exc}") from exc

    return _fetch_with_urllib(url)


def _fetch_with_urllib(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # nosec B310 - controlled URL
        return response.read().decode(
            response.headers.get_content_charset() or "utf-8", errors="replace"
        )


def _fetch_with_playwright(url: str) -> str:
    assert sync_playwright is not None  # for type-checkers

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            page.set_default_timeout(REQUEST_TIMEOUT_MS)
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)
            try:
                page.wait_for_load_state(
                    "networkidle", timeout=max(REQUEST_TIMEOUT_MS // 2, 1)
                )
            except PlaywrightTimeoutError:
                pass
            html_content = page.content()
        finally:
            context.close()
            browser.close()

    return html_content


def validate_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if not parsed.scheme:
        parsed = urlparse(f"https://{value}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Please provide a valid HTTP or HTTPS URL.")
    return parsed.geturl()


def render_page(
    url: str = "",
    error: str | None = None,
    results: list[PriceResult] | None = None,
    summary: str | None = None,
) -> bytes:
    rows = ""
    if results:
        for item in results:
            rows += (
                "<tr><td>{description}</td><td>{price}</td></tr>".format(
                    description=html.escape(item.description),
                    price=html.escape(item.price),
                )
            )
    elif results is not None:
        rows = '<tr><td colspan="2">No prices were detected on the page.</td></tr>'

    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    summary_html = f'<p class="summary">{html.escape(summary)}</p>' if summary else ""

    page = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Pricing Scraper</title>
        <style>
          body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 900px;
            margin: 2rem auto;
            padding: 0 1.5rem;
            line-height: 1.5;
          }}
          form {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-bottom: 1.5rem;
          }}
          input[type=url] {{
            flex: 1 1 300px;
            padding: 0.6rem;
            font-size: 1rem;
          }}
          button {{
            padding: 0.6rem 1.2rem;
            font-size: 1rem;
            cursor: pointer;
          }}
          table {{
            width: 100%;
            border-collapse: collapse;
          }}
          th, td {{
            border-bottom: 1px solid #ccc;
            padding: 0.75rem;
            text-align: left;
          }}
          th {{
            background-color: rgba(0, 0, 0, 0.05);
          }}
          tbody tr:nth-child(even) td {{
            background-color: rgba(0, 0, 0, 0.03);
          }}
          .error {{
            color: #d32f2f;
            margin-bottom: 1rem;
          }}
          .summary {{
            font-weight: 600;
            margin-bottom: 0.75rem;
          }}
        </style>
      </head>
      <body>
        <h1>Pricing Scraper</h1>
        <p>Paste the URL of a page that contains products with prices. The scraper will attempt to detect them and list the results.</p>
        <form method="post">
          <input type="url" name="url" value="{html.escape(url)}" placeholder="https://example.com/products" required>
          <button type="submit">Scrape</button>
        </form>
        {error_html}
        {summary_html}
        <table>
          <thead>
            <tr><th>Description</th><th>Price</th></tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </body>
    </html>
    """
    return page.encode("utf-8")


class ScraperHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - method name required by BaseHTTPRequestHandler
        query = parse_qs(self._parsed_path.query)
        url = query.get("url", [""])[0]
        results = None
        error = None
        summary = None
        if url:
            try:
                validated = validate_url(url)
                results, page_count = scrape_site(validated)
                summary = _format_summary(len(results), page_count)
            except (ValueError, URLError, HTTPError) as exc:
                error = str(exc)

        body = render_page(url=url, error=error, results=results, summary=summary)
        self._send_response(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length).decode("utf-8") if length else ""
        params = parse_qs(data)
        url = params.get("url", [""])[0]

        error = None
        results = None
        summary = None
        if url:
            try:
                validated = validate_url(url)
                results, page_count = scrape_site(validated)
                summary = _format_summary(len(results), page_count)
            except (ValueError, URLError, HTTPError) as exc:
                error = str(exc)

        body = render_page(url=url, error=error, results=results, summary=summary)
        self._send_response(body)

    def _send_response(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @property
    def _parsed_path(self):
        from urllib.parse import urlparse

        return urlparse(self.path)

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - keep output clean
        return


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), ScraperHandler)
    print(f"Serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pricing scraper web server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()


"""Tests for the dynamic HTML fetching helper."""

from urllib.error import URLError

import pytest


def test_fetch_uses_stdlib_when_playwright_missing(monkeypatch):
    import importlib

    server = importlib.import_module("server")

    monkeypatch.setattr(server, "sync_playwright", None)

    def fake_fetch(url: str) -> str:
        assert url == "https://example.com"
        return "<html></html>"

    monkeypatch.setattr(server, "_fetch_with_urllib", fake_fetch)

    assert server.fetch("https://example.com") == "<html></html>"


def test_fetch_wraps_playwright_errors(monkeypatch):
    import importlib

    server = importlib.import_module("server")

    class DummyError(Exception):
        pass

    monkeypatch.setattr(server, "sync_playwright", object())
    monkeypatch.setattr(server, "PlaywrightError", DummyError)
    monkeypatch.setattr(server, "PlaywrightTimeoutError", DummyError)

    def boom(url: str) -> str:
        raise DummyError("boom")

    monkeypatch.setattr(server, "_fetch_with_playwright", boom)

    with pytest.raises(URLError) as exc:
        server.fetch("https://example.com")

    assert "Playwright failed to fetch" in str(exc.value)


def test_playwright_timeout_fallback(monkeypatch):
    import importlib

    server = importlib.reload(importlib.import_module("server"))

    class DummyTimeout(Exception):
        pass

    class DummyPage:
        def __init__(self):
            self.goto_calls = []
            self.wait_calls = []
            self.default_timeout = None

        def set_default_timeout(self, value):
            self.default_timeout = value

        def goto(self, url, wait_until, timeout):
            self.goto_calls.append((url, wait_until, timeout))

        def wait_for_load_state(self, state, timeout):
            self.wait_calls.append((state, timeout))
            raise DummyTimeout("network idle never reached")

        def content(self):
            return "<html>ok</html>"

    class DummyContext:
        def __init__(self, page: DummyPage):
            self.page = page
            self.closed = False

        def new_page(self):
            return self.page

        def close(self):
            self.closed = True

    class DummyBrowser:
        def __init__(self, page: DummyPage):
            self.page = page
            self.headless = None
            self.closed = False

        def new_context(self, user_agent):
            self.user_agent = user_agent
            return DummyContext(self.page)

        def close(self):
            self.closed = True

    class DummyChromium:
        def __init__(self, page: DummyPage):
            self.page = page

        def launch(self, headless):
            browser = DummyBrowser(self.page)
            browser.headless = headless
            return browser

    class DummyPlaywright:
        def __init__(self, page: DummyPage):
            self.chromium = DummyChromium(page)

    class DummyManager:
        def __init__(self, page: DummyPage):
            self.page = page

        def __call__(self):
            return self

        def __enter__(self):
            return DummyPlaywright(self.page)

        def __exit__(self, exc_type, exc, tb):
            return False

    page = DummyPage()

    manager = DummyManager(page)
    monkeypatch.setattr(server, "sync_playwright", manager)
    monkeypatch.setattr(server, "PlaywrightTimeoutError", DummyTimeout)

    html = server._fetch_with_playwright("https://example.com")

    assert html == "<html>ok</html>"
    assert page.default_timeout == server.REQUEST_TIMEOUT_MS
    assert page.goto_calls == [
        ("https://example.com", "domcontentloaded", server.REQUEST_TIMEOUT_MS)
    ]
    assert page.wait_calls == [
        ("networkidle", max(server.REQUEST_TIMEOUT_MS // 2, 1))
    ]


def test_scrape_site_follows_pagination(monkeypatch):
    import importlib

    server = importlib.reload(importlib.import_module("server"))

    pages = {
        "https://example.com/products": """
            <html>
              <body>
                <div class='item'>
                  <span class='name'>Item One</span>
                  <span class='price'>$10.00</span>
                </div>
                <nav class='pagination'>
                  <a href='/products?page=2' class='next'>Next</a>
                </nav>
              </body>
            </html>
        """,
        "https://example.com/products?page=2": """
            <html>
              <body>
                <div class='item'>
                  <span class='name'>Item Two</span>
                  <span class='price'>$12.50</span>
                </div>
              </body>
            </html>
        """,
    }

    fetched: list[str] = []

    def fake_fetch(url: str) -> str:
        fetched.append(url)
        return pages[url]

    monkeypatch.setattr(server, "fetch", fake_fetch)

    results, page_count = server.scrape_site("https://example.com/products")

    assert page_count == 2
    assert {item.price for item in results} == {"$10.00", "$12.50"}
    assert fetched == [
        "https://example.com/products",
        "https://example.com/products?page=2",
    ]


def test_scrape_site_without_pagination(monkeypatch):
    import importlib

    server = importlib.reload(importlib.import_module("server"))

    pages = {
        "https://example.com/products": """
            <html>
              <body>
                <div class='item'>
                  <span class='name'>Solo Item</span>
                  <span class='price'>$8.00</span>
                </div>
              </body>
            </html>
        """,
    }

    monkeypatch.setattr(server, "fetch", lambda url: pages[url])

    results, page_count = server.scrape_site("https://example.com/products")

    assert page_count == 1
    assert {item.price for item in results} == {"$8.00"}


def test_format_summary():
    import importlib

    server = importlib.reload(importlib.import_module("server"))

    assert (
        server._format_summary(5, 1)
        == "5 products have been scrapped from 1 page"
    )
    assert (
        server._format_summary(3, 4)
        == "3 products have been scrapped from 4 pages"
    )

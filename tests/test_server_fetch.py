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

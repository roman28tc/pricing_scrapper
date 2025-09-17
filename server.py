"""Simple HTTP server that scrapes prices from a provided URL."""

from __future__ import annotations

import argparse
import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from pricing_scrapper.scraper import PriceResult, extract_prices

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:  # nosec B310 - controlled URL
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def validate_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if not parsed.scheme:
        parsed = urlparse(f"https://{value}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Please provide a valid HTTP or HTTPS URL.")
    return parsed.geturl()


def render_page(url: str = "", error: str | None = None, results: list[PriceResult] | None = None) -> bytes:
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
        if url:
            try:
                validated = validate_url(url)
                html_text = fetch(validated)
                results = extract_prices(html_text)
            except (ValueError, URLError, HTTPError) as exc:
                error = str(exc)

        body = render_page(url=url, error=error, results=results)
        self._send_response(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length).decode("utf-8") if length else ""
        params = parse_qs(data)
        url = params.get("url", [""])[0]

        error = None
        results = None
        try:
            validated = validate_url(url)
            html_text = fetch(validated)
            results = extract_prices(html_text)
        except (ValueError, URLError, HTTPError) as exc:
            error = str(exc)

        body = render_page(url=url, error=error, results=results)
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


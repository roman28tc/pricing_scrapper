# Pricing Scraper

A lightweight Python application that extracts prices from any publicly
available product listing page. Paste a URL into the form and the scraper
attempts to identify text that looks like a price, along with a short snippet
of surrounding context.

The project relies only on the Python standard library so it works out of the
box in restricted environments.

## Getting started

1. (Optional) Create and activate a virtual environment using your preferred
   tooling.
2. Run the development server:

   ```bash
   python server.py
   ```

3. Open `http://localhost:8000` in your browser and supply a page URL to
   scrape.

## Tests

Run the unit tests with:

```bash
pytest
```

## Notes

* The scraper uses a generic regular expression to detect prices. Results may
  vary depending on the structure of the target page.
* Be mindful of the target site's terms of service when scraping content.

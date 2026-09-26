"""Free web product discovery through a SearXNG-compatible search endpoint."""

import os
import re
from urllib.parse import urlparse

import requests

DEFAULT_SEARXNG_URLS = [
    "https://search.mectov.my.id",
    "https://searxng.eshnetwork.space",
]

RETAILER_DOMAINS = {
    "amazon": ("amazon.in", "amazon.com"),
    "flipkart": ("flipkart.com",),
    "croma": ("croma.com",),
    "reliance digital": ("reliancedigital.in",),
    "reliance": ("reliancedigital.in",),
    "vijay sales": ("vijaysales.com",),
    "tata cliq": ("tatacliq.com",),
    "poorvika": ("poorvika.com",),
    "samsung": ("samsung.com",),
    "apple": ("apple.com",),
}

PRICE_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)|"
    r"([\d,]{2,})(?:\s*(?:rs|inr))",
    re.I,
)


def _configured_urls():
    raw = os.getenv("SEARXNG_URLS") or os.getenv("SEARXNG_URL")
    if raw:
        return [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
    return DEFAULT_SEARXNG_URLS


def _retailer(url):
    host = (urlparse(url).hostname or "").lower()
    for name, domains in RETAILER_DOMAINS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return name.title() if name != "reliance" else "Reliance Digital"
    return None


def _price(text):
    if not text:
        return None
    for match in PRICE_RE.finditer(text):
        raw = next((x for x in match.groups() if x), None)
        if not raw:
            continue
        value = float(raw.replace(",", ""))
        if 1000 <= value <= 10000000 and not (1900 <= value <= 2100):
            return value
    return None


def search_web(query, limit=12, max_price=None):
    """Search the web and normalize product-like retailer results.

    Prices are search-result observations, not guaranteed checkout prices.
    The source URL is retained so the user can verify the listing.
    """
    errors = []
    for base_url in _configured_urls():
        try:
            response = requests.get(
                base_url.rstrip("/") + "/search",
                params={
                    "q": query,
                    "format": "json",
                    "language": "en",
                    "safesearch": 1,
                    "categories": "general",
                },
                headers={"Accept": "application/json", "User-Agent": "ByHub/0.5"},
                timeout=12,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results") or []
            products = []

            for item in results:
                url = item.get("url")
                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                if not url or not title:
                    continue

                retailer = _retailer(url)
                price = _price(" ".join((title, snippet)))
                if max_price is not None and price is not None and price > float(max_price):
                    continue

                productish = retailer or any(
                    word in (title + " " + snippet).lower()
                    for word in ("price", "buy", "₹", "inr", "rs.", "sale")
                )
                if not productish:
                    continue

                products.append({
                    "id": "web:" + str(abs(hash(url))),
                    "external_id": url,
                    "name": title,
                    "image": item.get("thumbnail"),
                    "best_price": price,
                    "currency": "INR" if price is not None else None,
                    "retailer": retailer or "Web result",
                    "url": url,
                    "snippet": snippet,
                    "source": "searxng",
                    "live": True,
                    "price_is_search_observation": price is not None,
                })

                if len(products) >= limit:
                    break

            return {
                "products": products,
                "search_engine": "SearXNG",
                "endpoint": base_url,
                "errors": errors,
            }
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append({"endpoint": base_url, "error": str(exc)[:180]})

    return {
        "products": [],
        "search_engine": "SearXNG",
        "endpoint": None,
        "errors": errors,
    }

"""Product discovery using free web search, with optional approved retailer APIs."""

from services.web_search import search_web
from services.amazon import AmazonCreatorsClient
from services.flipkart import FlipkartAffiliateClient


def search_retailers(query, limit_per_retailer=10, max_price=None):
    web = search_web(query, limit=max(12, limit_per_retailer * 2), max_price=max_price)
    results = list(web["products"])
    errors = list(web["errors"])
    enabled = ["SearXNG"] if web["endpoint"] else []

    # Keep approved retailer APIs available if credentials are later added.
    for provider in [AmazonCreatorsClient(), FlipkartAffiliateClient()]:
        if not provider.enabled:
            continue
        enabled.append(provider.retailer)
        try:
            results.extend(provider.search(query, limit_per_retailer, max_price=max_price))
        except Exception as exc:
            errors.append({"retailer": provider.retailer, "error": str(exc)[:180]})

    seen, unique = set(), []
    for product in results:
        key = (
            product.get("retailer"),
            (product.get("external_id") or product.get("url") or product.get("name") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)

    unique.sort(key=lambda p: (p.get("best_price") is None, p.get("best_price") or 10**18))
    return {
        "products": unique,
        "enabled_retailers": enabled,
        "errors": errors,
        "mode": "web_search" if web["endpoint"] else "no_search_endpoint",
    }

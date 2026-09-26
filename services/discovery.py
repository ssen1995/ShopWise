"""Live product discovery across approved retailer APIs."""

from services.amazon import AmazonCreatorsClient
from services.flipkart import FlipkartAffiliateClient

def search_retailers(query, limit_per_retailer=10, max_price=None):
    providers = [AmazonCreatorsClient(), FlipkartAffiliateClient()]
    results, errors, enabled = [], [], []
    for provider in providers:
        if not provider.enabled:
            continue
        enabled.append(provider.retailer)
        try:
            results.extend(provider.search(query, limit_per_retailer, max_price=max_price))
        except Exception as exc:
            errors.append({"retailer": provider.retailer, "error": str(exc)[:180]})

    # De-duplicate exact retailer/model results while preserving source truth.
    seen, unique = set(), []
    for p in results:
        key = (p.get("retailer"), (p.get("external_id") or p.get("name") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    unique.sort(key=lambda p: (p.get("best_price") is None, p.get("best_price") or 10**18))
    return {"products": unique, "enabled_retailers": enabled, "errors": errors}

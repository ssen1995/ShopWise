import re
from services.products import search_products

def run_agent(query):
    q = query.lower().strip()
    intent = "search"
    if any(x in q for x in ("deal", "discount", "cheap", "offer")):
        intent = "deal"
    elif any(x in q for x in ("buy or wait", "should i buy", "wait", "price history")):
        intent = "buy_or_wait"

    products = search_products(q, limit=12)

    budget_match = re.search(r"(?:under|below|less than)\s*₹?\s*([\d,]+)", q)
    if budget_match:
        budget = float(budget_match.group(1).replace(",", ""))
        filtered = [p for p in products if p["best_price"] is not None and p["best_price"] <= budget]
        if filtered:
            products = filtered

    for p in products:
        if p["best_price"] and p["average_price"]:
            p["vs_average_pct"] = round(
                (p["best_price"] - p["average_price"]) / p["average_price"] * 100, 1
            )
        else:
            p["vs_average_pct"] = None

    return {
        "intent": intent,
        "query": query,
        "products": products[:6],
        "message": "Results are generated from the ShopWise product and price database."
    }

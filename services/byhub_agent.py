import re
from datetime import datetime, timezone, timedelta
from statistics import mean

# ByHub AI v1: deterministic shopping analyst.
# This layer deliberately keeps product/price facts separate from conversation logic.
# An LLM can later sit on top of this structured result without changing the price engine.

BUDGET_RE = re.compile(r"(?:under|below|less than|max(?:imum)?|up to)\s*(?:₹|rs\.?\s*)?([\d,]+(?:\.\d+)?)", re.I)
RANGE_RE = re.compile(r"(?:₹|rs\.?\s*)?([\d,]+)\s*(?:-|to)\s*(?:₹|rs\.?\s*)?([\d,]+)", re.I)

def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None

def extract_preferences(text):
    q = (text or "").lower()
    budget_max = None
    budget_min = None

    m = RANGE_RE.search(q)
    if m:
        budget_min, budget_max = _num(m.group(1)), _num(m.group(2))
    else:
        m = BUDGET_RE.search(q)
        if m:
            budget_max = _num(m.group(1))

    intent = "product_search"
    if any(x in q for x in ("should i buy", "buy or wait", "wait", "good time to buy", "price right now")):
        intent = "buy_or_wait"
    elif any(x in q for x in ("price history", "historical price", "price trend", "getting cheaper", "getting expensive", "when was it cheapest")):
        intent = "price_analysis"
    elif any(x in q for x in ("deal", "discount", "offer", "sale", "cheap")):
        intent = "deal_hunting"
    elif any(x in q for x in ("compare", "versus", " vs ", "difference between")):
        intent = "comparison"

    priorities = []
    priority_terms = {
        "camera": ["camera", "photography", "photos", "video"],
        "gaming": ["gaming", "games", "fps"],
        "battery": ["battery", "battery life"],
        "performance": ["performance", "fast", "processor", "cpu", "gpu"],
        "noise_cancellation": ["noise cancellation", "anc"],
        "sound": ["sound", "audio", "music"],
        "calls": ["calls", "microphone", "meetings"],
        "portability": ["portable", "lightweight", "travel"],
        "display": ["display", "screen", "oled"],
        "storage": ["storage", "ssd", "disk"],
        "ram": ["ram", "memory"],
    }
    for key, terms in priority_terms.items():
        if any(t in q for t in terms):
            priorities.append(key)

    urgency = "unknown"
    if any(x in q for x in ("today", "now", "need it now", "urgent")):
        urgency = "now"
    elif any(x in q for x in ("not urgent", "can wait", "no rush", "later")):
        urgency = "flexible"

    return {
        "intent": intent,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "priorities": priorities,
        "urgency": urgency,
        "raw_query": text or "",
    }

def price_analysis(product):
    history = product.get("history") or []
    offers = product.get("offers") or []
    current = product.get("best_price")
    values = [float(x["price"]) for x in history if x.get("price") is not None]

    result = {
        "current": current,
        "average": product.get("avg"),
        "published_low": product.get("low"),
        "observations": len(values),
        "tracked_days": product.get("tracked_days"),
        "trend": "unknown",
        "volatility": "unknown",
        "position": "insufficient_data",
        "recent_low": None,
        "recent_average": None,
        "retailer_difference": None,
    }

    if current is not None and result["average"]:
        delta = (current - float(result["average"])) / float(result["average"]) * 100
        if delta <= -7:
            result["position"] = "well_below_average"
        elif delta < -2:
            result["position"] = "below_average"
        elif delta <= 7:
            result["position"] = "around_average"
        else:
            result["position"] = "above_average"
        result["vs_average_pct"] = round(delta, 1)

    if values:
        result["recent_low"] = min(values[-4:])
        result["recent_average"] = round(mean(values[-4:]), 2)
        if len(values) >= 4:
            first = values[0]
            last = values[-1]
            change = (last - first) / first * 100 if first else 0
            if change <= -5:
                result["trend"] = "falling"
            elif change >= 5:
                result["trend"] = "rising"
            else:
                result["trend"] = "stable"
            avg = mean(values)
            spread = ((max(values) - min(values)) / avg * 100) if avg else 0
            result["volatility"] = "high" if spread >= 15 else ("moderate" if spread >= 7 else "low")

    if len(offers) >= 2:
        result["retailer_difference"] = round(float(offers[-1]["price"]) - float(offers[0]["price"]), 2)

    return result

def _match_score(product, prefs):
    q = prefs["raw_query"].lower()
    name = (product.get("name") or "").lower()
    category = (product.get("category") or "").lower()
    score = 0

    tokens = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 2]
    for token in tokens:
        if token in name:
            score += 5
        elif token in category:
            score += 3

    if prefs["budget_max"] is not None and product.get("best_price") is not None:
        if product["best_price"] <= prefs["budget_max"]:
            score += 5
        else:
            score -= min(8, (product["best_price"] - prefs["budget_max"]) / max(prefs["budget_max"], 1) * 10)

    for p in prefs["priorities"]:
        if p.replace("_", " ") in name or p in category:
            score += 1

    return score

def run_agent(query, context=None):
    context = context or {}
    prefs = extract_preferences(query)
    # Keep the shopping session conversational. Prior user messages let short replies such as "yes", "40k", or "for travel" refine the existing request.
    prior = context.get("messages") or []
    prior_text = " ".join(
        str(m.get("content", "")) for m in prior[-8:]
        if isinstance(m, dict) and m.get("role") == "user"
    )
    merged_query = " ".join(x for x in [prior_text, context.get("last_query", ""), query] if x)

    # Import here so the agent module remains testable without starting FastAPI.
    from app import product_dict, db, SEED

    conn = db()
    rows = conn.execute(
        "SELECT id,name,category,image,mrp,avg,low,tracked_days,history_url,updated_at FROM products"
    ).fetchall()

    products = []
    for row in rows:
        p = product_dict(row)
        products.append(p)
    conn.close()

    prefs["raw_query"] = merged_query
    ranked = sorted(products, key=lambda p: (-_match_score(p, prefs), p["name"]))

    if prefs["budget_max"] is not None:
        in_budget = [p for p in ranked if p.get("best_price") is not None and p["best_price"] <= prefs["budget_max"]]
        if in_budget:
            ranked = in_budget + [p for p in ranked if p not in in_budget]

    selected = ranked[:6]

    analyses = {p["id"]: price_analysis(p) for p in selected}

    if not selected:
        message = "I couldn't find a matching product in the current ByHub catalog. Tell me the product type, budget, or a product name and I'll narrow it down."
    elif prefs["intent"] == "buy_or_wait":
        p = selected[0]
        a = analyses[p["id"]]
        position = {
            "well_below_average": "well below its stored average",
            "below_average": "below its stored average",
            "around_average": "around its stored average",
            "above_average": "above its stored average",
            "insufficient_data": "not supported by enough price observations",
        }.get(a["position"], "not yet clear")
        message = f"{p['name']} is currently {position}. I can compare the listed retailer prices and the historical price reference before you decide."
    elif prefs["intent"] == "price_analysis":
        p = selected[0]
        a = analyses[p["id"]]
        message = f"For {p['name']}, today's price is {('₹'+format(p['best_price'], ',.0f')) if p.get('best_price') else 'unavailable'}. The stored price trend is {a['trend']}, with {a['volatility']} volatility based on the observations currently available."
    elif prefs["intent"] == "deal_hunting":
        message = "I've prioritized products whose current price can be evaluated against stored historical context, rather than treating the MRP discount alone as the deal signal."
    elif prefs["intent"] == "comparison":
        message = "I can compare the matching products on price, historical price position, retailer difference and the trade-offs relevant to what you're buying."
    else:
        message = "I can narrow this down by budget, intended use and priorities. If your budget is flexible, I can also show a cheaper option and a stretch option."

    cards = []
    for p in selected:
        a = analyses[p["id"]]
        cards.append({
            "id": p["id"],
            "name": p["name"],
            "category": p.get("category"),
            "image": p.get("image"),
            "best_price": p.get("best_price"),
            "mrp": p.get("mrp"),
            "offers": p.get("offers", []),
            "average_price": a["average"],
            "published_low": a["published_low"],
            "vs_average_pct": a.get("vs_average_pct"),
            "trend": a["trend"],
            "volatility": a["volatility"],
            "price_position": a["position"],
            "observations": a["observations"],
            "reason": _reason(p, prefs, a),
            "price_sources": [
                {"retailer": o.get("retailer"), "price": o.get("price"),
                 "url": o.get("url"), "observed_at": o.get("observed_at")}
                for o in p.get("offers", []) if o.get("price") is not None
            ],
            "history_source": p.get("history_url"),
            "price_source_note": "Current price is the lowest price observed by ByHub from the listed retailer sources.",
            "history_source_note": "Historical context comes from the published price-history reference linked below."
        })

    follow_up = _follow_up(prefs, selected)

    return {
        "version": "1.0",
        "intent": prefs["intent"],
        "preferences": prefs,
        "message": message,
        "follow_up": follow_up,
        "products": cards,
        "context": {
            "last_query": query,
            "messages": prior[-8:] if isinstance(prior, list) else [],
        },
    }

def _reason(p, prefs, a):
    parts = []
    if prefs["budget_max"] is not None and p.get("best_price") is not None:
        parts.append("within your budget" if p["best_price"] <= prefs["budget_max"] else "above your stated budget")
    if a["position"] == "below_average":
        parts.append("currently below its stored average")
    elif a["position"] == "well_below_average":
        parts.append("well below its stored average")
    elif a["position"] == "above_average":
        parts.append("currently above its stored average")
    if a["trend"] != "unknown":
        parts.append(f"recent trend is {a['trend']}")
    return "; ".join(parts) if parts else "matches the current catalog search"

def _follow_up(prefs, selected):
    if not selected:
        return "What product are you looking for?"
    if prefs["budget_max"] is None and prefs["intent"] == "product_search":
        return "What's your comfortable budget? You can give me a hard ceiling or a target range."
    if not prefs["priorities"] and prefs["intent"] == "product_search":
        return "What matters most to you: performance, battery, camera, comfort, portability, or lowest price?"
    if prefs["urgency"] == "unknown" and prefs["intent"] in ("product_search", "buy_or_wait"):
        return "Do you need it now, or can you wait for a better price?"
    return None

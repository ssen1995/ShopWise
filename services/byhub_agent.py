import re
from datetime import datetime, timezone, timedelta
from statistics import mean

# ByHub AI v1: deterministic shopping analyst.
# This layer deliberately keeps product/price facts separate from conversation logic.
# An LLM can later sit on top of this structured result without changing the price engine.

BUDGET_RE = re.compile(r"(?:under|below|less than|max(?:imum)?|up to)\s*(?:₹|rs\.?\s*)?([\d,]+(?:\.\d+)?)(?:\s*(k|thousand|lakh|l))?", re.I)
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
            unit = (m.group(2) or "").lower()
            if unit in ("k", "thousand"):
                budget_max *= 1000
            elif unit in ("lakh", "l"):
                budget_max *= 100000

    intent = "product_search"
    if re.fullmatch(r"(hi|hello|hey|hiya|good morning|good afternoon|good evening|thanks|thank you|thx)[!. ]*", q):
        intent = "greeting"
    elif any(x in q for x in ("who are you", "what can you do", "how can you help", "what do you do")):
        intent = "capabilities"
    elif any(x in q for x in ("should i buy", "buy or wait", "wait", "good time to buy", "price right now")):
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
    # Classify the current turn before carrying any previous shopping context.
    # Greetings/capability questions must never inherit the previous product topic.
    prefs = extract_preferences(query)
    prior = context.get("messages") or []

    if prefs["intent"] in ("greeting", "capabilities"):
        merged_query = query
    else:
        # Keep the shopping session conversational. Prior user messages let short
        # replies such as "yes", "40k", or "for travel" refine the existing request.
        prior_text = " ".join(
            str(m.get("content", "")) for m in prior[-8:]
            if isinstance(m, dict) and m.get("role") == "user"
        )
        merged_query = " ".join(
            x for x in [prior_text, context.get("last_query", ""), query] if x
        )

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

    # Conversation-first behavior: broad shopping requests should gather the
    # missing decision criteria before dumping a catalog. A real shopping
    # assistant should understand the task first, then retrieve products.
    conversation_only = prefs["intent"] in ("greeting", "capabilities")
    broad_terms = {
        "headphones": ("Audio", "What is your comfortable budget for headphones?"),
        "earbuds": ("Audio", "What is your comfortable budget for earbuds?"),
        "camera": ("Cameras", "What's your budget for the camera, and what will you mainly use it for?"),
        "cameras": ("Cameras", "What's your budget for the camera, and what will you mainly use it for?"),
        "phone": ("Mobiles", "What's your budget for the phone, and what matters most: camera, performance, battery, or display?"),
        "mobile": ("Mobiles", "What's your budget for the phone, and what matters most: camera, performance, battery, or display?"),
        "smartphone": ("Mobiles", "What's your budget for the phone, and what matters most: camera, performance, battery, or display?"),
    }
    q_simple = (query or "").strip().lower()
    broad_match = next((v for k, v in broad_terms.items() if re.search(r"\b" + re.escape(k) + r"\b", q_simple)), None)

    if broad_match and prefs["intent"] == "product_search" and prefs["budget_max"] is None and not prefs["priorities"]:
        category, question = broad_match
        return {
            "version": "1.1",
            "intent": "product_search",
            "preferences": prefs,
            "message": f"Absolutely — I can help you find the right {q_simple}.",
            "follow_up": question,
            "products": [],
            "context": {"last_query": query, "messages": prior[-8:] if isinstance(prior, list) else []},
        }

    # Search live retailer catalogs first. Seeded/local products are historical
    # intelligence records, not a substitute for genuine product discovery.
    from services.discovery import search_retailers
    live_search = {"products": [], "enabled_retailers": [], "errors": []}
    if prefs["intent"] not in ("greeting", "capabilities"):
        live_search = search_retailers(
            merged_query,
            limit_per_retailer=10,
            max_price=prefs.get("budget_max"),
        )
    live_products = live_search["products"]

    if live_products:
        cards = []
        for p in live_products[:12]:
            cards.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "category": None,
                "image": p.get("image"),
                "best_price": p.get("best_price"),
                "mrp": None,
                "offers": [{
                    "retailer": p.get("retailer"),
                    "price": p.get("best_price"),
                    "url": p.get("url"),
                }],
                "average_price": None,
                "published_low": None,
                "vs_average_pct": None,
                "trend": "unknown",
                "volatility": "unknown",
                "price_position": "live_price_only",
                "observations": 0,
                "reason": "web-discovered result matching your request",
                "price_sources": [{
                    "retailer": p.get("retailer"),
                    "price": p.get("best_price"),
                    "url": p.get("url"),
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }],
                "history_source": None,
                "price_source_note": "Price shown when present is a search-result observation from the source page; verify the current checkout price before buying.",
                "history_source_note": "ByHub does not claim historical pricing for web-discovered results unless it has its own observations.",
            })
        return {
            "version": "2.0",
            "intent": prefs["intent"],
            "preferences": prefs,
            "message": f"I found {len(live_products)} current web results matching your request.",
            "follow_up": "Want me to narrow these by a specific feature, brand, or tighter budget?",
            "products": cards,
            "search": {
                "mode": live_search.get("mode", "web_search"),
                "retailers": live_search["enabled_retailers"],
                "errors": live_search["errors"],
            },
            "context": {"last_query": query, "messages": prior[-8:] if isinstance(prior, list) else []},
        }

    # If no live retailer result exists, never present unrelated demo products.
    # This is especially important for broad categories such as "smartphones".
    if not live_products and prefs["intent"] not in ("greeting", "capabilities"):
        scored = [(p, _match_score(p, prefs)) for p in products]
        relevant = [p for p, score in scored if score > 0]
        if not relevant:
            return {
                "version": "2.1",
                "intent": prefs["intent"],
                "preferences": prefs,
                "message": f"I understand you're looking for {q_simple or 'a product'}, but I don't have a genuine matching web result available yet. I won't show unrelated products just to fill the chat.",
                "follow_up": "I can try another search phrasing or you can give me a brand, model, budget, or key feature.",
                "products": [],
                "search": {
                    "mode": live_search.get("mode", "no_live_match"),
                    "retailers": live_search["enabled_retailers"],
                    "errors": live_search["errors"],
                },
                "context": {"last_query": query, "messages": prior[-8:] if isinstance(prior, list) else []},
            }

    # If there are relevant local records, they may be used as ByHub intelligence
    # fallback; unrelated seed products are never shown.
    scored = [(p, _match_score(p, prefs)) for p in products]
    ranked = [p for p, score in sorted(scored, key=lambda x: (-x[1], x[0]["name"])) if score > 0]

    if prefs["budget_max"] is not None:
        in_budget = [p for p in ranked if p.get("best_price") is not None and p["best_price"] <= prefs["budget_max"]]
        if in_budget:
            ranked = in_budget + [p for p in ranked if p not in in_budget]

    selected = ranked[:6]

    analyses = {p["id"]: price_analysis(p) for p in selected}

    if prefs["intent"] == "greeting":
        message = "Hi! I'm ByHub AI. I can help you find products, compare retailers, understand price history, and decide whether a current price is worth considering. What are you shopping for?"
    elif prefs["intent"] == "capabilities":
        message = "I can help you find a product, narrow choices by budget and priorities, compare options, check retailer prices, analyze price history, and explore whether buying now or waiting makes sense."
    elif not selected:
        message = "I don't have a genuine matching retailer result yet. I won't substitute unrelated demo products. Once a retailer API is connected, this search will query its live catalog."
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
    if prefs["intent"] in ("greeting", "capabilities"):
        selected = []
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

    follow_up = None if prefs["intent"] in ("greeting", "capabilities") else _follow_up(prefs, selected)

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

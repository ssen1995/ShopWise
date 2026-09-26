from datetime import datetime, timezone, timedelta
from database.database import connect

def record_offer(product_id, retailer, price, url, currency="INR", available=True):
    now = datetime.now(timezone.utc).isoformat()
    conn = connect()
    conn.execute(
        """INSERT INTO offers(product_id, retailer, price, url, currency, available, observed_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(product_id, retailer) DO UPDATE SET
             price=excluded.price, url=excluded.url, currency=excluded.currency,
             available=excluded.available, observed_at=excluded.observed_at""",
        (product_id, retailer, price, url, currency, int(available), now),
    )
    conn.execute(
        "INSERT INTO price_history(product_id, retailer, price, observed_at) VALUES(?,?,?,?)",
        (product_id, retailer, price, now),
    )
    conn.commit()
    conn.close()
    return now

def history(product_id):
    conn = connect()
    rows = conn.execute(
        """SELECT retailer, price, observed_at
           FROM price_history WHERE product_id=?
           ORDER BY observed_at ASC""",
        (product_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def price_intelligence(product_id):
    """Calculate transparent price-position metrics from ByHub's observations."""
    conn = connect()
    product = conn.execute(
        "SELECT id,name,mrp,average_price,lowest_price,tracked_days FROM products WHERE id=?",
        (product_id,),
    ).fetchone()
    rows = conn.execute(
        """SELECT price, observed_at FROM price_history
           WHERE product_id=? ORDER BY observed_at ASC""",
        (product_id,),
    ).fetchall()
    conn.close()

    if not product:
        return None

    prices = [float(r["price"]) for r in rows]
    current = min(prices) if prices else None

    # The current offer table is a better representation of today's
    # cross-retailer price than the historical observations.
    conn = connect()
    offer = conn.execute(
        "SELECT MIN(price) AS p FROM offers WHERE product_id=? AND available=1",
        (product_id,),
    ).fetchone()
    conn.close()
    if offer and offer["p"] is not None:
        current = float(offer["p"])

    def window(days):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        vals = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(r["observed_at"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    vals.append(float(r["price"]))
            except (ValueError, TypeError):
                pass
        return vals

    w30, w90, w365 = window(30), window(90), window(365)
    all_low = min(prices) if prices else product["lowest_price"]
    avg = (sum(prices) / len(prices)) if prices else product["average_price"]

    metrics = {
        "product_id": product_id,
        "current_price": current,
        "average_observed_price": round(avg, 2) if avg is not None else None,
        "all_time_observed_low": all_low,
        "30_day_low": min(w30) if w30 else None,
        "90_day_low": min(w90) if w90 else None,
        "365_day_low": min(w365) if w365 else None,
        "mrp": product["mrp"],
        "observations": len(prices),
        "tracked_days": product["tracked_days"],
    }

    if current is not None and avg:
        metrics["vs_average_pct"] = round((current - avg) / avg * 100, 1)
    if current is not None and product["mrp"]:
        metrics["below_mrp_pct"] = round((1 - current / product["mrp"]) * 100, 1)

    low = all_low
    if current is None or low is None:
        status = "insufficient_data"
    elif current <= low * 1.02:
        status = "near_record_low"
    elif avg and current <= avg * 0.97:
        status = "below_average"
    elif avg and current >= avg * 1.07:
        status = "above_average"
    else:
        status = "around_average"

    metrics["price_position"] = status
    metrics["interpretation"] = {
        "near_record_low": "Current price is within 2% of the lowest observed ByHub price.",
        "below_average": "Current price is below the observed average.",
        "above_average": "Current price is above the observed average.",
        "around_average": "Current price is close to the observed average.",
        "insufficient_data": "Not enough observations for a reliable price-position assessment.",
    }[status]
    return metrics

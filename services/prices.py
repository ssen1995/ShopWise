from datetime import datetime, timezone
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

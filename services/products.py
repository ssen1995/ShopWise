from database.database import connect

def _offers(conn, product_id):
    rows = conn.execute(
        """SELECT retailer, price, url, currency, available, observed_at
           FROM offers WHERE product_id=? ORDER BY price ASC""",
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def _history(conn, product_id):
    rows = conn.execute(
        """SELECT retailer, price, observed_at
           FROM price_history WHERE product_id=?
           ORDER BY observed_at ASC""",
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def serialize(conn, row):
    item = dict(row)
    offers = _offers(conn, item["id"])
    item["offers"] = offers
    item["history"] = _history(conn, item["id"])
    item["best_price"] = min((x["price"] for x in offers), default=None)
    return item

def search_products(query=None, category=None, limit=24):
    conn = connect()
    sql = "SELECT * FROM products WHERE 1=1"
    params = []
    if query:
        sql += " AND (name LIKE ? OR brand LIKE ? OR category LIKE ?)"
        term = f"%{query}%"
        params += [term, term, term]
    if category:
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY name LIMIT ?"
    params.append(max(1, min(limit, 100)))
    rows = conn.execute(sql, params).fetchall()
    result = [serialize(conn, r) for r in rows]
    conn.close()
    return result

def get_product(product_id):
    conn = connect()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    result = serialize(conn, row) if row else None
    conn.close()
    return result

def categories():
    conn = connect()
    rows = conn.execute(
        "SELECT category, COUNT(*) AS count FROM products GROUP BY category ORDER BY category"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

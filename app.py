import os, sqlite3, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB = BASE / "shopwise.db"

app = FastAPI(title="ByHub API", version="0.2.0")

STATIC = BASE / "static"
TEMPLATES = BASE / "templates"
STATIC.mkdir(exist_ok=True)
TEMPLATES.mkdir(exist_ok=True)

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

SEED = [
    {
        "id": "sony-wh1000xm6",
        "name": "Sony WH-1000XM6",
        "category": "Audio",
        "image": "https://sony.scene7.com/is/image/sonyglobalsolutions/GGB-8071_Olive_Gray_Gallery-1?$originalDimensions$",
        "sources": [
            {"retailer": "Flipkart", "price": 39990, "url": "https://www.flipkart.com/sony-wh-1000xm6-wireless-noise-cancellation-ai-reduction-bluetooth-wired/p/itmd27e0df955122"},
            {"retailer": "Amazon", "price": 39651, "url": "https://www.amazon.in/s?k=Sony+WH-1000XM6"},
        ],
        "mrp": 49990, "avg": 39081, "low": 34989, "tracked_days": 361,
        "history_url": "https://pricehistory.app/p/sony-wh-1000xm6-best-wireless-noise-canceling-8jeyRtce",
    },
    {
        "id": "canon-eos-r50",
        "name": "Canon EOS R50 + RF-S 18-45mm",
        "category": "Cameras",
        "image": "https://heyjimmy.in/wp-content/uploads/2023/03/Canon-EOS-R50-Mirrorless-Camera-with-RF-S18-45mm-F4.5-6.3-IS-STM-Lens-Online-Buy-Mumbai-India.jpg",
        "sources": [{"retailer": "Amazon", "price": 66990, "url": "https://www.amazon.in/s?k=Canon+EOS+R50+18-45mm"}],
        "mrp": 75995, "avg": 65557, "low": 52490, "tracked_days": 1244,
        "history_url": "https://pricehistory.app/p/canon-eos-r50-mirrorless-camera-body-rf-6CeZVo2h",
    },
    {
        "id": "samsung-s25-256",
        "name": "Samsung Galaxy S25 256GB",
        "category": "Mobiles",
        "image": "https://images.samsung.com/is/image/samsung/p6pim/in/sm-s931bzsgins/gallery/in-galaxy-s25-s931-sm-s931bzsgins-thumb-544566006?$344_344_PNG$",
        "sources": [{"retailer": "Flipkart", "price": 79999, "url": "https://www.flipkart.com/search?q=Samsung%20Galaxy%20S25%20256GB"}],
        "mrp": 84999, "avg": 73112, "low": 62990, "tracked_days": 394,
        "history_url": "https://www.cheapestinindia.com/price-history/galaxy-s25-5g-icyblue-256-gb--685f1e45206b1ef222944c8c",
    },
    {
        "id": "airpods-pro-3",
        "name": "Apple AirPods Pro 3",
        "category": "Audio",
        "image": "https://m.media-amazon.com/images/I/61SUj2aKoEL._SL1500_.jpg",
        "sources": [{"retailer": "Amazon", "price": 25899, "url": "https://www.amazon.in/s?k=AirPods+Pro+3"}],
        "mrp": 25900, "avg": 24707, "low": 17990, "tracked_days": 338,
        "history_url": "https://pricehistory.app/p/apple-airpods-pro-3",
    },
]

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS products(
      id TEXT PRIMARY KEY, name TEXT, category TEXT, image TEXT,
      mrp REAL, avg REAL, low REAL, tracked_days INTEGER,
      history_url TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS offers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id TEXT, retailer TEXT, price REAL, url TEXT, observed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS price_history(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id TEXT, retailer TEXT, price REAL, observed_at TEXT
    );
    """)
    now = datetime.now(timezone.utc).isoformat()
    for p in SEED:
        c.execute(
            """INSERT OR IGNORE INTO products
            (id,name,category,image,mrp,avg,low,tracked_days,history_url,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (p["id"], p["name"], p["category"], p["image"], p["mrp"],
             p["avg"], p["low"], p["tracked_days"], p["history_url"], now)
        )
        for s in p["sources"]:
            c.execute(
                "SELECT 1 FROM offers WHERE product_id=? AND retailer=? LIMIT 1",
                (p["id"], s["retailer"])
            )
            if not c.fetchone():
                c.execute(
                    "INSERT INTO offers(product_id,retailer,price,url,observed_at) VALUES (?,?,?,?,?)",
                    (p["id"], s["retailer"], s["price"], s["url"], now)
                )
                c.execute(
                    "INSERT INTO price_history(product_id,retailer,price,observed_at) VALUES (?,?,?,?)",
                    (p["id"], s["retailer"], s["price"], now)
                )
    c.commit()
    c.close()

init_db()

def product_dict(r):
    c = db()
    offers = [
        dict(x) for x in c.execute(
            "SELECT retailer,price,url,observed_at FROM offers WHERE product_id=? ORDER BY price",
            (r["id"],)
        )
    ]
    hist = [
        dict(x) for x in c.execute(
            "SELECT retailer,price,observed_at FROM price_history WHERE product_id=? ORDER BY observed_at",
            (r["id"],)
        )
    ]
    c.close()
    return {
        **dict(r),
        "offers": offers,
        "history": hist,
        "best_price": min((o["price"] for o in offers), default=None),
        "source": "ByHub database",
    }

@app.get("/")
def home():
    index = TEMPLATES / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "ByHub API", "docs": "/docs"}

@app.get("/api/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat(), "database": DB.name}

@app.get("/api/products")
def products(q: Optional[str] = None, category: Optional[str] = None, limit: int = 20):
    limit = min(max(limit, 1), 100)
    c = db()
    sql = "SELECT * FROM products WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR category LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if category:
        sql += " AND category=?"
        args.append(category)
    sql += " ORDER BY name LIMIT ?"
    args.append(limit)
    rows = c.execute(sql, args).fetchall()
    c.close()
    return [product_dict(r) for r in rows]

@app.get("/api/search")
def ranked_search(q: Optional[str] = None, category: Optional[str] = None, limit: int = 24):
    return search_ranked(q, category, limit)

@app.get("/api/categories")
def get_categories():
    from services.products import categories
    return categories()

@app.get("/api/products/{pid}")
def product(pid: str):
    c = db()
    r = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    c.close()
    if not r:
        return Response(status_code=404)
    return product_dict(r)

@app.get("/api/price-intelligence/{pid}")
def get_price_intelligence(pid: str):
    data = price_intelligence(pid)
    if data is None:
        return Response(status_code=404)
    return data

@app.get("/api/price-history/{pid}")
def price_history(pid: str):
    c = db()
    rows = c.execute(
        "SELECT retailer,price,observed_at FROM price_history WHERE product_id=? ORDER BY observed_at",
        (pid,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]

class AgentRequest(BaseModel):
    query: str

@app.post("/api/agent")
def agent(req: AgentRequest):
    q = req.query.lower()
    c = db()
    rows = c.execute("SELECT * FROM products").fetchall()
    c.close()

    matches = []
    for r in rows:
        text = (r["name"] + " " + r["category"]).lower()
        score = sum(
            1 for t in re.findall(r"[a-z0-9]+", q)
            if len(t) > 2 and t in text
        )
        if score:
            matches.append((score, r))

    matches.sort(key=lambda x: x[0], reverse=True)
    selected = [product_dict(r) for _, r in matches[:4]]
    if not selected:
        selected = [product_dict(r) for r in rows[:4]]

    budget = re.search(r"(?:under|below|less than)\s*₹?\s*([\d,]+)", q)
    if budget:
        b = float(budget.group(1).replace(",", ""))
        filtered = [p for p in selected if (p["best_price"] or 1e18) <= b]
        if filtered:
            selected = filtered

    intent = (
        "buy_or_wait" if any(x in q for x in ["buy", "wait", "price history", "should i"])
        else "deal" if any(x in q for x in ["deal", "discount", "cheap", "offer"])
        else "search"
    )

    out = []
    for p in selected:
        cur = p["best_price"]
        gap = ((cur - p["avg"]) / p["avg"] * 100) if cur and p["avg"] else 0
        out.append({
            "id": p["id"], "name": p["name"], "best_price": cur,
            "avg": p["avg"], "low": p["low"],
            "gap_vs_avg_pct": round(gap, 1),
            "offers": p["offers"], "image": p["image"],
        })

    return {
        "intent": intent,
        "query": req.query,
        "message": "Comparison generated from the ByHub product database. Historical figures are published records currently seeded into this MVP; retailer APIs can replace these seeds after credentials are added.",
        "products": out,
    }

@app.get("/api/image-proxy")
def image_proxy(url: str = Query(..., max_length=2000)):
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ByHub/0.2)"},
        timeout=15,
    )
    if r.status_code >= 400:
        return Response(status_code=r.status_code)
    ct = r.headers.get("content-type", "image/jpeg")
    if not ct.startswith("image/"):
        ct = "image/jpeg"
    return Response(
        content=r.content,
        media_type=ct,
        headers={"Cache-Control": "public, max-age=86400"},
    )

class DiscoveryObservationRequest(BaseModel):
    product_id: str
    retailer: str
    price: float
    url: str
    source_url: Optional[str] = None
    source_type: str = "manual_web_research"
    currency: str = "INR"
    available: bool = True

@app.post("/api/discovery/observation")
def discovery_observation(req: DiscoveryObservationRequest):
    return record_discovery_observation(DiscoveryObservation(
        product_id=req.product_id, retailer=req.retailer, price=req.price,
        url=req.url, source_url=req.source_url, source_type=req.source_type,
        currency=req.currency, available=req.available
    ))

@app.post("/api/sync")
def sync():
    return {
        "ok": True,
        "message": "Seed data is available. Add approved retailer credentials to enable live ingestion.",
        "amazon_enabled": bool(os.getenv("AMAZON_CLIENT_ID")),
        "flipkart_enabled": bool(os.getenv("FLIPKART_API_KEY")),
    }

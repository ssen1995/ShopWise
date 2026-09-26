import os, sqlite3, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB = BASE / "shopwise.db"

app = FastAPI(title="ByHub API", version="0.4.0")

STATIC = BASE / "static"
TEMPLATES = BASE / "templates"
STATIC.mkdir(exist_ok=True)
TEMPLATES.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

SEED = [
    {
        "id": "sony-wh1000xm6", "name": "Sony WH-1000XM6", "category": "Audio",
        "image": "https://sony.scene7.com/is/image/sonyglobalsolutions/GGB-8071_Olive_Gray_Gallery-1?$originalDimensions$",
        "sources": [
            {"retailer": "Amazon", "price": 39651, "url": "https://www.amazon.in/s?k=Sony+WH-1000XM6"},
            {"retailer": "Flipkart", "price": 39990, "url": "https://www.flipkart.com/sony-wh-1000xm6-wireless-noise-cancellation-ai-reduction-bluetooth-wired/p/itmd27e0df955122"}
        ],
        "mrp": 49990, "avg": 39139, "low": 34989, "tracked_days": 361,
        "history_url": "https://pricehistory.app/p/sony-wh-1000xm6-best-wireless-noise-canceling-8jeyRtce",
        "history": [
            ("2025-12-19", 37989), ("2026-01-16", 37765),
            ("2026-03-09", 37989), ("2026-07-03", 35990),
            ("2026-08-07", 37989), ("2026-09-10", 39990)
        ]
    },
    {
        "id": "canon-eos-r50", "name": "Canon EOS R50 + RF-S 18-45mm", "category": "Cameras",
        "image": "https://heyjimmy.in/wp-content/uploads/2023/03/Canon-EOS-R50-Mirrorless-Camera-with-RF-S18-45mm-F4.5-6.3-IS-STM-Lens-Online-Buy-Mumbai-India.jpg",
        "sources": [{"retailer": "Amazon", "price": 66990, "url": "https://www.amazon.in/s?k=Canon+EOS+R50+18-45mm"}],
        "mrp": 75995, "avg": 65557, "low": 52490, "tracked_days": 1244,
        "history_url": "https://pricehistory.app/p/canon-eos-r50-mirrorless-camera-body-rf-6CeZVo2h",
        "history": [
            ("2025-09-22", 57990), ("2025-10-04", 58990),
            ("2026-03-06", 59991), ("2026-07-08", 64990),
            ("2026-09-26", 66990)
        ]
    },
    {
        "id": "samsung-s25-256", "name": "Samsung Galaxy S25 256GB", "category": "Mobiles",
        "image": "https://reimg-teknosa-cloud-prod.mncdn.com/mnresize/600/600/productimage/125079836/125079836_0_MC/100328153.png",
        "sources": [{"retailer": "Flipkart", "price": 79999, "url": "https://www.flipkart.com/search?q=Samsung%20Galaxy%20S25%20256GB"}],
        "mrp": 84999, "avg": 73112, "low": 62990, "tracked_days": 394,
        "history_url": "https://www.cheapestinindia.com/price-history/galaxy-s25-5g-icyblue-256-gb--685f1e45206b1ef222944c8c",
        "history": [
            ("2026-07-19", 69999), ("2026-07-22", 79999),
            ("2026-07-31", 65999), ("2026-08-05", 79999),
            ("2026-08-10", 68999), ("2026-09-17", 79999)
        ]
    },
    {
        "id": "airpods-pro-3", "name": "Apple AirPods Pro 3", "category": "Audio",
        "image": "https://m.media-amazon.com/images/I/61SUj2aKoEL._SL1500_.jpg",
        "sources": [{"retailer": "Amazon", "price": 25899, "url": "https://www.amazon.in/s?k=AirPods+Pro+3"}],
        "mrp": 25900, "avg": 24707, "low": 17990, "tracked_days": 338,
        "history_url": "https://pricehistory.app/p/apple-airpods-pro-3-wireless-earbuds-active-5UXzXASj",
        "history": [
            ("2026-01-16", 24490), ("2026-02-06", 17990),
            ("2026-05-22", 23990), ("2026-06-16", 23990),
            ("2026-09-10", 25899)
        ]
    }
]

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()

    # Lightweight schema migration for databases created by earlier ByHub/ShopWise
    # versions. Render may retain an older SQLite file between deploys.
    existing = {row["name"] for row in c.execute("PRAGMA table_info(products)").fetchall()}
    migrations = {
        "image": "ALTER TABLE products ADD COLUMN image TEXT",
        "avg": "ALTER TABLE products ADD COLUMN avg REAL",
        "low": "ALTER TABLE products ADD COLUMN low REAL",
    }
    for col, statement in migrations.items():
        if existing and col not in existing:
            c.execute(statement)

    # Copy values from the original schema when those columns exist.
    existing = {row["name"] for row in c.execute("PRAGMA table_info(products)").fetchall()}
    if {"image_url", "image"}.issubset(existing):
        c.execute("UPDATE products SET image=image_url WHERE (image IS NULL OR image='') AND image_url IS NOT NULL")
    if {"average_price", "avg"}.issubset(existing):
        c.execute("UPDATE products SET avg=average_price WHERE avg IS NULL AND average_price IS NOT NULL")
    if {"lowest_price", "low"}.issubset(existing):
        c.execute("UPDATE products SET low=lowest_price WHERE low IS NULL AND lowest_price IS NOT NULL")

    c.executescript("""
    CREATE TABLE IF NOT EXISTS products(
      id TEXT PRIMARY KEY, name TEXT, category TEXT, image TEXT,
      mrp REAL, avg REAL, low REAL, tracked_days INTEGER,
      history_url TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS offers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id TEXT, retailer TEXT, price REAL, url TEXT,
      observed_at TEXT, UNIQUE(product_id, retailer)
    );
    CREATE TABLE IF NOT EXISTS price_history(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id TEXT, retailer TEXT, price REAL, observed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_history_product_time
      ON price_history(product_id, observed_at);
    CREATE TABLE IF NOT EXISTS observation_sources(
      id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, retailer TEXT,
      price REAL, source_type TEXT, source_url TEXT, observed_at TEXT
    );
    """)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS products(
      id TEXT PRIMARY KEY, name TEXT, category TEXT, image TEXT,
      mrp REAL, avg REAL, low REAL, tracked_days INTEGER,
      history_url TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS offers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id TEXT, retailer TEXT, price REAL, url TEXT,
      observed_at TEXT, UNIQUE(product_id, retailer)
    );
    CREATE TABLE IF NOT EXISTS price_history(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id TEXT, retailer TEXT, price REAL, observed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_history_product_time
      ON price_history(product_id, observed_at);
    CREATE TABLE IF NOT EXISTS observation_sources(
      id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, retailer TEXT,
      price REAL, source_type TEXT, source_url TEXT, observed_at TEXT
    );
    """)
    now = datetime.now(timezone.utc).isoformat()
    for p in SEED:
        c.execute(
            """INSERT OR IGNORE INTO products
            (id,name,category,image,mrp,avg,low,tracked_days,history_url,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (p["id"], p["name"], p["category"], p["image"], p["mrp"], p["avg"],
             p["low"], p["tracked_days"], p["history_url"], now)
        )
        for s in p["sources"]:
            exists = c.execute(
                "SELECT 1 FROM offers WHERE product_id=? AND retailer=?",
                (p["id"], s["retailer"])
            ).fetchone()
            if not exists:
                c.execute(
                    "INSERT INTO offers(product_id,retailer,price,url,observed_at) VALUES(?,?,?,?,?)",
                    (p["id"], s["retailer"], s["price"], s["url"], now)
                )
            else:
                c.execute(
                    "UPDATE offers SET price=?,url=?,observed_at=? WHERE product_id=? AND retailer=?",
                    (s["price"], s["url"], now, p["id"], s["retailer"])
                )
        existing = c.execute(
            "SELECT COUNT(*) AS n FROM price_history WHERE product_id=?",
            (p["id"],)
        ).fetchone()["n"]
        if existing < 3:
            for d, price in p["history"]:
                ts = d + "T12:00:00+00:00"
                if not c.execute(
                    "SELECT 1 FROM price_history WHERE product_id=? AND observed_at=?",
                    (p["id"], ts)
                ).fetchone():
                    c.execute(
                        "INSERT INTO price_history(product_id,retailer,price,observed_at) VALUES(?,?,?,?)",
                        (p["id"], "Historical source", price, ts)
                    )
    c.commit()
    c.close()

init_db()

def product_dict(r):
    c = db()
    offers = [dict(x) for x in c.execute(
        "SELECT retailer,price,url,observed_at FROM offers WHERE product_id=? ORDER BY price",
        (r["id"],)
    )]
    hist = [dict(x) for x in c.execute(
        "SELECT retailer,price,observed_at FROM price_history WHERE product_id=? ORDER BY observed_at",
        (r["id"],)
    )]
    c.close()
    return {**dict(r), "offers": offers, "history": hist,
            "best_price": min((o["price"] for o in offers), default=None),
            "source": "ByHub observations + published historical reference"}

def intelligence(pid):
    c = db()
    p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    offers = c.execute(
        "SELECT retailer,price,url,observed_at FROM offers WHERE product_id=? AND price IS NOT NULL ORDER BY price",
        (pid,)
    ).fetchall()
    hist = c.execute(
        "SELECT retailer,price,observed_at FROM price_history WHERE product_id=? ORDER BY observed_at",
        (pid,)
    ).fetchall()
    c.close()
    if not p:
        return None
    current = min((float(x["price"]) for x in offers), default=None)
    points = [{"date": x["observed_at"][:10], "price": float(x["price"])} for x in hist]
    vals = [x["price"] for x in points]
    avg = float(p["avg"]) if p["avg"] else (sum(vals)/len(vals) if vals else None)
    all_low = min([float(p["low"])] + vals) if vals else float(p["low"] or 0)
    def low_window(days):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        v = []
        for x in hist:
            try:
                ts = datetime.fromisoformat(x["observed_at"].replace("Z","+00:00"))
                if ts >= cutoff: v.append(float(x["price"]))
            except Exception:
                pass
        return min(v) if v else None
    return {
        "product_id": pid, "current_price": current,
        "average_price": round(avg,2) if avg is not None else None,
        "reported_low": float(p["low"]) if p["low"] else all_low,
        "observed_chart_low": min(vals) if vals else None,
        "low_30d": low_window(30), "low_90d": low_window(90), "low_365d": low_window(365),
        "mrp": float(p["mrp"]) if p["mrp"] else None,
        "tracked_days": p["tracked_days"], "observations": len(points),
        "history_url": p["history_url"], "chart": points,
        "vs_average_pct": round((current-avg)/avg*100,1) if current and avg else None,
        "below_mrp_pct": round((1-current/p["mrp"])*100,1) if current and p["mrp"] else None
    }

@app.get("/")
def home():
    return FileResponse(TEMPLATES / "index.html")

@app.get("/product/{pid}")
def product_page(pid: str):
    c = db()
    exists = c.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone()
    c.close()
    if not exists:
        return Response(status_code=404)
    return FileResponse(TEMPLATES / "index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat(), "database": DB.name}

@app.get("/api/products")
def products(q: Optional[str] = None, category: Optional[str] = None, limit: int = 24):
    limit = min(max(limit,1),100)
    c = db()
    # The deployed app may have been initialized by an earlier ByHub schema.
    # Read the common product fields explicitly so extra legacy columns do not matter.
    sql = "SELECT id,name,category,image,mrp,avg,low,tracked_days,history_url,updated_at FROM products WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR category LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if category:
        sql += " AND category=?"; args.append(category)
    sql += " ORDER BY name LIMIT ?"; args.append(limit)
    rows = c.execute(sql,args).fetchall(); c.close()
    return [product_dict(r) for r in rows]

@app.get("/api/search")
def search(q: Optional[str] = None, category: Optional[str] = None, limit: int = 24):
    rows = products(q, category, limit)
    if q:
        tokens = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t)>1]
        def score(p):
            text=(p["name"]+" "+p["category"]).lower()
            return sum(3 if t in p["name"].lower() else 1 for t in tokens if t in text)
        rows=sorted(rows,key=lambda p:(-score(p),p["name"]))
    return rows

@app.get("/api/categories")
def categories():
    c=db()
    rows=c.execute("SELECT category,COUNT(*) AS count FROM products WHERE category IS NOT NULL AND category != '' GROUP BY category ORDER BY category").fetchall()
    c.close()
    return [dict(r) for r in rows]

@app.get("/api/products/{pid}")
def product(pid: str):
    c=db(); r=c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone(); c.close()
    if not r: return Response(status_code=404)
    return product_dict(r)

@app.get("/api/price-history/{pid}")
def price_history(pid: str):
    c=db()
    rows=c.execute(
        "SELECT retailer,price,observed_at FROM price_history WHERE product_id=? ORDER BY observed_at",
        (pid,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]

@app.get("/api/price-intelligence/{pid}")
def price_intelligence(pid: str):
    data=intelligence(pid)
    return data if data else Response(status_code=404)

class AgentRequest(BaseModel):
    query: str
    context: Optional[dict] = None

@app.post("/api/agent")
def agent(req: AgentRequest):
    from services.byhub_agent import run_agent
    return run_agent(req.query, req.context or {})

@app.get("/api/image-proxy")
def image_proxy(url: str = Query(..., max_length=2000)):
    try:
        r=requests.get(url,headers={"User-Agent":"Mozilla/5.0 (compatible; ByHub/0.4)"},timeout=15)
        if r.status_code>=400: return Response(status_code=r.status_code)
        ct=r.headers.get("content-type","image/jpeg")
        if not ct.startswith("image/"): ct="image/jpeg"
        return Response(content=r.content,media_type=ct,headers={"Cache-Control":"public,max-age=86400"})
    except requests.RequestException:
        return Response(status_code=502)

class DiscoveryObservationRequest(BaseModel):
    product_id: str
    retailer: str
    price: float
    url: str
    source_url: Optional[str]=None
    source_type: str="manual_web_research"

@app.post("/api/discovery/observation")
def discovery_observation(req: DiscoveryObservationRequest):
    now=datetime.now(timezone.utc).isoformat()
    c=db()
    if not c.execute("SELECT 1 FROM products WHERE id=?", (req.product_id,)).fetchone():
        c.close(); return Response(status_code=404)
    c.execute("""INSERT INTO offers(product_id,retailer,price,url,observed_at) VALUES(?,?,?,?,?)
                 ON CONFLICT(product_id,retailer) DO UPDATE SET price=excluded.price,url=excluded.url,observed_at=excluded.observed_at""",
              (req.product_id,req.retailer,req.price,req.url,now))
    c.execute("INSERT INTO price_history(product_id,retailer,price,observed_at) VALUES(?,?,?,?)",
              (req.product_id,req.retailer,req.price,now))
    c.execute("INSERT INTO observation_sources(product_id,retailer,price,source_type,source_url,observed_at) VALUES(?,?,?,?,?,?)",
              (req.product_id,req.retailer,req.price,req.source_type,req.source_url,now))
    c.commit(); c.close()
    return {"ok":True,"observed_at":now}

@app.post("/api/sync")
def sync():
    return {"ok":True,"message":"ByHub is ready for approved retailer API/feed credentials.","amazon_enabled":bool(os.getenv("AMAZON_CLIENT_ID")),"flipkart_enabled":bool(os.getenv("FLIPKART_API_KEY"))}

import os
from datetime import datetime, timezone

from database.database import init_db, connect
from services.amazon import AmazonCreatorsClient
from services.flipkart import FlipkartAffiliateClient

def main():
    init_db()
    clients = [AmazonCreatorsClient(), FlipkartAffiliateClient()]
    conn = connect()
    for client in clients:
        started = datetime.now(timezone.utc).isoformat()
        if not client.enabled:
            conn.execute(
                "INSERT INTO sync_runs(retailer, started_at, finished_at, status, message) VALUES(?,?,?,?,?)",
                (client.retailer, started, datetime.now(timezone.utc).isoformat(),
                 "skipped", "API credentials not configured.")
            )
        else:
            # Live API implementation is intentionally isolated here.
            conn.execute(
                "INSERT INTO sync_runs(retailer, started_at, finished_at, status, message) VALUES(?,?,?,?,?)",
                (client.retailer, started, datetime.now(timezone.utc).isoformat(),
                 "ready", "Credentials detected; adapter ready for API implementation.")
            )
    conn.commit()
    conn.close()
    print("ShopWise price sync completed.")

if __name__ == "__main__":
    main()

# ShopWise

AI shopping + product discovery + price intelligence.

## Run locally

    pip install -r requirements.txt
    uvicorn app:app --reload

Open http://127.0.0.1:8000

## Current architecture

FastAPI + SQLite + retailer adapters + API-backed frontend.

The Amazon and Flipkart adapters are credential-ready but do not scrape retailer pages. Add approved API/affiliate credentials to a local .env file before enabling live ingestion.

The current database includes seeded product observations for development. Once live APIs are connected, ShopWise records its own timestamped observations in price_history.

import os
import requests

class FlipkartAffiliateClient:
    """Live Flipkart keyword search through the approved Affiliate API."""

    retailer = "Flipkart"

    def __init__(self):
        self.api_key = os.getenv("FLIPKART_API_KEY") or os.getenv("FLIPKART_AFFILIATE_TOKEN")
        self.affiliate_id = os.getenv("FLIPKART_AFFILIATE_ID")

    @property
    def enabled(self):
        return bool(self.api_key and self.affiliate_id)

    def search(self, query, limit=10, max_price=None):
        if not self.enabled:
            return []
        response = requests.get(
            "https://affiliate-api.flipkart.net/affiliate/1.0/search.json",
            params={"query": query, "resultCount": max(1, min(int(limit), 10))},
            headers={"Fk-Affiliate-Id": self.affiliate_id, "Fk-Affiliate-Token": self.api_key},
            timeout=15,
        )
        response.raise_for_status()
        out = []
        for row in response.json().get("productInfoList", []):
            base = row.get("productBaseInfoV1") or row.get("productBaseInfo") or {}
            price_obj = base.get("flipkartSellingPrice") or base.get("sellingPrice") or {}
            price = price_obj.get("amount") if isinstance(price_obj, dict) else None
            if max_price and price is not None and float(price) > float(max_price):
                continue
            images = base.get("imageUrls") or {}
            image = images.get("400x400") or images.get("275x275") or next(iter(images.values()), None)
            out.append({
                "id": "flipkart:" + str(base.get("productId", "")),
                "external_id": base.get("productId"),
                "name": base.get("title") or "Flipkart product",
                "image": image,
                "best_price": float(price) if price is not None else None,
                "currency": "INR",
                "retailer": self.retailer,
                "url": base.get("productUrl"),
                "source": "flipkart_affiliate_api",
                "live": True,
            })
        return out

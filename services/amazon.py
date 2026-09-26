import os
import time
import requests

class AmazonCreatorsClient:
    """Live Amazon India product search through the approved Creators API."""

    retailer = "Amazon"
    base_url = "https://creatorsapi.amazon"

    def __init__(self):
        self.client_id = os.getenv("AMAZON_CLIENT_ID")
        self.client_secret = os.getenv("AMAZON_CLIENT_SECRET")
        self.partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        self.marketplace = os.getenv("AMAZON_MARKETPLACE", "www.amazon.in")
        self.token_url = os.getenv("AMAZON_TOKEN_URL", "https://api.amazon.co.uk/auth/o2/token")
        self._token = None
        self._expires_at = 0

    @property
    def enabled(self):
        return all([self.client_id, self.client_secret, self.partner_tag])

    def _access_token(self):
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        if not self.enabled:
            raise RuntimeError("Amazon Creators API credentials are not configured")
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "creatorsapi/default",
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    @staticmethod
    def _first(obj, *paths):
        for path in paths:
            cur = obj
            try:
                for key in path.split("."):
                    if key.isdigit():
                        cur = cur[int(key)]
                    else:
                        cur = cur[key]
                if cur is not None:
                    return cur
            except (KeyError, IndexError, TypeError):
                pass
        return None

    def search(self, query, limit=10, max_price=None):
        if not self.enabled:
            return []
        payload = {
            "partnerTag": self.partner_tag,
            "keywords": query,
            "itemCount": max(1, min(int(limit), 10)),
            "searchIndex": "All",
            "marketplace": self.marketplace,
            "resources": [
                "images.primary.medium",
                "itemInfo.title",
                "itemInfo.byLineInfo",
                "offersV2.listings.price",
                "offersV2.listings.availability",
            ],
        }
        if max_price:
            payload["maxPrice"] = int(float(max_price) * 100)

        response = requests.post(
            self.base_url + "/catalog/v1/searchItems",
            headers={
                "Authorization": "Bearer " + self._access_token(),
                "Content-Type": "application/json",
                "x-marketplace": self.marketplace,
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        items = (data.get("searchResult") or {}).get("items") or []
        out = []
        for item in items:
            title = self._first(item, "itemInfo.title.displayValue", "itemInfo.title")
            image = self._first(item, "images.primary.medium.url", "images.primary.large.url")
            price = self._first(
                item,
                "offersV2.listings.0.price.amount",
                "offersV2.listings.0.price.money.amount",
            )
            out.append({
                "id": "amazon:" + str(item.get("asin", "")),
                "external_id": item.get("asin"),
                "name": title or "Amazon product",
                "image": image,
                "best_price": float(price) if price is not None else None,
                "currency": "INR",
                "retailer": self.retailer,
                "url": item.get("detailPageURL"),
                "source": "amazon_creators_api",
                "live": True,
            })
        return out

import os

class FlipkartAffiliateClient:
    """Credential-ready adapter for the Flipkart Affiliate API.

    Credentials must be supplied through environment variables. No web scraping
    is performed by this adapter.
    """
    retailer = "Flipkart"

    def __init__(self):
        self.api_key = os.getenv("FLIPKART_API_KEY")
        self.affiliate_id = os.getenv("FLIPKART_AFFILIATE_ID")

    @property
    def enabled(self):
        return bool(self.api_key and self.affiliate_id)

import os

class AmazonCreatorsClient:
    """Credential-ready adapter for Amazon Creators API.

    Credentials must be supplied through environment variables. This adapter
    intentionally does not scrape Amazon pages.
    """
    retailer = "Amazon"

    def __init__(self):
        self.client_id = os.getenv("AMAZON_CLIENT_ID")
        self.client_secret = os.getenv("AMAZON_CLIENT_SECRET")
        self.partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        self.marketplace = os.getenv("AMAZON_MARKETPLACE", "www.amazon.in")

    @property
    def enabled(self):
        return all([self.client_id, self.client_secret, self.partner_tag])

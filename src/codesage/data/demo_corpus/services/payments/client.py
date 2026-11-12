"""HTTP client for the external payment gateway."""
import time
import uuid

from .settings import HTTP_TIMEOUT, RETRIES


class GatewayTimeout(Exception):
    pass


class PaymentClient:
    """Charges cards through the gateway. Every request carries an idempotency key so retries never double-charge."""

    def __init__(self, transport, timeout=HTTP_TIMEOUT, retries=RETRIES):
        self.transport = transport
        self.timeout = timeout
        self.retries = retries

    def charge(self, account_id, amount_minor, currency="INR"):
        key = str(uuid.uuid4())
        for attempt in range(self.retries + 1):
            try:
                return self.transport.post("/charges", {"account": account_id, "amount": amount_minor,
                                                        "currency": currency}, idempotency_key=key, timeout=self.timeout)
            except GatewayTimeout:
                if attempt == self.retries:
                    raise
                time.sleep(min(2 ** attempt * 0.2, 2.0))  # exponential backoff, capped

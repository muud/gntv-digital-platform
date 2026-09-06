"""Payment provider interface and registry for partner payouts."""

from typing import Dict, Optional

from app.modules.partners.providers.base import (
    PaymentProviderBase,
    ProviderPayoutRequest,
    ProviderPayoutResult,
    ProviderReconciliationResult,
)
from app.modules.partners.providers.mock_provider import MockPaymentProvider

_PROVIDERS: Dict[str, PaymentProviderBase] = {
    "mock": MockPaymentProvider(),
    "sandbox": MockPaymentProvider(),
}


def get_payment_provider(name: Optional[str] = None) -> PaymentProviderBase:
    """Retrieve payment provider instance by name, defaulting to mock/sandbox."""
    provider_name = (name or "mock").strip().lower()
    provider = _PROVIDERS.get(provider_name)
    if not provider:
        raise ValueError(f"Unknown payment provider: {name}")
    return provider


__all__ = [
    "PaymentProviderBase",
    "ProviderPayoutRequest",
    "ProviderPayoutResult",
    "ProviderReconciliationResult",
    "MockPaymentProvider",
    "get_payment_provider",
]

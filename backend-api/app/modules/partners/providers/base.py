"""Payment provider abstraction base contracts and interfaces for partner payouts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ProviderPayoutRequest:
    payout_id: UUID
    partner_id: UUID
    amount: Decimal
    currency: str
    destination_reference: str
    destination_routing: str | None
    idempotency_key: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderPayoutResult:
    success: bool
    provider_transaction_id: str
    status: str  # "paid", "processing", "failed", "cancelled"
    error_message: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderReconciliationResult:
    matched: bool
    status: str  # "matched", "amount_mismatch", "currency_mismatch", "unknown_transaction", "failed_returned"
    provider_transaction_id: str
    reported_amount: Decimal | None
    reported_currency: str | None
    details: dict[str, Any] | None = None


class PaymentProviderBase(ABC):
    """Abstract interface that all payment gateway adapters must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier."""
        ...

    @abstractmethod
    def create_payout(self, request: ProviderPayoutRequest) -> ProviderPayoutResult:
        """Submit a payout instruction to the external payment rail."""
        ...

    @abstractmethod
    def get_payout_status(self, provider_transaction_id: str) -> ProviderPayoutResult:
        """Fetch status of an in-flight or executed payout."""
        ...

    @abstractmethod
    def cancel_payout(self, provider_transaction_id: str, reason: str | None = None) -> ProviderPayoutResult:
        """Attempt to cancel an uncollected or pending payout."""
        ...

    @abstractmethod
    def reconcile_transaction(
        self,
        provider_transaction_id: str,
        expected_amount: Decimal,
        expected_currency: str,
    ) -> ProviderReconciliationResult:
        """Verify external settlement record against expected internal ledger."""
        ...

"""Deterministic mock payment provider for sandbox execution and tests."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from typing import Any

from app.modules.partners.providers.base import (
    PaymentProviderBase,
    ProviderPayoutRequest,
    ProviderPayoutResult,
    ProviderReconciliationResult,
    utc_now,
)


class MockPaymentProvider(PaymentProviderBase):
    """Provider-neutral sandbox implementation that stores simulated transactions in-memory."""

    def __init__(self, simulate_failure: bool = False) -> None:
        self._simulate_failure = simulate_failure
        self._transactions: dict[str, dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        return "mock_sandbox_provider"

    def set_simulate_failure(self, simulate: bool) -> None:
        self._simulate_failure = simulate

    def record_external_transaction(
        self,
        provider_transaction_id: str,
        amount: Decimal,
        currency: str,
        status: str = "paid",
    ) -> None:
        """Helper to seed simulated external gateway transactions for reconciliation tests."""
        self._transactions[provider_transaction_id] = {
            "amount": amount,
            "currency": currency.upper(),
            "status": status,
            "created_at": utc_now().isoformat(),
        }

    def create_payout(self, request: ProviderPayoutRequest) -> ProviderPayoutResult:
        if self._simulate_failure or request.destination_reference.lower().endswith("fail"):
            return ProviderPayoutResult(
                success=False,
                provider_transaction_id="",
                status="failed",
                error_message="Simulated gateway rejection: account closed or invalid route",
                raw_response={"code": "GATEWAY_ERROR", "retryable": False},
            )

        # Deterministic transaction ID derived from idempotency key and payout ID
        tx_hash = hashlib.sha256(f"{request.payout_id}:{request.idempotency_key}".encode("utf-8")).hexdigest()[:16]
        tx_id = f"tx_mock_{tx_hash}"

        self._transactions[tx_id] = {
            "amount": request.amount,
            "currency": request.currency.upper(),
            "status": "paid",
            "destination": request.destination_reference,
            "created_at": utc_now().isoformat(),
        }

        return ProviderPayoutResult(
            success=True,
            provider_transaction_id=tx_id,
            status="paid",
            error_message=None,
            raw_response={"status": "succeeded", "rail": "sandbox_ach", "tx_id": tx_id},
        )

    def get_payout_status(self, provider_transaction_id: str) -> ProviderPayoutResult:
        tx = self._transactions.get(provider_transaction_id)
        if not tx:
            return ProviderPayoutResult(
                success=False,
                provider_transaction_id=provider_transaction_id,
                status="unknown",
                error_message="Transaction not found in mock provider ledger",
            )
        return ProviderPayoutResult(
            success=True,
            provider_transaction_id=provider_transaction_id,
            status=str(tx.get("status", "paid")),
            raw_response=tx,
        )

    def cancel_payout(self, provider_transaction_id: str, reason: str | None = None) -> ProviderPayoutResult:
        tx = self._transactions.get(provider_transaction_id)
        if not tx:
            return ProviderPayoutResult(
                success=False,
                provider_transaction_id=provider_transaction_id,
                status="failed",
                error_message="Transaction not found to cancel",
            )
        tx["status"] = "cancelled"
        tx["cancel_reason"] = reason or "Operator requested cancellation"
        return ProviderPayoutResult(
            success=True,
            provider_transaction_id=provider_transaction_id,
            status="cancelled",
            raw_response=tx,
        )

    def reconcile_transaction(
        self,
        provider_transaction_id: str,
        expected_amount: Decimal,
        expected_currency: str,
    ) -> ProviderReconciliationResult:
        tx = self._transactions.get(provider_transaction_id)
        if not tx:
            return ProviderReconciliationResult(
                matched=False,
                status="unknown_transaction",
                provider_transaction_id=provider_transaction_id,
                reported_amount=None,
                reported_currency=None,
                details={"reason": "Transaction reference does not exist on provider rail"},
            )

        reported_amount = Decimal(str(tx["amount"]))
        reported_currency = str(tx["currency"]).upper()
        status = str(tx.get("status", "paid"))

        if status in ("failed", "returned"):
            return ProviderReconciliationResult(
                matched=False,
                status="failed_returned",
                provider_transaction_id=provider_transaction_id,
                reported_amount=reported_amount,
                reported_currency=reported_currency,
                details={"reason": f"External payout returned with status: {status}"},
            )

        if reported_currency != expected_currency.upper():
            return ProviderReconciliationResult(
                matched=False,
                status="currency_mismatch",
                provider_transaction_id=provider_transaction_id,
                reported_amount=reported_amount,
                reported_currency=reported_currency,
                details={
                    "expected_currency": expected_currency.upper(),
                    "reported_currency": reported_currency,
                },
            )

        if reported_amount != expected_amount:
            return ProviderReconciliationResult(
                matched=False,
                status="amount_mismatch",
                provider_transaction_id=provider_transaction_id,
                reported_amount=reported_amount,
                reported_currency=reported_currency,
                details={
                    "expected_amount": str(expected_amount),
                    "reported_amount": str(reported_amount),
                },
            )

        return ProviderReconciliationResult(
            matched=True,
            status="matched",
            provider_transaction_id=provider_transaction_id,
            reported_amount=reported_amount,
            reported_currency=reported_currency,
            details={"status": status},
        )

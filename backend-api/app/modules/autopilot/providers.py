"""Provider-neutral publishing adapter boundary for Autopilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.modules.autopilot.models import (
    AutopilotPublishingDestination,
    AutopilotPublishingPlan,
)


@dataclass(frozen=True)
class PublishProviderResult:
    provider_reference: str
    status: str
    metadata: dict[str, Any]


class PublishingProvider(Protocol):
    def validate_destination(self, destination: AutopilotPublishingDestination) -> None:
        """Raise ValueError when a destination is not publishable."""

    def prepare_payload(
        self, plan: AutopilotPublishingPlan
    ) -> dict[str, Any]:
        """Return the sanitized provider payload."""

    def publish(self, plan: AutopilotPublishingPlan) -> PublishProviderResult:
        """Publish or schedule via provider boundary."""

    def get_status(self, provider_reference: str) -> str:
        """Return provider status."""

    def verify_publication(self, provider_reference: str) -> bool:
        """Verify a provider reference exists and is visible to the adapter."""

    def cancel_scheduled_publication(self, provider_reference: str) -> bool:
        """Cancel a scheduled publication if supported."""


class MockPublishingProvider:
    """Deterministic Sprint 8.5 provider; never contacts external platforms."""

    def validate_destination(self, destination: AutopilotPublishingDestination) -> None:
        if not destination.enabled:
            raise ValueError("Destination is disabled")

    def prepare_payload(self, plan: AutopilotPublishingPlan) -> dict[str, Any]:
        return {
            "platform": plan.destination.platform.value,
            "title": plan.title,
            "language": plan.language,
            "visibility": plan.visibility.value,
            "scheduled": plan.scheduled_at.isoformat() if plan.scheduled_at else None,
        }

    def publish(self, plan: AutopilotPublishingPlan) -> PublishProviderResult:
        self.validate_destination(plan.destination)
        if (plan.platform_metadata_json or {}).get("force_mock_failure"):
            raise ValueError("Mock provider rejected this publication")
        prefix = plan.destination.platform.value.lower()
        ref = f"mock-{prefix}-{str(plan.id)[:8]}"
        return PublishProviderResult(
            provider_reference=ref,
            status="scheduled" if plan.scheduled_at else "published",
            metadata=self.prepare_payload(plan),
        )

    def get_status(self, provider_reference: str) -> str:
        return "published" if provider_reference.startswith("mock-") else "unknown"

    def verify_publication(self, provider_reference: str) -> bool:
        return provider_reference.startswith("mock-")

    def cancel_scheduled_publication(self, provider_reference: str) -> bool:
        return provider_reference.startswith("mock-")


class PublishingProviderRegistry:
    """Allowlisted provider registry."""

    def __init__(self) -> None:
        self._providers: dict[str, PublishingProvider] = {
            "mock": MockPublishingProvider()
        }

    def get(self, provider: str = "mock") -> PublishingProvider:
        if provider != "mock" or provider not in self._providers:
            raise ValueError("Only the mock publishing provider is enabled")
        return self._providers[provider]


default_publishing_registry = PublishingProviderRegistry()

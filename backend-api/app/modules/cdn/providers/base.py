"""Base CDN Provider interface for Global Multi-CDN operation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.modules.cdn.models import CDNHealthStatus, CDNProviderType


class BaseCDNProvider(ABC):
    """Abstract Base Class for CDN Provider Abstractions."""

    @property
    @abstractmethod
    def provider_type(self) -> CDNProviderType:
        """Return the CDN provider identifier."""

    @abstractmethod
    def generate_signed_url(
        self,
        edge_hostname: str,
        asset_path: str,
        secret: str,
        expires_at: datetime,
        client_ip: str | None = None,
        custom_params: dict[str, str] | None = None,
    ) -> str:
        """Generate a signed CDN playback URL."""

    @abstractmethod
    def validate_signature(
        self,
        signed_url: str,
        secret: str,
        client_ip: str | None = None,
    ) -> bool:
        """Validate a signed CDN playback URL using constant-time comparison."""

    @abstractmethod
    def get_cache_policy_headers(
        self,
        asset_path: str,
        playback_type: str = "live",
        custom_policy: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Derive CDN cache policy headers for a given asset."""

    @abstractmethod
    def probe_health(
        self,
        edge_hostname: str,
        health_path: str = "/health",
        timeout_seconds: float = 3.0,
    ) -> tuple[CDNHealthStatus, float, str | None]:
        """Perform a health probe against the CDN edge target."""

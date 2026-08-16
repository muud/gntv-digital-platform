"""Edge URL Signing service for Global Multi-CDN (Module 7 Sprint 7.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.modules.cdn.models import CDNProviderType
from app.modules.cdn.providers.alibaba_dcdn import AlibabaDcdnProvider
from app.modules.cdn.providers.base import BaseCDNProvider


def utc_now() -> datetime:
    return datetime.now(UTC)


class CdnUrlSigner:
    """Orchestrates edge URL signing across registered CDN providers."""

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret or settings.CDN_SIGNING_SECRET.get_secret_value()
        self._providers: dict[CDNProviderType, BaseCDNProvider] = {
            CDNProviderType.ALIBABA_DCDN: AlibabaDcdnProvider(),
        }

    def get_provider(self, provider_type: CDNProviderType) -> BaseCDNProvider:
        provider = self._providers.get(provider_type)
        if not provider:
            # Fallback to Alibaba DCDN provider abstraction
            return self._providers[CDNProviderType.ALIBABA_DCDN]
        return provider

    def sign_url(
        self,
        edge_hostname: str,
        asset_path: str,
        *,
        provider_type: CDNProviderType = CDNProviderType.ALIBABA_DCDN,
        secret: str | None = None,
        ttl_seconds: int | None = None,
        client_ip: str | None = None,
        custom_params: dict[str, str] | None = None,
    ) -> tuple[str, datetime]:
        """Sign a playback URL for an edge CDN endpoint."""
        signing_secret = secret or self.secret
        ttl = ttl_seconds or settings.CDN_DEFAULT_TTL_SECONDS
        expires_at = utc_now() + timedelta(seconds=ttl)

        provider = self.get_provider(provider_type)
        signed_url = provider.generate_signed_url(
            edge_hostname=edge_hostname,
            asset_path=asset_path,
            secret=signing_secret,
            expires_at=expires_at,
            client_ip=client_ip,
            custom_params=custom_params,
        )
        return signed_url, expires_at

    def validate_url(
        self,
        signed_url: str,
        *,
        provider_type: CDNProviderType = CDNProviderType.ALIBABA_DCDN,
        secret: str | None = None,
        client_ip: str | None = None,
    ) -> bool:
        """Validate a signed playback URL."""
        signing_secret = secret or self.secret
        provider = self.get_provider(provider_type)
        return provider.validate_signature(
            signed_url=signed_url,
            secret=signing_secret,
            client_ip=client_ip,
        )

    def get_cache_headers(
        self,
        asset_path: str,
        playback_type: str = "live",
        provider_type: CDNProviderType = CDNProviderType.ALIBABA_DCDN,
        custom_policy: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Retrieve cache control policy headers."""
        provider = self.get_provider(provider_type)
        return provider.get_cache_policy_headers(
            asset_path=asset_path,
            playback_type=playback_type,
            custom_policy=custom_policy,
        )

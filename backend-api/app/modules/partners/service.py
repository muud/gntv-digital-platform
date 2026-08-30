"""Business logic for partner syndication and secure embed authorization."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.core.config import settings
from app.modules.partners.models import (
    Partner,
    PartnerApiCredential,
    PartnerBranding,
    PartnerContentType,
    PartnerCredentialStatus,
    PartnerDomain,
    PartnerEmbedEvent,
    PartnerEmbedEventType,
    PartnerEntitlement,
)
from app.modules.partners.repository import PartnerRepository
from app.modules.partners.schemas import (
    EmbedAuthorizeRequest,
    EmbedAuthorizeResponse,
    EmbedTokenRequest,
    EmbedTokenResponse,
    PartnerAnalyticsOverview,
    PartnerBrandingInput,
    PartnerBrandingResponse,
    PartnerCreate,
    PartnerCreateResponse,
    PartnerCredentialResponse,
    PartnerDomainCreate,
    PartnerEmbedEventCreate,
    PartnerEntitlementCreate,
    PartnerResponse,
)


class PartnerSecurityError(ValueError):
    """Raised when partner security validation fails."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def normalize_domain(value: str) -> str:
    """Return a lower-case hostname from a hostname or URL-like value."""
    candidate = value.strip().lower()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = parsed.hostname or candidate
    return host.strip(".")


def domain_matches(pattern: str, domain: str) -> bool:
    normalized_pattern = normalize_domain(pattern)
    normalized_domain = normalize_domain(domain)
    if normalized_pattern.startswith("*."):
        suffix = normalized_pattern[2:]
        return normalized_domain.endswith(f".{suffix}") and normalized_domain != suffix
    return hmac.compare_digest(normalized_pattern, normalized_domain)


class PartnerSyndicationService:
    """Coordinates partner authorization, token signing, and analytics attribution."""

    token_prefix = "gntv_embed.v1"

    def __init__(self, repo: PartnerRepository, signing_secret: str | None = None) -> None:
        self.repo = repo
        self.signing_secret = signing_secret or settings.EMBED_SIGNING_SECRET.get_secret_value()

    def create_partner(self, payload: PartnerCreate, created_by_user_id: int | None) -> PartnerCreateResponse:
        raw_secret = f"gntv_pk_{secrets.token_urlsafe(24)}"
        key_prefix = raw_secret[:14]
        credential = PartnerApiCredential(
            partner_id=uuid4(),
            key_prefix=key_prefix,
            secret_hash=self.hash_api_secret(raw_secret),
            status=PartnerCredentialStatus.ACTIVE,
        )
        branding = self._make_branding(payload.branding, payload.name)
        partner = Partner(
            name=payload.name,
            slug=payload.slug,
            status=payload.status,
            contact_email=payload.contact_email,
            rate_limit_per_minute=payload.rate_limit_per_minute,
            audit_metadata_json=payload.audit_metadata_json,
            created_by_user_id=created_by_user_id,
        )
        created = self.repo.create_partner(partner, branding, credential)
        return PartnerCreateResponse(
            partner=PartnerResponse.model_validate(created),
            credential=PartnerCredentialResponse(
                id=credential.id,
                key_prefix=credential.key_prefix,
                status=credential.status.value,
                created_at=credential.created_at,
            ),
        )

    def list_partners(self) -> list[Partner]:
        return self.repo.list_partners()

    def get_partner(self, partner_id: UUID) -> Partner:
        partner = self.repo.get_partner(partner_id)
        if partner is None:
            raise ValueError("Partner not found")
        return partner

    def add_domain(self, partner_id: UUID, payload: PartnerDomainCreate) -> PartnerDomain:
        self.get_partner(partner_id)
        domain = PartnerDomain(
            partner_id=partner_id,
            domain_pattern=normalize_domain(payload.domain_pattern) if not payload.domain_pattern.startswith("*.") else payload.domain_pattern,
            origin_pattern=payload.origin_pattern,
        )
        return self.repo.create_domain(domain)

    def list_domains(self, partner_id: UUID) -> list[PartnerDomain]:
        self.get_partner(partner_id)
        return self.repo.list_domains(partner_id)

    def add_entitlement(self, partner_id: UUID, payload: PartnerEntitlementCreate) -> PartnerEntitlement:
        self.get_partner(partner_id)
        if payload.starts_at and payload.expires_at and payload.starts_at >= payload.expires_at:
            raise ValueError("starts_at must be before expires_at")
        entitlement = PartnerEntitlement(
            partner_id=partner_id,
            content_type=payload.content_type,
            content_id=payload.content_id,
            scopes_json=payload.scopes,
            starts_at=payload.starts_at,
            expires_at=payload.expires_at,
        )
        return self.repo.create_entitlement(entitlement)

    def list_entitlements(self, partner_id: UUID) -> list[PartnerEntitlement]:
        self.get_partner(partner_id)
        return self.repo.list_entitlements(partner_id)

    def issue_embed_token(self, partner_id: UUID, payload: EmbedTokenRequest) -> EmbedTokenResponse:
        partner = self._load_active_partner(partner_id)
        self._assert_domain_authorized(partner_id, payload.domain, payload.origin)
        entitlement = self.repo.get_active_entitlement(partner_id, payload.content_type, payload.content_id)
        if entitlement is None:
            raise PartnerSecurityError("Partner is not entitled to this content")
        requested_scopes = sorted({scope.strip() for scope in payload.scopes if scope.strip()})
        allowed_scopes = set(entitlement.scopes_json or [])
        if not set(requested_scopes).issubset(allowed_scopes):
            raise PartnerSecurityError("Requested scopes exceed partner entitlement")

        ttl = min(payload.ttl_seconds or settings.EMBED_TOKEN_TTL_SECONDS, settings.EMBED_TOKEN_MAX_TTL_SECONDS)
        issued_at = utc_now()
        expires_at = issued_at + timedelta(seconds=ttl)
        viewer_hash = self._hash_optional(payload.viewer_session_id)
        token_payload: dict[str, Any] = {
            "jti": str(uuid4()),
            "pid": str(partner_id),
            "cty": payload.content_type.value,
            "cid": payload.content_id,
            "dom": normalize_domain(payload.domain),
            "origin": payload.origin,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "sid": payload.playback_session_id,
            "vsh": viewer_hash,
            "scp": requested_scopes,
        }
        token = self._sign_payload(token_payload)
        return EmbedTokenResponse(
            token=token,
            expires_at=expires_at,
            partner_id=partner.id,
            content_type=payload.content_type,
            content_id=payload.content_id,
            scopes=requested_scopes,
            branding=self._branding_response(partner.branding),
        )

    def authorize_embed(self, payload: EmbedAuthorizeRequest) -> EmbedAuthorizeResponse:
        claims = self.verify_token(payload.token)
        partner_id = UUID(str(claims["pid"]))
        partner = self._load_active_partner(partner_id)
        token_domain = str(claims["dom"])
        request_domain = normalize_domain(payload.domain)
        if not hmac.compare_digest(token_domain, request_domain):
            raise PartnerSecurityError("Token domain does not match request domain")
        self._assert_domain_authorized(partner_id, request_domain, payload.origin or claims.get("origin"))
        content_type = PartnerContentType(str(claims["cty"]))
        content_id = str(claims["cid"])
        if self.repo.get_active_entitlement(partner_id, content_type, content_id) is None:
            raise PartnerSecurityError("Partner is not entitled to this content")
        self.repo.record_event(
            PartnerEmbedEvent(
                partner_id=partner_id,
                content_type=content_type,
                content_id=content_id,
                event_type=PartnerEmbedEventType.AUTHORIZE,
                playback_session_id=payload.playback_session_id or claims.get("sid"),
                viewer_session_id_hash=claims.get("vsh"),
                domain=request_domain,
                origin=payload.origin,
                metadata_json={"scopes": claims.get("scp", [])},
            )
        )
        return EmbedAuthorizeResponse(
            authorized=True,
            partner_id=partner_id,
            content_type=content_type,
            content_id=content_id,
            expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC),
            scopes=list(claims.get("scp", [])),
            playback_url=self._playback_url(content_type, content_id, payload.token),
            branding=self._branding_response(partner.branding),
        )

    def record_embed_event(self, payload: PartnerEmbedEventCreate) -> PartnerEmbedEvent:
        claims = self.verify_token(payload.token)
        partner_id = UUID(str(claims["pid"]))
        self._assert_domain_authorized(partner_id, payload.domain, payload.origin)
        event = PartnerEmbedEvent(
            partner_id=partner_id,
            content_type=PartnerContentType(str(claims["cty"])),
            content_id=str(claims["cid"]),
            event_type=payload.event_type,
            playback_session_id=payload.playback_session_id or claims.get("sid"),
            viewer_session_id_hash=claims.get("vsh"),
            domain=normalize_domain(payload.domain),
            origin=payload.origin,
            error_code=payload.error_code,
            metadata_json=payload.metadata_json,
        )
        return self.repo.record_event(event)

    def analytics_overview(self) -> PartnerAnalyticsOverview:
        return PartnerAnalyticsOverview(**self.repo.analytics_overview())

    def verify_token(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 4 or ".".join(parts[:2]) != self.token_prefix:
            raise PartnerSecurityError("Invalid embed token format")
        payload_part = parts[2]
        signature = parts[3]
        expected = self._signature(payload_part)
        if not hmac.compare_digest(signature, expected):
            raise PartnerSecurityError("Invalid embed token signature")
        try:
            raw_claims = json.loads(_b64decode(payload_part))
            if not isinstance(raw_claims, dict):
                raise PartnerSecurityError("Invalid embed token payload")
            claims: dict[str, Any] = dict(raw_claims)
        except (json.JSONDecodeError, ValueError) as exc:
            raise PartnerSecurityError("Invalid embed token payload") from exc
        expires_at = int(claims.get("exp", 0))
        if expires_at <= int(utc_now().timestamp()):
            raise PartnerSecurityError("Embed token has expired")
        return claims

    def verify_api_secret(self, raw_secret: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self.hash_api_secret(raw_secret), stored_hash)

    def hash_api_secret(self, raw_secret: str) -> str:
        return hmac.new(self.signing_secret.encode("utf-8"), raw_secret.encode("utf-8"), hashlib.sha256).hexdigest()

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        payload_part = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        return f"{self.token_prefix}.{payload_part}.{self._signature(payload_part)}"

    def _signature(self, payload_part: str) -> str:
        digest = hmac.new(self.signing_secret.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
        return _b64encode(digest)

    def _load_active_partner(self, partner_id: UUID) -> Partner:
        partner = self.repo.get_active_partner(partner_id)
        if partner is None:
            raise PartnerSecurityError("Partner is not active")
        return partner

    def _assert_domain_authorized(self, partner_id: UUID, domain: str, origin: str | None) -> None:
        domains = self.repo.list_active_domains(partner_id)
        normalized_domain = normalize_domain(domain)
        if not any(domain_matches(item.domain_pattern, normalized_domain) for item in domains):
            raise PartnerSecurityError("Domain is not authorized for this partner")
        if origin:
            normalized_origin = normalize_domain(origin)
            origin_patterns = [item.origin_pattern for item in domains if item.origin_pattern]
            if origin_patterns and not any(domain_matches(pattern, normalized_origin) for pattern in origin_patterns if pattern):
                raise PartnerSecurityError("Origin is not authorized for this partner")

    def _make_branding(self, payload: PartnerBrandingInput | None, fallback_name: str) -> PartnerBranding:
        branding = payload or PartnerBrandingInput(display_name=fallback_name, accent_color="#ff8a00")
        return PartnerBranding(
            partner_id=uuid4(),
            display_name=branding.display_name,
            logo_url=str(branding.logo_url) if branding.logo_url else None,
            accent_color=branding.accent_color,
            theme_json=branding.theme_json,
            show_gntv_attribution=branding.show_gntv_attribution,
        )

    def _hash_optional(self, value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _branding_response(self, branding: PartnerBranding | None) -> PartnerBrandingResponse | None:
        if branding is None:
            return None
        return PartnerBrandingResponse.model_validate(branding)

    def _playback_url(self, content_type: PartnerContentType, content_id: str, token: str) -> str:
        safe_content_id = content_id.replace("/", "")
        if content_type == PartnerContentType.LIVE_CHANNEL:
            return f"/api/v1/streaming/live/{safe_content_id}/playlist.m3u8?embed_token={token}"
        return f"/api/v1/content/{safe_content_id}/playback?embed_token={token}"

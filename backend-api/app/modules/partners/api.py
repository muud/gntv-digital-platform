"""FastAPI endpoints for partner syndication and embed authorization."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.partners.models import PartnerCredentialStatus
from app.modules.partners.repository import PartnerRepository
from app.modules.partners.schemas import (
    EmbedAuthorizeRequest,
    EmbedAuthorizeResponse,
    EmbedTokenRequest,
    EmbedTokenResponse,
    PartnerAnalyticsOverview,
    PartnerCreate,
    PartnerCreateResponse,
    PartnerDomainCreate,
    PartnerDomainResponse,
    PartnerEmbedEventCreate,
    PartnerEmbedEventResponse,
    PartnerEntitlementCreate,
    PartnerEntitlementResponse,
    PartnerResponse,
)
from app.modules.partners.service import PartnerSecurityError, PartnerSyndicationService
from app.utils.jwt import decode_token

partners_router = APIRouter(prefix="/api/v1/partners", tags=["Partner Syndication"])
embed_router = APIRouter(prefix="/api/v1/embed", tags=["Embed SDK Authorization"])


def get_service(db: Session = Depends(get_db)) -> PartnerSyndicationService:
    return PartnerSyndicationService(PartnerRepository(db))


def require_partner_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an admin or operator role for partner administration."""
    user_roles = set(current_user.role_names) if hasattr(current_user, "role_names") else {r.name for r in current_user.roles}
    if {"admin", "operator", "super_admin"} & user_roles:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or operator role required",
    )


def authenticate_partner_or_admin(
    partner_id: UUID,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_partner_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
    service: PartnerSyndicationService = Depends(get_service),
) -> None:
    """Authorize either a platform admin/operator or a partner via API key."""
    # 1. Try JWT auth from standard Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        if not token.startswith("gntv_pk_"):
            try:
                payload = decode_token(token)
                subject = payload.get("sub")
                if subject is None:
                    raise ValueError("missing subject")
                user = db.query(User).filter(User.id == int(subject)).one()
                user_roles = set(user.role_names) if hasattr(user, "role_names") else {r.name for r in user.roles}
                if {"admin", "operator", "super_admin"} & user_roles:
                    return
            except Exception:
                pass

    # 2. Try Partner API Key from header or Authorization Bearer
    partner_key = x_partner_key
    if not partner_key and authorization and authorization.startswith("Bearer gntv_pk_"):
        partner_key = authorization.split(" ", 1)[1]

    if partner_key:
        prefix = partner_key[:14]
        partner = service.repo.get_partner(partner_id)
        if partner:
            for cred in partner.credentials:
                if cred.status == PartnerCredentialStatus.ACTIVE and cred.key_prefix == prefix:
                    if service.verify_api_secret(partner_key, cred.secret_hash):
                        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid partner API key or admin authorization required",
        headers={"WWW-Authenticate": "Bearer"},
    )


@partners_router.post(
    "",
    response_model=PartnerCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new partner organization",
)
def create_partner(
    payload: PartnerCreate,
    current_user: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> PartnerCreateResponse:
    try:
        return service.create_partner(payload, created_by_user_id=current_user.id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@partners_router.get(
    "",
    response_model=list[PartnerResponse],
    summary="List all partner organizations",
)
def list_partners(
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> list[PartnerResponse]:
    return [PartnerResponse.model_validate(p) for p in service.list_partners()]


@partners_router.get(
    "/analytics/overview",
    response_model=PartnerAnalyticsOverview,
    summary="Get partner syndication analytics overview",
)
def get_partner_analytics_overview(
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> PartnerAnalyticsOverview:
    return service.analytics_overview()


@partners_router.get(
    "/{partner_id}",
    response_model=PartnerResponse,
    summary="Get partner details by ID",
)
def get_partner(
    partner_id: UUID,
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> PartnerResponse:
    try:
        return PartnerResponse.model_validate(service.get_partner(partner_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@partners_router.post(
    "/{partner_id}/domains",
    response_model=PartnerDomainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an allowed domain/origin pattern for a partner",
)
def add_partner_domain(
    partner_id: UUID,
    payload: PartnerDomainCreate,
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> PartnerDomainResponse:
    try:
        domain = service.add_domain(partner_id, payload)
        return PartnerDomainResponse(
            id=domain.id,
            partner_id=domain.partner_id,
            domain_pattern=domain.domain_pattern,
            origin_pattern=domain.origin_pattern,
            status=domain.status.value,
            created_at=domain.created_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@partners_router.get(
    "/{partner_id}/domains",
    response_model=list[PartnerDomainResponse],
    summary="List allowed domains for a partner",
)
def list_partner_domains(
    partner_id: UUID,
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> list[PartnerDomainResponse]:
    try:
        domains = service.list_domains(partner_id)
        return [
            PartnerDomainResponse(
                id=d.id,
                partner_id=d.partner_id,
                domain_pattern=d.domain_pattern,
                origin_pattern=d.origin_pattern,
                status=d.status.value,
                created_at=d.created_at,
            )
            for d in domains
        ]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@partners_router.post(
    "/{partner_id}/entitlements",
    response_model=PartnerEntitlementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign content entitlement to a partner",
)
def add_partner_entitlement(
    partner_id: UUID,
    payload: PartnerEntitlementCreate,
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> PartnerEntitlementResponse:
    try:
        entitlement = service.add_entitlement(partner_id, payload)
        return PartnerEntitlementResponse.model_validate(entitlement)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@partners_router.get(
    "/{partner_id}/entitlements",
    response_model=list[PartnerEntitlementResponse],
    summary="List content entitlements for a partner",
)
def list_partner_entitlements(
    partner_id: UUID,
    _: User = Depends(require_partner_admin),
    service: PartnerSyndicationService = Depends(get_service),
) -> list[PartnerEntitlementResponse]:
    try:
        entitlements = service.list_entitlements(partner_id)
        return [PartnerEntitlementResponse.model_validate(e) for e in entitlements]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@partners_router.post(
    "/{partner_id}/embed-token",
    response_model=EmbedTokenResponse,
    summary="Issue a signed short-lived embed authorization token",
)
def issue_embed_token(
    partner_id: UUID,
    payload: EmbedTokenRequest,
    service: PartnerSyndicationService = Depends(get_service),
    _: None = Depends(authenticate_partner_or_admin),
) -> EmbedTokenResponse:
    try:
        return service.issue_embed_token(partner_id, payload)
    except PartnerSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Embed Authorization Endpoints ---


@embed_router.get(
    "/authorize",
    response_model=EmbedAuthorizeResponse,
    summary="Authorize embed playback via GET query parameters",
)
def authorize_embed_get(
    token: str = Query(..., min_length=32, description="Signed embed token"),
    domain: str = Query(..., min_length=3, description="Client hostname"),
    origin: str | None = Query(None, description="Client Origin header value"),
    playback_session_id: str | None = Query(None, description="Client session ID"),
    service: PartnerSyndicationService = Depends(get_service),
) -> EmbedAuthorizeResponse:
    payload = EmbedAuthorizeRequest(
        token=token,
        domain=domain,
        origin=origin,
        playback_session_id=playback_session_id,
    )
    try:
        return service.authorize_embed(payload)
    except PartnerSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@embed_router.post(
    "/authorize",
    response_model=EmbedAuthorizeResponse,
    summary="Authorize embed playback via POST body",
)
def authorize_embed_post(
    payload: EmbedAuthorizeRequest,
    service: PartnerSyndicationService = Depends(get_service),
) -> EmbedAuthorizeResponse:
    try:
        return service.authorize_embed(payload)
    except PartnerSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@embed_router.post(
    "/events",
    response_model=PartnerEmbedEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record partner embed telemetry / playback event",
)
def record_embed_event(
    payload: PartnerEmbedEventCreate,
    service: PartnerSyndicationService = Depends(get_service),
) -> PartnerEmbedEventResponse:
    try:
        event = service.record_embed_event(payload)
        return PartnerEmbedEventResponse.model_validate(event)
    except PartnerSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@embed_router.get(
    "/sdk.js",
    response_class=PlainTextResponse,
    summary="Serve the lightweight browser embed SDK",
)
def get_embed_sdk() -> Response:
    sdk = """
(function (global) {
  "use strict";
  function sessionId() {
    return "gntv_sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
  async function sendEvent(apiBaseUrl, token, eventType, domain, origin, playbackSessionId, errorCode) {
    try {
      await fetch(apiBaseUrl + "/api/v1/embed/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, event_type: eventType, domain, origin, playback_session_id: playbackSessionId, error_code: errorCode || null })
      });
    } catch (_) {}
  }
  global.GNTV = global.GNTV || {};
  global.GNTV.embed = async function embed(options) {
    if (!options || !options.target || !options.token) throw new Error("GNTV.embed requires target and token");
    var target = typeof options.target === "string" ? document.querySelector(options.target) : options.target;
    if (!target) throw new Error("GNTV embed target not found");
    var apiBaseUrl = (options.apiBaseUrl || global.GNTV_EMBED_API_BASE || "").replace(/\\/+$/, "");
    var playbackSessionId = options.playbackSessionId || sessionId();
    var domain = global.location.hostname || "localhost";
    var origin = global.location.origin || "";
    target.innerHTML = '<div style="min-height:300px;display:flex;align-items:center;justify-content:center;background:#05070a;color:#f3f4f6;border-radius:8px;font-family:system-ui">Verifying secure broadcast ticket...</div>';
    var response = await fetch(apiBaseUrl + "/api/v1/embed/authorize", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ token: options.token, domain, origin, playback_session_id: playbackSessionId })
    });
    if (!response.ok) {
      target.innerHTML = '<div style="min-height:300px;display:flex;align-items:center;justify-content:center;background:#0d1117;color:#fca5a5;border-radius:8px;font-family:system-ui">Playback restricted by GNTV Digital security.</div>';
      throw new Error("GNTV embed authorization failed");
    }
    var auth = await response.json();
    var branding = auth.branding || {};
    target.innerHTML = '<div style="position:relative;width:100%;min-height:300px;aspect-ratio:16/9;background:#000;border-radius:8px;overflow:hidden"><video controls playsinline style="width:100%;height:100%;display:block;background:#000" src="' + auth.playback_url + '"></video><div style="position:absolute;top:12px;left:12px;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,.55);color:#fff;font:700 12px system-ui">' + (branding.display_name || "GNTV Digital") + '</div></div>';
    var video = target.querySelector("video");
    if (options.autoplay) video.autoplay = true;
    if (options.muted || options.autoplay) video.muted = true;
    video.addEventListener("play", function () { sendEvent(apiBaseUrl, options.token, "playback_start", domain, origin, playbackSessionId); }, { once: true });
    video.addEventListener("ended", function () { sendEvent(apiBaseUrl, options.token, "playback_complete", domain, origin, playbackSessionId); }, { once: true });
    video.addEventListener("error", function () { sendEvent(apiBaseUrl, options.token, "playback_error", domain, origin, playbackSessionId, "media_error"); }, { once: true });
    return { authorization: auth, video: video };
  };
})(typeof window !== "undefined" ? window : globalThis);
""".strip()
    return PlainTextResponse(sdk, media_type="application/javascript")

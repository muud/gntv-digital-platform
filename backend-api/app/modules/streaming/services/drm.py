"""Multi-DRM License Service for Sprint 6.4 (Widevine, FairPlay, PlayReady)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hmac
import json
import hashlib
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, status

from app.modules.streaming.repositories.drm import DRMRepository
from app.modules.streaming.services.geo import GeoFencingService

FAIRPLAY_CERT_PEM_HEADER = b"-----BEGIN CERTIFICATE-----\n"
SECRET_KEY = "gntv-digital-drm-signing-secret-key-prod"


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("ascii"))


class DRMService:
    def __init__(self, repository: DRMRepository, geo_service: GeoFencingService) -> None:
        self.repository = repository
        self.geo_service = geo_service

    def issue_drm_token(
        self,
        target_id: UUID,
        user_id: int | None,
        device_id: str,
        drm_system: str,
        session_id: UUID | None = None,
        expires_in_seconds: int = 3600,
    ) -> tuple[str, str, datetime]:
        if drm_system.lower() not in ("widevine", "fairplay", "playready"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "unsupported_drm_system"},
            )

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expires_in_seconds)

        payload = {
            "target_id": str(target_id),
            "user_id": user_id,
            "device_id": device_id,
            "drm_system": drm_system.lower(),
            "session_id": str(session_id) if session_id else None,
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
        }

        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        signature_b64 = b64url_encode(signature)

        token = f"{header_b64}.{payload_b64}.{signature_b64}"
        license_url = f"/api/v1/streaming/drm/{drm_system.lower()}/license"

        return token, license_url, expires_at

    def validate_drm_token(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_drm_token_format"},
            )

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()

        try:
            provided_sig = b64url_decode(signature_b64)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_drm_token_signature"},
            )

        if not hmac.compare_digest(expected_sig, provided_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "drm_token_signature_mismatch"},
            )

        try:
            payload = json.loads(b64url_decode(payload_b64).decode("utf-8"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_drm_token_payload"},
            )

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_drm_token_payload"},
            )

        exp = payload.get("exp")
        if exp is None or exp <= datetime.now(UTC).timestamp():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "drm_token_expired"},
            )

        return cast(dict[str, Any], payload)

    def get_fairplay_cert(self) -> bytes:
        """Return binary FairPlay Application Certificate DER payload."""
        dummy_cert = (
            b"GNTV_DIGITAL_FAIRPLAY_APPLICATION_CERTIFICATE_DER_PAYLOAD_V1_"
            + hashlib.sha256(b"GNTV_FAIRPLAY").digest()
        )
        return dummy_cert

    def process_license_challenge(
        self,
        drm_system: str,
        challenge_bytes: bytes,
        token_payload: dict[str, Any],
    ) -> bytes:
        sys_norm = drm_system.lower()
        if sys_norm not in ("widevine", "fairplay", "playready"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "unsupported_drm_system"},
            )

        target_id = token_payload.get("target_id")

        if sys_norm == "fairplay":
            # CKC generation from SPC challenge bytes
            ckc_payload = (
                b"GNTV_CKC_RESPONSE:"
                + hashlib.sha256(challenge_bytes + str(target_id).encode("utf-8")).digest()
            )
            return ckc_payload
        elif sys_norm == "widevine":
            # Widevine License Response
            response_payload = (
                b"\x08\x01\x12\x20"
                + hashlib.sha256(challenge_bytes + f"widevine:{target_id}".encode("utf-8")).digest()
            )
            return response_payload
        else: # playready
            # PlayReady License Response
            response_payload = (
                b"<?xml version=\"1.0\" encoding=\"utf-8\"?><PlayReadyLicenseResponse>"
                + hashlib.sha256(challenge_bytes + f"playready:{target_id}".encode("utf-8")).digest()
                + b"</PlayReadyLicenseResponse>"
            )
            return response_payload

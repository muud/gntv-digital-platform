"""Pydantic schemas for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.cdn.models import CDNHealthStatus, CDNOriginType, CDNProviderType


class CDNOriginBase(BaseModel):
    name: str = Field(..., max_length=100, description="Unique human-readable origin identifier")
    origin_hostname: str = Field(..., max_length=255, description="FQDN of origin server")
    origin_type: CDNOriginType = Field(default=CDNOriginType.PRIMARY, description="Primary, secondary, or backup origin")
    is_active: bool = Field(default=True, description="Whether origin is active")
    health_check_path: str = Field(default="/health", max_length=255, description="Path for health checks")


class CDNOriginCreate(CDNOriginBase):
    pass


class CDNOriginResponse(CDNOriginBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CDNEndpointBase(BaseModel):
    origin_id: UUID
    provider_type: CDNProviderType = Field(default=CDNProviderType.ALIBABA_DCDN, description="CDN Provider abstraction type")
    edge_hostname: str = Field(..., max_length=255, description="Edge CDN domain name")
    signing_key_ref: str = Field(default="PLAYBACK_SIGNING_SECRET", max_length=100, description="Reference name for signing secret")
    priority: int = Field(default=100, ge=1, le=1000, description="Routing priority order (lower number = higher priority)")
    is_enabled: bool = Field(default=True, description="Enabled status")
    cache_policy_json: dict[str, Any] | None = Field(default=None, description="Custom cache headers policy settings")


class CDNEndpointCreate(CDNEndpointBase):
    pass


class CDNEndpointUpdate(BaseModel):
    priority: int | None = Field(default=None, ge=1, le=1000)
    is_enabled: bool | None = None
    health_status: CDNHealthStatus | None = None
    cache_policy_json: dict[str, Any] | None = None


class CDNEndpointResponse(BaseModel):
    id: UUID
    origin_id: UUID
    provider_type: CDNProviderType
    edge_hostname: str
    priority: int
    is_enabled: bool
    cache_policy_json: dict[str, Any] | None
    health_status: CDNHealthStatus
    consecutive_failures: int
    last_health_check_at: datetime | None
    last_failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CDNHealthCheckCreate(BaseModel):
    status: CDNHealthStatus
    response_latency_ms: float = Field(default=0.0, ge=0.0)
    failure_reason: str | None = None


class CDNHealthCheckResponse(CDNHealthCheckCreate):
    id: UUID
    endpoint_id: UUID
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CDNHealthUpdate(BaseModel):
    status: CDNHealthStatus
    response_latency_ms: float = Field(default=0.0, ge=0.0)
    failure_reason: str | None = None


class CDNHealthSummary(BaseModel):
    endpoint_id: UUID
    edge_hostname: str
    provider_type: CDNProviderType
    health_status: CDNHealthStatus
    consecutive_failures: int
    last_health_check_at: datetime | None
    response_latency_ms: float | None
    last_failure_reason: str | None


class CDNSignedUrlRequest(BaseModel):
    asset_path: str = Field(..., description="Canonical path to HLS/VOD asset or manifest")
    ttl_seconds: int = Field(default=1800, ge=30, le=86400, description="Expiration time in seconds")
    client_ip: str | None = Field(default=None, description="Client IP for access restriction if required")
    custom_params: dict[str, str] | None = Field(default=None, description="Additional query parameters to preserve (e.g. SSAI session_id)")


class CDNSignedUrlResponse(BaseModel):
    signed_url: str
    expires_at: datetime
    edge_hostname: str
    provider_type: CDNProviderType
    signature_algorithm: str = "HMAC-SHA256"


class CDNRouteRequest(BaseModel):
    asset_id: str
    asset_path: str
    playback_type: str = Field(default="live", description="live, vod, fast, or asset")
    client_ip: str | None = None
    query_params: dict[str, str] | None = None
    ttl_seconds: int = Field(default=1800, ge=30, le=86400)


class CDNRouteResponse(BaseModel):
    routed_url: str
    endpoint_id: UUID
    edge_hostname: str
    provider_type: CDNProviderType
    origin_hostname: str
    routing_reason: str
    is_failover: bool
    expires_at: datetime
    cache_control: str


class CDNRoutingEventResponse(BaseModel):
    id: UUID
    asset_id: str
    endpoint_id: UUID | None
    routing_reason: str
    client_ip: str | None
    decision_metadata_json: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

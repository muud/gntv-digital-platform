"""Pydantic v2 contracts for Module 5 distribution and geo-fencing."""

from datetime import datetime
from typing import Any, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.modules.distribution.models import (
    CDNSyncStatus,
    DistributionTargetStatus,
    DistributionTargetType,
    GeoPolicyMode,
    GeoPolicyStatus,
)
from app.modules.streaming.schemas import CursorPageMeta

ISO_ALPHA2 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split()
)


class DistributionContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DistributionTargetCreateRequest(DistributionContractModel):
    live_channel_id: UUID
    name: str = Field(min_length=1, max_length=160)
    target_type: DistributionTargetType
    endpoint: str = Field(min_length=1, max_length=2048)
    credential: SecretStr
    public_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "rtmp", "rtmps"} or not parsed.netloc:
            raise ValueError("endpoint must use https, rtmp, or rtmps with a host")
        if parsed.username or parsed.password:
            raise ValueError("endpoint must not contain embedded credentials")
        return value

    @field_validator("credential")
    @classmethod
    def valid_credential(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("credential must contain at least 16 characters")
        return value


class DistributionTargetResponse(DistributionContractModel):
    id: UUID
    live_channel_id: UUID
    name: str
    target_type: DistributionTargetType
    status: DistributionTargetStatus
    masked_endpoint: str
    credentials_configured: bool
    public_config: dict[str, Any]
    last_health_at: datetime | None
    last_success_at: datetime | None
    failure_code: str | None
    failure_detail: str | None
    created_at: datetime
    updated_at: datetime
    lock_version: int


class DistributionTargetPageResponse(DistributionContractModel):
    items: list[DistributionTargetResponse]
    page: CursorPageMeta


class GeoFencingPolicyUpsertRequest(DistributionContractModel):
    content_id: UUID | None = None
    catalog_item_id: UUID | None = None
    live_channel_id: UUID | None = None
    policy_mode: GeoPolicyMode
    allowed_countries: list[str] = Field(default_factory=list, max_length=249)
    blocked_countries: list[str] = Field(default_factory=list, max_length=249)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    expected_version: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("allowed_countries", "blocked_countries")
    @classmethod
    def valid_countries(cls, values: list[str]) -> list[str]:
        normalized = [value.upper() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("country lists must not contain duplicates")
        invalid = sorted(set(normalized) - ISO_ALPHA2)
        if invalid:
            raise ValueError(f"invalid ISO 3166-1 alpha-2 country codes: {', '.join(invalid)}")
        return normalized

    @model_validator(mode="after")
    def valid_policy(self) -> Self:
        targets = (self.content_id, self.catalog_item_id, self.live_channel_id)
        if sum(value is not None for value in targets) != 1:
            raise ValueError("exactly one geo-fencing target is required")
        overlap = set(self.allowed_countries) & set(self.blocked_countries)
        if overlap:
            raise ValueError("allowed and blocked countries must be disjoint")
        if self.policy_mode == GeoPolicyMode.ALLOWLIST and not self.allowed_countries:
            raise ValueError("allowlist mode requires allowed_countries")
        if self.policy_mode == GeoPolicyMode.BLOCKLIST and not self.blocked_countries:
            raise ValueError("blocklist mode requires blocked_countries")
        if self.policy_mode == GeoPolicyMode.GLOBAL and (self.allowed_countries or self.blocked_countries):
            raise ValueError("global mode cannot include country lists")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class GeoFencingPolicyResponse(DistributionContractModel):
    id: UUID
    content_id: UUID | None
    catalog_item_id: UUID | None
    live_channel_id: UUID | None
    policy_mode: GeoPolicyMode
    allowed_countries: list[str]
    blocked_countries: list[str]
    status: GeoPolicyStatus
    starts_at: datetime | None
    ends_at: datetime | None
    policy_version: int
    cdn_sync_status: CDNSyncStatus
    cdn_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    lock_version: int


__all__ = [
    "DistributionTargetCreateRequest",
    "DistributionTargetPageResponse",
    "DistributionTargetResponse",
    "GeoFencingPolicyResponse",
    "GeoFencingPolicyUpsertRequest",
    "ISO_ALPHA2",
]

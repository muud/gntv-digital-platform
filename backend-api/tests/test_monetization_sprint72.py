"""Module 7 Sprint 7.2 SSAI, FAST packaging, and ad tracking tests."""

from __future__ import annotations

from collections.abc import Generator
import importlib.util
from pathlib import Path
from typing import cast
from uuid import UUID

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.auth_extra import EmailVerification, FailedLoginAttempt, PasswordReset, RefreshToken
from app.models.user import Device, Permission, Profile, Role, User, UserSession, role_permissions, user_roles
from app.modules.monetization.models import (
    AdBreak,
    AdCampaign,
    AdCreative,
    AdImpression,
    AdImpressionEventType,
    AdTrackingEvent,
)
from app.modules.monetization.repository import MonetizationRepository
from app.modules.monetization.schemas import (
    AdBreakCreateRequest,
    AdCampaignCreateRequest,
    AdCreativeCreateRequest,
    Scte35Cue,
    TrackingBeaconRequest,
)
from app.modules.monetization.scte35 import cue_to_opportunity, parse_scte35_marker
from app.modules.monetization.services import MonetizationService, build_ssai_manifest, sign_beacon_payload
from app.modules.monetization.vast import parse_vast, parse_vmap
from app.utils.jwt import create_access_token
from app.utils.security import hash_password


MONETIZATION_TABLES: list[Table] = [
    cast(Table, User.__table__),
    cast(Table, Profile.__table__),
    cast(Table, Role.__table__),
    cast(Table, Permission.__table__),
    user_roles,
    role_permissions,
    cast(Table, Device.__table__),
    cast(Table, UserSession.__table__),
    cast(Table, EmailVerification.__table__),
    cast(Table, PasswordReset.__table__),
    cast(Table, RefreshToken.__table__),
    cast(Table, FailedLoginAttempt.__table__),
    cast(Table, AuditLog.__table__),
    cast(Table, AdCampaign.__table__),
    cast(Table, AdCreative.__table__),
    cast(Table, AdBreak.__table__),
    cast(Table, AdImpression.__table__),
    cast(Table, AdTrackingEvent.__table__),
]


VAST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<VAST version="3.0">
  <Ad id="ad-1">
    <InLine>
      <Impression><![CDATA[https://track.example/impression]]></Impression>
      <Error><![CDATA[https://track.example/error]]></Error>
      <Creatives>
        <Creative>
          <Linear>
            <Duration>00:00:30.000</Duration>
            <TrackingEvents>
              <Tracking event="start"><![CDATA[https://track.example/start]]></Tracking>
              <Tracking event="firstQuartile"><![CDATA[https://track.example/q1]]></Tracking>
              <Tracking event="midpoint"><![CDATA[https://track.example/mid]]></Tracking>
              <Tracking event="thirdQuartile"><![CDATA[https://track.example/q3]]></Tracking>
              <Tracking event="complete"><![CDATA[https://track.example/complete]]></Tracking>
            </TrackingEvents>
            <MediaFiles>
              <MediaFile type="video/mp2t" width="1280" height="720"><![CDATA[https://cdn.example/ad.ts]]></MediaFile>
            </MediaFiles>
          </Linear>
        </Creative>
      </Creatives>
    </InLine>
  </Ad>
</VAST>
"""

VMAP_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<vmap:VMAP xmlns:vmap="http://www.iab.net/videosuite/vmap" version="1.0">
  <vmap:AdBreak timeOffset="00:05:00.000" breakType="linear" breakId="mid-1">
    <vmap:AdSource>
      <vmap:VASTData>{VAST_XML.replace('<?xml version="1.0" encoding="UTF-8"?>', '')}</vmap:VASTData>
    </vmap:AdSource>
  </vmap:AdBreak>
</vmap:VMAP>
"""


@pytest.fixture()
def monetization_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=MONETIZATION_TABLES)
    local_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = local_session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=reversed(MONETIZATION_TABLES))
        engine.dispose()


@pytest.fixture()
def monetization_client(monetization_db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield monetization_db
            monetization_db.commit()
        except Exception:
            monetization_db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create_user(db: Session, email: str, role_name: str = "viewer") -> User:
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(email=email, hashed_password=hash_password("StrongPass123"), is_active=True, is_verified=True)
    user.roles.append(role)
    user.name = email.split("@", maxsplit=1)[0]
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id), additional_claims={'email': user.email})}"}


def seed_campaign(db: Session, user: User) -> tuple[AdCampaign, AdCreative, AdBreak]:
    service = MonetizationService(MonetizationRepository(db))
    campaign = service.create_campaign(AdCampaignCreateRequest(name="GNTV Launch Partner"), user)
    creative = service.create_creative(
        AdCreativeCreateRequest(
            campaign_id=campaign.id,
            name="Launch Spot",
            media_url="https://cdn.gntv.example/ads/launch.ts",
            duration_seconds=30.0,
        ),
        user,
    )
    ad_break = service.create_break(
        AdBreakCreateRequest(
            campaign_id=campaign.id,
            target_id="gntv-fast",
            time_offset_seconds=12,
            duration_seconds=30,
            scte35_event_id="break-1",
        ),
        user,
    )
    db.commit()
    return campaign, creative, ad_break


def test_vast_parsing() -> None:
    creatives = parse_vast(VAST_XML)
    assert creatives[0].duration_seconds == 30
    assert creatives[0].media_files[0].url == "https://cdn.example/ad.ts"
    assert creatives[0].impressions == ["https://track.example/impression"]
    assert creatives[0].tracking["firstQuartile"] == ["https://track.example/q1"]
    assert creatives[0].errors == ["https://track.example/error"]


def test_vmap_parsing() -> None:
    breaks = parse_vmap(VMAP_XML)
    assert breaks[0].time_offset == "00:05:00.000"
    assert breaks[0].break_id == "mid-1"
    assert breaks[0].vast_ad_data is not None


def test_malformed_vast_vmap_rejection() -> None:
    with pytest.raises(HTTPException) as unsafe:
        parse_vast("<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><VAST />")
    with pytest.raises(HTTPException) as malformed:
        parse_vmap("<VMAP><AdBreak>")
    assert unsafe.value.status_code == 400
    assert malformed.value.status_code == 400


def test_scte35_cue_handling() -> None:
    cue = Scte35Cue(cue_type="cue-out", event_id="evt-7", duration_seconds=30)
    opportunity = cue_to_opportunity(cue)
    marker = parse_scte35_marker("#EXT-X-CUE-OUT:DURATION=30,ID=evt-9")
    assert opportunity.starts_break is True
    assert opportunity.ends_break is False
    assert marker.event_id == "evt-9"
    assert marker.duration_seconds == 30


def test_hls_manifest_stitching_and_fast_packaging(monetization_db: Session) -> None:
    user = create_user(monetization_db, "producer@example.com", "producer")
    seed_campaign(monetization_db, user)
    manifest = MonetizationService(MonetizationRepository(monetization_db)).ssai_manifest("gntv-fast")
    assert manifest.startswith("#EXTM3U\n#EXT-X-VERSION:3")
    assert "#EXT-X-TARGETDURATION:30" in manifest
    assert "#EXT-X-MEDIA-SEQUENCE:0" in manifest
    assert manifest.count("#EXT-X-DISCONTINUITY") == 2
    assert "#EXT-X-DATERANGE" in manifest
    assert "https://cdn.gntv.example/ads/launch.ts" in manifest


def test_build_manifest_without_ads_is_valid() -> None:
    manifest = build_ssai_manifest(target_id="empty", content_segments=[], breaks=[])
    assert manifest == "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXT-X-MEDIA-SEQUENCE:0\n"


def test_signed_beacon_validation_and_duplicate_idempotency(monetization_db: Session) -> None:
    user = create_user(monetization_db, "producer@example.com", "producer")
    campaign, creative, ad_break = seed_campaign(monetization_db, user)
    signature = sign_beacon_payload(idempotency_key="beacon-123", session_id="session-1", event_type="impression")
    payload = TrackingBeaconRequest(
        campaign_id=campaign.id,
        creative_id=creative.id,
        break_id=ad_break.id,
        session_id="session-1",
        event_type=AdImpressionEventType.IMPRESSION,
        idempotency_key="beacon-123",
        signature=signature,
    )
    service = MonetizationService(MonetizationRepository(monetization_db))

    accepted = service.record_beacon(payload)
    duplicate = service.record_beacon(payload)

    assert accepted.idempotency_outcome == "accepted"
    assert duplicate.idempotency_outcome == "duplicate"
    assert accepted.impression_id == duplicate.impression_id
    assert monetization_db.query(AdImpression).count() == 1
    assert monetization_db.query(AdTrackingEvent).count() == 2


def test_invalid_beacon_signature_rejected(monetization_db: Session) -> None:
    service = MonetizationService(MonetizationRepository(monetization_db))
    payload = TrackingBeaconRequest(
        session_id="session-1",
        event_type=AdImpressionEventType.START,
        idempotency_key="beacon-bad",
        signature="bad-signature-value",
    )
    with pytest.raises(HTTPException) as error:
        service.record_beacon(payload)
    assert error.value.status_code == 403


def test_unauthorized_campaign_access(monetization_client: TestClient, monetization_db: Session) -> None:
    viewer = create_user(monetization_db, "viewer@example.com", "viewer")
    response = monetization_client.post(
        "/api/v1/monetization/campaigns",
        headers=auth_headers(viewer),
        json={"name": "Viewer Campaign"},
    )
    assert response.status_code == 403


def test_monetization_api_manifest_and_tracking(monetization_client: TestClient, monetization_db: Session) -> None:
    producer = create_user(monetization_db, "producer@example.com", "producer")
    campaign, creative, ad_break = seed_campaign(monetization_db, producer)
    manifest_response = monetization_client.get("/api/v1/monetization/manifest/gntv-fast/ssai.m3u8")
    signature = sign_beacon_payload(idempotency_key="api-beacon-1", session_id="api-session", event_type="complete")
    beacon_response = monetization_client.post(
        "/api/v1/monetization/tracking/beacon",
        json={
            "campaign_id": str(campaign.id),
            "creative_id": str(creative.id),
            "break_id": str(ad_break.id),
            "session_id": "api-session",
            "event_type": "complete",
            "idempotency_key": "api-beacon-1",
            "signature": signature,
        },
    )
    assert manifest_response.status_code == 200
    assert manifest_response.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert "#EXT-X-DISCONTINUITY" in manifest_response.text
    assert beacon_response.status_code == 202
    assert beacon_response.json()["idempotency_outcome"] == "accepted"


def test_sprint72_openapi_paths_exist() -> None:
    schema = app.openapi()
    assert "/api/v1/monetization/manifest/{target_id}/ssai.m3u8" in schema["paths"]
    assert "/api/v1/monetization/tracking/beacon" in schema["paths"]
    assert "/api/v1/monetization/campaigns" in schema["paths"]


def test_sprint72_migration_upgrade_and_downgrade_on_isolated_database() -> None:
    migration_path = Path(__file__).parents[1] / "alembic/versions/202608131200_module7_sprint72_ssai_fast.py"
    spec = importlib.util.spec_from_file_location("sprint72_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    context = MigrationContext.configure(connection)
    original_op = module.op
    module.op = Operations(context)
    try:
        module.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert {"ad_campaigns", "ad_creatives", "ad_breaks", "ad_impressions", "ad_tracking_events"} <= tables
        module.downgrade()
        assert "ad_campaigns" not in inspect(connection).get_table_names()
    finally:
        module.op = original_op
        connection.close()
        engine.dispose()

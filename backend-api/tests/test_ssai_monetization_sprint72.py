from __future__ import annotations

from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.monetization.beacon_service import BeaconService, BeaconValidationError, generate_beacon_signature
from app.modules.monetization.manifest_stitcher import generate_ssai_hls_manifest
from app.modules.monetization.models import AdBreak, AdCampaign, AdCampaignStatus, AdCreative, AdImpression
from app.modules.monetization.schemas import AdBeaconRequest, AdBreakCreateRequest, AdCampaignCreateRequest
from app.modules.monetization.scte35 import format_hls_daterange_tag, generate_scte35_cue, parse_scte35_cue
from app.modules.monetization.service import MonetizationService
from app.modules.monetization.vast_vmap import VASTVMAPParserError, parse_vast_xml, parse_vmap_xml
from app.utils.jwt import create_access_token


@pytest.fixture(autouse=True)
def setup_monetization_tables(db_session: Session) -> None:
    Base.metadata.create_all(bind=db_session.get_bind())


@pytest.fixture
def auth_headers(db_session: Session) -> dict[str, str]:
    user = User(
        email="ad_admin@gntv.test",
        hashed_password="hashed_password",
        is_active=True,
        is_verified=True,
    )
    role = Role(name="admin", description="Administrator")
    user.roles.append(role)
    user.name = "Ad Admin"
    db_session.add(role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


# 1. VAST Parsing Test
def test_vast_xml_parsing_success() -> None:
    vast_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <VAST version="4.0">
        <Ad id="ad_test_100">
            <InLine>
                <AdTitle>GNTV Commercial Ad 1</AdTitle>
                <Duration>00:00:15</Duration>
                <Impression>https://ad.example.com/impression</Impression>
                <Tracking event="start">https://ad.example.com/start</Tracking>
                <MediaFile delivery="progressive" type="video/mp4" width="1920" height="1080">
                    https://cdn.example.com/ads/promo.mp4
                </MediaFile>
            </InLine>
        </Ad>
    </VAST>"""
    ads = parse_vast_xml(vast_xml)
    assert len(ads) == 1
    assert ads[0].ad_id == "ad_test_100"
    assert ads[0].duration_seconds == 15.0
    assert len(ads[0].media_files) == 1
    assert ads[0].media_files[0].url == "https://cdn.example.com/ads/promo.mp4"


# 2. VMAP Parsing Test
def test_vmap_xml_parsing_success() -> None:
    vmap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <vmap:VMAP xmlns:vmap="http://www.iab.net/vmap-1.0" version="1.0">
        <vmap:AdBreak timeOffset="00:10:00" breakType="linear" breakId="midroll_1">
            <vmap:AdSource id="ad-1" allowMultipleAds="true" followRedirects="true">
                <vmap:VASTData>
                    <VAST version="4.0">
                        <Ad id="ad_vmap_1">
                            <InLine>
                                <AdTitle>VMAP Midroll Ad</AdTitle>
                                <Duration>00:00:30</Duration>
                                <MediaFile type="video/mp4">https://cdn.example.com/vmap_ad.mp4</MediaFile>
                            </InLine>
                        </Ad>
                    </VAST>
                </vmap:VASTData>
            </vmap:AdSource>
        </vmap:AdBreak>
    </vmap:VMAP>"""
    breaks = parse_vmap_xml(vmap_xml)
    assert len(breaks) == 1
    assert breaks[0].break_id == "midroll_1"
    assert breaks[0].time_offset == "00:10:00"
    assert breaks[0].vast_ad is not None
    assert breaks[0].vast_ad.ad_id == "ad_vmap_1"


# 3. Malformed XML and XXE Protection Test
def test_xml_xxe_and_malformed_rejection() -> None:
    xxe_payload = """<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <VAST version="4.0">
        <Ad id="xxe">&xxe;</Ad>
    </VAST>"""
    with pytest.raises(VASTVMAPParserError, match="XXE protection"):
        parse_vast_xml(xxe_payload)

    with pytest.raises(VASTVMAPParserError):
        parse_vast_xml("not an xml string")


# 4. SCTE-35 Cue Test
def test_scte35_cue_generation_and_parsing() -> None:
    cue = generate_scte35_cue(event_id=42, duration_seconds=30.0, cue_type="cue_out")
    assert cue.event_id == 42
    assert cue.duration_seconds == 30.0
    assert cue.cue_type == "cue_out"

    parsed = parse_scte35_cue(cue.raw_base64)
    assert parsed.event_id == 42
    assert parsed.duration_seconds == 30.0
    assert parsed.cue_type == "cue_out"

    daterange_tag = format_hls_daterange_tag(cue)
    assert "#EXT-X-DATERANGE" in daterange_tag
    assert 'CLASS="com.apple.hls.scte35.out"' in daterange_tag
    assert "PLANNED-DURATION=30.000" in daterange_tag


# 5. HLS SSAI Manifest Stitching Test
def test_ssai_hls_manifest_stitching() -> None:
    content_segs = [(6.0, "https://cdn.example.com/c1.ts"), (6.0, "https://cdn.example.com/c2.ts")]
    ad_segs = [(15.0, "https://cdn.example.com/ad1.ts")]
    ad_breaks = [(6.0, ad_segs, None)]

    manifest = generate_ssai_hls_manifest("ch_test_10", content_segments=content_segs, ad_breaks=ad_breaks)
    assert "#EXTM3U" in manifest
    assert "#EXT-X-VERSION:3" in manifest
    assert "#EXT-X-TARGETDURATION:10" in manifest
    assert "#EXT-X-DISCONTINUITY" in manifest
    assert "#EXT-X-DATERANGE" in manifest
    assert "https://cdn.example.com/ad1.ts" in manifest
    assert "https://cdn.example.com/c1.ts" in manifest
    assert manifest.endswith("#EXT-X-ENDLIST\n")


# 6. Signed Tracking Beacon & Idempotency Test
def test_signed_beacon_tracking_and_idempotency(db_session: Session) -> None:
    camp_uuid = uuid4()
    campaign = AdCampaign(id=camp_uuid, name="GNTV Brand Launch", status=AdCampaignStatus.ACTIVE)
    db_session.add(campaign)
    db_session.commit()

    service = MonetizationService(db_session)
    idempotency_key = "idemp_key_unique_12345"
    sig = generate_beacon_signature(str(camp_uuid), "sess_555", "impression", idempotency_key, getattr(settings, "JWT_SECRET_KEY", "secret"))

    beacon_req = AdBeaconRequest(
        campaign_id=str(camp_uuid),
        session_id="sess_555",
        event_type="impression",
        idempotency_key=idempotency_key,
        signature=sig,
    )

    # First call records impression
    res1 = service.process_beacon(beacon_req)
    assert res1.impression_id is not None

    # Second call with same idempotency_key returns duplicate status
    res2 = service.process_beacon(beacon_req)
    assert res2.impression_id == res1.impression_id

    # Count database records
    count = db_session.query(AdImpression).filter(AdImpression.idempotency_key == idempotency_key).count()
    assert count == 1


# 7. Invalid Beacon Signature Rejection Test
def test_invalid_beacon_signature_rejection(db_session: Session) -> None:
    service = MonetizationService(db_session)
    bad_req = AdBeaconRequest(
        campaign_id=str(uuid4()),
        session_id="sess_999",
        event_type="start",
        idempotency_key="idemp_key_bad_999",
        signature="invalid_tampered_signature_hex_1234567890",
    )
    with pytest.raises(HTTPException) as exc_info:
        service.process_beacon(bad_req)
    assert exc_info.value.status_code == 403


# 8. REST API Endpoints Integration Test
def test_monetization_api_routes(db_session: Session, auth_headers: dict[str, str]) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)

        # GET Manifest
        res_manifest = client.get("/api/v1/monetization/manifest/vod_demo_101/ssai.m3u8")
        assert res_manifest.status_code == 200
        assert res_manifest.headers["content-type"] == "application/vnd.apple.mpegurl"
        assert "#EXTM3U" in res_manifest.text
        assert "#EXT-X-MEDIA-SEQUENCE:0" in res_manifest.text

        # POST Campaign
        res_camp = client.post(
            "/api/v1/monetization/campaigns",
            json={"name": "Summer FAST Channel Campaign", "status": "active"},
            headers=auth_headers,
        )
        assert res_camp.status_code == 201
        camp_id = res_camp.json()["id"]

        # GET Campaign
        res_get_camp = client.get(f"/api/v1/monetization/campaigns/{camp_id}", headers=auth_headers)
        assert res_get_camp.status_code == 200
        assert res_get_camp.json()["name"] == "Summer FAST Channel Campaign"

        # POST Creative
        res_creative = client.post(
            f"/api/v1/monetization/campaigns/{camp_id}/creatives",
            json={"name": "Promo 15s", "media_url": "https://cdn.example.com/p15.mp4", "duration_seconds": 15.0},
            headers=auth_headers,
        )
        assert res_creative.status_code == 201

        # POST Ad Break
        res_break = client.post(
            "/api/v1/monetization/breaks",
            json={"target_id": "vod_demo_101", "break_type": "midroll", "time_offset_seconds": 120.0, "duration_seconds": 15.0},
            headers=auth_headers,
        )
        assert res_break.status_code == 201
    finally:
        app.dependency_overrides.clear()


# 9. Unauthorized API Access Test
def test_unauthorized_campaign_creation() -> None:
    client = TestClient(app)
    res = client.post("/api/v1/monetization/campaigns", json={"name": "Unauth Campaign"})
    assert res.status_code in (401, 403)

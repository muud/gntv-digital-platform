"""Automated verification suite for Sprint 6.4 (Multi-DRM, Geo-control & Watermarking)."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app
from app.modules.streaming.models import GeoPolicy
from app.modules.streaming.repositories.drm import DRMRepository
from app.modules.streaming.services import (
    DRMService,
    GeoFencingService,
    WatermarkService,
)

client = TestClient(app)


def test_geo_fencing_service_rules():
    service = GeoFencingService(default_country="US")

    # No policy -> allowed
    res_no_policy = service.evaluate(None, "127.0.0.1")
    assert res_no_policy.allowed is True
    assert res_no_policy.country_code == "US"

    # Allow list policy
    policy_allow = GeoPolicy(
        name="Allow-US-KE",
        country_allow_list=["US", "KE"],
        country_deny_list=[],
        block_vpn=True,
        block_proxy=True,
        fail_closed=True,
    )

    # Allowed country
    res_us = service.evaluate(policy_allow, "127.0.0.1", {"X-Country-Code": "US"})
    assert res_us.allowed is True
    assert res_us.country_code == "US"

    # Denied country (not in allow list)
    res_gb = service.evaluate(policy_allow, "127.0.0.1", {"X-Country-Code": "GB"})
    assert res_gb.allowed is False
    assert res_gb.reason == "country_not_allowed"

    # VPN blocked
    res_vpn = service.evaluate(policy_allow, "127.0.0.1", {"X-Country-Code": "US", "X-VPN-Detected": "true"})
    assert res_vpn.allowed is False
    assert res_vpn.reason == "vpn_detected"

    # Fail closed on unknown/XX
    res_fail_closed = service.evaluate(policy_allow, "10.99.1.1")
    assert res_fail_closed.allowed is False
    assert res_fail_closed.reason == "geo_resolution_failed"


def test_watermark_service():
    wm_service = WatermarkService()
    sess_id = uuid4()

    text = wm_service.generate_watermark_text(user_id=42, session_id=sess_id, client_ip="192.168.1.100")
    assert "UID:42" in text
    assert str(sess_id)[:8] in text
    assert "192.168.1.100" in text

    ab_seq = wm_service.generate_ab_sequence(sess_id, length=32)
    assert len(ab_seq) == 32
    assert all(bit in ("0", "1") for bit in ab_seq)

    # Deterministic sequence check
    ab_seq2 = wm_service.generate_ab_sequence(sess_id, length=32)
    assert ab_seq == ab_seq2

    cfg = wm_service.get_watermark_config(user_id=42, session_id=sess_id, client_ip="192.168.1.100")
    assert cfg["session_id"] == str(sess_id)
    assert cfg["opacity"] == 0.25
    assert len(cfg["ab_sequence"]) == 64


def test_drm_service_token_issuance_and_validation():
    db = Session()
    repo = DRMRepository(db)
    geo_service = GeoFencingService()
    drm_service = DRMService(repo, geo_service)

    target_id = uuid4()
    sess_id = uuid4()

    # Issue token for Widevine
    token, url, expires = drm_service.issue_drm_token(
        target_id=target_id,
        user_id=101,
        device_id="device-web-1",
        drm_system="widevine",
        session_id=sess_id,
    )
    assert token is not None
    assert "widevine" in url
    assert expires > datetime.now(UTC)

    # Validate valid token
    payload = drm_service.validate_drm_token(token)
    assert payload["target_id"] == str(target_id)
    assert payload["user_id"] == 101
    assert payload["device_id"] == "device-web-1"
    assert payload["drm_system"] == "widevine"

    # Unsupported DRM system
    with pytest.raises(Exception):
        drm_service.issue_drm_token(target_id=target_id, user_id=101, device_id="d1", drm_system="invalid_sys")

    # Invalid token signature
    invalid_token = token[:-5] + "XXXXX"
    with pytest.raises(Exception):
        drm_service.validate_drm_token(invalid_token)


def test_drm_license_challenge_processing():
    db = Session()
    repo = DRMRepository(db)
    geo_service = GeoFencingService()
    drm_service = DRMService(repo, geo_service)

    cert_bytes = drm_service.get_fairplay_cert()
    assert cert_bytes is not None
    assert len(cert_bytes) > 0

    token_payload = {"target_id": str(uuid4()), "user_id": 77}
    challenge = b"sample_challenge_bytes_12345"

    # FairPlay CKC
    ckc = drm_service.process_license_challenge("fairplay", challenge, token_payload)
    assert ckc.startswith(b"GNTV_CKC_RESPONSE:")

    # Widevine response
    wv_resp = drm_service.process_license_challenge("widevine", challenge, token_payload)
    assert wv_resp is not None
    assert len(wv_resp) > 0

    # PlayReady response
    pr_resp = drm_service.process_license_challenge("playready", challenge, token_payload)
    assert b"PlayReadyLicenseResponse" in pr_resp


def test_sprint64_api_routes():
    # Geo check endpoint
    response = client.get("/api/v1/streaming/geo/check")
    assert response.status_code == 200
    data = response.json()
    assert "allowed" in data
    assert "country_code" in data

    # FairPlay Cert endpoint
    cert_resp = client.get("/api/v1/streaming/drm/fairplay/cert")
    assert cert_resp.status_code == 200
    assert cert_resp.headers["content-type"] == "application/octet-stream"


def test_sprint64_migration_upgrade_and_downgrade():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text

    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "202608061800_module6_sprint64_drm_geo_watermark.py"
    spec = importlib.util.spec_from_file_location("sprint64_mig", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            """
            CREATE TABLE live_channels (
                id CHAR(32) PRIMARY KEY,
                channel_code VARCHAR(80) NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE recordings (
                id CHAR(32) PRIMARY KEY,
                stream_id CHAR(32) NOT NULL
            )
            """
        )
    )
    context = MigrationContext.configure(connection)
    original_op = module.op
    module.op = Operations(context)
    try:
        module.upgrade()
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        assert "drm_policies" in tables
        assert "geo_policies" in tables
        assert "drm_keys" in tables
        assert {"drm_policy_id", "geo_policy_id"} <= {
            col["name"] for col in inspector.get_columns("live_channels")
        }
        assert {"drm_policy_id", "geo_policy_id"} <= {
            col["name"] for col in inspector.get_columns("recordings")
        }
        module.downgrade()
        tables_after = set(inspect(connection).get_table_names())
        assert "drm_policies" not in tables_after
        assert "geo_policies" not in tables_after
        assert "drm_keys" not in tables_after
    finally:
        module.op = original_op
        connection.close()
        engine.dispose()

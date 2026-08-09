"""Automated verification suite for Sprint 6.5 (QoE Telemetry & Observability)."""

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.modules.streaming.models import (
    PlaybackSession,
    PlaybackSessionStatus,
    QoEAggregateHourly,
)
from app.modules.streaming.repositories.telemetry import QoERepository
from app.modules.streaming.schemas.contracts import (
    TelemetryBatchRequest,
    TelemetryEventItem,
)
from app.modules.streaming.services.telemetry import QoEService, anonymize_identifier

pytestmark = pytest.mark.anyio


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_pii_anonymization():
    raw_ip = "197.232.45.10"
    anon1 = anonymize_identifier(raw_ip)
    anon2 = anonymize_identifier(raw_ip)
    assert len(anon1) == 32
    assert anon1 == anon2
    assert raw_ip not in anon1


def test_qoe_telemetry_ingestion_and_summary(db_session: Session):
    channel_id = uuid4()
    session_id = uuid4()

    db_session.add(
        PlaybackSession(
            id=session_id,
            live_channel_id=channel_id,
            user_id=1,
            device_id="test-device-1",
            token_jti_hash=f"token-{session_id}",
            status=PlaybackSessionStatus.PLAYING,
            policy_version=1,
            expires_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    repo = QoERepository(db_session)
    service = QoEService(repo)

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    batch_req = TelemetryBatchRequest(
        session_id=session_id,
        sequence_number=1,
        client_timestamp_ms=now_ms - 5000,
        events=[
            TelemetryEventItem(
                event_type="startup",
                timestamp_ms=now_ms - 5000,
                position_ms=0,
                bitrate_bps=2500000,
                metadata={"stall_duration_ms": 320},
            ),
            TelemetryEventItem(
                event_type="buffer_start",
                timestamp_ms=now_ms - 3000,
                position_ms=2000,
                bitrate_bps=2500000,
            ),
            TelemetryEventItem(
                event_type="buffer_end",
                timestamp_ms=now_ms - 2000,
                position_ms=2000,
                bitrate_bps=4500000,
                metadata={"stall_duration_ms": 1000},
            ),
        ],
    )

    resp = service.ingest_batch(batch_req, client_ip="41.204.180.1", user_agent="Mozilla/5.0")
    assert resp.accepted_count == 3
    assert resp.dropped_count == 0

    metric = repo.get_session_metric(session_id)
    assert metric is not None
    assert metric.startup_latency_ms == 320
    assert metric.rebuffer_count == 1
    assert metric.total_rebuffer_duration_ms == 1000
    assert metric.average_bitrate_bps == 3166666


def test_qoe_telemetry_api_routes(client: TestClient, db_session: Session):
    channel_id = uuid4()
    session_id = uuid4()

    db_session.add(
        PlaybackSession(
            id=session_id,
            live_channel_id=channel_id,
            user_id=1,
            device_id="test-device-route",
            token_jti_hash=f"token-{session_id}",
            status=PlaybackSessionStatus.PLAYING,
            policy_version=1,
            expires_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    batch_payload = {
        "session_id": str(session_id),
        "sequence_number": 1,
        "client_timestamp_ms": now_ms,
        "events": [
            {
                "event_type": "startup",
                "timestamp_ms": now_ms,
                "position_ms": 0,
                "bitrate_bps": 3000000,
                "metadata": {"stall_duration_ms": 400},
            }
        ],
    }

    res = client.post("/api/v1/streaming/telemetry/batch", json=batch_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["accepted_count"] == 1
    assert data["next_flush_interval_ms"] == 10000


def test_qoe_hourly_aggregation(db_session: Session):
    repo = QoERepository(db_session)
    service = QoEService(repo)
    target_id = uuid4()
    now_dt = datetime.now(UTC)

    agg = QoEAggregateHourly(
        window_start=now_dt,
        target_type="channel",
        target_id=target_id,
        device_category="all",
        country_code="KE",
        total_sessions=150,
        p50_startup_latency_ms=300,
        p95_startup_latency_ms=950,
        avg_rebuffer_ratio=0.012,
        total_errors=2,
        avg_bitrate_bps=4200000,
    )
    repo.save_hourly_aggregate(agg)

    summary = service.get_metrics_summary(target_id)
    assert summary["target_id"] == str(target_id)
    assert summary["total_sessions"] == 150
    assert summary["status"] == "healthy"


def test_sprint65_migration_upgrade_and_downgrade():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration_path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "202608081200_module6_sprint65_qoe_telemetry.py"
    )
    spec = importlib.util.spec_from_file_location("sprint65_mig", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        text(
            """
            CREATE TABLE playback_sessions (
                id CHAR(32) PRIMARY KEY
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE live_channels (
                id CHAR(32) PRIMARY KEY
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE recordings (
                id CHAR(32) PRIMARY KEY
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
        assert "qoe_events_raw" in tables
        assert "qoe_session_metrics" in tables
        assert "qoe_aggregates_hourly" in tables

        module.downgrade()
        tables_after = set(inspect(connection).get_table_names())
        assert "qoe_events_raw" not in tables_after
        assert "qoe_session_metrics" not in tables_after
        assert "qoe_aggregates_hourly" not in tables_after
    finally:
        module.op = original_op
        connection.close()
        engine.dispose()


def test_qoe_consumer_worker(db_session: Session):
    from app.modules.streaming.workers.qoe_consumer import QoEConsumerWorker

    repo = QoERepository(db_session)
    worker = QoEConsumerWorker(repo)

    target_id = uuid4()
    count = worker.process_stream_batch([
        {"target_id": str(target_id), "event": "startup"},
        {"target_id": None},
    ])
    assert count == 1

    agg = worker.compute_hourly_rollup(
        window_start=datetime.now(UTC),
        target_type="channel",
        target_id=target_id,
        total_sessions=10,
        p50_ms=250,
        p95_ms=800,
        avg_rebuffer=0.01,
        total_errors=0,
    )
    assert agg.total_sessions == 10


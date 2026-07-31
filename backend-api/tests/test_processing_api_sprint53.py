"""Sprint 5.3 Processing Operations Center API integration tests."""

import json
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.redis import get_redis
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import Role, User
from app.modules.streaming.models import (
    Manifest,
    ManifestFormat,
    ManifestKind,
    ManifestStatus,
    Thumbnail,
    ThumbnailKind,
    ThumbnailStatus,
    TranscodingJob,
)
from app.modules.streaming.processing.api import get_processing_dispatcher


PROCESSING_TABLES: list[Table] = [
    TranscodingJob.__table__,
    Manifest.__table__,
    Thumbnail.__table__,
]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.online = True

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def ping(self) -> bool:
        return self.online

    async def scan_iter(self, match: str) -> AsyncIterator[str]:
        prefix = match.removesuffix("*")
        for key in self.values:
            if key.startswith(prefix):
                yield key


class FakeDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []
        self.cancelled: list[str] = []

    async def enqueue(
        self, *, task_name: str, queue: str, payload: dict[str, Any], task_id: str
    ) -> str:
        self.enqueued.append(
            {"task_name": task_name, "queue": queue, "payload": payload, "task_id": task_id}
        )
        return task_id

    async def cancel(self, task_id: str) -> None:
        self.cancelled.append(task_id)


def operator() -> User:
    user = User(
        id=901,
        email="processing-operator@example.test",
        hashed_password="unused",
        is_active=True,
        is_verified=True,
    )
    user.roles.append(Role(name="operator"))
    return user


@pytest.fixture()
def processing_client(tmp_path: Path) -> Generator[tuple[TestClient, Session, FakeRedis, FakeDispatcher], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=PROCESSING_TABLES)
    local = sessionmaker(bind=engine, expire_on_commit=False)
    db = local()
    redis = FakeRedis()
    producer = FakeDispatcher()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test-media")

    old_workspace = settings.MEDIA_PROCESSING_WORKSPACE_ROOT
    old_output = settings.MEDIA_PROCESSING_OUTPUT_ROOT
    settings.MEDIA_PROCESSING_WORKSPACE_ROOT = str(tmp_path)
    settings.MEDIA_PROCESSING_OUTPUT_ROOT = str(tmp_path / "output")

    def database_override() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = database_override
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_processing_dispatcher] = lambda: producer
    app.dependency_overrides[get_current_user] = operator
    try:
        yield TestClient(app), db, redis, producer
    finally:
        app.dependency_overrides.clear()
        settings.MEDIA_PROCESSING_WORKSPACE_ROOT = old_workspace
        settings.MEDIA_PROCESSING_OUTPUT_ROOT = old_output
        db.close()
        Base.metadata.drop_all(engine, tables=PROCESSING_TABLES)
        engine.dispose()


def test_job_create_read_list_cancel_and_idempotency(
    processing_client: tuple[TestClient, Session, FakeRedis, FakeDispatcher],
) -> None:
    client, _db, redis, producer = processing_client
    payload = {
        "idempotency_key": "studio-job-0001",
        "job_type": "vod_transcode",
        "input_url": "source.mp4",
        "output_prefix": "tenant/jobs/studio-job-0001",
        "renditions": ["720p", "480p"],
        "queue": "transcode-cpu",
    }
    created = client.post("/api/v1/processing/jobs", json=payload)
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "QUEUED"
    assert producer.enqueued[0]["task_name"] == "streaming.media.transcode_cpu"
    assert producer.enqueued[0]["payload"]["renditions"] == ["720p", "480p"]

    duplicate = client.post("/api/v1/processing/jobs", json=payload)
    assert duplicate.status_code == 202
    assert duplicate.json()["job_id"] == body["job_id"]
    assert len(producer.enqueued) == 1

    redis.values[f"gntv:processing:progress:{body['job_id']}"] = json.dumps(
        {"metrics": {"encoding_fps": 29.97, "encoding_speed_factor": 2.4}}
    )
    detail = client.get(f"/api/v1/processing/jobs/{body['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["metrics"]["encoding_fps"] == 29.97
    assert client.get("/api/v1/processing/jobs").json()["total"] == 1

    cancelled = client.delete(f"/api/v1/processing/jobs/{body['job_id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert producer.cancelled == ["studio-job-0001"]
    assert client.delete(f"/api/v1/processing/jobs/{body['job_id']}").status_code == 409
    assert client.get(f"/api/v1/processing/jobs/{uuid4()}").status_code == 404


def test_queue_worker_manifest_thumbnail_and_metrics_read_models(
    processing_client: tuple[TestClient, Session, FakeRedis, FakeDispatcher],
) -> None:
    client, db, redis, _producer = processing_client
    now = datetime.now(UTC)
    stream_id = uuid4()
    manifest = Manifest(
        stream_id=stream_id,
        format=ManifestFormat.HLS,
        kind=ManifestKind.LIVE,
        status=ManifestStatus.READY,
        oss_object_key="channel/master.m3u8",
        cdn_path="unused-by-processing-api",
        generation=1,
        renditions=[],
        published_at=now,
    )
    thumbnail = Thumbnail(
        stream_id=stream_id,
        kind=ThumbnailKind.POSTER,
        width=1280,
        height=720,
        oss_object_key="channel/thumbnails/poster.jpg",
        status=ThumbnailStatus.READY,
    )
    db.add_all([manifest, thumbnail])
    db.commit()

    redis.values["gntv:processing:worker:worker-1"] = json.dumps(
        {
            "worker_id": "worker-1",
            "hostname": "node-1",
            "queue": "transcode-cpu",
            "status": "processing",
            "healthy": True,
            "observed_at": now.isoformat(),
            "hardware": {"cpu_usage_pct": 31.5},
        }
    )
    metrics_job_id = uuid4()
    redis.values[f"gntv:processing:metrics:{metrics_job_id}"] = json.dumps(
        {
            "job_id": str(metrics_job_id),
            "queue": "transcode-cpu",
            "processing_duration_seconds": 12.5,
            "encoding_fps": 29.97,
            "observed_at": now.isoformat(),
        }
    )
    redis.values[f"gntv:processing:manifest:{metrics_job_id}"] = json.dumps(
        {
            "job_id": str(metrics_job_id),
            "queue": "manifest",
            "manifest_freshness_seconds": 0.4,
            "observed_at": now.isoformat(),
        }
    )

    workers = client.get("/api/v1/processing/workers")
    assert workers.status_code == 200
    assert workers.json()[0]["hardware"]["cpu_usage_pct"] == 31.5
    queues = client.get("/api/v1/processing/queues")
    assert queues.json()["queues"]["transcode-cpu"]["active_workers"] == 1
    assert set(queues.json()["queues"]) == {
        "transcode-cpu",
        "transcode-accelerated",
        "manifest",
        "thumbnail",
    }

    manifests = client.get("/api/v1/processing/manifests").json()
    assert manifests["items"][0]["manifest_path"] == "channel/master.m3u8"
    assert "cdn_path" not in manifests["items"][0]
    assert client.get(f"/api/v1/processing/manifests/{manifest.id}").status_code == 200
    assert client.get(f"/api/v1/processing/manifests/{uuid4()}").status_code == 404

    thumbnails = client.get("/api/v1/processing/thumbnails").json()
    assert thumbnails["items"][0]["asset_path"].endswith("poster.jpg")
    assert client.get(f"/api/v1/processing/thumbnails/{thumbnail.id}").status_code == 200
    assert client.get(f"/api/v1/processing/thumbnails/{uuid4()}").status_code == 404

    metrics = client.get("/api/v1/processing/metrics").json()
    assert metrics["total"] == 1
    assert metrics["items"][0]["manifest_freshness_seconds"] == 0.4
    assert client.get(f"/api/v1/processing/metrics?job_id={metrics_job_id}").json()["total"] == 1


def test_manifest_validation_and_contract_boundaries(
    processing_client: tuple[TestClient, Session, FakeRedis, FakeDispatcher],
) -> None:
    client, _db, _redis, _producer = processing_client
    output_root = Path(settings.MEDIA_PROCESSING_OUTPUT_ROOT)
    variant = output_root / "channel/stream_720p"
    variant.mkdir(parents=True)
    (variant / "segment_000001.ts").write_bytes(b"segment")
    (variant / "index.m3u8").write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:6",
                "#EXT-X-INDEPENDENT-SEGMENTS",
                "#EXT-X-TARGETDURATION:6",
                "#EXT-X-MEDIA-SEQUENCE:1",
                "#EXTINF:6.0,",
                "segment_000001.ts",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (output_root / "channel/master.m3u8").write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:6",
                "#EXT-X-INDEPENDENT-SEGMENTS",
                "#EXT-X-STREAM-INF:BANDWIDTH=2000000",
                "stream_720p/index.m3u8",
                "",
            ]
        ),
        encoding="utf-8",
    )

    valid = client.post(
        "/api/v1/processing/manifests/validate",
        json={"manifest_url": "channel/master.m3u8"},
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True
    invalid = client.post(
        "/api/v1/processing/manifests/validate",
        json={"manifest_url": "../../etc/passwd"},
    )
    assert invalid.json()["valid"] is False

    schema = app.openapi()
    processing_paths = {path for path in schema["paths"] if path.startswith("/api/v1/processing")}
    assert processing_paths == {
        "/api/v1/processing/jobs",
        "/api/v1/processing/jobs/{job_id}",
        "/api/v1/processing/workers",
        "/api/v1/processing/queues",
        "/api/v1/processing/manifests",
        "/api/v1/processing/manifests/validate",
        "/api/v1/processing/manifests/{manifest_id}",
        "/api/v1/processing/thumbnails",
        "/api/v1/processing/thumbnails/{thumbnail_id}",
        "/api/v1/processing/metrics",
    }
    assert not any(
        forbidden in path
        for path in processing_paths
        for forbidden in ("playback", "recordings", "dvr", "cdn")
    )
    for path in processing_paths:
        for method, operation in schema["paths"][path].items():
            if method not in {"get", "post", "delete"}:
                continue
            assert operation["security"] == [{"HTTPBearer": []}]
            assert {"401", "403"} <= set(operation["responses"])
    assert "409" in schema["paths"]["/api/v1/processing/jobs"]["post"]["responses"]
    job_item_responses = schema["paths"]["/api/v1/processing/jobs/{job_id}"]
    assert "404" in job_item_responses["get"]["responses"]
    assert {"404", "409"} <= set(job_item_responses["delete"]["responses"])


def test_invalid_redis_telemetry_is_ignored(
    processing_client: tuple[TestClient, Session, FakeRedis, FakeDispatcher],
) -> None:
    client, _db, redis, _producer = processing_client
    redis.values.update(
        {
            "gntv:processing:worker:missing-fields": json.dumps(
                {"worker_id": "incomplete"}
            ),
            "gntv:processing:worker:invalid-date": json.dumps(
                {
                    "worker_id": "invalid-date",
                    "queue": "transcode-cpu",
                    "observed_at": "not-a-date",
                }
            ),
            "gntv:processing:metrics:not-a-uuid": json.dumps(
                {"job_id": "not-a-uuid", "encoding_fps": 29.97}
            ),
            f"gntv:processing:metrics:{uuid4()}": json.dumps(
                {"job_id": str(uuid4()), "encoding_fps": "not-a-number"}
            ),
        }
    )

    assert client.get("/api/v1/processing/workers").json() == []
    assert client.get("/api/v1/processing/metrics").json() == {
        "items": [],
        "total": 0,
    }


def test_checked_in_processing_openapi_matches_registered_routes() -> None:
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "contracts"
        / "processing-openapi.json"
    )
    exported = json.loads(contract_path.read_text(encoding="utf-8"))
    registered = app.openapi()
    processing_paths = {
        path: item
        for path, item in registered["paths"].items()
        if path.startswith("/api/v1/processing")
    }

    validate(exported)
    assert exported["openapi"] == "3.1.0"
    assert exported["paths"] == processing_paths

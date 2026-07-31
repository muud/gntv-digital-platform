"""Provider-neutral processing metrics and Redis worker-health snapshots."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.modules.streaming.media.process import FFmpegProgress


@dataclass(frozen=True, slots=True)
class ProcessingMetrics:
    job_id: UUID
    queue: str
    processing_duration_seconds: float
    queue_wait_time_seconds: float
    encoding_fps: float | None
    encoding_speed_factor: float | None
    cpu_usage_percent: float
    dropped_frames: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ManifestMetrics:
    job_id: UUID
    queue: str
    manifest_freshness_seconds: float
    observed_at: datetime


class TelemetrySink(Protocol):
    async def progress(self, job_id: UUID, queue: str, progress: FFmpegProgress) -> None: ...
    async def completed(self, metrics: ProcessingMetrics) -> None: ...
    async def manifest(self, metrics: ManifestMetrics) -> None: ...
    async def worker_health(self, worker_id: str, queue: str, healthy: bool) -> None: ...


class RedisTelemetryCommands(Protocol):
    async def set(self, name: str, value: str, **kwargs: Any) -> Any: ...
    async def publish(self, channel: str, message: str) -> Any: ...


class RedisTelemetrySink:
    def __init__(self, redis: RedisTelemetryCommands, *, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    async def progress(self, job_id: UUID, queue: str, progress: FFmpegProgress) -> None:
        payload = {
            "event_type": "job.processing",
            "job_id": str(job_id),
            "queue": queue,
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": {key: value for key, value in asdict(progress).items() if value is not None},
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        await self.redis.set(f"gntv:processing:progress:{job_id}", encoded, ex=self.ttl_seconds)
        await self.redis.publish("gntv.events.processing", encoded)

    async def completed(self, metrics: ProcessingMetrics) -> None:
        payload = asdict(metrics)
        payload["job_id"] = str(metrics.job_id)
        payload["observed_at"] = metrics.observed_at.isoformat()
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        await self.redis.set(f"gntv:processing:metrics:{metrics.job_id}", encoded, ex=self.ttl_seconds)
        await self.redis.publish("gntv.events.processing", encoded)

    async def manifest(self, metrics: ManifestMetrics) -> None:
        payload = asdict(metrics)
        payload["job_id"] = str(metrics.job_id)
        payload["observed_at"] = metrics.observed_at.isoformat()
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        await self.redis.set(f"gntv:processing:manifest:{metrics.job_id}", encoded, ex=self.ttl_seconds)
        await self.redis.publish("gntv.events.processing", encoded)

    async def worker_health(self, worker_id: str, queue: str, healthy: bool) -> None:
        payload = json.dumps(
            {
                "worker_id": worker_id,
                "queue": queue,
                "healthy": healthy,
                "observed_at": datetime.now(UTC).isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        await self.redis.set(f"gntv:processing:worker:{worker_id}", payload, ex=self.ttl_seconds)


class NullTelemetrySink:
    async def progress(self, job_id: UUID, queue: str, progress: FFmpegProgress) -> None:
        del job_id, queue, progress

    async def completed(self, metrics: ProcessingMetrics) -> None:
        del metrics

    async def manifest(self, metrics: ManifestMetrics) -> None:
        del metrics

    async def worker_health(self, worker_id: str, queue: str, healthy: bool) -> None:
        del worker_id, queue, healthy


__all__ = [
    "ManifestMetrics",
    "NullTelemetrySink",
    "ProcessingMetrics",
    "RedisTelemetrySink",
    "TelemetrySink",
]

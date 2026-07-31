"""Celery consumers for approved Sprint 5.3 queues only."""

import asyncio
import os
import socket
from pathlib import Path
from typing import Any, cast

import redis.asyncio as redis
from celery import Celery  # type: ignore[import-untyped]
from kombu import Queue  # type: ignore[import-untyped]

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.streaming.media.commands import FFmpegCommandBuilder, FFprobeCommandBuilder
from app.modules.streaming.media.contracts import (
    ManifestTaskPayload,
    ThumbnailTaskPayload,
    TranscodeTaskPayload,
)
from app.modules.streaming.media.executor import MediaTaskExecutor, RetryableMediaJobError, retry_delay
from app.modules.streaming.media.pipeline import MediaPipeline
from app.modules.streaming.media.process import AsyncProcessRunner
from app.modules.streaming.media.repository import MediaJobRepository
from app.modules.streaming.media.telemetry import RedisTelemetryCommands, RedisTelemetrySink


class GPUWorkerDisabledError(RuntimeError):
    """Raised when accelerated execution is requested without explicit approval."""


media_worker_app = Celery(
    "gntv-media-workers",
    broker=str(settings.REDIS_URL),
    backend=None,
)
media_worker_app.conf.update(
    task_queues=(
        Queue("transcode-cpu"),
        Queue("transcode-accelerated"),
        Queue("manifest"),
        Queue("thumbnail"),
        Queue("recording"),  # Declared for topology only; no recording task is registered.
    ),
    task_routes={
        "streaming.media.transcode_cpu": {"queue": "transcode-cpu"},
        "streaming.media.transcode_accelerated": {"queue": "transcode-accelerated"},
        "streaming.media.manifest": {"queue": "manifest"},
        "streaming.media.thumbnail": {"queue": "thumbnail"},
    },
    task_serializer="json",
    accept_content=("json",),
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def execute_task(kind: str, payload: dict[str, Any]) -> dict[str, object]:
    if kind == "transcode-accelerated" and not settings.MEDIA_GPU_WORKERS_ENABLED:
        raise GPUWorkerDisabledError(
            "accelerated media workers are disabled by MEDIA_GPU_WORKERS_ENABLED"
        )
    redis_client = redis.from_url(  # type: ignore[no-untyped-call]
        str(settings.REDIS_URL), decode_responses=True
    )
    db = SessionLocal()
    try:
        telemetry = RedisTelemetrySink(
            cast(RedisTelemetryCommands, redis_client),
            ttl_seconds=settings.MEDIA_TELEMETRY_TTL_SECONDS,
        )
        identity = worker_id()
        pipeline = MediaPipeline(
            workspace_root=Path(settings.MEDIA_PROCESSING_WORKSPACE_ROOT),
            output_root=Path(settings.MEDIA_PROCESSING_OUTPUT_ROOT),
            ffmpeg=FFmpegCommandBuilder(settings.FFMPEG_BINARY),
            ffprobe=FFprobeCommandBuilder(settings.FFPROBE_BINARY),
            runner=AsyncProcessRunner.default(),
            telemetry=telemetry,
            worker_id=identity,
        )
        executor = MediaTaskExecutor(
            MediaJobRepository(db),
            pipeline,
            identity,
            lease_seconds=settings.MEDIA_WORKER_LEASE_SECONDS,
        )
        await telemetry.worker_health(identity, kind, True)
        if kind == "transcode-cpu":
            return await executor.transcode(TranscodeTaskPayload.model_validate(payload), accelerated=False)
        if kind == "transcode-accelerated":
            return await executor.transcode(TranscodeTaskPayload.model_validate(payload), accelerated=True)
        if kind == "manifest":
            return await executor.manifest(ManifestTaskPayload.model_validate(payload))
        if kind == "thumbnail":
            return await executor.thumbnail(ThumbnailTaskPayload.model_validate(payload))
        raise ValueError("unsupported media worker kind")
    finally:
        db.close()
        await redis_client.aclose()


def run_with_retry(task: Any, kind: str, payload: dict[str, Any]) -> dict[str, object]:
    try:
        return asyncio.run(execute_task(kind, payload))
    except RetryableMediaJobError as exc:
        attempt = int(payload.get("attempt", 1))
        max_attempts = int(payload.get("max_attempts", 3))
        raise task.retry(
            exc=exc,
            countdown=retry_delay(attempt),
            max_retries=max(0, max_attempts - 1),
        ) from exc


@media_worker_app.task(bind=True, name="streaming.media.transcode_cpu")  # type: ignore[untyped-decorator]
def transcode_cpu(task: Any, payload: dict[str, Any]) -> dict[str, object]:
    return run_with_retry(task, "transcode-cpu", payload)


@media_worker_app.task(bind=True, name="streaming.media.transcode_accelerated")  # type: ignore[untyped-decorator]
def transcode_accelerated(task: Any, payload: dict[str, Any]) -> dict[str, object]:
    return run_with_retry(task, "transcode-accelerated", payload)


@media_worker_app.task(bind=True, name="streaming.media.manifest")  # type: ignore[untyped-decorator]
def manifest(task: Any, payload: dict[str, Any]) -> dict[str, object]:
    return run_with_retry(task, "manifest", payload)


@media_worker_app.task(bind=True, name="streaming.media.thumbnail")  # type: ignore[untyped-decorator]
def thumbnail(task: Any, payload: dict[str, Any]) -> dict[str, object]:
    return run_with_retry(task, "thumbnail", payload)


__all__ = [
    "GPUWorkerDisabledError",
    "execute_task",
    "manifest",
    "media_worker_app",
    "thumbnail",
    "transcode_accelerated",
    "transcode_cpu",
]

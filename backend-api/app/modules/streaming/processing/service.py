"""Application service for approved Processing Operations Center operations."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.modules.streaming.media.contracts import (
    ManifestTaskPayload,
    ThumbnailTaskPayload,
    TranscodeTaskPayload,
)
from app.modules.streaming.media.manifests import (
    ManifestValidationError,
    validate_dash_mpd,
    validate_hls_master,
)
from app.modules.streaming.media.security import (
    UnsafeMediaSourceError,
    resolve_within,
    safe_relative_path,
    validate_input_source,
)
from app.modules.streaming.models import (
    Manifest,
    ManifestFormat,
    Thumbnail,
    TranscodingJob,
    TranscodingJobStatus,
    TranscodingJobType,
)
from app.modules.streaming.processing.dispatch import ProcessingDispatcher
from app.modules.streaming.processing.repository import ProcessingRepository
from app.modules.streaming.processing.schemas import (
    ManifestPage,
    ManifestStatusResponse,
    ManifestValidationResponse,
    MetricsPage,
    ProcessingJobCancelResponse,
    ProcessingJobCreateRequest,
    ProcessingJobPage,
    ProcessingJobResponse,
    ProcessingMetricsResponse,
    QueueStatus,
    QueueTelemetryResponse,
    ThumbnailPage,
    ThumbnailStatusResponse,
    WorkerHardware,
    WorkerStatusResponse,
)


APPROVED_QUEUES = (
    "transcode-cpu",
    "transcode-accelerated",
    "manifest",
    "thumbnail",
)


class RedisReadCommands(Protocol):
    async def get(self, name: str) -> Any: ...
    async def ping(self) -> Any: ...
    def scan_iter(self, match: str) -> Any: ...


class ProcessingConflictError(RuntimeError):
    pass


class ProcessingNotFoundError(LookupError):
    pass


def _status(job: TranscodingJob) -> str:
    if job.status == TranscodingJobStatus.LEASED:
        return "CLAIMED"
    if job.status == TranscodingJobStatus.RUNNING:
        return str(job.progress.get("phase", "PROCESSING")).upper()
    return {
        TranscodingJobStatus.QUEUED: "QUEUED",
        TranscodingJobStatus.RETRYING: "RETRYING",
        TranscodingJobStatus.SUCCEEDED: "COMPLETED",
        TranscodingJobStatus.FAILED: "FAILED",
        TranscodingJobStatus.CANCELLED: "CANCELLED",
    }[job.status]


def _job_type(job: TranscodingJob) -> str:
    if job.capability in {"vod_transcode", "live_transcode", "manifest", "thumbnail"}:
        return job.capability
    if job.queue == "manifest":
        return "manifest"
    if job.queue == "thumbnail":
        return "thumbnail"
    return "live_transcode" if job.job_type == TranscodingJobType.LIVE_TRANSCODE else "vod_transcode"


def job_response(job: TranscodingJob, telemetry: dict[str, Any] | None = None) -> ProcessingJobResponse:
    metrics = dict(telemetry or {})
    progress_value = job.progress.get("progress", job.progress.get("percent", 0))
    try:
        progress = max(0.0, min(100.0, float(progress_value)))
    except (TypeError, ValueError):
        progress = 0.0
    return ProcessingJobResponse(
        job_id=job.id,
        job_type=cast(Any, _job_type(job)),
        status=_status(job),
        queue=job.queue,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        progress=progress,
        metrics=metrics,
        worker_id=job.worker_id,
        error_code=job.error_code,
        error_detail=job.error_detail,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


class ProcessingService:
    def __init__(
        self,
        repository: ProcessingRepository,
        redis: RedisReadCommands,
        dispatcher: ProcessingDispatcher,
    ) -> None:
        self.repository = repository
        self.redis = redis
        self.dispatcher = dispatcher

    def _route(self, payload: ProcessingJobCreateRequest) -> tuple[str, str, TranscodingJobType]:
        if payload.job_type in {"vod_transcode", "live_transcode"}:
            queue = payload.queue or "transcode-cpu"
            return (
                queue,
                "streaming.media.transcode_accelerated"
                if queue == "transcode-accelerated"
                else "streaming.media.transcode_cpu",
                TranscodingJobType.LIVE_TRANSCODE,
            )
        if payload.job_type == "manifest":
            return "manifest", "streaming.media.manifest", TranscodingJobType.PACKAGE
        return "thumbnail", "streaming.media.thumbnail", TranscodingJobType.THUMBNAIL

    def _task_payload(
        self, request: ProcessingJobCreateRequest, job: TranscodingJob
    ) -> dict[str, Any]:
        if request.job_type in {"vod_transcode", "live_transcode"}:
            return TranscodeTaskPayload(
                job_id=job.id,
                idempotency_key=job.idempotency_key,
                enqueued_at=job.created_at,
                input_source=request.input_url,
                output_prefix=request.output_prefix,
                renditions=request.renditions,
                attempt=1,
                max_attempts=request.max_attempts,
                timeout_seconds=request.timeout_seconds,
                live=request.job_type == "live_transcode",
            ).model_dump(mode="json")
        if request.job_type == "manifest":
            return ManifestTaskPayload(
                job_id=job.id,
                idempotency_key=job.idempotency_key,
                enqueued_at=job.created_at,
                workspace=cast(str, request.workspace),
                output_prefix=request.output_prefix,
                renditions=request.renditions,
            ).model_dump(mode="json")
        return ThumbnailTaskPayload(
            job_id=job.id,
            idempotency_key=job.idempotency_key,
            enqueued_at=job.created_at,
            input_source=request.input_url,
            workspace=cast(str, request.workspace),
            kinds=request.thumbnail_kinds,
            interval_seconds=request.thumbnail_interval_seconds,
            timeout_seconds=min(request.timeout_seconds, 3600),
        ).model_dump(mode="json")

    def _validate_paths(self, request: ProcessingJobCreateRequest) -> None:
        safe_relative_path(request.output_prefix)
        if request.job_type != "manifest":
            validate_input_source(
                request.input_url,
                local_root=Path(settings.MEDIA_PROCESSING_WORKSPACE_ROOT),
            )
        if request.workspace is not None:
            resolve_within(Path(settings.MEDIA_PROCESSING_WORKSPACE_ROOT), request.workspace)

    async def create_job(self, request: ProcessingJobCreateRequest) -> ProcessingJobResponse:
        existing = self.repository.job_by_idempotency_key(request.idempotency_key)
        if existing is not None and existing.error_code != "BROKER_DISPATCH_FAILED":
            return job_response(existing)
        try:
            self._validate_paths(request)
        except (UnsafeMediaSourceError, OSError) as exc:
            raise ProcessingConflictError(str(exc)) from exc
        queue, task_name, domain_type = self._route(request)
        job = existing
        if job is None:
            job = self.repository.add_job(
                TranscodingJob(
                    stream_id=request.stream_id,
                    recording_id=request.recording_id,
                    job_type=domain_type,
                    queue=queue,
                    capability=request.job_type,
                    input_source=request.input_url,
                    output_prefix=request.output_prefix,
                    renditions=list(request.renditions),
                    status=TranscodingJobStatus.QUEUED,
                    attempt=0,
                    max_attempts=request.max_attempts,
                    progress={"phase": "queued"},
                    idempotency_key=request.idempotency_key,
                )
            )
            try:
                # The durable job must be visible before a worker can claim the broker message.
                self.repository.db.commit()
            except IntegrityError as exc:
                self.repository.db.rollback()
                concurrent = self.repository.job_by_idempotency_key(request.idempotency_key)
                if concurrent is not None:
                    return job_response(concurrent)
                raise ProcessingConflictError("processing job could not be persisted") from exc
        else:
            job.status = TranscodingJobStatus.QUEUED
            job.error_code = None
            job.error_detail = None
            job.progress = {"phase": "queued"}
            self.repository.db.commit()
        try:
            await self.dispatcher.enqueue(
                task_name=task_name,
                queue=queue,
                payload=self._task_payload(request, job),
                task_id=request.idempotency_key,
            )
        except Exception as exc:
            job.status = TranscodingJobStatus.RETRYING
            job.error_code = "BROKER_DISPATCH_FAILED"
            job.error_detail = "Processing broker did not accept the task"
            self.repository.db.commit()
            raise ProcessingConflictError("processing job could not be enqueued") from exc
        return job_response(job)

    async def get_job(self, job_id: UUID) -> ProcessingJobResponse:
        job = self.repository.job(job_id)
        if job is None:
            raise ProcessingNotFoundError("processing job was not found")
        telemetry = await self._json(f"gntv:processing:progress:{job_id}")
        return job_response(job, telemetry.get("metrics") if telemetry else None)

    async def list_jobs(self, *, limit: int, offset: int) -> ProcessingJobPage:
        jobs, total = self.repository.jobs(limit=limit, offset=offset)
        return ProcessingJobPage(items=[job_response(job) for job in jobs], total=total)

    async def cancel_job(self, job_id: UUID) -> ProcessingJobCancelResponse:
        job = self.repository.job(job_id)
        if job is None:
            raise ProcessingNotFoundError("processing job was not found")
        try:
            self.repository.cancel_job(job)
        except ValueError as exc:
            raise ProcessingConflictError(str(exc)) from exc
        await self.dispatcher.cancel(job.idempotency_key)
        terminated_at = datetime.now(UTC)
        job.completed_at = terminated_at
        self.repository.db.commit()
        return ProcessingJobCancelResponse(
            job_id=job.id, status="CANCELLED", terminated_at=terminated_at
        )

    async def _json(self, key: str) -> dict[str, Any] | None:
        try:
            value = await self.redis.get(key)
        except Exception:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        if not isinstance(value, str):
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _keys(self, pattern: str) -> list[str]:
        keys: list[str] = []
        try:
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key.decode() if isinstance(key, bytes) else str(key))
        except Exception:
            return []
        return keys

    async def workers(self) -> list[WorkerStatusResponse]:
        workers: list[WorkerStatusResponse] = []
        for key in await self._keys("gntv:processing:worker:*"):
            item = await self._json(key)
            if not item:
                continue
            try:
                observed = datetime.fromisoformat(
                    str(item["observed_at"]).replace("Z", "+00:00")
                )
                hardware_data = item.get("hardware", {})
                workers.append(
                    WorkerStatusResponse(
                        worker_id=str(item["worker_id"]),
                        hostname=item.get("hostname"),
                        queue=str(item["queue"]),
                        status=str(item.get("status", "IDLE")).upper(),
                        healthy=bool(item.get("healthy", False)),
                        last_heartbeat=observed,
                        hardware=WorkerHardware.model_validate(hardware_data),
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError):
                # Heartbeats are ephemeral and may be observed between writes. A
                # corrupt cache record must not make the operations API unavailable.
                continue
        return sorted(workers, key=lambda worker: worker.worker_id)

    async def queues(self) -> QueueTelemetryResponse:
        counts = self.repository.queue_counts()
        workers = await self.workers()
        queues: dict[str, QueueStatus] = {}
        for queue in APPROVED_QUEUES:
            queue_counts = counts.get(queue, {})
            queues[queue] = QueueStatus(
                messages_queued=queue_counts.get("queued", 0),
                messages_leased=queue_counts.get("leased", 0),
                messages_running=queue_counts.get("running", 0),
                messages_retrying=queue_counts.get("retrying", 0),
                active_workers=sum(worker.healthy and worker.queue == queue for worker in workers),
            )
        try:
            online = bool(await self.redis.ping())
        except Exception:
            online = False
        return QueueTelemetryResponse(
            broker="Redis (Online)" if online else "Redis (Unavailable)",
            queues=queues,
        )

    def manifests(self, *, limit: int, offset: int) -> ManifestPage:
        items, total = self.repository.manifests(limit=limit, offset=offset)
        return ManifestPage(items=[self._manifest(item) for item in items], total=total)

    def manifest(self, manifest_id: UUID) -> ManifestStatusResponse:
        item = self.repository.manifest(manifest_id)
        if item is None:
            raise ProcessingNotFoundError("manifest was not found")
        return self._manifest(item)

    @staticmethod
    def _manifest(item: Manifest) -> ManifestStatusResponse:
        return ManifestStatusResponse(
            manifest_id=item.id,
            stream_id=item.stream_id,
            recording_id=item.recording_id,
            format=item.format,
            kind=item.kind,
            status=item.status,
            manifest_path=item.oss_object_key,
            generation=item.generation,
            renditions=item.renditions,
            published_at=item.published_at,
        )

    def validate_manifest(self, manifest_url: str) -> ManifestValidationResponse:
        try:
            path = resolve_within(Path(settings.MEDIA_PROCESSING_OUTPUT_ROOT), manifest_url)
            if not path.is_file():
                raise ManifestValidationError("manifest file was not found")
            document = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".m3u8":
                validate_hls_master(document, path.parent)
                manifest_format = ManifestFormat.HLS
                conformance = "HLS H.264 ABR Ladder Conforming"
            elif path.suffix.lower() == ".mpd":
                validate_dash_mpd(document, path.parent)
                manifest_format = ManifestFormat.DASH
                conformance = "MPEG-DASH ABR Manifest Conforming"
            else:
                raise ManifestValidationError("only .m3u8 and .mpd manifests are supported")
            return ManifestValidationResponse(
                valid=True,
                format=manifest_format,
                conformance=conformance,
                validations={
                    "structure": "PASSED",
                    "renditions": "PASSED",
                    "referenced_objects": "PASSED",
                    "warnings": [],
                },
            )
        except (ManifestValidationError, UnsafeMediaSourceError, OSError) as exc:
            return ManifestValidationResponse(
                valid=False,
                format=None,
                conformance="NON_CONFORMING",
                validations={"warnings": [str(exc)]},
            )

    def thumbnails(self, *, limit: int, offset: int) -> ThumbnailPage:
        items, total = self.repository.thumbnails(limit=limit, offset=offset)
        return ThumbnailPage(items=[self._thumbnail(item) for item in items], total=total)

    def thumbnail(self, thumbnail_id: UUID) -> ThumbnailStatusResponse:
        item = self.repository.thumbnail(thumbnail_id)
        if item is None:
            raise ProcessingNotFoundError("thumbnail was not found")
        return self._thumbnail(item)

    @staticmethod
    def _thumbnail(item: Thumbnail) -> ThumbnailStatusResponse:
        return ThumbnailStatusResponse(
            thumbnail_id=item.id,
            stream_id=item.stream_id,
            recording_id=item.recording_id,
            media_file_id=item.media_file_id,
            kind=item.kind,
            timestamp_ms=item.timestamp_ms,
            width=item.width,
            height=item.height,
            status=item.status,
            asset_path=item.oss_object_key,
        )

    async def metrics(self, job_id: UUID | None = None) -> MetricsPage:
        keys = (
            [f"gntv:processing:metrics:{job_id}", f"gntv:processing:manifest:{job_id}"]
            if job_id
            else await self._keys("gntv:processing:metrics:*")
            + await self._keys("gntv:processing:manifest:*")
        )
        combined: dict[UUID, dict[str, Any]] = {}
        for key in keys:
            item = await self._json(key)
            if not item or "job_id" not in item:
                continue
            try:
                identifier = UUID(str(item["job_id"]))
            except (TypeError, ValueError):
                continue
            combined.setdefault(identifier, {}).update(item)
        items: list[ProcessingMetricsResponse] = []
        for identifier, values in combined.items():
            try:
                items.append(
                    ProcessingMetricsResponse.model_validate(
                        {"job_id": identifier, **values}
                    )
                )
            except ValidationError:
                continue
        items.sort(key=lambda item: item.observed_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return MetricsPage(items=items, total=len(items))

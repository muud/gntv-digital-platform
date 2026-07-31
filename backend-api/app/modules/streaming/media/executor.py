"""Durable job-state wrapper around the media pipeline."""

from random import Random

from app.modules.streaming.media.contracts import (
    ManifestTaskPayload,
    ThumbnailTaskPayload,
    TranscodeTaskPayload,
)
from app.modules.streaming.media.pipeline import MediaPipeline
from app.modules.streaming.media.probe import ProbeValidationError
from app.modules.streaming.media.process import FFmpegExecutionError, MediaProcessTimeout
from app.modules.streaming.media.repository import MediaJobRepository


class RetryableMediaJobError(RuntimeError):
    pass


def retry_delay(attempt: int, *, random: Random | None = None) -> int:
    generator = random or Random()
    jitter = int(generator.randint(0, 5))
    return int(min((2 ** max(attempt, 0)) * 5, 300) + jitter)


class MediaTaskExecutor:
    def __init__(
        self,
        repository: MediaJobRepository,
        pipeline: MediaPipeline,
        worker_id: str,
        *,
        lease_seconds: int = 30,
    ) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    async def transcode(
        self,
        payload: TranscodeTaskPayload,
        *,
        accelerated: bool,
    ) -> dict[str, object]:
        queue = "transcode-accelerated" if accelerated else "transcode-cpu"
        job = self.repository.claim(
            payload.job_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        try:
            self.repository.phase(job, "probing", queue=queue)
            self.repository.phase(job, "processing", queue=queue)
            result = await self.pipeline.transcode(
                payload,
                encoder="accelerated" if accelerated else "cpu",
                queue=queue,
            )
            self.repository.succeed(job, queue=queue, workspace=result["workspace"])
            return result
        except (MediaProcessTimeout, OSError) as exc:
            if self._recoverable(job, exc):
                raise RetryableMediaJobError(str(exc)) from exc
            raise
        except (FFmpegExecutionError, ProbeValidationError, ValueError) as exc:
            self.repository.fail(job, code="media_validation_failed", detail=str(exc))
            self.pipeline.quarantine(payload.job_id)
            raise

    async def manifest(self, payload: ManifestTaskPayload) -> dict[str, object]:
        job = self.repository.claim(
            payload.job_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        try:
            self.repository.phase(job, "validating", queue="manifest")
            result = await self.pipeline.package_and_publish(payload)
            self.repository.succeed(job, queue="manifest", **result)
            return result
        except (OSError, TimeoutError) as exc:
            if self._recoverable(job, exc):
                raise RetryableMediaJobError(str(exc)) from exc
            raise
        except ValueError as exc:
            self.repository.fail(job, code="manifest_validation_failed", detail=str(exc))
            raise

    async def thumbnail(self, payload: ThumbnailTaskPayload) -> dict[str, object]:
        job = self.repository.claim(
            payload.job_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        try:
            self.repository.phase(job, "processing", queue="thumbnail")
            result = await self.pipeline.thumbnails(payload)
            self.repository.succeed(job, queue="thumbnail", **result)
            return result
        except (MediaProcessTimeout, OSError) as exc:
            if self._recoverable(job, exc):
                raise RetryableMediaJobError(str(exc)) from exc
            raise
        except (FFmpegExecutionError, ValueError) as exc:
            self.repository.fail(job, code="thumbnail_failed", detail=str(exc))
            raise

    def _recoverable(self, job: object, error: Exception) -> bool:
        from app.modules.streaming.models import TranscodingJob

        if not isinstance(job, TranscodingJob):
            raise TypeError("invalid processing job")
        if job.attempt < job.max_attempts:
            self.repository.retry(job, code="temporary_media_failure", detail=str(error))
            return True
        else:
            self.repository.fail(job, code="media_attempts_exhausted", detail=str(error))
            return False


__all__ = ["MediaTaskExecutor", "RetryableMediaJobError", "retry_delay"]

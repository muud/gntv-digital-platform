"""Durable processing-job lifecycle repository."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.streaming.models import TranscodingJob, TranscodingJobStatus


class MediaJobConflictError(RuntimeError):
    pass


class MediaJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, job_id: UUID, *, lock: bool = False) -> TranscodingJob | None:
        query = select(TranscodingJob).where(TranscodingJob.id == job_id)
        if lock:
            query = query.with_for_update()
        return self.db.execute(query).scalar_one_or_none()

    def claim(self, job_id: UUID, *, worker_id: str, lease_seconds: int) -> TranscodingJob:
        job = self.get(job_id, lock=True)
        if job is None:
            raise LookupError("processing job was not found")
        if job.status not in {TranscodingJobStatus.QUEUED, TranscodingJobStatus.RETRYING}:
            raise MediaJobConflictError("processing job is not claimable")
        if job.attempt >= job.max_attempts:
            raise MediaJobConflictError("processing job exhausted its attempts")
        now = datetime.now(UTC)
        job.status = TranscodingJobStatus.LEASED
        job.worker_id = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.attempt += 1
        job.lock_version += 1
        self.db.commit()
        return job

    def phase(self, job: TranscodingJob, phase: str, **progress: object) -> None:
        job.status = TranscodingJobStatus.RUNNING
        job.progress = {"phase": phase, **progress}
        job.started_at = job.started_at or datetime.now(UTC)
        job.lock_version += 1
        self.db.commit()

    def succeed(self, job: TranscodingJob, **progress: object) -> None:
        job.status = TranscodingJobStatus.SUCCEEDED
        job.progress = {"phase": "completed", **progress}
        job.completed_at = datetime.now(UTC)
        job.lease_expires_at = None
        job.error_code = None
        job.error_detail = None
        job.lock_version += 1
        self.db.commit()

    def retry(self, job: TranscodingJob, *, code: str, detail: str) -> None:
        job.status = TranscodingJobStatus.RETRYING
        job.error_code = code
        job.error_detail = detail[:1000]
        job.lease_expires_at = None
        job.lock_version += 1
        self.db.commit()

    def fail(self, job: TranscodingJob, *, code: str, detail: str) -> None:
        job.status = TranscodingJobStatus.FAILED
        job.error_code = code
        job.error_detail = detail[:1000]
        job.completed_at = datetime.now(UTC)
        job.lease_expires_at = None
        job.lock_version += 1
        self.db.commit()


__all__ = ["MediaJobConflictError", "MediaJobRepository"]

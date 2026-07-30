"""Database queries owned by the processing operations boundary."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.streaming.models import Manifest, Thumbnail, TranscodingJob, TranscodingJobStatus


class ProcessingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def job(self, job_id: UUID) -> TranscodingJob | None:
        return self.db.get(TranscodingJob, job_id)

    def job_by_idempotency_key(self, key: str) -> TranscodingJob | None:
        return self.db.execute(
            select(TranscodingJob).where(TranscodingJob.idempotency_key == key)
        ).scalar_one_or_none()

    def jobs(self, *, limit: int, offset: int) -> tuple[list[TranscodingJob], int]:
        query = select(TranscodingJob).order_by(TranscodingJob.created_at.desc())
        items = list(self.db.execute(query.limit(limit).offset(offset)).scalars())
        total = self.db.scalar(select(func.count()).select_from(TranscodingJob)) or 0
        return items, total

    def add_job(self, job: TranscodingJob) -> TranscodingJob:
        self.db.add(job)
        self.db.flush()
        return job

    def queue_counts(self) -> dict[str, dict[str, int]]:
        rows = self.db.execute(
            select(TranscodingJob.queue, TranscodingJob.status, func.count())
            .group_by(TranscodingJob.queue, TranscodingJob.status)
        )
        result: dict[str, dict[str, int]] = {}
        for queue, job_status, count in rows:
            result.setdefault(queue, {})[job_status.value] = count
        return result

    def cancel_job(self, job: TranscodingJob) -> None:
        if job.status in {
            TranscodingJobStatus.SUCCEEDED,
            TranscodingJobStatus.FAILED,
            TranscodingJobStatus.CANCELLED,
        }:
            raise ValueError("processing job is already terminal")
        job.status = TranscodingJobStatus.CANCELLED
        job.lease_expires_at = None
        job.lock_version += 1
        self.db.flush()

    def manifests(self, *, limit: int, offset: int) -> tuple[list[Manifest], int]:
        query = select(Manifest).order_by(Manifest.created_at.desc())
        items = list(self.db.execute(query.limit(limit).offset(offset)).scalars())
        total = self.db.scalar(select(func.count()).select_from(Manifest)) or 0
        return items, total

    def manifest(self, manifest_id: UUID) -> Manifest | None:
        return self.db.get(Manifest, manifest_id)

    def thumbnails(self, *, limit: int, offset: int) -> tuple[list[Thumbnail], int]:
        query = select(Thumbnail).order_by(Thumbnail.created_at.desc())
        items = list(self.db.execute(query.limit(limit).offset(offset)).scalars())
        total = self.db.scalar(select(func.count()).select_from(Thumbnail)) or 0
        return items, total

    def thumbnail(self, thumbnail_id: UUID) -> Thumbnail | None:
        return self.db.get(Thumbnail, thumbnail_id)

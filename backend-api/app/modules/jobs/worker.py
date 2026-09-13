"""Callable durable worker service; importing this module starts no loops."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.events.security import sanitize_payload
from app.modules.jobs.models import (
    DurableJob,
    JobAuditAction,
    JobStatus,
    WorkerRecord,
    WorkerStatus,
)
from app.modules.jobs.queue import DatabaseJobQueue
from app.modules.jobs.registry import NonRetryableJobError, default_job_registry
from app.modules.jobs.repository import JobRepository


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkerService:
    """Claims and executes a bounded batch of registered internal jobs."""

    def __init__(
        self,
        db: Session,
        worker_id: str,
        *,
        queues: list[str] | None = None,
        concurrency: int = 1,
        lease_duration_seconds: int = 60,
        version: str = "8.3",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.db = db
        self.worker_id = worker_id
        self.queues = queues or ["default"]
        self.concurrency = max(1, concurrency)
        self.lease_duration_seconds = max(1, lease_duration_seconds)
        self.version = version
        self.metadata = sanitize_payload(metadata) if metadata else None
        self.queue = DatabaseJobQueue()

    def register(self) -> WorkerRecord:
        record = self.db.get(WorkerRecord, self.worker_id)
        now = utc_now()
        if record is None:
            record = WorkerRecord(
                worker_id=self.worker_id,
                hostname=None,
                queues_json=self.queues,
                concurrency=self.concurrency,
                status=WorkerStatus.ONLINE,
                started_at=now,
                last_heartbeat_at=now,
                version=self.version,
                metadata_json=self.metadata,
            )
            self.db.add(record)
        else:
            record.queues_json = self.queues
            record.concurrency = self.concurrency
            record.status = WorkerStatus.ONLINE
            record.last_heartbeat_at = now
            record.version = self.version
            record.metadata_json = self.metadata
        self.db.flush()
        JobRepository.create_audit_log(
            self.db,
            action=JobAuditAction.WORKER_STARTED,
            worker_id=self.worker_id,
            metadata={"queues": self.queues, "concurrency": self.concurrency, "version": self.version},
        )
        return record

    def _record(self) -> WorkerRecord:
        return self.db.get(WorkerRecord, self.worker_id) or self.register()

    def heartbeat(self) -> WorkerRecord:
        record = self._record()
        record.last_heartbeat_at = utc_now()
        active = self.db.scalar(
            select(DurableJob.id).where(
                DurableJob.worker_id == self.worker_id,
                DurableJob.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
            ).limit(1)
        )
        record.active_job_count = 1 if active else 0
        JobRepository.create_audit_log(
            self.db, action=JobAuditAction.WORKER_HEARTBEAT, worker_id=self.worker_id
        )
        self.db.flush()
        return record

    def process_once(self) -> list[DurableJob]:
        record = self._record()
        if record.status != WorkerStatus.ONLINE:
            return []
        claimed = self.queue.claim(
            self.db,
            worker_id=self.worker_id,
            queue_names=self.queues,
            batch_size=self.concurrency,
            lease_duration_seconds=self.lease_duration_seconds,
        )
        record.active_job_count = len(claimed)
        for job in claimed:
            job.status = JobStatus.RUNNING
            JobRepository.create_audit_log(
                self.db,
                action=JobAuditAction.JOB_STARTED,
                job_id=job.id,
                worker_id=self.worker_id,
            )
            try:
                if job.cancel_requested:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = utc_now()
                    continue
                result = default_job_registry.execute(self.db, job)
                self.queue.acknowledge(
                    self.db, job_id=job.id, worker_id=self.worker_id, result=result
                )
                record.completed_job_count += 1
            except NonRetryableJobError as exc:
                self.queue.fail(
                    self.db,
                    job_id=job.id,
                    worker_id=self.worker_id,
                    error_message=str(exc),
                    is_retryable=False,
                )
                record.failed_job_count += 1
            except Exception as exc:
                self.queue.fail(
                    self.db,
                    job_id=job.id,
                    worker_id=self.worker_id,
                    error_message=str(exc),
                    is_retryable=True,
                )
                record.failed_job_count += 1
        record.active_job_count = 0
        record.last_heartbeat_at = utc_now()
        self.db.flush()
        return claimed

    def drain(self) -> WorkerRecord:
        record = self._record()
        record.status = WorkerStatus.DRAINING
        JobRepository.create_audit_log(
            self.db, action=JobAuditAction.WORKER_DRAINING, worker_id=self.worker_id
        )
        self.db.flush()
        return record

    def shutdown(self) -> WorkerRecord:
        record = self._record()
        claimed = self.db.scalars(
            select(DurableJob).where(
                DurableJob.worker_id == self.worker_id,
                DurableJob.status == JobStatus.CLAIMED,
            )
        )
        for job in claimed:
            self.queue.release(self.db, job_id=job.id, worker_id=self.worker_id)
        record.status = WorkerStatus.OFFLINE
        record.active_job_count = 0
        record.last_heartbeat_at = utc_now()
        JobRepository.create_audit_log(
            self.db, action=JobAuditAction.WORKER_OFFLINE, worker_id=self.worker_id
        )
        self.db.flush()
        return record

    @staticmethod
    def effective_status(record: WorkerRecord, unhealthy_after_seconds: int = 60) -> WorkerStatus:
        heartbeat = record.last_heartbeat_at.replace(
            tzinfo=record.last_heartbeat_at.tzinfo or UTC
        )
        if record.status == WorkerStatus.ONLINE and heartbeat < utc_now() - timedelta(
            seconds=unhealthy_after_seconds
        ):
            return WorkerStatus.UNHEALTHY
        return record.status

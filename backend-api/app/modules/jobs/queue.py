"""Provider-neutral durable job queue abstraction and database-backed implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.events.security import sanitize_payload
from app.modules.jobs.models import (
    JobAttempt,
    JobAttemptStatus,
    JobAuditAction,
    JobDeadLetter,
    JobDeadLetterStatus,
    JobStatus,
    DurableJob,
)
from app.modules.jobs.registry import default_job_registry

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


def sanitize_error(message: str) -> str:
    """Bound and redact common inline credential forms before persistence."""
    bounded = str(message).replace("\n", " ")[:500]
    return re.sub(
        r"(?i)(password|secret|token|authorization|api[_-]?key)\s*[=:]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        bounded,
    )


class JobQueue(ABC):
    """Abstract interface for durable asynchronous job queue."""

    @abstractmethod
    def enqueue(
        self,
        db: Session,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        queue_name: str = "default",
        priority: int = 0,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        scheduled_for: datetime | None = None,
        delay_seconds: int = 0,
        max_retries: int = 3,
        retry_delay: int = 5,
        timeout_seconds: int = 60,
        actor_user_id: int | None = None,
    ) -> DurableJob:
        """Enqueue a background job."""
        pass

    @abstractmethod
    def claim(
        self,
        db: Session,
        *,
        worker_id: str,
        queue_names: list[str] | None = None,
        batch_size: int = 1,
        lease_duration_seconds: int = 60,
    ) -> list[DurableJob]:
        """Atomically claim eligible jobs for worker execution."""
        pass

    @abstractmethod
    def acknowledge(
        self,
        db: Session,
        *,
        job_id: UUID,
        worker_id: str,
        result: dict[str, Any] | None = None,
    ) -> DurableJob:
        """Acknowledge successful completion of a job."""
        pass

    @abstractmethod
    def fail(
        self,
        db: Session,
        *,
        job_id: UUID,
        worker_id: str,
        error_message: str,
        is_retryable: bool = True,
    ) -> DurableJob:
        """Mark a job as failed, scheduling retry or dead-lettering."""
        pass

    @abstractmethod
    def heartbeat(
        self,
        db: Session,
        *,
        job_id: UUID,
        worker_id: str,
        extension_seconds: int = 60,
    ) -> DurableJob:
        """Extend lease duration for an active job."""
        pass

    @abstractmethod
    def cancel(
        self,
        db: Session,
        *,
        job_id: UUID,
        reason: str,
        actor_user_id: int | None = None,
    ) -> DurableJob:
        """Cancel a pending, scheduled, or running job."""
        pass

    @abstractmethod
    def retry(
        self, db: Session, *, job_id: UUID, actor_user_id: int | None = None
    ) -> DurableJob:
        """Requeue a terminal job through an audited, idempotent transition."""
        pass

    @abstractmethod
    def release(self, db: Session, *, job_id: UUID, worker_id: str) -> DurableJob:
        """Release a claimed job during graceful worker shutdown."""
        pass

    @abstractmethod
    def dead_letter(
        self, db: Session, *, job_id: UUID, worker_id: str, reason: str
    ) -> DurableJob:
        """Move a job to terminal dead-letter state."""
        pass

    @abstractmethod
    def recover_stale_leases(
        self,
        db: Session,
        *,
        stale_threshold_seconds: int = 0,
    ) -> list[DurableJob]:
        """Recover abandoned jobs whose worker lease has expired."""
        pass


class DatabaseJobQueue(JobQueue):
    """PostgreSQL and SQLite compatible database-backed durable queue."""

    def enqueue(
        self,
        db: Session,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        queue_name: str = "default",
        priority: int = 0,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        scheduled_for: datetime | None = None,
        delay_seconds: int = 0,
        max_retries: int = 3,
        retry_delay: int = 5,
        timeout_seconds: int = 60,
        actor_user_id: int | None = None,
    ) -> DurableJob:
        now = utc_now()

        # A key is permanent for a job type: terminal jobs must not be duplicated either.
        if idempotency_key:
            stmt = select(DurableJob).where(
                DurableJob.job_type == job_type,
                DurableJob.idempotency_key == idempotency_key,
            )
            existing = db.scalars(stmt).first()
            if existing is not None:
                return existing

        # Validate job type allowlist
        if not default_job_registry.is_registered(job_type):
            raise ValueError(f"Job type '{job_type}' is not registered in safe allowlist")

        # Sanitize payload
        clean_payload = sanitize_payload(payload) if payload else None

        # Determine initial availability and status
        available_at = now + timedelta(seconds=delay_seconds)
        if scheduled_for and scheduled_for > now:
            available_at = scheduled_for
            status = JobStatus.SCHEDULED
        else:
            status = JobStatus.QUEUED

        corr_id = correlation_id or uuid4().hex

        job = DurableJob(
            job_type=job_type,
            queue_name=queue_name,
            priority=priority,
            status=status,
            payload_json=clean_payload,
            idempotency_key=idempotency_key,
            correlation_id=corr_id,
            causation_id=causation_id,
            scheduled_for=scheduled_for,
            available_at=available_at,
            created_at=now,
            retry_count=0,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout_seconds=timeout_seconds,
        )
        db.add(job)
        db.flush()

        # Record audit log
        from app.modules.jobs.repository import JobRepository
        JobRepository.create_audit_log(
            db,
            action=JobAuditAction.JOB_ENQUEUED,
            job_id=job.id,
            actor_user_id=actor_user_id,
            metadata={
                "job_type": job_type,
                "queue_name": queue_name,
                "priority": priority,
                "idempotency_key": idempotency_key,
                "available_at": available_at.isoformat(),
            },
        )
        return job

    def claim(
        self,
        db: Session,
        *,
        worker_id: str,
        queue_names: list[str] | None = None,
        batch_size: int = 1,
        lease_duration_seconds: int = 60,
    ) -> list[DurableJob]:
        now = utc_now()
        queues = queue_names or ["default"]

        # Build candidate query
        stmt = (
            select(DurableJob)
            .where(
                DurableJob.queue_name.in_(queues),
                DurableJob.status.in_([JobStatus.QUEUED, JobStatus.SCHEDULED, JobStatus.WAITING_RETRY]),
                DurableJob.available_at <= now,
            )
            .order_by(DurableJob.priority.desc(), DurableJob.available_at.asc())
            .limit(batch_size)
        )

        # Use with_for_update(skip_locked=True) if supported by database dialect
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        candidates = db.scalars(stmt).all()
        claimed_jobs: list[DurableJob] = []

        lease_expiration = now + timedelta(seconds=lease_duration_seconds)
        from app.modules.jobs.repository import JobRepository

        for job in candidates:
            # Double check in case of concurrency
            if job.status not in (JobStatus.QUEUED, JobStatus.SCHEDULED, JobStatus.WAITING_RETRY):
                continue

            job.status = JobStatus.CLAIMED
            job.worker_id = worker_id
            job.lease_expires_at = lease_expiration
            job.last_heartbeat_at = now
            if not job.started_at:
                job.started_at = now

            # Create attempt record
            previous_attempt = JobRepository.get_latest_attempt(db, job.id)
            attempt = JobAttempt(
                job_id=job.id,
                attempt_number=(previous_attempt.attempt_number + 1 if previous_attempt else 1),
                worker_id=worker_id,
                started_at=now,
                status=JobAttemptStatus.RUNNING,
            )
            db.add(attempt)
            db.flush()

            JobRepository.create_audit_log(
                db,
                action=JobAuditAction.JOB_CLAIMED,
                job_id=job.id,
                worker_id=worker_id,
                metadata={
                    "attempt": attempt.attempt_number,
                    "lease_expires_at": lease_expiration.isoformat(),
                },
            )
            claimed_jobs.append(job)

        return claimed_jobs

    def acknowledge(
        self,
        db: Session,
        *,
        job_id: UUID,
        worker_id: str,
        result: dict[str, Any] | None = None,
    ) -> DurableJob:
        job = db.get(DurableJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        if job.worker_id != worker_id or job.status not in (JobStatus.CLAIMED, JobStatus.RUNNING):
            raise ValueError(f"Worker '{worker_id}' does not own active job '{job_id}'")

        now = utc_now()
        clean_result = sanitize_payload(result) if result else None

        job.status = JobStatus.SUCCEEDED
        job.completed_at = now
        job.result_json = clean_result
        job.lease_expires_at = None

        # Update latest attempt
        from app.modules.jobs.repository import JobRepository
        latest_attempt = JobRepository.get_latest_attempt(db, job_id)
        if latest_attempt and latest_attempt.status == JobAttemptStatus.RUNNING:
            latest_attempt.status = JobAttemptStatus.SUCCEEDED
            latest_attempt.completed_at = now
            latest_attempt.result_json = clean_result

        JobRepository.create_audit_log(
            db,
            action=JobAuditAction.JOB_SUCCEEDED,
            job_id=job.id,
            worker_id=worker_id,
            metadata={"status": "succeeded"},
        )
        db.flush()
        return job

    def fail(
        self,
        db: Session,
        *,
        job_id: UUID,
        worker_id: str,
        error_message: str,
        is_retryable: bool = True,
    ) -> DurableJob:
        job = db.get(DurableJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        if job.worker_id != worker_id or job.status not in (JobStatus.CLAIMED, JobStatus.RUNNING):
            raise ValueError(f"Worker '{worker_id}' does not own active job '{job_id}'")

        now = utc_now()
        error_message = sanitize_error(error_message)
        safe_error = {"message": error_message, "occurred_at": now.isoformat()}
        job.failed_at = now
        job.error_details_json = safe_error
        job.lease_expires_at = None

        # Update attempt
        from app.modules.jobs.repository import JobRepository
        latest_attempt = JobRepository.get_latest_attempt(db, job_id)
        if latest_attempt and latest_attempt.status == JobAttemptStatus.RUNNING:
            latest_attempt.status = JobAttemptStatus.FAILED
            latest_attempt.completed_at = now
            latest_attempt.error_message = error_message

        JobRepository.create_audit_log(
            db,
            action=JobAuditAction.JOB_FAILED,
            job_id=job.id,
            worker_id=worker_id,
            metadata={"retryable": is_retryable, "error": error_message[:200]},
        )

        # Check retry policy
        should_retry = is_retryable and job.retry_count < job.max_retries

        if should_retry:
            job.retry_count += 1
            # Exponential backoff with jitter ceiling (max 300s)
            backoff = min(job.retry_delay * (2 ** (job.retry_count - 1)), 300)
            job.available_at = now + timedelta(seconds=backoff)
            job.status = JobStatus.WAITING_RETRY
            job.worker_id = None

            JobRepository.create_audit_log(
                db,
                action=JobAuditAction.JOB_RETRY_SCHEDULED,
                job_id=job.id,
                worker_id=worker_id,
                metadata={
                    "retry_count": job.retry_count,
                    "max_retries": job.max_retries,
                    "retry_delay_seconds": backoff,
                    "available_at": job.available_at.isoformat(),
                    "error": error_message[:200],
                },
            )
        else:
            # Terminal dead-letter
            job.status = JobStatus.DEAD_LETTERED
            dlq = JobDeadLetter(
                job_id=job.id,
                status=JobDeadLetterStatus.OPEN,
                reason=f"Exceeded max retries ({job.max_retries})" if is_retryable else f"Non-retryable failure: {error_message[:200]}",
                error_details_json=safe_error,
                retry_count=job.retry_count,
                created_at=now,
            )
            db.add(dlq)
            JobRepository.create_audit_log(
                db,
                action=JobAuditAction.JOB_DEAD_LETTERED,
                job_id=job.id,
                worker_id=worker_id,
                metadata={
                    "reason": dlq.reason,
                    "retry_count": job.retry_count,
                    "is_retryable": is_retryable,
                },
            )

        db.flush()
        return job

    def heartbeat(
        self,
        db: Session,
        *,
        job_id: UUID,
        worker_id: str,
        extension_seconds: int = 60,
    ) -> DurableJob:
        job = db.get(DurableJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        if job.worker_id != worker_id:
            raise ValueError(f"Worker '{worker_id}' does not own lease on job '{job_id}'")

        now = utc_now()
        job.last_heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=extension_seconds)
        db.flush()
        return job

    def cancel(
        self,
        db: Session,
        *,
        job_id: UUID,
        reason: str,
        actor_user_id: int | None = None,
    ) -> DurableJob:
        job = db.get(DurableJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")

        # Can only cancel queued, scheduled, claimed, running, or waiting_retry jobs
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD_LETTERED):
            raise ValueError(f"Cannot cancel job in terminal status '{job.status.value}'")

        now = utc_now()
        running = job.status in (JobStatus.CLAIMED, JobStatus.RUNNING)
        job.cancel_requested = running
        if not running:
            job.status = JobStatus.CANCELLED
            job.completed_at = now
            job.lease_expires_at = None
        job.error_details_json = {"cancellation_reason": reason[:300], "cancel_requested_at": now.isoformat(), "cooperative": running}

        from app.modules.jobs.repository import JobRepository
        latest_attempt = JobRepository.get_latest_attempt(db, job_id)
        if latest_attempt and latest_attempt.status == JobAttemptStatus.RUNNING and not running:
            latest_attempt.status = JobAttemptStatus.CANCELLED
            latest_attempt.completed_at = now
            latest_attempt.error_message = f"Cancelled by operator: {reason[:200]}"

        JobRepository.create_audit_log(
            db,
            action=JobAuditAction.JOB_CANCELLED,
            job_id=job.id,
            actor_user_id=actor_user_id,
            metadata={"reason": reason[:300]},
        )
        db.flush()
        return job

    def retry(
        self, db: Session, *, job_id: UUID, actor_user_id: int | None = None
    ) -> DurableJob:
        job = db.get(DurableJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        if job.status not in (JobStatus.DEAD_LETTERED, JobStatus.FAILED, JobStatus.CANCELLED):
            raise ValueError(f"Cannot retry job in status '{job.status.value}'")
        if job.dead_letter is not None:
            job.dead_letter.status = JobDeadLetterStatus.RETRIED
            job.dead_letter.retry_count += 1
        job.status = JobStatus.QUEUED
        job.retry_count = 0
        job.available_at = utc_now()
        job.worker_id = None
        job.lease_expires_at = None
        job.cancel_requested = False
        job.error_details_json = None
        from app.modules.jobs.repository import JobRepository
        JobRepository.create_audit_log(db, action=JobAuditAction.JOB_RETRIED, job_id=job.id, actor_user_id=actor_user_id)
        db.flush()
        return job

    def release(self, db: Session, *, job_id: UUID, worker_id: str) -> DurableJob:
        job = db.get(DurableJob, job_id)
        if job is None or job.worker_id != worker_id:
            raise ValueError("Worker does not own this job")
        if job.status != JobStatus.CLAIMED:
            raise ValueError("Only claimed jobs may be released")
        job.status = JobStatus.QUEUED
        job.worker_id = None
        job.lease_expires_at = None
        job.available_at = utc_now()
        from app.modules.jobs.repository import JobRepository
        attempt = JobRepository.get_latest_attempt(db, job.id)
        if attempt and attempt.status == JobAttemptStatus.RUNNING:
            attempt.status = JobAttemptStatus.CANCELLED
            attempt.completed_at = utc_now()
            attempt.error_message = "Lease released during graceful shutdown"
        db.flush()
        return job

    def dead_letter(
        self, db: Session, *, job_id: UUID, worker_id: str, reason: str
    ) -> DurableJob:
        return self.fail(
            db,
            job_id=job_id,
            worker_id=worker_id,
            error_message=reason,
            is_retryable=False,
        )

    def recover_stale_leases(
        self,
        db: Session,
        *,
        stale_threshold_seconds: int = 0,
    ) -> list[DurableJob]:
        now = utc_now()
        cutoff = now - timedelta(seconds=stale_threshold_seconds)

        # Look for jobs in CLAIMED or RUNNING whose lease has expired
        stmt = (
            select(DurableJob)
            .where(
                DurableJob.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
                DurableJob.lease_expires_at <= cutoff,
            )
        )
        stale_jobs = db.scalars(stmt).all()
        recovered: list[DurableJob] = []

        from app.modules.jobs.repository import JobRepository

        for job in stale_jobs:
            worker_id = job.worker_id or "unknown"
            # Close stale running attempt
            latest_attempt = JobRepository.get_latest_attempt(db, job.id)
            if latest_attempt and latest_attempt.status == JobAttemptStatus.RUNNING:
                latest_attempt.status = JobAttemptStatus.TIMED_OUT
                latest_attempt.completed_at = now
                latest_attempt.error_message = "Worker lease expired; heartbeat timed out"

            if job.retry_count >= job.max_retries:
                # Dead letter
                job.status = JobStatus.DEAD_LETTERED
                job.failed_at = now
                job.lease_expires_at = None
                dlq = JobDeadLetter(
                    job_id=job.id,
                    status=JobDeadLetterStatus.OPEN,
                    reason=f"Stale lease timed out and exceeded max retries ({job.max_retries})",
                    error_details_json={"recovered_from_worker": worker_id, "recovered_at": now.isoformat()},
                    retry_count=job.retry_count,
                    created_at=now,
                )
                db.add(dlq)
                JobRepository.create_audit_log(
                    db,
                    action=JobAuditAction.JOB_DEAD_LETTERED,
                    job_id=job.id,
                    worker_id=worker_id,
                    metadata={"reason": dlq.reason, "stale_recovery": True},
                )
            else:
                # Requeue for retry
                job.retry_count += 1
                job.status = JobStatus.WAITING_RETRY
                job.worker_id = None
                job.lease_expires_at = None
                backoff = min(job.retry_delay * (2 ** (job.retry_count - 1)), 300)
                job.available_at = now + timedelta(seconds=backoff)

                JobRepository.create_audit_log(
                    db,
                    action=JobAuditAction.JOB_RETRY_SCHEDULED,
                    job_id=job.id,
                    worker_id=worker_id,
                    metadata={
                        "stale_recovery": True,
                        "retry_count": job.retry_count,
                        "available_at": job.available_at.isoformat(),
                    },
                )
            recovered.append(job)

        db.flush()
        return recovered


default_job_queue = DatabaseJobQueue()

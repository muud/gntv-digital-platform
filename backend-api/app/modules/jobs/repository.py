"""Small persistence helpers shared by queue, worker, and scheduler services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.events.security import sanitize_payload
from app.modules.jobs.models import JobAttempt, JobAuditAction, JobAuditLog


class JobRepository:
    @staticmethod
    def get_latest_attempt(db: Session, job_id: UUID) -> JobAttempt | None:
        return db.scalar(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number.desc())
            .limit(1)
        )

    @staticmethod
    def create_audit_log(
        db: Session,
        *,
        action: JobAuditAction,
        job_id: UUID | None = None,
        worker_id: str | None = None,
        schedule_id: UUID | None = None,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobAuditLog:
        audit = JobAuditLog(
            action=action,
            job_id=job_id,
            worker_id=worker_id,
            schedule_id=schedule_id,
            actor_user_id=actor_user_id,
            metadata_json=sanitize_payload(metadata) if metadata else None,
            created_at=datetime.now(UTC),
        )
        db.add(audit)
        db.flush()
        return audit

"""Operator-facing application service for durable execution infrastructure."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.events.security import sanitize_payload
from app.modules.jobs.models import (
    DurableJob,
    JobAuditAction,
    JobDeadLetter,
    JobDeadLetterStatus,
    JobSchedule,
    JobStatus,
    WorkerRecord,
)
from app.modules.jobs.queue import DatabaseJobQueue
from app.modules.jobs.registry import default_job_registry
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import EnqueueJobRequest, ScheduleCreateRequest, ScheduleUpdateRequest


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobOperationsService:
    """A transaction-neutral service; API callers decide when to commit."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.queue = DatabaseJobQueue()

    def enqueue(self, request: EnqueueJobRequest, actor_user_id: int | None = None) -> DurableJob:
        return self.queue.enqueue(self.db, actor_user_id=actor_user_id, **request.model_dump())

    def list_jobs(
        self,
        *,
        status: JobStatus | None = None,
        job_type: str | None = None,
        queue_name: str | None = None,
        correlation_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[DurableJob]:
        stmt = select(DurableJob).options(selectinload(DurableJob.attempts))
        for condition in (
            DurableJob.status == status if status else None,
            DurableJob.job_type == job_type if job_type else None,
            DurableJob.queue_name == queue_name if queue_name else None,
            DurableJob.correlation_id == correlation_id if correlation_id else None,
        ):
            if condition is not None:
                stmt = stmt.where(condition)
        stmt = stmt.order_by(DurableJob.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).unique())

    def get_job(self, job_id: UUID) -> DurableJob:
        job = self.db.scalar(
            select(DurableJob)
            .options(selectinload(DurableJob.attempts))
            .where(DurableJob.id == job_id)
        )
        if job is None:
            raise ValueError("Job not found")
        return job

    def workers(self) -> list[WorkerRecord]:
        return list(self.db.scalars(select(WorkerRecord).order_by(WorkerRecord.started_at.desc())))

    def worker(self, worker_id: str) -> WorkerRecord:
        worker = self.db.get(WorkerRecord, worker_id)
        if worker is None:
            raise ValueError("Worker not found")
        return worker

    def schedules(self) -> list[JobSchedule]:
        return list(self.db.scalars(select(JobSchedule).order_by(JobSchedule.created_at.desc())))

    def schedule(self, schedule_id: UUID) -> JobSchedule:
        schedule = self.db.get(JobSchedule, schedule_id)
        if schedule is None:
            raise ValueError("Schedule not found")
        return schedule

    def create_schedule(
        self, request: ScheduleCreateRequest, actor_user_id: int | None = None
    ) -> JobSchedule:
        if not default_job_registry.is_registered(request.job_type):
            raise ValueError(f"Job type '{request.job_type}' is not registered")
        data = request.model_dump()
        payload = sanitize_payload(data.pop("payload"))
        enabled = data.pop("enabled")
        schedule = JobSchedule(payload_json=payload, is_enabled=enabled, **data)
        self.db.add(schedule)
        self.db.flush()
        JobRepository.create_audit_log(
            self.db,
            action=JobAuditAction.SCHEDULE_CREATED,
            schedule_id=schedule.id,
            actor_user_id=actor_user_id,
            metadata={"job_type": schedule.job_type, "name": schedule.name},
        )
        return schedule

    def update_schedule(
        self,
        schedule: JobSchedule,
        request: ScheduleUpdateRequest,
        actor_user_id: int | None = None,
    ) -> JobSchedule:
        updates = request.model_dump(exclude_unset=True)
        if "payload" in updates:
            updates["payload_json"] = sanitize_payload(updates.pop("payload"))
        for name, value in updates.items():
            setattr(schedule, name, value)
        schedule.updated_at = utc_now()
        JobRepository.create_audit_log(
            self.db,
            action=JobAuditAction.SCHEDULE_UPDATED,
            schedule_id=schedule.id,
            actor_user_id=actor_user_id,
            metadata={"fields": sorted(updates)},
        )
        self.db.flush()
        return schedule

    def enable(
        self, schedule: JobSchedule, enabled: bool, actor_user_id: int | None = None
    ) -> JobSchedule:
        schedule.is_enabled = enabled
        schedule.updated_at = utc_now()
        JobRepository.create_audit_log(
            self.db,
            action=(JobAuditAction.SCHEDULE_ENABLED if enabled else JobAuditAction.SCHEDULE_DISABLED),
            schedule_id=schedule.id,
            actor_user_id=actor_user_id,
        )
        self.db.flush()
        return schedule

    def run_now(self, schedule: JobSchedule, actor_user_id: int | None = None) -> DurableJob:
        from app.modules.jobs.scheduler import SchedulerService

        return SchedulerService(self.db, f"operator:{actor_user_id or 'system'}").run_now(
            schedule, actor_user_id=actor_user_id
        )

    def dead_letters(
        self, *, status: JobDeadLetterStatus | None = None
    ) -> list[JobDeadLetter]:
        stmt = select(JobDeadLetter).order_by(JobDeadLetter.created_at.desc())
        if status:
            stmt = stmt.where(JobDeadLetter.status == status)
        return list(self.db.scalars(stmt))

    def metrics(self) -> dict[str, Any]:
        statuses: dict[JobStatus, int] = {
            key: count for key, count in self.db.execute(
                select(DurableJob.status, func.count(DurableJob.id)).group_by(DurableJob.status)
            ).tuples()
        }
        by_type: dict[str, int] = {
            key: count for key, count in self.db.execute(
                select(DurableJob.job_type, func.count(DurableJob.id)).group_by(DurableJob.job_type)
            ).tuples()
        }
        by_queue: dict[str, int] = {
            key: count for key, count in self.db.execute(
                select(DurableJob.queue_name, func.count(DurableJob.id)).group_by(DurableJob.queue_name)
            ).tuples()
        }
        now = utc_now()
        oldest = self.db.scalar(
            select(func.min(DurableJob.created_at)).where(
                DurableJob.status.in_([JobStatus.QUEUED, JobStatus.WAITING_RETRY])
            )
        )
        heartbeat = self.db.scalar(select(func.max(WorkerRecord.last_heartbeat_at)))
        next_due = self.db.scalar(
            select(func.min(JobSchedule.next_run_at)).where(JobSchedule.is_enabled.is_(True))
        )
        durations = [
            (completed.replace(tzinfo=completed.tzinfo or UTC) - started.replace(tzinfo=started.tzinfo or UTC)).total_seconds()
            for started, completed in self.db.execute(
                select(DurableJob.started_at, DurableJob.completed_at).where(
                    DurableJob.started_at.is_not(None), DurableJob.completed_at.is_not(None)
                )
            )
        ]

        def age(value: datetime | None) -> float | None:
            if value is None:
                return None
            return max(0.0, (now - value.replace(tzinfo=value.tzinfo or UTC)).total_seconds())

        return {
            "queued_jobs": statuses.get(JobStatus.QUEUED, 0),
            "running_jobs": statuses.get(JobStatus.RUNNING, 0) + statuses.get(JobStatus.CLAIMED, 0),
            "scheduled_jobs": statuses.get(JobStatus.SCHEDULED, 0),
            "succeeded_jobs": statuses.get(JobStatus.SUCCEEDED, 0),
            "failed_jobs": statuses.get(JobStatus.FAILED, 0),
            "dead_letter_jobs": statuses.get(JobStatus.DEAD_LETTERED, 0),
            "retries": sum(job.retry_count for job in self.db.scalars(select(DurableJob))),
            "oldest_queued_job_age_seconds": age(oldest),
            "worker_heartbeat_age_seconds": age(heartbeat),
            "average_job_duration_seconds": sum(durations) / len(durations) if durations else None,
            "scheduler_lag_seconds": age(next_due),
            "jobs_by_type": {str(key): value for key, value in by_type.items()},
            "jobs_by_queue": {str(key): value for key, value in by_queue.items()},
        }

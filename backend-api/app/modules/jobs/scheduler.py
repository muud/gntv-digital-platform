"""Deterministic, callable scheduler for persisted internal job schedules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.jobs.models import (
    DurableJob,
    JobAuditAction,
    JobSchedule,
    JobStatus,
    ScheduleExecution,
    ScheduleMisfirePolicy,
    ScheduleRecurrenceType,
)
from app.modules.jobs.queue import DatabaseJobQueue
from app.modules.jobs.repository import JobRepository


ACTIVE_STATES = (JobStatus.QUEUED, JobStatus.SCHEDULED, JobStatus.CLAIMED, JobStatus.RUNNING)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)


def _cron_values(field: str, minimum: int, maximum: int) -> set[int]:
    if field == "*":
        return set(range(minimum, maximum + 1))
    values: set[int] = set()
    for item in field.split(","):
        if "/" in item:
            base, step_raw = item.split("/", 1)
            step = int(step_raw)
            if step < 1:
                raise ValueError("Cron step must be positive")
            start, end = (minimum, maximum) if base == "*" else map(int, base.split("-", 1))
            values.update(range(start, end + 1, step))
        elif "-" in item:
            start, end = map(int, item.split("-", 1))
            values.update(range(start, end + 1))
        else:
            values.add(int(item))
    if not values or min(values) < minimum or max(values) > maximum:
        raise ValueError("Cron field is outside its valid range")
    return values


def next_cron_occurrence(expression: str, after: datetime, timezone: str) -> datetime:
    """Return the next UTC minute matching safe five-field cron metadata."""
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError("Cron expression must contain exactly five fields")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc
    minute, hour, day, month, weekday = (
        _cron_values(parts[0], 0, 59),
        _cron_values(parts[1], 0, 23),
        _cron_values(parts[2], 1, 31),
        _cron_values(parts[3], 1, 12),
        _cron_values(parts[4], 0, 6),
    )
    candidate = as_utc(after).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(527_040):
        local = candidate.astimezone(zone)
        cron_weekday = (local.weekday() + 1) % 7
        if (
            local.minute in minute
            and local.hour in hour
            and local.day in day
            and local.month in month
            and cron_weekday in weekday
        ):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("Cron expression has no occurrence in the supported lookahead")


def next_run(schedule: JobSchedule, after: datetime) -> datetime | None:
    if schedule.recurrence_type == ScheduleRecurrenceType.ONE_TIME:
        return None
    if schedule.recurrence_type == ScheduleRecurrenceType.INTERVAL:
        if not schedule.interval_seconds or schedule.interval_seconds < 1:
            raise ValueError("Interval schedules require a positive interval_seconds")
        return as_utc(after) + timedelta(seconds=schedule.interval_seconds)
    if not schedule.cron_expression:
        raise ValueError("Cron schedules require cron_expression")
    return next_cron_occurrence(schedule.cron_expression, after, schedule.timezone)


class SchedulerService:
    """Claims due schedules and idempotently emits a bounded number of jobs."""

    def __init__(self, db: Session, scheduler_id: str, claim_seconds: int = 30) -> None:
        self.db = db
        self.scheduler_id = scheduler_id
        self.claim_seconds = max(1, claim_seconds)
        self.queue = DatabaseJobQueue()

    def _record_occurrence(
        self, schedule: JobSchedule, scheduled_for: datetime, outcome: str, job: DurableJob | None = None
    ) -> ScheduleExecution:
        existing = self.db.scalar(
            select(ScheduleExecution).where(
                ScheduleExecution.schedule_id == schedule.id,
                ScheduleExecution.scheduled_for == scheduled_for,
            )
        )
        if existing:
            return existing
        execution = ScheduleExecution(
            schedule_id=schedule.id,
            scheduled_for=scheduled_for,
            job_id=job.id if job else None,
            outcome=outcome,
        )
        self.db.add(execution)
        self.db.flush()
        return execution

    def _enqueue_occurrence(self, schedule: JobSchedule, occurrence: datetime) -> DurableJob | None:
        active_count = self.db.scalar(
            select(func.count(DurableJob.id)).where(
                DurableJob.schedule_id == schedule.id, DurableJob.status.in_(ACTIVE_STATES)
            )
        ) or 0
        if active_count >= schedule.max_concurrent_runs:
            self._record_occurrence(schedule, occurrence, "concurrency_limited")
            return None
        key = f"schedule:{schedule.id}:{as_utc(occurrence).isoformat()}"
        job = self.queue.enqueue(
            self.db,
            job_type=schedule.job_type,
            payload=schedule.payload_json or {},
            queue_name=schedule.queue_name,
            idempotency_key=key,
            correlation_id=key,
            causation_id=str(schedule.id),
            scheduled_for=occurrence,
        )
        job.schedule_id = schedule.id
        self._record_occurrence(schedule, occurrence, "enqueued", job)
        JobRepository.create_audit_log(
            self.db,
            action=JobAuditAction.SCHEDULE_TRIGGERED,
            job_id=job.id,
            schedule_id=schedule.id,
            metadata={"scheduled_for": occurrence.isoformat()},
        )
        return job

    def tick(self, now: datetime | None = None) -> list[DurableJob]:
        now = as_utc(now or datetime.now(UTC))
        stmt = select(JobSchedule).where(
            JobSchedule.is_enabled.is_(True),
            JobSchedule.next_run_at.is_not(None),
            JobSchedule.next_run_at <= now,
            (JobSchedule.claim_expires_at.is_(None)) | (JobSchedule.claim_expires_at <= now),
        ).order_by(JobSchedule.next_run_at)
        if self.db.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        schedules = list(self.db.scalars(stmt))
        emitted: list[DurableJob] = []
        for schedule in schedules:
            schedule.claimed_by = self.scheduler_id
            schedule.claim_expires_at = now + timedelta(seconds=self.claim_seconds)
            assert schedule.next_run_at is not None
            occurrence = as_utc(schedule.next_run_at)
            misfired = occurrence < now.replace(microsecond=0)
            occurrences: list[datetime] = []
            if misfired and schedule.misfire_policy == ScheduleMisfirePolicy.SKIP:
                self._record_occurrence(schedule, occurrence, "skipped")
            elif misfired and schedule.misfire_policy == ScheduleMisfirePolicy.CATCH_UP_LIMITED:
                cursor = occurrence
                for _ in range(schedule.catch_up_limit):
                    if cursor > now:
                        break
                    occurrences.append(cursor)
                    following = next_run(schedule, cursor)
                    if following is None:
                        break
                    cursor = following
            else:
                occurrences.append(occurrence)
            if misfired:
                JobRepository.create_audit_log(
                    self.db,
                    action=JobAuditAction.SCHEDULE_MISFIRED,
                    schedule_id=schedule.id,
                    metadata={"policy": schedule.misfire_policy.value, "scheduled_for": occurrence.isoformat()},
                )
            for due in occurrences:
                job = self._enqueue_occurrence(schedule, due)
                if job:
                    emitted.append(job)
            schedule.last_run_at = occurrences[-1] if occurrences else occurrence
            if schedule.recurrence_type == ScheduleRecurrenceType.ONE_TIME:
                schedule.is_enabled = False
                schedule.next_run_at = None
            else:
                cursor = schedule.last_run_at
                following = next_run(schedule, cursor)
                while following is not None and following <= now:
                    cursor = following
                    following = next_run(schedule, cursor)
                schedule.next_run_at = following
            schedule.claimed_by = None
            schedule.claim_expires_at = None
            schedule.updated_at = now
        self.db.flush()
        return emitted

    def run_now(
        self, schedule: JobSchedule, actor_user_id: int | None = None
    ) -> DurableJob:
        occurrence = datetime.now(UTC)
        job = self.queue.enqueue(
            self.db,
            job_type=schedule.job_type,
            payload=schedule.payload_json or {},
            queue_name=schedule.queue_name,
            idempotency_key=f"manual:{schedule.id}:{uuid4().hex}",
            correlation_id=f"manual:{schedule.id}:{uuid4().hex}",
            causation_id=str(schedule.id),
        )
        job.schedule_id = schedule.id
        JobRepository.create_audit_log(
            self.db,
            action=JobAuditAction.SCHEDULE_TRIGGERED,
            job_id=job.id,
            schedule_id=schedule.id,
            actor_user_id=actor_user_id,
            metadata={"manual": True, "triggered_at": occurrence.isoformat()},
        )
        self.db.flush()
        return job


if __name__ == "__main__":
    from app.modules.jobs.scheduler_runner import main

    main()

"""Operator API for durable jobs, workers, schedules, and dead letters."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.jobs.models import JobAuditAction, JobDeadLetterStatus, JobStatus
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import (
    DeadLetterResponse,
    EnqueueJobRequest,
    JobMetricsResponse,
    JobResponse,
    ScheduleCreateRequest,
    ScheduleResponse,
    ScheduleUpdateRequest,
    WorkerResponse,
)
from app.modules.jobs.service import JobOperationsService

OPERATOR_ROLES = {"operator", "admin", "super_admin"}
READER_ROLES = OPERATOR_ROLES | {"viewer"}


def _roles(user: User) -> set[str]:
    return {role.name for role in user.roles}


def require_operator(user: User = Depends(get_current_user)) -> User:
    if not _roles(user) & OPERATOR_ROLES:
        raise HTTPException(status_code=403, detail="Operator access required")
    return user


def require_reader(user: User = Depends(get_current_user)) -> User:
    if not _roles(user) & READER_ROLES:
        raise HTTPException(status_code=403, detail="Worker infrastructure access denied")
    return user


jobs_router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
workers_router = APIRouter(prefix="/api/v1/workers", tags=["workers"])
schedules_router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])
job_dead_letters_router = APIRouter(prefix="/api/v1/job-dead-letters", tags=["job-dead-letters"])


def _error(exc: ValueError, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


@jobs_router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def enqueue_job(request: EnqueueJobRequest, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        service = JobOperationsService(db)
        job = service.enqueue(request, user.id)
        db.commit()
        return service.get_job(job.id)
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@jobs_router.get("", response_model=list[JobResponse])
def list_jobs(
    job_status: JobStatus | None = Query(default=None, alias="status"), job_type: str | None = None,
    queue_name: str | None = None, correlation_id: str | None = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db), _user: User = Depends(require_reader),
) -> Any:
    return JobOperationsService(db).list_jobs(status=job_status, job_type=job_type, queue_name=queue_name, correlation_id=correlation_id, offset=offset, limit=limit)


@jobs_router.get("/metrics/summary", response_model=JobMetricsResponse)
def metrics(db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    return JobOperationsService(db).metrics()


@jobs_router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    try:
        return JobOperationsService(db).get_job(job_id)
    except ValueError as exc:
        raise _error(exc, 404) from exc


@jobs_router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: UUID, reason: str = "operator cancellation", db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        service = JobOperationsService(db)
        job = service.queue.cancel(db, job_id=job_id, reason=reason, actor_user_id=user.id)
        db.commit()
        return service.get_job(job.id)
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@jobs_router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        service = JobOperationsService(db)
        job = service.queue.retry(db, job_id=job_id, actor_user_id=user.id)
        db.commit()
        return service.get_job(job.id)
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@workers_router.get("", response_model=list[WorkerResponse])
def list_workers(db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    return JobOperationsService(db).workers()


@workers_router.get("/{worker_id}", response_model=WorkerResponse)
def get_worker(worker_id: str, db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    try:
        return JobOperationsService(db).worker(worker_id)
    except ValueError as exc:
        raise _error(exc, 404) from exc


@schedules_router.get("", response_model=list[ScheduleResponse])
def list_schedules(db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    return JobOperationsService(db).schedules()


@schedules_router.post("", response_model=ScheduleResponse, status_code=201)
def create_schedule(request: ScheduleCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        schedule = JobOperationsService(db).create_schedule(request, user.id)
        db.commit()
        db.refresh(schedule)
        return schedule
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@schedules_router.get("/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(schedule_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    try:
        return JobOperationsService(db).schedule(schedule_id)
    except ValueError as exc:
        raise _error(exc, 404) from exc


@schedules_router.patch("/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(schedule_id: UUID, request: ScheduleUpdateRequest, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        service = JobOperationsService(db)
        schedule = service.update_schedule(service.schedule(schedule_id), request, user.id)
        db.commit()
        db.refresh(schedule)
        return schedule
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


def _enable(schedule_id: UUID, enabled: bool, db: Session, user: User) -> Any:
    service = JobOperationsService(db)
    schedule = service.enable(service.schedule(schedule_id), enabled, user.id)
    db.commit()
    db.refresh(schedule)
    return schedule


@schedules_router.post("/{schedule_id}/enable", response_model=ScheduleResponse)
def enable_schedule(schedule_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        return _enable(schedule_id, True, db, user)
    except ValueError as exc:
        raise _error(exc) from exc


@schedules_router.post("/{schedule_id}/disable", response_model=ScheduleResponse)
def disable_schedule(schedule_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        return _enable(schedule_id, False, db, user)
    except ValueError as exc:
        raise _error(exc) from exc


@schedules_router.post("/{schedule_id}/run-now", response_model=JobResponse)
def run_now(schedule_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    try:
        service = JobOperationsService(db)
        job = service.run_now(service.schedule(schedule_id), user.id)
        db.commit()
        return service.get_job(job.id)
    except ValueError as exc:
        raise _error(exc) from exc


@job_dead_letters_router.get("", response_model=list[DeadLetterResponse])
def list_dead_letters(letter_status: JobDeadLetterStatus | None = Query(default=None, alias="status"), db: Session = Depends(get_db), _user: User = Depends(require_reader)) -> Any:
    return JobOperationsService(db).dead_letters(status=letter_status)


@job_dead_letters_router.post("/{job_id}/retry", response_model=JobResponse)
def retry_dead_letter(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    return retry_job(job_id, db, user)


@job_dead_letters_router.post("/{letter_id}/dismiss", response_model=DeadLetterResponse)
def dismiss_dead_letter(letter_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> Any:
    service = JobOperationsService(db)
    letter = next((item for item in service.dead_letters() if item.id == letter_id), None)
    if not letter:
        raise HTTPException(status_code=404, detail="Dead letter not found")
    letter.status = JobDeadLetterStatus.DISMISSED
    JobRepository.create_audit_log(
        db,
        action=JobAuditAction.DLQ_DISMISSED,
        job_id=letter.job_id,
        actor_user_id=user.id,
        metadata={"dead_letter_id": str(letter.id)},
    )
    db.commit()
    db.refresh(letter)
    return letter

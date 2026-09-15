"""Module 8 Sprint 8.3 durable workers and scheduler acceptance tests."""

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.events.models import DomainEvent, EventProcessingStatus
from app.modules.events.service import EventService
from app.modules.jobs.models import (
    DurableJob,
    JobAttempt,
    JobAuditAction,
    JobAuditLog,
    JobDeadLetterStatus,
    JobSchedule,
    JobStatus,
    ScheduleExecution,
    ScheduleMisfirePolicy,
    ScheduleRecurrenceType,
    WorkerStatus,
)
from app.modules.jobs.queue import DatabaseJobQueue
from app.modules.jobs.registry import (
    JobTypeRegistry,
    NonRetryableJobError,
    UnregisteredJobTypeError,
    default_job_registry,
)
from app.modules.jobs.scheduler import SchedulerService, next_cron_occurrence, next_run
from app.modules.jobs.schemas import EnqueueJobRequest, ScheduleCreateRequest, ScheduleUpdateRequest
from app.modules.jobs.service import JobOperationsService
from app.modules.jobs.worker import WorkerService
from app.modules.workflows.models import Workflow, WorkflowStatus, WorkflowStepDefinition, WorkflowStepType
from app.modules.workflows.repository import WorkflowRepository
from app.modules.workflows.service import WorkflowService
from app.utils.jwt import create_access_token


def make_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_client(db: Session) -> TestClient:
    def override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def create_user(db: Session, role_name: str) -> User:
    role = Role(name=role_name, description=role_name)
    user = User(email=f"{role_name}-{uuid4().hex[:6]}@test.invalid", hashed_password="hash", is_active=True, is_verified=True)
    user.roles.append(role)
    db.add_all([role, user])
    db.commit()
    return user


def headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def enqueue(db: Session, **overrides) -> DurableJob:
    values = {"job_type": "REPORT_GENERATION", "payload": {"report_type": "daily"}, "idempotency_key": uuid4().hex}
    values.update(overrides)
    return DatabaseJobQueue().enqueue(db, **values)


def test_enqueue_idempotency_sanitization_and_delayed_job() -> None:
    db = make_db()
    queue = DatabaseJobQueue()
    first = queue.enqueue(
        db,
        job_type="REPORT_GENERATION",
        payload={"password": "secret", "nested": {"authorization": "Bearer nope"}},
        idempotency_key="daily-report",
        correlation_id="corr-1",
        causation_id="cause-1",
        delay_seconds=30,
    )
    duplicate = queue.enqueue(db, job_type="REPORT_GENERATION", payload={"different": True}, idempotency_key="daily-report")
    assert first.id == duplicate.id
    assert first.payload_json == {"password": "[REDACTED]", "nested": {"authorization": "[REDACTED]"}}
    assert first.correlation_id == "corr-1"
    assert first.available_at > first.created_at
    assert db.scalar(select(JobAuditLog).where(JobAuditLog.action == JobAuditAction.JOB_ENQUEUED))
    with pytest.raises(ValueError, match="not registered"):
        queue.enqueue(db, job_type="os.system", payload={"command": "rm"})


def test_claim_contention_heartbeat_acknowledge_and_release() -> None:
    db = make_db()
    queue = DatabaseJobQueue()
    first = enqueue(db, priority=10)
    second = enqueue(db, priority=1)
    claimed = queue.claim(db, worker_id="worker-a", batch_size=1, lease_duration_seconds=10)
    assert claimed == [first]
    assert queue.claim(db, worker_id="worker-b", batch_size=1) == [second]
    old_lease = first.lease_expires_at
    queue.heartbeat(db, job_id=first.id, worker_id="worker-a", extension_seconds=60)
    assert first.lease_expires_at > old_lease
    with pytest.raises(ValueError, match="does not own"):
        queue.heartbeat(db, job_id=first.id, worker_id="worker-b")
    queue.release(db, job_id=first.id, worker_id="worker-a")
    assert first.status == JobStatus.QUEUED
    reclaimed = queue.claim(db, worker_id="worker-c", batch_size=1)[0]
    queue.acknowledge(db, job_id=reclaimed.id, worker_id="worker-c", result={"token": "hide", "rows": 2})
    assert reclaimed.status == JobStatus.SUCCEEDED
    assert reclaimed.result_json["token"] == "[REDACTED]"
    assert db.query(JobAttempt).filter_by(job_id=reclaimed.id).count() == 2


def test_retry_backoff_terminal_dead_letter_and_operator_retry() -> None:
    db = make_db()
    queue = DatabaseJobQueue()
    job = enqueue(db, max_retries=1, retry_delay=2)
    queue.claim(db, worker_id="worker", batch_size=1)
    queue.fail(db, job_id=job.id, worker_id="worker", error_message="temporary token=abc", is_retryable=True)
    assert job.status == JobStatus.WAITING_RETRY
    assert job.retry_count == 1
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    queue.claim(db, worker_id="worker", batch_size=1)
    queue.fail(db, job_id=job.id, worker_id="worker", error_message="still failing", is_retryable=True)
    assert job.status == JobStatus.DEAD_LETTERED
    assert job.dead_letter.status == JobDeadLetterStatus.OPEN
    queue.retry(db, job_id=job.id, actor_user_id=None)
    assert job.status == JobStatus.QUEUED
    assert job.dead_letter.status == JobDeadLetterStatus.RETRIED


def test_nonretryable_failure_and_cooperative_cancellation() -> None:
    db = make_db()
    queue = DatabaseJobQueue()
    bad = enqueue(db, max_retries=10)
    queue.claim(db, worker_id="worker", batch_size=1)
    queue.fail(db, job_id=bad.id, worker_id="worker", error_message="permanent", is_retryable=False)
    assert bad.status == JobStatus.DEAD_LETTERED
    queued = enqueue(db)
    queue.cancel(db, job_id=queued.id, reason="operator")
    assert queued.status == JobStatus.CANCELLED
    running = enqueue(db)
    queue.claim(db, worker_id="worker", batch_size=1)
    running.status = JobStatus.RUNNING
    queue.cancel(db, job_id=running.id, reason="cooperate")
    assert running.status == JobStatus.RUNNING
    assert running.cancel_requested is True


def test_stale_lease_recovery_is_bounded() -> None:
    db = make_db()
    queue = DatabaseJobQueue()
    retryable = enqueue(db, max_retries=2)
    terminal = enqueue(db, max_retries=0)
    queue.claim(db, worker_id="crashed", batch_size=2, lease_duration_seconds=1)
    for job in (retryable, terminal):
        job.lease_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    recovered = queue.recover_stale_leases(db)
    assert len(recovered) == 2
    assert retryable.status == JobStatus.WAITING_RETRY
    assert terminal.status == JobStatus.DEAD_LETTERED
    assert terminal.dead_letter is not None


def test_worker_registration_execution_health_and_shutdown() -> None:
    db = make_db()
    job = enqueue(db, payload={"report_type": "audience"})
    worker = WorkerService(db, "worker-1", concurrency=2, version="8.3", metadata={"api_key": "nope", "build": "test"})
    record = worker.register()
    assert record.status == WorkerStatus.ONLINE
    assert record.metadata_json["api_key"] == "[REDACTED]"
    processed = worker.process_once()
    assert processed == [job]
    assert job.status == JobStatus.SUCCEEDED
    worker.heartbeat()
    record.last_heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    assert WorkerService.effective_status(record, 30) == WorkerStatus.UNHEALTHY
    assert worker.drain().status == WorkerStatus.DRAINING
    assert worker.process_once() == []
    assert worker.shutdown().status == WorkerStatus.OFFLINE


def test_worker_retries_transient_and_deadletters_permanent_handler_failures() -> None:
    db = make_db()
    transient = enqueue(db, payload={"fail_transient": True}, max_retries=1)
    permanent = enqueue(db, payload={"fail_permanent": True}, max_retries=5)
    worker = WorkerService(db, "worker-errors", concurrency=2)
    worker.process_once()
    assert transient.status == JobStatus.WAITING_RETRY
    assert permanent.status == JobStatus.DEAD_LETTERED


def test_registry_rejects_arbitrary_job_types() -> None:
    registry = JobTypeRegistry()
    assert registry.is_registered("EVENT_DISPATCH")
    with pytest.raises(UnregisteredJobTypeError):
        registry.register("python.module:function", lambda db, job: {})
    injected = DurableJob(job_type="subprocess", queue_name="default", status=JobStatus.RUNNING, correlation_id="x", available_at=datetime.now(UTC))
    with pytest.raises(UnregisteredJobTypeError):
        registry.execute(make_db(), injected)


def test_registered_handlers_are_bounded_and_classify_errors() -> None:
    db = make_db()
    expected = {
        "OUTBOUND_WEBHOOK_DELIVERY": "delivered",
        "CONTENT_PUBLISH_REQUEST": "published",
        "DISTRIBUTION_REQUEST": "batches",
        "MEDIA_PROCESSING_REQUEST": "renditions",
    }
    for job_type, result_key in expected.items():
        job = enqueue(db, job_type=job_type, payload={})
        assert result_key in default_job_registry.execute(db, job)

    for job_type in (
        "NOTIFICATION_EVENT",
        "CONTENT_PUBLISH_REQUEST",
        "DISTRIBUTION_REQUEST",
        "MEDIA_PROCESSING_REQUEST",
    ):
        job = enqueue(db, job_type=job_type, payload={"fail_transient": True})
        with pytest.raises(RuntimeError):
            default_job_registry.execute(db, job)

    for job_type, payload in (
        ("WORKFLOW_RUN", {}),
        ("WORKFLOW_RUN", {"run_id": "not-a-uuid"}),
        ("EVENT_DISPATCH", {}),
        ("EVENT_DISPATCH", {"event_id": "not-a-uuid"}),
        ("EVENT_DISPATCH", {"event_id": str(uuid4())}),
        ("OUTBOUND_WEBHOOK_DELIVERY", {"delivery_id": "not-a-uuid"}),
        ("OUTBOUND_WEBHOOK_DELIVERY", {"delivery_id": str(uuid4())}),
    ):
        job = enqueue(db, job_type=job_type, payload=payload)
        with pytest.raises(NonRetryableJobError):
            default_job_registry.execute(db, job)

    assert len(default_job_registry.list_types()) == 9


def test_interval_cron_and_timezone_calculation() -> None:
    interval = JobSchedule(name="interval", job_type="NOTIFICATION_EVENT", recurrence_type=ScheduleRecurrenceType.INTERVAL, interval_seconds=300, timezone="UTC", next_run_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert next_run(interval, datetime(2026, 1, 1, tzinfo=UTC)) == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    cron_next = next_cron_occurrence("0 9 * * *", datetime(2026, 1, 1, 0, 0, tzinfo=UTC), "Africa/Nairobi")
    assert cron_next == datetime(2026, 1, 1, 6, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="five fields"):
        next_cron_occurrence("rm -rf /", datetime.now(UTC), "UTC")
    with pytest.raises(ValueError, match="Unknown timezone"):
        next_cron_occurrence("0 1 * * *", datetime.now(UTC), "Mars/Base")


def test_one_time_schedule_duplicate_prevention_and_manual_run() -> None:
    db = make_db()
    due = datetime.now(UTC) - timedelta(seconds=1)
    schedule = JobSchedule(name="once", job_type="NOTIFICATION_EVENT", queue_name="default", payload_json={"channel": "ops"}, recurrence_type=ScheduleRecurrenceType.ONE_TIME, timezone="UTC", next_run_at=due, misfire_policy=ScheduleMisfirePolicy.RUN_ONCE, max_concurrent_runs=1, catch_up_limit=2)
    db.add(schedule)
    db.flush()
    scheduler = SchedulerService(db, "scheduler-a")
    jobs = scheduler.tick()
    assert len(jobs) == 1
    assert schedule.is_enabled is False
    assert db.query(ScheduleExecution).count() == 1
    assert scheduler.tick() == []
    schedule.is_enabled = True
    manual = scheduler.run_now(schedule)
    assert manual.schedule_id == schedule.id


def test_misfire_skip_and_limited_catchup() -> None:
    db = make_db()
    now = datetime.now(UTC)
    skipped = JobSchedule(name="skip", job_type="NOTIFICATION_EVENT", queue_name="default", recurrence_type=ScheduleRecurrenceType.INTERVAL, interval_seconds=60, timezone="UTC", next_run_at=now - timedelta(minutes=5), misfire_policy=ScheduleMisfirePolicy.SKIP, max_concurrent_runs=1, catch_up_limit=3)
    catchup = JobSchedule(name="catch", job_type="NOTIFICATION_EVENT", queue_name="catch", recurrence_type=ScheduleRecurrenceType.INTERVAL, interval_seconds=60, timezone="UTC", next_run_at=now - timedelta(minutes=5), misfire_policy=ScheduleMisfirePolicy.CATCH_UP_LIMITED, max_concurrent_runs=10, catch_up_limit=3)
    db.add_all([skipped, catchup])
    db.flush()
    jobs = SchedulerService(db, "scheduler").tick(now)
    assert len(jobs) == 3
    assert db.scalar(select(ScheduleExecution).where(ScheduleExecution.schedule_id == skipped.id)).outcome == "skipped"


def test_operations_service_schedule_metrics_and_updates() -> None:
    db = make_db()
    operations = JobOperationsService(db)
    request = EnqueueJobRequest(job_type="NOTIFICATION_EVENT", payload={}, idempotency_key="ops")
    job = operations.enqueue(request)
    assert operations.get_job(job.id).id == job.id
    assert operations.list_jobs(job_type="NOTIFICATION_EVENT") == [job]
    schedule = operations.create_schedule(ScheduleCreateRequest(name="hourly", job_type="NOTIFICATION_EVENT", recurrence_type=ScheduleRecurrenceType.INTERVAL, interval_seconds=3600))
    operations.update_schedule(schedule, ScheduleUpdateRequest(name="hourly-updated", payload={"token": "hide"}))
    assert schedule.payload_json["token"] == "[REDACTED]"
    operations.enable(schedule, False)
    assert schedule.is_enabled is False
    assert operations.schedules()[0].id == schedule.id
    metrics = operations.metrics()
    assert metrics["jobs_by_type"]["NOTIFICATION_EVENT"] == 1
    with pytest.raises(ValueError, match="not found"):
        operations.get_job(uuid4())


def test_workflow_and_event_durable_integration() -> None:
    db = make_db()
    workflow = Workflow(name="async", status=WorkflowStatus.ACTIVE, is_enabled=True)
    workflow.steps.append(WorkflowStepDefinition(step_order=1, name="notify", step_type=WorkflowStepType.NOTIFICATION_EVENT))
    db.add(workflow)
    db.commit()
    run = WorkflowService(WorkflowRepository(db)).enqueue_durable_workflow_run(workflow.id, correlation_id="workflow-corr", idempotency_key="workflow-idem")
    workflow_job = db.scalar(select(DurableJob).where(DurableJob.job_type == "WORKFLOW_RUN"))
    assert workflow_job.payload_json["run_id"] == str(run.id)
    assert workflow_job.correlation_id == "workflow-corr"
    event = DomainEvent(event_type="content.updated", event_version=1, source="cms", correlation_id="event-corr", idempotency_key="event-idem", payload_json={}, status=EventProcessingStatus.PENDING, occurred_at=datetime.now(UTC), received_at=datetime.now(UTC))
    db.add(event)
    db.flush()
    event_job = EventService().enqueue_durable_dispatch(db, event)
    assert event_job.correlation_id == "event-corr"
    assert event_job.causation_id == str(event.id)


def test_operator_api_and_partner_rbac() -> None:
    db = make_db()
    client = make_client(db)
    operator = create_user(db, "operator")
    partner = create_user(db, "partner")
    created = client.post("/api/v1/jobs", headers=headers(operator), json={"job_type": "REPORT_GENERATION", "payload": {}, "idempotency_key": "api-job"})
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert client.get("/api/v1/jobs", headers=headers(operator)).status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers(operator)).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers(operator)).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers(operator)).status_code == 200
    assert client.get("/api/v1/jobs/metrics/summary", headers=headers(operator)).status_code == 200
    schedule = client.post("/api/v1/schedules", headers=headers(operator), json={"name": "api-schedule", "job_type": "NOTIFICATION_EVENT", "recurrence_type": "interval", "interval_seconds": 60})
    assert schedule.status_code == 201
    schedule_id = schedule.json()["id"]
    assert client.get(f"/api/v1/schedules/{schedule_id}", headers=headers(operator)).status_code == 200
    assert client.get("/api/v1/schedules", headers=headers(operator)).status_code == 200
    assert client.patch(f"/api/v1/schedules/{schedule_id}", headers=headers(operator), json={"timezone": "Africa/Nairobi"}).status_code == 200
    assert client.post(f"/api/v1/schedules/{schedule_id}/disable", headers=headers(operator)).status_code == 200
    assert client.post(f"/api/v1/schedules/{schedule_id}/enable", headers=headers(operator)).status_code == 200
    assert client.post(f"/api/v1/schedules/{schedule_id}/run-now", headers=headers(operator)).status_code == 200
    WorkerService(db, "api-worker").register()
    db.commit()
    assert client.get("/api/v1/workers", headers=headers(operator)).status_code == 200
    assert client.get("/api/v1/workers/api-worker", headers=headers(operator)).status_code == 200
    assert client.get("/api/v1/job-dead-letters", headers=headers(operator)).status_code == 200
    assert client.post("/api/v1/jobs", headers=headers(partner), json={"job_type": "REPORT_GENERATION"}).status_code == 403
    assert client.post("/api/v1/schedules", headers=headers(partner), json={"name": "bad", "job_type": "REPORT_GENERATION", "recurrence_type": "interval", "interval_seconds": 2}).status_code == 403
    assert client.get("/api/v1/workers", headers=headers(partner)).status_code == 403
    assert client.get("/api/v1/jobs").status_code == 401


def test_migration_upgrade_and_downgrade() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    path = Path(__file__).parents[1] / "alembic/versions/202609131200_module8_sprint83_durable_workers_scheduler.py"
    spec = importlib.util.spec_from_file_location("sprint83_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()
    assert {"jobs", "job_attempts", "workers", "job_schedules", "job_schedule_executions", "job_dead_letters", "job_audit_logs"}.issubset(set(__import__("sqlalchemy").inspect(engine).get_table_names()))
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.downgrade()
    assert "jobs" not in __import__("sqlalchemy").inspect(engine).get_table_names()

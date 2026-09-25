"""Focused tests for WorkerDaemon and SchedulerDaemon process entrypoints."""

from datetime import UTC, datetime, timedelta
import threading
import time
from typing import Any
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.jobs.models import (
    DurableJob,
    JobSchedule,
    JobStatus,
    ScheduleExecution,
    ScheduleRecurrenceType,
    WorkerRecord,
    WorkerStatus,
)
from app.modules.jobs.scheduler_runner import SchedulerDaemon, main as scheduler_main
from app.modules.jobs.worker_runner import WorkerDaemon, main as worker_main


@pytest.fixture
def session_factory() -> Any:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_worker_daemon_starts_and_stops_gracefully(session_factory: Any) -> None:
    daemon = WorkerDaemon(
        worker_id="test-worker-1",
        queues=["default"],
        concurrency=2,
        poll_interval=0.05,
        session_factory=session_factory,
    )

    # Run for 2 loops then stop
    daemon.run(max_loops=2)

    with session_factory() as db:
        record = db.get(WorkerRecord, "test-worker-1")
        assert record is not None
        assert record.status == WorkerStatus.OFFLINE


def test_worker_daemon_explicit_stop_request(session_factory: Any) -> None:
    daemon = WorkerDaemon(
        worker_id="test-worker-stop",
        poll_interval=0.05,
        session_factory=session_factory,
    )

    def _stopper() -> None:
        time.sleep(0.1)
        daemon.request_stop()

    thread = threading.Thread(target=_stopper)
    thread.start()

    daemon.run()
    thread.join(timeout=2.0)

    with session_factory() as db:
        record = db.get(WorkerRecord, "test-worker-stop")
        assert record is not None
        assert record.status == WorkerStatus.OFFLINE


def test_worker_daemon_startup_failure_raises() -> None:
    def broken_session_factory() -> Any:
        raise RuntimeError("Database connection refused")

    daemon = WorkerDaemon(
        worker_id="broken-worker",
        session_factory=broken_session_factory,
    )
    with pytest.raises(RuntimeError, match="Database connection refused"):
        daemon.run()


def test_worker_main_exits_non_zero_on_error() -> None:
    with patch("app.modules.jobs.worker_runner.WorkerDaemon.run", side_effect=RuntimeError("Fatal")):
        with pytest.raises(SystemExit) as exc:
            worker_main()
        assert exc.value.code == 1


def test_scheduler_daemon_starts_and_emits_due_jobs(session_factory: Any) -> None:
    past = datetime.now(UTC) - timedelta(minutes=5)
    with session_factory() as db:
        schedule = JobSchedule(
            name="Health Check",
            job_type="RELIABILITY_HEALTH_CHECK",
            queue_name="default",
            recurrence_type=ScheduleRecurrenceType.INTERVAL,
            interval_seconds=60,
            is_enabled=True,
            next_run_at=past,
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id

    daemon = SchedulerDaemon(
        scheduler_id="test-sched-1",
        interval=0.05,
        session_factory=session_factory,
    )
    daemon.run(max_loops=1)

    with session_factory() as db:
        updated_schedule = db.get(JobSchedule, schedule_id)
        assert updated_schedule is not None
        assert updated_schedule.next_run_at is not None
        next_run_dt = updated_schedule.next_run_at.replace(
            tzinfo=updated_schedule.next_run_at.tzinfo or UTC
        )
        assert next_run_dt > past

        jobs = list(db.scalars(select(DurableJob).where(DurableJob.schedule_id == schedule_id)))
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.QUEUED

        executions = list(
            db.scalars(select(ScheduleExecution).where(ScheduleExecution.schedule_id == schedule_id))
        )
        assert len(executions) >= 1
        assert executions[0].outcome == "enqueued"


def test_scheduler_daemon_explicit_stop_request(session_factory: Any) -> None:
    daemon = SchedulerDaemon(
        scheduler_id="test-sched-stop",
        interval=0.05,
        session_factory=session_factory,
    )

    def _stopper() -> None:
        time.sleep(0.1)
        daemon.request_stop()

    thread = threading.Thread(target=_stopper)
    thread.start()

    daemon.run()
    thread.join(timeout=2.0)
    assert daemon.stop_event.is_set()


def test_scheduler_main_exits_non_zero_on_error() -> None:
    with patch("app.modules.jobs.scheduler_runner.SchedulerDaemon.run", side_effect=RuntimeError("Fatal")):
        with pytest.raises(SystemExit) as exc:
            scheduler_main()
        assert exc.value.code == 1


def test_no_duplicate_scheduler_execution(session_factory: Any) -> None:
    past = datetime.now(UTC) - timedelta(minutes=5)
    with session_factory() as db:
        schedule = JobSchedule(
            name="Health Check",
            job_type="RELIABILITY_HEALTH_CHECK",
            queue_name="default",
            recurrence_type=ScheduleRecurrenceType.INTERVAL,
            interval_seconds=300,
            is_enabled=True,
            next_run_at=past,
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id

    daemon1 = SchedulerDaemon(
        scheduler_id="sched-leader-1",
        interval=0.05,
        session_factory=session_factory,
    )
    daemon2 = SchedulerDaemon(
        scheduler_id="sched-leader-2",
        interval=0.05,
        session_factory=session_factory,
    )

    # First scheduler claims and ticks
    daemon1.run(max_loops=1)
    # Second scheduler runs immediately after
    daemon2.run(max_loops=1)

    with session_factory() as db:
        jobs = list(db.scalars(select(DurableJob).where(DurableJob.schedule_id == schedule_id)))
        # Exactly 1 job should be created, no duplicate emission
        assert len(jobs) == 1

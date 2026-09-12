"""Comprehensive test suite for Module 8 Sprint 8.1: Workflow Orchestration & Job Execution Platform."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.workflows.engine import (
    NonRetryableStepError,
    StepContext,
    StepHandler,
    sanitize_metadata,
)
from app.modules.workflows.models import (
    WorkflowRun,
    WorkflowStepType,
)
from app.modules.workflows.queue import InMemoryWorkflowQueue
from app.utils.jwt import create_access_token


def make_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    return testing_session()


def make_client(db: Session) -> TestClient:
    def override_get_db() -> Iterator[Session]:
        try:
            yield db
        finally:
            db.rollback()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def create_user(db: Session, role_name: str) -> User:
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(
        email=f"{role_name}-{uuid4().hex[:6]}@gntv.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    user.name = f"{role_name} User"
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ---------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------

def test_workflow_crud_and_lifecycle_state_machine() -> None:
    """Verifies workflow definition creation, version bumping, and activation/pause transitions."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        # 1. Create Workflow
        create_resp = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Publish News VOD",
                "description": "End-to-end publishing pipeline",
                "workflow_type": "content_publishing",
                "steps": [
                    {
                        "step_order": 1,
                        "name": "Validate Content",
                        "step_type": "CONTENT_VALIDATE",
                        "config_json": {"content_type": "vod"},
                    },
                    {
                        "step_order": 2,
                        "name": "Publish Request",
                        "step_type": "CONTENT_PUBLISH_REQUEST",
                        "config_json": {"channels": ["news-24"]},
                    },
                ],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        wf = create_resp.json()
        assert wf["status"] == "draft"
        assert wf["version"] == 1
        assert len(wf["steps"]) == 2
        wf_id = wf["id"]

        # 2. Cannot run draft workflow
        bad_run = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"content_id": "vod-123"}},
        )
        assert bad_run.status_code == 400
        assert "draft" in bad_run.text

        # 3. Update Workflow (version bumps to 2)
        patch_resp = client.patch(
            f"/api/v1/workflows/{wf_id}",
            headers=headers,
            json={"description": "Updated description with new policy"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["version"] == 2

        # 4. Activate Workflow
        act_resp = client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)
        assert act_resp.status_code == 200
        assert act_resp.json()["status"] == "active"

        # 5. Pause Workflow
        pause_resp = client.post(f"/api/v1/workflows/{wf_id}/pause", headers=headers)
        assert pause_resp.status_code == 200
        assert pause_resp.json()["status"] == "paused"

        # 6. Re-activate and run successfully
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)
        run_resp = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"content_id": "vod-123"}},
        )
        assert run_resp.status_code == 201
        run_data = run_resp.json()
        assert run_data["status"] == "succeeded"
        assert len(run_data["step_executions"]) == 2
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_ordered_step_execution_and_data_flow() -> None:
    """Verifies sequential step execution and data flow across safe step types."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        create_resp = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Full Ingest Flow",
                "workflow_type": "syndication_sync",
                "steps": [
                    {
                        "step_order": 1,
                        "name": "Internal Ping",
                        "step_type": "HTTP_INTERNAL",
                        "config_json": {"endpoint": "/api/v1/health", "method": "GET"},
                    },
                    {
                        "step_order": 2,
                        "name": "Validate Media",
                        "step_type": "CONTENT_VALIDATE",
                        "config_json": {"content_id": "video-001"},
                    },
                    {
                        "step_order": 3,
                        "name": "Generate Summary Report",
                        "step_type": "REPORT_GENERATION",
                        "config_json": {"report_type": "ingest_audit"},
                    },
                    {
                        "step_order": 4,
                        "name": "Notify Dispatch",
                        "step_type": "NOTIFICATION_EVENT",
                        "config_json": {"event_name": "media_ready", "recipient": "broadcast_ops"},
                    },
                    {
                        "step_order": 5,
                        "name": "Conditional Check",
                        "step_type": "CONDITIONAL",
                        "config_json": {"field": "report_type", "operator": "==", "value": "ingest_audit"},
                    },
                ],
            },
        )
        wf_id = create_resp.json()["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        run_resp = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"content_id": "video-001"}},
        )
        assert run_resp.status_code == 201
        run = run_resp.json()
        assert run["status"] == "succeeded"
        assert len(run["step_executions"]) == 5

        # Check step 1 HTTP_INTERNAL output
        assert run["step_executions"][0]["output_json"]["status_code"] == 200
        # Check step 5 CONDITIONAL output
        assert run["step_executions"][4]["output_json"]["condition_met"] is True
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_idempotency_workflow_runs_and_steps() -> None:
    """Repeated triggers with identical idempotency key return existing run without re-executing."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        wf_resp = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Idempotent Pipeline",
                "steps": [
                    {
                        "step_order": 1,
                        "name": "Validate",
                        "step_type": "CONTENT_VALIDATE",
                        "config_json": {"content_id": "item-999"},
                    }
                ],
            },
        )
        wf_id = wf_resp.json()["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        key = "idemp-key-broadcast-2026"
        run1 = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"idempotency_key": key, "input_metadata": {"content_id": "item-999"}},
        )
        run2 = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"idempotency_key": key, "input_metadata": {"content_id": "item-999"}},
        )

        assert run1.status_code == 201
        assert run2.status_code == 201
        assert run1.json()["id"] == run2.json()["id"]
        assert db.query(WorkflowRun).filter_by(workflow_id=UUID(wf_id)).count() == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_retry_policy_exponential_backoff_and_max_retries() -> None:
    """Retryable step failures increment retries and stop at max_retries without infinite loop."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        # Create workflow where step 1 simulates a retryable failure
        wf_resp = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Retryable Pipeline",
                "steps": [
                    {
                        "step_order": 1,
                        "name": "Validate Transient",
                        "step_type": "CONTENT_VALIDATE",
                        "max_retries": 3,
                        "retry_delay_seconds": 2,
                        "config_json": {"content_id": "item-err", "simulate_failure": True, "simulate_retryable": True},
                    }
                ],
            },
        )
        wf_id = wf_resp.json()["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        run_resp = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"content_id": "item-err"}},
        )
        assert run_resp.status_code == 201
        run = run_resp.json()
        assert run["status"] == "failed"
        assert run["retry_count"] >= 3
        assert "failed" in run["error_summary"].lower()
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_manual_approval_workflow_wait_approve_and_reject() -> None:
    """Manual approval halts workflow in waiting state until operator explicitly approves or rejects."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        operator = create_user(db, "operator")
        headers = auth_headers(admin)

        # Create workflow with MANUAL_APPROVAL step
        wf_resp = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Editorial Clearance Pipeline",
                "steps": [
                    {
                        "step_order": 1,
                        "name": "Validate Story",
                        "step_type": "CONTENT_VALIDATE",
                        "config_json": {"content_id": "news-urgent"},
                    },
                    {
                        "step_order": 2,
                        "name": "Editorial Lead Approval",
                        "step_type": "MANUAL_APPROVAL",
                        "config_json": {"prompt": "Confirm compliance with editorial standards"},
                    },
                    {
                        "step_order": 3,
                        "name": "Publish Broadcast",
                        "step_type": "CONTENT_PUBLISH_REQUEST",
                        "config_json": {"channels": ["gntv-live"]},
                    },
                ],
            },
        )
        wf_id = wf_resp.json()["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        # Run 1: Approval flow
        run1 = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"content_id": "news-urgent"}},
        ).json()
        assert run1["status"] == "waiting"
        step2 = run1["step_executions"][1]
        assert step2["status"] == "waiting"

        # Approve by operator
        appr_resp = client.post(
            f"/api/v1/workflow-runs/{run1['id']}/steps/{step2['id']}/approve",
            headers=auth_headers(operator),
            json={"notes": "Cleared for broadcast"},
        )
        assert appr_resp.status_code == 200
        run1_after = appr_resp.json()
        assert run1_after["status"] == "succeeded"
        assert run1_after["step_executions"][1]["status"] == "succeeded"
        assert run1_after["step_executions"][2]["status"] == "succeeded"

        # Run 2: Rejection flow
        run2 = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"content_id": "news-urgent-2"}},
        ).json()
        assert run2["status"] == "waiting"
        step2_run2 = run2["step_executions"][1]

        rej_resp = client.post(
            f"/api/v1/workflow-runs/{run2['id']}/steps/{step2_run2['id']}/reject",
            headers=auth_headers(operator),
            json={"notes": "Fails fact check"},
        )
        assert rej_resp.status_code == 200
        run2_after = rej_resp.json()
        assert run2_after["status"] == "failed"
        assert run2_after["step_executions"][1]["status"] == "failed"
        assert run2_after["step_executions"][2]["status"] == "pending"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_workflow_run_cancellation() -> None:
    """Cancelling a waiting or active run marks steps cancelled and records audit."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        wf_resp = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Long Flow",
                "steps": [
                    {"step_order": 1, "name": "Approval", "step_type": "MANUAL_APPROVAL"},
                    {"step_order": 2, "name": "Distribute", "step_type": "DISTRIBUTION_REQUEST"},
                ],
            },
        )
        wf_id = wf_resp.json()["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        run = client.post(f"/api/v1/workflows/{wf_id}/run", headers=headers, json={}).json()
        assert run["status"] == "waiting"

        cancel_resp = client.post(
            f"/api/v1/workflow-runs/{run['id']}/cancel?reason=operator_stopped",
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        cancelled_run = cancel_resp.json()
        assert cancelled_run["status"] == "cancelled"
        assert cancelled_run["step_executions"][0]["status"] == "cancelled"
        assert cancelled_run["step_executions"][1]["status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_operator_rbac_and_viewer_read_only() -> None:
    """Only operators/admins can mutate or approve; viewers have read-only access."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        viewer = create_user(db, "viewer")

        # Viewer cannot create workflow
        create_attempt = client.post(
            "/api/v1/workflows",
            headers=auth_headers(viewer),
            json={"name": "Forbidden WF", "steps": []},
        )
        assert create_attempt.status_code == 403

        # Admin creates workflow
        wf = client.post(
            "/api/v1/workflows",
            headers=auth_headers(admin),
            json={"name": "Permitted WF", "steps": []},
        ).json()
        wf_id = wf["id"]

        # Viewer can read workflow list and detail
        list_resp = client.get("/api/v1/workflows", headers=auth_headers(viewer))
        assert list_resp.status_code == 200
        get_resp = client.get(f"/api/v1/workflows/{wf_id}", headers=auth_headers(viewer))
        assert get_resp.status_code == 200

        # Viewer cannot run workflow
        run_attempt = client.post(f"/api/v1/workflows/{wf_id}/run", headers=auth_headers(viewer), json={})
        assert run_attempt.status_code == 403

        # Unauthenticated rejected
        unauth = client.get("/api/v1/workflows")
        assert unauth.status_code == 401
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sensitive_secret_sanitization() -> None:
    """Sensitive keys (passwords, tokens, credentials, secrets) are redacted in persisted data."""
    raw = {
        "content_id": "vod-safe",
        "api_key": "raw_secret_xyz123",
        "nested": {"admin_password": "supersecretpassword", "auth_token": "bearer-abc"},
    }
    cleaned = sanitize_metadata(raw)
    assert cleaned["content_id"] == "vod-safe"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["admin_password"] == "[REDACTED]"
    assert cleaned["nested"]["auth_token"] == "[REDACTED]"


def test_no_arbitrary_code_or_shell_execution() -> None:
    """Ensures step execution cannot execute arbitrary shell commands or external URLs."""
    ctx = StepContext(
        run_id=uuid4(),
        step_id=uuid4(),
        step_order=1,
        step_type=WorkflowStepType.HTTP_INTERNAL,
        config={"endpoint": "https://malicious-external-site.com/steal"},
        input_data={},
        previous_outputs={},
    )
    try:
        StepHandler.execute(WorkflowStepType.HTTP_INTERNAL, ctx)
        assert False, "Should have raised NonRetryableStepError"
    except NonRetryableStepError as err:
        assert "restricted" in err.message.lower() or "external" in err.message.lower()


def test_schedule_and_trigger_persistence() -> None:
    """Verifies workflow triggers and cron schedule persistence."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        wf = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={"name": "Scheduled Workflow", "steps": []},
        ).json()
        wf_id = wf["id"]

        # Trigger
        trig_resp = client.post(
            f"/api/v1/workflows/{wf_id}/triggers",
            headers=headers,
            json={
                "trigger_type": "scheduled",
                "name": "Nightly Ingest Trigger",
                "schedule_cron": "0 2 * * *",
                "schedule_timezone": "UTC",
            },
        )
        assert trig_resp.status_code == 201
        assert trig_resp.json()["schedule_cron"] == "0 2 * * *"

        # Schedule
        sched_resp = client.post(
            f"/api/v1/workflows/{wf_id}/schedules",
            headers=headers,
            json={
                "schedule_type": "recurring",
                "cron_expression": "0 2 * * *",
                "timezone": "UTC",
            },
        )
        assert sched_resp.status_code == 201
        assert sched_resp.json()["cron_expression"] == "0 2 * * *"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_queue_abstraction() -> None:
    """Tests the WorkflowQueue interface with InMemoryWorkflowQueue implementation."""
    q = InMemoryWorkflowQueue()
    assert q.size() == 0

    id1, id2 = uuid4(), uuid4()
    q.enqueue(id1)
    q.enqueue(id2)
    assert q.size() == 2
    assert q.peek() == id1

    assert q.dequeue() == id1
    assert q.size() == 1
    assert q.dequeue() == id2
    assert q.dequeue() is None


def test_orchestration_metrics_summary() -> None:
    """Verifies metrics summary calculation."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        metrics_resp = client.get("/api/v1/workflows/metrics/summary", headers=headers)
        assert metrics_resp.status_code == 200
        data = metrics_resp.json()
        assert "runs_queued" in data
        assert "total_runs" in data
        assert "pending_approvals" in data
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_api_error_contracts_and_empty_read_collections() -> None:
    """Missing resources map to stable API errors and read collections remain usable."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)
        missing_workflow = uuid4()
        missing_run = uuid4()
        missing_step = uuid4()

        assert client.get(f"/api/v1/workflows/{missing_workflow}", headers=headers).status_code == 404
        assert client.patch(
            f"/api/v1/workflows/{missing_workflow}", headers=headers, json={"description": "missing"}
        ).status_code == 404
        assert client.post(f"/api/v1/workflows/{missing_workflow}/activate", headers=headers).status_code == 400
        assert client.post(f"/api/v1/workflows/{missing_workflow}/pause", headers=headers).status_code == 400
        assert client.post(
            f"/api/v1/workflows/{missing_workflow}/run", headers=headers, json={}
        ).status_code == 400
        assert client.get(f"/api/v1/workflows/{missing_workflow}/triggers", headers=headers).status_code == 404
        assert client.post(
            f"/api/v1/workflows/{missing_workflow}/triggers",
            headers=headers,
            json={"trigger_type": "manual", "name": "Missing workflow"},
        ).status_code == 404
        assert client.post(
            f"/api/v1/workflows/{missing_workflow}/schedules",
            headers=headers,
            json={"schedule_type": "recurring", "cron_expression": "0 2 * * *"},
        ).status_code == 404

        assert client.get("/api/v1/workflow-runs", headers=headers).json() == []
        assert client.get(f"/api/v1/workflow-runs/{missing_run}", headers=headers).status_code == 404
        assert client.post(f"/api/v1/workflow-runs/{missing_run}/cancel", headers=headers).status_code == 404
        assert client.post(
            f"/api/v1/workflow-runs/{missing_run}/steps/{missing_step}/approve", headers=headers, json={}
        ).status_code == 400
        assert client.post(
            f"/api/v1/workflow-runs/{missing_run}/steps/{missing_step}/reject", headers=headers, json={}
        ).status_code == 400
    finally:
        app.dependency_overrides.clear()
        engine = db.get_bind()
        db.close()
        engine.dispose()


def test_migration_upgrade_and_downgrade() -> None:
    """Verifies migration 202609111200 applies and rolls back cleanly."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    context = MigrationContext.configure(connection)
    operations = Operations(context)
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "202609111200_module8_sprint81_workflow_orchestration.py"
    )
    spec = importlib.util.spec_from_file_location("sprint81_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    connection.exec_driver_sql(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email VARCHAR(255),
            hashed_password VARCHAR(255),
            is_active BOOLEAN,
            is_verified BOOLEAN
        )
        """
    )
    module.op = operations
    module.upgrade()
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    assert "workflows" in tables
    assert "workflow_runs" in tables
    assert "workflow_step_executions" in tables
    assert "workflow_audit_logs" in tables

    module.downgrade()
    inspector = inspect(connection)
    tables_after = inspector.get_table_names()
    assert "workflows" not in tables_after
    assert "workflow_runs" not in tables_after
    connection.close()


def test_workflow_runs_filtering_and_details_api() -> None:
    """Verifies listing runs with filtering and inspecting run details with timeline."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        wf = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Filtering Pipeline",
                "steps": [
                    {"step_order": 1, "name": "Ping", "step_type": "HTTP_INTERNAL", "config_json": {"endpoint": "/api/v1/health"}},
                ],
            },
        ).json()
        wf_id = wf["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        run = client.post(f"/api/v1/workflows/{wf_id}/run", headers=headers, json={}).json()
        run_id = run["id"]

        # List runs with filter
        runs_list = client.get(f"/api/v1/workflow-runs?workflow_id={wf_id}&status=succeeded", headers=headers)
        assert runs_list.status_code == 200
        assert len(runs_list.json()) >= 1

        # Get run detail
        run_detail = client.get(f"/api/v1/workflow-runs/{run_id}", headers=headers)
        assert run_detail.status_code == 200
        assert run_detail.json()["id"] == run_id
        assert len(run_detail.json()["step_executions"]) == 1

        # Non-existent run
        non_run = client.get(f"/api/v1/workflow-runs/{uuid4()}", headers=headers)
        assert non_run.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_workflow_triggers_and_schedules_listing_and_audits() -> None:
    """Verifies listing triggers, schedules, and audit logs."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        wf = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Audit Test WF",
                "steps": [
                    {"step_order": 1, "name": "Ping", "step_type": "HTTP_INTERNAL", "config_json": {"endpoint": "/api/v1/health"}},
                ],
            },
        ).json()
        wf_id = wf["id"]

        # Create trigger
        client.post(
            f"/api/v1/workflows/{wf_id}/triggers",
            headers=headers,
            json={"trigger_type": "manual", "name": "Manual Ingest"},
        )
        # Create schedule
        client.post(
            f"/api/v1/workflows/{wf_id}/schedules",
            headers=headers,
            json={"schedule_type": "recurring", "cron_expression": "0 0 * * *"},
        )

        triggers = client.get(f"/api/v1/workflows/{wf_id}/triggers", headers=headers)
        assert triggers.status_code == 200
        assert len(triggers.json()) == 1

        schedules = client.get(f"/api/v1/workflows/{wf_id}/schedules", headers=headers)
        assert schedules.status_code == 200
        assert len(schedules.json()) == 1

        audits = client.get(f"/api/v1/workflows/{wf_id}/audit", headers=headers)
        assert audits.status_code == 200
        assert len(audits.json()) >= 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_workflow_error_cases_and_validations() -> None:
    """Tests 404, 400 invalid state transitions, and step validation errors."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        # 404 for missing workflow
        missing_wf = client.get(f"/api/v1/workflows/{uuid4()}", headers=headers)
        assert missing_wf.status_code == 404

        # Cannot activate workflow with 0 steps
        empty_wf = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={"name": "Empty WF", "steps": []},
        ).json()
        empty_act = client.post(f"/api/v1/workflows/{empty_wf['id']}/activate", headers=headers)
        assert empty_act.status_code == 400
        assert "at least one step" in empty_act.text

        # Cannot pause non-active workflow
        bad_pause = client.post(f"/api/v1/workflows/{empty_wf['id']}/pause", headers=headers)
        assert bad_pause.status_code == 400

        # Updating partial fields
        patch_resp = client.patch(
            f"/api/v1/workflows/{empty_wf['id']}",
            headers=headers,
            json={
                "name": "Updated Empty WF",
                "workflow_type": "batch",
                "is_enabled": False,
                "timeout_seconds": 1800,
                "retry_policy": {"max_retries": 2, "retry_delay_seconds": 10, "exponential_backoff": True},
            },
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Updated Empty WF"
        assert patch_resp.json()["is_enabled"] is False
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_step_handler_delay_and_conditionals() -> None:
    """Tests DELAY step execution and CONDITIONAL step operations (==, !=, in, exists)."""
    db = make_db()
    client = make_client(db)
    try:
        admin = create_user(db, "admin")
        headers = auth_headers(admin)

        wf = client.post(
            "/api/v1/workflows",
            headers=headers,
            json={
                "name": "Delay and Condition WF",
                "steps": [
                    {"step_order": 1, "name": "Short Delay", "step_type": "DELAY", "config_json": {"delay_seconds": 1}},
                    {"step_order": 2, "name": "Check In List", "step_type": "CONDITIONAL", "config_json": {"field": "target_env", "operator": "in", "value": ["staging", "prod"]}},
                    {"step_order": 3, "name": "Check Not Equal", "step_type": "CONDITIONAL", "config_json": {"field": "target_env", "operator": "!=", "value": "dev"}},
                    {"step_order": 4, "name": "Check Exists", "step_type": "CONDITIONAL", "config_json": {"field": "target_env", "operator": "exists"}},
                ],
            },
        ).json()
        wf_id = wf["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=headers)

        run = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            headers=headers,
            json={"input_metadata": {"target_env": "prod"}},
        ).json()

        assert run["status"] == "succeeded"
        assert len(run["step_executions"]) == 4
        # DELAY
        assert run["step_executions"][0]["output_json"]["elapsed"] is True
        # in
        assert run["step_executions"][1]["output_json"]["condition_met"] is True
        # !=
        assert run["step_executions"][2]["output_json"]["condition_met"] is True
        # exists
        assert run["step_executions"][3]["output_json"]["condition_met"] is True
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_partner_portal_users_forbidden() -> None:
    """Partner portal or non-staff user roles are strictly blocked with 403 Forbidden."""
    db = make_db()
    client = make_client(db)
    try:
        partner_user = create_user(db, "partner_admin")
        headers = auth_headers(partner_user)

        resp = client.get("/api/v1/workflows", headers=headers)
        assert resp.status_code == 403
        assert "Clearance required" in resp.text
    finally:
        app.dependency_overrides.clear()
        db.close()

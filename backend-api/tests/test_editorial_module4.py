from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.modules.cms.models import CMSContent, CMSLanguage, ContentType
from app.modules.editorial.models import EditorialNotification, EditorialWorkflow, WorkflowState


@pytest.fixture()
def editorial_client() -> Generator[tuple[TestClient, Session, dict[str, User | CMSContent]], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    roles = {name: Role(name=name) for name in ["admin", "editor", "reporter", "viewer"]}
    users: dict[str, User] = {}
    for index, name in enumerate(roles, start=1):
        user = User(id=index, email=f"{name}@gntv.example", hashed_password="x", is_active=True, is_verified=True)
        user.roles = [roles[name]]
        users[name] = user
        db.add(user)
    language = CMSLanguage(code="en", name="English")
    db.add(language)
    db.flush()
    content = CMSContent(
        title="Module 4 Story",
        slug="module-4-story",
        body="Initial copy",
        content_type=ContentType.ARTICLE,
        language_id=language.id,
        author_id=users["reporter"].id,
    )
    db.add(content)
    db.commit()
    context: dict[str, User | CMSContent] = {**users, "content": content}

    def override_db() -> Generator[Session, None, None]:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: users["admin"]
    try:
        yield TestClient(app), db, context
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_complete_editorial_api_lifecycle(editorial_client: tuple[TestClient, Session, dict[str, User | CMSContent]]) -> None:
    client, db, context = editorial_client
    content = context["content"]
    reporter = context["reporter"]
    assert isinstance(content, CMSContent) and isinstance(reporter, User)
    created = client.post(
        "/api/v1/editorial/workflows",
        json={"content_id": str(content.id), "priority": "high", "due_at": "2026-07-14T12:00:00+03:00"},
    )
    assert created.status_code == 201, created.text
    workflow = created.json()
    workflow_id = workflow["id"]
    assert workflow["state"] == "draft" and workflow["lock_version"] == 1
    assert client.get(f"/api/v1/editorial/workflows/{workflow_id}").status_code == 200

    assignment = client.put(
        f"/api/v1/editorial/workflows/{workflow_id}/assignments",
        json={"role": "reporter", "user_id": reporter.id},
    )
    assert assignment.status_code == 200 and assignment.json()["user_id"] == reporter.id
    assignment = client.put(
        f"/api/v1/editorial/workflows/{workflow_id}/assignments",
        json={"role": "editor", "user_id": context["editor"].id},
    )
    assert assignment.status_code == 200
    assert len(client.get(f"/api/v1/editorial/workflows/{workflow_id}/assignments").json()) == 2

    comment = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/comments",
        json={"kind": "review_note", "body": "Please verify the figures", "mentions": [reporter.id]},
    )
    assert comment.status_code == 201 and comment.json()["mentions"] == [reporter.id]
    assert len(client.get(f"/api/v1/editorial/workflows/{workflow_id}/comments").json()) == 1

    first = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/revisions",
        json={"snapshot": {"title": "Module 4 Story", "body": "First"}, "change_summary": "Initial revision", "expected_version": 1},
    )
    assert first.status_code == 201 and first.json()["version"] == 1
    second = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/revisions",
        json={"snapshot": {"title": "Updated Story", "body": "Second"}, "change_summary": "Copy edit", "expected_version": 2},
    )
    assert second.status_code == 201 and second.json()["version"] == 2
    comparison = client.get(
        f"/api/v1/editorial/workflows/{workflow_id}/revisions/compare",
        params={"from_version": 1, "to_version": 2},
    )
    assert comparison.status_code == 200 and set(comparison.json()["changes"]) == {"title", "body"}
    restored = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/revisions/1/restore",
        params={"expected_version": 3},
    )
    assert restored.status_code == 200 and restored.json()["version"] == 3
    assert len(client.get(f"/api/v1/editorial/workflows/{workflow_id}/revisions").json()) == 3

    planned = client.patch(
        f"/api/v1/editorial/workflows/{workflow_id}/planning",
        json={"priority": "urgent", "expected_version": 4},
    )
    assert planned.status_code == 200 and planned.json()["lock_version"] == 5
    stale = client.patch(
        f"/api/v1/editorial/workflows/{workflow_id}/planning",
        json={"priority": "low", "expected_version": 4},
    )
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "editorial_optimistic_lock_conflict"

    version = 5
    states = ["in_review", "fact_check", "legal_review", "editorial_approval", "approved"]
    for state in states:
        response = client.post(
            f"/api/v1/editorial/workflows/{workflow_id}/transitions",
            json={"target_state": state, "expected_version": version, "note": f"Move to {state}"},
        )
        assert response.status_code == 200, response.text
        version += 1
    publish_at = datetime.now(UTC) - timedelta(minutes=1)
    unpublish_at = datetime.now(UTC) + timedelta(hours=1)
    scheduled = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/schedule",
        json={
            "publish_at": publish_at.isoformat(),
            "timezone": "Africa/Nairobi",
            "embargo_at": (publish_at - timedelta(minutes=1)).isoformat(),
            "unpublish_at": unpublish_at.isoformat(),
            "expected_version": version,
        },
    )
    assert scheduled.status_code == 200 and scheduled.json()["state"] == "scheduled"
    processed = client.post("/api/v1/editorial/publishing/process-due")
    assert processed.status_code == 200 and processed.json()["published"] == 1
    current = client.get(f"/api/v1/editorial/workflows/{workflow_id}").json()
    assert current["state"] == "published"

    emergency = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/emergency-unpublish",
        json={"expected_version": current["lock_version"], "reason": "Legal injunction"},
    )
    assert emergency.status_code == 200 and emergency.json()["state"] == "expired"
    republished = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/republish",
        json={"expected_version": emergency.json()["lock_version"], "reason": "Cleared"},
    )
    assert republished.status_code == 200 and republished.json()["state"] == "published"

    assert client.get("/api/v1/editorial/dashboard/pending-reviews").status_code == 200
    assert client.get("/api/v1/editorial/dashboard/assigned-to-me").status_code == 200
    assert client.get("/api/v1/editorial/dashboard/scheduled-content").status_code == 200
    assert client.get("/api/v1/editorial/dashboard/publishing-queue").status_code == 200
    assert client.get("/api/v1/editorial/dashboard/failed-publications").status_code == 200
    assert len(client.get("/api/v1/editorial/dashboard/recent-activity").json()) > 10
    assert len(client.get(f"/api/v1/editorial/workflows/{workflow_id}/activity").json()) > 10
    notifications = client.get("/api/v1/editorial/notifications").json()
    assert {item["channel"] for item in notifications} == {"in_app", "email", "webhook"}
    assert db.query(AuditLog).filter(AuditLog.event_type.like("editorial.%")).count() > 10
    assert db.query(EditorialNotification).count() >= 3
    schema = client.get("/openapi.json").json()
    assert f"/api/v1/editorial/workflows/{'{'}workflow_id{'}'}/transitions" in schema["paths"]


def test_editorial_validation_rbac_and_error_paths(editorial_client: tuple[TestClient, Session, dict[str, User | CMSContent]]) -> None:
    client, db, context = editorial_client
    content = context["content"]
    assert isinstance(content, CMSContent)
    created = client.post("/api/v1/editorial/workflows", json={"content_id": str(content.id)}).json()
    workflow_id = created["id"]
    assert client.post("/api/v1/editorial/workflows", json={"content_id": str(content.id)}).status_code == 409
    assert client.post("/api/v1/editorial/workflows", json={"content_id": str(uuid4())}).status_code == 404
    assert client.get(f"/api/v1/editorial/workflows/{uuid4()}").status_code == 404
    assert client.put(
        f"/api/v1/editorial/workflows/{workflow_id}/assignments", json={"role": "producer", "user_id": 9999}
    ).status_code == 404
    assert client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/comments", json={"body": "Hello @missing", "mentions": [9999]}
    ).status_code == 404
    assert client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/transitions",
        json={"target_state": "published", "expected_version": 1},
    ).status_code == 422
    assert client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/schedule",
        json={"publish_at": datetime.now(UTC).isoformat(), "timezone": "Africa/Nairobi", "expected_version": 1},
    ).status_code == 422
    assert client.get(
        f"/api/v1/editorial/workflows/{workflow_id}/revisions/compare", params={"from_version": 1, "to_version": 2}
    ).status_code == 404
    assert client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/revisions/1/restore", params={"expected_version": 1}
    ).status_code == 404
    assert client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/publish", json={"expected_version": 1}
    ).status_code == 422
    assert client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/emergency-unpublish", json={"expected_version": 1}
    ).status_code == 422
    invalid_timezone = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/schedule",
        json={"publish_at": "2026-07-14T12:00:00+03:00", "timezone": "Mars/Olympus", "expected_version": 1},
    )
    assert invalid_timezone.status_code == 422

    viewer = context["viewer"]
    assert isinstance(viewer, User)
    app.dependency_overrides[get_current_user] = lambda: viewer
    assert client.get(f"/api/v1/editorial/workflows/{workflow_id}").status_code == 403
    assert client.post("/api/v1/editorial/workflows", json={"content_id": str(uuid4())}).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: context["reporter"]
    assert client.post("/api/v1/editorial/publishing/process-due").status_code == 403
    db.rollback()


def test_rejection_requires_reason_and_auto_unpublish(editorial_client: tuple[TestClient, Session, dict[str, User | CMSContent]]) -> None:
    client, db, context = editorial_client
    content = context["content"]
    assert isinstance(content, CMSContent)
    item = client.post(
        "/api/v1/editorial/workflows",
        json={"content_id": str(content.id), "due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    ).json()
    workflow_id = item["id"]
    moved = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/transitions",
        json={"target_state": "in_review", "expected_version": 1},
    ).json()
    reminders = client.post("/api/v1/editorial/notifications/review-reminders")
    assert reminders.status_code == 200 and len(reminders.json()) == 3
    rejected = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/transitions",
        json={"target_state": "draft", "expected_version": moved["lock_version"]},
    )
    assert rejected.status_code == 422
    accepted = client.post(
        f"/api/v1/editorial/workflows/{workflow_id}/transitions",
        json={"target_state": "draft", "expected_version": moved["lock_version"], "note": "Needs sourcing"},
    )
    assert accepted.status_code == 200
    workflow_uuid = UUID(workflow_id)
    workflow = db.get(EditorialWorkflow, workflow_uuid)
    assert workflow is not None
    workflow.state = WorkflowState.PUBLISHED
    workflow.unpublish_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    result = client.post("/api/v1/editorial/publishing/process-due").json()
    assert result["unpublished"] == 1
    assert db.get(EditorialWorkflow, workflow_uuid).state == WorkflowState.EXPIRED  # type: ignore[union-attr]

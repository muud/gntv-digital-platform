"""Comprehensive test suite for Module 8 Sprint 8.2: Event Bus, Secure Webhooks & Automation Triggers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.events.bus import (
    InMemoryEventBus,
    matches_event_pattern,
)
from app.modules.events.models import (
    DeadLetterStatus,
    DomainEvent,
    EventProcessingStatus,
    OutboundDeliveryStatus,
)
from app.modules.events.repository import EventRepository
from app.modules.events.schemas import (
    EventPublishRequest,
    OutboundSubscriptionCreateRequest,
    WebhookSourceCreateRequest,
    WebhookSourceUpdateRequest,
)
from app.modules.events.security import (
    compute_hmac_sha256,
    decrypt_secret,
    encrypt_secret,
    sanitize_payload,
    verify_hmac_signature,
)
from app.modules.events.service import (
    EventService,
    evaluate_trigger_filters,
)
from app.modules.events.ssrf import (
    SSRFValidationError,
    is_ip_private_or_restricted,
    validate_outbound_url,
)
from app.modules.workflows.models import (
    Workflow,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepDefinition,
    WorkflowStepType,
    WorkflowTrigger,
    WorkflowTriggerType,
)
from app.utils.jwt import create_access_token


def make_db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id), additional_claims={"email": user.email})
    return {"Authorization": f"Bearer {token}"}


class MockHTTPClient:
    def __init__(self, status_code: int = 200, text: str = '{"ok": true}') -> None:
        self.status_code = status_code
        self.text = text
        self.calls: list[dict] = []

    def post(self, url: str, content: bytes, headers: dict) -> httpx.Response:
        self.calls.append({"url": url, "content": content, "headers": headers})
        req = httpx.Request("POST", url, headers=headers, content=content)
        return httpx.Response(self.status_code, text=self.text, request=req)


# =====================================================================
# 1. SSRF Protection Tests
# =====================================================================
def test_ssrf_blocks_private_ips() -> None:
    assert is_ip_private_or_restricted("127.0.0.1") is True
    assert is_ip_private_or_restricted("10.0.0.1") is True
    assert is_ip_private_or_restricted("192.168.1.100") is True
    assert is_ip_private_or_restricted("172.16.0.5") is True
    assert is_ip_private_or_restricted("169.254.169.254") is True
    assert is_ip_private_or_restricted("::1") is True
    assert is_ip_private_or_restricted("8.8.8.8") is False


def test_validate_outbound_url_rejections() -> None:
    # Scheme
    with pytest.raises(SSRFValidationError, match="Invalid scheme"):
        validate_outbound_url("ftp://webhook.example.com/endpoint")

    # Localhost
    with pytest.raises(SSRFValidationError, match="forbidden by SSRF security policy"):
        validate_outbound_url("https://localhost/webhook")

    # 127.0.0.1
    with pytest.raises(SSRFValidationError, match="forbidden by SSRF security policy"):
        validate_outbound_url("https://127.0.0.1/webhook")

    # Cloud metadata
    with pytest.raises(SSRFValidationError, match="forbidden by SSRF security policy"):
        validate_outbound_url("https://169.254.169.254/latest/meta-data")

    # Private IP
    with pytest.raises(SSRFValidationError, match="restricted"):
        validate_outbound_url("https://10.20.30.40/webhook")

    # Invalid port
    with pytest.raises(SSRFValidationError, match="Port 22 is not permitted"):
        validate_outbound_url("https://webhook.example.com:22/listen")

    # Valid external URL
    assert (
        validate_outbound_url(
            "https://webhook.site/abc-123", allow_private_for_tests=True
        )
        == "https://webhook.site/abc-123"
    )


# =====================================================================
# 2. Security & Sanitization Tests
# =====================================================================
def test_recursive_payload_sanitization() -> None:
    raw = {
        "title": "Evening News",
        "api_key": "live_secret_key_123",
        "nested": {
            "password": "Password123!",
            "client_secret": "super_secret",
            "safe_field": 42,
            "card": {"credit_card": "4111222233334444", "cvv": "123"},
        },
        "items": [
            {"token": "jwt_token_here", "name": "item1"},
            {"name": "item2"},
        ],
    }

    sanitized = sanitize_payload(raw)
    assert sanitized["title"] == "Evening News"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["client_secret"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == 42
    assert sanitized["nested"]["card"]["credit_card"] == "[REDACTED]"
    assert sanitized["nested"]["card"]["cvv"] == "[REDACTED]"
    assert sanitized["items"][0]["token"] == "[REDACTED]"
    assert sanitized["items"][0]["name"] == "item1"


def test_hmac_signing_and_verification() -> None:
    secret = "my_high_entropy_secret_1234567890"
    payload = b'{"event": "content.published", "id": 100}'

    sig = compute_hmac_sha256(secret, payload, include_prefix=True)
    assert sig.startswith("sha256=")

    # Verify matching
    assert verify_hmac_signature(secret, payload, sig) is True
    # Verify without sha256= prefix
    assert verify_hmac_signature(secret, payload, sig[7:]) is True

    # Tampered body fails
    assert verify_hmac_signature(secret, b'{"event": "tampered"}', sig) is False
    # Wrong secret fails
    assert verify_hmac_signature("wrong_secret", payload, sig) is False


def test_aes_secret_encryption_roundtrip() -> None:
    raw_secret = "secret_key_to_be_sealed"
    ct, nonce = encrypt_secret(
        raw_secret, master_key="test_master_key_1234567890123456"
    )
    assert ct != raw_secret

    decrypted = decrypt_secret(ct, nonce, master_key="test_master_key_1234567890123456")
    assert decrypted == raw_secret


# =====================================================================
# 3. Pattern Matching & Event Bus Tests
# =====================================================================
def test_matches_event_pattern() -> None:
    assert matches_event_pattern("*", "content.published") is True
    assert matches_event_pattern("content.*", "content.published") is True
    assert matches_event_pattern("content.*", "content.updated") is True
    assert matches_event_pattern("content.*", "partner.activated") is False
    assert matches_event_pattern("content.published", "content.published") is True
    assert matches_event_pattern("content.published", "content.updated") is False


def test_in_memory_event_bus_delivery() -> None:
    db = make_db()
    bus = InMemoryEventBus()
    received_events = []

    def handler_all(event: DomainEvent, session: Session) -> None:
        received_events.append(("all", event.event_type))

    def handler_content(event: DomainEvent, session: Session) -> None:
        received_events.append(("content", event.event_type))

    bus.subscribe("*", handler_all)
    bus.subscribe("content.*", handler_content)

    event = EventRepository.create_event(
        db,
        event_type="content.published",
        event_version=1,
        source="cms",
        tenant_id="gntv",
        aggregate_type="article",
        aggregate_id="art-1",
        correlation_id=uuid4().hex,
        causation_id=None,
        idempotency_key="idemp-1",
        payload_json={"title": "Hello World"},
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
    )

    bus.publish(db, event)
    assert len(received_events) == 2
    assert ("all", "content.published") in received_events
    assert ("content", "content.published") in received_events
    assert event.status == EventProcessingStatus.PROCESSED


def test_event_bus_failure_to_dlq() -> None:
    db = make_db()
    bus = InMemoryEventBus()

    def failing_handler(event: DomainEvent, session: Session) -> None:
        raise RuntimeError("Fatal processing crash")

    bus.subscribe("crash.*", failing_handler)

    event = EventRepository.create_event(
        db,
        event_type="crash.event",
        event_version=1,
        source="test",
        tenant_id=None,
        aggregate_type=None,
        aggregate_id=None,
        correlation_id=uuid4().hex,
        causation_id=None,
        idempotency_key="crash-idemp",
        payload_json={},
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        max_retries=1,
    )

    # First attempt fails
    bus.publish(db, event)
    assert event.status == EventProcessingStatus.DEAD_LETTERED
    dlq = EventRepository.list_dead_letters(db)
    assert len(dlq) == 1
    assert dlq[0].event_id == event.id
    assert "Fatal processing crash" in dlq[0].reason


# =====================================================================
# 4. Safe Filter Evaluation Tests
# =====================================================================
def test_safe_filter_evaluation() -> None:
    payload = {
        "status": "published",
        "category": "news",
        "score": 95,
        "tags": ["live", "breaking"],
    }

    # Simple dict equality
    allowed = {"status", "category", "score"}
    assert evaluate_trigger_filters({"status": "published"}, payload, allowed) is True
    assert evaluate_trigger_filters({"status": "draft"}, payload, allowed) is False

    # Rule list
    rules = [
        {"field": "status", "op": "==", "value": "published"},
        {"field": "category", "op": "==", "value": "news"},
        {"field": "score", "op": "==", "value": 95},
    ]
    assert evaluate_trigger_filters({"rules": rules}, payload, allowed) is True

    # Failing rule
    failing_rules = [
        {"field": "status", "op": "==", "value": "published"},
        {"field": "category", "op": "==", "value": "sports"},
    ]
    assert evaluate_trigger_filters({"rules": failing_rules}, payload, allowed) is False


# =====================================================================
# 5. Automation Workflow Triggers Integration Tests
# =====================================================================
def test_event_triggers_active_workflow() -> None:
    db = make_db()
    service = EventService()

    # Create active workflow with internal event trigger
    wf = Workflow(
        name="Auto-Publish Social Distribution",
        status=WorkflowStatus.ACTIVE,
        is_enabled=True,
        timeout_seconds=300,
    )
    step1 = WorkflowStepDefinition(
        step_order=1,
        name="Send Notification",
        step_type=WorkflowStepType.NOTIFICATION_EVENT,
        is_required=True,
    )
    trigger = WorkflowTrigger(
        trigger_type=WorkflowTriggerType.INTERNAL_EVENT,
        name="On Content Published",
        event_pattern="content.published",
        is_enabled=True,
        metadata_json={
            "filters": {"status": "approved"},
            "allowed_payload_fields": ["status"],
        },
    )
    wf.steps.append(step1)
    wf.triggers.append(trigger)
    db.add(wf)
    db.commit()

    # Publish non-matching event (different event type)
    service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.drafted",
            source="cms",
            payload={"status": "approved"},
        ),
    )
    runs_ev1 = db.query(WorkflowRun).all()
    assert len(runs_ev1) == 0

    # Publish non-matching filter (status != approved)
    service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.published",
            source="cms",
            payload={"status": "pending"},
        ),
    )
    runs_ev2 = db.query(WorkflowRun).all()
    assert len(runs_ev2) == 0

    # Publish matching event
    ev3 = service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.published",
            source="cms",
            payload={"status": "approved", "article_id": "art-99"},
        ),
    )
    runs_ev3 = db.query(WorkflowRun).all()
    assert len(runs_ev3) == 1
    run = runs_ev3[0]
    assert run.workflow_id == wf.id
    assert run.idempotency_key == f"evt-{ev3.id}-wf-{wf.id}"
    assert run.input_metadata_json["correlation_id"] == ev3.correlation_id
    assert run.input_metadata_json["event_type"] == "content.published"


def test_inactive_workflows_never_triggered() -> None:
    db = make_db()
    service = EventService()

    # Draft workflow
    wf_draft = Workflow(
        name="Draft Workflow",
        status=WorkflowStatus.DRAFT,
        is_enabled=True,
    )
    wf_draft.steps.append(
        WorkflowStepDefinition(
            step_order=1, name="Step", step_type=WorkflowStepType.NOTIFICATION_EVENT
        )
    )
    wf_draft.triggers.append(
        WorkflowTrigger(
            trigger_type=WorkflowTriggerType.INTERNAL_EVENT,
            name="Trigger",
            event_pattern="*",
            is_enabled=True,
        )
    )

    # Paused workflow
    wf_paused = Workflow(
        name="Paused Workflow",
        status=WorkflowStatus.PAUSED,
        is_enabled=True,
    )
    wf_paused.steps.append(
        WorkflowStepDefinition(
            step_order=1, name="Step", step_type=WorkflowStepType.NOTIFICATION_EVENT
        )
    )
    wf_paused.triggers.append(
        WorkflowTrigger(
            trigger_type=WorkflowTriggerType.INTERNAL_EVENT,
            name="Trigger",
            event_pattern="*",
            is_enabled=True,
        )
    )

    db.add(wf_draft)
    db.add(wf_paused)
    db.commit()

    service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.published",
            source="cms",
            payload={},
        ),
    )

    runs = db.query(WorkflowRun).all()
    assert len(runs) == 0


# =====================================================================
# 6. Inbound Webhooks API Tests
# =====================================================================
def test_inbound_webhook_full_flow() -> None:
    db = make_db()
    client = make_client(db)
    operator = create_user(db, "operator")
    headers = auth_headers(operator)

    # 1. Register Webhook Source
    create_resp = client.post(
        "/api/v1/webhook-sources",
        headers=headers,
        json={
            "source_key": "github-partner",
            "name": "GitHub Partner Ingestion",
            "provider_type": "hmac_sha256",
            "header_name": "X-Hub-Signature-256",
            "timestamp_header": "X-GNTV-Timestamp",
            "timestamp_tolerance_seconds": 300,
            "event_type_mapping": {"push": "partner.code.pushed"},
            "secret": "github_test_secret_1234567890",
        },
    )
    assert create_resp.status_code == 201
    source_data = create_resp.json()
    secret = "github_test_secret_1234567890"
    assert "secret" not in source_data

    # Secret is never disclosed on subsequent GET
    get_resp = client.get(
        f"/api/v1/webhook-sources/{source_data['id']}", headers=headers
    )
    assert get_resp.status_code == 200
    assert "secret" not in get_resp.json()

    # 2. Receive valid webhook
    now_ts = str(int(datetime.now(UTC).timestamp()))
    payload_dict = {"type": "push", "ref": "refs/heads/main", "commit": "abc1234"}
    body_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = compute_hmac_sha256(secret, body_bytes, include_prefix=True)

    webhook_resp = client.post(
        "/api/v1/webhooks/github-partner",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GNTV-Timestamp": now_ts,
            "X-Event-ID": "ext-evt-12345",
        },
    )
    assert webhook_resp.status_code == 202
    wh_data = webhook_resp.json()
    assert wh_data["status"] == "accepted"
    assert wh_data["mapped_event_type"] == "partner.code.pushed"

    # 3. Duplicate delivery fingerprint is rejected with 409
    dup_resp = client.post(
        "/api/v1/webhooks/github-partner",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GNTV-Timestamp": now_ts,
            "X-Event-ID": "ext-evt-12345",
        },
    )
    assert dup_resp.status_code == 409
    assert "Duplicate webhook delivery detected" in dup_resp.json()["detail"]

    # 4. Bad signature rejected with 400
    bad_sig_resp = client.post(
        "/api/v1/webhooks/github-partner",
        content=b'{"type": "push"}',
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=invalid000000000000000000000000000000000000000000000000000000000",
            "X-GNTV-Timestamp": str(int(datetime.now(UTC).timestamp())),
        },
    )
    assert bad_sig_resp.status_code == 400
    assert "Invalid HMAC signature" in bad_sig_resp.json()["detail"]

    # 5. Expired timestamp rejected with 400
    old_ts = str(int((datetime.now(UTC) - timedelta(seconds=600)).timestamp()))
    old_body = b'{"type": "push"}'
    old_sig = compute_hmac_sha256(secret, old_body, include_prefix=True)
    expired_resp = client.post(
        "/api/v1/webhooks/github-partner",
        content=old_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": old_sig,
            "X-GNTV-Timestamp": old_ts,
        },
    )
    assert expired_resp.status_code == 400
    assert "Timestamp tolerance exceeded" in expired_resp.json()["detail"]

    # 6. Unknown source returns 404
    missing_src_resp = client.post(
        "/api/v1/webhooks/nonexistent-source",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert missing_src_resp.status_code == 404


# =====================================================================
# 7. Outbound Webhooks & DLQ Tests
# =====================================================================
def test_outbound_webhook_dispatch_and_dlq() -> None:
    db = make_db()
    mock_http = MockHTTPClient(status_code=200)
    service = EventService(http_client=mock_http, allow_test_urls=True)

    # 1. Create outbound subscription
    sub, raw_secret = service.create_outbound_subscription(
        db,
        OutboundSubscriptionCreateRequest(
            name="External Notification Webhook",
            endpoint_url="https://webhook.site/test-endpoint",
            event_patterns=["content.*"],
            secret="outbound_test_secret_123456789",
            max_retries=2,
            timeout_seconds=5,
        ),
    )

    # 2. Publish matching event
    event = service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.published",
            source="cms",
            payload={"article_id": "123"},
        ),
    )

    deliveries = EventRepository.list_outbound_deliveries(db, event_id=event.id)
    assert len(deliveries) == 1
    assert deliveries[0].status == OutboundDeliveryStatus.DELIVERED
    assert len(mock_http.calls) == 1
    assert "X-Hub-Signature-256" in mock_http.calls[0]["headers"]


def test_outbound_webhook_exhausted_retries_to_dlq() -> None:
    db = make_db()
    mock_http = MockHTTPClient(status_code=500, text="Internal Server Error")
    service = EventService(http_client=mock_http, allow_test_urls=True)

    sub, _ = service.create_outbound_subscription(
        db,
        OutboundSubscriptionCreateRequest(
            name="Failing Partner Webhook",
            endpoint_url="https://webhook.site/failing",
            event_patterns=["system.*"],
            secret="outbound_test_secret_123456789",
            max_retries=1,
            timeout_seconds=5,
        ),
    )

    event = service.publish_event(
        db,
        EventPublishRequest(
            event_type="system.alert",
            source="monitoring",
            payload={"severity": "high"},
        ),
    )

    deliveries = EventRepository.list_outbound_deliveries(db, event_id=event.id)
    assert len(deliveries) == 1
    assert deliveries[0].status == OutboundDeliveryStatus.DEAD_LETTERED

    dlqs = EventRepository.list_dead_letters(db)
    assert len(dlqs) == 1
    assert dlqs[0].outbound_delivery_id == deliveries[0].id


def test_dlq_operator_retry_and_dismiss() -> None:
    db = make_db()
    client = make_client(db)
    operator = create_user(db, "operator")
    headers = auth_headers(operator)

    dlq = EventRepository.create_dead_letter(
        db,
        event_id=None,
        outbound_delivery_id=None,
        reason="Manual test error",
    )
    db.commit()

    # List DLQs
    list_resp = client.get("/api/v1/event-dead-letters", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Retry DLQ
    retry_resp = client.post(
        f"/api/v1/event-dead-letters/{dlq.id}/retry", headers=headers
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "retried"

    # Reset to pending to test dismiss
    dlq.status = DeadLetterStatus.PENDING
    db.commit()

    dismiss_resp = client.post(
        f"/api/v1/event-dead-letters/{dlq.id}/dismiss", headers=headers
    )
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["status"] == "dismissed"


# =====================================================================
# 8. Event Trace & Metrics Tests
# =====================================================================
def test_event_trace_endpoint() -> None:
    db = make_db()
    client = make_client(db)
    operator = create_user(db, "operator")
    headers = auth_headers(operator)
    service = EventService()

    corr_id = uuid4().hex
    event = service.publish_event(
        db,
        EventPublishRequest(
            event_type="test.trace.event",
            source="test",
            correlation_id=corr_id,
            payload={"msg": "trace me"},
        ),
    )
    db.commit()

    trace_resp = client.get(f"/api/v1/events/trace/{corr_id}", headers=headers)
    assert trace_resp.status_code == 200
    trace_json = trace_resp.json()
    assert trace_json["correlation_id"] == corr_id
    assert trace_json["event"]["id"] == str(event.id)

    metrics_resp = client.get("/api/v1/events/metrics/summary", headers=headers)
    assert metrics_resp.status_code == 200
    assert metrics_resp.json()["total_events"] >= 1


# =====================================================================
# 9. RBAC Clearance Tests
# =====================================================================
def test_rbac_clearance() -> None:
    db = make_db()
    client = make_client(db)
    viewer = create_user(db, "viewer")
    headers = auth_headers(viewer)

    # Viewer cannot publish events
    pub_resp = client.post(
        "/api/v1/events/publish",
        headers=headers,
        json={"event_type": "viewer.event", "source": "test", "payload": {}},
    )
    assert pub_resp.status_code == 403

    # Viewer cannot register webhook sources
    src_resp = client.post(
        "/api/v1/webhook-sources",
        headers=headers,
        json={"source_key": "viewer-source", "name": "V", "secret": "1234567890123456"},
    )
    assert src_resp.status_code == 403

    # Unauthenticated rejected
    unauth_resp = client.get("/api/v1/events")
    assert unauth_resp.status_code == 401


def test_operator_api_inventory_and_error_paths() -> None:
    """Exercise the operator read models without exposing write-only secrets."""
    db = make_db()
    client = make_client(db)
    operator = create_user(db, "operator")
    headers = auth_headers(operator)

    published = client.post(
        "/api/v1/events/publish",
        headers=headers,
        json={
            "event_type": "content.updated",
            "source": "cms",
            "idempotency_key": "operator-api-event",
            "payload": {"password": "never-store", "title": "Safe"},
        },
    )
    assert published.status_code == 201
    event_id = published.json()["id"]
    assert published.json()["payload_json"]["password"] == "[REDACTED]"
    assert client.get("/api/v1/events", headers=headers).status_code == 200
    assert client.get(f"/api/v1/events/{event_id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/events/{uuid4()}", headers=headers).status_code == 404
    rejected = client.post(
        "/api/v1/events/publish",
        headers=headers,
        json={"event_type": "unknown.not-registered", "source": "test"},
    )
    assert rejected.status_code == 400

    source_secret = "operator_source_secret_123456"
    source = client.post(
        "/api/v1/webhook-sources",
        headers=headers,
        json={
            "source_key": "operator-source",
            "name": "Operator Source",
            "secret": source_secret,
            "event_type_mapping": {"updated": "content.updated"},
        },
    )
    assert source.status_code == 201
    source_id = source.json()["id"]
    assert "secret" not in source.json()
    assert client.get("/api/v1/webhook-sources", headers=headers).status_code == 200
    assert client.get(
        f"/api/v1/webhook-sources/{source_id}", headers=headers
    ).status_code == 200
    patched = client.patch(
        f"/api/v1/webhook-sources/{source_id}",
        headers=headers,
        json={"name": "Renamed Source", "payload_size_limit_bytes": 2048},
    )
    assert patched.status_code == 200
    assert patched.json()["payload_size_limit_bytes"] == 2048
    assert client.get(
        f"/api/v1/webhook-sources/{uuid4()}", headers=headers
    ).status_code == 404

    body = json.dumps({"type": "updated", "title": "Signed"}).encode()
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signature = compute_hmac_sha256(source_secret, body)
    accepted = client.post(
        "/api/v1/webhooks/operator-source",
        content=body,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GNTV-Timestamp": timestamp,
            "X-Event-ID": "operator-delivery-1",
        },
    )
    assert accepted.status_code == 202
    deliveries = client.get("/api/v1/webhook-deliveries", headers=headers)
    assert deliveries.status_code == 200
    delivery_id = deliveries.json()[0]["id"]
    assert client.get(
        f"/api/v1/webhook-deliveries/{delivery_id}", headers=headers
    ).status_code == 200
    assert client.get(
        f"/api/v1/webhook-deliveries/{uuid4()}", headers=headers
    ).status_code == 404

    subscription = client.post(
        "/api/v1/outbound-webhooks/subscriptions",
        headers=headers,
        json={
            "name": "Public Endpoint",
            "endpoint_url": "https://8.8.8.8/hooks",
            "event_patterns": ["payout.*"],
            "secret": "outbound_operator_secret_1234",
        },
    )
    assert subscription.status_code == 201
    assert client.get(
        "/api/v1/outbound-webhooks/subscriptions", headers=headers
    ).status_code == 200
    assert client.get(
        "/api/v1/outbound-webhooks/deliveries", headers=headers
    ).status_code == 200


def test_defensive_service_and_bus_paths() -> None:
    db = make_db()
    service = EventService()
    with pytest.raises(ValueError, match="not found"):
        service.update_webhook_source(db, uuid4(), object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not found"):
        service.retry_dead_letter(db, uuid4())
    with pytest.raises(ValueError, match="not found"):
        service.dismiss_dead_letter(db, uuid4())

    bus = InMemoryEventBus()
    event = EventRepository.create_event(
        db,
        event_type="content.failed",
        event_version=1,
        source="test",
        tenant_id=None,
        aggregate_type=None,
        aggregate_id=None,
        correlation_id="bus-correlation",
        causation_id=None,
        idempotency_key="bus-ack",
        payload_json={},
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        status=EventProcessingStatus.PENDING,
    )
    assert bus.dispatch(db, event).status == EventProcessingStatus.PROCESSED
    event.status = EventProcessingStatus.PENDING
    assert bus.acknowledge(db, event).status == EventProcessingStatus.PROCESSED
    event.status = EventProcessingStatus.PENDING
    assert bus.retry(db, event).status == EventProcessingStatus.PROCESSED


def test_service_webhook_edge_cases_and_metrics() -> None:
    db = make_db()
    service = EventService()

    # 1. Duplicate source key
    service.create_webhook_source(
        db,
        WebhookSourceCreateRequest(
            source_key="unique-src-1",
            name="Unique 1",
            secret="super-secret-12345678",
        ),
    )
    with pytest.raises(ValueError, match="already exists"):
        service.create_webhook_source(
            db,
            WebhookSourceCreateRequest(
                source_key="unique-src-1",
                name="Duplicate",
                secret="super-secret-12345678",
            ),
        )

    # 2. Update webhook source various fields
    src = EventRepository.get_webhook_source_by_key(db, "unique-src-1")
    assert src is not None
    updated_src = service.update_webhook_source(
        db,
        src.id,
        WebhookSourceUpdateRequest(
            name="Updated Name",
            description="Updated Desc",
            header_name="X-Custom-Sig",
            timestamp_header="X-Custom-TS",
            timestamp_tolerance_seconds=120,
            payload_size_limit_bytes=512,
            event_type_mapping={"custom": "event.custom"},
            is_enabled=False,
        ),
    )
    assert updated_src.name == "Updated Name"
    assert updated_src.is_enabled is False

    # 3. Webhook with disabled source
    body = json.dumps({"custom": True}).encode()
    status, res = service.handle_inbound_webhook(
        db,
        source_key="unique-src-1",
        headers={"x-custom-sig": "dummy", "x-custom-ts": "1000"},
        raw_body=body,
    )
    assert status == 403
    assert "disabled" in res["detail"]

    # Re-enable source
    service.update_webhook_source(
        db,
        src.id,
        WebhookSourceUpdateRequest(is_enabled=True),
    )

    # 4. Webhook payload size limit exceeded
    large_body = b"x" * 1024
    status_large, res_large = service.handle_inbound_webhook(
        db,
        source_key="unique-src-1",
        headers={"x-custom-sig": "dummy", "x-custom-ts": str(int(datetime.now(UTC).timestamp()))},
        raw_body=large_body,
    )
    assert status_large == 413
    assert "exceeds" in res_large["detail"]

    # 5. Missing signature header
    status_nosig, res_nosig = service.handle_inbound_webhook(
        db,
        source_key="unique-src-1",
        headers={"x-custom-ts": str(int(datetime.now(UTC).timestamp()))},
        raw_body=body,
    )
    assert status_nosig == 400
    assert "Missing signature header" in res_nosig["detail"]

    # 6. Replay protection (duplicate delivery)
    status_dup, res_dup = service.handle_inbound_webhook(
        db,
        source_key="unique-src-1",
        headers={"x-custom-sig": "any", "x-custom-ts": str(int(datetime.now(UTC).timestamp()))},
        raw_body=body,
    )
    assert status_dup == 409
    assert "Duplicate" in res_dup["detail"]

    # 7. Invalid signature with fresh body
    body_badsig = json.dumps({"custom": "different"}).encode()
    status_badsig, res_badsig = service.handle_inbound_webhook(
        db,
        source_key="unique-src-1",
        headers={"x-custom-sig": "invalid-signature", "x-custom-ts": str(int(datetime.now(UTC).timestamp()))},
        raw_body=body_badsig,
    )
    assert status_badsig == 400
    assert "Invalid HMAC signature" in res_badsig["detail"]

    # 7. Duplicate event publish returns existing event
    ev1 = service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.published",
            source="test",
            idempotency_key="same-key-1",
            payload={"id": "abc"},
        ),
    )
    ev2 = service.publish_event(
        db,
        EventPublishRequest(
            event_type="content.published",
            source="test",
            idempotency_key="same-key-1",
            payload={"id": "abc-different"},
        ),
    )
    assert ev1.id == ev2.id

    # 8. SSRF edge cases
    with pytest.raises(SSRFValidationError, match="scheme"):
        validate_outbound_url("ftp://example.com")
    with pytest.raises(SSRFValidationError, match="port"):
        validate_outbound_url("https://example.com:99999")
    with pytest.raises(SSRFValidationError):
        validate_outbound_url("https://invalid...domain...nowhere...local")

    # 9. Metrics retrieval
    metrics = EventRepository.get_metrics_summary(db)
    assert "total_events" in metrics
    assert "total_webhook_deliveries" in metrics
    assert "webhook_delivery_success_rate" in metrics
    assert "dead_letter_count" in metrics

# =====================================================================
# 10. Alembic Migration Upgrade & Downgrade
# =====================================================================
def test_alembic_migration_sprint82() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    migration_file = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "202609121200_module8_sprint82_event_bus_webhooks.py"
    )
    spec = importlib.util.spec_from_file_location("sprint82_migration", migration_file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Need user and workflow_runs table stubs for foreign keys
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY);")
        conn.exec_driver_sql("CREATE TABLE workflow_runs (id BLOB PRIMARY KEY);")
        conn.exec_driver_sql("CREATE TABLE workflow_step_executions (id BLOB PRIMARY KEY);")
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        mod.op = op

        # Upgrade
        mod.upgrade()

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "events" in tables
    assert "webhook_sources" in tables
    assert "webhook_deliveries" in tables
    assert "outbound_webhook_subscriptions" in tables
    assert "outbound_webhook_deliveries" in tables
    assert "event_dead_letters" in tables
    assert "event_audit_logs" in tables

    # Downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        mod.op = op
        mod.downgrade()

    insp_post = inspect(engine)
    post_tables = set(insp_post.get_table_names())
    assert "events" not in post_tables
    assert "webhook_sources" not in post_tables
    assert "webhook_deliveries" not in post_tables

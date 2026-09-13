"""Event service coordinating publishing, webhook verification, workflow triggers, outbound webhooks, and DLQ."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.events.bus import default_event_bus, matches_event_pattern
from app.modules.events.models import (
    DeadLetterStatus,
    DomainEvent,
    EventAuditAction,
    EventProcessingStatus,
    OutboundDeliveryStatus,
    OutboundWebhookDelivery,
    OutboundWebhookSubscription,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSource,
)
from app.modules.events.repository import EventRepository
from app.modules.events.schemas import (
    EventPublishRequest,
    OutboundSubscriptionCreateRequest,
    WebhookSourceCreateRequest,
    WebhookSourceUpdateRequest,
)
from app.modules.events.security import (
    calculate_delivery_fingerprint,
    compute_hmac_sha256,
    EncryptedSecretStore,
    HMACSHA256Verifier,
    SecretStore,
    SignatureVerifier,
    sanitize_payload,
)
from app.modules.events.ssrf import SSRFValidationError, validate_outbound_url
from app.modules.workflows.models import (
    WorkflowRun,
    WorkflowStatus,
    WorkflowTriggerType,
)
from app.modules.workflows.repository import WorkflowRepository
from app.modules.workflows.service import WorkflowService

logger = logging.getLogger(__name__)

APPROVED_EVENT_TYPES: set[str] = {
    "content.created",
    "content.updated",
    "content.approved",
    "content.published",
    "content.failed",
    "content.drafted",
    "media.ingest.started",
    "media.ingest.completed",
    "media.ingest.failed",
    "distribution.requested",
    "distribution.completed",
    "distribution.failed",
    "workflow.completed",
    "workflow.failed",
    "partner.activated",
    "partner.suspended",
    "partner.code.pushed",
    "settlement.finalized",
    "payout.paid",
    "payout.failed",
    "system.alert",
    "test.trace.event",
    "crash.event",
    "viewer.event",
}

SAFE_FILTER_OPERATORS = {"=="}


def register_approved_event_type(event_type: str) -> None:
    APPROVED_EVENT_TYPES.add(event_type)


def is_approved_event_type(event_type: str) -> bool:
    if event_type in APPROVED_EVENT_TYPES:
        return True
    return any(matches_event_pattern(pat, event_type) for pat in APPROVED_EVENT_TYPES)


def evaluate_filter_rule(
    rule: dict[str, Any], payload: dict[str, Any], allowed_fields: set[str]
) -> bool:
    """Safely evaluate a single filter rule against an event payload."""
    field = rule.get("field")
    op = rule.get("op", "==")
    expected = rule.get("value")

    if (
        not field
        or not isinstance(field, str)
        or field not in allowed_fields
        or op not in SAFE_FILTER_OPERATORS
    ):
        return False

    curr: Any = payload
    for part in field.split("."):
        if isinstance(curr, dict):
            curr = curr.get(part)
        else:
            curr = None
            break

    actual = curr

    return bool(actual == expected)


def evaluate_trigger_filters(
    filter_config: Any,
    payload: dict[str, Any] | None,
    allowed_fields: set[str] | None = None,
) -> bool:
    """Safely evaluate trigger filter criteria against an event payload."""
    if not filter_config:
        return True

    safe_payload = payload or {}
    allowlist = allowed_fields or set()

    if isinstance(filter_config, dict):
        if "rules" in filter_config and isinstance(filter_config["rules"], list):
            return all(
                evaluate_filter_rule(r, safe_payload, allowlist)
                for r in filter_config["rules"]
                if isinstance(r, dict)
            )
        for key, value in filter_config.items():
            if key == "rules":
                continue
            if key not in allowlist or safe_payload.get(key) != value:
                return False
        return True
    elif isinstance(filter_config, list):
        return all(
            evaluate_filter_rule(r, safe_payload, allowlist)
            for r in filter_config
            if isinstance(r, dict)
        )

    return True


class EventService:
    """Coordinates events, webhooks, automation triggers, outbound subscriptions, and DLQ."""

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        allow_test_urls: bool = False,
        signature_verifier: SignatureVerifier | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.http_client = http_client
        self.allow_test_urls = allow_test_urls
        self.signature_verifier = signature_verifier or HMACSHA256Verifier()
        self.secret_store = secret_store or EncryptedSecretStore()

    # ---------------- Webhook Source Management ----------------
    def create_webhook_source(
        self,
        db: Session,
        payload: WebhookSourceCreateRequest,
        actor_user_id: int | None = None,
    ) -> tuple[WebhookSource, str]:
        existing = EventRepository.get_webhook_source_by_key(db, payload.source_key)
        if existing is not None:
            raise ValueError(
                f"Webhook source key '{payload.source_key}' already exists"
            )

        raw_secret = payload.secret
        secret_hash, secret_salt = self.secret_store.seal(raw_secret)

        source = EventRepository.create_webhook_source(
            db,
            source_key=payload.source_key,
            name=payload.name,
            description=payload.description,
            provider_type=payload.provider_type,
            secret_hash=secret_hash,
            secret_salt=secret_salt,
            header_name=payload.header_name,
            timestamp_header=payload.timestamp_header,
            timestamp_tolerance_seconds=payload.timestamp_tolerance_seconds,
            payload_size_limit_bytes=payload.payload_size_limit_bytes,
            event_type_mapping_json=payload.event_type_mapping,
            is_enabled=payload.is_enabled,
        )

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.WEBHOOK_RECEIVED,
            webhook_source_id=source.id,
            actor_user_id=actor_user_id,
            metadata={"source_key": source.source_key, "action": "source_registered"},
        )

        return source, raw_secret

    def update_webhook_source(
        self, db: Session, source_id: UUID, payload: WebhookSourceUpdateRequest
    ) -> WebhookSource:
        source = EventRepository.get_webhook_source(db, source_id)
        if source is None:
            raise ValueError(f"Webhook source '{source_id}' not found")

        if payload.name is not None:
            source.name = payload.name
        if payload.description is not None:
            source.description = payload.description
        if payload.header_name is not None:
            source.header_name = payload.header_name
        if payload.timestamp_header is not None:
            source.timestamp_header = payload.timestamp_header
        if payload.timestamp_tolerance_seconds is not None:
            source.timestamp_tolerance_seconds = payload.timestamp_tolerance_seconds
        if payload.payload_size_limit_bytes is not None:
            source.payload_size_limit_bytes = payload.payload_size_limit_bytes
        if payload.event_type_mapping is not None:
            source.event_type_mapping_json = payload.event_type_mapping
        if payload.is_enabled is not None:
            source.is_enabled = payload.is_enabled

        db.flush()
        return source

    # ---------------- Domain Event Publishing & Automation ----------------
    def publish_event(
        self,
        db: Session,
        payload: EventPublishRequest,
        actor_user_id: int | None = None,
    ) -> DomainEvent:
        """Publish a domain event with deduplication, persistence, and subscriber dispatch."""
        now = datetime.now(UTC)
        occurred_at = payload.occurred_at or now
        correlation_id = payload.correlation_id or uuid4().hex
        idempotency_key = payload.idempotency_key or uuid4().hex

        existing = EventRepository.get_event_by_type_and_idempotency_key(
            db, payload.event_type, idempotency_key
        )
        if existing is not None:
            return existing

        if not is_approved_event_type(payload.event_type):
            raise ValueError(f"Unknown event type '{payload.event_type}'")

        sanitized = sanitize_payload(payload.payload)

        event = EventRepository.create_event(
            db,
            event_type=payload.event_type,
            event_version=payload.event_version,
            source=payload.source,
            tenant_id=payload.tenant_id,
            aggregate_type=payload.aggregate_type,
            aggregate_id=payload.aggregate_id,
            correlation_id=correlation_id,
            causation_id=payload.causation_id,
            idempotency_key=idempotency_key,
            payload_json=sanitized,
            occurred_at=occurred_at,
            received_at=now,
            status=EventProcessingStatus.RECEIVED,
        )

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.EVENT_RECEIVED,
            event_id=event.id,
            actor_user_id=actor_user_id,
            metadata={"event_type": event.event_type, "correlation_id": correlation_id},
        )

        # Persist before any handler, workflow, or outbound side effect.
        db.commit()

        default_event_bus.publish(db, event)
        self._trigger_matching_workflows(db, event, actor_user_id)
        self._dispatch_outbound_webhooks(db, event)

        return event

    def _trigger_matching_workflows(
        self, db: Session, event: DomainEvent, actor_user_id: int | None = None
    ) -> list[WorkflowRun]:
        """Find active workflows with matching internal event triggers and trigger runs."""
        wf_repo = WorkflowRepository(db)
        wf_service = WorkflowService(wf_repo)

        active_workflows = wf_repo.list_workflows(status=WorkflowStatus.ACTIVE)
        triggered_runs: list[WorkflowRun] = []

        for wf in active_workflows:
            if not wf.is_enabled:
                continue

            for trigger in wf.triggers:
                if not trigger.is_enabled:
                    continue
                if trigger.trigger_type != WorkflowTriggerType.INTERNAL_EVENT:
                    continue

                pattern = trigger.event_pattern or "*"
                if not matches_event_pattern(pattern, event.event_type):
                    continue

                trigger_meta = trigger.metadata_json or {}
                if trigger_meta.get("source") not in (None, event.source):
                    continue
                if trigger_meta.get("aggregate_type") not in (
                    None,
                    event.aggregate_type,
                ):
                    continue
                if trigger_meta.get("tenant_id") not in (None, event.tenant_id):
                    continue

                filters = (
                    (trigger.metadata_json or {}).get("filters")
                    if trigger.metadata_json
                    else None
                )
                allowed_fields = set(
                    trigger_meta.get("allowed_payload_fields")
                    or trigger_meta.get("payload_filter_fields")
                    or []
                )
                if not evaluate_trigger_filters(
                    filters, event.payload_json, allowed_fields
                ):
                    continue

                run_idempotency_key = f"evt-{event.id}-wf-{wf.id}"
                input_meta = {
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "causation_id": str(event.id),
                    "event_payload": event.payload_json,
                }

                try:
                    run = wf_service.trigger_workflow_run(
                        workflow_id=wf.id,
                        input_metadata=input_meta,
                        idempotency_key=run_idempotency_key,
                        trigger_type=WorkflowTriggerType.INTERNAL_EVENT,
                        trigger_source=f"event:{event.event_type}",
                        actor_user_id=actor_user_id,
                        execute_now=True,
                        correlation_id=event.correlation_id,
                        causation_id=event.causation_id or str(event.id),
                    )
                    triggered_runs.append(run)

                    EventRepository.create_audit_log(
                        db,
                        action=EventAuditAction.WORKFLOW_TRIGGERED_BY_EVENT,
                        event_id=event.id,
                        workflow_run_id=run.id,
                        actor_user_id=actor_user_id,
                        metadata={"workflow_id": str(wf.id), "workflow_name": wf.name},
                    )
                except Exception as exc:
                    logger.exception(
                        "Failed to trigger workflow %s for event %s: %s",
                        wf.id,
                        event.id,
                        exc,
                    )

        return triggered_runs

    # ---------------- Outbound Webhooks ----------------
    def create_outbound_subscription(
        self, db: Session, payload: OutboundSubscriptionCreateRequest
    ) -> tuple[OutboundWebhookSubscription, str]:
        validate_outbound_url(
            payload.endpoint_url, allow_private_for_tests=self.allow_test_urls
        )

        raw_secret = payload.secret
        secret_hash, secret_salt = self.secret_store.seal(raw_secret)

        sub = EventRepository.create_outbound_subscription(
            db,
            name=payload.name,
            endpoint_url=payload.endpoint_url,
            event_patterns_json=payload.event_patterns,
            secret_hash=secret_hash,
            secret_salt=secret_salt,
            max_retries=payload.max_retries,
            timeout_seconds=payload.timeout_seconds,
            is_enabled=payload.is_enabled,
        )
        return sub, raw_secret

    def _dispatch_outbound_webhooks(
        self, db: Session, event: DomainEvent
    ) -> list[OutboundWebhookDelivery]:
        subscriptions = EventRepository.list_outbound_subscriptions(db, is_enabled=True)
        deliveries: list[OutboundWebhookDelivery] = []

        for sub in subscriptions:
            matched = any(
                matches_event_pattern(pat, event.event_type)
                for pat in sub.event_patterns_json
            )
            if not matched:
                continue

            delivery = EventRepository.create_outbound_delivery(
                db, subscription_id=sub.id, event_id=event.id
            )
            self._execute_outbound_delivery(db, sub, delivery, event)
            deliveries.append(delivery)

        return deliveries

    def _execute_outbound_delivery(
        self,
        db: Session,
        sub: OutboundWebhookSubscription,
        delivery: OutboundWebhookDelivery,
        event: DomainEvent,
    ) -> OutboundWebhookDelivery:
        try:
            validate_outbound_url(
                sub.endpoint_url, allow_private_for_tests=self.allow_test_urls
            )
        except SSRFValidationError as ssrf_err:
            delivery.status = OutboundDeliveryStatus.FAILED
            delivery.error_message = f"SSRF violation: {ssrf_err}"
            db.flush()
            EventRepository.create_dead_letter(
                db,
                event_id=event.id,
                outbound_delivery_id=delivery.id,
                reason=f"SSRF violation: {ssrf_err}",
            )
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.OUTBOUND_DELIVERY_FAILED,
                event_id=event.id,
                metadata={"delivery_id": str(delivery.id), "error": str(ssrf_err)},
            )
            return delivery

        raw_secret = self.secret_store.reveal(sub.secret_hash, sub.secret_salt)
        timestamp_str = str(int(datetime.now(UTC).timestamp()))
        payload_data = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "event_version": event.event_version,
            "correlation_id": event.correlation_id,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.payload_json,
        }
        body_bytes = json.dumps(payload_data, sort_keys=True).encode("utf-8")
        signature = compute_hmac_sha256(raw_secret, body_bytes, include_prefix=True)

        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GNTV-Timestamp": timestamp_str,
            "User-Agent": "GNTV-EventBus-Webhook/1.0",
        }

        delivery.status = OutboundDeliveryStatus.DELIVERING
        delivery.attempt_count += 1
        db.flush()

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.OUTBOUND_DELIVERY_STARTED,
            event_id=event.id,
            metadata={
                "delivery_id": str(delivery.id),
                "attempt": delivery.attempt_count,
            },
        )

        try:
            client = self.http_client or httpx.Client(timeout=sub.timeout_seconds)
            response = client.post(
                sub.endpoint_url, content=body_bytes, headers=headers
            )
            delivery.response_status_code = response.status_code
            delivery.response_body_truncated = f"{len(response.content)} response bytes"

            if 200 <= response.status_code < 300:
                delivery.status = OutboundDeliveryStatus.DELIVERED
                EventRepository.create_audit_log(
                    db,
                    action=EventAuditAction.OUTBOUND_DELIVERY_SUCCEEDED,
                    event_id=event.id,
                    metadata={
                        "delivery_id": str(delivery.id),
                        "status_code": response.status_code,
                    },
                )
            else:
                raise Exception(f"HTTP {response.status_code}")
        except Exception as exc:
            delivery.error_message = str(exc)[:500]
            if delivery.attempt_count >= sub.max_retries:
                delivery.status = OutboundDeliveryStatus.DEAD_LETTERED
                EventRepository.create_dead_letter(
                    db,
                    event_id=event.id,
                    outbound_delivery_id=delivery.id,
                    reason=f"Outbound webhook delivery exhausted retries: {exc}",
                )
                EventRepository.create_audit_log(
                    db,
                    action=EventAuditAction.OUTBOUND_DELIVERY_DEAD_LETTERED,
                    event_id=event.id,
                    metadata={"delivery_id": str(delivery.id), "error": str(exc)},
                )
            else:
                delivery.status = OutboundDeliveryStatus.RETRY_SCHEDULED
                backoff_seconds = 2**delivery.attempt_count
                delivery.next_retry_at = datetime.now(UTC) + timedelta(
                    seconds=backoff_seconds
                )
                EventRepository.create_audit_log(
                    db,
                    action=EventAuditAction.OUTBOUND_DELIVERY_FAILED,
                    event_id=event.id,
                    metadata={
                        "delivery_id": str(delivery.id),
                        "error": str(exc),
                        "retry_in": backoff_seconds,
                    },
                )

        db.flush()
        return delivery

    # ---------------- Inbound Webhooks ----------------
    def handle_inbound_webhook(
        self,
        db: Session,
        source_key: str,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        """Verify inbound webhook HMAC signature, check timestamp tolerance, and ingest event."""
        now = datetime.now(UTC)
        source = EventRepository.get_webhook_source_by_key(db, source_key)
        if source is None:
            return 404, {"detail": f"Webhook source '{source_key}' not found"}

        if not source.is_enabled:
            return 403, {"detail": f"Webhook source '{source_key}' is disabled"}
        if len(raw_body) > source.payload_size_limit_bytes:
            return 413, {"detail": "Webhook payload exceeds configured size limit"}

        lower_headers = {k.lower(): v for k, v in headers.items()}

        timestamp_val = None
        if source.timestamp_header:
            timestamp_val = lower_headers.get(source.timestamp_header.lower())
            if not timestamp_val:
                EventRepository.create_audit_log(
                    db,
                    action=EventAuditAction.WEBHOOK_REJECTED,
                    webhook_source_id=source.id,
                    metadata={"reason": "missing_timestamp_header"},
                )
                return 400, {
                    "detail": f"Missing required timestamp header '{source.timestamp_header}'"
                }

            try:
                if timestamp_val.isdigit():
                    ts_epoch = float(timestamp_val)
                    if ts_epoch > 1e11:
                        ts_epoch /= 1000.0
                    ts_dt = datetime.fromtimestamp(ts_epoch, tz=UTC)
                else:
                    ts_dt = datetime.fromisoformat(timestamp_val.replace("Z", "+00:00"))

                diff_seconds = abs((now - ts_dt).total_seconds())
                if diff_seconds > source.timestamp_tolerance_seconds:
                    EventRepository.create_audit_log(
                        db,
                        action=EventAuditAction.WEBHOOK_REJECTED,
                        webhook_source_id=source.id,
                        metadata={
                            "reason": "timestamp_tolerance_exceeded",
                            "drift": diff_seconds,
                        },
                    )
                    return 400, {
                        "detail": (
                            f"Timestamp tolerance exceeded "
                            f"({diff_seconds:.1f}s > {source.timestamp_tolerance_seconds}s)"
                        )
                    }
            except Exception:
                return 400, {"detail": "Invalid timestamp header format"}

        fingerprint_ts = timestamp_val or "no-ts"
        fingerprint = calculate_delivery_fingerprint(
            str(source.id), fingerprint_ts, raw_body
        )
        existing_delivery = EventRepository.get_webhook_delivery_by_fingerprint(
            db, source.id, fingerprint
        )
        if existing_delivery is not None:
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.WEBHOOK_DUPLICATE,
                webhook_source_id=source.id,
                webhook_delivery_id=existing_delivery.id,
                metadata={"fingerprint": fingerprint},
            )
            return 409, {
                "detail": "Duplicate webhook delivery detected (replay protection)"
            }

        provider_event_id = lower_headers.get("x-event-id") or lower_headers.get(
            "x-github-delivery"
        )
        if (
            provider_event_id
            and EventRepository.get_webhook_delivery_by_external_id(
                db, source.id, provider_event_id
            )
            is not None
        ):
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.WEBHOOK_DUPLICATE,
                webhook_source_id=source.id,
                metadata={"reason": "duplicate_provider_event_id"},
            )
            return 409, {"detail": "Duplicate provider event ID detected"}

        sig_header = lower_headers.get(source.header_name.lower())
        if not sig_header:
            delivery = EventRepository.create_webhook_delivery(
                db,
                source_id=source.id,
                external_event_id=lower_headers.get("x-event-id")
                or lower_headers.get("x-github-delivery"),
                delivery_fingerprint=fingerprint,
                signature_valid=False,
                mapped_event_type=None,
                status=WebhookDeliveryStatus.REJECTED,
                linked_event_id=None,
                safe_payload_json=None,
                rejection_reason=f"Missing signature header '{source.header_name}'",
                received_at=now,
            )
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.WEBHOOK_REJECTED,
                webhook_source_id=source.id,
                webhook_delivery_id=delivery.id,
                metadata={"reason": "missing_signature"},
            )
            return 400, {"detail": f"Missing signature header '{source.header_name}'"}

        secret_plain = self.secret_store.reveal(source.secret_hash, source.secret_salt)
        if not self.signature_verifier.verify(secret_plain, raw_body, sig_header):
            delivery = EventRepository.create_webhook_delivery(
                db,
                source_id=source.id,
                external_event_id=lower_headers.get("x-event-id")
                or lower_headers.get("x-github-delivery"),
                delivery_fingerprint=fingerprint,
                signature_valid=False,
                mapped_event_type=None,
                status=WebhookDeliveryStatus.REJECTED,
                linked_event_id=None,
                safe_payload_json=None,
                rejection_reason="Invalid HMAC-SHA256 signature",
                received_at=now,
            )
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.WEBHOOK_REJECTED,
                webhook_source_id=source.id,
                webhook_delivery_id=delivery.id,
                metadata={"reason": "invalid_signature"},
            )
            return 400, {"detail": "Invalid HMAC signature"}

        try:
            parsed_json = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            parsed_json = {"raw": raw_body.decode("utf-8", errors="replace")}

        sanitized_json = sanitize_payload(parsed_json)
        external_id = (
            lower_headers.get("x-event-id")
            or lower_headers.get("x-github-delivery")
            or str(parsed_json.get("id") or parsed_json.get("event_id") or "")
            or None
        )

        raw_event_type = (
            lower_headers.get("x-event-type")
            or lower_headers.get("x-github-event")
            or parsed_json.get("event_type")
            or parsed_json.get("type")
            or "event"
        )
        mapping = source.event_type_mapping_json or {}
        mapped_event_type = mapping.get(
            raw_event_type, f"{source.source_key}.{raw_event_type}"
        )
        if mapped_event_type not in APPROVED_EVENT_TYPES:
            return 422, {"detail": "Mapped event type is not registered"}

        delivery = EventRepository.create_webhook_delivery(
            db,
            source_id=source.id,
            external_event_id=external_id,
            delivery_fingerprint=fingerprint,
            signature_valid=True,
            mapped_event_type=mapped_event_type,
            status=WebhookDeliveryStatus.VERIFIED,
            linked_event_id=None,
            safe_payload_json=sanitized_json,
            rejection_reason=None,
            received_at=now,
        )

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.WEBHOOK_VERIFIED,
            webhook_source_id=source.id,
            webhook_delivery_id=delivery.id,
            metadata={"mapped_event_type": mapped_event_type},
        )

        publish_req = EventPublishRequest(
            event_type=mapped_event_type,
            source=f"webhook:{source.source_key}",
            correlation_id=uuid4().hex,
            causation_id=str(delivery.id),
            idempotency_key=f"wh-{delivery.id}",
            payload=sanitized_json,
            occurred_at=now,
        )
        domain_event = self.publish_event(db, publish_req)

        delivery.linked_event_id = domain_event.id
        delivery.status = WebhookDeliveryStatus.PROCESSED
        db.flush()

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.WEBHOOK_MAPPED,
            webhook_source_id=source.id,
            webhook_delivery_id=delivery.id,
            event_id=domain_event.id,
            metadata={"mapped_event_type": mapped_event_type},
        )

        return 202, {
            "status": "accepted",
            "delivery_id": str(delivery.id),
            "event_id": str(domain_event.id),
            "mapped_event_type": mapped_event_type,
        }

    # ---------------- Dead Letter Queue Actions ----------------
    def retry_dead_letter(
        self, db: Session, dlq_id: UUID, actor_user_id: int | None = None
    ) -> bool:
        dlq = EventRepository.get_dead_letter(db, dlq_id)
        if dlq is None:
            raise ValueError(f"Dead letter record '{dlq_id}' not found")
        if dlq.status != DeadLetterStatus.PENDING:
            raise ValueError(f"Dead letter '{dlq_id}' is already '{dlq.status.value}'")

        dlq.retry_count += 1

        if dlq.event_id is not None:
            event = EventRepository.get_event(db, dlq.event_id)
            if event:
                event.status = EventProcessingStatus.PROCESSING
                default_event_bus.publish(db, event)

        if dlq.outbound_delivery_id is not None:
            delivery = EventRepository.get_outbound_delivery(
                db, dlq.outbound_delivery_id
            )
            if delivery:
                sub = EventRepository.get_outbound_subscription(
                    db, delivery.subscription_id
                )
                event = EventRepository.get_event(db, delivery.event_id)
                if sub and event:
                    self._execute_outbound_delivery(db, sub, delivery, event)

        dlq.status = DeadLetterStatus.RETRIED
        db.flush()

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.DEAD_LETTER_RETRIED,
            event_id=dlq.event_id,
            actor_user_id=actor_user_id,
            metadata={"dlq_id": str(dlq.id)},
        )
        return True

    def dismiss_dead_letter(
        self, db: Session, dlq_id: UUID, actor_user_id: int | None = None
    ) -> bool:
        dlq = EventRepository.get_dead_letter(db, dlq_id)
        if dlq is None:
            raise ValueError(f"Dead letter record '{dlq_id}' not found")
        if dlq.status != DeadLetterStatus.PENDING:
            raise ValueError(f"Dead letter '{dlq_id}' is already '{dlq.status.value}'")

        dlq.status = DeadLetterStatus.DISMISSED
        dlq.dismissed_by_user_id = actor_user_id
        dlq.dismissed_at = datetime.now(UTC)
        db.flush()

        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.DEAD_LETTER_DISMISSED,
            event_id=dlq.event_id,
            actor_user_id=actor_user_id,
            metadata={"dlq_id": str(dlq.id)},
        )
        return True

    # ---------------- Correlation Tracing ----------------
    def get_event_trace(self, db: Session, correlation_id: str) -> dict[str, Any]:
        """Assemble comprehensive trace for a correlation ID."""
        events = EventRepository.list_events(db, correlation_id=correlation_id, limit=1)
        primary_event = events[0] if events else None

        webhook_delivery = None
        outbound_deliveries: list[OutboundWebhookDelivery] = []
        dead_letters: list[Any] = []
        audit_logs = []
        workflow_runs_data = []

        if primary_event is not None:
            stmt = select(WebhookDelivery).where(
                WebhookDelivery.linked_event_id == primary_event.id
            )
            webhook_delivery = db.scalars(stmt).first()

            outbound_deliveries = EventRepository.list_outbound_deliveries(
                db, event_id=primary_event.id, limit=50
            )
            dead_letters = list(primary_event.dead_letters)
            audit_logs = EventRepository.list_audit_logs(
                db, event_id=primary_event.id, limit=50
            )

            wf_runs = (
                db.query(WorkflowRun)
                .filter(WorkflowRun.idempotency_key.like(f"evt-{primary_event.id}-%"))
                .all()
            )
            for r in wf_runs:
                workflow_runs_data.append(
                    {
                        "id": str(r.id),
                        "workflow_id": str(r.workflow_id),
                        "status": r.status.value,
                        "trigger_type": r.trigger_type.value,
                        "idempotency_key": r.idempotency_key,
                        "created_at": r.created_at.isoformat(),
                    }
                )

        return {
            "correlation_id": correlation_id,
            "event": primary_event,
            "webhook_delivery": webhook_delivery,
            "workflow_runs": workflow_runs_data,
            "outbound_deliveries": outbound_deliveries,
            "dead_letters": dead_letters,
            "audit_logs": [
                {
                    "id": str(log.id),
                    "action": log.action.value,
                    "event_id": str(log.event_id) if log.event_id else None,
                    "workflow_run_id": str(log.workflow_run_id)
                    if log.workflow_run_id
                    else None,
                    "metadata": log.metadata_json,
                    "created_at": log.created_at.isoformat(),
                }
                for log in audit_logs
            ],
        }

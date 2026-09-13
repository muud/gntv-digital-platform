"""Database repository for events, webhooks, subscriptions, deliveries, DLQ, and audit logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.events.models import (
    DeadLetterStatus,
    DomainEvent,
    EventAuditAction,
    EventAuditLog,
    EventDeadLetter,
    EventProcessingStatus,
    OutboundDeliveryStatus,
    OutboundWebhookDelivery,
    OutboundWebhookSubscription,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSource,
)
from app.modules.events.security import sanitize_payload


class EventRepository:
    """Repository handling all database interactions for Module 8 Sprint 8.2."""

    # ---------------- Domain Events ----------------
    @staticmethod
    def create_event(
        db: Session,
        *,
        event_type: str,
        event_version: int,
        source: str,
        tenant_id: str | None,
        aggregate_type: str | None,
        aggregate_id: str | None,
        correlation_id: str,
        causation_id: str | None,
        idempotency_key: str,
        payload_json: dict[str, Any] | None,
        occurred_at: datetime,
        received_at: datetime,
        status: EventProcessingStatus = EventProcessingStatus.RECEIVED,
        max_retries: int = 3,
    ) -> DomainEvent:
        event = DomainEvent(
            event_type=event_type,
            event_version=event_version,
            source=source,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
            payload_json=payload_json,
            occurred_at=occurred_at,
            received_at=received_at,
            status=status,
            max_retries=max_retries,
        )
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def get_event(db: Session, event_id: UUID) -> DomainEvent | None:
        stmt = select(DomainEvent).where(DomainEvent.id == event_id)
        return db.scalars(stmt).first()

    @staticmethod
    def get_event_by_type_and_idempotency_key(
        db: Session, event_type: str, idempotency_key: str
    ) -> DomainEvent | None:
        stmt = select(DomainEvent).where(
            DomainEvent.event_type == event_type,
            DomainEvent.idempotency_key == idempotency_key,
        )
        return db.scalars(stmt).first()

    @staticmethod
    def list_events(
        db: Session,
        *,
        event_type: str | None = None,
        status: EventProcessingStatus | None = None,
        correlation_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainEvent]:
        stmt = select(DomainEvent)
        if event_type:
            stmt = stmt.where(DomainEvent.event_type == event_type)
        if status:
            stmt = stmt.where(DomainEvent.status == status)
        if correlation_id:
            stmt = stmt.where(DomainEvent.correlation_id == correlation_id)
        stmt = stmt.order_by(DomainEvent.created_at.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def update_event_status(
        db: Session,
        event: DomainEvent,
        *,
        status: EventProcessingStatus,
        error_details: dict[str, Any] | None = None,
    ) -> DomainEvent:
        event.status = status
        if error_details is not None:
            event.error_details_json = error_details
        db.flush()
        return event

    @staticmethod
    def increment_event_retry(db: Session, event: DomainEvent) -> DomainEvent:
        event.retry_count += 1
        db.flush()
        return event

    # ---------------- Webhook Sources ----------------
    @staticmethod
    def create_webhook_source(
        db: Session,
        *,
        source_key: str,
        name: str,
        description: str | None,
        provider_type: str,
        secret_hash: str,
        secret_salt: str,
        header_name: str,
        timestamp_header: str | None,
        timestamp_tolerance_seconds: int,
        payload_size_limit_bytes: int,
        event_type_mapping_json: dict[str, Any] | None,
        is_enabled: bool = True,
    ) -> WebhookSource:
        source = WebhookSource(
            source_key=source_key,
            name=name,
            description=description,
            provider_type=provider_type,
            secret_hash=secret_hash,
            secret_salt=secret_salt,
            header_name=header_name,
            timestamp_header=timestamp_header,
            timestamp_tolerance_seconds=timestamp_tolerance_seconds,
            payload_size_limit_bytes=payload_size_limit_bytes,
            event_type_mapping_json=event_type_mapping_json,
            is_enabled=is_enabled,
        )
        db.add(source)
        db.flush()
        return source

    @staticmethod
    def get_webhook_source(db: Session, source_id: UUID) -> WebhookSource | None:
        stmt = select(WebhookSource).where(WebhookSource.id == source_id)
        return db.scalars(stmt).first()

    @staticmethod
    def get_webhook_source_by_key(db: Session, source_key: str) -> WebhookSource | None:
        stmt = select(WebhookSource).where(WebhookSource.source_key == source_key)
        return db.scalars(stmt).first()

    @staticmethod
    def list_webhook_sources(
        db: Session,
        *,
        is_enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WebhookSource]:
        stmt = select(WebhookSource)
        if is_enabled is not None:
            stmt = stmt.where(WebhookSource.is_enabled == is_enabled)
        stmt = (
            stmt.order_by(WebhookSource.created_at.desc()).offset(offset).limit(limit)
        )
        return list(db.scalars(stmt).all())

    # ---------------- Webhook Deliveries ----------------
    @staticmethod
    def create_webhook_delivery(
        db: Session,
        *,
        source_id: UUID,
        external_event_id: str | None,
        delivery_fingerprint: str,
        signature_valid: bool,
        mapped_event_type: str | None,
        status: WebhookDeliveryStatus,
        linked_event_id: UUID | None,
        safe_payload_json: dict[str, Any] | None,
        rejection_reason: str | None,
        received_at: datetime,
    ) -> WebhookDelivery:
        delivery = WebhookDelivery(
            source_id=source_id,
            external_event_id=external_event_id,
            delivery_fingerprint=delivery_fingerprint,
            signature_valid=signature_valid,
            mapped_event_type=mapped_event_type,
            status=status,
            linked_event_id=linked_event_id,
            safe_payload_json=safe_payload_json,
            rejection_reason=rejection_reason,
            received_at=received_at,
        )
        db.add(delivery)
        db.flush()
        return delivery

    @staticmethod
    def get_webhook_delivery(db: Session, delivery_id: UUID) -> WebhookDelivery | None:
        stmt = select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        return db.scalars(stmt).first()

    @staticmethod
    def get_webhook_delivery_by_fingerprint(
        db: Session, source_id: UUID, delivery_fingerprint: str
    ) -> WebhookDelivery | None:
        stmt = select(WebhookDelivery).where(
            WebhookDelivery.source_id == source_id,
            WebhookDelivery.delivery_fingerprint == delivery_fingerprint,
        )
        return db.scalars(stmt).first()

    @staticmethod
    def get_webhook_delivery_by_external_id(
        db: Session, source_id: UUID, external_event_id: str
    ) -> WebhookDelivery | None:
        stmt = select(WebhookDelivery).where(
            WebhookDelivery.source_id == source_id,
            WebhookDelivery.external_event_id == external_event_id,
        )
        return db.scalars(stmt).first()

    @staticmethod
    def list_webhook_deliveries(
        db: Session,
        *,
        source_id: UUID | None = None,
        status: WebhookDeliveryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WebhookDelivery]:
        stmt = select(WebhookDelivery)
        if source_id:
            stmt = stmt.where(WebhookDelivery.source_id == source_id)
        if status:
            stmt = stmt.where(WebhookDelivery.status == status)
        stmt = (
            stmt.order_by(WebhookDelivery.received_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    # ---------------- Outbound Webhooks ----------------
    @staticmethod
    def create_outbound_subscription(
        db: Session,
        *,
        name: str,
        endpoint_url: str,
        event_patterns_json: list[str],
        secret_hash: str,
        secret_salt: str,
        max_retries: int = 3,
        timeout_seconds: int = 10,
        is_enabled: bool = True,
    ) -> OutboundWebhookSubscription:
        sub = OutboundWebhookSubscription(
            name=name,
            endpoint_url=endpoint_url,
            event_patterns_json=event_patterns_json,
            secret_hash=secret_hash,
            secret_salt=secret_salt,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            is_enabled=is_enabled,
        )
        db.add(sub)
        db.flush()
        return sub

    @staticmethod
    def get_outbound_subscription(
        db: Session, sub_id: UUID
    ) -> OutboundWebhookSubscription | None:
        stmt = select(OutboundWebhookSubscription).where(
            OutboundWebhookSubscription.id == sub_id
        )
        return db.scalars(stmt).first()

    @staticmethod
    def list_outbound_subscriptions(
        db: Session, *, is_enabled: bool | None = None
    ) -> list[OutboundWebhookSubscription]:
        stmt = select(OutboundWebhookSubscription)
        if is_enabled is not None:
            stmt = stmt.where(OutboundWebhookSubscription.is_enabled == is_enabled)
        return list(db.scalars(stmt).all())

    @staticmethod
    def create_outbound_delivery(
        db: Session, *, subscription_id: UUID, event_id: UUID
    ) -> OutboundWebhookDelivery:
        delivery = OutboundWebhookDelivery(
            subscription_id=subscription_id,
            event_id=event_id,
            status=OutboundDeliveryStatus.PENDING,
            attempt_count=0,
        )
        db.add(delivery)
        db.flush()
        return delivery

    @staticmethod
    def get_outbound_delivery(
        db: Session, delivery_id: UUID
    ) -> OutboundWebhookDelivery | None:
        stmt = select(OutboundWebhookDelivery).where(
            OutboundWebhookDelivery.id == delivery_id
        )
        return db.scalars(stmt).first()

    @staticmethod
    def list_outbound_deliveries(
        db: Session,
        *,
        event_id: UUID | None = None,
        subscription_id: UUID | None = None,
        status: OutboundDeliveryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OutboundWebhookDelivery]:
        stmt = select(OutboundWebhookDelivery)
        if event_id:
            stmt = stmt.where(OutboundWebhookDelivery.event_id == event_id)
        if subscription_id:
            stmt = stmt.where(
                OutboundWebhookDelivery.subscription_id == subscription_id
            )
        if status:
            stmt = stmt.where(OutboundWebhookDelivery.status == status)
        stmt = (
            stmt.order_by(OutboundWebhookDelivery.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    # ---------------- Dead Letter Queue ----------------
    @staticmethod
    def create_dead_letter(
        db: Session,
        *,
        event_id: UUID | None,
        outbound_delivery_id: UUID | None,
        reason: str,
    ) -> EventDeadLetter:
        dlq = EventDeadLetter(
            event_id=event_id,
            outbound_delivery_id=outbound_delivery_id,
            reason=reason[:500],
            status=DeadLetterStatus.PENDING,
            retry_count=0,
        )
        db.add(dlq)
        db.flush()
        return dlq

    @staticmethod
    def get_dead_letter(db: Session, dlq_id: UUID) -> EventDeadLetter | None:
        stmt = select(EventDeadLetter).where(EventDeadLetter.id == dlq_id)
        return db.scalars(stmt).first()

    @staticmethod
    def list_dead_letters(
        db: Session,
        *,
        status: DeadLetterStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EventDeadLetter]:
        stmt = select(EventDeadLetter)
        if status:
            stmt = stmt.where(EventDeadLetter.status == status)
        stmt = (
            stmt.order_by(EventDeadLetter.created_at.desc()).offset(offset).limit(limit)
        )
        return list(db.scalars(stmt).all())

    # ---------------- Event Audit Logs ----------------
    @staticmethod
    def create_audit_log(
        db: Session,
        *,
        action: EventAuditAction,
        event_id: UUID | None = None,
        webhook_source_id: UUID | None = None,
        webhook_delivery_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventAuditLog:
        audit_entry = EventAuditLog(
            action=action,
            event_id=event_id,
            webhook_source_id=webhook_source_id,
            webhook_delivery_id=webhook_delivery_id,
            workflow_run_id=workflow_run_id,
            actor_user_id=actor_user_id,
            metadata_json=sanitize_payload(metadata),
        )
        db.add(audit_entry)
        db.flush()
        return audit_entry

    @staticmethod
    def list_audit_logs(
        db: Session,
        *,
        event_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EventAuditLog]:
        stmt = select(EventAuditLog)
        if event_id:
            stmt = stmt.where(EventAuditLog.event_id == event_id)
        stmt = (
            stmt.order_by(EventAuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        return list(db.scalars(stmt).all())

    # ---------------- Metrics Summary ----------------
    @staticmethod
    def get_metrics_summary(db: Session) -> dict[str, Any]:
        total_events = db.scalar(select(func.count(DomainEvent.id))) or 0
        total_webhooks = db.scalar(select(func.count(WebhookDelivery.id))) or 0
        active_sources = (
            db.scalar(
                select(func.count(WebhookSource.id)).where(
                    WebhookSource.is_enabled.is_(True)
                )
            )
            or 0
        )
        pending_dlq = (
            db.scalar(
                select(func.count(EventDeadLetter.id)).where(
                    EventDeadLetter.status == DeadLetterStatus.PENDING
                )
            )
            or 0
        )

        event_status_rows = db.execute(
            select(DomainEvent.status, func.count(DomainEvent.id)).group_by(
                DomainEvent.status
            )
        ).all()
        events_by_status = {
            str(row[0].value if hasattr(row[0], "value") else row[0]): row[1]
            for row in event_status_rows
        }

        webhook_status_rows = db.execute(
            select(WebhookDelivery.status, func.count(WebhookDelivery.id)).group_by(
                WebhookDelivery.status
            )
        ).all()
        deliveries_by_status = {
            str(row[0].value if hasattr(row[0], "value") else row[0]): row[1]
            for row in webhook_status_rows
        }

        processed = events_by_status.get(EventProcessingStatus.PROCESSED.value, 0)
        failed = events_by_status.get(EventProcessingStatus.FAILED.value, 0)
        duplicate_events = (
            db.scalar(
                select(func.count(EventAuditLog.id)).where(
                    EventAuditLog.action == EventAuditAction.WEBHOOK_DUPLICATE
                )
            )
            or 0
        )
        verification_failures = (
            db.scalar(
                select(func.count(WebhookDelivery.id)).where(
                    WebhookDelivery.signature_valid.is_(False)
                )
            )
            or 0
        )
        outbound_total = (
            db.scalar(select(func.count(OutboundWebhookDelivery.id))) or 0
        )
        outbound_success = (
            db.scalar(
                select(func.count(OutboundWebhookDelivery.id)).where(
                    OutboundWebhookDelivery.status
                    == OutboundDeliveryStatus.DELIVERED
                )
            )
            or 0
        )
        outbound_failures = (
            db.scalar(
                select(func.count(OutboundWebhookDelivery.id)).where(
                    OutboundWebhookDelivery.status.in_(
                        (
                            OutboundDeliveryStatus.FAILED,
                            OutboundDeliveryStatus.RETRY_SCHEDULED,
                            OutboundDeliveryStatus.DEAD_LETTERED,
                        )
                    )
                )
            )
            or 0
        )
        dead_letter_count = db.scalar(select(func.count(EventDeadLetter.id))) or 0
        workflow_runs = (
            db.scalar(
                select(func.count(EventAuditLog.id)).where(
                    EventAuditLog.action
                    == EventAuditAction.WORKFLOW_TRIGGERED_BY_EVENT
                )
            )
            or 0
        )
        completed_events = list(
            db.scalars(
                select(DomainEvent).where(
                    DomainEvent.status.in_(
                        (
                            EventProcessingStatus.PROCESSED,
                            EventProcessingStatus.PARTIALLY_PROCESSED,
                            EventProcessingStatus.FAILED,
                            EventProcessingStatus.DEAD_LETTERED,
                        )
                    )
                )
            ).all()
        )
        latencies = []
        for event in completed_events:
            updated_at = event.updated_at
            received_at = event.received_at
            if updated_at.tzinfo is None and received_at.tzinfo is not None:
                updated_at = updated_at.replace(tzinfo=received_at.tzinfo)
            elif received_at.tzinfo is None and updated_at.tzinfo is not None:
                received_at = received_at.replace(tzinfo=updated_at.tzinfo)
            latencies.append(
                max(0.0, (updated_at - received_at).total_seconds() * 1000)
            )

        return {
            "total_events": total_events,
            "events_by_status": events_by_status,
            "total_webhook_deliveries": total_webhooks,
            "deliveries_by_status": deliveries_by_status,
            "active_sources_count": active_sources,
            "pending_dead_letters_count": pending_dlq,
            "events_received": total_events,
            "events_processed": processed,
            "events_failed": failed,
            "duplicate_events": duplicate_events,
            "webhook_verification_failures": verification_failures,
            "webhook_delivery_success_rate": (
                round(outbound_success / outbound_total, 4) if outbound_total else 0.0
            ),
            "webhook_delivery_failures": outbound_failures,
            "dead_letter_count": dead_letter_count,
            "event_triggered_workflow_runs": workflow_runs,
            "average_event_processing_latency_ms": (
                round(sum(latencies) / len(latencies), 3) if latencies else 0.0
            ),
        }

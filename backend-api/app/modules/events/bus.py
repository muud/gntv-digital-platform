"""Internal Event Bus interface, pattern matching, and in-memory delivery engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
import fnmatch
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.modules.events.models import (
    DomainEvent,
    EventAuditAction,
    EventProcessingStatus,
)
from app.modules.events.repository import EventRepository

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent, Session], Any]


def matches_event_pattern(pattern: str, event_type: str) -> bool:
    """
    Match an event type against a pattern.
    Supports exact matching, single-level wildcard (content.*), and glob patterns (*).
    """
    if not pattern or not event_type:
        return False
    if pattern == "*" or pattern == event_type:
        return True
    return fnmatch.fnmatch(event_type, pattern)


class EventBus(ABC):
    """Abstract Event Bus interface."""

    @abstractmethod
    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        """Register a handler for events matching the given pattern."""
        pass

    @abstractmethod
    def publish(self, db: Session, event: DomainEvent) -> DomainEvent:
        """Publish a persisted domain event to registered subscribers and automation triggers."""
        pass

    @abstractmethod
    def dispatch(self, db: Session, event: DomainEvent) -> DomainEvent:
        """Dispatch a previously persisted event."""
        pass

    @abstractmethod
    def acknowledge(self, db: Session, event: DomainEvent) -> DomainEvent:
        """Mark a claimed event processed."""
        pass

    @abstractmethod
    def retry(self, db: Session, event: DomainEvent) -> DomainEvent:
        """Retry a failed durable event."""
        pass

    @abstractmethod
    def dead_letter(self, db: Session, event: DomainEvent, reason: str) -> None:
        """Move an unprocessable or exhausted event to the dead letter queue."""
        pass


class InMemoryEventBus(EventBus):
    """
    Durable in-process event bus.
    Persists delivery records, dispatches to matching handlers, and logs audit events.
    """

    def __init__(self) -> None:
        self._subscribers: list[tuple[str, EventHandler]] = []

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        self._subscribers.append((pattern, handler))

    def publish(self, db: Session, event: DomainEvent) -> DomainEvent:
        """Dispatch a persisted domain event to all subscribers matching event_type."""
        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.EVENT_DISPATCHED,
            event_id=event.id,
            metadata={
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
            },
        )

        matching_handlers = [
            handler
            for pattern, handler in self._subscribers
            if matches_event_pattern(pattern, event.event_type)
        ]

        if not matching_handlers:
            EventRepository.update_event_status(
                db, event, status=EventProcessingStatus.PROCESSED
            )
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.EVENT_PROCESSED,
                event_id=event.id,
                metadata={"reason": "no_subscribers_found"},
            )
            return event

        EventRepository.update_event_status(
            db, event, status=EventProcessingStatus.PROCESSING
        )

        success_count = 0
        failure_count = 0
        last_error = None

        for handler in matching_handlers:
            try:
                handler(event, db)
                success_count += 1
            except Exception as exc:
                failure_count += 1
                last_error = str(exc)
                logger.exception(
                    "Handler failed for event %s (%s): %s",
                    event.id,
                    event.event_type,
                    exc,
                )

        if failure_count == 0:
            EventRepository.update_event_status(
                db, event, status=EventProcessingStatus.PROCESSED
            )
            EventRepository.create_audit_log(
                db,
                action=EventAuditAction.EVENT_PROCESSED,
                event_id=event.id,
                metadata={"dispatched_handlers": success_count},
            )
        elif success_count > 0:
            EventRepository.update_event_status(
                db,
                event,
                status=EventProcessingStatus.PARTIALLY_PROCESSED,
                error_details={
                    "errors": [last_error],
                    "failed_handlers": failure_count,
                },
            )
        else:
            EventRepository.increment_event_retry(db, event)
            if event.retry_count >= event.max_retries:
                self.dead_letter(
                    db, event, reason=f"Max retries exceeded: {last_error}"
                )
            else:
                EventRepository.update_event_status(
                    db,
                    event,
                    status=EventProcessingStatus.FAILED,
                    error_details={
                        "error": last_error,
                        "retry_count": event.retry_count,
                    },
                )
                EventRepository.create_audit_log(
                    db,
                    action=EventAuditAction.EVENT_FAILED,
                    event_id=event.id,
                    metadata={"error": last_error, "retry_count": event.retry_count},
                )

        return event

    def dispatch(self, db: Session, event: DomainEvent) -> DomainEvent:
        return self.publish(db, event)

    def acknowledge(self, db: Session, event: DomainEvent) -> DomainEvent:
        return EventRepository.update_event_status(
            db, event, status=EventProcessingStatus.PROCESSED
        )

    def retry(self, db: Session, event: DomainEvent) -> DomainEvent:
        return self.publish(db, event)

    def dead_letter(self, db: Session, event: DomainEvent, reason: str) -> None:
        """Route failed event to dead-letter queue."""
        EventRepository.update_event_status(
            db,
            event,
            status=EventProcessingStatus.DEAD_LETTERED,
            error_details={"dead_letter_reason": reason},
        )
        EventRepository.create_dead_letter(
            db,
            event_id=event.id,
            outbound_delivery_id=None,
            reason=reason,
        )
        EventRepository.create_audit_log(
            db,
            action=EventAuditAction.EVENT_DEAD_LETTERED,
            event_id=event.id,
            metadata={"reason": reason},
        )


# Global default bus singleton
default_event_bus = InMemoryEventBus()

"""FastAPI API router for Event Bus, Webhook Sources, Deliveries, and Dead Letters."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.events.models import (
    DeadLetterStatus,
    EventProcessingStatus,
    OutboundDeliveryStatus,
    WebhookDeliveryStatus,
)
from app.modules.events.repository import EventRepository
from app.modules.events.schemas import (
    DeadLetterResponse,
    DomainEventResponse,
    EventMetricsSummary,
    EventPublishRequest,
    EventTraceResponse,
    OutboundDeliveryResponse,
    OutboundSubscriptionCreateRequest,
    OutboundSubscriptionResponse,
    WebhookDeliveryResponse,
    WebhookSourceCreateRequest,
    WebhookSourceResponse,
    WebhookSourceUpdateRequest,
)
from app.modules.events.service import EventService

events_router = APIRouter(prefix="/api/v1/events", tags=["Events"])
webhook_sources_router = APIRouter(
    prefix="/api/v1/webhook-sources", tags=["Webhook Sources"]
)
webhook_deliveries_router = APIRouter(
    prefix="/api/v1/webhook-deliveries", tags=["Webhook Deliveries"]
)
outbound_webhooks_router = APIRouter(
    prefix="/api/v1/outbound-webhooks", tags=["Outbound Webhooks"]
)
dead_letters_router = APIRouter(
    prefix="/api/v1/event-dead-letters", tags=["Event Dead Letters"]
)
public_webhooks_router = APIRouter(prefix="/api/v1/webhooks", tags=["Inbound Webhooks"])

OPERATOR_ROLES = {"admin", "operator", "super_admin"}
READ_ROLES = {"admin", "operator", "super_admin", "viewer"}


def get_event_service() -> EventService:
    return EventService()


def require_operator_role(user: User = Depends(get_current_user)) -> User:
    roles = (
        set(user.role_names)
        if hasattr(user, "role_names")
        else {r.name for r in user.roles}
    )
    if not (roles & OPERATOR_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or Admin clearance required for event bus management",
        )
    return user


def require_read_role(user: User = Depends(get_current_user)) -> User:
    roles = (
        set(user.role_names)
        if hasattr(user, "role_names")
        else {r.name for r in user.roles}
    )
    if not (roles & READ_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read clearance required for inspecting events and webhooks",
        )
    return user


# =====================================================================
# 1. Public Inbound Webhook Endpoint
# =====================================================================
@public_webhooks_router.post("/{source_key}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    source_key: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
) -> dict[str, Any]:
    """Public inbound webhook receiver with HMAC signature verification and replay prevention."""
    body_bytes = await request.body()
    headers = dict(request.headers)

    status_code, result = service.handle_inbound_webhook(
        db, source_key, headers, body_bytes
    )
    response.status_code = status_code
    if status_code >= 400:
        db.rollback()
        raise HTTPException(
            status_code=status_code, detail=result.get("detail", "Webhook rejected")
        )
    db.commit()
    return result


# =====================================================================
# 2. Domain Events Endpoints
# =====================================================================
@events_router.post(
    "/publish",
    response_model=DomainEventResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator_role)],
)
def publish_event(
    payload: EventPublishRequest,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
    current_user: User = Depends(require_operator_role),
) -> DomainEventResponse:
    try:
        event = service.publish_event(db, payload, actor_user_id=current_user.id)
        db.commit()
        db.refresh(event)
        return DomainEventResponse.model_validate(event)
    except ValueError as err:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@events_router.get(
    "",
    response_model=list[DomainEventResponse],
    dependencies=[Depends(require_read_role)],
)
def list_events(
    event_type: str | None = Query(None),
    status_filter: EventProcessingStatus | None = Query(None, alias="status"),
    correlation_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[DomainEventResponse]:
    events = EventRepository.list_events(
        db,
        event_type=event_type,
        status=status_filter,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset,
    )
    return [DomainEventResponse.model_validate(e) for e in events]


@events_router.get(
    "/metrics/summary",
    response_model=EventMetricsSummary,
    dependencies=[Depends(require_read_role)],
)
def get_metrics_summary(db: Session = Depends(get_db)) -> EventMetricsSummary:
    metrics = EventRepository.get_metrics_summary(db)
    return EventMetricsSummary(**metrics)


@events_router.get(
    "/trace/{correlation_id}",
    response_model=EventTraceResponse,
    dependencies=[Depends(require_read_role)],
)
def get_event_trace(
    correlation_id: str,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
) -> EventTraceResponse:
    trace_data = service.get_event_trace(db, correlation_id)
    return EventTraceResponse(
        correlation_id=correlation_id,
        event=(
            DomainEventResponse.model_validate(trace_data["event"])
            if trace_data.get("event")
            else None
        ),
        webhook_delivery=(
            WebhookDeliveryResponse.model_validate(trace_data["webhook_delivery"])
            if trace_data.get("webhook_delivery")
            else None
        ),
        workflow_runs=trace_data.get("workflow_runs", []),
        outbound_deliveries=[
            OutboundDeliveryResponse.model_validate(d)
            for d in trace_data.get("outbound_deliveries", [])
        ],
        dead_letters=[
            DeadLetterResponse.model_validate(dl)
            for dl in trace_data.get("dead_letters", [])
        ],
        audit_logs=trace_data.get("audit_logs", []),
    )


@events_router.get(
    "/{event_id}",
    response_model=DomainEventResponse,
    dependencies=[Depends(require_read_role)],
)
def get_event(
    event_id: UUID,
    db: Session = Depends(get_db),
) -> DomainEventResponse:
    event = EventRepository.get_event(db, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )
    return DomainEventResponse.model_validate(event)


# =====================================================================
# 3. Webhook Sources Endpoints
# =====================================================================
@webhook_sources_router.post(
    "",
    response_model=WebhookSourceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator_role)],
)
def create_webhook_source(
    payload: WebhookSourceCreateRequest,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
    current_user: User = Depends(require_operator_role),
) -> WebhookSourceResponse:
    try:
        source, _raw_secret = service.create_webhook_source(
            db, payload, actor_user_id=current_user.id
        )
        db.commit()
        db.refresh(source)
        return WebhookSourceResponse.model_validate(source)
    except ValueError as err:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@webhook_sources_router.get(
    "",
    response_model=list[WebhookSourceResponse],
    dependencies=[Depends(require_read_role)],
)
def list_webhook_sources(
    is_enabled: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[WebhookSourceResponse]:
    sources = EventRepository.list_webhook_sources(
        db, is_enabled=is_enabled, limit=limit, offset=offset
    )
    return [WebhookSourceResponse.model_validate(s) for s in sources]


@webhook_sources_router.get(
    "/{source_id}",
    response_model=WebhookSourceResponse,
    dependencies=[Depends(require_read_role)],
)
def get_webhook_source(
    source_id: UUID,
    db: Session = Depends(get_db),
) -> WebhookSourceResponse:
    source = EventRepository.get_webhook_source(db, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook source '{source_id}' not found",
        )
    return WebhookSourceResponse.model_validate(source)


@webhook_sources_router.patch(
    "/{source_id}",
    response_model=WebhookSourceResponse,
    dependencies=[Depends(require_operator_role)],
)
def update_webhook_source(
    source_id: UUID,
    payload: WebhookSourceUpdateRequest,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
) -> WebhookSourceResponse:
    try:
        source = service.update_webhook_source(db, source_id, payload)
        db.commit()
        db.refresh(source)
        return WebhookSourceResponse.model_validate(source)
    except ValueError as err:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


# =====================================================================
# 4. Webhook Deliveries Endpoints
# =====================================================================
@webhook_deliveries_router.get(
    "",
    response_model=list[WebhookDeliveryResponse],
    dependencies=[Depends(require_read_role)],
)
def list_webhook_deliveries(
    source_id: UUID | None = Query(None),
    status_filter: WebhookDeliveryStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    deliveries = EventRepository.list_webhook_deliveries(
        db, source_id=source_id, status=status_filter, limit=limit, offset=offset
    )
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]


@webhook_deliveries_router.get(
    "/{delivery_id}",
    response_model=WebhookDeliveryResponse,
    dependencies=[Depends(require_read_role)],
)
def get_webhook_delivery(
    delivery_id: UUID,
    db: Session = Depends(get_db),
) -> WebhookDeliveryResponse:
    delivery = EventRepository.get_webhook_delivery(db, delivery_id)
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook delivery '{delivery_id}' not found",
        )
    return WebhookDeliveryResponse.model_validate(delivery)


# =====================================================================
# 5. Outbound Webhook Subscriptions & Deliveries Endpoints
# =====================================================================
@outbound_webhooks_router.post(
    "/subscriptions",
    response_model=OutboundSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator_role)],
)
def create_outbound_subscription(
    payload: OutboundSubscriptionCreateRequest,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
) -> OutboundSubscriptionResponse:
    try:
        sub, _raw_secret = service.create_outbound_subscription(db, payload)
        return OutboundSubscriptionResponse.model_validate(sub)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@outbound_webhooks_router.get(
    "/subscriptions",
    response_model=list[OutboundSubscriptionResponse],
    dependencies=[Depends(require_read_role)],
)
def list_outbound_subscriptions(
    is_enabled: bool | None = Query(None),
    db: Session = Depends(get_db),
) -> list[OutboundSubscriptionResponse]:
    subs = EventRepository.list_outbound_subscriptions(db, is_enabled=is_enabled)
    return [OutboundSubscriptionResponse.model_validate(s) for s in subs]


@outbound_webhooks_router.get(
    "/deliveries",
    response_model=list[OutboundDeliveryResponse],
    dependencies=[Depends(require_read_role)],
)
def list_outbound_deliveries(
    event_id: UUID | None = Query(None),
    subscription_id: UUID | None = Query(None),
    status_filter: OutboundDeliveryStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[OutboundDeliveryResponse]:
    deliveries = EventRepository.list_outbound_deliveries(
        db,
        event_id=event_id,
        subscription_id=subscription_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [OutboundDeliveryResponse.model_validate(d) for d in deliveries]


# =====================================================================
# 6. Dead Letter Queue Endpoints
# =====================================================================
@dead_letters_router.get(
    "",
    response_model=list[DeadLetterResponse],
    dependencies=[Depends(require_read_role)],
)
def list_dead_letters(
    status_filter: DeadLetterStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[DeadLetterResponse]:
    records = EventRepository.list_dead_letters(
        db, status=status_filter, limit=limit, offset=offset
    )
    return [DeadLetterResponse.model_validate(r) for r in records]


@dead_letters_router.post(
    "/{dlq_id}/retry",
    dependencies=[Depends(require_operator_role)],
)
def retry_dead_letter(
    dlq_id: UUID,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
    current_user: User = Depends(require_operator_role),
) -> dict[str, str]:
    try:
        service.retry_dead_letter(db, dlq_id, actor_user_id=current_user.id)
        return {"status": "retried"}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@dead_letters_router.post(
    "/{dlq_id}/dismiss",
    dependencies=[Depends(require_operator_role)],
)
def dismiss_dead_letter(
    dlq_id: UUID,
    db: Session = Depends(get_db),
    service: EventService = Depends(get_event_service),
    current_user: User = Depends(require_operator_role),
) -> dict[str, str]:
    try:
        service.dismiss_dead_letter(db, dlq_id, actor_user_id=current_user.id)
        return {"status": "dismissed"}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

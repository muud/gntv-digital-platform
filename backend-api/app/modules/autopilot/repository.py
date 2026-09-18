"""Database repository for Sprint 8.5 Autopilot Production & Publishing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.autopilot.models import (
    ApprovalStatus,
    ApprovalType,
    AutopilotApproval,
    AutopilotAuditAction,
    AutopilotAuditLog,
    AutopilotBrief,
    AutopilotProduction,
    AutopilotPublishingAttempt,
    AutopilotPublishingDestination,
    AutopilotPublishingPlan,
    AutopilotResearchTask,
    AutopilotScriptVersion,
    ProductionStatus,
    PublishAttemptStatus,
)
from app.modules.events.security import sanitize_payload


def _utc() -> datetime:
    return datetime.now(UTC)


class AutopilotRepository:
    """Data access for autopilot productions, scripts, approvals, and publications."""

    # ── Productions ──────────────────────────────────────────────────────────

    @staticmethod
    def get_production(db: Session, production_id: UUID) -> AutopilotProduction | None:
        return db.get(AutopilotProduction, production_id)

    @staticmethod
    def get_production_by_idempotency(
        db: Session, key: str
    ) -> AutopilotProduction | None:
        stmt = select(AutopilotProduction).where(AutopilotProduction.idempotency_key == key)
        return db.scalars(stmt).first()

    @staticmethod
    def list_productions(
        db: Session,
        *,
        status: str | None = None,
        brand: str | None = None,
        owner_user_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AutopilotProduction]:
        stmt = select(AutopilotProduction)
        if status:
            stmt = stmt.where(AutopilotProduction.status == status)
        if brand:
            stmt = stmt.where(AutopilotProduction.brand == brand)
        if owner_user_id is not None:
            stmt = stmt.where(AutopilotProduction.owner_user_id == owner_user_id)
        stmt = stmt.order_by(AutopilotProduction.created_at.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt).all())

    # ── Briefs ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_brief(db: Session, production_id: UUID) -> AutopilotBrief | None:
        stmt = select(AutopilotBrief).where(AutopilotBrief.production_id == production_id)
        return db.scalars(stmt).first()

    # ── Research Tasks ────────────────────────────────────────────────────────

    @staticmethod
    def get_research_task(db: Session, production_id: UUID) -> AutopilotResearchTask | None:
        stmt = select(AutopilotResearchTask).where(
            AutopilotResearchTask.production_id == production_id
        )
        return db.scalars(stmt).first()

    # ── Scripts ───────────────────────────────────────────────────────────────

    @staticmethod
    def list_scripts(
        db: Session, production_id: UUID, *, status: str | None = None
    ) -> list[AutopilotScriptVersion]:
        stmt = select(AutopilotScriptVersion).where(
            AutopilotScriptVersion.production_id == production_id
        )
        if status:
            stmt = stmt.where(AutopilotScriptVersion.status == status)
        stmt = stmt.order_by(AutopilotScriptVersion.version.desc())
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_script(db: Session, script_id: UUID) -> AutopilotScriptVersion | None:
        return db.get(AutopilotScriptVersion, script_id)

    # ── Approvals ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_active_approval(
        db: Session, production_id: UUID, approval_type: ApprovalType
    ) -> AutopilotApproval | None:
        stmt = (
            select(AutopilotApproval)
            .where(
                AutopilotApproval.production_id == production_id,
                AutopilotApproval.approval_type == approval_type,
                AutopilotApproval.status == ApprovalStatus.PENDING,
            )
            .order_by(AutopilotApproval.requested_at.desc())
            .limit(1)
        )
        return db.scalars(stmt).first()

    @staticmethod
    def get_approval(db: Session, approval_id: UUID) -> AutopilotApproval | None:
        return db.get(AutopilotApproval, approval_id)

    @staticmethod
    def list_approvals(
        db: Session,
        *,
        production_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AutopilotApproval]:
        stmt = select(AutopilotApproval)
        if production_id:
            stmt = stmt.where(AutopilotApproval.production_id == production_id)
        if status:
            stmt = stmt.where(AutopilotApproval.status == status)
        stmt = stmt.order_by(AutopilotApproval.requested_at.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt).all())

    @staticmethod
    def has_approved_final(db: Session, production_id: UUID) -> bool:
        """Return True if a FINAL_CONTENT approval exists and is APPROVED."""
        stmt = select(AutopilotApproval).where(
            AutopilotApproval.production_id == production_id,
            AutopilotApproval.approval_type == ApprovalType.FINAL_CONTENT,
            AutopilotApproval.status == ApprovalStatus.APPROVED,
        )
        return db.scalars(stmt).first() is not None

    # ── Publishing Destinations ───────────────────────────────────────────────

    @staticmethod
    def get_destination(db: Session, dest_id: UUID) -> AutopilotPublishingDestination | None:
        return db.get(AutopilotPublishingDestination, dest_id)

    @staticmethod
    def list_destinations(
        db: Session, *, enabled: bool | None = None
    ) -> list[AutopilotPublishingDestination]:
        stmt = select(AutopilotPublishingDestination)
        if enabled is not None:
            stmt = stmt.where(AutopilotPublishingDestination.enabled == enabled)
        stmt = stmt.order_by(AutopilotPublishingDestination.name)
        return list(db.scalars(stmt).all())

    # ── Publishing Plan ───────────────────────────────────────────────────────

    @staticmethod
    def list_plan_items(
        db: Session, production_id: UUID
    ) -> list[AutopilotPublishingPlan]:
        stmt = select(AutopilotPublishingPlan).where(
            AutopilotPublishingPlan.production_id == production_id
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_plan_item(
        db: Session, production_id: UUID, destination_id: UUID
    ) -> AutopilotPublishingPlan | None:
        stmt = select(AutopilotPublishingPlan).where(
            AutopilotPublishingPlan.production_id == production_id,
            AutopilotPublishingPlan.destination_id == destination_id,
        )
        return db.scalars(stmt).first()

    # ── Publication Attempts ──────────────────────────────────────────────────

    @staticmethod
    def list_attempts(
        db: Session,
        *,
        production_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AutopilotPublishingAttempt]:
        stmt = select(AutopilotPublishingAttempt)
        if production_id:
            stmt = stmt.where(AutopilotPublishingAttempt.production_id == production_id)
        if status:
            stmt = stmt.where(AutopilotPublishingAttempt.status == status)
        stmt = stmt.order_by(AutopilotPublishingAttempt.created_at.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_attempt_by_idempotency(
        db: Session, key: str
    ) -> AutopilotPublishingAttempt | None:
        stmt = select(AutopilotPublishingAttempt).where(
            AutopilotPublishingAttempt.idempotency_key == key
        )
        return db.scalars(stmt).first()

    @staticmethod
    def get_succeeded_attempt(
        db: Session, production_id: UUID, destination_id: UUID
    ) -> AutopilotPublishingAttempt | None:
        """Return existing successful attempt to prevent duplicate publishing."""
        stmt = select(AutopilotPublishingAttempt).where(
            AutopilotPublishingAttempt.production_id == production_id,
            AutopilotPublishingAttempt.destination_id == destination_id,
            AutopilotPublishingAttempt.status.in_(
                [PublishAttemptStatus.SUCCEEDED, PublishAttemptStatus.VERIFIED]
            ),
        )
        return db.scalars(stmt).first()

    # ── Audit ─────────────────────────────────────────────────────────────────

    @staticmethod
    def create_audit(
        db: Session,
        *,
        action: AutopilotAuditAction,
        production_id: UUID | None = None,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AutopilotAuditLog:
        clean = sanitize_payload(metadata) if metadata else None
        log = AutopilotAuditLog(
            action=action,
            production_id=production_id,
            actor_user_id=actor_user_id,
            metadata_json=clean,
            created_at=_utc(),
        )
        db.add(log)
        db.flush()
        return log

    @staticmethod
    def list_audit_logs(
        db: Session,
        production_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AutopilotAuditLog]:
        stmt = select(AutopilotAuditLog)
        if production_id:
            stmt = stmt.where(AutopilotAuditLog.production_id == production_id)
        stmt = stmt.order_by(AutopilotAuditLog.created_at.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt).all())

    # ── Metrics ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_metrics(db: Session) -> dict[str, Any]:
        def _count(*filters: Any) -> int:
            stmt = select(func.count()).select_from(AutopilotProduction)
            for f in filters:
                stmt = stmt.where(f)
            return db.scalar(stmt) or 0

        total = _count()
        draft = _count(AutopilotProduction.status == ProductionStatus.DRAFT)
        researching = _count(AutopilotProduction.status == ProductionStatus.RESEARCHING)
        scripting = _count(AutopilotProduction.status == ProductionStatus.SCRIPTING)
        awaiting_approval = _count(
            AutopilotProduction.status == ProductionStatus.AWAITING_FINAL_APPROVAL
        )
        publishing_queued = _count(AutopilotProduction.status == ProductionStatus.PUBLISHING_QUEUED)
        publishing = _count(AutopilotProduction.status == ProductionStatus.PUBLISHING)
        published = _count(AutopilotProduction.status == ProductionStatus.PUBLISHED)
        partially = _count(AutopilotProduction.status == ProductionStatus.PARTIALLY_PUBLISHED)
        failed = _count(AutopilotProduction.status == ProductionStatus.FAILED)
        cancelled = _count(AutopilotProduction.status == ProductionStatus.CANCELLED)

        pending_approvals = db.scalar(
            select(func.count()).select_from(AutopilotApproval).where(
                AutopilotApproval.status == ApprovalStatus.PENDING
            )
        ) or 0

        destinations = db.scalar(
            select(func.count()).select_from(AutopilotPublishingDestination).where(
                AutopilotPublishingDestination.enabled.is_(True)
            )
        ) or 0

        oldest_pending: datetime | None = db.scalar(
            select(func.min(AutopilotProduction.created_at)).where(
                AutopilotProduction.status.in_([
                    ProductionStatus.DRAFT,
                    ProductionStatus.RESEARCHING,
                    ProductionStatus.SCRIPTING,
                    ProductionStatus.AWAITING_FINAL_APPROVAL,
                ])
            )
        )
        oldest_age_seconds: int | None = None
        if oldest_pending:
            if oldest_pending.tzinfo is None:
                oldest_pending = oldest_pending.replace(tzinfo=UTC)
            oldest_age_seconds = int((_utc() - oldest_pending).total_seconds())

        return {
            "total_productions": total,
            "draft": draft,
            "researching": researching,
            "scripting": scripting,
            "awaiting_approval": awaiting_approval,
            "publishing_queued": publishing_queued,
            "publishing": publishing,
            "published": published,
            "partially_published": partially,
            "failed": failed,
            "cancelled": cancelled,
            "pending_approvals": pending_approvals,
            "active_destinations": destinations,
            "oldest_pending_age_seconds": oldest_age_seconds,
        }

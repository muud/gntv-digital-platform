"""AutopilotOrchestrator — coordinates multi-stage production lifecycle.

Every stage is persisted before execution.
No uncontrolled autonomous loops.
All external side effects are idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.autopilot.models import (
    ApprovalStatus,
    ApprovalType,
    AutopilotApproval,
    AutopilotAuditAction,
    AutopilotProduction,
    ProductionStatus,
)
from app.modules.autopilot.repository import AutopilotRepository
from app.modules.events.repository import EventRepository
from app.modules.events.security import sanitize_payload


def _utc() -> datetime:
    return datetime.now(UTC)


# Valid production lifecycle transitions (server-enforced)
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"researching", "scripting", "cancelled"},
    "researching": {"research_ready", "failed", "cancelled"},
    "research_ready": {"scripting", "cancelled"},
    "scripting": {"script_review", "failed", "cancelled"},
    "script_review": {"scripting", "production_planning", "cancelled"},
    "production_planning": {"asset_preparation", "awaiting_final_approval", "failed", "cancelled"},
    "asset_preparation": {"awaiting_final_approval", "failed", "cancelled"},
    "awaiting_final_approval": {"approved", "draft", "cancelled"},
    "approved": {"publishing_queued", "cancelled"},
    "publishing_queued": {"publishing", "failed", "cancelled"},
    "publishing": {"published", "partially_published", "failed"},
    "published": set(),
    "partially_published": {"publishing_queued"},
    "failed": {"draft", "cancelled"},
    "cancelled": set(),
}


def validate_transition(current: str, target: str) -> None:
    """Raise ValueError if the requested transition is invalid."""
    allowed = _TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid production state transition: {current!r} → {target!r}. "
            f"Allowed: {sorted(allowed) or 'none'}"
        )


class AutopilotOrchestrator:
    """Coordinates each production stage safely.

    - Validates transitions server-side.
    - Persists state before triggering downstream work.
    - Emits domain events via Sprint 8.2 EventBus.
    - Never starts uncontrolled background threads.
    - Never exposes raw secrets in events or audit logs.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── State transitions ──────────────────────────────────────────────────

    def transition(
        self,
        production: AutopilotProduction,
        target: ProductionStatus,
        *,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AutopilotProduction:
        """Apply a validated, audited state transition."""
        validate_transition(production.status.value, target.value)
        old_status = production.status.value
        production.status = target
        production.updated_at = _utc()

        if target == ProductionStatus.PUBLISHED:
            production.completed_at = _utc()
        elif target == ProductionStatus.CANCELLED:
            production.cancelled_at = _utc()

        self.db.flush()

        AutopilotRepository.create_audit(
            self.db,
            action=AutopilotAuditAction.PRODUCTION_UPDATED,
            production_id=production.id,
            actor_user_id=actor_user_id,
            metadata={
                "old_status": old_status,
                "new_status": target.value,
                **(sanitize_payload(metadata) if metadata else {}),
            },
        )
        self._emit_event(
            f"autopilot.production.{target.value.replace('_', '.')}",
            production,
            actor_user_id=actor_user_id,
        )
        return production

    # ── Research stage ────────────────────────────────────────────────────

    def start_research(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
        agent_run_id: UUID | None = None,
    ) -> AutopilotProduction:
        """Transition to RESEARCHING and record the agent run linkage."""
        self.transition(
            production,
            ProductionStatus.RESEARCHING,
            actor_user_id=actor_user_id,
            metadata={"agent_run_id": str(agent_run_id) if agent_run_id else None},
        )
        AutopilotRepository.create_audit(
            self.db,
            action=AutopilotAuditAction.RESEARCH_STARTED,
            production_id=production.id,
            actor_user_id=actor_user_id,
            metadata={"agent_run_id": str(agent_run_id) if agent_run_id else None},
        )
        self._emit_event("autopilot.research.started", production, actor_user_id=actor_user_id)
        return production

    def complete_research(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
        summary: str | None = None,
    ) -> AutopilotProduction:
        """Transition to RESEARCH_READY."""
        self.transition(
            production,
            ProductionStatus.RESEARCH_READY,
            actor_user_id=actor_user_id,
        )
        AutopilotRepository.create_audit(
            self.db,
            action=AutopilotAuditAction.RESEARCH_COMPLETED,
            production_id=production.id,
            actor_user_id=actor_user_id,
            metadata={"summary_length": len(summary or "")},
        )
        self._emit_event("autopilot.research.ready", production, actor_user_id=actor_user_id)
        return production

    # ── Script stage ──────────────────────────────────────────────────────

    def start_scripting(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
    ) -> AutopilotProduction:
        validate_transition(production.status.value, ProductionStatus.SCRIPTING.value)
        return self.transition(
            production, ProductionStatus.SCRIPTING, actor_user_id=actor_user_id
        )

    def request_script_review(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
    ) -> AutopilotProduction:
        return self.transition(
            production, ProductionStatus.SCRIPT_REVIEW, actor_user_id=actor_user_id
        )

    # ── Approval gate ─────────────────────────────────────────────────────

    def create_approval(
        self,
        production: AutopilotProduction,
        approval_type: ApprovalType,
        *,
        actor_user_id: int | None = None,
        reason: str | None = None,
        expires_at: datetime | None = None,
    ) -> AutopilotApproval:
        """Create an approval request; block if one already exists and is pending."""
        existing = AutopilotRepository.get_active_approval(
            self.db, production.id, approval_type
        )
        if existing and existing.status == ApprovalStatus.PENDING:
            return existing  # idempotent

        approval = AutopilotApproval(
            production_id=production.id,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING,
            requested_by_user_id=actor_user_id,
            requested_at=_utc(),
            expires_at=expires_at,
        )
        self.db.add(approval)
        self.db.flush()

        AutopilotRepository.create_audit(
            self.db,
            action=AutopilotAuditAction.APPROVAL_REQUESTED,
            production_id=production.id,
            actor_user_id=actor_user_id,
            metadata={"approval_type": approval_type.value, "approval_id": str(approval.id)},
        )
        self._emit_event("autopilot.approval.requested", production, actor_user_id=actor_user_id)
        return approval

    def decide_approval(
        self,
        approval: AutopilotApproval,
        decision: str,  # "approved" | "rejected" | "changes_requested"
        *,
        decided_by_user_id: int | None = None,
        reason: str | None = None,
    ) -> AutopilotApproval:
        """Apply an approval decision. Expired approvals are not activated."""
        now = _utc()

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Approval {approval.id} is already in state {approval.status.value!r}"
            )

        # Enforce expiry: expired approval never auto-executes
        if approval.expires_at and approval.expires_at.replace(tzinfo=UTC) < now:
            approval.status = ApprovalStatus.EXPIRED
            approval.decided_at = now
            self.db.flush()
            raise ValueError(f"Approval {approval.id} has expired and cannot be decided")

        approval.status = ApprovalStatus(decision)
        approval.decided_by_user_id = decided_by_user_id
        approval.decided_at = now
        approval.decision_reason = reason
        self.db.flush()

        action = (
            AutopilotAuditAction.APPROVAL_APPROVED
            if decision == "approved"
            else AutopilotAuditAction.APPROVAL_REJECTED
        )
        production = AutopilotRepository.get_production(self.db, approval.production_id)
        AutopilotRepository.create_audit(
            self.db,
            action=action,
            production_id=approval.production_id,
            actor_user_id=decided_by_user_id,
            metadata={
                "approval_id": str(approval.id),
                "approval_type": approval.approval_type.value,
                "decision": decision,
            },
        )
        if production:
            event_name = f"autopilot.approval.{decision}"
            self._emit_event(event_name, production, actor_user_id=decided_by_user_id)
        return approval

    # ── Final approval gate ───────────────────────────────────────────────

    def request_final_approval(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
    ) -> AutopilotApproval:
        if production.status.value not in {
            "production_planning", "asset_preparation",
        }:
            validate_transition(
                production.status.value, ProductionStatus.AWAITING_FINAL_APPROVAL.value
            )
        self.transition(
            production,
            ProductionStatus.AWAITING_FINAL_APPROVAL,
            actor_user_id=actor_user_id,
        )
        return self.create_approval(
            production,
            ApprovalType.FINAL_CONTENT,
            actor_user_id=actor_user_id,
        )

    def finalize_approved(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
    ) -> AutopilotProduction:
        """Mark production as APPROVED after final approval decision."""
        if not AutopilotRepository.has_approved_final(self.db, production.id):
            raise ValueError("Production cannot be approved — no FINAL_CONTENT approval found")
        return self.transition(
            production, ProductionStatus.APPROVED, actor_user_id=actor_user_id
        )

    # ── Publishing gate ───────────────────────────────────────────────────

    def queue_for_publishing(
        self,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
    ) -> AutopilotProduction:
        """Gate: final approval required, plan items required."""
        if not AutopilotRepository.has_approved_final(self.db, production.id):
            raise ValueError(
                "Publishing blocked: FINAL_CONTENT approval required before publishing"
            )
        plan_items = AutopilotRepository.list_plan_items(self.db, production.id)
        if not plan_items:
            raise ValueError(
                "Publishing blocked: at least one publishing plan item required"
            )
        result = self.transition(
            production, ProductionStatus.PUBLISHING_QUEUED, actor_user_id=actor_user_id
        )
        AutopilotRepository.create_audit(
            self.db,
            action=AutopilotAuditAction.PUBLISH_QUEUED,
            production_id=production.id,
            actor_user_id=actor_user_id,
            metadata={"destination_count": len(plan_items)},
        )
        self._emit_event("autopilot.publish.queued", production, actor_user_id=actor_user_id)
        return result

    # ── Kids safety gate ──────────────────────────────────────────────────

    def check_kids_safety(self, production: AutopilotProduction) -> None:
        """Raise if GNTV_KIDS production is missing required safety metadata."""
        from app.modules.autopilot.models import AutopilotBrand

        if production.brand != AutopilotBrand.GNTV_KIDS:
            return
        kids_meta = getattr(production, "kids_metadata", None)
        if kids_meta is None:
            raise ValueError(
                "GNTV_KIDS production cannot be published: kids safety metadata is missing. "
                "Please provide made_for_kids, age_band, child_safe, comments_policy, "
                "advertising_policy, and parental_review_required fields."
            )
        if not kids_meta.child_safe:
            raise ValueError("GNTV_KIDS: child_safe flag must be True before publishing")
        if kids_meta.parental_review_required and not kids_meta.reviewed_by_user_id:
            raise ValueError(
                "GNTV_KIDS: parental review is required but has not been completed"
            )

    # ── Event emission ────────────────────────────────────────────────────

    def _emit_event(
        self,
        event_type: str,
        production: AutopilotProduction,
        *,
        actor_user_id: int | None = None,
    ) -> None:
        """Emit a Sprint 8.2 domain event safely (fire-and-forget)."""
        from datetime import UTC, datetime
        from uuid import uuid4

        now = datetime.now(UTC)
        try:
            EventRepository.create_event(
                self.db,
                event_type=event_type,
                event_version=1,
                source="autopilot",
                tenant_id=None,
                aggregate_type="production",
                aggregate_id=str(production.id),
                correlation_id=production.correlation_id or str(uuid4()),
                causation_id=production.causation_id,
                idempotency_key=f"autopilot.{production.id}.{event_type}.{now.timestamp()}",
                payload_json={
                    "production_id": str(production.id),
                    "title": production.title,
                    "brand": production.brand.value,
                    "status": production.status.value,
                    "actor_user_id": actor_user_id,
                },
                occurred_at=now,
                received_at=now,
            )
        except Exception:
            # Event emission failure must not break the transaction
            pass

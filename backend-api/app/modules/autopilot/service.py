"""Autopilot production and publishing orchestration service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.agents.models import AgentDefinition, AgentStatus, AgentType
from app.modules.agents.schemas import AgentRunCreate
from app.modules.agents.service import AgentControlService
from app.modules.autopilot.models import (
    ApprovalStatus,
    ApprovalType,
    AssetStatus,
    AutopilotApproval,
    AutopilotAsset,
    AutopilotAuditAction,
    AutopilotAuditLog,
    AutopilotBrand,
    AutopilotBrief,
    AutopilotProduction,
    AutopilotProductionPlan,
    AutopilotPublishingAttempt,
    AutopilotPublishingDestination,
    AutopilotPublishingPlan,
    AutopilotResearchTask,
    AutopilotScriptVersion,
    ProductionStatus,
    PublishAttemptStatus,
    PublishingPolicyCode,
    ResearchStatus,
    ScriptStatus,
)
from app.modules.autopilot.providers import default_publishing_registry
from app.modules.autopilot.schemas import (
    ApprovalDecision,
    ApprovalRequestCreate,
    AssetCreate,
    BriefUpsert,
    DestinationCreate,
    ProductionCreate,
    ProductionPlanCreate,
    ProductionUpdate,
    PublishingPlanCreate,
    PublishRequest,
    ScriptCreate,
    StageRequest,
)
from app.modules.events.models import EventProcessingStatus
from app.modules.events.repository import EventRepository
from app.modules.events.security import sanitize_payload
from app.modules.jobs.models import DurableJob
from app.modules.jobs.queue import DatabaseJobQueue


def utc_now() -> datetime:
    return datetime.now(UTC)


TERMINAL_PRODUCTION_STATES = {
    ProductionStatus.PUBLISHED,
    ProductionStatus.PARTIALLY_PUBLISHED,
    ProductionStatus.FAILED,
    ProductionStatus.CANCELLED,
}


class AutopilotService:
    """Transaction-neutral orchestration service."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.queue = DatabaseJobQueue()

    def list_productions(
        self, status: ProductionStatus | None = None
    ) -> list[AutopilotProduction]:
        stmt = (
            select(AutopilotProduction)
            .options(
                selectinload(AutopilotProduction.brief),
                selectinload(AutopilotProduction.scripts),
                selectinload(AutopilotProduction.assets),
                selectinload(AutopilotProduction.approvals),
                selectinload(AutopilotProduction.publishing_plans),
                selectinload(AutopilotProduction.attempts),
            )
            .order_by(AutopilotProduction.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(AutopilotProduction.status == status)
        return list(self.db.scalars(stmt).unique())

    def get_production(self, production_id: UUID) -> AutopilotProduction:
        production = self.db.scalar(
            select(AutopilotProduction)
            .options(
                selectinload(AutopilotProduction.brief),
                selectinload(AutopilotProduction.scripts),
                selectinload(AutopilotProduction.assets),
                selectinload(AutopilotProduction.approvals),
                selectinload(AutopilotProduction.publishing_plans).selectinload(
                    AutopilotPublishingPlan.destination
                ),
                selectinload(AutopilotProduction.attempts),
            )
            .where(AutopilotProduction.id == production_id)
        )
        if production is None:
            raise ValueError("Production not found")
        return production

    def create_production(
        self, payload: ProductionCreate, actor_user_id: int | None = None
    ) -> AutopilotProduction:
        key = payload.idempotency_key
        if key:
            existing = self.db.scalar(
                select(AutopilotProduction).where(
                    AutopilotProduction.idempotency_key == key
                )
            )
            if existing is not None:
                return existing
        production = AutopilotProduction(
            **payload.model_dump(exclude={"correlation_id", "idempotency_key"}),
            owner_user_id=actor_user_id,
            correlation_id=payload.correlation_id or f"autopilot-{uuid4()}",
            idempotency_key=key,
        )
        self.db.add(production)
        self.db.flush()
        self.audit(
            production,
            AutopilotAuditAction.PRODUCTION_CREATED,
            actor_user_id,
            {"title": production.title},
        )
        self.emit_event("autopilot.production.created", production)
        return production

    def update_production(
        self,
        production_id: UUID,
        payload: ProductionUpdate,
        actor_user_id: int | None = None,
    ) -> AutopilotProduction:
        production = self.get_production(production_id)
        self._ensure_mutable(production)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(production, key, value)
        production.updated_at = utc_now()
        self.audit(production, AutopilotAuditAction.PRODUCTION_UPDATED, actor_user_id)
        self.emit_event("autopilot.production.updated", production)
        self.db.flush()
        return production

    def upsert_brief(
        self, production_id: UUID, payload: BriefUpsert
    ) -> AutopilotBrief:
        production = self.get_production(production_id)
        self._ensure_mutable(production)
        safe = sanitize_payload(payload.model_dump())
        brief = production.brief
        if brief is None:
            brief = AutopilotBrief(production_id=production.id, **safe)
            self.db.add(brief)
        else:
            for key, value in safe.items():
                setattr(brief, key, value)
            brief.updated_at = utc_now()
        self.db.flush()
        return brief

    def start_research(
        self,
        production_id: UUID,
        request: StageRequest,
        actor_user_id: int | None = None,
    ) -> AutopilotResearchTask:
        production = self.get_production(production_id)
        key = request.idempotency_key or f"research:{production.id}"
        existing = self.db.scalar(
            select(AutopilotResearchTask).where(
                AutopilotResearchTask.production_id == production.id,
                AutopilotResearchTask.idempotency_key == key,
            )
        )
        if existing is not None:
            return existing
        self._transition(
            production,
            {ProductionStatus.DRAFT, ProductionStatus.RESEARCH_READY},
            ProductionStatus.RESEARCHING,
        )
        run_id = self._create_agent_run(
            AgentType.RESEARCH_AGENT,
            request.agent_id,
            production,
            "autopilot.research",
            key,
            actor_user_id,
        )
        task = AutopilotResearchTask(
            production_id=production.id,
            status=ResearchStatus.RUNNING,
            agent_run_id=run_id,
            idempotency_key=key,
            started_at=utc_now(),
            generated_material_json={"ai_generated": True},
        )
        self.db.add(task)
        self.db.flush()
        self.enqueue_job(
            "AUTOPILOT_RESEARCH",
            {"production_id": str(production.id), "research_task_id": str(task.id)},
            f"{key}:job",
            production,
            actor_user_id,
        )
        self.audit(production, AutopilotAuditAction.RESEARCH_STARTED, actor_user_id)
        self.emit_event("autopilot.research.started", production)
        return task

    def complete_research_task(self, task_id: UUID) -> AutopilotResearchTask:
        task = self.db.get(AutopilotResearchTask, task_id)
        if task is None:
            raise ValueError("Research task not found")
        task.status = ResearchStatus.READY
        task.completed_at = utc_now()
        task.summary = task.summary or "Mock research summary awaiting human review."
        task.key_facts = task.key_facts or [
            {"fact": "AI generated research requires editorial verification."}
        ]
        production = self.get_production(task.production_id)
        production.status = ProductionStatus.RESEARCH_READY
        self.audit(production, AutopilotAuditAction.RESEARCH_COMPLETED, None)
        self.emit_event("autopilot.research.ready", production)
        self.db.flush()
        return task

    def generate_script(
        self,
        production_id: UUID,
        request: StageRequest,
        actor_user_id: int | None = None,
    ) -> AutopilotScriptVersion:
        production = self.get_production(production_id)
        self._transition(
            production,
            {ProductionStatus.RESEARCH_READY, ProductionStatus.SCRIPT_REVIEW},
            ProductionStatus.SCRIPTING,
        )
        key = request.idempotency_key or f"script:{production.id}"
        run_id = self._create_agent_run(
            AgentType.SCRIPT_WRITER_AGENT,
            request.agent_id,
            production,
            "autopilot.script",
            key,
            actor_user_id,
        )
        version = (max([s.version for s in production.scripts], default=0) + 1)
        script = AutopilotScriptVersion(
            production_id=production.id,
            version=version,
            language=production.language,
            title=production.title,
            body="Draft script generated through the AI Agent Control Plane.",
            generated_by_agent_run_id=run_id,
            created_by_user_id=actor_user_id,
            status=ScriptStatus.REVIEW,
        )
        for older in production.scripts:
            if older.status not in {ScriptStatus.APPROVED, ScriptStatus.SUPERSEDED}:
                older.status = ScriptStatus.SUPERSEDED
        self.db.add(script)
        production.status = ProductionStatus.SCRIPT_REVIEW
        self.db.flush()
        self.enqueue_job(
            "AUTOPILOT_SCRIPT_GENERATION",
            {"production_id": str(production.id), "script_id": str(script.id)},
            f"{key}:job",
            production,
            actor_user_id,
        )
        self.audit(production, AutopilotAuditAction.SCRIPT_CREATED, actor_user_id)
        self.emit_event("autopilot.script.generated", production)
        return script

    def create_script(
        self, production_id: UUID, payload: ScriptCreate, actor_user_id: int | None
    ) -> AutopilotScriptVersion:
        production = self.get_production(production_id)
        version = max([s.version for s in production.scripts], default=0) + 1
        script = AutopilotScriptVersion(
            production_id=production.id,
            version=version,
            created_by_user_id=actor_user_id,
            **payload.model_dump(),
        )
        self.db.add(script)
        self.db.flush()
        self.audit(production, AutopilotAuditAction.SCRIPT_CREATED, actor_user_id)
        return script

    def approve_script(
        self, script_id: UUID, actor_user_id: int | None
    ) -> AutopilotScriptVersion:
        script = self.db.get(AutopilotScriptVersion, script_id)
        if script is None:
            raise ValueError("Script not found")
        script.status = ScriptStatus.APPROVED
        script.approved_at = utc_now()
        production = self.get_production(script.production_id)
        self.audit(production, AutopilotAuditAction.SCRIPT_APPROVED, actor_user_id)
        self.emit_event("autopilot.script.approved", production)
        self.db.flush()
        return script

    def create_production_plan(
        self, production_id: UUID, payload: ProductionPlanCreate, actor_user_id: int | None
    ) -> AutopilotProductionPlan:
        production = self.get_production(production_id)
        self._transition(
            production,
            {ProductionStatus.SCRIPT_REVIEW, ProductionStatus.PRODUCTION_PLANNING},
            ProductionStatus.PRODUCTION_PLANNING,
        )
        plan = production.production_plan
        if plan is None:
            plan = AutopilotProductionPlan(
                production_id=production.id, **payload.model_dump()
            )
            self.db.add(plan)
        else:
            for key, value in payload.model_dump().items():
                setattr(plan, key, value)
        self.db.flush()
        self.enqueue_job(
            "AUTOPILOT_PRODUCTION_PLAN",
            {"production_id": str(production.id), "plan_id": str(plan.id)},
            f"plan:{production.id}",
            production,
            actor_user_id,
        )
        self.audit(
            production, AutopilotAuditAction.PRODUCTION_PLAN_CREATED, actor_user_id
        )
        self.emit_event("autopilot.production_plan.ready", production)
        return plan

    def add_asset(
        self, production_id: UUID, payload: AssetCreate, actor_user_id: int | None
    ) -> AutopilotAsset:
        production = self.get_production(production_id)
        asset = AutopilotAsset(
            production_id=production.id,
            **sanitize_payload(payload.model_dump()),
        )
        if asset.status == AssetStatus.APPROVED:
            asset.approved_at = utc_now()
        self.db.add(asset)
        self.db.flush()
        self.audit(production, AutopilotAuditAction.ASSET_ADDED, actor_user_id)
        self.emit_event("autopilot.asset.ready", production)
        return asset

    def request_approval(
        self,
        production_id: UUID,
        payload: ApprovalRequestCreate,
        actor_user_id: int | None,
    ) -> AutopilotApproval:
        production = self.get_production(production_id)
        approval = AutopilotApproval(
            production_id=production.id,
            approval_type=payload.approval_type,
            requested_by_user_id=actor_user_id,
            expires_at=payload.expires_at,
        )
        self.db.add(approval)
        if payload.approval_type == ApprovalType.FINAL_CONTENT:
            production.status = ProductionStatus.AWAITING_FINAL_APPROVAL
        self.db.flush()
        self.audit(production, AutopilotAuditAction.APPROVAL_REQUESTED, actor_user_id)
        self.emit_event("autopilot.approval.requested", production)
        return approval

    def decide_approval(
        self,
        approval_id: UUID,
        approved: bool,
        payload: ApprovalDecision,
        actor_user_id: int | None,
    ) -> AutopilotApproval:
        approval = self.db.get(AutopilotApproval, approval_id)
        if approval is None:
            raise ValueError("Approval not found")
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("Approval is not pending")
        if approval.expires_at and approval.expires_at <= utc_now():
            approval.status = ApprovalStatus.EXPIRED
            self.db.flush()
            raise ValueError("Approval has expired")
        approval.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        approval.decided_by_user_id = actor_user_id
        approval.decided_at = utc_now()
        approval.decision_reason = payload.reason
        production = self.get_production(approval.production_id)
        if approved and approval.approval_type == ApprovalType.FINAL_CONTENT:
            production.status = ProductionStatus.APPROVED
        action = (
            AutopilotAuditAction.APPROVAL_APPROVED
            if approved
            else AutopilotAuditAction.APPROVAL_REJECTED
        )
        self.audit(production, action, actor_user_id)
        self.emit_event(
            "autopilot.approval.approved"
            if approved
            else "autopilot.approval.rejected",
            production,
        )
        self.db.flush()
        return approval

    def create_destination(
        self, payload: DestinationCreate, actor_user_id: int | None
    ) -> AutopilotPublishingDestination:
        destination = AutopilotPublishingDestination(
            **sanitize_payload(payload.model_dump())
        )
        self.db.add(destination)
        self.db.flush()
        return destination

    def list_destinations(self) -> list[AutopilotPublishingDestination]:
        return list(
            self.db.scalars(
                select(AutopilotPublishingDestination).order_by(
                    AutopilotPublishingDestination.created_at.desc()
                )
            )
        )

    def create_publishing_plan(
        self, production_id: UUID, payload: PublishingPlanCreate, actor_user_id: int | None
    ) -> AutopilotPublishingPlan:
        production = self.get_production(production_id)
        destination = self.db.get(AutopilotPublishingDestination, payload.destination_id)
        if destination is None:
            raise ValueError("Destination not found")
        plan = AutopilotPublishingPlan(
            production_id=production.id,
            **sanitize_payload(payload.model_dump()),
        )
        self.db.add(plan)
        self.db.flush()
        self.audit(production, AutopilotAuditAction.PUBLISH_PLAN_CREATED, actor_user_id)
        return plan

    def publish(
        self, production_id: UUID, payload: PublishRequest, actor_user_id: int | None
    ) -> list[AutopilotPublishingAttempt]:
        production = self.get_production(production_id)
        if production.status == ProductionStatus.PUBLISHED:
            return list(
                self.db.scalars(
                    select(AutopilotPublishingAttempt).where(
                        AutopilotPublishingAttempt.production_id == production.id
                    )
                )
            )
        self._assert_publishable(production)
        attempts: list[AutopilotPublishingAttempt] = []
        for plan in production.publishing_plans:
            successful = self.db.scalar(
                select(AutopilotPublishingAttempt).where(
                    AutopilotPublishingAttempt.publishing_plan_id == plan.id,
                    AutopilotPublishingAttempt.status.in_(
                        [
                            PublishAttemptStatus.SUCCEEDED,
                            PublishAttemptStatus.VERIFICATION_PENDING,
                            PublishAttemptStatus.VERIFIED,
                        ]
                    ),
                )
            )
            if successful is not None:
                continue
            key_base = payload.idempotency_key or f"publish:{production.id}"
            key = f"{key_base}:{plan.id}"
            existing = self.db.scalar(
                select(AutopilotPublishingAttempt).where(
                    AutopilotPublishingAttempt.idempotency_key == key
                )
            )
            if existing is not None:
                attempts.append(existing)
                continue
            attempt_no = (
                self.db.scalar(
                    select(func.count(AutopilotPublishingAttempt.id)).where(
                        AutopilotPublishingAttempt.publishing_plan_id == plan.id
                    )
                )
                or 0
            ) + 1
            attempt = AutopilotPublishingAttempt(
                production_id=production.id,
                publishing_plan_id=plan.id,
                destination_id=plan.destination_id,
                status=(
                    PublishAttemptStatus.SCHEDULED
                    if plan.scheduled_at
                    else PublishAttemptStatus.QUEUED
                ),
                attempt_number=attempt_no,
                idempotency_key=key,
                scheduled_at=plan.scheduled_at,
            )
            self.db.add(attempt)
            self.db.flush()
            self.enqueue_job(
                "AUTOPILOT_PUBLISH",
                {"production_id": str(production.id), "attempt_id": str(attempt.id)},
                f"{key}:job",
                production,
                actor_user_id,
                scheduled_for=plan.scheduled_at,
            )
            attempts.append(attempt)
        if not attempts and production.publishing_plans:
            return list(production.attempts)
        production.status = ProductionStatus.PUBLISHING_QUEUED
        self.audit(production, AutopilotAuditAction.PUBLISH_QUEUED, actor_user_id)
        self.emit_event("autopilot.publish.queued", production)
        self.db.flush()
        return attempts

    def execute_publish_attempt(self, attempt_id: UUID) -> AutopilotPublishingAttempt:
        attempt = self.db.get(AutopilotPublishingAttempt, attempt_id)
        if attempt is None:
            raise ValueError("Publish attempt not found")
        if attempt.status in {
            PublishAttemptStatus.SUCCEEDED,
            PublishAttemptStatus.VERIFICATION_PENDING,
            PublishAttemptStatus.VERIFIED,
        }:
            return attempt
        production = self.get_production(attempt.production_id)
        plan = self.db.get(AutopilotPublishingPlan, attempt.publishing_plan_id)
        if plan is None:
            raise ValueError("Publishing plan not found")
        attempt.status = PublishAttemptStatus.PUBLISHING
        attempt.started_at = utc_now()
        production.status = ProductionStatus.PUBLISHING
        self.audit(production, AutopilotAuditAction.PUBLISH_STARTED, None)
        self.emit_event("autopilot.publish.started", production)
        try:
            provider = default_publishing_registry.get("mock")
            result = provider.publish(plan)
            attempt.provider_reference = result.provider_reference
            attempt.metadata_json = sanitize_payload(result.metadata)
            attempt.status = PublishAttemptStatus.VERIFICATION_PENDING
            attempt.completed_at = utc_now()
            self.audit(production, AutopilotAuditAction.PUBLISH_SUCCEEDED, None)
            self.emit_event("autopilot.publish.succeeded", production)
            self.verify_publication(attempt.id)
        except Exception as exc:
            attempt.status = PublishAttemptStatus.FAILED
            attempt.safe_error_summary = str(exc)[:1000]
            attempt.completed_at = utc_now()
            self.audit(
                production,
                AutopilotAuditAction.PUBLISH_FAILED,
                None,
                {"error": attempt.safe_error_summary},
            )
            self.emit_event("autopilot.publish.failed", production)
        self._refresh_publication_state(production)
        self.db.flush()
        return attempt

    def verify_publication(self, attempt_id: UUID) -> AutopilotPublishingAttempt:
        attempt = self.db.get(AutopilotPublishingAttempt, attempt_id)
        if attempt is None:
            raise ValueError("Publish attempt not found")
        if not attempt.provider_reference:
            return attempt
        if default_publishing_registry.get("mock").verify_publication(
            attempt.provider_reference
        ):
            attempt.status = PublishAttemptStatus.VERIFIED
            production = self.get_production(attempt.production_id)
            self.audit(production, AutopilotAuditAction.PUBLISH_VERIFIED, None)
            self.emit_event("autopilot.publish.succeeded", production)
            self._refresh_publication_state(production)
        self.db.flush()
        return attempt

    def cancel_production(
        self, production_id: UUID, actor_user_id: int | None
    ) -> AutopilotProduction:
        production = self.get_production(production_id)
        if production.status in TERMINAL_PRODUCTION_STATES:
            return production
        production.status = ProductionStatus.CANCELLED
        production.cancelled_at = utc_now()
        for attempt in production.attempts:
            if attempt.status in {
                PublishAttemptStatus.QUEUED,
                PublishAttemptStatus.SCHEDULED,
            }:
                attempt.status = PublishAttemptStatus.CANCELLED
        self.audit(production, AutopilotAuditAction.PRODUCTION_CANCELLED, actor_user_id)
        self.db.flush()
        return production

    def list_approvals(self) -> list[AutopilotApproval]:
        return list(
            self.db.scalars(
                select(AutopilotApproval).order_by(AutopilotApproval.requested_at.desc())
            )
        )

    def list_attempts(self) -> list[AutopilotPublishingAttempt]:
        return list(
            self.db.scalars(
                select(AutopilotPublishingAttempt).order_by(
                    AutopilotPublishingAttempt.created_at.desc()
                )
            )
        )

    def metrics(self) -> dict[str, Any]:
        state_counts = {
            key.value: count
            for key, count in self.db.execute(
                select(AutopilotProduction.status, func.count()).group_by(
                    AutopilotProduction.status
                )
            ).tuples()
        }
        status_by_platform: dict[str, dict[str, int]] = {}
        for platform, status, count in self.db.execute(
            select(
                AutopilotPublishingDestination.platform,
                AutopilotPublishingAttempt.status,
                func.count(),
            )
            .join(
                AutopilotPublishingAttempt,
                AutopilotPublishingAttempt.destination_id
                == AutopilotPublishingDestination.id,
            )
            .group_by(
                AutopilotPublishingDestination.platform,
                AutopilotPublishingAttempt.status,
            )
        ).tuples():
            status_by_platform.setdefault(platform.value, {})[status.value] = count
        jobs = {
            key: count
            for key, count in self.db.execute(
                select(DurableJob.status, func.count(DurableJob.id))
                .where(DurableJob.job_type.like("AUTOPILOT_%"))
                .group_by(DurableJob.status)
            ).tuples()
        }
        return {
            "productions_by_state": state_counts,
            "awaiting_approval": state_counts.get(
                ProductionStatus.AWAITING_FINAL_APPROVAL.value, 0
            ),
            "scheduled_publications": self.db.scalar(
                select(func.count(AutopilotPublishingAttempt.id)).where(
                    AutopilotPublishingAttempt.status == PublishAttemptStatus.SCHEDULED
                )
            )
            or 0,
            "publishing_queue_depth": self.db.scalar(
                select(func.count(AutopilotPublishingAttempt.id)).where(
                    AutopilotPublishingAttempt.status.in_(
                        [PublishAttemptStatus.QUEUED, PublishAttemptStatus.PUBLISHING]
                    )
                )
            )
            or 0,
            "destination_success_failure": status_by_platform,
            "partial_publishing_count": state_counts.get(
                ProductionStatus.PARTIALLY_PUBLISHED.value, 0
            ),
            "oldest_pending_production": self.db.scalar(
                select(func.min(AutopilotProduction.created_at)).where(
                    AutopilotProduction.status.not_in(list(TERMINAL_PRODUCTION_STATES))
                )
            ),
            "ai_agent_usage": self.db.scalar(
                select(func.count(AutopilotResearchTask.agent_run_id)).where(
                    AutopilotResearchTask.agent_run_id.is_not(None)
                )
            )
            or 0,
            "durable_job_status": {str(k.value): v for k, v in jobs.items()},
        }

    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        production: AutopilotProduction,
        actor_user_id: int | None,
        scheduled_for: datetime | None = None,
    ) -> DurableJob:
        return self.queue.enqueue(
            self.db,
            job_type=job_type,
            queue_name="autopilot",
            payload=sanitize_payload(payload),
            idempotency_key=idempotency_key,
            correlation_id=production.correlation_id,
            causation_id=production.causation_id,
            scheduled_for=scheduled_for,
            actor_user_id=actor_user_id,
        )

    def audit(
        self,
        production: AutopilotProduction,
        action: AutopilotAuditAction,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AutopilotAuditLog:
        row = AutopilotAuditLog(
            production_id=production.id,
            action=action,
            actor_user_id=actor_user_id,
            correlation_id=production.correlation_id,
            causation_id=production.causation_id,
            metadata_json=sanitize_payload(metadata or {}),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def emit_event(self, event_type: str, production: AutopilotProduction) -> None:
        EventRepository.create_event(
            self.db,
            event_type=event_type,
            event_version=1,
            source="autopilot",
            tenant_id=None,
            aggregate_type="autopilot_production",
            aggregate_id=str(production.id),
            correlation_id=production.correlation_id,
            causation_id=production.causation_id,
            idempotency_key=f"{event_type}:{production.id}:{uuid4()}",
            payload_json=sanitize_payload(
                {"production_id": str(production.id), "status": production.status.value}
            ),
            occurred_at=utc_now(),
            received_at=utc_now(),
            status=EventProcessingStatus.RECEIVED,
        )

    def _create_agent_run(
        self,
        agent_type: AgentType,
        requested_agent_id: UUID | None,
        production: AutopilotProduction,
        trigger_source: str,
        idempotency_key: str,
        actor_user_id: int | None,
    ) -> UUID | None:
        stmt = select(AgentDefinition).where(
            AgentDefinition.status == AgentStatus.ACTIVE
        )
        if requested_agent_id:
            stmt = stmt.where(AgentDefinition.id == requested_agent_id)
        else:
            stmt = stmt.where(AgentDefinition.agent_type == agent_type)
        agent = self.db.scalar(stmt.order_by(AgentDefinition.created_at.desc()))
        if agent is None:
            return None
        run = AgentControlService(self.db).create_run(
            agent.id,
            AgentRunCreate(
                input_json={
                    "production_id": str(production.id),
                    "title": production.title,
                    "status": production.status.value,
                    "untrusted_brief": (production.brief.metadata_json if production.brief else {}),
                },
                context_json={"trusted_context": "autopilot stage request"},
                trigger_type="autopilot",
                trigger_source=trigger_source,
                correlation_id=production.correlation_id,
                causation_id=production.causation_id,
                idempotency_key=idempotency_key,
            ),
            actor_user_id,
        )
        return run.id

    def _assert_publishable(self, production: AutopilotProduction) -> None:
        if production.status not in {
            ProductionStatus.APPROVED,
            ProductionStatus.PUBLISHING_QUEUED,
            ProductionStatus.PARTIALLY_PUBLISHED,
        }:
            raise ValueError("Production is not approved for publishing")
        final_approval = any(
            a.approval_type == ApprovalType.FINAL_CONTENT
            and a.status == ApprovalStatus.APPROVED
            for a in production.approvals
        )
        if not final_approval:
            raise ValueError("Final approval is required before publishing")
        if not production.publishing_plans:
            raise ValueError("Publishing plan is required")
        for plan in production.publishing_plans:
            policies = set(plan.destination.publishing_policy or [])
            policies.update(plan.platform_metadata_json.get("policies", []) if plan.platform_metadata_json else [])
            if PublishingPolicyCode.REQUIRE_THUMBNAIL.value in policies and not plan.thumbnail_asset_id:
                raise ValueError("Thumbnail is required by publishing policy")
            if PublishingPolicyCode.REQUIRE_SUBTITLES.value in policies and not plan.captions:
                raise ValueError("Subtitles are required by publishing policy")
            if (
                production.brand == AutopilotBrand.GNTV_KIDS
                or PublishingPolicyCode.REQUIRE_KIDS_METADATA.value in policies
            ):
                kids = plan.kids_metadata_json or {}
                required = {
                    "made_for_kids",
                    "age_band",
                    "child_safe",
                    "comments_policy",
                    "advertising_policy",
                    "parental_review_required",
                }
                if not required.issubset(kids) or kids.get("child_safe") is not True:
                    raise ValueError("Complete child-safe metadata is required")

    def _refresh_publication_state(self, production: AutopilotProduction) -> None:
        if not production.publishing_plans:
            return
        plan_ids = {p.id for p in production.publishing_plans}
        attempts = list(
            self.db.scalars(
                select(AutopilotPublishingAttempt).where(
                    AutopilotPublishingAttempt.production_id == production.id
                )
            )
        )
        good = {
            a.publishing_plan_id
            for a in attempts
            if a.status
            in {
                PublishAttemptStatus.SUCCEEDED,
                PublishAttemptStatus.VERIFICATION_PENDING,
                PublishAttemptStatus.VERIFIED,
            }
        }
        failed = any(a.status == PublishAttemptStatus.FAILED for a in attempts)
        if good == plan_ids:
            production.status = ProductionStatus.PUBLISHED
            production.completed_at = utc_now()
            self.audit(production, AutopilotAuditAction.PRODUCTION_COMPLETED, None)
            self.emit_event("autopilot.production.completed", production)
        elif good and failed:
            production.status = ProductionStatus.PARTIALLY_PUBLISHED
        elif failed and not good:
            production.status = ProductionStatus.FAILED

    def _transition(
        self,
        production: AutopilotProduction,
        allowed: set[ProductionStatus],
        target: ProductionStatus,
    ) -> None:
        if production.status not in allowed:
            raise ValueError(
                f"Cannot transition production from {production.status.value} to {target.value}"
            )
        production.status = target

    def _ensure_mutable(self, production: AutopilotProduction) -> None:
        if production.status in TERMINAL_PRODUCTION_STATES:
            raise ValueError("Terminal production cannot be changed")

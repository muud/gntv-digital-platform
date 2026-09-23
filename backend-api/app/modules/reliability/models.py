"""Persisted models for Sprint 8.6 Reliability, Monitoring, Recovery & Disaster Recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.jobs.models import enum_type


def utc_now() -> datetime:
    return datetime.now(UTC)


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class ComponentType(StrEnum):
    API = "API"
    DATABASE = "DATABASE"
    EVENT_BUS = "EVENT_BUS"
    WORKFLOW_ENGINE = "WORKFLOW_ENGINE"
    JOB_QUEUE = "JOB_QUEUE"
    WORKERS = "WORKERS"
    AI_AGENT_CONTROL = "AI_AGENT_CONTROL"
    AUTOPILOT = "AUTOPILOT"
    PUBLISHING = "PUBLISHING"
    STUDIO = "STUDIO"


class IncidentSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class IncidentState(StrEnum):
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RECOVERING = "RECOVERING"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class RecoveryActionType(StrEnum):
    RETRY_FAILED_JOB = "RETRY_FAILED_JOB"
    REQUEUE_DLQ_JOB = "REQUEUE_DLQ_JOB"
    RESTART_WORKFLOW_RUN = "RESTART_WORKFLOW_RUN"
    RETRY_WEBHOOK_DELIVERY = "RETRY_WEBHOOK_DELIVERY"
    RETRY_AGENT_RUN = "RETRY_AGENT_RUN"
    RETRY_AUTOPILOT_PUBLICATION = "RETRY_AUTOPILOT_PUBLICATION"
    VERIFY_COMPONENT_HEALTH = "VERIFY_COMPONENT_HEALTH"
    MARK_COMPONENT_DEGRADED = "MARK_COMPONENT_DEGRADED"
    ESCALATE_INCIDENT = "ESCALATE_INCIDENT"


class RecoveryRunStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RecoveryStepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BackupStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    VERIFIED = "VERIFIED"


class BackupType(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    TRANSACTION_LOG = "TRANSACTION_LOG"


class DRReadinessStatus(StrEnum):
    READY = "READY"
    PARTIALLY_READY = "PARTIALLY_READY"
    NOT_READY = "NOT_READY"
    UNKNOWN = "UNKNOWN"


class SystemHealthSnapshot(Base):
    """Aggregate health state snapshot across platform services."""

    __tablename__ = "reliability_health_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    overall_status: Mapped[HealthStatus] = mapped_column(
        enum_type(HealthStatus, "reliability_overall_health_status_enum"),
        nullable=False,
        default=HealthStatus.HEALTHY,
    )
    health_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    healthy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    degraded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unhealthy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    checks: Mapped[list[ServiceHealthCheck]] = relationship(
        "ServiceHealthCheck",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="ServiceHealthCheck.component",
    )

    __table_args__ = (
        Index("ix_reliability_snapshots_observed", "observed_at"),
        Index("ix_reliability_snapshots_status", "overall_status"),
    )


class ServiceHealthCheck(Base):
    """Component-level health check observation."""

    __tablename__ = "reliability_service_health_checks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reliability_health_snapshots.id", ondelete="CASCADE"),
        nullable=True,
    )
    component: Mapped[ComponentType] = mapped_column(
        enum_type(ComponentType, "reliability_component_type_enum"),
        nullable=False,
    )
    status: Mapped[HealthStatus] = mapped_column(
        enum_type(HealthStatus, "reliability_service_health_status_enum"),
        nullable=False,
        default=HealthStatus.HEALTHY,
    )
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    snapshot: Mapped[SystemHealthSnapshot | None] = relationship(
        "SystemHealthSnapshot", back_populates="checks"
    )

    __table_args__ = (
        Index("ix_reliability_checks_comp_status", "component", "status"),
        Index("ix_reliability_checks_observed", "observed_at"),
    )


class ReliabilityIncident(Base):
    """Operational incident recorded by reliability engine or operators."""

    __tablename__ = "reliability_incidents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    component: Mapped[ComponentType] = mapped_column(
        enum_type(ComponentType, "reliability_incident_component_type_enum"),
        nullable=False,
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        enum_type(IncidentSeverity, "reliability_incident_severity_enum"),
        nullable=False,
        default=IncidentSeverity.WARNING,
    )
    state: Mapped[IncidentState] = mapped_column(
        enum_type(IncidentState, "reliability_incident_state_enum"),
        nullable=False,
        default=IncidentState.DETECTED,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    assigned_to_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recovery_verification_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    events: Mapped[list[IncidentEvent]] = relationship(
        "IncidentEvent",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.created_at",
    )
    recovery_runs: Mapped[list[RecoveryRun]] = relationship(
        "RecoveryRun",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="RecoveryRun.created_at.desc()",
    )
    alert_occurrences: Mapped[list[AlertOccurrence]] = relationship(
        "AlertOccurrence",
        back_populates="incident",
    )

    __table_args__ = (
        Index("ix_reliability_incidents_comp_state", "component", "state"),
        Index("ix_reliability_incidents_severity", "severity"),
        Index("ix_reliability_incidents_correlation", "correlation_id"),
        Index("ix_reliability_incidents_created", "created_at"),
    )


class IncidentEvent(Base):
    """Immutable audit timeline event for an incident."""

    __tablename__ = "reliability_incident_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    incident: Mapped[ReliabilityIncident] = relationship(
        "ReliabilityIncident", back_populates="events"
    )

    __table_args__ = (
        Index("ix_reliability_inc_events_incident", "incident_id", "created_at"),
    )


class AlertRule(Base):
    """Provider-neutral alert rule configuration."""

    __tablename__ = "reliability_alert_rules"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        enum_type(IncidentSeverity, "reliability_alert_severity_enum"),
        nullable=False,
        default=IncidentSeverity.WARNING,
    )
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    occurrences: Mapped[list[AlertOccurrence]] = relationship(
        "AlertOccurrence",
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_reliability_alert_rules_type", "rule_type"),
        Index("ix_reliability_alert_rules_comp", "component"),
    )


class AlertOccurrence(Base):
    """Triggered alert instance subject to cooldown and deduplication."""

    __tablename__ = "reliability_alert_occurrences"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reliability_alert_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        enum_type(IncidentSeverity, "reliability_alert_occ_severity_enum"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    incident_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reliability_incidents.id", ondelete="SET NULL"),
        nullable=True,
    )

    rule: Mapped[AlertRule | None] = relationship("AlertRule", back_populates="occurrences")
    incident: Mapped[ReliabilityIncident | None] = relationship(
        "ReliabilityIncident", back_populates="alert_occurrences"
    )

    __table_args__ = (
        Index("ix_reliability_alert_occ_dedup", "dedup_key", "triggered_at"),
        Index("ix_reliability_alert_occ_incident", "incident_id"),
    )


class RecoveryRun(Base):
    """Coordinated recovery execution attempt for an incident."""

    __tablename__ = "reliability_recovery_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[RecoveryActionType] = mapped_column(
        enum_type(RecoveryActionType, "reliability_recovery_action_enum"),
        nullable=False,
    )
    status: Mapped[RecoveryRunStatus] = mapped_column(
        enum_type(RecoveryRunStatus, "reliability_recovery_status_enum"),
        nullable=False,
        default=RecoveryRunStatus.PENDING_APPROVAL,
    )
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    verification_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    incident: Mapped[ReliabilityIncident] = relationship(
        "ReliabilityIncident", back_populates="recovery_runs"
    )
    steps: Mapped[list[RecoveryStep]] = relationship(
        "RecoveryStep",
        back_populates="recovery_run",
        cascade="all, delete-orphan",
        order_by="RecoveryStep.step_order",
    )

    __table_args__ = (
        Index("ix_reliability_recovery_incident", "incident_id"),
        Index("ix_reliability_recovery_status", "status"),
        Index("ix_reliability_recovery_action", "action_type"),
    )


class RecoveryStep(Base):
    """Step execution detail within a recovery run."""

    __tablename__ = "reliability_recovery_steps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recovery_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("reliability_recovery_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[RecoveryStepStatus] = mapped_column(
        enum_type(RecoveryStepStatus, "reliability_recovery_step_status_enum"),
        nullable=False,
        default=RecoveryStepStatus.PENDING,
    )
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    recovery_run: Mapped[RecoveryRun] = relationship(
        "RecoveryRun", back_populates="steps"
    )

    __table_args__ = (
        Index("ix_reliability_recovery_steps_run", "recovery_run_id", "step_order"),
    )


class BackupRecord(Base):
    """Metadata tracking for platform backups and verification."""

    __tablename__ = "reliability_backup_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="MOCK_LOCAL", nullable=False)
    backup_type: Mapped[BackupType] = mapped_column(
        enum_type(BackupType, "reliability_backup_type_enum"),
        nullable=False,
        default=BackupType.SNAPSHOT,
    )
    status: Mapped[BackupStatus] = mapped_column(
        enum_type(BackupStatus, "reliability_backup_status_enum"),
        nullable=False,
        default=BackupStatus.COMPLETED,
    )
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_reliability_backups_resource", "resource_type", "logical_identifier"),
        Index("ix_reliability_backups_status", "status"),
        Index("ix_reliability_backups_started", "started_at"),
    )


class DisasterRecoveryPlan(Base):
    """Versioned Disaster Recovery specifications and target objectives."""

    __tablename__ = "reliability_dr_plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    plan_version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rto_target_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    rpo_target_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    activation_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_priorities_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dependencies_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    verification_checklist_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("plan_version", name="uq_reliability_dr_plan_version"),
        Index("ix_reliability_dr_plans_active", "is_active"),
    )


class ResiliencePolicy(Base):
    """Policy rules governing failure thresholds, recovery retries, and cooldowns."""

    __tablename__ = "reliability_resilience_policies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    component: Mapped[str | None] = mapped_column(String(64), nullable=True)  # None = Global default
    max_automatic_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    recovery_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    escalation_threshold_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    health_failure_threshold: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    incident_deduplication_window_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    alert_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    auto_recovery_permitted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    human_approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    audit_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_reliability_policies_component", "component", "is_active"),
    )

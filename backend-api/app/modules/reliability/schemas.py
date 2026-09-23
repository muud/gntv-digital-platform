"""Pydantic schemas for Sprint 8.6 Reliability, Monitoring, Recovery & DR."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reliability.models import (
    BackupStatus,
    BackupType,
    ComponentType,
    DRReadinessStatus,
    HealthStatus,
    IncidentSeverity,
    IncidentState,
    RecoveryActionType,
    RecoveryRunStatus,
    RecoveryStepStatus,
)


# --- Health Schemas ---
class ServiceHealthCheckResponse(BaseModel):
    id: UUID
    component: ComponentType
    status: HealthStatus
    latency_ms: float
    failure_reason: str | None = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemHealthSnapshotResponse(BaseModel):
    id: UUID
    overall_status: HealthStatus
    health_score: float
    healthy_count: int
    degraded_count: int
    unhealthy_count: int
    unknown_count: int
    details_json: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    correlation_id: str | None = None
    checks: list[ServiceHealthCheckResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class HealthOverviewResponse(BaseModel):
    snapshot: SystemHealthSnapshotResponse | None = None
    recent_checks: list[ServiceHealthCheckResponse] = Field(default_factory=list)
    active_incidents_count: int = 0
    dr_readiness: DRReadinessStatus = DRReadinessStatus.READY


class TriggerHealthCheckRequest(BaseModel):
    component: ComponentType | None = None
    correlation_id: str | None = None


# --- Incident Schemas ---
class IncidentEventResponse(BaseModel):
    id: UUID
    incident_id: UUID
    event_type: str
    from_state: str | None = None
    to_state: str | None = None
    message: str
    actor_user_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReliabilityIncidentResponse(BaseModel):
    id: UUID
    title: str
    description: str
    component: ComponentType
    severity: IncidentSeverity
    state: IncidentState
    failure_reason: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    assigned_to_user_id: int | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by_user_id: int | None = None
    resolved_at: datetime | None = None
    resolved_by_user_id: int | None = None
    resolution_summary: str | None = None
    closed_at: datetime | None = None
    closed_by_user_id: int | None = None
    recovery_verification_summary: str | None = None
    retry_count: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReliabilityIncidentDetailResponse(ReliabilityIncidentResponse):
    events: list[IncidentEventResponse] = Field(default_factory=list)
    recovery_runs: list[RecoveryRunResponse] = Field(default_factory=list)


class IncidentCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    component: ComponentType
    severity: IncidentSeverity = IncidentSeverity.WARNING
    failure_reason: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IncidentAcknowledgeRequest(BaseModel):
    notes: str | None = None


class IncidentResolveRequest(BaseModel):
    resolution_summary: str = Field(min_length=3)


class IncidentCloseRequest(BaseModel):
    recovery_verification_summary: str = Field(min_length=3)


# --- Recovery Schemas ---
class RecoveryStepResponse(BaseModel):
    id: UUID
    recovery_run_id: UUID
    step_order: int
    name: str
    status: RecoveryStepStatus
    output_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RecoveryRunResponse(BaseModel):
    id: UUID
    incident_id: UUID
    action_type: RecoveryActionType
    status: RecoveryRunStatus
    requires_approval: bool
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    parameters_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)
    verification_status: str
    verification_details: str | None = None
    retry_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecoveryRunDetailResponse(RecoveryRunResponse):
    steps: list[RecoveryStepResponse] = Field(default_factory=list)


class StartRecoveryRequest(BaseModel):
    incident_id: UUID
    action_type: RecoveryActionType
    parameters_json: dict[str, Any] = Field(default_factory=dict)


class ApproveRecoveryRequest(BaseModel):
    comments: str | None = None


class VerifyRecoveryRequest(BaseModel):
    verification_details: str | None = None


# --- Alert Schemas ---
class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    rule_type: str = Field(min_length=3, max_length=64)
    severity: IncidentSeverity = IncidentSeverity.WARNING
    component: str = Field(min_length=2, max_length=64)
    threshold_value: float = Field(default=1.0, ge=0.0)
    window_seconds: int = Field(default=300, ge=10)
    cooldown_seconds: int = Field(default=300, ge=10)
    is_enabled: bool = True


class AlertRuleUpdate(BaseModel):
    threshold_value: float | None = None
    window_seconds: int | None = None
    cooldown_seconds: int | None = None
    is_enabled: bool | None = None


class AlertRuleResponse(BaseModel):
    id: UUID
    name: str
    rule_type: str
    severity: IncidentSeverity
    component: str
    threshold_value: float
    window_seconds: int
    cooldown_seconds: int
    is_enabled: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertOccurrenceResponse(BaseModel):
    id: UUID
    rule_id: UUID | None = None
    component: str
    severity: IncidentSeverity
    message: str
    dedup_key: str
    correlation_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    triggered_at: datetime
    incident_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class TriggerAlertRequest(BaseModel):
    rule_type: str
    component: str
    message: str
    severity: IncidentSeverity = IncidentSeverity.WARNING
    correlation_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


# --- Resilience Policy Schemas ---
class ResiliencePolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    component: str | None = None
    max_automatic_retries: int = Field(default=3, ge=0, le=10)
    recovery_cooldown_seconds: int = Field(default=300, ge=10)
    escalation_threshold_minutes: int = Field(default=60, ge=1)
    health_failure_threshold: int = Field(default=3, ge=1)
    incident_deduplication_window_seconds: int = Field(default=600, ge=10)
    alert_cooldown_seconds: int = Field(default=300, ge=10)
    auto_recovery_permitted: bool = True
    human_approval_required: bool = False
    is_active: bool = True
    audit_metadata_json: dict[str, Any] = Field(default_factory=dict)


class ResiliencePolicyUpdate(BaseModel):
    max_automatic_retries: int | None = None
    recovery_cooldown_seconds: int | None = None
    escalation_threshold_minutes: int | None = None
    health_failure_threshold: int | None = None
    incident_deduplication_window_seconds: int | None = None
    alert_cooldown_seconds: int | None = None
    auto_recovery_permitted: bool | None = None
    human_approval_required: bool | None = None
    is_active: bool | None = None


class ResiliencePolicyResponse(BaseModel):
    id: UUID
    name: str
    component: str | None = None
    max_automatic_retries: int
    recovery_cooldown_seconds: int
    escalation_threshold_minutes: int
    health_failure_threshold: int
    incident_deduplication_window_seconds: int
    alert_cooldown_seconds: int
    auto_recovery_permitted: bool
    human_approval_required: bool
    is_active: bool
    audit_metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Backup Schemas ---
class BackupRecordCreate(BaseModel):
    resource_type: str = Field(min_length=2, max_length=64)
    logical_identifier: str = Field(min_length=2, max_length=128)
    provider: str = Field(default="MOCK_LOCAL", max_length=64)
    backup_type: BackupType = BackupType.SNAPSHOT
    retention_days: int = Field(default=30, ge=1)
    checksum: str | None = None
    size_bytes: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class BackupRecordResponse(BaseModel):
    id: UUID
    resource_type: str
    logical_identifier: str
    provider: str
    backup_type: BackupType
    status: BackupStatus
    checksum: str | None = None
    size_bytes: int | None = None
    retention_days: int
    started_at: datetime
    completed_at: datetime | None = None
    verified_at: datetime | None = None
    verification_result: str | None = None
    verification_details: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerifyBackupRequest(BaseModel):
    verification_details: str | None = None


# --- Disaster Recovery Plan Schemas ---
class DisasterRecoveryPlanCreate(BaseModel):
    plan_version: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=3, max_length=128)
    description: str = Field(min_length=3)
    rto_target_minutes: int = Field(default=30, ge=1)
    rpo_target_minutes: int = Field(default=15, ge=1)
    activation_criteria: str = Field(min_length=3)
    recovery_priorities_json: list[str] = Field(default_factory=list)
    dependencies_json: dict[str, Any] = Field(default_factory=dict)
    verification_checklist_json: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    is_active: bool = False


class DisasterRecoveryPlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    rto_target_minutes: int | None = None
    rpo_target_minutes: int | None = None
    activation_criteria: str | None = None
    recovery_priorities_json: list[str] | None = None
    dependencies_json: dict[str, Any] | None = None
    verification_checklist_json: list[str] | None = None
    is_active: bool | None = None


class DisasterRecoveryPlanResponse(BaseModel):
    id: UUID
    plan_version: str
    name: str
    description: str
    rto_target_minutes: int
    rpo_target_minutes: int
    activation_criteria: str
    recovery_priorities_json: list[str] = Field(default_factory=list)
    dependencies_json: dict[str, Any] = Field(default_factory=dict)
    verification_checklist_json: list[str] = Field(default_factory=list)
    requires_approval: bool
    is_active: bool
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DRReadinessResponse(BaseModel):
    overall_status: DRReadinessStatus
    active_plan: DisasterRecoveryPlanResponse | None = None
    rto_target_minutes: int = 30
    rpo_target_minutes: int = 15
    critical_services_healthy: bool
    backup_freshness_minutes: float | None = None
    recovery_success_rate: float = 100.0
    checklist_status: dict[str, bool] = Field(default_factory=dict)
    evaluation_notes: list[str] = Field(default_factory=list)


# --- Reliability Metrics Schemas ---
class ReliabilityMetricsResponse(BaseModel):
    healthy_component_count: int
    degraded_component_count: int
    unhealthy_component_count: int
    unresolved_incident_count: int
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    mean_recovery_duration_seconds: float = 0.0
    successful_recovery_runs: int = 0
    failed_recovery_runs: int = 0
    dlq_related_incidents: int = 0
    dr_readiness: DRReadinessStatus
    recent_health_trend: list[dict[str, Any]] = Field(default_factory=list)

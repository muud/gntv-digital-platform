"""Sprint 8.4 AI Agent Control Plane."""

from app.modules.events.service import register_approved_event_type

for _event_name in (
    "agent.created",
    "agent.updated",
    "agent.activated",
    "agent.paused",
    "agent.archived",
    "agent.run.queued",
    "agent.run.started",
    "agent.run.waiting_for_human",
    "agent.run.succeeded",
    "agent.run.failed",
    "agent.run.cancelled",
    "agent.run.blocked",
    "agent.tool.requested",
    "agent.tool.approved",
    "agent.tool.denied",
    "agent.tool.succeeded",
    "agent.tool.failed",
    "agent.approval.requested",
    "agent.approval.approved",
    "agent.approval.rejected",
):
    register_approved_event_type(_event_name)

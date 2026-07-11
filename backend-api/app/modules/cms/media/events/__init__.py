"""Stable event payload emitted by future asynchronous media integrations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class MediaEvent:
    event_type: str
    asset_id: UUID
    actor_id: int
    occurred_at: datetime


__all__ = ["MediaEvent"]

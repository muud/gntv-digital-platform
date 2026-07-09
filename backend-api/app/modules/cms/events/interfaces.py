"""Event contracts for CMS asynchronous boundaries."""

from typing import Protocol

from app.modules.cms.events.payloads import CMSEvent


class CMSEventInterface(Protocol):
    """Boundary for publishing CMS events."""

    def publish(self, event: CMSEvent) -> None: ...

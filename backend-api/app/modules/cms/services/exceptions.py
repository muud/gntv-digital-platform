"""CMS service exceptions."""

from uuid import UUID


class CMSServiceError(Exception):
    """Base exception for CMS service failures."""


class CMSInvalidTransitionError(CMSServiceError):
    """Raised when a workflow transition is not allowed."""

    def __init__(self, transition: str) -> None:
        super().__init__(f"Invalid CMS workflow transition: {transition}")
        self.transition = transition


class CMSContentNotFoundError(CMSServiceError):
    """Raised when a requested CMS content record does not exist."""

    def __init__(self, content_id: UUID) -> None:
        super().__init__(f"CMS content not found: {content_id}")
        self.content_id = content_id


class CMSValidationError(CMSServiceError):
    """Raised when CMS service validation fails."""

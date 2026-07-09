"""Permission contracts for CMS access control."""

from collections.abc import Iterable
from typing import Protocol

from app.modules.cms.permissions.matrix import CMSScope


class CMSPermissionInterface(Protocol):
    """Boundary for CMS permission checks."""

    def has_scope(self, *, roles: Iterable[str], required_scope: CMSScope) -> bool: ...

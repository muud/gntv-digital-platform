"""CMS permission helpers."""

from app.modules.cms.permissions.interfaces import CMSPermissionInterface
from app.modules.cms.permissions.matrix import (
    ROLE_SCOPES,
    CMSPermissionChecker,
    CMSRole,
    CMSScope,
    has_scope,
    scopes_for_roles,
)

__all__ = [
    "ROLE_SCOPES",
    "CMSPermissionChecker",
    "CMSPermissionInterface",
    "CMSRole",
    "CMSScope",
    "has_scope",
    "scopes_for_roles",
]

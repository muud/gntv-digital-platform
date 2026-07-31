"""Streaming RBAC exports."""

from app.modules.streaming.permissions.dependencies import require_streaming_scope
from app.modules.streaming.permissions.matrix import (
    ALL_SCOPES,
    ROLE_SCOPES,
    StreamingScope,
    has_scope,
    scopes_for_roles,
)

__all__ = [
    "ALL_SCOPES",
    "ROLE_SCOPES",
    "StreamingScope",
    "has_scope",
    "require_streaming_scope",
    "scopes_for_roles",
]

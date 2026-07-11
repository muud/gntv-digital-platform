# utils/auth_dependencies.py
"""Authentication and authorization dependencies for FastAPI.

Provides:
- get_current_user(): validates JWT, loads User, Session, Device and checks revocation.
- get_current_active_user(): ensures the user is active and email‑verified.
- require_role(role_name): dependency that ensures the user has a given role.
- require_permission(permission_name): dependency that ensures the user possesses a permission.

All checks raise appropriate HTTPException status codes.
"""

from app.dependencies.auth import get_current_active_user, get_current_user, require_permission, require_role

__all__ = ["get_current_active_user", "get_current_user", "require_permission", "require_role"]

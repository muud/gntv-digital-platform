"""Media RBAC dependency."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.cms.permissions import CMSScope, has_scope


def require_media_scope(scope: CMSScope) -> Callable[..., User]:
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_scope(roles=current_user.role_names, required_scope=scope):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "media_forbidden"})
        return current_user
    return dependency


__all__ = ["require_media_scope"]

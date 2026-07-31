"""FastAPI RBAC dependencies for Module 5."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.streaming.permissions.matrix import StreamingScope, has_scope


def require_streaming_scope(required_scope: StreamingScope) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_scope(roles=user.role_names, required_scope=required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "streaming_forbidden", "required_scope": required_scope},
            )
        return user

    return dependency

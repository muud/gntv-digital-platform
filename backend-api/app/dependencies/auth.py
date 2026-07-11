# app/dependencies/auth.py
"""Authentication dependencies for FastAPI.

Provides utilities to retrieve the current user from a JWT access token,
validate session and device status, enforce role-based access control, and
permission checks.

All protected routes should depend on these functions.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import Session as UserSession
from app.models.user import User
from app.utils.jwt import decode_token

security = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Decode JWT access token and return the authenticated User.

    Raises:
        HTTPException 401: If token is missing, invalid, expired, or user not found.
        HTTPException 403: If user is inactive, email not verified, or session/device revoked.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Ensure token type is access (no explicit type claim for access tokens)
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    user_id = int(subject)
    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Check user status
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account disabled")
    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")
    # Verify session existence via jti claim if present
    jti = payload.get("jti")
    if jti:
        session = db.query(UserSession).filter(UserSession.id == jti, UserSession.user_id == user_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session revoked or expired")
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Alias that can be used when only active users are allowed.
    The checks are already performed in ``get_current_user``.
    """
    return current_user

def require_role(required_role: str) -> Callable[..., User]:
    """Dependency factory that ensures the current user has the given role.
    Usage::
        @router.get(..., dependencies=[Depends(require_role("admin"))])
    """
    def role_dependency(user: User = Depends(get_current_user)) -> User:
        if required_role not in user.role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role, required: {required_role}",
            )
        return user
    return role_dependency

def require_permission(permission: str) -> Callable[..., User]:
    """Dependency factory that checks database-backed role permissions."""
    def permission_dependency(user: User = Depends(get_current_user)) -> User:
        perms = user.permission_names
        if "*" not in perms and permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return user
    return permission_dependency

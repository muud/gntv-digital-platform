# app/api/auth.py
"""Authentication API routes.

Implements registration, email verification, login, logout, token refresh,
password reset, device management, and profile endpoints.
All business logic is delegated to AuthService.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    DeviceResponse,
    VerifyEmailResponse,
)
from app.services.auth_service import AuthService
from app.core.database import get_db

# Authentication dependencies
from app.dependencies.auth import (
    get_current_active_user,
    get_current_user,
)
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)

@router.post("/register", response_model=dict, summary="User registration")
def register(
    req: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        return service.register(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/verify-email", response_model=VerifyEmailResponse, summary="Verify email token")
def verify_email(
    token: str,
    service: AuthService = Depends(get_auth_service),
) -> VerifyEmailResponse:
    try:
        return service.verify_email(token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/login", response_model=TokenResponse, summary="User login")
def login(
    req: LoginRequest,
    service: AuthService = Depends(get_auth_service),
    ip_address: str = "127.0.0.1",
    user_agent: str = "unknown",
    location: dict[str, str] | None = None,
) -> TokenResponse:
    try:
        return service.login(req, ip_address, user_agent, location)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout current device")
def logout(
    refresh_token: str,
    service: AuthService = Depends(get_auth_service),
) -> None:
    try:
        service.logout(refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return

@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, summary="Logout all devices")
def logout_all(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    # current_user is a User model instance
    service.logout_all(current_user.id)
    return

@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
def refresh(
    req: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        return service.refresh(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/password-reset-request", status_code=status.HTTP_202_ACCEPTED, summary="Request password reset")
def password_reset_request(
    req: PasswordResetRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    service.password_reset_request(req)
    return {"detail": "If the email exists, a reset link has been sent."}

@router.post("/password-reset-confirm", status_code=status.HTTP_200_OK, summary="Confirm password reset")
def password_reset_confirm(
    req: PasswordResetConfirm,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    try:
        service.password_reset_confirm(req)
        return {"detail": "Password has been reset successfully."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/me", response_model=dict, summary="Get current user profile")
def get_me(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "is_verified": current_user.email_verified,
    }

@router.patch("/me", response_model=dict, summary="Update current user profile")
def update_me(
    name: str | None = None,
    current_user: User = Depends(get_current_active_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    if name:
        current_user.name = name
        service.repo.db.add(current_user)
        service.repo.db.flush()
    return {"detail": "Profile updated"}

@router.get("/devices", response_model=list[DeviceResponse], summary="List user devices")
def list_devices(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> list[DeviceResponse]:
    return service.list_devices(current_user.id)

@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a device")
def revoke_device(
    device_id: int,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    try:
        service.revoke_device(current_user.id, device_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return

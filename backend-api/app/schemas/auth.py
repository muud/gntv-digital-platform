# schemas/auth.py
"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Plain password (min 8 chars)")
    name: Optional[str] = Field(None, description="Full name of the user")

    @field_validator("password")
    @classmethod
    def no_common_password(cls, v: str) -> str:
        if v.lower() in {"password", "12345678", "qwerty"}:
            raise ValueError("Password is too common")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_name: str = Field(..., description="User‑provided device name")
    platform: Optional[str] = None
    browser: Optional[str] = None
    app_version: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def no_common_password(cls, v: str) -> str:
        if v.lower() in {"password", "12345678", "qwerty"}:
            raise ValueError("Password is too common")
        return v


class DeviceResponse(BaseModel):
    id: int
    device_name: str
    platform: Optional[str]
    browser: Optional[str]
    ip_address: Optional[str]
    created_at: Optional[datetime]
    is_deleted: bool = False

    model_config = ConfigDict(from_attributes=True)


class VerifyEmailResponse(BaseModel):
    detail: str = "Email verified successfully"

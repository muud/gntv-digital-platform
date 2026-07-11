"""Compatibility exports for authentication models."""

from app.models.auth_extra import (
    EmailVerification,
    FailedLoginAttempt,
    PasswordReset,
    PasswordResetToken,
    RefreshToken,
)

__all__ = [
    "EmailVerification",
    "FailedLoginAttempt",
    "PasswordReset",
    "PasswordResetToken",
    "RefreshToken",
]

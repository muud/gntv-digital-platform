# utils/jwt.py
"""JWT utility functions for access and refresh tokens.

Configuration is pulled from environment variables:
- JWT_SECRET_KEY
- JWT_ALGORITHM (default HS256)
- JWT_ACCESS_TOKEN_EXPIRE_MINUTES (default 15)
- JWT_REFRESH_TOKEN_EXPIRE_DAYS (default 30)
- JWT_ISSUER
- JWT_AUDIENCE
"""
import os
import datetime
from typing import Any, Dict, cast
from jose import jwt
from app.core.config import settings

# Load configuration from environment with defaults where appropriate
SECRET_KEY = os.getenv("JWT_SECRET_KEY", settings.JWT_SECRET_KEY)
ALGORITHM = os.getenv("JWT_ALGORITHM", settings.JWT_ALGORITHM)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", str(settings.ACCESS_TOKEN_EXPIRE_MINUTES)))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", str(settings.REFRESH_TOKEN_EXPIRE_DAYS)))
ISSUER = os.getenv("JWT_ISSUER", "GNTV DIGITAL, ALL EVERYWHERE")
AUDIENCE = os.getenv("JWT_AUDIENCE", "GNTV DIGITAL, ALL EVERYWHERE_CLIENT")

def _base_claims(subject: str) -> Dict[str, Any]:
    """Common JWT claims shared by access and refresh tokens."""
    now = datetime.datetime.utcnow()
    return {
        "sub": subject,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "nbf": now,
    }


def create_access_token(subject: str, additional_claims: Dict[str, Any] | None = None) -> str:
    """Create a signed access token.

    Args:
        subject: The subject (e.g., user id) for the token.
        additional_claims: Optional extra claims to embed.
    Returns:
        JWT string.
    """
    claims = _base_claims(subject)
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    claims.update({"exp": expire})
    if additional_claims:
        claims.update(additional_claims)
    return cast(str, jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM))


def create_refresh_token(subject: str, additional_claims: Dict[str, Any] | None = None) -> str:
    """Create a signed refresh token.

    Args:
        subject: The subject (e.g., user id).
        additional_claims: Optional extra claims.
    Returns:
        JWT string.
    """
    claims = _base_claims(subject)
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    claims.update({"exp": expire, "type": "refresh"})
    if additional_claims:
        claims.update(additional_claims)
    return cast(str, jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM))


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT token.

    Raises jose.exceptions.JWTError on failure.
    """
    return cast(Dict[str, Any], jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER))

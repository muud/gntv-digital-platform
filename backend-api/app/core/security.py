from datetime import datetime, timedelta
from typing import Optional, Any, cast

# Argon2 stubs not available; ignore specific import-not-found error
from argon2 import PasswordHasher  # type: ignore[import-not-found]
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import settings

ph = PasswordHasher()

class TokenData(BaseModel):
    sub: Optional[int] = None
    exp: Optional[int] = None


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return cast(str, ph.hash(password))


def verify_password(hashed_password: str, plain_password: str) -> bool:
    """Verify a plaintext password against the stored Argon2id hash."""
    try:
        return cast(bool, ph.verify(hashed_password, plain_password))
    except Exception:
        return False


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    * ``data`` – custom claims to embed.
    * ``expires_delta`` – optional custom expiry; defaults to ``settings.ACCESS_TOKEN_EXPIRE_MINUTES``.
    """
    to_encode: dict[str, Any] = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = cast(str, jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256"))
    return encoded_jwt


def create_refresh_token(user_id: int) -> str:
    """Create a JWT refresh token for ``user_id``."""
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": str(user_id), "exp": expire}
    encoded_jwt = cast(str, jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256"))
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """Decode a JWT token and return :class:`TokenData`.

    Returns an empty ``TokenData`` instance on failure.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return TokenData(**payload)
    except JWTError:
        return TokenData()

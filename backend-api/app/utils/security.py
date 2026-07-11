# utils/security.py
"""Security utilities: password hashing with Argon2id and verification."""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id hasher configuration – defaults are secure
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plain password using Argon2id.

    Args:
        password: Plain-text password.
    Returns:
        The hashed password string.
    """
    return _hasher.hash(password)


def verify_password(hash: str, password: str) -> bool:
    """Verify a password against its Argon2id hash.

    Returns True if the password matches, False otherwise.
    """
    try:
        return _hasher.verify(hash, password)
    except VerifyMismatchError:
        return False

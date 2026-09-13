"""Security utilities for HMAC verification, AES-GCM secret encryption, fingerprinting, and payload sanitization."""

from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import hmac
import os
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SENSITIVE_FIELD_NAMES = {
    "password",
    "secret",
    "client_secret",
    "webhook_secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "private_key",
    "credit_card",
    "card_number",
    "cvv",
    "pan",
    "bank_account",
    "account_number",
    "routing_number",
    "ssn",
    "encryption_key",
}


class SignatureVerifier(ABC):
    """Provider-neutral signature verification boundary."""

    @abstractmethod
    def verify(self, secret: str, payload_bytes: bytes, signature_header: str) -> bool:
        """Return whether a signature is valid for the exact raw request body."""


class HMACSHA256Verifier(SignatureVerifier):
    """Constant-time HMAC-SHA256 verifier used by Sprint 8.2 sources."""

    def verify(self, secret: str, payload_bytes: bytes, signature_header: str) -> bool:
        return verify_hmac_signature(secret, payload_bytes, signature_header)


class SecretStore(ABC):
    """Provider-neutral storage boundary for reusable webhook secrets."""

    @abstractmethod
    def seal(self, secret: str) -> tuple[str, str]:
        """Seal plaintext and return an opaque ciphertext/reference pair."""

    @abstractmethod
    def reveal(self, ciphertext: str, reference: str) -> str:
        """Reveal a previously sealed secret for signing or verification only."""


class EncryptedSecretStore(SecretStore):
    """AES-256-GCM secret store backed by the configured application key."""

    def seal(self, secret: str) -> tuple[str, str]:
        return encrypt_secret(secret)

    def reveal(self, ciphertext: str, reference: str) -> str:
        return decrypt_secret(ciphertext, reference)


def generate_secret(num_bytes: int = 32) -> str:
    """Generate a high-entropy secret string."""
    return secrets.token_hex(num_bytes)


def encrypt_secret(secret: str, master_key: str | None = None) -> tuple[str, str]:
    """
    Encrypt a shared secret using AES-256-GCM.
    Returns (hex_ciphertext_and_tag, hex_nonce).
    """
    if master_key is None:
        from app.core.config import settings

        master_key = settings.JWT_SECRET_KEY

    key = hashlib.sha256(master_key.encode("utf-8")).digest()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, secret.encode("utf-8"), None)
    return ct.hex(), nonce.hex()


def decrypt_secret(
    secret_hash: str, secret_salt: str, master_key: str | None = None
) -> str:
    """Decrypt an AES-256-GCM encrypted shared secret."""
    if master_key is None:
        from app.core.config import settings

        master_key = settings.JWT_SECRET_KEY

    key = hashlib.sha256(master_key.encode("utf-8")).digest()
    aesgcm = AESGCM(key)
    nonce = bytes.fromhex(secret_salt)
    ct = bytes.fromhex(secret_hash)
    plain = aesgcm.decrypt(nonce, ct, None)
    return plain.decode("utf-8")


def compute_hmac_sha256(
    secret: str, payload_bytes: bytes, include_prefix: bool = True
) -> str:
    """Compute HMAC-SHA256 digest over bytes, optionally prefixing with 'sha256='."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    if include_prefix:
        return f"sha256={mac}"
    return mac


def verify_hmac_signature(
    secret: str, payload_bytes: bytes, signature_header: str
) -> bool:
    """
    Verify incoming HMAC-SHA256 signature using constant-time comparison.
    Supports either 'sha256=<hex>' or '<hex>' header formats.
    """
    if not signature_header or not secret:
        return False

    raw_sig = signature_header.strip()
    if raw_sig.lower().startswith("sha256="):
        raw_sig = raw_sig[7:].strip()

    expected_hex = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(raw_sig.lower(), expected_hex.lower())


def calculate_delivery_fingerprint(
    source_id: str, timestamp_str: str, body_bytes: bytes
) -> str:
    """Calculate deterministic SHA256 fingerprint of delivery for replay prevention."""
    hasher = hashlib.sha256()
    hasher.update(str(source_id).encode("utf-8"))
    hasher.update(b":")
    hasher.update(timestamp_str.strip().encode("utf-8"))
    hasher.update(b":")
    hasher.update(body_bytes)
    return hasher.hexdigest()


def sanitize_payload(obj: Any) -> Any:
    """
    Recursively sanitize dictionaries and lists to redact sensitive credentials,
    secrets, tokens, or personal payment numbers before persistence or logging.
    """
    if isinstance(obj, dict):
        sanitized = {}
        for key, value in obj.items():
            key_str = str(key).lower()
            if any(sensitive in key_str for sensitive in SENSITIVE_FIELD_NAMES):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(sanitize_payload(item) for item in obj)
    return obj

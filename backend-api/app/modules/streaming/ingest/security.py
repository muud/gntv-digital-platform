"""Stream-key parsing and validation without retaining plaintext credentials."""

from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.modules.streaming.ingest.errors import IngestError
from app.modules.streaming.models import StreamKey, StreamKeyStatus, StreamProtocol


class StreamKeyLookup(Protocol):
    def stream_key_by_prefix(self, key_prefix: str) -> StreamKey | None: ...


class ValidatedStreamKey:
    def __init__(self, record: StreamKey) -> None:
        self.record = record


class StreamKeyValidator:
    """Validate an Argon2id-backed stream key and its admission policy."""

    def __init__(self, repository: StreamKeyLookup, hasher: PasswordHasher | None = None) -> None:
        self.repository = repository
        self.hasher = hasher or PasswordHasher()

    @staticmethod
    def split_key(stream_key: str) -> tuple[str, str]:
        prefix, separator, secret = stream_key.partition(".")
        if separator != "." or not prefix or not secret or len(prefix) > 32:
            raise IngestError("invalid_stream_key", "Stream key is invalid", status_code=401)
        return prefix, secret

    def validate(
        self,
        stream_key: str,
        *,
        protocol: StreamProtocol,
        source_ip: IPv4Address | IPv6Address,
        now: datetime | None = None,
    ) -> ValidatedStreamKey:
        prefix, secret = self.split_key(stream_key)
        record = self.repository.stream_key_by_prefix(prefix)
        if record is None or record.status != StreamKeyStatus.ACTIVE:
            raise IngestError("invalid_stream_key", "Stream key is invalid", status_code=401)

        current_time = now or datetime.now(UTC)
        expiry = record.expires_at
        if expiry is not None:
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= current_time:
                raise IngestError("expired_stream_key", "Stream key has expired", status_code=401)

        if protocol.value not in record.allowed_protocols:
            raise IngestError("protocol_not_allowed", "Protocol is not allowed for this key", status_code=403)

        if record.allowed_cidrs and not any(
            ip_address(source_ip) in ip_network(cidr, strict=False) for cidr in record.allowed_cidrs
        ):
            raise IngestError("source_not_allowed", "Encoder source is not allowed", status_code=403)

        valid_secret: bool
        try:
            valid_secret = self.hasher.verify(record.secret_hash, secret)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            valid_secret = False
        if not valid_secret:
            raise IngestError("invalid_stream_key", "Stream key is invalid", status_code=401)
        return ValidatedStreamKey(record)


__all__ = ["StreamKeyValidator", "ValidatedStreamKey"]

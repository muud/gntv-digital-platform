"""Redis-backed ephemeral ingest registration, lease, and health coordination."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.core.config import settings


class RedisCommands(Protocol):
    async def get(self, name: str) -> Any: ...
    async def set(self, name: str, value: str, **kwargs: Any) -> Any: ...
    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...
    async def ping(self) -> Any: ...


class IngestCoordinationInterface(Protocol):
    async def register_encoder(self, registration_id: UUID, payload: dict[str, Any], ttl: int) -> bool: ...
    async def encoder(self, registration_id: UUID) -> dict[str, Any] | None: ...
    async def acquire_stream_lease(self, channel_id: UUID, stream_id: UUID, ttl: int) -> bool: ...
    async def renew_stream_lease(self, channel_id: UUID, stream_id: UUID, ttl: int) -> bool: ...
    async def release_stream_lease(self, channel_id: UUID, stream_id: UUID) -> bool: ...
    async def store_health(self, stream_id: UUID, health: dict[str, Any], ttl: int) -> None: ...
    async def cached_key_validation(self, fingerprint: str) -> dict[str, Any] | None: ...
    async def cache_key_validation(self, fingerprint: str, payload: dict[str, Any], ttl: int) -> None: ...
    async def ping(self) -> bool: ...


class RedisIngestCoordination:
    _compare_expire = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
      return redis.call('EXPIRE', KEYS[1], ARGV[2])
    end
    return 0
    """
    _compare_delete = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
      return redis.call('DEL', KEYS[1])
    end
    return 0
    """

    def __init__(self, redis: RedisCommands) -> None:
        self.redis = redis

    @staticmethod
    def _encoder_key(registration_id: UUID) -> str:
        return f"gntv:ingest:encoder:{registration_id}"

    @staticmethod
    def _lease_key(channel_id: UUID) -> str:
        return f"gntv:ingest:lease:{channel_id}"

    async def register_encoder(self, registration_id: UUID, payload: dict[str, Any], ttl: int) -> bool:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return bool(await self.redis.set(self._encoder_key(registration_id), encoded, ex=ttl, nx=True))

    async def encoder(self, registration_id: UUID) -> dict[str, Any] | None:
        raw = await self.redis.get(self._encoder_key(registration_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else None

    async def acquire_stream_lease(self, channel_id: UUID, stream_id: UUID, ttl: int) -> bool:
        return bool(await self.redis.set(self._lease_key(channel_id), str(stream_id), ex=ttl, nx=True))

    async def renew_stream_lease(self, channel_id: UUID, stream_id: UUID, ttl: int) -> bool:
        result = await self.redis.eval(
            self._compare_expire,
            1,
            self._lease_key(channel_id),
            str(stream_id),
            ttl,
        )
        return bool(result)

    async def release_stream_lease(self, channel_id: UUID, stream_id: UUID) -> bool:
        result = await self.redis.eval(
            self._compare_delete,
            1,
            self._lease_key(channel_id),
            str(stream_id),
        )
        return bool(result)

    async def store_health(self, stream_id: UUID, health: dict[str, Any], ttl: int) -> None:
        safe_health = {
            "observed_at": datetime.now(UTC).isoformat(),
            "metrics": health,
        }
        await self.redis.set(
            f"gntv:ingest:health:{stream_id}",
            json.dumps(safe_health, separators=(",", ":"), sort_keys=True),
            ex=ttl,
        )

    async def cached_key_validation(self, fingerprint: str) -> dict[str, Any] | None:
        raw = await self.redis.get(f"gntv:ingest:key-validation:{fingerprint}")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else None

    async def cache_key_validation(
        self, fingerprint: str, payload: dict[str, Any], ttl: int
    ) -> None:
        await self.redis.set(
            f"gntv:ingest:key-validation:{fingerprint}",
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            ex=ttl,
        )

    async def ping(self) -> bool:
        response = await self.redis.ping()
        return response in (True, b"PONG", "PONG")

    @staticmethod
    def source_ip_hash(source_ip: str) -> str:
        return hmac.new(
            settings.INGEST_GATEWAY_TOKEN.encode("utf-8"),
            source_ip.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def key_fingerprint(stream_key: str, protocol: str, source_ip: str) -> str:
        material = f"{stream_key}\0{protocol}\0{source_ip}".encode("utf-8")
        return hmac.new(
            settings.INGEST_GATEWAY_TOKEN.encode("utf-8"),
            material,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def expires_at(ttl: int) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=ttl)


__all__ = ["IngestCoordinationInterface", "RedisIngestCoordination"]

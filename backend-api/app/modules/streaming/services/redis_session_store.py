"""Redis session storage and ZSET concurrency tracking service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from time import time
from uuid import UUID



@dataclass
class RedisSessionMeta:
    session_id: UUID
    user_id: int
    device_id: str
    content_id: UUID
    status: str
    started_at: datetime
    last_seen_at: datetime


class RedisSessionStore:
    """Manage transient stream concurrency slots using Redis ZSETs with an in-memory fallback."""

    def __init__(self, redis_client: Any = None) -> None:
        self._redis = redis_client
        # In-memory fallback structures: user_id -> dict[session_id_str, score_float]
        self._mem_zsets: dict[int, dict[str, float]] = {}
        # session_id_str -> meta_dict
        self._mem_meta: dict[str, dict[str, Any]] = {}

    def _get_zset_key(self, user_id: int) -> str:
        return f"user:sessions:{user_id}"

    def _get_meta_key(self, session_id: UUID) -> str:
        return f"session:meta:{session_id}"

    def acquire_slot(
        self, user_id: int, session_id: UUID, limit: int = 3, now_epoch: float | None = None
    ) -> UUID | None:
        """Add session to user's active ZSET. If count > limit, return the evicted oldest session ID."""

        timestamp = time() if now_epoch is None else now_epoch
        session_str = str(session_id)
        evicted_id: UUID | None = None

        if self._redis is not None:
            try:
                key = self._get_zset_key(user_id)
                self._redis.zadd(key, {session_str: timestamp})
                count = self._redis.zcard(key)
                if count > limit:
                    # Get oldest session (lowest score)
                    oldest = self._redis.zrange(key, 0, count - limit - 1)
                    for item in oldest:
                        item_str = item.decode() if isinstance(item, bytes) else str(item)
                        if item_str != session_str:
                            self._redis.zrem(key, item_str)
                            evicted_id = UUID(item_str)
                            break
                return evicted_id
            except Exception:
                pass  # Fallback to in-memory store

        # In-memory fallback
        if user_id not in self._mem_zsets:
            self._mem_zsets[user_id] = {}
        user_dict = self._mem_zsets[user_id]
        user_dict[session_str] = timestamp

        if len(user_dict) > limit:
            sorted_items = sorted(user_dict.items(), key=lambda x: x[1])
            for oldest_str, _ in sorted_items:
                if oldest_str != session_str:
                    del user_dict[oldest_str]
                    evicted_id = UUID(oldest_str)
                    break

        return evicted_id

    def record_heartbeat(self, user_id: int, session_id: UUID, now_epoch: float | None = None) -> None:
        """Refresh active session score in user ZSET."""

        timestamp = time() if now_epoch is None else now_epoch
        session_str = str(session_id)

        if self._redis is not None:
            try:
                key = self._get_zset_key(user_id)
                self._redis.zadd(key, {session_str: timestamp}, xx=True)
                return
            except Exception:
                pass

        if user_id in self._mem_zsets and session_str in self._mem_zsets[user_id]:
            self._mem_zsets[user_id][session_str] = timestamp

    def release_slot(self, user_id: int, session_id: UUID) -> None:
        """Remove session from user ZSET on explicit stop/revocation."""

        session_str = str(session_id)

        if self._redis is not None:
            try:
                key = self._get_zset_key(user_id)
                self._redis.zrem(key, session_str)
                meta_key = self._get_meta_key(session_id)
                self._redis.delete(meta_key)
                return
            except Exception:
                pass

        if user_id in self._mem_zsets and session_str in self._mem_zsets[user_id]:
            del self._mem_zsets[user_id][session_str]
        if session_str in self._mem_meta:
            del self._mem_meta[session_str]

    def sweep_idle_sessions(
        self, user_id: int, idle_cutoff_seconds: float = 90.0, now_epoch: float | None = None
    ) -> list[UUID]:
        """Return list of session IDs whose heartbeats are older than idle_cutoff_seconds."""

        timestamp = time() if now_epoch is None else now_epoch
        cutoff = timestamp - idle_cutoff_seconds
        expired: list[UUID] = []

        if self._redis is not None:
            try:
                key = self._get_zset_key(user_id)
                items = self._redis.zrangebyscore(key, 0, cutoff)
                for item in items:
                    item_str = item.decode() if isinstance(item, bytes) else str(item)
                    expired.append(UUID(item_str))
                    self._redis.zrem(key, item_str)
                return expired
            except Exception:
                pass

        if user_id in self._mem_zsets:
            user_dict = self._mem_zsets[user_id]
            to_remove = [s_id for s_id, score in user_dict.items() if score < cutoff]
            for s_id in to_remove:
                expired.append(UUID(s_id))
                del user_dict[s_id]

        return expired


__all__ = ["RedisSessionMeta", "RedisSessionStore"]

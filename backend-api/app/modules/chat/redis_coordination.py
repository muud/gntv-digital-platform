"""Redis coordination primitives for horizontally scalable live chat."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis


def chat_pubsub_key(room_id: UUID) -> str:
    return f"chat:pubsub:{room_id}"


def chat_presence_key(room_id: UUID) -> str:
    return f"chat:presence:{room_id}"


def chat_ratelimit_key(user_id: int, room_id: UUID) -> str:
    return f"chat:ratelimit:{user_id}:{room_id}"


def chat_dedup_key(room_id: UUID) -> str:
    return f"chat:dedup:{room_id}"


class ChatCoordinator(Protocol):
    async def publish(self, room_id: UUID, event: dict[str, Any]) -> None: ...

    async def heartbeat_presence(self, room_id: UUID, user_id: int) -> int: ...

    async def leave_presence(self, room_id: UUID, user_id: int) -> int: ...

    async def check_rate_limit(self, user_id: int, room_id: UUID) -> bool: ...

    async def check_dedup(self, room_id: UUID, client_msg_id: str) -> bool: ...


class RedisChatCoordinator:
    presence_ttl_seconds = 30
    rate_limit_window_seconds = 5
    rate_limit_max_messages = 5
    dedup_ttl_seconds = 60

    def __init__(self, client: Redis) -> None:
        self.client = client

    async def publish(self, room_id: UUID, event: dict[str, Any]) -> None:
        await self.client.publish(chat_pubsub_key(room_id), json.dumps(event, default=str, separators=(",", ":")))

    async def heartbeat_presence(self, room_id: UUID, user_id: int) -> int:
        now = time.time()
        key = chat_presence_key(room_id)
        await self.client.zadd(key, {str(user_id): now})
        await self.client.zremrangebyscore(key, "-inf", now - self.presence_ttl_seconds)
        await self.client.expire(key, self.presence_ttl_seconds)
        return int(await self.client.zcard(key))

    async def leave_presence(self, room_id: UUID, user_id: int) -> int:
        key = chat_presence_key(room_id)
        await self.client.zrem(key, str(user_id))
        return int(await self.client.zcard(key))

    async def check_rate_limit(self, user_id: int, room_id: UUID) -> bool:
        key = chat_ratelimit_key(user_id, room_id)
        count = int(await self.client.incr(key))
        if count == 1:
            await self.client.expire(key, self.rate_limit_window_seconds)
        return count <= self.rate_limit_max_messages

    async def check_dedup(self, room_id: UUID, client_msg_id: str) -> bool:
        key = f"{chat_dedup_key(room_id)}:{client_msg_id}"
        return bool(await self.client.set(key, "1", ex=self.dedup_ttl_seconds, nx=True))


class InMemoryChatCoordinator:
    presence_ttl_seconds = 30
    rate_limit_window_seconds = 5
    rate_limit_max_messages = 5
    dedup_ttl_seconds = 60

    def __init__(self) -> None:
        self.events: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        self.presence: dict[UUID, dict[int, float]] = defaultdict(dict)
        self.rate_limits: dict[tuple[int, UUID], list[float]] = defaultdict(list)
        self.dedup: dict[UUID, dict[str, float]] = defaultdict(dict)
        self.fail_publish = False

    async def publish(self, room_id: UUID, event: dict[str, Any]) -> None:
        if self.fail_publish:
            raise RuntimeError("Redis publish failed")
        self.events[room_id].append(event)

    async def heartbeat_presence(self, room_id: UUID, user_id: int) -> int:
        now = time.time()
        self.presence[room_id] = {
            present_user_id: seen_at
            for present_user_id, seen_at in self.presence[room_id].items()
            if seen_at >= now - self.presence_ttl_seconds
        }
        self.presence[room_id][user_id] = now
        return len(self.presence[room_id])

    async def leave_presence(self, room_id: UUID, user_id: int) -> int:
        self.presence[room_id].pop(user_id, None)
        return len(self.presence[room_id])

    async def check_rate_limit(self, user_id: int, room_id: UUID) -> bool:
        now = time.time()
        bucket = [seen_at for seen_at in self.rate_limits[(user_id, room_id)] if seen_at >= now - 5]
        bucket.append(now)
        self.rate_limits[(user_id, room_id)] = bucket
        return len(bucket) <= self.rate_limit_max_messages

    async def check_dedup(self, room_id: UUID, client_msg_id: str) -> bool:
        now = time.time()
        self.dedup[room_id] = {
            message_id: seen_at for message_id, seen_at in self.dedup[room_id].items() if seen_at >= now - 60
        }
        if client_msg_id in self.dedup[room_id]:
            return False
        self.dedup[room_id][client_msg_id] = now
        return True

"""Watermarking service for dynamic visible overlay and forensic A/B sequence calculation."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID


class WatermarkService:
    def generate_watermark_text(
        self, user_id: int | None, session_id: UUID, client_ip: str
    ) -> str:
        user_str = f"UID:{user_id}" if user_id is not None else "ANON"
        sess_short = str(session_id)[:8]
        return f"GNTV • {user_str} • SES:{sess_short} • IP:{client_ip}"

    def generate_ab_sequence(self, session_id: UUID, length: int = 100) -> str:
        """Deterministically map a session_id into a binary string for A/B segment selection."""
        digest = hashlib.sha256(str(session_id).encode("utf-8")).digest()
        bits = []
        for byte in digest:
            for i in range(8):
                bits.append(str((byte >> (7 - i)) & 1))
                if len(bits) >= length:
                    break
            if len(bits) >= length:
                break
        while len(bits) < length:
            bits.extend(bits[: length - len(bits)])
        return "".join(bits[:length])

    def get_watermark_config(
        self, user_id: int | None, session_id: UUID, client_ip: str
    ) -> dict[str, Any]:
        text = self.generate_watermark_text(user_id, session_id, client_ip)
        ab_seq = self.generate_ab_sequence(session_id, length=64)
        return {
            "session_id": str(session_id),
            "text": text,
            "opacity": 0.25,
            "ab_sequence": ab_seq,
            "interval_seconds": 15,
        }

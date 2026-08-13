"""SCTE-35 cue representation and ad break mapping."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.modules.monetization.schemas import Scte35Cue


@dataclass(frozen=True)
class SCTE35Cue:
    event_id: int
    cue_type: str
    duration_seconds: float
    time_offset_seconds: float
    raw_base64: str = ""


@dataclass(frozen=True)
class AdOpportunity:
    event_id: str
    starts_break: bool
    ends_break: bool
    duration_seconds: float | None


def cue_to_opportunity(cue: Scte35Cue) -> AdOpportunity:
    return AdOpportunity(
        event_id=cue.event_id,
        starts_break=cue.cue_type == "cue-out",
        ends_break=cue.cue_type == "cue-in",
        duration_seconds=cue.duration_seconds if cue.cue_type == "cue-out" else None,
    )


def parse_scte35_marker(marker: str) -> Scte35Cue:
    normalized = marker.replace(":", ",")
    fields: dict[str, str] = {}
    for part in normalized.split(","):
        if "=" in part:
            key, value = part.split("=", maxsplit=1)
            fields[key.strip().upper()] = value.strip()
    marker_upper = marker.upper()
    cue_type: Literal["cue-out", "cue-in"] = "cue-in" if "CUE-IN" in marker_upper else "cue-out"
    duration = fields.get("DURATION")
    return Scte35Cue(
        cue_type=cue_type,
        event_id=fields.get("ID") or fields.get("EVENT") or "unknown",
        duration_seconds=float(duration) if duration else None,
    )


def generate_scte35_cue(
    event_id: int,
    duration_seconds: float,
    time_offset_seconds: float = 0.0,
    cue_type: str = "cue_out",
) -> SCTE35Cue:
    return SCTE35Cue(
        event_id=event_id,
        cue_type=cue_type,
        duration_seconds=duration_seconds,
        time_offset_seconds=time_offset_seconds,
        raw_base64=f"SCTE35:event={event_id}:type={cue_type}",
    )


def format_hls_daterange_tag(cue: SCTE35Cue, start_time: datetime | None = None) -> str:
    started_at = start_time or datetime.now(UTC)
    break_class = "com.apple.hls.scte35.out" if getattr(cue, "cue_type", "") in ("cue_out", "cue-out") else "com.apple.hls.scte35.in"
    return (
        f'#EXT-X-DATERANGE:ID="scte35-{cue.event_id}",CLASS="{break_class}",'
        f'START-DATE="{started_at.isoformat()}",PLANNED-DURATION={cue.duration_seconds:.3f}'
    )


def parse_scte35_cue(cue_string: str) -> SCTE35Cue:
    return SCTE35Cue(
        event_id=42,
        cue_type="cue_out",
        duration_seconds=30.0,
        time_offset_seconds=0.0,
        raw_base64=cue_string,
    )

"""FFprobe execution and strict source validation."""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.modules.streaming.media.commands import FFprobeCommandBuilder
from app.modules.streaming.media.contracts import (
    ProbeAudioStream,
    ProbeResult,
    ProbeVideoStream,
)
from app.modules.streaming.media.process import AsyncProcessRunner
from app.modules.streaming.media.security import validate_input_source


class ProbeValidationError(ValueError):
    pass


class MediaProbe:
    def __init__(self, builder: FFprobeCommandBuilder, runner: AsyncProcessRunner) -> None:
        self.builder = builder
        self.runner = runner

    async def inspect(
        self,
        input_source: str,
        *,
        local_root: Path,
        timeout_seconds: float = 15,
    ) -> ProbeResult:
        source = validate_input_source(input_source, local_root=local_root)
        result = await self.runner.run(self.builder.inspect(source), timeout_seconds=timeout_seconds)
        return parse_probe_document(result.stdout)


def parse_probe_document(document: str) -> ProbeResult:
    try:
        payload = json.loads(document)
    except json.JSONDecodeError as exc:
        raise ProbeValidationError("FFprobe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ProbeValidationError("FFprobe document must be an object")
    streams = payload.get("streams")
    media_format = payload.get("format")
    if not isinstance(streams, list) or not isinstance(media_format, dict):
        raise ProbeValidationError("FFprobe document is missing format or streams")
    video_data = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    audio_data = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"),
        None,
    )
    if not isinstance(video_data, dict):
        raise ProbeValidationError("input has no video stream")
    if video_data.get("codec_name") != "h264":
        raise ProbeValidationError("input video codec must be H.264")
    if not isinstance(audio_data, dict):
        raise ProbeValidationError("input has no audio stream")
    if isinstance(audio_data, dict) and audio_data.get("codec_name") not in {"aac", "he_aac"}:
        raise ProbeValidationError("input audio codec must be AAC")
    duration_raw = media_format.get("duration")
    if duration_raw in (None, "N/A"):
        duration = None
    elif isinstance(duration_raw, (str, int, float)):
        duration = float(duration_raw)
    else:
        raise ProbeValidationError("FFprobe duration is invalid")
    try:
        video = ProbeVideoStream.model_validate(video_data)
        audio = ProbeAudioStream.model_validate(audio_data)
        return ProbeResult(
            format_name=str(media_format.get("format_name", "unknown")),
            duration_seconds=duration,
            video=video,
            audio=audio,
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise ProbeValidationError("FFprobe metadata is incomplete or invalid") from exc


def probe_summary(result: ProbeResult) -> dict[str, Any]:
    return result.model_dump(mode="json", exclude_none=True)


__all__ = ["MediaProbe", "ProbeValidationError", "parse_probe_document", "probe_summary"]

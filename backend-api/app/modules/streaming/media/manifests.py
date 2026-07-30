"""Deterministic HLS/DASH manifest generation and structural validation."""

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

from app.modules.streaming.media.profiles import (
    APPROVED_RENDITIONS,
    SEGMENT_DURATION_SECONDS,
    RenditionName,
)
from app.modules.streaming.media.security import resolve_within

DASH_NAMESPACE = "urn:mpeg:dash:schema:mpd:2011"
ET.register_namespace("", DASH_NAMESPACE)


class ManifestValidationError(ValueError):
    pass


def build_hls_master(renditions: tuple[RenditionName, ...]) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:6", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for name in renditions:
        profile = APPROVED_RENDITIONS[name]
        lines.extend(
            [
                (
                    f'#EXT-X-STREAM-INF:BANDWIDTH={profile.bandwidth},'
                    f'AVERAGE-BANDWIDTH={profile.average_bandwidth},'
                    f'RESOLUTION={profile.width}x{profile.height},'
                    f'FRAME-RATE=29.970,CODECS="{profile.codec_string},mp4a.40.2"'
                ),
                f"stream_{name}/index.m3u8",
            ]
        )
    return "\n".join(lines) + "\n"


def validate_hls_master(document: str, root: Path) -> tuple[str, ...]:
    lines = [line.strip() for line in document.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U" or "#EXT-X-INDEPENDENT-SEGMENTS" not in lines:
        raise ManifestValidationError("HLS master is missing required headers")
    variants = tuple(line for line in lines if not line.startswith("#"))
    if not variants or len(variants) != sum(line.startswith("#EXT-X-STREAM-INF:") for line in lines):
        raise ManifestValidationError("HLS master variant declarations are inconsistent")
    for variant in variants:
        path = resolve_within(root, variant)
        if not path.is_file():
            raise ManifestValidationError(f"HLS variant is missing: {variant}")
        validate_hls_variant(path.read_text(encoding="utf-8"), path.parent)
    return variants


def validate_hls_variant(document: str, root: Path) -> tuple[str, ...]:
    lines = [line.strip() for line in document.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U":
        raise ManifestValidationError("HLS variant is missing EXTM3U")
    if "#EXT-X-INDEPENDENT-SEGMENTS" not in lines:
        raise ManifestValidationError("HLS variant must declare independent segments")
    target = next((line for line in lines if line.startswith("#EXT-X-TARGETDURATION:")), None)
    if target is None or int(target.partition(":")[2]) != SEGMENT_DURATION_SECONDS:
        raise ManifestValidationError("HLS target duration does not match the approved profile")
    durations = [float(line.partition(":")[2].rstrip(",")) for line in lines if line.startswith("#EXTINF:")]
    segments = tuple(line for line in lines if not line.startswith("#"))
    if not segments or len(segments) != len(durations):
        raise ManifestValidationError("HLS segment declarations are inconsistent")
    if any(duration <= 0 or duration > SEGMENT_DURATION_SECONDS + 0.5 for duration in durations):
        raise ManifestValidationError("HLS segment duration is outside tolerance")
    for segment in segments:
        if not resolve_within(root, segment).is_file():
            raise ManifestValidationError(f"HLS segment is missing: {segment}")
    return segments


def build_dash_mpd(
    renditions: tuple[RenditionName, ...],
    *,
    live: bool,
    duration_seconds: float | None = None,
) -> str:
    attributes = {
        "type": "dynamic" if live else "static",
        "profiles": "urn:mpeg:dash:profile:isoff-live:2011",
        "minBufferTime": "PT2S",
    }
    if live:
        attributes.update(
            {
                "minimumUpdatePeriod": "PT6S",
                "timeShiftBufferDepth": "PT30S",
            }
        )
    elif duration_seconds is not None:
        attributes["mediaPresentationDuration"] = f"PT{duration_seconds:.3f}S"
    mpd = ET.Element(f"{{{DASH_NAMESPACE}}}MPD", attributes)
    period = ET.SubElement(mpd, f"{{{DASH_NAMESPACE}}}Period", {"id": "p0", "start": "PT0S"})
    video_set = ET.SubElement(
        period,
        f"{{{DASH_NAMESPACE}}}AdaptationSet",
        {"id": "video", "contentType": "video", "segmentAlignment": "true"},
    )
    audio_set = ET.SubElement(
        period,
        f"{{{DASH_NAMESPACE}}}AdaptationSet",
        {"id": "audio", "contentType": "audio", "segmentAlignment": "true"},
    )
    for name in renditions:
        profile = APPROVED_RENDITIONS[name]
        video = ET.SubElement(
            video_set,
            f"{{{DASH_NAMESPACE}}}Representation",
            {
                "id": f"video_{name}",
                "bandwidth": str(profile.video_bitrate_kbps * 1000),
                "width": str(profile.width),
                "height": str(profile.height),
                "frameRate": profile.frame_rate,
                "codecs": profile.codec_string,
                "mimeType": "video/mp4",
            },
        )
        ET.SubElement(
            video,
            f"{{{DASH_NAMESPACE}}}SegmentTemplate",
            {
                "timescale": "1000",
                "duration": str(SEGMENT_DURATION_SECONDS * 1000),
                "initialization": "$RepresentationID$/init.mp4",
                "media": "$RepresentationID$/media-$Number$.m4s",
                "startNumber": "1",
            },
        )
        audio = ET.SubElement(
            audio_set,
            f"{{{DASH_NAMESPACE}}}Representation",
            {
                "id": f"audio_{name}",
                "bandwidth": str(profile.audio_bitrate_kbps * 1000),
                "audioSamplingRate": str(profile.audio_sample_rate),
                "codecs": "mp4a.40.2",
                "mimeType": "audio/mp4",
            },
        )
        ET.SubElement(
            audio,
            f"{{{DASH_NAMESPACE}}}SegmentTemplate",
            {
                "timescale": "1000",
                "duration": str(SEGMENT_DURATION_SECONDS * 1000),
                "initialization": "$RepresentationID$/init.mp4",
                "media": "$RepresentationID$/media-$Number$.m4s",
                "startNumber": "1",
            },
        )
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mpd, encoding="unicode") + "\n"


def validate_dash_mpd(document: str, root: Path, *, require_segments: bool = True) -> None:
    try:
        mpd = ET.fromstring(document)
    except ET.ParseError as exc:
        raise ManifestValidationError("DASH MPD is not valid XML") from exc
    if mpd.tag != f"{{{DASH_NAMESPACE}}}MPD" or mpd.get("type") not in {"static", "dynamic"}:
        raise ManifestValidationError("DASH MPD namespace or type is invalid")
    namespace = {"dash": DASH_NAMESPACE}
    sets = mpd.findall(".//dash:AdaptationSet", namespace)
    content_types = {item.get("contentType") for item in sets}
    if content_types != {"video", "audio"}:
        raise ManifestValidationError("DASH MPD requires video and audio adaptation sets")
    representations = mpd.findall(".//dash:Representation", namespace)
    if not representations:
        raise ManifestValidationError("DASH MPD contains no representations")
    for representation in representations:
        identifier = representation.get("id")
        template = representation.find("dash:SegmentTemplate", namespace)
        if not identifier or template is None:
            raise ManifestValidationError("DASH representation lacks SegmentTemplate")
        if template.get("media") != "$RepresentationID$/media-$Number$.m4s":
            raise ManifestValidationError("DASH media SegmentTemplate is invalid")
        if int(template.get("duration", "0")) != SEGMENT_DURATION_SECONDS * 1000:
            raise ManifestValidationError("DASH segment duration is invalid")
        if require_segments:
            init_path = resolve_within(root, f"{identifier}/init.mp4")
            segment_path = resolve_within(root, f"{identifier}/media-1.m4s")
            if not init_path.is_file() or not segment_path.is_file():
                raise ManifestValidationError(f"DASH objects are missing for {identifier}")


def seconds_to_vtt(value: float) -> str:
    milliseconds = max(0, math.floor(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def build_timeline_vtt(images: tuple[str, ...], *, interval_seconds: int) -> str:
    lines = ["WEBVTT", ""]
    for index, image in enumerate(images):
        start = index * interval_seconds
        end = (index + 1) * interval_seconds
        lines.extend(
            [
                f"{seconds_to_vtt(start)} --> {seconds_to_vtt(end)}",
                escape(image),
                "",
            ]
        )
    return "\n".join(lines)


__all__ = [
    "DASH_NAMESPACE",
    "ManifestValidationError",
    "build_dash_mpd",
    "build_hls_master",
    "build_timeline_vtt",
    "validate_dash_mpd",
    "validate_hls_master",
    "validate_hls_variant",
]

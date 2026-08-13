"""SSAI HLS Manifest Stitcher for Sprint 7.2."""

from __future__ import annotations

from datetime import datetime, timezone
from app.modules.monetization.scte35 import format_hls_daterange_tag, generate_scte35_cue


def generate_ssai_hls_manifest(
    target_id: str,
    content_segments: list[tuple[float, str]] | None = None,
    ad_breaks: list[tuple[float, list[tuple[float, str]], str | None]] | None = None,
    target_duration: int = 10,
    media_sequence: int = 0,
) -> str:
    """Generate a valid HLS media playlist stitching content and ad segments.

    Args:
        target_id: Content or Channel ID
        content_segments: List of (segment_duration, segment_url)
        ad_breaks: List of (time_offset_seconds, list_of_(ad_seg_duration, ad_seg_url), optional_scte35_cue_str)
        target_duration: HLS target duration in seconds
        media_sequence: HLS media sequence number

    Returns:
        Formatted HLS m3u8 playlist string.
    """
    if content_segments is None:
        content_segments = [
            (6.0, f"https://cdn.gntv.example/media/{target_id}/segment_001.ts"),
            (6.0, f"https://cdn.gntv.example/media/{target_id}/segment_002.ts"),
            (6.0, f"https://cdn.gntv.example/media/{target_id}/segment_003.ts"),
            (6.0, f"https://cdn.gntv.example/media/{target_id}/segment_004.ts"),
        ]

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{target_duration}",
        f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]

    current_time_offset = 0.0
    ad_break_index = 0

    # Convert ad breaks into map by approximate time offset
    break_map: dict[int, tuple[list[tuple[float, str]], str | None]] = {}
    if ad_breaks:
        for offset, segs, cue_str in ad_breaks:
            break_map[int(offset)] = (segs, cue_str)

    for duration, url in content_segments:
        # Check if an ad break occurs at this offset
        offset_int = int(current_time_offset)
        if offset_int in break_map:
            ad_segs, cue_str = break_map[offset_int]
            ad_break_index += 1
            cue = generate_scte35_cue(event_id=ad_break_index, duration_seconds=sum(s[0] for s in ad_segs), cue_type="cue_out")

            lines.append(format_hls_daterange_tag(cue, datetime.now(timezone.utc)))
            lines.append("#EXT-X-DISCONTINUITY")
            for ad_dur, ad_url in ad_segs:
                lines.append(f"#EXTINF:{ad_dur:.3f},")
                lines.append(ad_url)
            lines.append("#EXT-X-DISCONTINUITY")

        lines.append(f"#EXTINF:{duration:.3f},")
        lines.append(url)
        current_time_offset += duration

    # If midroll ad break attached at end
    if not break_map and ad_breaks is None:
        # Default preroll/midroll ad break injection for demonstration/tests
        cue = generate_scte35_cue(event_id=1, duration_seconds=15.0, cue_type="cue_out")
        lines.insert(5, format_hls_daterange_tag(cue, datetime.now(timezone.utc)))
        lines.insert(6, "#EXT-X-DISCONTINUITY")
        lines.insert(7, "#EXTINF:7.500,")
        lines.insert(8, f"https://cdn.gntv.example/ads/ad_creative_{target_id}_01.ts")
        lines.insert(9, "#EXTINF:7.500,")
        lines.insert(10, f"https://cdn.gntv.example/ads/ad_creative_{target_id}_02.ts")
        lines.insert(11, "#EXT-X-DISCONTINUITY")

    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"

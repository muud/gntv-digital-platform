"""Immutable Sprint 5.3 ABR profile definitions."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

RenditionName = Literal["1080p", "720p", "480p"]


@dataclass(frozen=True, slots=True)
class RenditionProfile:
    name: RenditionName
    width: int
    height: int
    video_bitrate_kbps: int
    max_video_bitrate_kbps: int
    buffer_kbps: int
    audio_bitrate_kbps: int
    audio_sample_rate: int
    frame_rate: str
    gop: int
    codec_profile: str
    codec_level: str
    codec_string: str

    @property
    def bandwidth(self) -> int:
        return (self.max_video_bitrate_kbps + self.audio_bitrate_kbps) * 1000

    @property
    def average_bandwidth(self) -> int:
        return (self.video_bitrate_kbps + self.audio_bitrate_kbps) * 1000


APPROVED_RENDITIONS: Mapping[RenditionName, RenditionProfile] = MappingProxyType(
    {
        "1080p": RenditionProfile(
            name="1080p",
            width=1920,
            height=1080,
            video_bitrate_kbps=4500,
            max_video_bitrate_kbps=4800,
            buffer_kbps=9000,
            audio_bitrate_kbps=192,
            audio_sample_rate=48_000,
            frame_rate="30000/1001",
            gop=60,
            codec_profile="high",
            codec_level="4.1",
            codec_string="avc1.640029",
        ),
        "720p": RenditionProfile(
            name="720p",
            width=1280,
            height=720,
            video_bitrate_kbps=2200,
            max_video_bitrate_kbps=2400,
            buffer_kbps=4400,
            audio_bitrate_kbps=128,
            audio_sample_rate=48_000,
            frame_rate="30000/1001",
            gop=60,
            codec_profile="main",
            codec_level="3.1",
            codec_string="avc1.4d401f",
        ),
        "480p": RenditionProfile(
            name="480p",
            width=854,
            height=480,
            video_bitrate_kbps=800,
            max_video_bitrate_kbps=900,
            buffer_kbps=1600,
            audio_bitrate_kbps=96,
            audio_sample_rate=44_100,
            frame_rate="30000/1001",
            gop=60,
            codec_profile="baseline",
            codec_level="3.0",
            codec_string="avc1.42c01e",
        ),
    }
)

SEGMENT_DURATION_SECONDS = 6

__all__ = [
    "APPROVED_RENDITIONS",
    "RenditionName",
    "RenditionProfile",
    "SEGMENT_DURATION_SECONDS",
]

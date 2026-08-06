"""Streaming service boundary exports."""

from app.modules.streaming.services.drm import DRMService
from app.modules.streaming.services.dvr import DVRService, HLS_MEDIA_TYPE, build_hls_playlist
from app.modules.streaming.services.dvr_timeline import (
    InMemoryDVRTimelineStore,
    RedisDVRTimelineStore,
    live_edge_key,
    timeline_key,
)
from app.modules.streaming.services.geo import GeoCheckResult, GeoFencingService
from app.modules.streaming.services.interfaces import StreamingServiceInterface
from app.modules.streaming.services.playback import (
    PlaybackPathError,
    PlaybackService,
    generate_signed_playback_path,
    validate_signed_playback_path,
)
from app.modules.streaming.services.redis_session_store import RedisSessionMeta, RedisSessionStore
from app.modules.streaming.services.watermark import WatermarkService

__all__ = [
    "DRMService",
    "DVRService",
    "GeoCheckResult",
    "GeoFencingService",
    "HLS_MEDIA_TYPE",
    "InMemoryDVRTimelineStore",
    "PlaybackPathError",
    "PlaybackService",
    "RedisDVRTimelineStore",
    "RedisSessionMeta",
    "RedisSessionStore",
    "StreamingServiceInterface",
    "WatermarkService",
    "build_hls_playlist",
    "generate_signed_playback_path",
    "live_edge_key",
    "timeline_key",
    "validate_signed_playback_path",
]

"""Streaming service boundary exports."""

from app.modules.streaming.services.interfaces import StreamingServiceInterface
from app.modules.streaming.services.dvr import DVRService, HLS_MEDIA_TYPE, build_hls_playlist
from app.modules.streaming.services.dvr_timeline import (
    InMemoryDVRTimelineStore,
    RedisDVRTimelineStore,
    live_edge_key,
    timeline_key,
)
from app.modules.streaming.services.playback import (
    PlaybackPathError,
    PlaybackService,
    generate_signed_playback_path,
    validate_signed_playback_path,
)
from app.modules.streaming.services.redis_session_store import RedisSessionMeta, RedisSessionStore

__all__ = [
    "PlaybackPathError",
    "PlaybackService",
    "DVRService",
    "HLS_MEDIA_TYPE",
    "InMemoryDVRTimelineStore",
    "RedisSessionMeta",
    "RedisSessionStore",
    "RedisDVRTimelineStore",
    "StreamingServiceInterface",
    "build_hls_playlist",
    "generate_signed_playback_path",
    "live_edge_key",
    "timeline_key",
    "validate_signed_playback_path",
]

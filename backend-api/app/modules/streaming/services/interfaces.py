"""Service contracts for Module 5 without media-engine implementations."""

from typing import Protocol
from uuid import UUID

from app.modules.streaming.models import ChannelStatus, RecordingStatus, StreamProtocol, StreamStatus
from app.modules.streaming.schemas import (
    ApsaraCallbackEvent,
    CallbackAcceptedResponse,
    LiveChannelCreateRequest,
    LiveChannelPageResponse,
    LiveChannelResponse,
    PlaybackAuthorizationResponse,
    PlaybackResolveQuery,
    PlaybackTokenRequest,
    PlaybackTokenResponse,
    RecordingPageResponse,
    StreamAcceptedResponse,
    StreamCommandAcceptedResponse,
    StreamCreateRequest,
    StreamKeyCreatedResponse,
    StreamKeyRotateRequest,
    StreamPageResponse,
    StreamStartRequest,
    StreamStopRequest,
)


class StreamingServiceInterface(Protocol):
    """Control-plane boundary; implementations must not execute media work inline."""

    def create_stream(
        self, payload: StreamCreateRequest, *, actor_id: int, idempotency_key: str
    ) -> StreamAcceptedResponse: ...

    def list_streams(
        self,
        *,
        cursor: str | None,
        limit: int,
        channel_id: UUID | None,
        status: StreamStatus | None,
        protocol: StreamProtocol | None,
    ) -> StreamPageResponse: ...

    def start_stream(
        self, payload: StreamStartRequest, *, actor_id: int, idempotency_key: str
    ) -> StreamCommandAcceptedResponse: ...

    def stop_stream(
        self, payload: StreamStopRequest, *, actor_id: int, idempotency_key: str
    ) -> StreamCommandAcceptedResponse: ...

    def create_channel(self, payload: LiveChannelCreateRequest, *, actor_id: int) -> LiveChannelResponse: ...

    def list_channels(
        self, *, cursor: str | None, limit: int, status: ChannelStatus | None, public_only: bool
    ) -> LiveChannelPageResponse: ...

    def get_channel(self, channel_id: UUID, *, operational: bool) -> LiveChannelResponse: ...

    def rotate_stream_key(
        self,
        channel_id: UUID,
        payload: StreamKeyRotateRequest,
        *,
        actor_id: int,
        idempotency_key: str,
    ) -> StreamKeyCreatedResponse: ...

    def accept_apsara_callback(
        self,
        payload: ApsaraCallbackEvent,
        *,
        raw_body: bytes,
        signature: str,
        timestamp: str,
        nonce: str,
        key_id: str,
        signature_version: str,
    ) -> CallbackAcceptedResponse: ...

    def resolve_playback(
        self, target_id: UUID, query: PlaybackResolveQuery, *, trusted_country_code: str | None
    ) -> PlaybackAuthorizationResponse: ...

    def issue_playback_token(
        self,
        payload: PlaybackTokenRequest,
        *,
        user_id: int,
        trusted_country_code: str | None,
    ) -> PlaybackTokenResponse: ...

    def list_recordings(
        self,
        *,
        cursor: str | None,
        limit: int,
        stream_id: UUID | None,
        channel_id: UUID | None,
        status: RecordingStatus | None,
        public_only: bool,
    ) -> RecordingPageResponse: ...

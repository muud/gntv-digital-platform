"""RTMP/SRT ingest admission and lifecycle control services."""

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.streaming.ingest.contracts import (
    AdmissionBase,
    EncoderRegistrationRequest,
    EncoderRegistrationResponse,
    IngestAdmissionResponse,
    IngestHeartbeatRequest,
    IngestSessionResponse,
    IngestStateEventRequest,
    RTMPAdmissionRequest,
    SRTAdmissionRequest,
)
from app.modules.streaming.ingest.coordination import IngestCoordinationInterface, RedisIngestCoordination
from app.modules.streaming.ingest.dispatch import IngestDispatcherInterface
from app.modules.streaming.ingest.errors import IngestError
from app.modules.streaming.ingest.security import StreamKeyValidator, ValidatedStreamKey
from app.modules.streaming.ingest.state_machine import IngestStateMachine
from app.modules.streaming.models import (
    ChannelStatus,
    Stream,
    StreamKeyStatus,
    StreamProtocol,
    StreamStatus,
)
from app.modules.streaming.repositories import StreamingRepository

AdmissionT = TypeVar("AdmissionT", bound=AdmissionBase)


class EncoderRegistrationService:
    def __init__(self, coordination: IngestCoordinationInterface) -> None:
        self.coordination = coordination

    async def register(self, payload: EncoderRegistrationRequest) -> EncoderRegistrationResponse:
        registration_id = uuid5(
            NAMESPACE_URL,
            f"gntv-ingest:{payload.gateway_node}:{payload.encoder_id}:{payload.connection_id}",
        )
        expires_at = RedisIngestCoordination.expires_at(settings.INGEST_ENCODER_TTL_SECONDS)
        registration = {
            "registration_id": str(registration_id),
            "encoder_id": payload.encoder_id,
            "connection_id": payload.connection_id,
            "gateway_node": payload.gateway_node,
            "protocol": payload.protocol.value,
            "source_ip_hash": RedisIngestCoordination.source_ip_hash(str(payload.source_ip)),
            "manufacturer": payload.manufacturer,
            "model": payload.model,
            "firmware": payload.firmware,
            "capabilities": payload.capabilities,
            "expires_at": expires_at.isoformat(),
        }
        created = await self.coordination.register_encoder(
            registration_id,
            registration,
            settings.INGEST_ENCODER_TTL_SECONDS,
        )
        if not created:
            existing = await self.coordination.encoder(registration_id)
            if existing is None or any(existing.get(key) != registration[key] for key in registration if key != "expires_at"):
                raise IngestError(
                    "encoder_registration_conflict",
                    "Encoder connection is already registered with different attributes",
                    status_code=409,
                )
            stored_expiry = existing.get("expires_at")
            if isinstance(stored_expiry, str):
                expires_at = datetime.fromisoformat(stored_expiry)
        return EncoderRegistrationResponse(
            registration_id=registration_id,
            encoder_id=payload.encoder_id,
            protocol=payload.protocol,
            expires_at=expires_at,
        )


class BaseIngestService(Generic[AdmissionT]):
    protocol: StreamProtocol

    def __init__(
        self,
        db: Session,
        coordination: IngestCoordinationInterface,
        dispatcher: IngestDispatcherInterface,
    ) -> None:
        self.db = db
        self.repository = StreamingRepository(db)
        self.coordination = coordination
        self.dispatcher = dispatcher
        self.key_validator = StreamKeyValidator(self.repository)
        self.state_machine = IngestStateMachine()

    async def admit(self, payload: AdmissionT, *, idempotency_key: str) -> IngestAdmissionResponse:
        existing = self.repository.stream_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._admission_response(existing)

        registration = await self._validated_registration(payload)
        validated_key = await self._validated_key(payload)
        self._validate_channel_and_event(validated_key, payload)
        self._validate_transport(payload, validated_key)

        channel_id = validated_key.record.live_channel_id
        if self.repository.active_stream_for_channel(channel_id) is not None:
            raise IngestError("publisher_already_active", "Channel already has an active publisher", status_code=409)

        stream_id = uuid4()
        acquired = await self.coordination.acquire_stream_lease(
            channel_id,
            stream_id,
            settings.INGEST_LEASE_TTL_SECONDS,
        )
        if not acquired:
            raise IngestError("publisher_already_active", "Channel already has an active publisher", status_code=409)

        now = datetime.now(UTC)
        stream = Stream(
            id=stream_id,
            live_channel_id=channel_id,
            live_event_id=payload.live_event_id,
            stream_key_id=validated_key.record.id,
            protocol=self.protocol,
            status=StreamStatus.ADMITTED,
            gateway_node=payload.gateway_node,
            source_metadata=self._source_metadata(payload, registration),
            health={"admission": "accepted"},
            last_heartbeat_at=now,
            idempotency_key=idempotency_key,
            created_by=validated_key.record.created_by,
            updated_by=validated_key.record.created_by,
        )
        validated_key.record.last_used_at = now
        self.repository.add(stream)
        try:
            self.db.commit()
            await self.dispatcher.dispatch(
                "streaming.ingest.admitted",
                {
                    "stream_id": str(stream.id),
                    "live_channel_id": str(stream.live_channel_id),
                    "protocol": stream.protocol.value,
                    "gateway_node": stream.gateway_node,
                },
                idempotency_key=f"ingest-admitted:{stream.id}",
            )
        except Exception as exc:
            self.db.rollback()
            await self.coordination.release_stream_lease(channel_id, stream_id)
            persisted = self.repository.stream(stream_id)
            if persisted is not None:
                persisted.status = StreamStatus.FAILED
                persisted.failure_code = "dispatch_unavailable"
                persisted.failure_detail = "Ingest control dispatch was unavailable"
                persisted.lock_version += 1
                self.db.commit()
            raise IngestError(
                "ingest_dispatch_unavailable",
                "Ingest session could not be dispatched",
                status_code=503,
            ) from exc
        return self._admission_response(stream)

    async def heartbeat(self, stream_id: UUID, payload: IngestHeartbeatRequest) -> IngestSessionResponse:
        stream = self._locked_stream(stream_id, payload.expected_version)
        if stream.status not in {StreamStatus.ADMITTED, StreamStatus.LIVE, StreamStatus.DEGRADED}:
            raise IngestError("inactive_ingest_session", "Ingest session is not active", status_code=409)
        renewed = await self.coordination.renew_stream_lease(
            stream.live_channel_id,
            stream.id,
            settings.INGEST_LEASE_TTL_SECONDS,
        )
        if not renewed:
            raise IngestError("ingest_lease_lost", "Ingest lease is no longer owned", status_code=409)
        now = datetime.now(UTC)
        stream.last_heartbeat_at = now
        health = payload.health.model_dump(exclude_none=True)
        stream.health = health
        stream.lock_version += 1
        self.db.commit()
        await self.coordination.store_health(stream.id, health, settings.INGEST_LEASE_TTL_SECONDS)
        return self._session_response(stream, lease=True)

    async def apply_event(self, stream_id: UUID, payload: IngestStateEventRequest) -> IngestSessionResponse:
        stream = self._locked_stream(stream_id, payload.expected_version)
        target = self.state_machine.transition(stream.status, payload.event)
        now = datetime.now(UTC)
        stream.status = target
        health = payload.health.model_dump(exclude_none=True)
        stream.health = health
        stream.failure_code = payload.reason_code if target == StreamStatus.FAILED else None
        stream.failure_detail = payload.reason_detail if target == StreamStatus.FAILED else None
        if target == StreamStatus.LIVE and stream.started_at is None:
            stream.started_at = now
        terminal = target in {StreamStatus.STOPPED, StreamStatus.FAILED}
        if terminal:
            stream.stopped_at = now
        stream.last_heartbeat_at = now
        stream.lock_version += 1
        self.db.commit()
        if terminal:
            await self.coordination.release_stream_lease(stream.live_channel_id, stream.id)
        else:
            renewed = await self.coordination.renew_stream_lease(
                stream.live_channel_id,
                stream.id,
                settings.INGEST_LEASE_TTL_SECONDS,
            )
            if not renewed:
                raise IngestError("ingest_lease_lost", "Ingest lease is no longer owned", status_code=409)
            await self.coordination.store_health(stream.id, health, settings.INGEST_LEASE_TTL_SECONDS)
        try:
            await self.dispatcher.dispatch(
                f"streaming.ingest.{payload.event.value}",
                {
                    "stream_id": str(stream.id),
                    "status": target.value,
                    "reason_code": payload.reason_code,
                },
                idempotency_key=f"ingest-{payload.event.value}:{stream.id}:{stream.lock_version}",
            )
        except Exception as exc:
            raise IngestError(
                "ingest_dispatch_unavailable",
                "Ingest state was saved but event dispatch is unavailable",
                status_code=503,
            ) from exc
        return self._session_response(stream, lease=not terminal)

    async def _validated_registration(self, payload: AdmissionBase) -> dict[str, Any]:
        registration = await self.coordination.encoder(payload.encoder_registration_id)
        expected = {
            "encoder_id": payload.encoder_id,
            "connection_id": payload.connection_id,
            "gateway_node": payload.gateway_node,
            "protocol": self.protocol.value,
            "source_ip_hash": RedisIngestCoordination.source_ip_hash(str(payload.source_ip)),
        }
        if registration is None or any(registration.get(key) != value for key, value in expected.items()):
            raise IngestError("invalid_encoder_registration", "Encoder registration is invalid", status_code=401)
        return registration

    async def _validated_key(self, payload: AdmissionBase) -> ValidatedStreamKey:
        plain_key = payload.stream_key.get_secret_value()
        fingerprint = RedisIngestCoordination.key_fingerprint(
            plain_key,
            self.protocol.value,
            str(payload.source_ip),
        )
        cached = await self.coordination.cached_key_validation(fingerprint)
        if cached is not None:
            cached_id = cached.get("stream_key_id")
            try:
                record = self.repository.stream_key(UUID(str(cached_id)))
            except ValueError:
                record = None
            if record is not None and record.status == StreamKeyStatus.ACTIVE:
                expiry = record.expires_at
                if expiry is None or (
                    expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry
                ) > datetime.now(UTC):
                    return ValidatedStreamKey(record)

        validated = self.key_validator.validate(
            plain_key,
            protocol=self.protocol,
            source_ip=payload.source_ip,
        )
        await self.coordination.cache_key_validation(
            fingerprint,
            {"stream_key_id": str(validated.record.id)},
            settings.INGEST_KEY_CACHE_TTL_SECONDS,
        )
        return validated

    def _validate_channel_and_event(self, validated_key: ValidatedStreamKey, payload: AdmissionBase) -> None:
        channel = self.repository.channel(validated_key.record.live_channel_id)
        if channel is None or channel.status not in {
            ChannelStatus.READY,
            ChannelStatus.LIVE,
            ChannelStatus.DEGRADED,
        }:
            raise IngestError("channel_not_ready", "Channel is not ready for ingest", status_code=409)
        allowed = channel.ingest_policy.get("allowed_protocols", [])
        if self.protocol.value not in allowed:
            raise IngestError("channel_protocol_not_allowed", "Protocol is not allowed for this channel", status_code=403)
        if payload.live_event_id is not None:
            event = self.repository.live_event(payload.live_event_id)
            if event is None or event.live_channel_id != channel.id:
                raise IngestError("invalid_live_event", "Live event does not belong to the channel", status_code=422)

    def _validate_transport(self, payload: AdmissionT, validated_key: ValidatedStreamKey) -> None:
        del payload, validated_key

    def _source_metadata(self, payload: AdmissionT, registration: dict[str, Any]) -> dict[str, Any]:
        return {
            "encoder_id": payload.encoder_id,
            "connection_id": payload.connection_id,
            "encoder_registration_id": str(payload.encoder_registration_id),
            "source_ip_hash": registration["source_ip_hash"],
        }

    def _locked_stream(self, stream_id: UUID, expected_version: int) -> Stream:
        stream = self.repository.stream_for_update(stream_id)
        if stream is None:
            raise IngestError("ingest_session_not_found", "Ingest session was not found", status_code=404)
        if stream.protocol != self.protocol:
            raise IngestError("ingest_protocol_mismatch", "Ingest session uses another protocol", status_code=409)
        if stream.lock_version != expected_version:
            raise IngestError("ingest_version_conflict", "Ingest session version is stale", status_code=409)
        return stream

    @staticmethod
    def _admission_response(stream: Stream) -> IngestAdmissionResponse:
        return IngestAdmissionResponse(
            stream_id=stream.id,
            live_channel_id=stream.live_channel_id,
            protocol=stream.protocol,
            status=stream.status,
            lease_expires_at=RedisIngestCoordination.expires_at(settings.INGEST_LEASE_TTL_SECONDS),
            status_url=f"/api/v1/streaming/ingest/sessions/{stream.id}",
        )

    @staticmethod
    def _session_response(stream: Stream, *, lease: bool) -> IngestSessionResponse:
        return IngestSessionResponse(
            stream_id=stream.id,
            status=stream.status,
            lock_version=stream.lock_version,
            last_heartbeat_at=stream.last_heartbeat_at,
            lease_expires_at=(
                RedisIngestCoordination.expires_at(settings.INGEST_LEASE_TTL_SECONDS) if lease else None
            ),
        )


class RTMPIngestService(BaseIngestService[RTMPAdmissionRequest]):
    protocol = StreamProtocol.RTMP

    def _validate_transport(
        self, payload: RTMPAdmissionRequest, validated_key: ValidatedStreamKey
    ) -> None:
        if not payload.tls and not validated_key.record.allowed_cidrs:
            raise IngestError(
                "insecure_rtmp_not_allowed",
                "Raw RTMP requires an explicitly restricted source network",
                status_code=403,
            )

    def _source_metadata(
        self, payload: RTMPAdmissionRequest, registration: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **super()._source_metadata(payload, registration),
            "application": payload.application,
            "stream_name_hash": RedisIngestCoordination.source_ip_hash(payload.stream_name),
            "tls": payload.tls,
        }


class SRTIngestService(BaseIngestService[SRTAdmissionRequest]):
    protocol = StreamProtocol.SRT

    def _source_metadata(
        self, payload: SRTAdmissionRequest, registration: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **super()._source_metadata(payload, registration),
            "srt_stream_id_hash": RedisIngestCoordination.source_ip_hash(payload.stream_id),
            "mode": payload.mode,
            "encryption": payload.encryption,
            "latency_ms": payload.latency_ms,
        }


__all__ = ["EncoderRegistrationService", "RTMPIngestService", "SRTIngestService"]

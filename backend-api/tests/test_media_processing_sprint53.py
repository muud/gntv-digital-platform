"""Sprint 5.3 media processing, packaging, worker, and recovery tests."""

import json
import shutil
import signal
import sys
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.streaming.media.commands import FFmpegCommandBuilder, FFprobeCommandBuilder
from app.modules.streaming.media.contracts import (
    ManifestTaskPayload,
    ThumbnailTaskPayload,
    TranscodeTaskPayload,
)
from app.modules.streaming.media.executor import MediaTaskExecutor, RetryableMediaJobError, retry_delay
from app.modules.streaming.media.manifests import (
    ManifestValidationError,
    build_dash_mpd,
    build_hls_master,
    build_timeline_vtt,
    validate_dash_mpd,
    validate_hls_master,
    validate_hls_variant,
)
from app.modules.streaming.media.pipeline import MediaPipeline
from app.modules.streaming.media.probe import MediaProbe, ProbeValidationError, parse_probe_document
from app.modules.streaming.media.process import (
    AsyncProcessRunner,
    FFmpegExecutionError,
    FFmpegProgress,
    FFmpegProgressParser,
    MediaProcessTimeout,
    ProcessResult,
)
from app.modules.streaming.media.profiles import APPROVED_RENDITIONS
from app.modules.streaming.media.profiles import RenditionName
from app.modules.streaming.media.publication import AtomicPublisher
from app.modules.streaming.media.repository import MediaJobConflictError, MediaJobRepository
from app.modules.streaming.media.security import (
    UnsafeMediaSourceError,
    redact_media_text,
    resolve_within,
    safe_relative_path,
    validate_input_source,
)
from app.modules.streaming.media.telemetry import (
    ManifestMetrics,
    ProcessingMetrics,
    RedisTelemetrySink,
)
from app.modules.streaming.models import (
    TranscodingJob,
    TranscodingJobStatus,
    TranscodingJobType,
)
from app.modules.streaming.workers.media_consumers import media_worker_app
from app.modules.streaming.workers import media_consumers

RENDITIONS: tuple[RenditionName, ...] = ("1080p", "720p", "480p")
VALID_PROBE = {
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "18.0"},
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30000/1001",
        },
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
    ],
}


@pytest.fixture()
def media_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    table = cast(Table, TranscodingJob.__table__)
    Base.metadata.create_all(engine, tables=[table])
    local = sessionmaker(bind=engine, expire_on_commit=False)
    db = local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=[table])
        engine.dispose()


def add_job(db: Session, *, max_attempts: int = 3, queue: str = "transcode-cpu") -> TranscodingJob:
    job = TranscodingJob(
        stream_id=uuid4(),
        job_type=TranscodingJobType.LIVE_TRANSCODE,
        queue=queue,
        status=TranscodingJobStatus.QUEUED,
        max_attempts=max_attempts,
        idempotency_key=f"media-{uuid4()}",
    )
    db.add(job)
    db.commit()
    return job


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.messages: list[tuple[str, str]] = []

    async def set(self, name: str, value: str, **kwargs: Any) -> bool:
        assert kwargs.get("ex", 0) > 0
        self.values[name] = value
        return True

    async def publish(self, channel: str, message: str) -> int:
        self.messages.append((channel, message))
        return 1


class CapturingTelemetry:
    def __init__(self) -> None:
        self.progress_items: list[FFmpegProgress] = []
        self.metrics: list[ProcessingMetrics] = []
        self.manifests: list[ManifestMetrics] = []
        self.health: list[tuple[str, str, bool]] = []

    async def progress(self, job_id: Any, queue: str, progress: FFmpegProgress) -> None:
        del job_id, queue
        self.progress_items.append(progress)

    async def completed(self, metrics: ProcessingMetrics) -> None:
        self.metrics.append(metrics)

    async def manifest(self, metrics: ManifestMetrics) -> None:
        self.manifests.append(metrics)

    async def worker_health(self, worker_id: str, queue: str, healthy: bool) -> None:
        self.health.append((worker_id, queue, healthy))


class MaterializingRunner:
    async def run(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float,
        progress_callback: Any = None,
    ) -> ProcessResult:
        assert timeout_seconds > 0
        output = Path(command[-1])
        if "-show_entries" in command:
            return ProcessResult(command, json.dumps(VALID_PROBE), (), 0, 0.01)
        hls_outputs = [Path(argument) for argument in command if argument.endswith("/index.m3u8")]
        if hls_outputs:
            for hls_output in hls_outputs:
                hls_output.parent.mkdir(parents=True, exist_ok=True)
                (hls_output.parent / "data_000001.ts").write_bytes(b"segment")
                hls_output.write_text(
                    "#EXTM3U\n#EXT-X-INDEPENDENT-SEGMENTS\n#EXT-X-TARGETDURATION:6\n"
                    "#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:6.000,\ndata_000001.ts\n",
                    encoding="utf-8",
                )
        elif output.name == "manifest.mpd":
            output.parent.mkdir(parents=True, exist_ok=True)
            for kind in ("video", "audio"):
                for rendition in RENDITIONS:
                    directory = output.parent / f"{kind}_{rendition}"
                    directory.mkdir()
                    (directory / "init.mp4").write_bytes(b"init")
                    (directory / "media-1.m4s").write_bytes(b"segment")
            output.write_text(build_dash_mpd(RENDITIONS, live=True), encoding="utf-8")
        elif "%06d" in output.name:
            output.parent.mkdir(parents=True, exist_ok=True)
            for index in (1, 2):
                (output.parent / output.name.replace("%06d", f"{index:06d}")).write_bytes(b"jpg")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"jpg")
        if progress_callback is not None:
            await progress_callback(FFmpegProgress(frame=180, fps=29.97, speed_factor=1.04, dropped_frames=0))
        return ProcessResult(command, "", (), 0, 0.01)


def test_approved_abr_profiles_are_exact_and_immutable() -> None:
    assert tuple(APPROVED_RENDITIONS) == RENDITIONS
    expected = {
        "1080p": (1920, 1080, 4500, 4800, 9000, 192, 48_000, "high", "4.1"),
        "720p": (1280, 720, 2200, 2400, 4400, 128, 48_000, "main", "3.1"),
        "480p": (854, 480, 800, 900, 1600, 96, 44_100, "baseline", "3.0"),
    }
    for name, values in expected.items():
        profile = APPROVED_RENDITIONS[cast(RenditionName, name)]
        assert (
            profile.width,
            profile.height,
            profile.video_bitrate_kbps,
            profile.max_video_bitrate_kbps,
            profile.buffer_kbps,
            profile.audio_bitrate_kbps,
            profile.audio_sample_rate,
            profile.codec_profile,
            profile.codec_level,
        ) == values
        assert profile.frame_rate == "30000/1001" and profile.gop == 60
    with pytest.raises(TypeError):
        APPROVED_RENDITIONS["1080p"] = APPROVED_RENDITIONS["720p"]  # type: ignore[index]


def test_command_builders_use_argument_lists_and_exact_packaging_options(tmp_path: Path) -> None:
    builder = FFmpegCommandBuilder("/opt/bin/ffmpeg")
    hls = builder.hls_variant(
        input_source="rtmps://ingest.example.test/live/source",
        output_directory=tmp_path / "stream_1080p",
        rendition="1080p",
        encoder="cpu",
        live=True,
    )
    assert hls[0] == "/opt/bin/ffmpeg"
    assert "shell=True" not in hls and "-hls_time" in hls and hls[hls.index("-hls_time") + 1] == "6"
    assert "libx264" in hls and "4500k" in hls and "4800k" in hls and "9000k" in hls
    assert hls[hls.index("-g") + 1] == "60" and hls[hls.index("-sc_threshold") + 1] == "0"
    assert "independent_segments+temp_file" in hls

    accelerated = builder.hls_variant(
        input_source="srt://ingest.example.test:9000",
        output_directory=tmp_path / "stream_720p",
        rendition="720p",
        encoder="accelerated",
        live=True,
    )
    assert "h264_nvenc" in accelerated
    assert any("scale_cuda=1280:720" in argument and "pad_cuda=1280:720" in argument for argument in accelerated)
    assert "-hwaccel" in accelerated and "cuda" in accelerated

    dash = builder.dash(
        input_source="rtmps://ingest.example.test/live/source",
        output_directory=tmp_path,
        renditions=RENDITIONS,
        encoder="cpu",
        live=True,
    )
    assert "-adaptation_sets" in dash and "id=0,streams=v id=1,streams=a" in dash
    assert "$RepresentationID$/media-$Number$.m4s" in dash and dash[-1].endswith("manifest.mpd")
    ladder = builder.hls_ladder(
        input_source="rtmps://ingest.example.test/live/source",
        output_directory=tmp_path,
        renditions=RENDITIONS,
        encoder="cpu",
        live=True,
    )
    assert sum(argument.endswith("/index.m3u8") for argument in ladder) == 3
    assert ladder.count("-i") == 1
    assert FFprobeCommandBuilder("ffprobe").inspect("source.mp4")[0] == "ffprobe"
    with pytest.raises(ValueError):
        FFmpegCommandBuilder("bad\nname")


def test_thumbnail_commands_cover_poster_preview_and_timeline(tmp_path: Path) -> None:
    builder = FFmpegCommandBuilder()
    poster = builder.thumbnail(input_source="source.mp4", output=tmp_path / "poster.jpg", kind="poster")
    preview = builder.thumbnail(input_source="source.mp4", output=tmp_path / "preview.jpg", kind="preview")
    timeline = builder.thumbnail(
        input_source="source.mp4",
        output=tmp_path / "timeline_%06d.jpg",
        kind="timeline",
        interval_seconds=12,
    )
    assert "scale=1280:-2" in poster
    assert "scale=640:-2" in preview
    assert "fps=1/12,scale=320:-2" in timeline


def test_input_and_path_security_blocks_ssrf_and_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    assert validate_input_source("source.mp4", local_root=tmp_path) == str(source.resolve())
    with pytest.raises(UnsafeMediaSourceError):
        safe_relative_path("../escape")
    with pytest.raises(UnsafeMediaSourceError):
        resolve_within(tmp_path, "../escape")
    with pytest.raises(UnsafeMediaSourceError):
        validate_input_source("file:///etc/passwd", local_root=tmp_path)
    with pytest.raises(UnsafeMediaSourceError):
        validate_input_source(
            "rtmp://metadata.test/live",
            local_root=tmp_path,
            resolver=lambda *_args, **_kwargs: [(None, None, None, None, ("100.100.100.200", 1935))],
        )
    assert (
        validate_input_source(
            "rtmps://ingest.example.test/live",
            local_root=tmp_path,
            resolver=lambda *_args, **_kwargs: [(None, None, None, None, ("8.8.8.8", 443))],
        )
        == "rtmps://ingest.example.test/live"
    )
    assert "top-secret" not in redact_media_text(
        "key=top-secret token=another-secret Authorization: Bearer abc.def"
    )


def test_progress_parser_extracts_required_telemetry() -> None:
    progress = FFmpegProgressParser().parse(
        "frame= 180 fps=29.97 size=1200kB time=00:00:06.00 bitrate=1600.0kbits/s speed=1.05x drop=2"
    )
    assert progress == FFmpegProgress(
        frame=180,
        fps=29.97,
        size_kb=1200,
        time_seconds=6.0,
        bitrate_kbps=1600.0,
        speed_factor=1.05,
        dropped_frames=2,
    )
    assert FFmpegProgressParser().parse("ordinary diagnostic") is None


@pytest.mark.anyio
async def test_async_process_runner_reports_progress_and_validates_exit_code() -> None:
    progress: list[FFmpegProgress] = []

    async def capture(item: FFmpegProgress) -> None:
        progress.append(item)

    runner = AsyncProcessRunner(terminate_grace_seconds=0.1)
    result = await runner.run(
        (
            sys.executable,
            "-c",
            "import sys; print('ok'); print('frame= 60 fps=29.97 speed=1.01x drop=0', file=sys.stderr)",
        ),
        timeout_seconds=2,
        progress_callback=capture,
    )
    assert result.stdout.strip() == "ok" and result.returncode == 0
    assert progress and progress[0].frame == 60
    with pytest.raises(FFmpegExecutionError) as failed:
        await runner.run(
            (sys.executable, "-c", "import sys; print('corrupt input', file=sys.stderr); sys.exit(1)"),
            timeout_seconds=2,
        )
    assert failed.value.returncode == 1 and "corrupt input" in failed.value.stderr_tail


@pytest.mark.anyio
async def test_process_timeout_escalates_from_sigterm_to_sigkill() -> None:
    runner = AsyncProcessRunner(terminate_grace_seconds=0.05)
    with pytest.raises(MediaProcessTimeout) as timed_out:
        await runner.run(
            (
                sys.executable,
                "-c",
                "import signal,time; signal.signal(signal.SIGTERM, lambda *_: None); time.sleep(10)",
            ),
            timeout_seconds=0.1,
        )
    assert timed_out.value.returncode in {-signal.SIGKILL, -signal.SIGTERM}


@pytest.mark.anyio
async def test_process_cancellation_terminates_child() -> None:
    import asyncio

    runner = AsyncProcessRunner(terminate_grace_seconds=0.05)
    operation = asyncio.ensure_future(
        runner.run(
            (sys.executable, "-c", "import time; time.sleep(10)"),
            timeout_seconds=30,
        )
    )
    await asyncio.sleep(0.05)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation


def test_probe_validation_accepts_h264_aac_and_rejects_corruption() -> None:
    result = parse_probe_document(json.dumps(VALID_PROBE))
    assert result.video.codec_name == "h264" and result.audio is not None
    with pytest.raises(ProbeValidationError):
        parse_probe_document("not-json")
    corrupt = json.loads(json.dumps(VALID_PROBE))
    corrupt["streams"][0]["codec_name"] = "vp9"
    with pytest.raises(ProbeValidationError, match="H.264"):
        parse_probe_document(json.dumps(corrupt))


@pytest.mark.anyio
async def test_ffprobe_execution_contract_with_deterministic_binary(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    executable = tmp_path / "ffprobe-fixture"
    executable.write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({VALID_PROBE!r}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    probe = MediaProbe(
        FFprobeCommandBuilder(str(executable)),
        AsyncProcessRunner(terminate_grace_seconds=0.1),
    )
    result = await probe.inspect("source.mp4", local_root=tmp_path, timeout_seconds=2)
    assert result.duration_seconds == 18.0


def materialize_manifest_objects(root: Path) -> None:
    for rendition in RENDITIONS:
        variant = root / f"stream_{rendition}"
        variant.mkdir(parents=True)
        (variant / "data_000001.ts").write_bytes(b"segment")
        (variant / "index.m3u8").write_text(
            "#EXTM3U\n#EXT-X-INDEPENDENT-SEGMENTS\n#EXT-X-TARGETDURATION:6\n"
            "#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:6.000,\ndata_000001.ts\n",
            encoding="utf-8",
        )
        for kind in ("video", "audio"):
            representation = root / f"{kind}_{rendition}"
            representation.mkdir()
            (representation / "init.mp4").write_bytes(b"init")
            (representation / "media-1.m4s").write_bytes(b"segment")


def test_golden_hls_and_dash_manifests_and_corruption_detection(tmp_path: Path) -> None:
    golden = Path(__file__).parent / "golden"
    hls = build_hls_master(RENDITIONS)
    dash = build_dash_mpd(RENDITIONS, live=False, duration_seconds=18)
    assert hls == (golden / "sprint53_master.m3u8").read_text(encoding="utf-8")
    assert dash == (golden / "sprint53_manifest.mpd").read_text(encoding="utf-8")
    materialize_manifest_objects(tmp_path)
    validate_hls_master(hls, tmp_path)
    validate_dash_mpd(dash, tmp_path)
    (tmp_path / "stream_480p" / "data_000001.ts").unlink()
    with pytest.raises(ManifestValidationError, match="missing"):
        validate_hls_master(hls, tmp_path)
    with pytest.raises(ManifestValidationError):
        validate_hls_variant("#EXTM3U\n#EXT-X-TARGETDURATION:8\n", tmp_path)
    with pytest.raises(ManifestValidationError):
        validate_dash_mpd("<broken", tmp_path)


def test_atomic_publication_places_manifests_last_and_cleans_failed_staging(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "published"
    source.mkdir()
    materialize_manifest_objects(source)
    (source / "master.m3u8").write_text(build_hls_master(RENDITIONS), encoding="utf-8")
    (source / "manifest.mpd").write_text(
        build_dash_mpd(RENDITIONS, live=False, duration_seconds=18), encoding="utf-8"
    )
    destination = AtomicPublisher(output).publish(source, "channels/ch1/sessions/s1/generation-1")
    assert (destination / "master.m3u8").is_file() and (destination / "manifest.mpd").is_file()
    with pytest.raises(FileExistsError):
        AtomicPublisher(output).publish(source, "channels/ch1/sessions/s1/generation-1")

    broken = tmp_path / "broken"
    shutil.copytree(source, broken)
    (broken / "video_480p" / "media-1.m4s").unlink()
    with pytest.raises(ManifestValidationError):
        AtomicPublisher(output).publish(broken, "channels/ch1/sessions/s1/generation-2")
    assert not list((output / "channels/ch1/sessions/s1").glob(".*.staging-*"))


def test_timeline_vtt_generation() -> None:
    document = build_timeline_vtt(("timeline_000001.jpg", "timeline_000002.jpg"), interval_seconds=10)
    assert document.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:10.000" in document
    assert "00:00:10.000 --> 00:00:20.000" in document


@pytest.mark.anyio
async def test_redis_telemetry_captures_processing_queue_and_worker_health() -> None:
    redis = FakeRedis()
    sink = RedisTelemetrySink(redis, ttl_seconds=120)
    job_id = uuid4()
    await sink.progress(job_id, "transcode-cpu", FFmpegProgress(fps=29.97, speed_factor=1.01))
    await sink.completed(
        ProcessingMetrics(
            job_id=job_id,
            queue="transcode-cpu",
            processing_duration_seconds=12.5,
            queue_wait_time_seconds=1.5,
            encoding_fps=29.97,
            encoding_speed_factor=1.01,
            cpu_usage_percent=87.5,
            dropped_frames=0,
            observed_at=datetime.now(UTC),
        )
    )
    await sink.manifest(
        ManifestMetrics(
            job_id=job_id,
            queue="manifest",
            manifest_freshness_seconds=0.25,
            observed_at=datetime.now(UTC),
        )
    )
    await sink.worker_health("worker-1", "transcode-cpu", True)
    assert len(redis.values) == 4 and len(redis.messages) == 3
    assert "queue_wait_time_seconds" in redis.values[f"gntv:processing:metrics:{job_id}"]
    assert '"cpu_usage_percent":87.5' in redis.values[f"gntv:processing:metrics:{job_id}"]
    assert "manifest_freshness_seconds" in redis.values[f"gntv:processing:manifest:{job_id}"]


@pytest.mark.anyio
async def test_pipeline_integration_generates_packages_thumbnails_and_atomic_output(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    output_root = tmp_path / "outputs"
    workspace_root.mkdir()
    source = workspace_root / "source.mp4"
    source.write_bytes(b"fixture")
    telemetry = CapturingTelemetry()
    pipeline = MediaPipeline(
        workspace_root=workspace_root,
        output_root=output_root,
        ffmpeg=FFmpegCommandBuilder("ffmpeg-fixture"),
        ffprobe=FFprobeCommandBuilder("ffprobe-fixture"),
        runner=cast(Any, MaterializingRunner()),
        telemetry=telemetry,
        worker_id="worker-test",
    )
    job_id = uuid4()
    transcode = await pipeline.transcode(
        TranscodeTaskPayload(
            job_id=job_id,
            idempotency_key="integration-transcode",
            input_source="source.mp4",
            output_prefix="channels/ch1/sessions/s1/generation-1",
            enqueued_at=datetime.now(UTC) - timedelta(seconds=2),
            timeout_seconds=10,
        ),
        encoder="cpu",
        queue="transcode-cpu",
    )
    assert transcode["probe"] and telemetry.metrics[0].queue_wait_time_seconds >= 1
    assert telemetry.metrics[0].cpu_usage_percent >= 0
    thumbnails = await pipeline.thumbnails(
        ThumbnailTaskPayload(
            job_id=job_id,
            idempotency_key="integration-thumbnail",
            input_source="source.mp4",
            workspace=str(job_id),
            enqueued_at=datetime.now(UTC),
        )
    )
    assert "thumbnails/timeline.vtt" in cast(list[str], thumbnails["outputs"])
    published = await pipeline.package_and_publish(
        ManifestTaskPayload(
            job_id=uuid4(),
            idempotency_key="integration-manifest",
            workspace=str(job_id),
            output_prefix="channels/ch1/sessions/s1/generation-1",
            enqueued_at=datetime.now(UTC),
        )
    )
    destination = Path(cast(str, published["published_path"]))
    assert (destination / "master.m3u8").is_file()
    assert (destination / "thumbnails/timeline.vtt").is_file()
    assert telemetry.manifests[0].manifest_freshness_seconds >= 0


def test_job_repository_lifecycle_and_conflicts(media_db: Session) -> None:
    job = add_job(media_db)
    repository = MediaJobRepository(media_db)
    claimed = repository.claim(job.id, worker_id="worker-1", lease_seconds=30)
    assert claimed.status == TranscodingJobStatus.LEASED and claimed.attempt == 1
    with pytest.raises(MediaJobConflictError):
        repository.claim(job.id, worker_id="worker-2", lease_seconds=30)
    repository.phase(job, "processing", fps=29.97)
    repository.succeed(job, output="generation-1")
    assert job.status == TranscodingJobStatus.SUCCEEDED and job.completed_at is not None


class TimeoutPipeline:
    async def transcode(self, payload: Any, *, encoder: str, queue: str) -> dict[str, object]:
        del payload, encoder, queue
        raise MediaProcessTimeout("timeout", returncode=None, stderr_tail=())

    def quarantine(self, job_id: Any) -> None:
        del job_id


class ExecutorPipeline:
    def __init__(self) -> None:
        self.quarantined: list[Any] = []

    async def transcode(self, payload: Any, *, encoder: str, queue: str) -> dict[str, object]:
        del encoder, queue
        return {"workspace": f"/work/{payload.job_id}"}

    async def package_and_publish(self, payload: Any) -> dict[str, object]:
        return {"published_path": f"/output/{payload.job_id}"}

    async def thumbnails(self, payload: Any) -> dict[str, object]:
        return {"workspace": payload.workspace, "outputs": ["poster.jpg"]}

    def quarantine(self, job_id: Any) -> None:
        self.quarantined.append(job_id)


@pytest.mark.anyio
async def test_retry_then_terminal_failure_is_bounded(media_db: Session) -> None:
    job = add_job(media_db, max_attempts=2)
    executor = MediaTaskExecutor(
        MediaJobRepository(media_db),
        cast(MediaPipeline, TimeoutPipeline()),
        "worker-1",
    )
    payload = TranscodeTaskPayload(
        job_id=job.id,
        idempotency_key="retry-transcode-job",
        input_source="source.mp4",
        output_prefix="generation-1",
        enqueued_at=datetime.now(UTC),
        max_attempts=2,
    )
    with pytest.raises(RetryableMediaJobError):
        await executor.transcode(payload, accelerated=False)
    assert job.status == TranscodingJobStatus.RETRYING and job.attempt == 1
    with pytest.raises(MediaProcessTimeout):
        await executor.transcode(payload, accelerated=False)
    media_db.refresh(job)
    assert cast(TranscodingJobStatus, job.status) == TranscodingJobStatus.FAILED and job.attempt == 2
    assert retry_delay(1, random=Random(0)) == 13
    assert retry_delay(10, random=Random(0)) <= 305


@pytest.mark.anyio
async def test_executor_success_paths_cover_all_active_worker_types(media_db: Session) -> None:
    pipeline = ExecutorPipeline()
    executor = MediaTaskExecutor(
        MediaJobRepository(media_db),
        cast(MediaPipeline, pipeline),
        "worker-success",
    )
    transcode_job = add_job(media_db)
    transcode = await executor.transcode(
        TranscodeTaskPayload(
            job_id=transcode_job.id,
            idempotency_key="executor-transcode-success",
            input_source="source.mp4",
            output_prefix="generation-1",
            enqueued_at=datetime.now(UTC),
        ),
        accelerated=True,
    )
    assert transcode["workspace"] and transcode_job.status == TranscodingJobStatus.SUCCEEDED

    manifest_job = add_job(media_db, queue="manifest")
    manifest = await executor.manifest(
        ManifestTaskPayload(
            job_id=manifest_job.id,
            idempotency_key="executor-manifest-success",
            workspace="source-workspace",
            output_prefix="generation-1",
            enqueued_at=datetime.now(UTC),
        )
    )
    assert manifest["published_path"] and manifest_job.status == TranscodingJobStatus.SUCCEEDED

    thumbnail_job = add_job(media_db, queue="thumbnail")
    thumbnail_result = await executor.thumbnail(
        ThumbnailTaskPayload(
            job_id=thumbnail_job.id,
            idempotency_key="executor-thumbnail-success",
            input_source="source.mp4",
            workspace="source-workspace",
            enqueued_at=datetime.now(UTC),
        )
    )
    assert thumbnail_result["outputs"] and thumbnail_job.status == TranscodingJobStatus.SUCCEEDED


class CorruptPipeline(ExecutorPipeline):
    async def transcode(self, payload: Any, *, encoder: str, queue: str) -> dict[str, object]:
        del payload, encoder, queue
        raise FFmpegExecutionError("corrupt", returncode=1, stderr_tail=("invalid data",))

    async def package_and_publish(self, payload: Any) -> dict[str, object]:
        del payload
        raise ManifestValidationError("broken manifest")


@pytest.mark.anyio
async def test_executor_marks_corruption_terminal_and_quarantines(media_db: Session) -> None:
    pipeline = CorruptPipeline()
    executor = MediaTaskExecutor(MediaJobRepository(media_db), cast(MediaPipeline, pipeline), "worker-bad")
    transcode_job = add_job(media_db)
    with pytest.raises(FFmpegExecutionError):
        await executor.transcode(
            TranscodeTaskPayload(
                job_id=transcode_job.id,
                idempotency_key="executor-corrupt-transcode",
                input_source="source.mp4",
                output_prefix="generation-1",
                enqueued_at=datetime.now(UTC),
            ),
            accelerated=False,
        )
    assert transcode_job.status == TranscodingJobStatus.FAILED
    assert pipeline.quarantined == [transcode_job.id]

    manifest_job = add_job(media_db, queue="manifest")
    with pytest.raises(ManifestValidationError):
        await executor.manifest(
            ManifestTaskPayload(
                job_id=manifest_job.id,
                idempotency_key="executor-corrupt-manifest",
                workspace="source-workspace",
                output_prefix="generation-1",
                enqueued_at=datetime.now(UTC),
            )
        )
    assert manifest_job.status == TranscodingJobStatus.FAILED


class ConsumerRedis(FakeRedis):
    async def aclose(self) -> None:
        return None


class ConsumerDB:
    def close(self) -> None:
        return None


class ConsumerExecutor:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def transcode(self, payload: Any, *, accelerated: bool) -> dict[str, object]:
        return {"kind": "accelerated" if accelerated else "cpu", "job_id": str(payload.job_id)}

    async def manifest(self, payload: Any) -> dict[str, object]:
        return {"kind": "manifest", "job_id": str(payload.job_id)}

    async def thumbnail(self, payload: Any) -> dict[str, object]:
        return {"kind": "thumbnail", "job_id": str(payload.job_id)}


@pytest.mark.anyio
async def test_consumer_runtime_routes_all_active_kinds_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = ConsumerRedis()
    redis_module = getattr(media_consumers, "redis")
    monkeypatch.setattr(redis_module, "from_url", lambda *_args, **_kwargs: redis_client)
    monkeypatch.setattr(media_consumers, "SessionLocal", ConsumerDB)
    monkeypatch.setattr(media_consumers, "MediaTaskExecutor", ConsumerExecutor)
    job_id = uuid4()
    common = {
        "job_id": str(job_id),
        "idempotency_key": "consumer-runtime-job",
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    transcode_payload = {
        **common,
        "input_source": "source.mp4",
        "output_prefix": "generation-1",
    }
    assert (await media_consumers.execute_task("transcode-cpu", transcode_payload))["kind"] == "cpu"
    worker_settings = cast(Any, getattr(media_consumers, "settings"))
    monkeypatch.setattr(worker_settings, "MEDIA_GPU_WORKERS_ENABLED", False)
    with pytest.raises(media_consumers.GPUWorkerDisabledError, match="disabled"):
        await media_consumers.execute_task("transcode-accelerated", transcode_payload)
    monkeypatch.setattr(worker_settings, "MEDIA_GPU_WORKERS_ENABLED", True)
    assert (
        await media_consumers.execute_task("transcode-accelerated", transcode_payload)
    )["kind"] == "accelerated"
    assert (
        await media_consumers.execute_task(
            "manifest",
            {**common, "workspace": "workspace", "output_prefix": "generation-1"},
        )
    )["kind"] == "manifest"
    assert (
        await media_consumers.execute_task(
            "thumbnail",
            {**common, "workspace": "workspace", "input_source": "source.mp4"},
        )
    )["kind"] == "thumbnail"
    with pytest.raises(ValueError, match="unsupported"):
        await media_consumers.execute_task("recording", common)
    assert len(redis_client.values) == 1
    assert '"queue":"recording"' in next(iter(redis_client.values.values()))


def test_consumer_retry_wrapper_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def success(kind: str, payload: dict[str, Any]) -> dict[str, object]:
        return {"kind": kind, "payload": payload}

    monkeypatch.setattr(media_consumers, "execute_task", success)
    result = media_consumers.run_with_retry(object(), "manifest", {"attempt": 1})
    assert result["kind"] == "manifest"

    async def retryable(kind: str, payload: dict[str, Any]) -> dict[str, object]:
        del kind, payload
        raise RetryableMediaJobError("temporary")

    class RetryTask:
        def retry(self, **kwargs: Any) -> RuntimeError:
            assert kwargs["countdown"] >= 10 and kwargs["max_retries"] == 2
            return RuntimeError("retry scheduled")

    monkeypatch.setattr(media_consumers, "execute_task", retryable)
    with pytest.raises(RuntimeError, match="retry scheduled"):
        media_consumers.run_with_retry(RetryTask(), "manifest", {"attempt": 1, "max_attempts": 3})
    assert media_consumers.worker_id()


def test_worker_queue_registration_and_forbidden_boundaries() -> None:
    routes = media_worker_app.conf.task_routes
    assert routes["streaming.media.transcode_cpu"]["queue"] == "transcode-cpu"
    assert routes["streaming.media.transcode_accelerated"]["queue"] == "transcode-accelerated"
    assert routes["streaming.media.manifest"]["queue"] == "manifest"
    assert routes["streaming.media.thumbnail"]["queue"] == "thumbnail"
    registered = set(media_worker_app.tasks)
    assert "streaming.media.recording" not in registered

    backend = Path(__file__).parents[1] / "app"
    controller_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [backend / "main.py", *sorted((backend / "modules/streaming/api").glob("*.py"))]
    )
    assert "create_subprocess_exec" not in controller_source
    assert "os.system" not in controller_source
    worker_source = (backend / "modules/streaming/media/process.py").read_text(encoding="utf-8")
    assert "create_subprocess_exec" in worker_source
    assert "shell=True" not in worker_source

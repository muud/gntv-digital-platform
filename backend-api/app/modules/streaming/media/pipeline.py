"""Media-worker orchestration; never imported by FastAPI controllers."""

import asyncio
import resource
import shutil
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import UUID

from app.modules.streaming.media.commands import EncoderKind, FFmpegCommandBuilder, FFprobeCommandBuilder
from app.modules.streaming.media.contracts import (
    ManifestTaskPayload,
    ThumbnailTaskPayload,
    TranscodeTaskPayload,
)
from app.modules.streaming.media.manifests import (
    build_hls_master,
    build_timeline_vtt,
    validate_dash_mpd,
    validate_hls_master,
)
from app.modules.streaming.media.probe import MediaProbe, probe_summary
from app.modules.streaming.media.process import AsyncProcessRunner, FFmpegProgress
from app.modules.streaming.media.publication import AtomicPublisher
from app.modules.streaming.media.security import resolve_within, validate_input_source
from app.modules.streaming.media.telemetry import ManifestMetrics, ProcessingMetrics, TelemetrySink


def _child_cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(usage.ru_utime + usage.ru_stime)


class MediaPipeline:
    def __init__(
        self,
        *,
        workspace_root: Path,
        output_root: Path,
        ffmpeg: FFmpegCommandBuilder,
        ffprobe: FFprobeCommandBuilder,
        runner: AsyncProcessRunner,
        telemetry: TelemetrySink,
        worker_id: str,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.output_root = output_root.resolve()
        self.ffmpeg = ffmpeg
        self.probe = MediaProbe(ffprobe, runner)
        self.runner = runner
        self.telemetry = telemetry
        self.worker_id = worker_id

    def job_workspace(self, job_id: UUID) -> Path:
        workspace = resolve_within(self.workspace_root, str(job_id))
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    async def transcode(
        self,
        payload: TranscodeTaskPayload,
        *,
        encoder: EncoderKind,
        queue: str,
    ) -> dict[str, object]:
        started = monotonic()
        cpu_started = _child_cpu_seconds()
        queue_wait = max(0.0, (datetime.now(UTC) - payload.enqueued_at).total_seconds())
        workspace = self.job_workspace(payload.job_id)
        source = validate_input_source(payload.input_source, local_root=self.workspace_root)
        probe_result = await self.probe.inspect(source, local_root=self.workspace_root)
        latest = FFmpegProgress()

        async def on_progress(progress: FFmpegProgress) -> None:
            nonlocal latest
            latest = progress
            await self.telemetry.progress(payload.job_id, queue, progress)

        for rendition in payload.renditions:
            rendition_dir = workspace / f"stream_{rendition}"
            rendition_dir.mkdir(parents=True, exist_ok=True)
        hls_command = self.ffmpeg.hls_ladder(
            input_source=source,
            output_directory=workspace,
            renditions=payload.renditions,
            encoder=encoder,
            live=payload.live,
        )
        dash_command = self.ffmpeg.dash(
                input_source=source,
                output_directory=workspace,
                renditions=payload.renditions,
                encoder=encoder,
                live=payload.live,
        )
        await asyncio.gather(
            self.runner.run(
                hls_command,
                timeout_seconds=payload.timeout_seconds,
                progress_callback=on_progress,
            ),
            self.runner.run(
                dash_command,
                timeout_seconds=payload.timeout_seconds,
                progress_callback=on_progress,
            ),
        )
        duration = monotonic() - started
        cpu_seconds = max(0.0, _child_cpu_seconds() - cpu_started)
        cpu_usage_percent = (cpu_seconds / duration * 100.0) if duration > 0 else 0.0
        metrics = ProcessingMetrics(
            job_id=payload.job_id,
            queue=queue,
            processing_duration_seconds=duration,
            queue_wait_time_seconds=queue_wait,
            encoding_fps=latest.fps,
            encoding_speed_factor=latest.speed_factor,
            cpu_usage_percent=cpu_usage_percent,
            dropped_frames=latest.dropped_frames or 0,
            observed_at=datetime.now(UTC),
        )
        await self.telemetry.completed(metrics)
        return {
            "workspace": str(workspace),
            "probe": probe_summary(probe_result),
            "processing_duration_seconds": duration,
            "queue_wait_time_seconds": queue_wait,
            "cpu_usage_percent": cpu_usage_percent,
        }

    async def package_and_publish(self, payload: ManifestTaskPayload) -> dict[str, object]:
        workspace = resolve_within(self.workspace_root, payload.workspace)
        master = build_hls_master(payload.renditions)
        master_path = workspace / "master.m3u8"
        master_path.write_text(master, encoding="utf-8")
        validate_hls_master(master, workspace)

        dash_source = workspace / "manifest.mpd"
        if not dash_source.is_file():
            raise FileNotFoundError("DASH MPD was not produced")
        dash_document = dash_source.read_text(encoding="utf-8")
        validate_dash_mpd(dash_document, workspace)
        published = AtomicPublisher(self.output_root).publish(workspace, payload.output_prefix)
        published_master = published / "master.m3u8"
        manifest_freshness = max(
            0.0,
            datetime.now(UTC).timestamp() - published_master.stat().st_mtime,
        )
        await self.telemetry.manifest(
            ManifestMetrics(
                job_id=payload.job_id,
                queue="manifest",
                manifest_freshness_seconds=manifest_freshness,
                observed_at=datetime.now(UTC),
            )
        )
        return {
            "published_path": str(published),
            "hls": "master.m3u8",
            "dash": "manifest.mpd",
            "manifest_freshness_seconds": manifest_freshness,
        }

    async def thumbnails(self, payload: ThumbnailTaskPayload, *, queue: str = "thumbnail") -> dict[str, object]:
        workspace = resolve_within(self.workspace_root, payload.workspace)
        source = validate_input_source(payload.input_source, local_root=self.workspace_root)
        thumbnail_dir = workspace / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[str] = []
        for kind in payload.kinds:
            if kind == "timeline":
                output = thumbnail_dir / "timeline_%06d.jpg"
            else:
                output = thumbnail_dir / f"{kind}.jpg"
            await self.runner.run(
                self.ffmpeg.thumbnail(
                    input_source=source,
                    output=output,
                    kind=kind,
                    interval_seconds=payload.interval_seconds,
                ),
                timeout_seconds=payload.timeout_seconds,
            )
            outputs.append(str(output.relative_to(workspace)))
        timeline_images = tuple(
            str(item.relative_to(thumbnail_dir)) for item in sorted(thumbnail_dir.glob("timeline_*.jpg"))
        )
        if timeline_images:
            vtt = build_timeline_vtt(timeline_images, interval_seconds=payload.interval_seconds)
            (thumbnail_dir / "timeline.vtt").write_text(vtt, encoding="utf-8")
            outputs.append("thumbnails/timeline.vtt")
        await self.telemetry.worker_health(self.worker_id, queue, True)
        return {"workspace": str(workspace), "outputs": outputs}

    def quarantine(self, job_id: UUID) -> Path | None:
        workspace = resolve_within(self.workspace_root, str(job_id))
        if not workspace.exists():
            return None
        quarantine_root = resolve_within(self.workspace_root, "quarantine")
        quarantine_root.mkdir(parents=True, exist_ok=True)
        destination = quarantine_root / str(job_id)
        if destination.exists():
            shutil.rmtree(destination)
        return Path(shutil.move(str(workspace), destination))

    def cleanup(self, job_id: UUID) -> None:
        shutil.rmtree(resolve_within(self.workspace_root, str(job_id)), ignore_errors=True)


__all__ = ["MediaPipeline"]

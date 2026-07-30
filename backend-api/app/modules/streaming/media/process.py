"""Async FFmpeg/FFprobe lifecycle management with bounded termination."""

import asyncio
import os
import re
import signal
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Self

from app.modules.streaming.media.security import redact_media_text


@dataclass(frozen=True, slots=True)
class FFmpegProgress:
    frame: int | None = None
    fps: float | None = None
    size_kb: int | None = None
    time_seconds: float | None = None
    bitrate_kbps: float | None = None
    speed_factor: float | None = None
    dropped_frames: int | None = None


@dataclass(frozen=True, slots=True)
class ProcessResult:
    command: tuple[str, ...]
    stdout: str
    stderr_tail: tuple[str, ...]
    returncode: int
    duration_seconds: float


class MediaProcessError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None, stderr_tail: tuple[str, ...]) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr_tail = stderr_tail


class MediaProcessTimeout(MediaProcessError):
    pass


class FFmpegExecutionError(MediaProcessError):
    pass


class FFmpegProgressParser:
    _patterns = {
        "frame": re.compile(r"\bframe=\s*(\d+)"),
        "fps": re.compile(r"\bfps=\s*([\d.]+)"),
        "size_kb": re.compile(r"\bsize=\s*(\d+)kB"),
        "time": re.compile(r"\btime=(\d+):(\d+):(\d+(?:\.\d+)?)"),
        "bitrate": re.compile(r"\bbitrate=\s*([\d.]+)kbits/s"),
        "speed": re.compile(r"\bspeed=\s*([\d.]+)x"),
        "drop": re.compile(r"\b(?:drop|drop_frames)=\s*(\d+)"),
    }

    def parse(self, line: str) -> FFmpegProgress | None:
        values: dict[str, int | float | None] = {
            "frame": self._integer("frame", line),
            "fps": self._decimal("fps", line),
            "size_kb": self._integer("size_kb", line),
            "time_seconds": self._time(line),
            "bitrate_kbps": self._decimal("bitrate", line),
            "speed_factor": self._decimal("speed", line),
            "dropped_frames": self._integer("drop", line),
        }
        if all(value is None for value in values.values()):
            return None
        return FFmpegProgress(**values)  # type: ignore[arg-type]

    def _integer(self, name: str, line: str) -> int | None:
        match = self._patterns[name].search(line)
        return int(match.group(1)) if match else None

    def _decimal(self, name: str, line: str) -> float | None:
        match = self._patterns[name].search(line)
        return float(match.group(1)) if match else None

    def _time(self, line: str) -> float | None:
        match = self._patterns["time"].search(line)
        if not match:
            return None
        return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


ProgressCallback = Callable[[FFmpegProgress], Awaitable[None]]


class AsyncProcessRunner:
    def __init__(self, *, terminate_grace_seconds: float = 3.0, stderr_tail_lines: int = 50) -> None:
        self.terminate_grace_seconds = terminate_grace_seconds
        self.stderr_tail_lines = stderr_tail_lines

    async def run(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float,
        progress_callback: ProgressCallback | None = None,
    ) -> ProcessResult:
        if not command or any("\x00" in argument for argument in command):
            raise ValueError("command arguments are invalid")
        loop = asyncio.get_running_loop()
        started = loop.time()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_reader = process.stdout
        stderr_reader = process.stderr
        stderr_tail: deque[str] = deque(maxlen=self.stderr_tail_lines)
        parser = FFmpegProgressParser()

        async def read_stderr() -> None:
            async for raw_line in stderr_reader:
                line = redact_media_text(raw_line.decode("utf-8", errors="replace").rstrip())
                stderr_tail.append(line)
                progress = parser.parse(line)
                if progress is not None and progress_callback is not None:
                    await progress_callback(progress)

        stderr_task = asyncio.ensure_future(read_stderr())
        stdout_task = asyncio.ensure_future(stdout_reader.read())
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError as exc:
            await self._terminate(process)
            await stderr_task
            await stdout_task
            raise MediaProcessTimeout(
                f"media process exceeded {timeout_seconds:.3f} seconds",
                returncode=process.returncode,
                stderr_tail=tuple(stderr_tail),
            ) from exc
        except asyncio.CancelledError:
            await self._terminate(process)
            await stderr_task
            await stdout_task
            raise
        await stderr_task
        stdout = (await stdout_task).decode("utf-8", errors="replace")
        duration = loop.time() - started
        result = ProcessResult(
            command=command,
            stdout=stdout,
            stderr_tail=tuple(stderr_tail),
            returncode=process.returncode or 0,
            duration_seconds=duration,
        )
        if process.returncode != 0:
            raise FFmpegExecutionError(
                f"media process exited with code {process.returncode}",
                returncode=process.returncode,
                stderr_tail=result.stderr_tail,
            )
        return result

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=self.terminate_grace_seconds)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    @classmethod
    def default(cls) -> Self:
        from app.core.config import settings

        return cls(terminate_grace_seconds=settings.FFMPEG_TERMINATE_GRACE_SECONDS)


__all__ = [
    "AsyncProcessRunner",
    "FFmpegExecutionError",
    "FFmpegProgress",
    "FFmpegProgressParser",
    "MediaProcessError",
    "MediaProcessTimeout",
    "ProcessResult",
]

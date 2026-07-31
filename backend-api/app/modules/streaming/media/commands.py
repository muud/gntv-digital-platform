"""Safe argument-list builders for approved FFmpeg operations."""

from pathlib import Path
from typing import Literal

from app.modules.streaming.media.profiles import (
    APPROVED_RENDITIONS,
    SEGMENT_DURATION_SECONDS,
    RenditionName,
    RenditionProfile,
)

EncoderKind = Literal["cpu", "accelerated"]


def _scale_filter(profile: RenditionProfile, encoder: EncoderKind = "cpu") -> str:
    if encoder == "accelerated":
        return (
            f"scale_cuda={profile.width}:{profile.height}:force_original_aspect_ratio=decrease:"
            f"format=yuv420p,pad_cuda={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2"
        )
    return (
        f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=decrease,"
        f"pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


def _video_encoder_args(profile: RenditionProfile, encoder: EncoderKind, index: int | None = None) -> list[str]:
    suffix = "" if index is None else f":{index}"
    if encoder == "cpu":
        codec_args = [f"-c:v{suffix}", "libx264", f"-preset{suffix}", "medium"]
    else:
        codec_args = [f"-c:v{suffix}", "h264_nvenc", f"-preset{suffix}", "p4"]
    return [
        *codec_args,
        f"-profile:v{suffix}",
        profile.codec_profile,
        f"-level:v{suffix}",
        profile.codec_level,
        f"-pix_fmt{suffix}",
        "yuv420p",
        f"-r{suffix}",
        profile.frame_rate,
        f"-b:v{suffix}",
        f"{profile.video_bitrate_kbps}k",
        f"-maxrate:v{suffix}",
        f"{profile.max_video_bitrate_kbps}k",
        f"-bufsize:v{suffix}",
        f"{profile.buffer_kbps}k",
        f"-g{suffix}",
        str(profile.gop),
        f"-keyint_min{suffix}",
        str(profile.gop),
        f"-sc_threshold{suffix}",
        "0",
        f"-force_key_frames{suffix}",
        "expr:gte(t,n_forced*2)",
    ]


class FFmpegCommandBuilder:
    def __init__(self, binary: str = "ffmpeg") -> None:
        if not binary or any(character in binary for character in "\x00\r\n"):
            raise ValueError("invalid FFmpeg binary")
        self.binary = binary

    def hls_variant(
        self,
        *,
        input_source: str,
        output_directory: Path,
        rendition: RenditionName,
        encoder: EncoderKind,
        live: bool,
    ) -> tuple[str, ...]:
        profile = APPROVED_RENDITIONS[rendition]
        playlist = output_directory / "index.m3u8"
        segment_pattern = output_directory / "data_%06d.ts"
        return (
            self.binary,
            "-hide_banner",
            "-nostdin",
            "-y",
            *(
                ("-hwaccel", "cuda", "-hwaccel_output_format", "cuda")
                if encoder == "accelerated"
                else ()
            ),
            "-i",
            input_source,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            _scale_filter(profile, encoder),
            *_video_encoder_args(profile, encoder),
            "-c:a",
            "aac",
            "-b:a",
            f"{profile.audio_bitrate_kbps}k",
            "-ar",
            str(profile.audio_sample_rate),
            "-ac",
            "2",
            "-f",
            "hls",
            "-hls_time",
            str(SEGMENT_DURATION_SECONDS),
            "-hls_playlist_type",
            "event" if live else "vod",
            "-hls_flags",
            "independent_segments+temp_file",
            "-hls_segment_filename",
            str(segment_pattern),
            str(playlist),
        )

    def dash(
        self,
        *,
        input_source: str,
        output_directory: Path,
        renditions: tuple[RenditionName, ...],
        encoder: EncoderKind,
        live: bool,
    ) -> tuple[str, ...]:
        split_labels = "".join(f"[v{index}]" for index in range(len(renditions)))
        filters = [f"[0:v:0]split={len(renditions)}{split_labels}"]
        for index, name in enumerate(renditions):
            filters.append(
                f"[v{index}]{_scale_filter(APPROVED_RENDITIONS[name], encoder)}[outv{index}]"
            )
        args: list[str] = [
            self.binary,
            "-hide_banner",
            "-nostdin",
            "-y",
            *(
                ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
                if encoder == "accelerated"
                else []
            ),
            "-i",
            input_source,
            "-filter_complex",
            ";".join(filters),
        ]
        for index, name in enumerate(renditions):
            profile = APPROVED_RENDITIONS[name]
            args.extend(["-map", f"[outv{index}]", "-map", "0:a:0?"])
            args.extend(_video_encoder_args(profile, encoder, index))
            args.extend(
                [
                    f"-c:a:{index}",
                    "aac",
                    f"-b:a:{index}",
                    f"{profile.audio_bitrate_kbps}k",
                    f"-ar:a:{index}",
                    str(profile.audio_sample_rate),
                    f"-ac:a:{index}",
                    "2",
                ]
            )
        args.extend(
            [
                "-f",
                "dash",
                "-seg_duration",
                str(SEGMENT_DURATION_SECONDS),
                "-use_template",
                "1",
                "-use_timeline",
                "1",
                "-adaptation_sets",
                "id=0,streams=v id=1,streams=a",
                "-init_seg_name",
                "$RepresentationID$/init.mp4",
                "-media_seg_name",
                "$RepresentationID$/media-$Number$.m4s",
                "-window_size",
                "5" if live else "0",
                "-extra_window_size",
                "5" if live else "0",
                str(output_directory / "manifest.mpd"),
            ]
        )
        return tuple(args)

    def hls_ladder(
        self,
        *,
        input_source: str,
        output_directory: Path,
        renditions: tuple[RenditionName, ...],
        encoder: EncoderKind,
        live: bool,
    ) -> tuple[str, ...]:
        split_labels = "".join(f"[hlsv{index}]" for index in range(len(renditions)))
        filters = [f"[0:v:0]split={len(renditions)}{split_labels}"]
        for index, name in enumerate(renditions):
            filters.append(
                f"[hlsv{index}]{_scale_filter(APPROVED_RENDITIONS[name], encoder)}[hlsout{index}]"
            )
        args: list[str] = [
            self.binary,
            "-hide_banner",
            "-nostdin",
            "-y",
            *(
                ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
                if encoder == "accelerated"
                else []
            ),
            "-i",
            input_source,
            "-filter_complex",
            ";".join(filters),
        ]
        for index, name in enumerate(renditions):
            profile = APPROVED_RENDITIONS[name]
            rendition_directory = output_directory / f"stream_{name}"
            args.extend(
                [
                    "-map",
                    f"[hlsout{index}]",
                    "-map",
                    "0:a:0",
                    *_video_encoder_args(profile, encoder),
                    "-c:a",
                    "aac",
                    "-b:a",
                    f"{profile.audio_bitrate_kbps}k",
                    "-ar",
                    str(profile.audio_sample_rate),
                    "-ac",
                    "2",
                    "-f",
                    "hls",
                    "-hls_time",
                    str(SEGMENT_DURATION_SECONDS),
                    "-hls_playlist_type",
                    "event" if live else "vod",
                    "-hls_flags",
                    "independent_segments+temp_file",
                    "-hls_segment_filename",
                    str(rendition_directory / "data_%06d.ts"),
                    str(rendition_directory / "index.m3u8"),
                ]
            )
        return tuple(args)

    def thumbnail(
        self,
        *,
        input_source: str,
        output: Path,
        kind: Literal["poster", "preview", "timeline"],
        interval_seconds: int = 10,
    ) -> tuple[str, ...]:
        common = [self.binary, "-hide_banner", "-nostdin", "-y", "-i", input_source]
        if kind == "poster":
            return tuple([*common, "-ss", "1", "-frames:v", "1", "-vf", "scale=1280:-2", str(output)])
        if kind == "preview":
            return tuple([*common, "-ss", "5", "-frames:v", "1", "-vf", "scale=640:-2", str(output)])
        return tuple(
            [
                *common,
                "-vf",
                f"fps=1/{interval_seconds},scale=320:-2",
                "-q:v",
                "3",
                str(output),
            ]
        )


class FFprobeCommandBuilder:
    def __init__(self, binary: str = "ffprobe") -> None:
        if not binary or any(character in binary for character in "\x00\r\n"):
            raise ValueError("invalid FFprobe binary")
        self.binary = binary

    def inspect(self, input_source: str) -> tuple[str, ...]:
        return (
            self.binary,
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,width,height,pix_fmt,"
            "avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            input_source,
        )


__all__ = ["EncoderKind", "FFmpegCommandBuilder", "FFprobeCommandBuilder"]

"""Provider-neutral atomic publication to a configured local media root."""

import os
import shutil
from pathlib import Path
from uuid import uuid4

from app.modules.streaming.media.manifests import validate_dash_mpd, validate_hls_master
from app.modules.streaming.media.security import resolve_within, safe_relative_path


class AtomicPublisher:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    def publish(self, source: Path, output_prefix: str) -> Path:
        source = source.resolve()
        if not source.is_dir():
            raise FileNotFoundError("publication source does not exist")
        relative = safe_relative_path(output_prefix)
        destination = resolve_within(self.output_root, relative)
        if destination.exists():
            raise FileExistsError("publication generation already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.staging-{uuid4().hex}"
        staging.mkdir()
        try:
            manifests = {"master.m3u8", "manifest.mpd"}
            variant_playlists: list[Path] = []
            final_manifests: list[Path] = []
            for item in sorted(source.rglob("*")):
                if not item.is_file():
                    continue
                relative_item = item.relative_to(source)
                if item.name in manifests:
                    final_manifests.append(relative_item)
                elif item.suffix == ".m3u8":
                    variant_playlists.append(relative_item)
                else:
                    target = staging / relative_item
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
            for relative_item in [*variant_playlists, *final_manifests]:
                target = staging / relative_item
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative_item, target)
            hls = staging / "master.m3u8"
            dash = staging / "manifest.mpd"
            if hls.is_file():
                validate_hls_master(hls.read_text(encoding="utf-8"), staging)
            if dash.is_file():
                validate_dash_mpd(dash.read_text(encoding="utf-8"), staging)
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return destination


__all__ = ["AtomicPublisher"]

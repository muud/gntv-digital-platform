"""Processing extension points; FFmpeg work belongs to the later video module."""

from typing import Protocol
from uuid import UUID


class MetadataExtractor(Protocol):
    def extract(self, asset_id: UUID) -> dict[str, object]: ...


class AntivirusScanner(Protocol):
    def scan(self, asset_id: UUID) -> bool: ...


class MediaProcessingDispatcher(Protocol):
    def dispatch_metadata_extraction(self, asset_id: UUID) -> None: ...


__all__ = ["AntivirusScanner", "MediaProcessingDispatcher", "MetadataExtractor"]

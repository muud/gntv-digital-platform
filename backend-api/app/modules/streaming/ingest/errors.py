"""Stable ingest-domain errors suitable for safe API responses."""


class IngestError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


__all__ = ["IngestError"]

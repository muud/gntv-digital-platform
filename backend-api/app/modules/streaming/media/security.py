"""Input-source and workspace validation for isolated media workers."""

import ipaddress
import re
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class UnsafeMediaSourceError(ValueError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"(?i)(?:key|token|passphrase|signature)=([^&\s]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
)


def redact_media_text(value: str) -> str:
    redacted = _SECRET_PATTERNS[0].sub(lambda match: match.group(0).split("=", 1)[0] + "=[REDACTED]", value)
    return _SECRET_PATTERNS[1].sub("Bearer [REDACTED]", redacted)


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeMediaSourceError("path must be a normalized relative path")
    return path


def resolve_within(root: Path, value: str | Path) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise UnsafeMediaSourceError("path escapes the configured media root")
    return candidate


def _blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    metadata = ipaddress.ip_address("100.100.100.200")
    return bool(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address == metadata
    )


def validate_input_source(
    source: str,
    *,
    local_root: Path,
    resolver: Callable[..., list[Any]] | None = None,
) -> str:
    if "\x00" in source or "\n" in source or "\r" in source:
        raise UnsafeMediaSourceError("input source contains control characters")
    parsed = urlsplit(source)
    if parsed.scheme == "":
        path = resolve_within(local_root, source)
        if not path.is_file():
            raise UnsafeMediaSourceError("local input does not exist")
        return str(path)
    if parsed.scheme not in {"rtmp", "rtmps", "srt"}:
        raise UnsafeMediaSourceError("input protocol is not allowed")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeMediaSourceError("input URL authority is invalid")
    resolve_host = resolver or socket.getaddrinfo
    try:
        addresses = resolve_host(parsed.hostname, parsed.port or 0, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeMediaSourceError("input host could not be resolved") from exc
    for result in addresses:
        sockaddr = result[4]
        if not isinstance(sockaddr, tuple) or not sockaddr:
            raise UnsafeMediaSourceError("input host resolution is invalid")
        address = ipaddress.ip_address(str(sockaddr[0]))
        if _blocked_address(address):
            raise UnsafeMediaSourceError("input host resolves to a restricted address")
    return source


__all__ = [
    "UnsafeMediaSourceError",
    "redact_media_text",
    "resolve_within",
    "safe_relative_path",
    "validate_input_source",
]

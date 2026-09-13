"""SSRF protection and outbound URL validation utilities."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

FORBIDDEN_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "169.254.169.254",
}

SAFE_PORTS = {80, 443, 8080, 8443}


class SSRFValidationError(ValueError):
    """Raised when an outbound URL violates SSRF safety policies."""

    pass


def is_ip_private_or_restricted(ip_str: str) -> bool:
    """Check if an IP string belongs to private, loopback, link-local, or metadata ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
        if ip in ipaddress.ip_network("169.254.0.0/16"):
            return True
        if ip.version == 6 and (
            ip in ipaddress.ip_network("fc00::/7")
            or ip in ipaddress.ip_network("fe80::/10")
        ):
            return True
        return False
    except ValueError:
        return True


def validate_outbound_url(url: str, allow_private_for_tests: bool = False) -> str:
    """Validate that an outbound webhook URL is safe against SSRF attacks."""
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL must be a non-empty string.")

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise SSRFValidationError(
            f"Invalid scheme '{parsed.scheme}'. Outbound webhooks require HTTPS."
        )

    if not parsed.netloc:
        raise SSRFValidationError("URL is missing a valid network location (host).")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL is missing a valid hostname.")

    hostname_lower = hostname.lower()

    if hostname_lower in FORBIDDEN_HOSTS:
        raise SSRFValidationError(
            f"Access to host '{hostname}' is forbidden by SSRF security policy."
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise SSRFValidationError(f"Invalid destination port: {exc}") from exc
    if port is not None and port not in SAFE_PORTS:
        raise SSRFValidationError(
            f"Port {port} is not permitted for outbound webhooks."
        )

    try:
        ip = ipaddress.ip_address(hostname_lower)
        if not allow_private_for_tests and is_ip_private_or_restricted(str(ip)):
            raise SSRFValidationError(
                f"Destination IP '{ip}' is in a private or restricted network range."
            )
        return url
    except ValueError:
        pass

    if allow_private_for_tests:
        return url

    try:
        resolved = socket.getaddrinfo(
            hostname_lower, port or 443, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        for entry in resolved:
            sockaddr = entry[4]
            ip_str = str(sockaddr[0])
            if is_ip_private_or_restricted(ip_str):
                raise SSRFValidationError(
                    f"Host '{hostname}' resolves to restricted IP '{ip_str}'."
                )
    except (socket.gaierror, UnicodeError) as e:
        raise SSRFValidationError(f"Could not resolve host '{hostname}': {e}") from e

    return url

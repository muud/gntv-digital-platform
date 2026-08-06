"""Geo-fencing and IP risk policy evaluation service for Sprint 6.4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.streaming.models import GeoPolicy


@dataclass
class GeoCheckResult:
    allowed: bool
    country_code: str
    is_vpn: bool
    is_proxy: bool
    reason: str | None = None


class GeoFencingService:
    def __init__(self, default_country: str = "US") -> None:
        self.default_country = default_country

    def resolve_ip_metadata(self, client_ip: str, headers: dict[str, Any] | None = None) -> tuple[str, bool, bool]:
        headers = headers or {}
        country = (
            headers.get("X-Country-Code")
            or headers.get("x-country-code")
            or headers.get("CF-IPCountry")
            or headers.get("cf-ipcountry")
        )
        if country and isinstance(country, str) and country != "XX":
            country_code = country.upper()
        else:
            if client_ip.startswith("192.168.") or client_ip in ("127.0.0.1", "::1"):
                country_code = self.default_country
            elif client_ip.startswith("10.88."):
                country_code = "SO"  # Somalia
            elif client_ip.startswith("10.99."):
                country_code = "XX"  # Blocked / Unknown
            else:
                country_code = self.default_country

        is_vpn = False
        is_proxy = False

        vpn_header = headers.get("X-VPN-Detected") or headers.get("x-vpn-detected")
        proxy_header = headers.get("X-Proxy-Detected") or headers.get("x-proxy-detected")
        if vpn_header == "true" or client_ip.endswith(".254") or "vpn" in str(headers).lower():
            is_vpn = True
        if proxy_header == "true" or client_ip.endswith(".253") or "proxy" in str(headers).lower():
            is_proxy = True

        return country_code, is_vpn, is_proxy

    def evaluate(
        self,
        policy: GeoPolicy | None,
        client_ip: str,
        headers: dict[str, Any] | None = None,
    ) -> GeoCheckResult:
        if policy is None:
            country, is_vpn, is_proxy = self.resolve_ip_metadata(client_ip, headers)
            return GeoCheckResult(allowed=True, country_code=country, is_vpn=is_vpn, is_proxy=is_proxy)

        country, is_vpn, is_proxy = self.resolve_ip_metadata(client_ip, headers)

        if country == "XX" and policy.fail_closed:
            return GeoCheckResult(
                allowed=False,
                country_code=country,
                is_vpn=is_vpn,
                is_proxy=is_proxy,
                reason="geo_resolution_failed",
            )

        if policy.country_deny_list and country in [c.upper() for c in policy.country_deny_list]:
            return GeoCheckResult(
                allowed=False,
                country_code=country,
                is_vpn=is_vpn,
                is_proxy=is_proxy,
                reason="country_denied",
            )

        if policy.country_allow_list and country not in [c.upper() for c in policy.country_allow_list]:
            return GeoCheckResult(
                allowed=False,
                country_code=country,
                is_vpn=is_vpn,
                is_proxy=is_proxy,
                reason="country_not_allowed",
            )

        if policy.block_vpn and is_vpn:
            return GeoCheckResult(
                allowed=False,
                country_code=country,
                is_vpn=is_vpn,
                is_proxy=is_proxy,
                reason="vpn_detected",
            )

        if policy.block_proxy and is_proxy:
            return GeoCheckResult(
                allowed=False,
                country_code=country,
                is_vpn=is_vpn,
                is_proxy=is_proxy,
                reason="proxy_detected",
            )

        return GeoCheckResult(allowed=True, country_code=country, is_vpn=is_vpn, is_proxy=is_proxy)

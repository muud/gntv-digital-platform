"""Provider-neutral interfaces and mock implementations for notifications and backups."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
import hashlib
import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class NotificationProvider(ABC):
    """Abstract provider for reliability notifications and alerts."""

    @abstractmethod
    def send_alert(
        self,
        component: str,
        severity: str,
        message: str,
        correlation_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch an operational alert to on-call or monitoring channels."""
        raise NotImplementedError


class MockInternalNotificationProvider(NotificationProvider):
    """Safe, internal-only mock notification provider logging alerts."""

    def __init__(self) -> None:
        self.sent_alerts: list[dict[str, Any]] = []

    def send_alert(
        self,
        component: str,
        severity: str,
        message: str,
        correlation_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        record = {
            "component": component,
            "severity": severity,
            "message": message,
            "correlation_id": correlation_id,
            "payload": payload or {},
            "dispatched_at": now.isoformat(),
            "status": "DELIVERED_MOCK",
        }
        self.sent_alerts.append(record)
        logger.info(
            "Reliability Alert [%s] for %s: %s (correlation_id=%s)",
            severity,
            component,
            message,
            correlation_id,
        )
        return record


class BackupProvider(ABC):
    """Abstract provider for platform backup inspection and verification."""

    @abstractmethod
    def verify_backup(
        self,
        backup_id: UUID,
        resource_type: str,
        logical_identifier: str,
        checksum: str | None = None,
    ) -> dict[str, Any]:
        """Verify checksum, accessibility, and retention status of a backup."""
        raise NotImplementedError


class MockBackupProvider(BackupProvider):
    """Safe mock backup provider for verification and metadata checks."""

    def verify_backup(
        self,
        backup_id: UUID,
        resource_type: str,
        logical_identifier: str,
        checksum: str | None = None,
    ) -> dict[str, Any]:
        expected_checksum = checksum or hashlib.sha256(
            f"{backup_id}:{resource_type}:{logical_identifier}".encode()
        ).hexdigest()
        return {
            "verified": True,
            "checksum": expected_checksum,
            "size_bytes": 1024 * 1024 * 50,  # 50MB simulated
            "verified_at": datetime.now(UTC).isoformat(),
            "details": f"Mock backup verification passed for {resource_type}:{logical_identifier}",
        }


# Global default instances
default_notification_provider: NotificationProvider = MockInternalNotificationProvider()
default_backup_provider: BackupProvider = MockBackupProvider()

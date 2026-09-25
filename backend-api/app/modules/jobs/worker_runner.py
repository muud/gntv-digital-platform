"""Dedicated long-running daemon runner for WorkerService."""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
import time
from typing import Any

from app.core.database import SessionLocal
from app.modules.jobs.worker import WorkerService

logger = logging.getLogger(__name__)


class WorkerDaemon:
    """Manages the lifecycle of a long-running WorkerService polling loop."""

    def __init__(
        self,
        worker_id: str | None = None,
        queues: list[str] | None = None,
        concurrency: int = 4,
        lease_duration_seconds: int = 60,
        poll_interval: float = 2.0,
        metadata: dict[str, Any] | None = None,
        session_factory: Any = SessionLocal,
    ) -> None:
        self.worker_id = (
            worker_id
            or os.environ.get("GNTV_WORKER_ID")
            or f"worker-{socket.gethostname()}-{os.getpid()}"
        )
        raw_queues = (
            queues
            if queues is not None
            else os.environ.get("GNTV_WORKER_QUEUES", "default").split(",")
        )
        self.queues = [q.strip() for q in raw_queues if q.strip()] or ["default"]
        self.concurrency = max(
            1, int(os.environ.get("GNTV_WORKER_CONCURRENCY", str(concurrency)))
        )
        self.lease_duration_seconds = max(
            1,
            int(
                os.environ.get(
                    "GNTV_WORKER_LEASE_SECONDS", str(lease_duration_seconds)
                )
            ),
        )
        self.poll_interval = max(
            0.05,
            float(os.environ.get("GNTV_WORKER_POLL_INTERVAL", str(poll_interval))),
        )
        self.metadata = metadata
        self.session_factory = session_factory
        self.stop_event = threading.Event()
        self.is_registered = False

    def request_stop(self, *args: Any) -> None:
        logger.info("WorkerDaemon[%s] stop requested", self.worker_id)
        self.stop_event.set()

    def run(self, max_loops: int | None = None) -> None:
        """Run worker polling loop until stop_event is set or max_loops reached."""
        logger.info(
            "WorkerDaemon[%s] starting (queues=%s, concurrency=%d, poll=%.2fs)",
            self.worker_id,
            self.queues,
            self.concurrency,
            self.poll_interval,
        )
        try:
            with self.session_factory() as db:
                service = WorkerService(
                    db=db,
                    worker_id=self.worker_id,
                    queues=self.queues,
                    concurrency=self.concurrency,
                    lease_duration_seconds=self.lease_duration_seconds,
                    metadata=self.metadata,
                )
                service.register()
                db.commit()
                self.is_registered = True
        except Exception as exc:
            logger.exception(
                "WorkerDaemon[%s] failed to register: %s", self.worker_id, exc
            )
            raise

        loops = 0
        last_heartbeat = time.monotonic()
        while not self.stop_event.is_set():
            if max_loops is not None and loops >= max_loops:
                break
            loops += 1
            claimed_count = 0
            try:
                with self.session_factory() as db:
                    service = WorkerService(
                        db=db,
                        worker_id=self.worker_id,
                        queues=self.queues,
                        concurrency=self.concurrency,
                        lease_duration_seconds=self.lease_duration_seconds,
                        metadata=self.metadata,
                    )
                    now_mono = time.monotonic()
                    if now_mono - last_heartbeat >= 15.0:
                        service.heartbeat()
                        last_heartbeat = now_mono
                    claimed = service.process_once()
                    db.commit()
                    claimed_count = len(claimed)
            except Exception as exc:
                logger.error(
                    "WorkerDaemon[%s] error during processing cycle: %s",
                    self.worker_id,
                    exc,
                )

            if claimed_count == 0 and not self.stop_event.is_set():
                self.stop_event.wait(self.poll_interval)

        self._shutdown()

    def _shutdown(self) -> None:
        if not self.is_registered:
            return
        logger.info("WorkerDaemon[%s] shutting down", self.worker_id)
        try:
            with self.session_factory() as db:
                service = WorkerService(
                    db=db,
                    worker_id=self.worker_id,
                    queues=self.queues,
                    concurrency=self.concurrency,
                    lease_duration_seconds=self.lease_duration_seconds,
                    metadata=self.metadata,
                )
                service.drain()
                service.shutdown()
                db.commit()
        except Exception as exc:
            logger.error(
                "WorkerDaemon[%s] error during shutdown: %s", self.worker_id, exc
            )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    daemon = WorkerDaemon()

    def _on_signal(sig: int, frame: Any) -> None:
        daemon.request_stop()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        daemon.run()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()

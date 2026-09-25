"""Dedicated long-running daemon runner for SchedulerService."""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
from typing import Any

from app.core.database import SessionLocal
from app.modules.jobs.scheduler import SchedulerService

logger = logging.getLogger(__name__)


class SchedulerDaemon:
    """Manages the lifecycle of a long-running SchedulerService tick loop."""

    def __init__(
        self,
        scheduler_id: str | None = None,
        claim_seconds: int = 30,
        interval: float = 5.0,
        session_factory: Any = SessionLocal,
    ) -> None:
        self.scheduler_id = (
            scheduler_id
            or os.environ.get("GNTV_SCHEDULER_ID")
            or f"scheduler-{socket.gethostname()}-{os.getpid()}"
        )
        self.claim_seconds = max(
            1,
            int(
                os.environ.get(
                    "GNTV_SCHEDULER_CLAIM_SECONDS", str(claim_seconds)
                )
            ),
        )
        self.interval = max(
            0.1,
            float(os.environ.get("GNTV_SCHEDULER_INTERVAL", str(interval))),
        )
        self.session_factory = session_factory
        self.stop_event = threading.Event()

    def request_stop(self, *args: Any) -> None:
        logger.info("SchedulerDaemon[%s] stop requested", self.scheduler_id)
        self.stop_event.set()

    def run(self, max_loops: int | None = None) -> None:
        """Run scheduler tick loop until stop_event is set or max_loops reached."""
        logger.info(
            "SchedulerDaemon[%s] starting (claim_seconds=%d, interval=%.2fs)",
            self.scheduler_id,
            self.claim_seconds,
            self.interval,
        )
        loops = 0
        while not self.stop_event.is_set():
            if max_loops is not None and loops >= max_loops:
                break
            loops += 1
            try:
                with self.session_factory() as db:
                    service = SchedulerService(
                        db=db,
                        scheduler_id=self.scheduler_id,
                        claim_seconds=self.claim_seconds,
                    )
                    emitted = service.tick()
                    db.commit()
                    if emitted:
                        logger.info(
                            "SchedulerDaemon[%s] emitted %d due jobs",
                            self.scheduler_id,
                            len(emitted),
                        )
            except Exception as exc:
                logger.error(
                    "SchedulerDaemon[%s] error during tick cycle: %s",
                    self.scheduler_id,
                    exc,
                )

            if not self.stop_event.is_set():
                self.stop_event.wait(self.interval)

        logger.info("SchedulerDaemon[%s] stopped cleanly", self.scheduler_id)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    daemon = SchedulerDaemon()

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

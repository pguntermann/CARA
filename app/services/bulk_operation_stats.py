"""Shared types for bulk database operations (tags, replace, clean PGN)."""

from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional, Any
import threading


class BulkProcessingOutcome(str, Enum):
    """Per-game outcome from bulk worker processes (picklable for ProcessPoolExecutor)."""

    UPDATED = "updated"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class BulkOperationStats:
    """Statistics returned by bulk operations on a database."""

    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None


# completed, total, message, updated, failed, skipped
BulkProgressCallback = Callable[[int, int, str, int, int, int], None]


def pump_bulk_ui_events() -> None:
    """Keep Qt timers (e.g. progress spinner) alive during UI-thread bulk work."""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QEventLoop

        app = QApplication.instance()
        if app is not None:
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    except Exception:
        pass


def shutdown_executor_keeping_ui_alive(executor: Any) -> None:
    """Shut down a ProcessPoolExecutor without freezing the Qt event loop.

    ``shutdown(wait=True)`` runs on a helper thread while the UI thread pumps
    events so overlays (spinner) stay fluent.
    """
    if executor is None:
        return
    done = threading.Event()

    def _wait() -> None:
        try:
            executor.shutdown(wait=True)
        finally:
            done.set()

    worker = threading.Thread(
        target=_wait,
        name="bulk-executor-shutdown",
        daemon=True,
    )
    worker.start()
    # ~60fps to match the bulk-ops spinner timer interval.
    while not done.wait(timeout=0.016):
        pump_bulk_ui_events()
    worker.join(timeout=5.0)
    pump_bulk_ui_events()


def emit_bulk_progress_applying(
    progress_callback: Optional[BulkProgressCallback],
    completed: int,
    total: int,
    updated: int,
    failed: int,
    skipped: int,
) -> None:
    """Notify UI before in-memory batch apply / pool teardown (not disk persistence).

    Message is \"Finishing…\" so the overlay updates before the blocking work;
    callers should treat this as wrap-up of the current step, not Save Database.
    """
    if not progress_callback:
        return
    progress_callback(
        max(0, int(completed)),
        max(0, int(total)),
        "Finishing…",
        max(0, int(updated)),
        max(0, int(failed)),
        max(0, int(skipped)),
    )
    pump_bulk_ui_events()

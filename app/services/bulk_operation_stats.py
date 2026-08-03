"""Shared types for bulk database operations (tags, replace, clean PGN)."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Optional, Any, Tuple


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
    # Object ids of games touched this step (for multi-step unique merge).
    updated_game_ids: Tuple[int, ...] = field(default_factory=tuple)
    failed_game_ids: Tuple[int, ...] = field(default_factory=tuple)


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
    """Release a ProcessPoolExecutor without blocking the Qt UI thread forever.

    Call only after all futures have already completed. Waiting on
    ``shutdown(wait=True)`` can hang indefinitely on some platforms (notably
    macOS + Qt) while worker processes tear down, which left Bulk Operations
    stuck on \"Finishing…\". Non-blocking shutdown is safe once work is done:
    idle workers exit shortly after.
    """
    if executor is None:
        return
    try:
        executor.shutdown(wait=False)
    except Exception:
        pass
    # Brief pump so the overlay can repaint before the next blocking step.
    pump_bulk_ui_events()


def emit_bulk_progress_applying(
    progress_callback: Optional[BulkProgressCallback],
    completed: int,
    total: int,
    updated: int,
    failed: int,
    skipped: int,
    *,
    message: str = "Finishing…",
) -> None:
    """Notify UI before in-memory batch apply (not disk persistence).

    Callers should treat this as wrap-up of the current step, not Save Database.
    """
    if not progress_callback:
        return
    progress_callback(
        max(0, int(completed)),
        max(0, int(total)),
        message,
        max(0, int(updated)),
        max(0, int(failed)),
        max(0, int(skipped)),
    )
    pump_bulk_ui_events()

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


def _on_ui_thread() -> bool:
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QThread

        app = QApplication.instance()
        return app is not None and QThread.currentThread() is app.thread()
    except Exception:
        return False


def pump_bulk_ui_events() -> None:
    """Pump Qt events only when called from the UI thread.

    Never call this while waiting on a ProcessPool from the UI thread — that
    combination hung/crashed on macOS. Prefer running the pool on a QThread
    so the UI event loop stays free without nested processEvents.
    """
    if not _on_ui_thread():
        return
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QEventLoop

        app = QApplication.instance()
        if app is not None:
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    except Exception:
        pass


def shutdown_executor_keeping_ui_alive(executor: Any) -> None:
    """Release a ProcessPoolExecutor after futures have already completed.

    ``shutdown(wait=True)`` can hang indefinitely during worker-process teardown
    on some platforms (observed on Windows after large bulk runs: UI stuck on
    "Running operations…" with final game counts). ``wait=False`` is safe here
    because ``as_completed`` / ``future.result()`` already waited for the work.
    """
    if executor is None:
        return
    try:
        executor.shutdown(wait=False)
    except Exception:
        pass
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
    """Notify UI before in-memory batch apply (not disk persistence)."""
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

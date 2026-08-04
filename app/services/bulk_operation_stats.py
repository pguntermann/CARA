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
    # Games already mutated in memory; apply via batch_update_games on the UI thread.
    pending_games: Tuple[Any, ...] = field(default_factory=tuple)
    # Whether UI-thread batch_update_games should rebuild the position index.
    reindex_positions: bool = False


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


def release_process_pool_executor(
    executor: Any,
    *,
    join_timeout_s: float = 10.0,
) -> None:
    """Release a ProcessPoolExecutor after futures have already completed.

    Prefers a graceful ``shutdown(wait=True)`` so worker processes release their
    multiprocessing semaphores (avoids resource_tracker leak warnings). The join
    runs on a helper thread with a timeout so a stuck teardown cannot freeze the
    bulk-ops worker forever. Only if the join times out are leftover processes
    terminated as a last resort.
    """
    if executor is None:
        return

    import threading

    def _graceful_shutdown() -> None:
        try:
            executor.shutdown(wait=True)
        except Exception:
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass

    joiner = threading.Thread(
        target=_graceful_shutdown,
        name="bulk-process-pool-shutdown",
        daemon=True,
    )
    joiner.start()
    joiner.join(timeout=max(0.1, float(join_timeout_s)))
    if not joiner.is_alive():
        return

    # Graceful join stuck — force-stop idle workers (may leak semaphores).
    try:
        processes = getattr(executor, "_processes", None)
        if isinstance(processes, dict):
            for proc in list(processes.values()):
                try:
                    if proc is not None and proc.is_alive():
                        proc.terminate()
                except Exception:
                    pass
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
    except Exception:
        pass


# Backwards-compatible alias used by older call sites / docs.
shutdown_executor_keeping_ui_alive = release_process_pool_executor


def emit_bulk_progress_phase_complete(
    progress_callback: Optional[BulkProgressCallback],
    completed: int,
    total: int,
    updated: int,
    failed: int,
    skipped: int,
) -> None:
    """Refresh live counts after a compute phase (not final UI apply)."""
    if not progress_callback:
        return
    progress_callback(
        max(0, int(completed)),
        max(0, int(total)),
        f"Processed {max(0, int(completed))}/{max(0, int(total))} games",
        max(0, int(updated)),
        max(0, int(failed)),
        max(0, int(skipped)),
    )


# Older name — kept so any external import still resolves.
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
    """Deprecated alias; prefer ``emit_bulk_progress_phase_complete``."""
    del message
    emit_bulk_progress_phase_complete(
        progress_callback, completed, total, updated, failed, skipped
    )

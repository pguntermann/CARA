"""Shared types for bulk database operations (tags, replace, clean PGN)."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


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

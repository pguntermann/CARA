"""User-facing formatting for bulk operation statistics."""

from app.services.bulk_operation_stats import BulkOperationStats


def format_bulk_operation_counts(
    games_processed: int,
    games_updated: int,
    games_failed: int,
    games_skipped: int,
) -> str:
    """Plain-text counts for live progress and final summary."""
    return (
        f"Games processed: {games_processed}\n"
        f"Games updated: {games_updated}\n"
        f"Games failed: {games_failed}\n"
        f"Games skipped: {games_skipped}"
    )


def format_bulk_operation_summary_plain(stats: BulkOperationStats) -> str:
    """Plain-text summary shown in the Bulk Operations progress overlay."""
    return format_bulk_operation_counts(
        stats.games_processed,
        stats.games_updated,
        stats.games_failed,
        stats.games_skipped,
    )

"""User-facing formatting for bulk operation statistics."""

from app.services.bulk_operation_stats import BulkOperationStats


def format_bulk_operation_summary_plain(stats: BulkOperationStats) -> str:
    """Plain-text summary for dialogs (e.g. Bulk Tag, Bulk Replace)."""
    return (
        f"Operation completed:\n\n"
        f"Games processed: {stats.games_processed}\n"
        f"Games updated: {stats.games_updated}\n"
        f"Games failed: {stats.games_failed}\n"
        f"Games skipped: {stats.games_skipped}"
    )


def format_bulk_operation_summary_html(stats: BulkOperationStats) -> str:
    """HTML summary for dialogs that use rich text (e.g. Bulk Clean PGN)."""
    return (
        f"Operation completed:<br><br>"
        f"Games processed: {stats.games_processed}<br>"
        f"Games updated: {stats.games_updated}<br>"
        f"Games failed: {stats.games_failed}<br>"
        f"Games skipped: {stats.games_skipped}"
    )

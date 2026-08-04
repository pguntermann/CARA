"""PGN cleaning helpers used by the bulk plan worker."""

from typing import Optional, Tuple

from app.services.bulk_operation_stats import BulkProcessingOutcome
from app.services.pgn_cleaning_service import PgnCleaningService


def _process_game_for_cleaning(
    game_pgn: str,
    remove_comments: bool,
    remove_variations: bool,
    remove_non_standard_tags: bool,
    remove_annotations: bool,
) -> Tuple[Optional[str], BulkProcessingOutcome]:
    """Clean one game PGN string (picklable for ProcessPool / plan worker)."""
    try:
        class TempGame:
            def __init__(self, pgn: str):
                self.pgn = pgn

        temp_game = TempGame(game_pgn)
        game_modified = False

        if remove_comments:
            if PgnCleaningService.remove_comments_from_game(temp_game):
                game_modified = True

        if remove_variations:
            if PgnCleaningService.remove_variations_from_game(temp_game):
                game_modified = True

        if remove_non_standard_tags:
            if PgnCleaningService.remove_non_standard_tags_from_game(temp_game):
                game_modified = True

        if remove_annotations:
            if PgnCleaningService.remove_annotations_from_game(temp_game):
                game_modified = True

        if game_modified:
            return (temp_game.pgn, BulkProcessingOutcome.UPDATED)
        return (None, BulkProcessingOutcome.SKIPPED)

    except Exception:
        return (None, BulkProcessingOutcome.FAILED)

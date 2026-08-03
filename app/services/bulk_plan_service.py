"""Single-pass bulk plan executor: apply ordered ops to each game once."""

from __future__ import annotations

import os
import re
from io import StringIO
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import chess.pgn
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel
from app.services.bulk_clean_pgn_service import _process_game_for_cleaning
from app.services.bulk_operation_stats import (
    BulkOperationStats,
    BulkProcessingOutcome,
    BulkProgressCallback,
    emit_bulk_progress_applying,
    shutdown_executor_keeping_ui_alive,
)
from app.services.logging_service import LoggingService
from app.services.pgn_service import PgnService
from app.utils.concurrency_utils import get_process_pool_max_workers
from app.utils.game_data_header_sync import (
    apply_game_data_updates,
    game_data_updates_for_header_tag,
)

# Mode strings mirror BulkOperationsController (kept local so workers stay picklable).
_MODE_FIND_REPLACE = "find_replace"
_MODE_OVERWRITE = "overwrite"
_MODE_COPY = "copy"
_MODE_ADD_TAG = "add_tag"
_MODE_REMOVE_TAGS = "remove_tags"
_MODE_CLEAN = "clean"

PlanStep = Dict[str, Any]


def plan_step_from_operation(operation: Any) -> PlanStep:
    """Convert a BulkOperation-like object into a picklable plan step dict."""
    return {
        "mode": str(operation.mode),
        "tags": list(operation.tags or ()),
        "find_text": str(operation.find_text or ""),
        "replace_text": str(operation.replace_text or ""),
        "case_sensitive": bool(operation.case_sensitive),
        "use_regex": bool(operation.use_regex),
        "source_tag": str(operation.source_tag or ""),
        "copy_value_from_source": bool(operation.copy_value_from_source),
        "remove_comments": bool(operation.remove_comments),
        "remove_variations": bool(operation.remove_variations),
        "remove_non_standard_tags": bool(operation.remove_non_standard_tags),
        "remove_annotations": bool(operation.remove_annotations),
    }


def _apply_add_tag(
    chess_game: chess.pgn.Game, step: PlanStep
) -> Tuple[bool, Dict[str, Any], BulkProcessingOutcome]:
    tags = step.get("tags") or []
    tag_name = tags[0] if tags else ""
    if not tag_name:
        return False, {}, BulkProcessingOutcome.SKIPPED
    if tag_name in chess_game.headers:
        return False, {}, BulkProcessingOutcome.SKIPPED

    if step.get("copy_value_from_source"):
        source = step.get("source_tag") or ""
        new_value = chess_game.headers.get(source, "") if source else ""
    else:
        raw = step.get("replace_text")
        new_value = raw if (raw is not None and str(raw).strip()) else ""

    chess_game.headers[tag_name] = new_value
    return (
        True,
        game_data_updates_for_header_tag(tag_name, new_value, removed=False),
        BulkProcessingOutcome.UPDATED,
    )


def _apply_remove_tags(
    chess_game: chess.pgn.Game, step: PlanStep
) -> Tuple[bool, Dict[str, Any], BulkProcessingOutcome]:
    tag_names = list(step.get("tags") or [])
    removed_any = False
    field_updates: Dict[str, Any] = {}
    for tag_name in tag_names:
        if tag_name in chess_game.headers:
            del chess_game.headers[tag_name]
            removed_any = True
            field_updates.update(game_data_updates_for_header_tag(tag_name, removed=True))
    if not removed_any:
        return False, {}, BulkProcessingOutcome.SKIPPED
    return True, field_updates, BulkProcessingOutcome.UPDATED


def _apply_replace_or_overwrite(
    chess_game: chess.pgn.Game, step: PlanStep
) -> Tuple[bool, Dict[str, Any], BulkProcessingOutcome]:
    tag_names = list(step.get("tags") or [])
    find_text = step.get("find_text") or ""
    replace_text = step.get("replace_text") or ""
    case_sensitive = bool(step.get("case_sensitive"))
    use_regex = bool(step.get("use_regex"))
    overwrite_all = step.get("mode") == _MODE_OVERWRITE

    updated = False
    field_updates: Dict[str, Any] = {}
    for tag_name in tag_names:
        current_value = chess_game.headers.get(tag_name, "")
        if overwrite_all:
            new_value = replace_text
            should_update = True
        elif use_regex:
            try:
                pattern = re.compile(find_text, 0 if case_sensitive else re.IGNORECASE)
                if pattern.search(current_value):
                    new_value = pattern.sub(replace_text, current_value)
                    should_update = True
                else:
                    should_update = False
                    new_value = current_value
            except re.error:
                continue
        else:
            if case_sensitive:
                if find_text in current_value:
                    new_value = current_value.replace(find_text, replace_text)
                    should_update = True
                else:
                    should_update = False
                    new_value = current_value
            else:
                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                if pattern.search(current_value):
                    new_value = pattern.sub(replace_text, current_value)
                    should_update = True
                else:
                    should_update = False
                    new_value = current_value

        if should_update and (overwrite_all or new_value != current_value):
            chess_game.headers[tag_name] = new_value
            updated = True
            field_updates.update(
                game_data_updates_for_header_tag(tag_name, new_value, removed=False)
            )

    if updated:
        return True, field_updates, BulkProcessingOutcome.UPDATED
    return False, {}, BulkProcessingOutcome.SKIPPED


def _apply_copy(
    chess_game: chess.pgn.Game, step: PlanStep
) -> Tuple[bool, Dict[str, Any], BulkProcessingOutcome]:
    target_tags = list(step.get("tags") or [])
    source_tag = step.get("source_tag") or ""
    source_value = chess_game.headers.get(source_tag, "") if source_tag else ""
    if not source_value:
        return False, {}, BulkProcessingOutcome.SKIPPED

    updated = False
    field_updates: Dict[str, Any] = {}
    for target_tag in target_tags:
        current_value = chess_game.headers.get(target_tag, "")
        if source_value != current_value:
            chess_game.headers[target_tag] = source_value
            updated = True
            field_updates.update(
                game_data_updates_for_header_tag(target_tag, source_value, removed=False)
            )
    if updated:
        return True, field_updates, BulkProcessingOutcome.UPDATED
    return False, {}, BulkProcessingOutcome.SKIPPED


def _apply_header_step(
    chess_game: chess.pgn.Game, step: PlanStep
) -> Tuple[bool, Dict[str, Any], BulkProcessingOutcome]:
    mode = step.get("mode")
    if mode == _MODE_ADD_TAG:
        return _apply_add_tag(chess_game, step)
    if mode == _MODE_REMOVE_TAGS:
        return _apply_remove_tags(chess_game, step)
    if mode == _MODE_COPY:
        return _apply_copy(chess_game, step)
    if mode in (_MODE_FIND_REPLACE, _MODE_OVERWRITE):
        return _apply_replace_or_overwrite(chess_game, step)
    return False, {}, BulkProcessingOutcome.FAILED


def _process_game_for_plan(
    game_pgn: str, steps: Tuple[PlanStep, ...]
) -> Tuple[Optional[str], Dict[str, Any], BulkProcessingOutcome]:
    """Apply an ordered plan to one game (ProcessPool worker entry point)."""
    try:
        if not steps:
            return None, {}, BulkProcessingOutcome.SKIPPED

        chess_game = chess.pgn.read_game(StringIO(game_pgn))
        if not chess_game:
            return None, {}, BulkProcessingOutcome.FAILED

        field_updates: Dict[str, Any] = {}
        any_changed = False

        for step in steps:
            mode = step.get("mode")
            if mode == _MODE_CLEAN:
                current_pgn = PgnService.export_game_to_pgn(chess_game)
                new_pgn, outcome = _process_game_for_cleaning(
                    current_pgn,
                    bool(step.get("remove_comments")),
                    bool(step.get("remove_variations")),
                    bool(step.get("remove_non_standard_tags")),
                    bool(step.get("remove_annotations")),
                )
                if outcome == BulkProcessingOutcome.FAILED:
                    return None, {}, BulkProcessingOutcome.FAILED
                if outcome == BulkProcessingOutcome.UPDATED and new_pgn:
                    any_changed = True
                    chess_game = chess.pgn.read_game(StringIO(new_pgn))
                    if not chess_game:
                        return None, {}, BulkProcessingOutcome.FAILED
                continue

            changed, updates, outcome = _apply_header_step(chess_game, step)
            if outcome == BulkProcessingOutcome.FAILED:
                return None, {}, BulkProcessingOutcome.FAILED
            if changed:
                any_changed = True
                field_updates.update(updates)

        if any_changed:
            return (
                PgnService.export_game_to_pgn(chess_game),
                field_updates,
                BulkProcessingOutcome.UPDATED,
            )
        return None, {}, BulkProcessingOutcome.SKIPPED
    except Exception:
        return None, {}, BulkProcessingOutcome.FAILED


class BulkPlanService:
    """Run an ordered list of header/clean operations in one pass over games."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def apply_plan(
        self,
        database: DatabaseModel,
        operations: Sequence[Any],
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[BulkProgressCallback] = None,
        cancellation_check: Optional[Callable[[], bool]] = None,
    ) -> BulkOperationStats:
        """Apply all plan operations to each game once (process pool)."""
        steps = tuple(plan_step_from_operation(op) for op in operations)
        if not steps:
            return BulkOperationStats(True, 0, 0, 0, 0)

        games = database.get_all_games()
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = list(games)

        total_games = len(games_to_process)
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process", 0, 0, 0)
            return BulkOperationStats(True, 0, 0, 0, 0)

        max_workers = get_process_pool_max_workers(os.cpu_count(), self.config)
        updated_games: List[Any] = []
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        executor = None
        completed = 0

        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            future_to_game = {
                executor.submit(_process_game_for_plan, game.pgn, steps): game
                for game in games_to_process
            }

            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break

                game = future_to_game[future]
                completed += 1
                try:
                    new_pgn, field_updates, outcome = future.result()
                    if outcome == BulkProcessingOutcome.UPDATED:
                        if new_pgn:
                            game.pgn = new_pgn
                            if isinstance(field_updates, dict):
                                apply_game_data_updates(game, field_updates)
                            updated_games.append(game)
                            games_updated += 1
                        else:
                            games_failed += 1
                    elif outcome == BulkProcessingOutcome.SKIPPED:
                        games_skipped += 1
                    else:
                        games_failed += 1
                except Exception:
                    games_failed += 1

                if progress_callback:
                    progress_callback(
                        completed,
                        total_games,
                        f"Processing game {completed}/{total_games}",
                        games_updated,
                        games_failed,
                        games_skipped,
                    )

            emit_bulk_progress_applying(
                progress_callback,
                completed,
                total_games,
                games_updated,
                games_failed,
                games_skipped,
            )
        finally:
            if executor:
                shutdown_executor_keeping_ui_alive(executor)

        if updated_games:
            database.batch_update_games(updated_games)

        added_tags = {
            (step.get("tags") or [None])[0]
            for step in steps
            if step.get("mode") == _MODE_ADD_TAG and (step.get("tags") or [None])[0]
        }
        if added_tags:
            try:
                database._add_tags_to_cache(added_tags)
            except Exception:
                pass

        LoggingService.get_instance().info(
            f"Bulk plan completed: steps={len(steps)}, games_processed={completed}, "
            f"games_updated={games_updated}, games_failed={games_failed}, "
            f"games_skipped={games_skipped}"
        )
        return BulkOperationStats(
            success=True,
            games_processed=completed,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped,
        )

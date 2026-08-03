"""Bulk operations controller — header tags, clean PGN, and Smart Update."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel, GameData
from app.services.bulk_clean_pgn_service import BulkCleanPgnService
from app.services.bulk_operation_stats import BulkOperationStats
from app.services.bulk_replace_service import BulkReplaceService
from app.services.bulk_tag_service import BulkTagService
from app.services.engine_parameters_service import EngineParametersService
from app.services.opening_service import OpeningService
from app.services.progress_service import ProgressService

MODE_FIND_REPLACE = "find_replace"
MODE_OVERWRITE = "overwrite"
MODE_COPY = "copy"
MODE_ADD_TAG = "add_tag"
MODE_REMOVE_TAGS = "remove_tags"
MODE_CLEAN = "clean"

ALL_MODES = (
    MODE_FIND_REPLACE,
    MODE_OVERWRITE,
    MODE_COPY,
    MODE_ADD_TAG,
    MODE_REMOVE_TAGS,
    MODE_CLEAN,
)

MODE_LABELS = {
    MODE_FIND_REPLACE: "Replace PGN header tag values",
    MODE_OVERWRITE: "Overwrite PGN header tag values",
    MODE_COPY: "Copy PGN header tag values",
    MODE_ADD_TAG: "Add PGN header tag",
    MODE_REMOVE_TAGS: "Remove PGN header tags",
    MODE_CLEAN: "Clean PGN notation",
}

# PGN Seven Tag Roster — omit from add presets and remove options.
FIXED_PGN_TAGS: frozenset[str] = frozenset(
    {"Event", "Site", "Date", "Round", "White", "Black", "Result"}
)

STANDARD_TAGS: List[str] = [
    "White",
    "Black",
    "Result",
    "Date",
    "Event",
    "Site",
    "Round",
    "ECO",
    "WhiteElo",
    "BlackElo",
    "TimeControl",
    "WhiteTitle",
    "BlackTitle",
    "WhiteFideId",
    "BlackFideId",
    "WhiteTeam",
    "BlackTeam",
    "PlyCount",
    "EventDate",
    "Termination",
    "Annotator",
    "UTCTime",
]


def _pgn_fingerprint(pgn: str) -> bytes:
    """Compact digest for comparing PGN before/after multi-step bulk ops."""
    return hashlib.blake2b(pgn.encode("utf-8"), digest_size=16).digest()


def _combine_multi_step_bulk_stats(
    step_results: List[BulkOperationStats],
    games_in_scope: List[GameData],
    initial_fingerprints: Dict[int, bytes],
) -> BulkOperationStats:
    """Single summary for multiple phases: unique games via PGN fingerprint delta."""
    if not step_results:
        return BulkOperationStats(True, 0, 0, 0, 0)
    if len(step_results) == 1:
        return step_results[0]
    n = len(games_in_scope)
    modified = sum(
        1 for g in games_in_scope if _pgn_fingerprint(g.pgn) != initial_fingerprints[id(g)]
    )
    failed_sum = sum(r.games_failed for r in step_results)
    return BulkOperationStats(
        success=True,
        games_processed=n,
        games_updated=modified,
        games_failed=failed_sum,
        games_skipped=n - modified,
    )


@dataclass(frozen=True)
class BulkOperation:
    """One bulk step: header-tag mutation or PGN clean."""

    mode: str
    tags: Tuple[str, ...] = ()
    find_text: str = ""
    replace_text: str = ""
    case_sensitive: bool = False
    use_regex: bool = False
    source_tag: str = ""
    # add_tag: when True, value comes from source_tag; else replace_text is the fixed value.
    copy_value_from_source: bool = False
    remove_comments: bool = False
    remove_variations: bool = False
    remove_non_standard_tags: bool = False
    remove_annotations: bool = False

    def summary(self) -> str:
        """Human-readable one-line description for the operations list."""
        if self.mode == MODE_CLEAN:
            parts: List[str] = []
            if self.remove_comments:
                parts.append("comments")
            if self.remove_variations:
                parts.append("variations")
            if self.remove_non_standard_tags:
                parts.append("non-standard tags")
            if self.remove_annotations:
                parts.append("annotations")
            detail = ", ".join(parts) if parts else "(none)"
            return f"Clean PGN: {detail}"
        if self.mode == MODE_ADD_TAG:
            name = self.tags[0] if self.tags else "?"
            if self.copy_value_from_source:
                return f'Add tag {name} (copy from {self.source_tag})'
            return f'Add tag {name} → "{self.replace_text}"'
        if self.mode == MODE_REMOVE_TAGS:
            return f"Remove tags: {', '.join(self.tags)}"
        tags = ", ".join(self.tags)
        if self.mode == MODE_OVERWRITE:
            return f'Set {tags} → "{self.replace_text}"'
        if self.mode == MODE_COPY:
            return f"Copy {self.source_tag} → {tags}"
        opts: List[str] = []
        if self.case_sensitive:
            opts.append("case")
        if self.use_regex:
            opts.append("regex")
        suffix = f" ({', '.join(opts)})" if opts else ""
        return f'Replace in {tags}: "{self.find_text}" → "{self.replace_text}"{suffix}'


def sanitize_tag_name(tag_name: str) -> str:
    """Sanitize a tag name for PGN (alnum/underscore; must start alnum)."""
    tag_name = re.sub(r"\s+", "", tag_name)
    tag_name = re.sub(r"[^A-Za-z0-9_]", "", tag_name)
    if tag_name and not tag_name[0].isalnum():
        tag_name = "Tag" + tag_name
    return tag_name


def validate_bulk_operation(operation: BulkOperation) -> Optional[str]:
    """Validate a single operation. Returns an error message, or None if valid."""
    if operation.mode not in ALL_MODES:
        return "Invalid operation mode"

    if operation.mode == MODE_CLEAN:
        if not (
            operation.remove_comments
            or operation.remove_variations
            or operation.remove_non_standard_tags
            or operation.remove_annotations
        ):
            return "Please select at least one cleaning option"
        return None

    if operation.mode == MODE_ADD_TAG:
        if not operation.tags or not (operation.tags[0] or "").strip():
            return "Please enter a tag name"
        name = sanitize_tag_name(operation.tags[0])
        if not name:
            return "Please enter a valid tag name"
        if operation.copy_value_from_source:
            source = (operation.source_tag or "").strip()
            if not source:
                return "Please enter a source tag name"
            if sanitize_tag_name(source) == name:
                return "Source tag cannot be the same as the new tag"
        return None

    if operation.mode == MODE_REMOVE_TAGS:
        if not operation.tags:
            return "Please select at least one tag to remove"
        return None

    if not operation.tags:
        return "Please select at least one tag"

    if operation.mode == MODE_COPY:
        source = (operation.source_tag or "").strip()
        if not source:
            return "Please enter a source tag name"
        if source in operation.tags:
            return "Source tag cannot be in the target tags list"
        return None

    if operation.mode == MODE_OVERWRITE:
        return None

    if not (operation.find_text or "").strip():
        return "Please enter text to find"
    if not (operation.replace_text or "").strip():
        return "Please enter replacement text"
    return None


class BulkOperationsController(QObject):
    """Orchestrates bulk header-tag, clean, and Smart Update operations."""

    operation_complete = pyqtSignal(BulkOperationStats)

    def __init__(
        self,
        config: Dict[str, Any],
        database_controller,
        engine_controller,
        evaluation_controller,
        game_controller=None,
    ) -> None:
        super().__init__()
        self.config = config
        self.database_controller = database_controller
        self.engine_controller = engine_controller
        self.evaluation_controller = evaluation_controller
        self.game_controller = game_controller
        self.replace_service = BulkReplaceService(config)
        self.tag_service = BulkTagService(config)
        self.clean_service = BulkCleanPgnService(config)
        self.progress_service = ProgressService.get_instance()
        self._cancelled = False

    def get_active_database(self) -> Optional[DatabaseModel]:
        return self.database_controller.get_active_database()

    def get_add_tag_options(self) -> List[str]:
        """Tag name presets for Add tag mode (omits fixed PGN roster tags)."""
        return [t for t in STANDARD_TAGS if t not in FIXED_PGN_TAGS]

    def get_removable_tags(self, database: Optional[DatabaseModel]) -> List[str]:
        """Tags shown in Remove tag(s) mode (omits fixed PGN roster tags)."""
        if not database:
            return []
        tags = self.database_controller.get_available_tags(database)
        return [t for t in tags if t not in FIXED_PGN_TAGS]

    def get_available_tags(self, database: Optional[DatabaseModel]) -> List[str]:
        if not database:
            return []
        return self.database_controller.get_available_tags(database)

    def cancel_operation(self) -> None:
        self._cancelled = True

    def _refresh_active_game_if_updated(
        self, database: DatabaseModel, game_indices: Optional[List[int]]
    ) -> None:
        if not self.game_controller:
            return
        game_model = self.game_controller.get_game_model()
        active_game = game_model.active_game
        if not active_game:
            return
        games = database.get_all_games()
        if game_indices is not None:
            updated_games = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            updated_games = games
        if active_game in updated_games:
            game_model.refresh_active_game()

    def _progress_callback(self, game_index: int, total: int, message: str) -> None:
        if self._cancelled:
            return
        percent = int((game_index / total) * 100) if total > 0 else 0
        self.progress_service.set_progress(percent)
        self.progress_service.set_status(f"Bulk Operations: {message}")

    def _cancel_flag(self) -> bool:
        return self._cancelled

    def _run_operation(
        self,
        database: DatabaseModel,
        operation: BulkOperation,
        game_indices: Optional[List[int]],
    ) -> BulkOperationStats:
        if operation.mode == MODE_CLEAN:
            return self.clean_service.clean_pgn(
                database,
                operation.remove_comments,
                operation.remove_variations,
                operation.remove_non_standard_tags,
                operation.remove_annotations,
                game_indices,
                self._progress_callback,
                self._cancel_flag,
            )
        if operation.mode == MODE_ADD_TAG:
            tag_name = sanitize_tag_name(operation.tags[0])
            source = (
                sanitize_tag_name(operation.source_tag)
                if operation.copy_value_from_source
                else None
            )
            value = None if source else operation.replace_text
            return self.tag_service.add_tag(
                database,
                tag_name,
                value,
                source,
                game_indices,
                self._progress_callback,
                self._cancel_flag,
            )
        if operation.mode == MODE_REMOVE_TAGS:
            names = [sanitize_tag_name(t) for t in operation.tags]
            names = [t for t in names if t]
            return self.tag_service.remove_tags(
                database,
                names,
                game_indices,
                self._progress_callback,
                self._cancel_flag,
            )
        if operation.mode == MODE_COPY:
            return self.replace_service.copy_metadata_tags(
                database,
                list(operation.tags),
                operation.source_tag.strip(),
                game_indices,
                self._progress_callback,
                self._cancel_flag,
            )
        return self.replace_service.replace_metadata_tags(
            database,
            list(operation.tags),
            operation.find_text,
            operation.replace_text,
            operation.case_sensitive,
            operation.use_regex,
            operation.mode == MODE_OVERWRITE,
            game_indices,
            self._progress_callback,
            self._cancel_flag,
        )

    def _run_result_update(
        self,
        database: DatabaseModel,
        game_indices: Optional[List[int]],
    ) -> BulkOperationStats:
        from app.controllers.engine_controller import TASK_EVALUATION

        engine_id = self.engine_controller.get_engine_assignment(TASK_EVALUATION)
        if not engine_id:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="No evaluation engine configured",
            )

        engine = self.engine_controller.get_engine_model().get_engine(engine_id)
        if not engine:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="Evaluation engine not found",
            )

        engine_path = Path(engine.path)
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "evaluation",
            self.config,
        )

        eval_bar_config = (
            self.config.get("ui", {})
            .get("panels", {})
            .get("main", {})
            .get("board", {})
            .get("evaluation_bar", {})
        )
        max_depth = task_params.get("depth", eval_bar_config.get("max_depth_evaluation", 0))
        time_limit_ms = task_params.get("movetime", 0)
        max_threads = task_params.get("threads", eval_bar_config.get("max_threads", None))

        engine_options = {
            key: value
            for key, value in task_params.items()
            if key not in ["threads", "depth", "movetime"]
        }

        if max_depth == 0:
            max_depth = 12
        if time_limit_ms == 0:
            time_limit_ms = 500

        return self.replace_service.update_result_tags(
            database,
            engine_path,
            max_depth,
            time_limit_ms,
            max_threads,
            engine_options,
            game_indices,
            self._progress_callback,
            self._cancel_flag,
        )

    def _run_eco_update(
        self,
        database: DatabaseModel,
        game_indices: Optional[List[int]],
    ) -> BulkOperationStats:
        opening_service = OpeningService(self.config)
        opening_service.load()
        return self.replace_service.update_eco_tags(
            database,
            opening_service,
            game_indices,
            self._progress_callback,
            self._cancel_flag,
        )

    def execute_bulk_operations(
        self,
        database: DatabaseModel,
        operations: List[BulkOperation],
        has_result_update: bool,
        has_eco_update: bool,
        game_indices: Optional[List[int]],
    ) -> BulkOperationStats:
        """Execute operations in order, plus optional Smart Update steps."""
        if not operations and not has_result_update and not has_eco_update:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="Please add at least one operation, or enable Smart Update",
            )

        if game_indices is not None and len(game_indices) == 0:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="No games selected",
            )

        for operation in operations:
            error = validate_bulk_operation(operation)
            if error:
                return BulkOperationStats(
                    success=False,
                    games_processed=0,
                    games_updated=0,
                    games_failed=0,
                    games_skipped=0,
                    error_message=error,
                )

        games = database.get_all_games()
        if game_indices is not None:
            games_in_scope = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_in_scope = list(games)
        initial_fingerprints = {id(g): _pgn_fingerprint(g.pgn) for g in games_in_scope}

        self._cancelled = False
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Operations: Starting...")

        step_results: List[BulkOperationStats] = []
        result = BulkOperationStats(True, 0, 0, 0, 0)
        try:
            total_steps = len(operations) + int(has_result_update) + int(has_eco_update)
            step_index = 0
            failed: Optional[BulkOperationStats] = None

            for operation in operations:
                step_index += 1
                self.progress_service.set_status(
                    f"Bulk Operations: Operation {step_index}/{total_steps}…"
                )
                step = self._run_operation(database, operation, game_indices)
                if not step.success:
                    failed = step
                    break
                step_results.append(step)

            if failed is None and has_result_update:
                step_index += 1
                self.progress_service.set_status(
                    f"Bulk Operations: Operation {step_index}/{total_steps} (Result)…"
                )
                result_update = self._run_result_update(database, game_indices)
                if not result_update.success:
                    failed = result_update
                else:
                    step_results.append(result_update)

            if failed is None and has_eco_update:
                step_index += 1
                self.progress_service.set_status(
                    f"Bulk Operations: Operation {step_index}/{total_steps} (ECO)…"
                )
                eco_result = self._run_eco_update(database, game_indices)
                if not eco_result.success:
                    failed = eco_result
                else:
                    step_results.append(eco_result)

            if failed is not None:
                result = failed
            else:
                result = _combine_multi_step_bulk_stats(
                    step_results, games_in_scope, initial_fingerprints
                )
        finally:
            self.progress_service.hide_progress()

        if result.success:
            if self.game_controller:
                self._refresh_active_game_if_updated(database, game_indices)
            if result.games_updated > 0:
                self.database_controller.mark_database_unsaved(database)

        self.operation_complete.emit(result)
        return result

"""Bulk operations controller — header tags, clean PGN, and Smart Update."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel, GameData
from app.services.bulk_operation_stats import BulkOperationStats
from app.services.bulk_plan_service import BulkPlanService
from app.services.bulk_replace_service import BulkReplaceService
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


@dataclass(frozen=True)
class BulkPlanIssue:
    """One interlocking / redundant-plan finding for a bulk operation sequence."""

    message: str


def _plan_tag_name(raw: str) -> str:
    return sanitize_tag_name((raw or "").strip())


def _plan_step_label(index: int) -> str:
    return f"Step {index + 1}"


def validate_bulk_operation_plan(
    operations: List[BulkOperation],
    has_result_update: bool = False,
    has_eco_update: bool = False,
) -> List[BulkPlanIssue]:
    """Detect conflicting or redundant tag interactions across an ordered plan.

    Clean PGN does not affect header tags (its "non-standard tags" option removes
    comment markers like [%clk], not PGN headers), so it is ignored here.

    Returns human-readable issues. Empty list means no plan-level problems found.
    """
    issues: List[BulkPlanIssue] = []
    # Tags removed by an earlier step and not re-added yet.
    removed: Dict[str, int] = {}
    # Last step that wrote each tag (add / overwrite / replace / copy target).
    last_writer: Dict[str, int] = {}

    def _note_use_after_remove(step_index: int, tag: str, role: str) -> None:
        if tag in removed:
            issues.append(
                BulkPlanIssue(
                    f"{_plan_step_label(step_index)} {role} tag \"{tag}\", "
                    f"which was removed in {_plan_step_label(removed[tag])}"
                )
            )

    def _note_write(step_index: int, tag: str, action: str) -> None:
        _note_use_after_remove(step_index, tag, action)
        if tag in last_writer and tag not in removed:
            issues.append(
                BulkPlanIssue(
                    f"{_plan_step_label(step_index)} writes tag \"{tag}\", "
                    f"which was already modified in {_plan_step_label(last_writer[tag])} "
                    f"(earlier write will be overwritten)"
                )
            )
        removed.pop(tag, None)
        last_writer[tag] = step_index

    for index, operation in enumerate(operations):
        if operation.mode == MODE_CLEAN:
            continue

        if operation.mode == MODE_REMOVE_TAGS:
            for raw in operation.tags:
                tag = _plan_tag_name(raw)
                if not tag:
                    continue
                if tag in removed:
                    issues.append(
                        BulkPlanIssue(
                            f"{_plan_step_label(index)} removes tag \"{tag}\", "
                            f"which was already removed in {_plan_step_label(removed[tag])}"
                        )
                    )
                removed[tag] = index
                last_writer.pop(tag, None)
            continue

        if operation.mode == MODE_ADD_TAG:
            tag = _plan_tag_name(operation.tags[0] if operation.tags else "")
            if not tag:
                continue
            if operation.copy_value_from_source:
                source = _plan_tag_name(operation.source_tag)
                if source:
                    _note_use_after_remove(index, source, "copies from")
            # Re-adding after remove is intentional; clear removed and record write.
            if tag in last_writer and tag not in removed:
                issues.append(
                    BulkPlanIssue(
                        f"{_plan_step_label(index)} adds tag \"{tag}\", "
                        f"which was already modified in {_plan_step_label(last_writer[tag])} "
                        f"(earlier write will be overwritten)"
                    )
                )
            removed.pop(tag, None)
            last_writer[tag] = index
            continue

        if operation.mode == MODE_COPY:
            source = _plan_tag_name(operation.source_tag)
            if source:
                _note_use_after_remove(index, source, "copies from")
            for raw in operation.tags:
                tag = _plan_tag_name(raw)
                if tag:
                    _note_write(index, tag, "writes")
            continue

        # find_replace / overwrite
        action = "overwrites" if operation.mode == MODE_OVERWRITE else "updates"
        for raw in operation.tags:
            tag = _plan_tag_name(raw)
            if tag:
                _note_write(index, tag, action)

    def _note_smart(label: str, tag: str) -> None:
        if tag in removed:
            issues.append(
                BulkPlanIssue(
                    f"Smart Update ({label}) targets tag \"{tag}\", "
                    f"which was removed in {_plan_step_label(removed[tag])}"
                )
            )
            return
        if tag in last_writer:
            issues.append(
                BulkPlanIssue(
                    f"Smart Update ({label}) overwrites tag \"{tag}\", "
                    f"which was already modified in {_plan_step_label(last_writer[tag])}"
                )
            )

    if has_result_update:
        _note_smart("Result", "Result")
    if has_eco_update:
        _note_smart("ECO", "ECO")

    return issues


def format_bulk_plan_issues(issues: List[BulkPlanIssue]) -> str:
    """User-facing confirmation body for plan validation findings."""
    lines = ["The operation plan has potential conflicts:", ""]
    for issue in issues:
        lines.append(f"• {issue.message}")
    lines.append("")
    lines.append("Continue anyway?")
    return "\n".join(lines)


class BulkOperationsController(QObject):
    """Orchestrates bulk header-tag, clean, and Smart Update operations."""

    progress_updated = pyqtSignal(int, str, int, int, int, int, str)

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
        self.plan_service = BulkPlanService(config)
        self.progress_service = ProgressService.get_instance()
        self._cancelled = False
        self._progress_step_index = 0
        self._progress_total_steps = 1
        self._baseline_processed = 0
        self._baseline_updated = 0
        self._baseline_failed = 0
        self._games_in_scope: List[GameData] = []
        self._updated_game_ids: Set[int] = set()
        self._failed_game_ids: Set[int] = set()
        self._current_step_label = ""
        self._last_live_processed = 0
        self._last_live_updated = 0
        self._last_live_failed = 0
        self._last_live_skipped = 0

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

    def _overall_percent(self, fraction_within_step: float) -> int:
        total = max(1, int(self._progress_total_steps))
        step = max(0, min(total - 1, int(self._progress_step_index)))
        fraction = max(0.0, min(1.0, float(fraction_within_step)))
        return int(((step + fraction) / total) * 100)

    def _clamp_live_counts(
        self,
        processed: int,
        updated: int,
        failed: int,
        skipped: int,
    ) -> Tuple[int, int, int, int]:
        """Keep live counters within scope and mutually consistent."""
        n = len(self._games_in_scope)
        processed = max(0, int(processed))
        updated = max(0, int(updated))
        failed = max(0, int(failed))
        skipped = max(0, int(skipped))
        if n > 0:
            processed = min(processed, n)
            updated = min(updated, n)
            failed = min(failed, n)
        # Skipped is whatever remains — don't sum per-step skips (ECO would
        # otherwise overwrite a prior plan's "updated" with huge skip counts).
        skipped = max(0, processed - updated - failed)
        return processed, updated, failed, skipped

    def _merge_step_stats(self, step_results: List[BulkOperationStats]) -> BulkOperationStats:
        """Union per-game outcomes across plan + Smart Update phases."""
        n = len(self._games_in_scope)
        updated_ids: Set[int] = set()
        failed_ids: Set[int] = set()
        for step in step_results:
            updated_ids.update(step.updated_game_ids)
            failed_ids.update(step.failed_game_ids)
        # Prefer "updated" when a later step fails after an earlier update.
        failed_ids -= updated_ids
        updated = len(updated_ids)
        failed = len(failed_ids)
        if n <= 0:
            processed = sum(r.games_processed for r in step_results)
            return BulkOperationStats(
                success=True,
                games_processed=processed,
                games_updated=updated,
                games_failed=failed,
                games_skipped=max(0, processed - updated - failed),
                updated_game_ids=tuple(updated_ids),
                failed_game_ids=tuple(failed_ids),
            )
        return BulkOperationStats(
            success=True,
            games_processed=n,
            games_updated=updated,
            games_failed=failed,
            games_skipped=max(0, n - updated - failed),
            updated_game_ids=tuple(updated_ids),
            failed_game_ids=tuple(failed_ids),
        )

    def _emit_progress(
        self,
        percent: int,
        message: str,
        processed: int,
        updated: int,
        failed: int,
        skipped: int,
    ) -> None:
        processed, updated, failed, skipped = self._clamp_live_counts(
            processed, updated, failed, skipped
        )
        self._last_live_processed = processed
        self._last_live_updated = updated
        self._last_live_failed = failed
        self._last_live_skipped = skipped
        self.progress_updated.emit(
            int(percent),
            message,
            processed,
            updated,
            failed,
            skipped,
            self._current_step_label,
        )

    def _progress_callback(
        self,
        game_index: int,
        total: int,
        message: str,
        games_updated: int = 0,
        games_failed: int = 0,
        games_skipped: int = 0,
    ) -> None:
        if self._cancelled:
            return
        # Post-loop in-memory apply (not Save Database).
        if message == "Finishing…":
            percent = self._overall_percent(1.0)
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Operations: {message}")
            self._emit_progress(
                percent,
                message,
                self._baseline_processed + max(0, int(game_index)),
                max(
                    self._last_live_updated,
                    self._baseline_updated + max(0, int(games_updated)),
                ),
                self._baseline_failed + max(0, int(games_failed)),
                0,
            )
            return
        fraction = (game_index / total) if total > 0 else 0.0
        percent = self._overall_percent(fraction)
        status = f"Bulk Operations: {message}"
        self.progress_service.set_progress(percent)
        self.progress_service.set_status(status)
        processed_count = self._baseline_processed + max(0, int(game_index))
        # Unique updated so far (prior steps) plus this step's running updated
        # count as a lower bound for the live display. Derive skipped so ECO
        # skip-heavy ticks cannot erase earlier plan updates.
        unique_prior = len(self._updated_game_ids)
        step_updated = max(0, int(games_updated))
        updated_count = max(
            unique_prior,
            self._baseline_updated + step_updated
            if (total > 0 and int(game_index) >= int(total))
            else unique_prior + step_updated,
        )
        failed_count = len(self._failed_game_ids) + max(0, int(games_failed))
        self._emit_progress(
            percent,
            message,
            processed_count,
            updated_count,
            failed_count,
            0,  # recomputed in _clamp_live_counts
        )

    def _set_step_status(self, message: str, percent: Optional[int] = None) -> None:
        self._current_step_label = message
        self.progress_service.set_status(f"Bulk Operations: {message}")
        if percent is None:
            percent = self._overall_percent(0.0)
        self.progress_service.set_progress(percent)
        # Reuse last live counts on step transitions.
        self._emit_progress(
            int(percent),
            message,
            self._last_live_processed,
            self._last_live_updated,
            self._last_live_failed,
            self._last_live_skipped,
        )

    def _accumulate_step_stats(self, step: BulkOperationStats) -> None:
        self._baseline_processed += int(step.games_processed)
        self._baseline_updated += int(step.games_updated)
        self._baseline_failed += int(step.games_failed)
        self._updated_game_ids.update(step.updated_game_ids)
        self._failed_game_ids.update(step.failed_game_ids)
        self._failed_game_ids -= self._updated_game_ids

    def _cancel_flag(self) -> bool:
        return self._cancelled

    def _prepare_operations(self, operations: List[BulkOperation]) -> List[BulkOperation]:
        """Sanitize tag names on a validated plan before the single-pass runner."""
        prepared: List[BulkOperation] = []
        for op in operations:
            if op.mode == MODE_ADD_TAG:
                tag = sanitize_tag_name(op.tags[0]) if op.tags else ""
                source = (
                    sanitize_tag_name(op.source_tag)
                    if op.copy_value_from_source
                    else op.source_tag
                )
                prepared.append(
                    replace(op, tags=(tag,) if tag else (), source_tag=source)
                )
            elif op.mode == MODE_REMOVE_TAGS:
                tags = tuple(
                    t for t in (sanitize_tag_name(x) for x in op.tags) if t
                )
                prepared.append(replace(op, tags=tags))
            elif op.mode == MODE_COPY:
                tags = tuple(
                    t for t in (sanitize_tag_name(x) for x in op.tags) if t
                )
                prepared.append(
                    replace(
                        op,
                        tags=tags,
                        source_tag=sanitize_tag_name(op.source_tag),
                    )
                )
            elif op.mode in (MODE_FIND_REPLACE, MODE_OVERWRITE):
                tags = tuple(
                    t for t in (sanitize_tag_name(x) for x in op.tags) if t
                )
                prepared.append(replace(op, tags=tags))
            else:
                prepared.append(op)
        return prepared

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

        self._cancelled = False
        self._baseline_processed = 0
        self._baseline_updated = 0
        self._baseline_failed = 0
        self._last_live_processed = 0
        self._last_live_updated = 0
        self._last_live_failed = 0
        self._last_live_skipped = 0
        self._games_in_scope = games_in_scope
        self._updated_game_ids = set()
        self._failed_game_ids = set()
        self._current_step_label = ""
        self.progress_service.show_progress()
        # Plan ops share one game pass; Smart Update steps remain separate phases.
        phase_count = int(bool(operations)) + int(has_result_update) + int(has_eco_update)
        self._progress_total_steps = max(1, phase_count)
        self._progress_step_index = 0
        self._set_step_status("Starting…", 0)

        step_results: List[BulkOperationStats] = []
        result = BulkOperationStats(True, 0, 0, 0, 0)
        try:
            step_index = 0
            failed: Optional[BulkOperationStats] = None

            if operations and not self._cancelled:
                step_index += 1
                self._progress_step_index = step_index - 1
                n_ops = len(operations)
                self._set_step_status(
                    f"Step {step_index}/{phase_count}: "
                    f"Applying {n_ops} operation{'s' if n_ops != 1 else ''}…",
                )
                plan_ops = self._prepare_operations(list(operations))
                plan_result = self.plan_service.apply_plan(
                    database,
                    plan_ops,
                    game_indices,
                    self._progress_callback,
                    self._cancel_flag,
                )
                if not plan_result.success:
                    failed = plan_result
                else:
                    step_results.append(plan_result)
                    self._accumulate_step_stats(plan_result)

            if failed is None and has_result_update and not self._cancelled:
                step_index += 1
                self._progress_step_index = step_index - 1
                self._set_step_status(
                    f"Step {step_index}/{phase_count}: Smart Update (Result)",
                )
                result_update = self._run_result_update(database, game_indices)
                if not result_update.success:
                    failed = result_update
                else:
                    step_results.append(result_update)
                    self._accumulate_step_stats(result_update)

            if failed is None and has_eco_update and not self._cancelled:
                step_index += 1
                self._progress_step_index = step_index - 1
                self._set_step_status(
                    f"Step {step_index}/{phase_count}: Smart Update (ECO)",
                )
                eco_result = self._run_eco_update(database, game_indices)
                if not eco_result.success:
                    failed = eco_result
                else:
                    step_results.append(eco_result)
                    self._accumulate_step_stats(eco_result)

            if self._cancelled:
                result = BulkOperationStats(
                    success=False,
                    games_processed=sum(r.games_processed for r in step_results),
                    games_updated=sum(r.games_updated for r in step_results),
                    games_failed=sum(r.games_failed for r in step_results),
                    games_skipped=sum(r.games_skipped for r in step_results),
                    error_message="Cancelled",
                )
            elif failed is not None:
                result = failed
            else:
                if len(step_results) <= 1:
                    result = (
                        step_results[0]
                        if step_results
                        else BulkOperationStats(True, 0, 0, 0, 0)
                    )
                else:
                    # Union across plan + Smart Update: a game updated in any
                    # phase counts as updated (ECO skips must not erase plan hits).
                    result = self._merge_step_stats(step_results)
        finally:
            # hide_progress alone leaves the last status ("Finishing…") in the bar.
            self.progress_service.reset()

        return result

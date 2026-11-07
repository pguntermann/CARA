"""Single-source-of-truth guards for Chess Log data (#88; see "Single source of truth" in doc/chess_log.md).

Source-level tests: each pins the owner of one kind of Chess Log state, so a new
writer or a read around the accessor fails here instead of drifting into a second
copy.  Existing guards for the rest of the owner table are listed in the doc.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

_REPO = Path(__file__).resolve().parent.parent
_APP = _REPO / "app"

_CHARTS_CTRL = "app/controllers/chess_log_charts_controller.py"
_OWNER_CTRL = "app/controllers/chess_log_controller.py"


def _app_trees() -> Iterator[Tuple[str, ast.AST]]:
    for path in sorted(_APP.rglob("*.py")):
        yield path.relative_to(_REPO).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _attribute_uses(names: Set[str], allowed_files: Set[str]) -> List[Tuple[str, int, str]]:
    """Every `.name` attribute access in app/ outside *allowed_files*."""
    hits = []
    for rel, tree in _app_trees():
        if rel in allowed_files:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in names:
                hits.append((rel, node.lineno, node.attr))
    return hits


def _writers_by_function(rel: str, class_name: str, names: Set[str]) -> Dict[str, Set[str]]:
    """{attribute: {methods of *class_name* that assign it}} for `self.<attribute> = ...`."""
    tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    writers: Dict[str, Set[str]] = {}
    for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(fn):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Attribute) and t.attr in names:
                        writers.setdefault(t.attr, set()).add(fn.name)
    return writers


class TestChessLogControllerStoreIsPrivate(unittest.TestCase):
    """The per-game stores belong to ChessLogController: nothing else reads or writes them."""

    _PRIVATE = {
        "_nag_shown_by_game", "_pending_check_runs", "_dirty_games", "_resolved_cache",
        "_cache_version_by_game", "_cached_original_paths", "_multi_cache",
        "_cached_paths_data", "_cached_game_id",
    }

    def test_no_code_outside_the_owner_touches_its_stores(self):
        self.assertEqual(_attribute_uses(self._PRIVATE, {_OWNER_CTRL}), [])

    def test_pending_check_runs_written_only_by_set_and_save(self):
        writers = _writers_by_function(_OWNER_CTRL, "ChessLogController", {"_pending_check_runs"})
        # set_check_run_for_game queues; _save_single_game consumes (pop is a call, not an assignment).
        self.assertEqual(writers, {"_pending_check_runs": {"__init__"}})
        src = (_REPO / _OWNER_CTRL).read_text(encoding="utf-8")
        self.assertEqual(src.count("self._pending_check_runs[id(game)] ="), 1)
        self.assertEqual(src.count("self._pending_check_runs.pop("), 1)

    def test_nag_flag_written_only_by_load_and_confirm(self):
        src = (_REPO / _OWNER_CTRL).read_text(encoding="utf-8")
        # load (_load_into_cache) and should_confirm_extra_moment are the only assignments.
        self.assertEqual(src.count("self._nag_shown_by_game[gid] ="), 2)


class TestEntryFlagWritersAreTheEditPaths(unittest.TestCase):
    """is_shallow / is_vague / check_hash / ignore_* are set only where entries are built or edited."""

    _KEYS = {"is_shallow", "is_vague", "check_hash", "ignore_shallow", "ignore_text_hash"}
    _ALLOWED = {
        "app/services/chess_log_storage_service.py",       # make_entry / flag normalisation
        "app/views/dialogs/show_tags_dialog.py",           # Show Logged Moments edits (committed on Save)
        "app/views/dialogs/show_shallow_tags_dialog.py",   # Check Logs verdicts (committed on Save)
    }

    def test_entry_flag_keys_assigned_only_in_allowed_files(self):
        offenders = []
        for rel, tree in _app_trees():
            if rel in self._ALLOWED:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                                and t.slice.value in self._KEYS):
                            offenders.append((rel, node.lineno))
        self.assertEqual(offenders, [])

    def test_check_hash_is_named_only_where_it_is_written_or_read_for_an_edit(self):
        files = sorted(
            rel for rel, _ in _app_trees()
            if "check_hash" in (_REPO / rel).read_text(encoding="utf-8")
        )
        self.assertEqual(files, [
            "app/controllers/chess_log_controller.py",
            "app/services/chess_log_storage_service.py",
            "app/views/dialogs/show_shallow_tags_dialog.py",
            "app/views/dialogs/show_tags_dialog.py",
        ])


class TestChartsTabStateIsWrittenByItsController(unittest.TestCase):
    """Source, player, colour, results, model override and Tokens live in ChessLogChartsController."""

    _STATE = {
        "_cached_narrative", "_cached_narrative_flags", "_cached_narrative_usage",
        "_cached_narrative_counts", "_cached_narrative_generated_at",
        "_cached_narrative_model_label", "_cached_shallow_keys", "_cached_vague_keys",
        "_cached_shallow_usage", "_cached_shallow_model_label", "_cached_shallow_timestamp",
        "_last_players", "_last_chart_events", "_player_explicit_selected",
        "_narrative_model_override", "_narrative_token_limit", "_last_game_set_key",
        "_color_filter", "_source_selection", "_current_player",
    }
    # Player Stats has its own, unrelated _source_selection / _current_player.
    _OTHER_OWNERS = {_CHARTS_CTRL, "app/controllers/player_stats_controller.py"}

    def test_views_and_other_code_never_touch_the_state(self):
        self.assertEqual(_attribute_uses(self._STATE, self._OTHER_OWNERS), [])

    def test_state_is_written_only_by_its_named_methods(self):
        cache = {"_clear_result_cache"}
        expected = {
            "_source_selection": {"set_source_selection"},
            "_current_player": {"set_player_selection", "clear_player_selection"},
            "_player_explicit_selected": {"set_source_selection", "set_player_selection",
                                          "clear_player_selection"},
            "_color_filter": {"set_color_filter"},
            "_last_chart_events": set(),   # replaced only by the controller's own signal hooks
            "_last_players": {"set_source_selection", "_on_players_ready"},
            "_narrative_token_limit": {"set_narrative_token_limit"},
            "_narrative_model_override": {"set_narrative_model_override", "on_ai_settings_changed"},
            "_last_game_set_key": cache | {"_schedule_charts_refresh"},
            "_cached_shallow_keys": cache | {"_finish_shallow_run"},
            "_cached_vague_keys": cache | {"_finish_shallow_run"},
            "_cached_shallow_usage": cache | {"_finish_shallow_run"},
            "_cached_shallow_model_label": cache | {"_finish_shallow_run"},
            "_cached_shallow_timestamp": cache | {"_finish_shallow_run"},
        }
        for attr in ("", "_flags", "_usage", "_counts", "_generated_at", "_model_label"):
            expected["_cached_narrative" + attr] = cache | {
                "_on_narrative_thread_ready", "_on_narrative_thread_failed"}
        writers = _writers_by_function(_CHARTS_CTRL, "ChessLogChartsController", self._STATE)
        for attr, methods in writers.items():
            self.assertTrue(methods - {"__init__"} <= expected[attr], (attr, methods))
        self.assertEqual(set(writers), self._STATE)


class TestChessLogSettingsHaveOneWritePath(unittest.TestCase):
    """Chess Log settings are written only through UserSettingsService.update_chess_log_settings."""

    def test_callers_are_the_known_settings_writers(self):
        callers = set()
        for rel, tree in _app_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "update_chess_log_settings":
                    callers.add(rel)
        self.assertEqual(callers, {
            "app/main_window.py",                                   # highlight-in-list toggle
            _CHARTS_CTRL,                                           # Chess Log AI timeout, chart preferences
            "app/views/dialogs/chess_log_settings_dialog.py",       # Chess Log Settings dialog
        })


if __name__ == "__main__":
    unittest.main()

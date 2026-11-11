"""The one write path for a Check Logs run's check record (#98; owner table in doc/chess_log.md).

``commit_check_record`` is the only code that stamps ``check_hash``, clears stale
``is_shallow`` / ``is_vague`` flags on checked answers, queues ``_check_run`` and
saves the touched games after a live Check Logs run.  It takes plain data, so it
has no UI dependency: the Check Logs dialog's Save passes the decisions from its
rows; the Nothing Flagged Save passes none.  Writes go through the Chess Log
controller's own methods (``replace_entries_at_path_for_game``,
``set_check_run_for_game``, ``save_games``), which stay the owners of the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from app.services.chess_log_storage_service import ChessLogStorageService

_WHY_CATS = ("Why1", "Why2", "Why3", "Why4")


@dataclass(frozen=True)
class CheckRowDecision:
    """What the dialog's Save decided for one flagged row (one moment + preset).

    entries: the row's entries as Save would write them, before check_hash stamping.
    original: the stored entries when the dialog opened.
    baseline: the original entries with the run's verdicts stamped (the "unchanged" reference).
    force_write: write even when entries equal baseline (missing chip flags to repair).
    """
    game: Any
    path_key: str
    preset: str
    entries: List[Dict[str, Any]]
    original: List[Dict[str, Any]]
    baseline: List[Dict[str, Any]]
    force_write: bool = False


def _normalize(entries: List[Dict[str, Any]]) -> List[Tuple]:
    """(cat, why, ignore_shallow, ignore_text_hash, is_shallow, is_vague) tuples sorted for change detection."""
    return sorted(
        (
            e.get("cat", ""), e.get("why", ""),
            bool(e.get("ignore_shallow")), e.get("ignore_text_hash"),
            bool(e.get("is_shallow")), bool(e.get("is_vague")),
        )
        for e in entries
    )


def _key(game: Any, path_key: str, preset: str, cat: str) -> Tuple:
    return (game, path_key, preset, cat if preset == "3x3" else "")


def _stamp_shown_row(
    row: CheckRowDecision, classified_keys: FrozenSet
) -> List[Dict[str, Any]]:
    """Stamp check_hash on shown-row entries that were classified AND whose text is unchanged.

    Edited answers stay unchecked; honoured Ignores are excluded (they already count as checked).
    """
    if not classified_keys:
        return row.entries
    orig_by_cat = {e.get("cat", ""): (e.get("why") or "").strip() for e in row.original}
    result = []
    for e in row.entries:
        cat = e.get("cat", "")
        in_cls = _key(row.game, row.path_key, row.preset, cat) in classified_keys
        if in_cls and not ChessLogStorageService.is_entry_ignore_honoured(e):
            why = (e.get("why") or "").strip()
            if why:
                orig_key = cat if row.preset == "3x3" else next(iter(orig_by_cat), "")
                if why == orig_by_cat.get(orig_key, ""):
                    e = dict(e)
                    e["check_hash"] = ChessLogStorageService.compute_check_hash(why)
        result.append(e)
    return result


def _moment_has_flag(game: Any, pk: str, preset: str, flagged_keys: FrozenSet) -> bool:
    if preset == "3x3":
        return any((game, pk, "3x3", cat) in flagged_keys for cat in _WHY_CATS)
    return (game, pk, preset, "") in flagged_keys


def _stamp_hash(e_copy: Dict[str, Any]) -> bool:
    """Set check_hash on a non-blank answer; True when it changed."""
    why = (e_copy.get("why") or "").strip()
    if not why:
        return False
    new_hash = ChessLogStorageService.compute_check_hash(why)
    if e_copy.get("check_hash") == new_hash:
        return False
    e_copy["check_hash"] = new_hash
    return True


def commit_check_record(
    controller,
    games_in_scope: Iterable,
    rows: Iterable[CheckRowDecision],
    shallow_keys: FrozenSet,
    vague_keys: FrozenSet,
    classified_keys: FrozenSet,
    check_run_info: Optional[Dict[str, str]],
) -> Set:
    """Write a live Check Logs run's results; returns the set of games saved.

    a) rows: the dialog's shown rows, written when they changed.
    b) classified-but-not-shown answers: stale flags cleared, check_hash stamped
       (scoped to ``classified_keys``; unparsed, Ignored and blank answers untouched).
    c) ``_check_run`` queued for every game the run touched.
    Then ``controller.save_games`` writes the PGNs and marks each database unsaved.
    Nothing is written unless this is called (an explicit Save).
    """
    games_in_scope = list(games_in_scope)
    shallow_keys = frozenset(shallow_keys)
    vague_keys = frozenset(vague_keys)
    classified_keys = frozenset(classified_keys)
    flagged_keys = shallow_keys | vague_keys
    affected: set = set()

    # a) Shown rows.
    for row in rows:
        new_entries = _stamp_shown_row(row, classified_keys)
        if _normalize(new_entries) != _normalize(row.baseline) or row.force_write:
            controller.replace_entries_at_path_for_game(
                row.game, row.path_key, row.preset, new_entries
            )
            affected.add(row.game)

    # b) Classified-but-not-shown entries.
    for game in games_in_scope:
        tags = controller.get_tags_for_game(game)
        for path_key, entries in tags.items():
            by_preset: Dict[str, List[Dict[str, Any]]] = {}
            for e in entries:
                by_preset.setdefault(e.get("preset", ""), []).append(e)
            for preset, preset_entries in by_preset.items():
                if preset == "3x3":
                    new_list = []
                    changed = False
                    for e in preset_entries:
                        cat = e.get("cat", "")
                        in_cls = (game, path_key, preset, cat) in classified_keys
                        in_flag = (game, path_key, preset, cat) in flagged_keys
                        ignore_honoured = ChessLogStorageService.is_entry_ignore_honoured(e)
                        if in_cls and not in_flag:
                            e_copy = dict(e)
                            # Never stale-clear an entry whose Ignore is still honoured.
                            if not ignore_honoured and (e.get("is_shallow") or e.get("is_vague")):
                                # Editing the text invalidates the Ignore too; never leave
                                # ignore_shallow=True with no chip flag.
                                for k in ("is_shallow", "is_vague", "ignore_shallow", "ignore_text_hash"):
                                    e_copy.pop(k, None)
                                changed = True
                            if not ignore_honoured and _stamp_hash(e_copy):
                                changed = True
                            new_list.append(e_copy)
                        else:
                            new_list.append(e)
                    if changed:
                        controller.replace_entries_at_path_for_game(game, path_key, preset, new_list)
                        affected.add(game)
                else:
                    if (game, path_key, preset, "") not in classified_keys:
                        continue
                    if _moment_has_flag(game, path_key, preset, flagged_keys):
                        continue  # a shown row
                    new_list = []
                    changed = False
                    for e in preset_entries:
                        ignore_honoured = ChessLogStorageService.is_entry_ignore_honoured(e)
                        e_copy = dict(e)
                        if not ignore_honoured and (e.get("is_shallow") or e.get("is_vague")):
                            for k in ("is_shallow", "is_vague"):
                                e_copy.pop(k, None)
                            changed = True
                        if not ignore_honoured and _stamp_hash(e_copy):
                            changed = True
                        new_list.append(e_copy)
                    if changed:
                        controller.replace_entries_at_path_for_game(game, path_key, preset, new_list)
                        affected.add(game)

    # c) _check_run for every game the run touched.
    if check_run_info and classified_keys:
        for cg in {key[0] for key in classified_keys}:
            controller.set_check_run_for_game(cg, check_run_info)
            affected.add(cg)

    if affected:
        controller.save_games(affected)
    return affected

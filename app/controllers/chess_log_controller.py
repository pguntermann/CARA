"""Controller for Chess Log — per-move player self-diagnosis tagging."""

from __future__ import annotations

import hashlib
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chess.pgn

from app.controllers.game_controller import GameController
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.pgn_variation_path import decode_path, encode_path, node_at_path


class ChessLogController:
    """Controller for Chess Log tagging.

    Maintains an in-memory cache of the current game's moments (paths_data)
    and writes them back to the PGN tag only on an explicit save gesture,
    matching the Annotations / Notes explicit-save convention.

    Lifecycle:
    - Instantiated by AppController alongside NotesController.
    - Connects to game_model.active_game_changed to reload cache on game switch.
    - Views call add_moment_at_active_path() on user action, then
      save_tags_for_current_game() via the Chess Log menu or Ctrl+Alt+L.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        game_controller: GameController,
        database_controller=None,
        user_settings_service=None,
    ) -> None:
        self.config = config
        self._game_controller = game_controller
        self._database_controller = database_controller
        self._user_settings_service = user_settings_service
        self._cached_paths_data: Dict[str, List[Dict[str, Any]]] = {}
        self._cached_game_id: Optional[int] = None
        self._cached_game: Optional[Any] = None  # game object for the active game

        # Multi-game cache for Tags Report and save-all.  Keyed by id(game) so
        # two databases with the same sequential game_number cannot collide.
        # The active game lives in _cached_paths_data/_cached_game_id; inactive
        # games live here.  Games move between stores on active-game transitions.
        self._multi_cache: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}  # keyed by id(game)
        self._dirty_games: Dict[int, Any] = {}  # keyed by id(game) -> GameData

        # Nag persistence: once the "more than three moments?" nag has been shown
        # for a game, it is suppressed for the rest of the session (global flag)
        # and for all future sessions for that specific game (per-game flag
        # persisted in the CARAChessLog payload).
        self._nag_shown_by_game: Dict[int, bool] = {}  # keyed by id(game)
        self._nag_shown_this_session: bool = False

        # Original on-disk paths snapshot per game, keyed by id(game).  Captured
        # at every cache-load site (from a fresh load_tags disk read) and
        # refreshed from disk after every successful store_tags.  Passed as
        # original_paths= to activate the save-side orphan guard: new
        # unresolvable path_keys are refused, pre-existing orphans pass through
        # byte-for-byte.
        self._cached_original_paths: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}

        # Memoized resolved view (orphan-filtered) per game, keyed by id(game).
        # Value: (raw_version_int, pgn_blake2b_hex, resolved_dict).
        # Invalidated when raw_version bumps (in-memory write) or the PGN
        # content hash changes (e.g. analysis written to game.pgn).
        self._resolved_cache: Dict[int, Tuple[int, str, Dict[str, List[Dict[str, Any]]]]] = {}
        # Write-counter per game, bumped by every in-memory cache mutation.
        # Keyed by id(game); reset to 0 on fresh load.
        self._cache_version_by_game: Dict[int, int] = {}

        # Per-game _check_run override: set by ShowShallowTagsDialog._on_save after
        # a Check Logs run to write the model+date to the PGN.  _save_single_game
        # consumes and clears each entry after writing.
        self._pending_check_runs: Dict[int, Dict[str, str]] = {}  # keyed by id(game)

        game_model = game_controller.get_game_model()
        game_model.active_game_changed.connect(self._on_active_game_changed)
        self._connect_to_database_panel_model()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_active_preset(self) -> str:
        """Return the currently active Chess Log preset name (e.g. 'CLAMP')."""
        if self._user_settings_service is None:
            return "CLAMP"
        preset = self._user_settings_service.get_chess_log().get("active_preset", "CLAMP")
        return preset if preset in {"CLAMP", "CCT", "3x3"} else "CLAMP"

    def preset_for_logging(self) -> str:
        """Return the preset to use when opening MomentDialog at the active path.

        1. Active path has entries → most-common preset among them.
        2. Game has entries but not at this path → most-common across the game.
        3. No entries → active-preset setting.
        Tie-break: prefer the setting; otherwise alphabetically first.
        """
        setting = self.get_active_preset()
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return setting
        path_key = encode_path(self._game_controller.get_game_model().get_active_path())
        tags = self.get_tags_for_game(game)
        path_entries = tags.get(path_key, [])
        if path_entries:
            return _pick_preset(path_entries, setting)
        if tags:
            return _pick_preset_in_game(tags, setting)
        return setting

    def get_tags_for_current_game(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return in-memory moments for the active game (orphan-filtered copy)."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return {}
        if id(game) != self._cached_game_id:
            self._load_into_cache(game)
        return self._resolved_view(self._cached_paths_data, game)

    def get_entries_at_active_path(self) -> List[Dict[str, Any]]:
        """Return the entries stored at the current active path, or [] if none."""
        data = self.get_tags_for_current_game()
        path_key = encode_path(self._game_controller.get_game_model().get_active_path())
        return list(data.get(path_key, []))

    def add_moment_at_active_path(
        self,
        entries: List[Dict[str, Any]],
        parent_widget=None,
    ) -> bool:
        """Append one or more entries as a single moment at the active path.

        Args:
            entries: One or more {preset, cat, why, ...} dicts, all for the same
                     moment.  CCT with two letters = two entries, still one moment.
            parent_widget: Unused; kept for signature compatibility.

        Returns:
            True if the moment was added; False if there was nothing to add.
        """
        if not entries:
            return False
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return False
        if id(game) != self._cached_game_id:
            self._load_into_cache(game)

        path_key = encode_path(self._game_controller.get_game_model().get_active_path())
        tagged = [ChessLogStorageService.make_entry(e["preset"], e["cat"], e.get("why", "")) for e in entries]
        preset_of_new = tagged[0].get("preset") if tagged else None
        if path_key in self._cached_paths_data:
            if preset_of_new:
                kept = [e for e in self._cached_paths_data[path_key] if e.get("preset") != preset_of_new]
                self._cached_paths_data[path_key] = kept + tagged
            else:
                self._cached_paths_data[path_key].extend(tagged)
        else:
            self._cached_paths_data[path_key] = tagged
        self._cache_version_by_game[id(game)] = self._cache_version_by_game.get(id(game), 0) + 1
        return True

    def save_tags_for_current_game(self) -> bool:
        """Persist the in-memory cache to the active game's PGN tag."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return False
        gid = id(game)
        check_run = self._pending_check_runs.pop(gid, None)
        ok = ChessLogStorageService.store_tags(
            game, self._cached_paths_data, self.config,
            nag_shown=self._nag_shown_by_game.get(self._cached_game_id, False),
            original_paths=self._cached_original_paths.get(gid),
            check_run=check_run,
        )
        if ok:
            self._dirty_games.pop(gid, None)
            # Refresh the snapshot from disk — NOT from the paths_data we passed
            # in — so a refused new orphan isn't recorded as pre-existing on the
            # next save, which would defeat the guard.
            self._cached_original_paths[gid] = ChessLogStorageService.load_tags(game)
            self._cache_version_by_game[gid] = self._cache_version_by_game.get(gid, 0) + 1
            self._game_controller.get_game_model().metadata_updated.emit()
            self._mark_database_unsaved(game)
        return ok

    def clear_tags_for_current_game(self) -> bool:
        """Clear all moments for the active game (in-memory; needs save to persist)."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return False
        self._cached_paths_data = {}
        ok = ChessLogStorageService.clear_tags(game)
        if ok:
            # clear_tags writes the final state immediately, so nothing is left to
            # save for this game — remove it from _dirty_games to prevent
            # save_all_dirty_games from saving it again with empty data.
            self._dirty_games.pop(id(game), None)
            # On-disk tag is gone; refresh the snapshot to match.
            self._cached_original_paths[id(game)] = {}
            self._cache_version_by_game[id(game)] = self._cache_version_by_game.get(id(game), 0) + 1
            self._game_controller.get_game_model().metadata_updated.emit()
            self._mark_database_unsaved(game)
        return ok

    def game_has_any_tags(self) -> bool:
        """Return True if the current game has any tagged entries across any preset."""
        data = self.get_tags_for_current_game()
        return any(data.values())

    def replace_entries_at_path(
        self,
        path_key: str,
        preset: str,
        entries: List[Dict[str, Any]],
        view=None,
    ) -> None:
        """Replace all entries for *preset* at *path_key* in the in-memory cache.

        Analogous to add_moment_at_active_path but takes an explicit path_key
        instead of the game model's active path.  Only the named preset's entries
        at that path are replaced; other presets at the same path are preserved.
        In-memory only — call save_tags_for_current_game() to persist to PGN.
        """
        tagged = [
            ChessLogStorageService.make_entry(
                e["preset"], e["cat"], e.get("why", ""),
                ignore_shallow=bool(e.get("ignore_shallow")),
                is_shallow=bool(e.get("is_shallow")),
                is_vague=bool(e.get("is_vague")),
                ignore_text_hash=e.get("ignore_text_hash"),
                check_hash=e.get("check_hash"),
            )
            for e in entries
        ]
        if path_key in self._cached_paths_data:
            kept = [e for e in self._cached_paths_data[path_key] if e.get("preset") != preset]
            merged = kept + tagged
            if merged:
                self._cached_paths_data[path_key] = merged
            else:
                del self._cached_paths_data[path_key]
        elif tagged:
            self._cached_paths_data[path_key] = tagged
        if self._cached_game is not None:
            gid = id(self._cached_game)
            self._cache_version_by_game[gid] = self._cache_version_by_game.get(gid, 0) + 1

    def get_tags_for_game(self, game) -> Dict[str, List[Dict[str, Any]]]:
        """Return moments for any game (orphan-filtered copy).

        Checks the multi-cache first; falls back to disk.  The active game's
        moments are always read from the single-game cache to stay coherent with
        in-progress edits.
        """
        gid = id(game)
        if gid == self._cached_game_id:
            raw = self._cached_paths_data
        else:
            if gid not in self._multi_cache:
                loaded = ChessLogStorageService.load_tags(game)
                self._multi_cache[gid] = loaded
                # Snapshot the disk state for the save-side orphan guard.
                self._cached_original_paths[gid] = dict(loaded)
            raw = self._multi_cache[gid]
        return self._resolved_view(raw, game)

    def replace_entries_at_path_for_game(
        self,
        game,
        path_key: str,
        preset: str,
        entries: List[Dict[str, Any]],
    ) -> None:
        """Replace all entries for *preset* at *path_key* for any game.

        Writes to whichever store owns this game (single-game cache if it is
        the active game, multi-cache otherwise).  Marks the game dirty so
        save_all_dirty_games() will persist it later.
        """
        gid = id(game)
        tagged = [
            ChessLogStorageService.make_entry(
                e["preset"], e["cat"], e.get("why", ""),
                ignore_shallow=bool(e.get("ignore_shallow")),
                is_shallow=bool(e.get("is_shallow")),
                is_vague=bool(e.get("is_vague")),
                ignore_text_hash=e.get("ignore_text_hash"),
                check_hash=e.get("check_hash"),
            )
            for e in entries
        ]
        if gid == self._cached_game_id:
            data = self._cached_paths_data
        else:
            if gid not in self._multi_cache:
                loaded = ChessLogStorageService.load_tags(game)
                self._multi_cache[gid] = loaded
                self._cached_original_paths[gid] = dict(loaded)
            data = self._multi_cache[gid]

        if path_key in data:
            kept = [e for e in data[path_key] if e.get("preset") != preset]
            merged = kept + tagged
            if merged:
                data[path_key] = merged
            else:
                del data[path_key]
        elif tagged:
            data[path_key] = tagged

        self._dirty_games[gid] = game
        self._cache_version_by_game[gid] = self._cache_version_by_game.get(gid, 0) + 1

    def save_games(self, games: Iterable) -> Tuple[int, int]:
        """Persist the given games' Chess Log data and mark each DB unsaved.

        Writes the full in-memory cache for each game — including any pending
        Log-this-Moment edits on the same game — then marks its database unsaved.
        Commit granularity is the game, not the individual edit: all pending
        changes for a game land in a single store_tags call.

        Returns:
            (n_saved, n_failed)
        """
        saved = failed = 0
        for game in games:
            if self._save_single_game(game):
                saved += 1
            else:
                failed += 1
        return saved, failed

    def save_all_dirty_games(self) -> Tuple[int, int]:
        """Persist every dirty game via ChessLogStorageService.store_tags.

        Returns:
            (n_saved, n_failed)

        In addition to games tracked in _dirty_games (which covers edits made via
        ShowTagsDialog / ShowShallowTagsDialog), this also saves the active game's
        single-game cache when it has unsaved changes.  add_moment_at_active_path
        writes only to _cached_paths_data without touching _dirty_games, so without
        this check a Ctrl+Alt+Shift+L after tagging would silently skip the current game.
        """
        self._prune_dirty_games_against_open_databases()
        saved = failed = 0

        # Save the active game's single-game cache if it has unsaved changes and is
        # not already captured in _dirty_games (the loop below handles that case).
        current_game = self._game_controller.get_game_model().active_game
        if current_game is not None and id(current_game) not in self._dirty_games:
            if self.has_unsaved_changes():
                if self._save_single_game(current_game):
                    saved += 1
                    self._game_controller.get_game_model().metadata_updated.emit()
                else:
                    failed += 1

        for gid, game in list(self._dirty_games.items()):
            if self._save_single_game(game):
                saved += 1
            else:
                failed += 1
        return saved, failed

    def set_check_run_for_game(self, game: Any, check_run: Dict[str, str]) -> None:
        """Queue a _check_run dict to be written the next time this game is saved.

        Called by ShowShallowTagsDialog._on_save after a successful Check Logs run,
        once per game that had at least one note classified.  _save_single_game
        consumes and clears the entry after writing.
        """
        self._pending_check_runs[id(game)] = check_run

    def get_check_run_for_game(self, game: Any) -> Optional[Dict[str, Any]]:
        """Return the stored _check_run dict for a game, or None if absent."""
        return ChessLogStorageService.load_check_run(game)

    def get_shallow_vague_keys(self, games) -> Tuple[FrozenSet, FrozenSet]:
        """Return (shallow_keys, vague_keys) from stored is_shallow/is_vague flags.

        Keys are 4-tuples (game, path_key, preset, cat) keyed by game object.
        CLAMP/CCT entries use cat="" ; 3x3 entries use the actual cat string.
        """
        shallow: set = set()
        vague: set = set()
        for game in games:
            tags = self.get_tags_for_game(game)
            for path_key, entries in tags.items():
                by_preset: Dict[str, list] = {}
                for e in entries:
                    by_preset.setdefault(e.get("preset", ""), []).append(e)
                for preset, preset_entries in by_preset.items():
                    for e in preset_entries:
                        if not ChessLogStorageService.entry_has_flag(e):
                            continue
                        cat = e.get("cat", "")
                        key = (game, path_key, preset, cat if preset == "3x3" else "")
                        if e.get("is_shallow"):
                            shallow.add(key)
                        if e.get("is_vague"):
                            vague.add(key)
        return frozenset(shallow), frozenset(vague)

    def has_any_checked_answer(self, games) -> bool:
        """Return True if any non-blank answer in games has been checked by Check Logs.

        Checked means: matching check_hash, legacy is_shallow/is_vague flag, or
        honoured ignore_shallow.
        """
        for game in games:
            tags = self.get_tags_for_game(game)
            for entries in tags.values():
                for e in entries:
                    if (e.get("why") or "").strip() and ChessLogStorageService.is_entry_checked(e):
                        return True
        return False

    def count_unchecked_answers(self, games) -> int:
        """Count non-blank answers that have not been checked by Check Logs yet.

        CLAMP/CCT: counted per distinct note text per moment (same unit the
        classifier receives — one note may have multiple entries with different cats
        but only one is counted).  3x3: counted per Why answer independently.
        """
        count = 0
        for game in games:
            tags = self.get_tags_for_game(game)
            for entries in tags.values():
                by_preset: Dict[str, list] = {}
                for e in entries:
                    by_preset.setdefault(e.get("preset", ""), []).append(e)
                for preset, preset_entries in by_preset.items():
                    if preset == "3x3":
                        for e in preset_entries:
                            why = (e.get("why") or "").strip()
                            if why and not ChessLogStorageService.is_entry_checked(e):
                                count += 1
                    else:
                        # Per distinct note text per moment.
                        seen: Dict[str, bool] = {}  # why_text → is_checked
                        for e in preset_entries:
                            why = (e.get("why") or "").strip()
                            if not why:
                                continue
                            chk = ChessLogStorageService.is_entry_checked(e)
                            if why not in seen:
                                seen[why] = chk
                            elif chk:
                                seen[why] = True
                        for chk in seen.values():
                            if not chk:
                                count += 1
        return count

    def _save_single_game(self, game) -> bool:
        """Persist one game's Chess Log cache and mark its DB unsaved.

        Resolves which store owns the game (single-game cache if it is the active
        game, multi-cache otherwise), calls store_tags, refreshes the on-disk
        snapshot, bumps the version counter, marks the DB unsaved, and removes
        the game from _dirty_games.  Returns True on success.
        """
        gid = id(game)
        data = (
            self._cached_paths_data
            if gid == self._cached_game_id
            else self._multi_cache.get(gid, {})
        )
        # Consume any pending _check_run override from a Check Logs Save.
        # When present, store_tags writes the new run info; when absent (None),
        # store_tags auto-preserves whatever _check_run is already in the PGN.
        check_run = self._pending_check_runs.pop(gid, None)
        ok = ChessLogStorageService.store_tags(
            game, data, self.config,
            nag_shown=self._nag_shown_by_game.get(gid, False),
            original_paths=self._cached_original_paths.get(gid),
            check_run=check_run,
        )
        if ok:
            self._cached_original_paths[gid] = ChessLogStorageService.load_tags(game)
            self._cache_version_by_game[gid] = self._cache_version_by_game.get(gid, 0) + 1
            self._mark_database_unsaved(game)
            self._dirty_games.pop(gid, None)
        return ok

    def has_dirty_games(self) -> bool:
        """Return True if any multi-game edits are pending a save."""
        return bool(self._dirty_games)

    def has_unsaved_changes(self) -> bool:
        """Return True if in-memory cache differs from what's stored in the PGN."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return False
        stored = ChessLogStorageService.load_tags(game)
        return self._cached_paths_data != stored

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_active_game_changed(self, game) -> None:
        """Reload cache when the active game changes.

        Rule B (deactivation): flush the outgoing active game into _multi_cache
        so edits made via the Tags Report survive the game switch.

        Rule A (activation): promote from _multi_cache if present, so edits to
        an inactive game made via the Tags Report are visible once it becomes active.
        """
        # Rule B — flush outgoing active game into multi-cache
        old_gid = self._cached_game_id
        old_game = self._cached_game
        if old_gid is not None and (self._cached_paths_data or old_gid in self._dirty_games):
            self._multi_cache[old_gid] = dict(self._cached_paths_data)
            # Ensure save_all_dirty_games can reach this game.  add_moment_at_active_path
            # and replace_entries_at_path only write _cached_paths_data; a game that has
            # unsaved UI edits but was never touched by replace_entries_at_path_for_game
            # (the only method that explicitly marks dirty) would be silently skipped by
            # save_all.  setdefault preserves any richer game object already in the map.
            if old_game is not None and old_gid not in self._dirty_games and self._outgoing_has_real_edits():
                self._dirty_games[old_gid] = old_game

        if game is None:
            # Flush outgoing active game's REAL edits into dirty-set before
            # clearing pointers.  Compare against the OUTGOING game's disk
            # snapshot — the game model's active_game is already None here.
            if old_gid is not None and self._outgoing_has_real_edits():
                self._multi_cache[old_gid] = dict(self._cached_paths_data)
                self._dirty_games.setdefault(old_gid, old_game)
            self._cached_paths_data = {}
            self._cached_game_id = None
            self._cached_game = None
            # Prune cache entries whose GameData is no longer in any open DB
            # (reload / close).  Preserves dirty entries belonging to other
            # still-open databases.
            self._prune_dirty_games_against_open_databases()
            for gid in list(self._multi_cache.keys()):
                if gid not in self._dirty_games:
                    del self._multi_cache[gid]
            for gid in list(self._nag_shown_by_game.keys()):
                if gid not in self._dirty_games:
                    del self._nag_shown_by_game[gid]
            for gid in list(self._cached_original_paths.keys()):
                if gid not in self._dirty_games:
                    del self._cached_original_paths[gid]
            for gid in list(self._resolved_cache.keys()):
                if gid not in self._dirty_games:
                    del self._resolved_cache[gid]
            for gid in list(self._cache_version_by_game.keys()):
                if gid not in self._dirty_games:
                    del self._cache_version_by_game[gid]
        else:
            self._load_into_cache(game)

    def _load_into_cache(self, game) -> None:
        """Load *game* into the single-game cache.

        Rule A: check _multi_cache first so unsaved edits on an inactive game
        survive being made active.  Remove from _multi_cache once promoted
        (a game lives in exactly one store at a time).

        On any fresh disk read (either branch), capture a fresh on-disk
        snapshot into _cached_original_paths for the save-side orphan guard.
        On _multi_cache promotion the snapshot that was captured on first
        peek is already correct — don't overwrite with the possibly-edited
        in-memory dict.
        """
        gid = id(game)
        # Invalidate the resolved-view cache so the next call recomputes from
        # the newly-loaded data rather than returning a stale entry.
        self._resolved_cache.pop(gid, None)
        self._cache_version_by_game[gid] = 0
        if gid in self._multi_cache:
            self._cached_paths_data = self._multi_cache.pop(gid)
            # Keep any in-session nag flag set for this game; don't overwrite from disk.
            # Snapshot already captured on first peek via get_tags_for_game /
            # replace_entries_at_path_for_game — leave it alone.
            if gid not in self._cached_original_paths:
                self._cached_original_paths[gid] = ChessLogStorageService.load_tags(game)
        else:
            loaded = ChessLogStorageService.load_tags(game)
            self._cached_paths_data = loaded
            self._cached_original_paths[gid] = dict(loaded)
            self._nag_shown_by_game[gid] = ChessLogStorageService.load_nag_shown(game)
        self._cached_game_id = gid
        self._cached_game = game

    def _connect_to_database_panel_model(self) -> None:
        if self._database_controller is None:
            return
        panel_model = self._database_controller.get_panel_model()
        if not panel_model:
            return
        try:
            panel_model.active_database_changed.disconnect(self._on_active_database_changed)
        except (RuntimeError, TypeError):
            pass
        panel_model.active_database_changed.connect(self._on_active_database_changed)

    def _on_active_database_changed(self, _database) -> None:
        """Preserve unsaved Chess Log edits when the active database changes.

        Flush the outgoing active game's real edits into _multi_cache +
        _dirty_games (compared against the outgoing game's own disk snapshot
        — the game model's active_game may already be None or newly-switched
        by the time this handler runs).  Preserve _dirty_games byte-for-byte
        and prune only cache-only entries belonging to games no longer in any
        open database.
        """
        old_gid = self._cached_game_id
        old_game = self._cached_game
        if old_gid is not None and self._outgoing_has_real_edits():
            self._multi_cache[old_gid] = dict(self._cached_paths_data)
            self._dirty_games.setdefault(old_gid, old_game)

        self._cached_game = None
        self._cached_game_id = None
        self._cached_paths_data = {}

        self._prune_dirty_games_against_open_databases()

        for gid in list(self._multi_cache.keys()):
            if gid not in self._dirty_games:
                del self._multi_cache[gid]
        for gid in list(self._nag_shown_by_game.keys()):
            if gid not in self._dirty_games:
                del self._nag_shown_by_game[gid]
        for gid in list(self._cached_original_paths.keys()):
            if gid not in self._dirty_games:
                del self._cached_original_paths[gid]
        for gid in list(self._resolved_cache.keys()):
            if gid not in self._dirty_games:
                del self._resolved_cache[gid]
        for gid in list(self._cache_version_by_game.keys()):
            if gid not in self._dirty_games:
                del self._cache_version_by_game[gid]

    def _outgoing_has_real_edits(self) -> bool:
        """True iff the current outgoing-game cache differs from its on-disk tag.

        Compares against load_tags(self._cached_game) rather than
        has_unsaved_changes(), because the game model's active_game may already
        be None (close/clear) or the newly-switched game by the time this
        handler runs.
        """
        if self._cached_game is None:
            return False
        try:
            stored = ChessLogStorageService.load_tags(self._cached_game)
        except Exception:
            return bool(self._cached_paths_data)
        return self._cached_paths_data != stored

    def _prune_dirty_games_against_open_databases(self) -> None:
        """Drop _dirty_games (and companion dicts) for games no longer in any
        open database. Prevents stale GameData refs from being written to by
        save_all_dirty_games and from being double-counted.
        """
        if self._database_controller is None:
            return
        panel_model = self._database_controller.get_panel_model()
        if panel_model is None:
            return
        live_ids: set = set()
        for db_model in panel_model.get_all_database_models():
            for g in db_model.get_all_games():
                live_ids.add(id(g))
        for gid in list(self._dirty_games.keys()):
            if gid not in live_ids:
                del self._dirty_games[gid]
                self._multi_cache.pop(gid, None)
                self._nag_shown_by_game.pop(gid, None)
                self._cached_original_paths.pop(gid, None)
                self._resolved_cache.pop(gid, None)
                self._cache_version_by_game.pop(gid, None)

    def _mark_database_unsaved(self, game) -> None:
        if self._database_controller is None or game is None:
            return
        try:
            db_model = self._database_controller.find_database_model_for_game(game)
            if db_model:
                self._database_controller.mark_database_unsaved(db_model)
        except Exception:
            pass

    def _resolved_view(
        self,
        raw: Dict[str, List[Dict[str, Any]]],
        game,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return an orphan-filtered copy of *raw*, memoized per game.

        Memoization key: (write_counter, blake2b-16 of game.pgn).
        Always returns a fresh shallow copy so callers can freely mutate the
        top-level mapping without corrupting the internal cache.

        Orphan detection uses the same logic as load_resolved_paths: a
        path_key is an orphan if node_at_path returns None in the current
        move tree.  Filtering is skipped (full copy returned) when *raw* is
        empty or *game* has no PGN.
        """
        if not raw or not getattr(game, "pgn", None):
            return dict(raw)
        gid = id(game)
        raw_ver = self._cache_version_by_game.get(gid, 0)
        pgn_ver = hashlib.blake2b(game.pgn.encode("utf-8"), digest_size=16).hexdigest()
        cached = self._resolved_cache.get(gid)
        if cached and cached[0] == raw_ver and cached[1] == pgn_ver:
            return dict(cached[2])
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
        except Exception:
            return dict(raw)
        if chess_game is None:
            return dict(raw)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for pk, entries in raw.items():
            path = decode_path(pk)
            if path is not None and node_at_path(chess_game, path) is not None:
                out[pk] = entries
        self._resolved_cache[gid] = (raw_ver, pgn_ver, out)
        return dict(out)

    def should_confirm_extra_moment(self, parent_widget=None) -> bool:
        """Return True if the caller should proceed with opening Tag This Moment.

        Returns False only when: the player is attempting to tag a *new* path,
        the current game already has >= 3 moments, the nag hasn't been shown yet
        for this game or this session, AND the user said "no" to the nag.

        Called by DetailMovesListView._on_tag_moment BEFORE opening MomentDialog
        so the user is asked before investing typing effort — not after.
        """
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return True
        if id(game) != self._cached_game_id:
            self._load_into_cache(game)
        path_key = encode_path(self._game_controller.get_game_model().get_active_path())
        is_new_moment = (
            path_key not in self._cached_paths_data
            or not self._cached_paths_data[path_key]
        )
        if not is_new_moment:
            return True
        if ChessLogStorageService.count_tags(self._resolved_view(self._cached_paths_data, game)) < 3:
            return True
        gid = id(game)
        if self._nag_shown_this_session:
            return True
        if self._nag_shown_by_game.get(gid, False):
            return True
        confirmed = self._confirm_extra_moment(parent_widget)
        # Suppress for the rest of this session and for this game's future sessions
        # regardless of whether the user said Yes or No — the nag fires at most once.
        self._nag_shown_by_game[gid] = True
        self._nag_shown_this_session = True
        return confirmed

    def _confirm_extra_moment(self, parent_widget=None) -> bool:
        """Show the 4th-moment 'Are you sure?' confirmation dialog."""
        try:
            from app.views.dialogs.confirmation_dialog import ConfirmationDialog
            return ConfirmationDialog.show_confirmation(
                self.config,
                "Chess Log — More than three moments?",
                "You already have three tagged moments in this game. "
                "Three tends to be the sweet spot — enough to see a pattern, "
                "few enough that each one still stands out when you review the "
                "game later. Piling on more can dilute the lesson rather than "
                "sharpen it.\n\n"
                "Add this moment anyway?",
                parent_widget,
            )
        except Exception:
            return True


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _pick_preset(path_entries: List[Dict[str, Any]], tiebreak: str) -> str:
    """Return the preset to use for a single path; each method present counts once.

    A CLAMP moment with two categories and a 3x3 moment with three Why entries
    are both one method each.  Tie-break: prefer *tiebreak*, else alphabetical.
    """
    present = {e.get("preset", "") for e in path_entries if e.get("preset", "")}
    if not present:
        return tiebreak
    if len(present) == 1:
        return next(iter(present))
    return tiebreak if tiebreak in present else min(present)


def _pick_preset_in_game(
    tags: Dict[str, List[Dict[str, Any]]], tiebreak: str
) -> str:
    """Return the preset with the most distinct paths (moments) in the game.

    Counts one per path per method — a 3x3 path with three entries still
    contributes 1, same as a CLAMP path with two categories.
    Tie-break: prefer *tiebreak*, else alphabetical.
    """
    counts: Dict[str, int] = {}
    for path_entries in tags.values():
        for p in {e.get("preset", "") for e in path_entries if e.get("preset", "")}:
            counts[p] = counts.get(p, 0) + 1
    if not counts:
        return tiebreak
    max_count = max(counts.values())
    leaders = [p for p, c in counts.items() if c == max_count]
    return tiebreak if tiebreak in leaders else min(leaders)

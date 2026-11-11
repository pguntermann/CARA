# Chess Log — Data-Integrity Audit

Branch: `chess-log-charts` · Audit date: 2026-10-22 · Based on commit `c3e9eed`

---

## 1. Data Holders

All Chess Log runtime state lives in `ChessLogController` (`app/controllers/chess_log_controller.py`). Every
dict below is keyed by `id(game)` (Python object identity), not `game_number`, unless noted.

| Field | Key | Purpose |
|---|---|---|
| `_cached_paths_data` | — (single slot) | Active-game tags; loaded by `_load_into_cache` |
| `_cached_game` | — (single slot) | `GameData` whose tags `_cached_paths_data` holds |
| `_cached_game_id` | — (single slot) | `id(_cached_game)` for fast equality checks |
| `_multi_cache` | `id(game)` | Tags for inactive games edited via ShowTagsDialog |
| `_dirty_games` | `id(game)` | Games with unsaved Chess Log edits |
| `_cached_original_paths` | `id(game)` | On-disk snapshot at load time; used by orphan-path guard on save |
| `_resolved_cache` | `id(game)` | Memoized orphan-filtered view |
| `_cache_version_by_game` | `id(game)` | Version counter for `_resolved_cache` memoization |
| `_nag_shown_by_game` | `id(game)` | Per-game "more than 3 moments" nag-suppression flag |

**Charts-layer caches** (keyed by `GameData` object identity after F5/F6 fix):

| Field | Location | Key |
|---|---|---|
| `_cached_shallow_keys` / `_cached_vague_keys` | `ChessLogChartsController` | `frozenset` of `(game, path_key, preset, cat)` 4-tuples — `game` is the `GameData` object |
| `_last_shallow_keys` / `_last_vague_keys` | `DetailChessLogChartsView` | `frozenset` of `(game, path_key, preset, cat)` 4-tuples |

**Dialog snapshots** (keyed by row index after F3 fix):

| Field | Dialog | Scope at open time |
|---|---|---|
| `_original_snapshot` | `ShowTagsDialog` | Active database only — single DB, collision impossible |
| `_original_snapshot` | `ShowShallowTagsDialog` | Row index `i` (Dict[int, List]) — one entry per row, collision-free |

**Stale-cache note (F5 post-fix):** With game-object keys, `_cached_shallow_keys` holds the old `GameData` objects alive until `_clear_result_cache()` runs. This is a harmless memory hold: Python object identity guarantees a stale `game_A` reference never accidentally matches a different `game_B`, even if both have the same `game_number`. `_clear_result_cache()` is called on source/player/DB-switch but NOT on game delete or DB close — the stale hold exists but causes no false positives.

Canonical on-disk store: `game.pgn` — the `CARAChessLog` PGN header triple written by
`ChessLogStorageService.store_tags`. Transient (in-memory write); reaches disk only when the
owning `DatabaseModel` is saved via File > Save Database.

---

## 2. Write Paths

```
User action                         Method(s)                           Effect
─────────────────────────────────────────────────────────────────────────────────
Add moment at current ply           add_moment_at_active_path()         _cached_paths_data mutated.
                                                                        _dirty_games NOT touched here;
                                                                        game enters _dirty_games only
                                                                        on next game-switch (Rule B).

Edit/delete via ShowTagsDialog      replace_entries_at_path_for_game()  _multi_cache[id(game)] mutated;
                                                                        game explicitly added to
                                                                        _dirty_games.

Edit via ShowShallowTagsDialog      _on_save() → replace_entries_at_path_for_game() per row
                                                                        Same as above.

Explicit save (Ctrl+Alt+Shift+L)    save_all_dirty_games()              Iterates _dirty_games + active
                                    → _save_single_game()               game if not already there;
                                    → ChessLogStorageService.store_tags writes to game.pgn;
                                    → _mark_database_unsaved()          marks DB tab ● for next
                                                                        File > Save Database.

Dialog Save button                  ShowTagsDialog / ShowShallowTagsDialog
                                    → chess_log_controller.save_games() → _save_single_game() per game
```

`replace_entries_at_path` (no `_for_game` suffix, `chess_log_controller.py:189`) mutates
`_cached_paths_data` but does NOT add to `_dirty_games` and does NOT call
`_mark_database_unsaved`. It is called only from tests; no production path calls it.

---

## 3. Lifecycle Matrix

| Event | Handler | Chess Log effect |
|---|---|---|
| User navigates to game G | `_on_active_game_changed(G)` | Rule A: promote from `_multi_cache` or load from disk into `_cached_paths_data`. |
| User navigates away from G | `_on_active_game_changed(new_game)` | Rule B: flush `_cached_paths_data` → `_multi_cache`; mark G dirty **only** if `_outgoing_has_real_edits()` (F2 fixed). |
| All games closed / DB closed | `_on_active_game_changed(None)` | Flush **only** if `_outgoing_has_real_edits()`; prune orphaned cache entries. |
| Active database changes | `_on_active_database_changed()` | Flush only if real edits; prune; clear caches. Uses `_outgoing_has_real_edits()`. |
| Game deleted from DB | `DatabaseModel.remove_games()` | **No signal to ChessLogController.** Game stays in `_dirty_games` — but `save_all_dirty_games()` now calls `_prune_dirty_games_against_open_databases()` first (F1 fixed). |
| DB reloaded from file | `reload_database_from_file()` | **No callers** — dead code today. (See F4.) |
| Sort / reorder games | `DatabaseModel` sort operation | `id(game)` unchanged; all controller caches remain valid. `game_number` is immutable through sort. NO RISK. |

---

## 4. Unsaved-Changes Contract

`has_unsaved_changes()` compares `_cached_paths_data` against `ChessLogStorageService.load_tags(game)`
on every call. It reflects whether the active game's in-memory state diverges from disk.

`has_dirty_games()` returns `bool(_dirty_games)` — whether any multi-game edits are pending save.

`save_all_dirty_games()` calls `_prune_dirty_games_against_open_databases()` **first** (F1 fix),
then iterates `_dirty_games`, then also saves the active game if `has_unsaved_changes()` and it is
not already in `_dirty_games`.

`_dirty_games` is pruned by `_prune_dirty_games_against_open_databases()`, called from:
- `save_all_dirty_games()` (F1 fix — drops deleted games before the save loop)
- `_on_active_game_changed(None)` (existing)
- `_on_active_database_changed()` (existing)

---

## 5. Findings

Severity scale: **DATA LOSS** / **MISPLACED** / **SILENT FAILURE** / **FALSE UNSAVED** / **STALE DISPLAY** / **DESIGN QUESTION** / **NO RISK**

---

### F1 · Deleted game stays in _dirty_games; save_all writes to orphaned object · SILENT FAILURE · **FIXED** (commit *Chess Log: Save All skips games no longer in an open database (#51 F1)*)

**Files:** `database_model.py:620–655`, `chess_log_controller.py:310–366`, `chess_log_controller.py:537–558`, `chess_log_controller.py:560–568`

**Scenario:** User adds Chess Log moments to game A, switches to another game (Rule B puts A in `_dirty_games`), deletes A, then presses Ctrl+Alt+Shift+L.

1. `DatabaseModel.remove_games()` (lines 620–655) removes A from `_games`. No signal reaches `ChessLogController`. A remains in `_dirty_games`.

2. `save_all_dirty_games()` (line 335) iterates `_dirty_games`; calls `_save_single_game(A)`.

3. `_save_single_game` (line 356): `ChessLogStorageService.store_tags(A, data, ...)` writes to `A.pgn` on the orphaned `GameData` object. Returns `True`.

4. Line 364: `_mark_database_unsaved(A)` → `find_database_model_for_game(A)` searches every open DB by object identity. A is no longer in any `_games` list → returns `None`. `_mark_database_unsaved` returns silently (lines 565–568).

5. No database is flagged unsaved. The disk PGN is never updated. The user sees **"Chess Log saved for 1 game"** in the status bar (`main_window.py:1478`) — a false success report. The data went to a detached in-memory object and is garbage-collected when the session ends.

**Why not DATA LOSS:** the user explicitly deleted the game; the SILENT FAILURE is the deceptive "1 game saved" count and the absence of any disk update.

**Confirmed:** CONFIRMED-BY-RUNNING (`test_f1_real_controller.py`). Real `ChessLogController`, real `DatabaseModel`, real `DatabasePanelModel`. Script output:

```
game_a in _dirty_games before delete: True
game_a in db_model after remove: None
game_a still in _dirty_games after remove: True

save_all_dirty_games returned: saved=1, failed=0
mark_unsaved calls after save: 0
db has_unsaved_changes after save: False
game_a still in _dirty_games after save: False

CONFIRMED (F1): save_all reported 1 saved, but mark_database_unsaved was never called
User sees: success toast '1 game(s) saved'. DB never marked unsaved. Disk file unchanged.
```

**Fix:** `save_all_dirty_games()` now calls `self._prune_dirty_games_against_open_databases()` as its first statement. Games removed from all open databases are dropped before the save loop, so the count and the DB-unsaved signal reflect only real saves.

**Test:** `TestF1DeletedGamePruning::test_deleted_game_pruned_before_save_all` in `tests/controllers/test_chess_log_controller.py`. Adds a moment, switches away (game enters `_dirty_games`), removes the game from the live list, asserts `save_all_dirty_games()` returns `(0, 0)` with no `mark_database_unsaved` call and the game absent from `_dirty_games`. Fails before fix, passes after.

---

### F2 · Rule B marks any tagged game dirty on game switch, regardless of edits · FALSE UNSAVED · **FIXED** (commit *Chess Log: don't mark unedited games dirty on game switch (#51 F2)*)

**File:** `chess_log_controller.py:396–404`

```python
# Lines 396-404
if old_gid is not None and (self._cached_paths_data or old_gid in self._dirty_games):
    self._multi_cache[old_gid] = dict(self._cached_paths_data)
    if old_game is not None and old_gid not in self._dirty_games and self._cached_paths_data:
        self._dirty_games[old_gid] = old_game          # unconditional if cache non-empty
```

**Condition:** `self._cached_paths_data` is non-empty — i.e., the game has any Chess Log tags. This is true for any game loaded from disk that carries a `CARAChessLog` header, even if the user made zero edits.

**Contrast:** the `game=None` branch (line 410) calls `_outgoing_has_real_edits()` before adding to `_dirty_games`. The same guard is used in `_on_active_database_changed` (line 495). The normal game-switch branch does not use it.

**Consequence sequence:**

1. User opens a game with Chess Log tags. Tags are loaded into `_cached_paths_data`.
2. User switches to another game — no edits. Rule B fires: game enters `_dirty_games`.
3. The next `save_all_dirty_games()` call calls `_save_single_game(game)`.
4. `store_tags` writes the same data back to `game.pgn`. Returns `True`.
5. `_mark_database_unsaved` fires: `DatabasePanelModel.has_unsaved_changes` → `True`. DB tab shows ●.
6. User clicks File > Save Database. The file is rewritten unchanged.

No data is corrupted or lost. The cost is: a spurious unsaved indicator after browsing any tagged game, and an unnecessary round-trip write on the next DB save.

**Confirmed:** CONFIRMED-BY-RUNNING (`test_f2_real_controller.py`). Real `ChessLogController`, real `GameModel`, real `DatabaseModel` and `DatabasePanelModel`. Script output:

```
After loading game_a: _cached_paths_data non-empty = True
  game_a in _dirty_games = False

After switching to game_b (no edits to game_a):
  game_a in _dirty_games = True
  db has_unsaved_changes = False

After save_all_dirty_games():
  saved=1, failed=0
  mark_unsaved calls = 1
  db has_unsaved_changes = True

CONFIRMED (F2): real controller falsely marks DB unsaved after save of unedited tagged game
```

**Fix:** Rule B's dirty-marking condition changed from `self._cached_paths_data` (non-empty cache)
to `self._outgoing_has_real_edits()` (cache differs from disk). The `_multi_cache` flush is kept
unchanged — it avoids re-reading from disk on back-navigation and is correct regardless of edits.

**Safety analysis for `_outgoing_has_real_edits()` (`chess_log_controller.py:521–535`):** Compares
`self._cached_paths_data != ChessLogStorageService.load_tags(self._cached_game)` against the
outgoing game's current `game.pgn`. Every real edit path mutates `_cached_paths_data`:
`add_moment_at_active_path` (lines 132–139), `replace_entries_at_path` (213–219),
`replace_entries_at_path_for_game` when active (278–285). No edit can produce a dict that equals
the on-disk state without first saving — every add, delete, text change, category change, Ignore
toggle, or is_shallow stamp changes the dict. The `except` fallback returns `bool(_cached_paths_data)`,
i.e. safe-side "assume dirty" on disk-read failure. **No real edit can be falsely skipped.**

**Tests:** `TestF2RuleBFalseUnsaved` in `tests/controllers/test_chess_log_controller.py`:
- `test_a_unedited_tagged_game_not_saved_after_switch` — fails before fix, passes after.
- `test_b_add_moment_switch_away_saves_game` — positive control, passes before and after.
- `test_c_edit_text_switch_away_saves_game` — positive control, passes before and after.

---

### F3 · ShowShallowTagsDialog._original_snapshot keyed by game_number — collision across databases · MISPLACED · **FIXED** (see commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)*)

**File:** `show_shallow_tags_dialog.py:128–133`

```python
self._original_snapshot: Dict[Tuple[int, str, str], List[Dict[str, Any]]] = {
    (self._row_games[i].game_number, pk, pr): list(entries)
    for i, (pk, pr, entries) in enumerate(self._rows)
}
```

**What `path_key` encodes:** A dot-separated string of child-index integers representing the move path from the game root — e.g., `""` = start, `"0"` = after first move (mainline), `"1"` = after second move, `"0.1.0"` = first move of first variation off ply 2. Implemented in `app/utils/pgn_variation_path.py:encode_path`. Games tagged at the same ply in the mainline share the same path_key.

**Collision condition:** `_original_snapshot` is keyed by `(game_number, path_key, preset)`. `game_number` is assigned sequentially from 1 per database. When `ShowShallowTagsDialog` receives games from multiple databases (source_selection=2, "All Databases"), game 1 of DB-A and game 1 of DB-B both have `game_number=1`. If both are tagged at the same ply and preset, the dict comprehension silently overwrites the first game's snapshot with the second's — last writer wins.

**How likely:** Very likely when the user has two databases open and both contain games tagged at the same ply. Mainline move tagging uses path keys `"0"` through `"N"`. Any two games tagged at ply 5 share path_key `"4"`. The collision requires only: same game number (always true for "game 1 in DB-A and game 1 in DB-B"), same path_key (same ply), same preset. With typical libraries of 10–60 games and many tagged at similar plies, collisions are probable.

**Exactly what can land on the wrong game:**

`_on_save` (lines 494–588) uses `_original_snapshot` only for the **change-detection predicate** on shown rows (part a). It does NOT use it to decide WHAT to write — `new_entries` comes from `row_widget.get_current_entries()` which is bound to the correct `game` via `self._row_games[i]`. So the predicate is:

```python
original = self._original_snapshot.get(key, [])            # ← wrong game's entries when collided
orig_with_flags = self._stamp_entries(game.game_number, ..., original)
if _normalize_entries(new_entries) != _normalize_entries(orig_with_flags) or flags_missing ...:
    self._controller.replace_entries_at_path_for_game(game, path_key, preset, new_entries)
```

`replace_entries_at_path_for_game(game, ...)` is called with the **correct** `game` object. If it runs, the correct `is_shallow`/`is_vague` flags ARE written to the correct game's PGN.

**The risk is a false-skip:** if `_normalize_entries(new_entries) == _normalize_entries(orig_with_flags)` happens to hold when the snapshot is from the wrong game, the save is skipped for the first game and its `is_shallow`/`is_vague` flag is never written. In practice this requires the two games to have had coincidentally identical entry lists before the AI run — rare but not impossible for default/blank entries.

**What `flags_missing` contributes:** This is computed from `original` (the wrong game's entries), so it can incorrectly trigger or suppress a save decision for game 1. If game 2's entries had a missing flag that game 1's don't, the save is triggered for game 1 unnecessarily — harmless. If game 2's entries had no missing flags but game 1's do, `flags_missing=False` prevents the repair for game 1 — MISPLACED.

**Data affected:**
- `is_shallow` flag — can be silently not written to the first game's record (skip scenario)
- `is_vague` flag — same
- `ignore_shallow` / `ignore_text_hash` — unaffected: these are in stored entries, not the snapshot predicate
- `cat` / `why` (answer text) — **unaffected**: the text comes from `row_widget.get_current_entries()`, not from the snapshot. The user's edited text always goes to the correct game if `replace_entries_at_path_for_game` runs.

Summary: the only data that can land on the wrong game is the **is_shallow/is_vague stamp being silently omitted** from game 1 when the skip predicate fires on game 2's snapshot. Answer text, cat, ignore flags, and why fields are unaffected.

**`ShowTagsDialog` check:** `ShowTagsDialog._original_snapshot` uses the same `(game_number, path_key, preset)` key scheme (`show_tags_dialog.py:698–700`). However, `ShowTagsDialog` is only ever opened for the **active database** (`main_window.py:1500`): `games = [g for g in db.get_all_games() if ...]`. All games come from one `DatabaseModel`, so game numbers within that model are unique. No collision possible.

**User-level reproduction:**
1. Open two PGN databases both containing a game tagged at the same ply (e.g., move 5 mainline, `path_key="4"`) under the same preset.
2. Select "All Databases" in the Chess Log Charts source dropdown.
3. Click "Check Notes" to run the AI classifier.
4. When the dialog shows, click Save.
5. Game 1's `is_shallow` flag may not be written if its snapshot was displaced by game 2's.

**Confirmed:** CONFIRMED-BY-RUNNING (`test_f3_snapshot_collision.py`). Real `ShowShallowTagsDialog` instantiated offscreen with two synthetic `GameData` objects both having `game_number=1`, `path_key="0"`, `preset="CLAMP"`. Script output:

```
game_1.game_number = 1
game_2.game_number = 1

Rows in dialog: 2
_original_snapshot keys: [(1, '0', 'CLAMP')]
Number of snapshot entries: 1

Collision check:
  game_1 entries cat: 'C'
  game_2 entries cat: 'L'
  snapshot entries cat (last writer wins): 'L'

CONFIRMED (F3): _original_snapshot has 1 entry for key (1, '0', 'CLAMP').
  Game_1's snapshot was overwritten by game_2's.
  When _on_save processes game_1's row, orig_with_flags uses game_2's entries.
  The change-detection predicate ('new != original') compares game_1's actual
  current entries against game_2's original — wrong reference for game_1.

  _on_save for game_1 row:
    key used for snapshot lookup: (1, '0', 'CLAMP')
    'original' returned (game_2's data): cat='L'
    game_1's actual stored entries: cat='C'
```

**Fix:** `_original_snapshot` is now keyed by row index `i` (Dict[int, List]) — one entry per row, collision-free. `_on_save` accesses it via `self._original_snapshot.get(i, [])`.

**Test (now implemented):** `tests/views/test_show_shallow_tags_dialog.py::TestF3SnapshotNoCollision::test_snapshot_keyed_by_row_index_not_game_number` — constructs `ShowShallowTagsDialog` offscreen with two games sharing `(game_number=1, path_key="0", preset="CLAMP")`, asserts `len(dlg._original_snapshot) == 2` and both games' entries preserved separately. Fails on pre-fix code, passes after.

---

### F5 · AI shallow verdict keyed by game_number — stamps DEEP notes in sibling databases · MISPLACED · **FIXED** (see commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)*)

**Files:** `chess_log_shallow_service.py:438–442, 606–618`, `show_shallow_tags_dialog.py:160–182, 184–209, 502`, `chess_log_charts_controller.py:299–314, 348–365`

**Scenario:** Two databases are open, each with game_number=1. Both have a moment at `path_key="0"` under the same preset. Source dropdown is "All Databases." User clicks "Check Notes." AI correctly verdicts the first game's note SHALLOW and the second game's note DEEP.

**Identity-flow trace:**

| Stage | Key used | Two databases can collide? |
|---|---|---|
| `build_notes()` builds tuples | `(idx, game_number, path_key, preset, why)` — idx is unique | YES — both games included as separate items, but share `(game_number, path_key, preset)` |
| AI input | idx + text only; game_number never sent to the model | N/A |
| `_parse_verdicts` → `shallow_keys` | `(game_number, path_key, preset, cat)` 4-tuples | **YES** — one SHALLOW verdict creates a key that matches both games |
| `classified_keys` construction | same 4-tuples (frozenset) | **YES** — both games collapse to one frozenset entry |
| `three_ignored_lookup` | `(game_number, path_key)` | **YES** — second game's 3x3 ignore state overwrites first's |
| `ShowShallowTagsDialog._moment_has_flag` | `game_number` via `_is_shallow_key` | **YES** — key matches both games; both rows show chips |
| `ShowShallowTagsDialog._stamp_entries` | `game_number` → `_is_shallow_key` | **YES** — both games' entries get `is_shallow=True` stamped |
| `replace_entries_at_path_for_game` | `id(game)` (object identity) | NO — actual write uses correct game object |

**Root cause:** `shallow_keys` (and `classified_keys`, `three_ignored_lookup`) are keyed by `game_number`, not by `id(game)`. Two games from separate databases that happen to share the same game_number, path_key, and preset map to the same key. The AI verdict for one game's SHALLOW note is treated as applying to both games.

**`_moment_has_flag` (lines 160–167):** returns `True` for any game whose `game.game_number` matches a shallow_key. When game_1 and game_2 share game_number=1, `_moment_has_flag` returns `True` for both — both rows show the orange chip regardless of the AI's per-note verdict.

**`_stamp_entries` (lines 184–209):** stamps `is_shallow=True` on every entry whose `(game_number, path_key, preset, cat)` is in `shallow_keys`. Because both games match the same key, both games' entries get the flag — even game_2's DEEP note.

**`replace_entries_at_path_for_game` is safe:** the actual write uses `id(game)`. The contamination happens before this call, during `_stamp_entries`. Even if `replace_entries_at_path_for_game` is identity-correct, it faithfully writes the already-contaminated `is_shallow=True` entry.

**`three_ignored_lookup` sub-finding:** Built at `chess_log_charts_controller.py:299–304` by iterating `three_notes` and writing `(game_number, path_key)` → `ignored_cats`. When game_1 and game_2 share `(game_number, path_key)`, the second game's `ignored_cats` silently overwrites the first's. The filter at lines 307–313 then applies the wrong ignore set when deciding which 3x3 verdicts to pass to the dialog. If game_1 has `Why1` ignored but game_2 doesn't, game_1's SHALLOW verdict for Why1 is not filtered out — game_1 gets a chip it should not have (or vice versa).

**`classified_keys` sub-finding:** Both games collapse to one frozenset entry. The stale-clear loop in `_on_save` part (b) treats both as in-scope or both as out-of-scope. If the key is absent from `classified_keys` for game_2 (e.g., game_2's note was unparsed), stale-clear is skipped for game_1 too — game_1's stale `is_shallow` may not be cleared.

**Likelihood:** Occurs whenever "All Databases" is selected and two open databases share a game_number. The first game in each database always has `game_number=1`. With 2+ databases open and at least two games tagged at the same ply under the same preset, collisions are routine.

**Confirmed:** CONFIRMED-BY-RUNNING (`test_f5_verdict_contamination.py`). Two synthetic databases, both game_number=1; fabricated verdicts (idx 0 SHALLOW, idx 1 DEEP). Script output:

```
CLAMP TEST: game_1 has shallow note, game_2 has deep note
game_1.game_number = 1
game_2.game_number = 1
Notes sent to AI (2 total):
  idx=0, game_number=1, path_key='0', preset=CLAMP, why='No idea why this was bad.'
  idx=1, game_number=1, path_key='0', preset=CLAMP, why='Hung the knight on c3 to the bishop on a5.'
Fabricated shallow_keys: frozenset({(1, '0', 'CLAMP', '')})
classified_keys:         frozenset({(1, '0', 'CLAMP', '')})
Dialog rows: 2
  row 0: game id=4545426976, game_number=1, path_key='0', has_chip=YES
  row 1: game id=4544652432, game_number=1, path_key='0', has_chip=YES
After Save:
  game_1 (note: 'No idea why this was bad.') → is_shallow = True
  game_2 (note: 'Hung the knight on c3 to the bishop on a5.') → is_shallow = True
CONFIRMED (F5/CLAMP): game_2's DEEP note was stamped is_shallow=True

3x3 TEST: game_1 Why1 = generic, game_2 Why1 = specific
After Save:
  game_3 (Why1: 'I don't know.') → is_shallow = True
  game_4 (Why1: 'I miscalculated the pawn break on d5 after 18...Qe6.') → is_shallow = True
CONFIRMED (F5/3x3): game_4's SPECIFIC Why1 was stamped is_shallow=True

OVERALL: F5 CONFIRMED for both CLAMP and 3x3.
```

**Fix:** All key tuples (`shallow_keys`, `vague_keys`, `classified_keys`) now use the `GameData` object at position 0, not `game_number`. `build_notes()` emits `(idx, game, path_key, preset, why)` with the game object. `classify_notes` / `classify_notes_3x3` build `shallow_keys` from `notes[i][1]` (the game object). `ShowShallowTagsDialog._moment_has_flag` / `_is_shallow_key` check `(game, ...)` directly. `GameData` uses Python's default `__hash__`/`__eq__` (object identity), so two games with identical `game_number` from different DBs never collide.

**Stale-cache note:** After the fix, `_cached_shallow_keys` holds old `GameData` objects alive until `_clear_result_cache()` runs (on source/player/DB-switch). This is a harmless memory hold — no false positives possible because identity is unique per object. See §1 table above.

**Tests (now implemented):**
- `TestF5ClamNoContamination::test_only_shallow_game_row_is_shown` — CLAMP, 1 row shown (not 2)
- `TestF5ClamNoContamination::test_save_does_not_stamp_deep_game` — game_2 not stamped after Save
- `TestF53x3NoContamination::test_3x3_only_shallow_game_row_is_shown` — same for 3x3
- `TestF53x3NoContamination::test_3x3_save_does_not_stamp_deep_game`
- `TestMomentInLastShallowHelper` (8 tests) — identity-safety, stale-cache, sort-identity

All in `tests/views/`. Fail on pre-fix code, pass after.

---

### F6 · PDF/clipboard "Check Logs" section always empty — 3-tuple/4-tuple key mismatch · SILENT FAILURE · **FIXED** (see commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)*)

**File:** `detail_chess_log_charts_view.py:73, 631, 807–827, 860–884`

`_last_shallow_keys` (line 73) has type annotation `Optional[FrozenSet[Tuple[int, str, str]]]` (3-tuples). In practice it is populated from `shallow_keys` at line 631:

```python
self._last_shallow_keys = frozenset(shallow_keys) if shallow_keys else None
```

`shallow_keys` from the classifier is always a `FrozenSet[Tuple[int, str, str, str]]` — 4-tuples `(game_number, path_key, preset, cat)` — because `classify_notes` (lines 438–442) always appends `""` as the `cat` field for CLAMP/CCT, and 3x3 uses `"Why1"` etc. The annotation is stale.

The PDF export and clipboard export both check membership against `_last_shallow_keys` using a 3-tuple key:

```python
# detail_chess_log_charts_view.py:881-882
k: Tuple[int, str, str] = (game.game_number, path_key, preset)
if k not in self._last_shallow_keys or k in seen:
    continue
```

In Python, `(1, "0", "CLAMP")` is never equal to `(1, "0", "CLAMP", "")`. A 3-tuple cannot be a member of a frozenset of 4-tuples. `k not in self._last_shallow_keys` is therefore **always True**, and the `continue` is always executed. The `shallow_rows` list (PDF) and the clipboard "Check Logs" lines are always empty — the section never renders, regardless of how many shallow notes were found.

This bug is independent of cross-database game_number collisions (F5). Even with a single database, the PDF and clipboard never show the Check Logs section.

**Evidence:** CONFIRMED-BY-READING. `detail_chess_log_charts_view.py:73` (annotation), `detail_chess_log_charts_view.py:631` (store), `detail_chess_log_charts_view.py:817–819` (clipboard check), `detail_chess_log_charts_view.py:881–883` (PDF check). No code path creates a frozenset of 3-tuples from `shallow_keys`.

**Fix:** Replaced the inline `(game, path_key, preset, cat)` key lookup with a `_moment_in_last_shallow(game, path_key, preset)` helper that handles both presets correctly:
- CLAMP/CCT: checks `(game, path_key, preset, "")` — empty string cat, matching what `classify_notes` stores.
- 3x3: checks any of `(game, path_key, "3x3", cat)` for `cat in ("Why1","Why2","Why3","Why4")`.
The `seen` dedup set uses `(game, path_key, preset)` 3-tuples (one per moment, not per cat). Both clipboard and PDF export loops use the helper.

**Vague keys in export:** The export includes both Shallow and Vague moments, matching what `ShowShallowTagsDialog` shows. `_last_vague_keys` is stored on the view with the same lifecycle as `_last_shallow_keys` (cleared on source/player change, restored via `set_controller`). `_moment_in_last_shallow` checks both fields. Committed in `347e303` — *Chess Log: Charts export includes Vague lessons (#51 F6)*.

**Test (now implemented):** `TestMomentInLastShallowHelper` + `TestVagueKeysFreshness` in `tests/views/test_chess_log_charts_freshness.py` — 4 vague-only hit/miss tests and 6 lifecycle tests for `_last_vague_keys`. Fail on pre-fix code, pass after.

---

### F4 · reload_database_from_file has no callers — Chess Log flush not wired · DESIGN QUESTION

**File:** `database_controller.py:1116–1277`

`reload_database_from_file` is implemented (261 lines) but has no callers in the codebase. No menu item, shortcut, or signal connection triggers it.

**If wired in future:** `model.clear()` (line 1191) destroys all old `GameData` objects. The Chess Log controller's `id(game)` caches become stale. `_prune_dirty_games_against_open_databases` needs to run before repopulation; it is called in `_on_active_database_changed` but `reload_database_from_file` does not emit `active_database_changed`.

**Current risk:** none (dead code). **Future risk:** DATA LOSS if wired without ensuring the prune runs — stale dirty entries would be written back to the wrong `GameData` objects. This must be solved at wiring time.

---

## 6. Lead Verdicts

| Lead | Description | Verdict | Severity | Evidence |
|---|---|---|---|---|
| L1 | Deleted game stays in `_dirty_games`; save writes to orphan | **FIXED** | SILENT FAILURE | CONFIRMED-BY-RUNNING (F1); fixed in commit *Chess Log: Save All skips games no longer in an open database (#51 F1)* |
| L2 | Chess Log edits to search-result copies don't reach originals | CONFIRMED (by design) | DESIGN QUESTION | CONFIRMED-BY-READING |
| L3 | `ShowShallowTagsDialog` snapshot collision across databases | **FIXED** | MISPLACED | CONFIRMED-BY-RUNNING (F3); fixed in commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)* |
| L4 | Rule B false-dirty marking on game switch | **FIXED** | FALSE UNSAVED | CONFIRMED-BY-RUNNING (F2); fixed in commit *Chess Log: don't mark unedited games dirty on game switch (#51 F2)* |
| L5 | `reload_database_from_file` missing Chess Log flush | CONFIRMED (dead code) | DESIGN QUESTION | CONFIRMED-BY-READING |
| L6 | Sort reorder vs. caches | NO RISK | NO RISK | CONFIRMED-BY-READING |
| — | AI verdict keyed by `game_number` stamps DEEP notes in sibling databases | **FIXED** | MISPLACED | CONFIRMED-BY-RUNNING (F5); fixed in commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)* |
| — | PDF/clipboard "Check Logs" always empty (3-tuple/4-tuple mismatch) | **FIXED** | SILENT FAILURE | CONFIRMED-BY-READING (F6); fixed in commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)* |

---

## 7. Outside Chess Log

### L2 — Search-result copies

`SearchController._create_search_results_model()` (`search_controller.py:154–202`) creates new
`GameData` objects with `pgn=game.pgn` (content copied) and new Python identity.
`has_chess_log_tags` is not passed and defaults to `False`; it is updated to `True` as a side
effect of `ChessLogStorageService.load_tags()` when the controller loads the copy into cache.

Chess Log edits to a search result modify `game_copy.pgn`. The original game in its source
database is untouched. The `search_results` identifier is explicitly excluded from all save paths
(`database_controller.py:502, 573, 607, 632`): the search-results `DatabaseModel` is never
written to disk.

**Does Philipp's code propagate any edit from a copy to the original?** No. Analysis, annotations,
and notes also write to `game_copy.pgn` via the same PGN-header mechanism. `source_database`
on the copy is a display-only string, not a live reference. The design treats search results as a
read-only window: the user is expected to navigate to the original if they want to persist edits.

**Chess Log specifically:** consistent with CARA's existing behavior. Not uniquely broken, but
there is no UI hint that Chess Log moments tagged on a search result won't survive a session.

**DESIGN QUESTION** — options if this needs addressing: (a) disable Chess Log tagging when the
active game's owning DB is `search_results`; (b) add a warning on the first tag attempt;
(c) by design intent, leave it as-is and add documentation.

**Decision (2026-10-23):** No change. Consistent with CARA's handling of all edits on search copies — analysis, annotations, and PGN notes also write to the copy only. Addressing this would require coupling Chess Log to the search/DB architecture, which is out of scope for the current audit.

### L6 — Sort and cache keying

All seven `ChessLogController` caches are keyed by `id(game)`. Sort reorders the `_games` list
positions but does not replace `GameData` objects — `id(game)` is stable. `game_number` is set
at load/import time (`database_model.py:443–448`) and is never updated by sort.

Charts-layer caches (`_cached_shallow_keys`, `_cached_vague_keys`, `_last_shallow_keys`, `_last_vague_keys`) are now keyed by `GameData`
object identity (after F5/F6 fix). Sort does not replace game objects — `id(game)` is stable.

`ShowTagsDialog._original_snapshot` uses `(game_number, path_key, preset)` — sort does not
change game_number. `ShowShallowTagsDialog._original_snapshot` is now keyed by row index —
sort does not affect row indices at dialog-open time.

**Sort is safe for all caches. NO RISK.**

---

## 8. Test Proposals

| Finding | Proposed test | Status |
|---|---|---|
| F1 | After `remove_games()`, assert `id(game) not in ctrl._dirty_games`; also assert `save_all_dirty_games()` after a delete returns `(0, 0)` and calls `mark_database_unsaved` zero times | **IMPLEMENTED** (`TestF1DeletedGamePruning::test_deleted_game_pruned_before_save_all`) |
| F2 | Load a tagged game, switch away without editing, assert `save_all_dirty_games()` returns `(0, 0)` and no DB is marked unsaved | **IMPLEMENTED** (`TestF2RuleBFalseUnsaved::test_a_unedited_tagged_game_not_saved_after_switch` + two positive controls) |
| F3 | `TestF3SnapshotNoCollision` — `len(dlg._original_snapshot) == 2`, both games' entries preserved separately | **IMPLEMENTED** (commit `0c6e613` — *Chess Log: Check Logs keys by game object, not game number (#51 F5, F3, F6)*) |
| F4 | No test needed until `reload_database_from_file` is wired | Open — dead code |
| F5 | `TestF5ClamNoContamination` + `TestF53x3NoContamination` — 4 tests; row count, save-stamp, and positive-control assertions | **IMPLEMENTED** (commit `0c6e613`; positive controls in commit `4d5dea9` — *Chess Log: Check Logs identity tests for sort, DB close and positive controls (#51)*) |
| F5 (sort) | `TestF5SortScenario` — real `DatabaseModel.sort()` + `ChessLogChartsController` + theme-rebuild; chip survives on correct game | **IMPLEMENTED** (commit `4d5dea9`) |
| F5 (stale) | `TestF5StaleCacheScenario` — two real `DatabaseModel`s; DB-A game removed before DB-B dialog opened; no false chip | **IMPLEMENTED** (commit `4d5dea9`) |
| F6 | `TestMomentInLastShallowHelper` — 12 tests; identity-safety, stale-cache, sort-identity, CLAMP/3x3, vague-only hit/miss | **IMPLEMENTED** (commits `0c6e613`, `347e303` — *Chess Log: Charts export includes Vague lessons (#51 F6)*) |
| F6 (vague lifecycle) | `TestVagueKeysFreshness` — 6 tests; `_last_vague_keys` initial state, store, clear on source/player change, frozenset type | **IMPLEMENTED** (commit `347e303`) |

---

## 9. Unknown / Suspected

All six original leads are resolved. Two additional findings (F5, F6) were discovered during Directive 9d investigation of the charts path.

---

## 10. Verification Log

All CONFIRMED-BY-RUNNING scripts were created with the Write tool at
`/tmp/claude-501/cl_audit/`, run as `QT_QPA_PLATFORM=offscreen python3 <file>` from the
CARA repo root.

### test_f1_real_controller.py — F1 (SILENT FAILURE)

Real `ChessLogController` + real `GameModel` + real `DatabaseModel` + real `DatabasePanelModel`.
Adds a tagged game, switches away (Rule B → `_dirty_games`), calls `remove_games()`, then calls
`save_all_dirty_games()`. Asserts `mark_database_unsaved` was never called and DB stays clean.

**Output:**
```
game_a in _dirty_games before delete: True
game_a in db_model after remove: None
game_a still in _dirty_games after remove: True

save_all_dirty_games returned: saved=1, failed=0
mark_unsaved calls after save: 0
db has_unsaved_changes after save: False
game_a still in _dirty_games after save: False

CONFIRMED (F1): save_all reported 1 saved, but mark_database_unsaved was never called
User sees: success toast '1 game(s) saved'. DB never marked unsaved. Disk file unchanged.
```

### test_f2_real_controller.py — F2 (FALSE UNSAVED)

Real `ChessLogController` + real `GameModel` + real `DatabaseModel` + real `DatabasePanelModel`.
Loads a tagged game (no edits), switches to a second game, calls `save_all_dirty_games()`.
Asserts DB was marked unsaved despite zero edits.

**Output:**
```
After loading game_a: _cached_paths_data non-empty = True
  game_a in _dirty_games = False

After switching to game_b (no edits to game_a):
  game_a in _dirty_games = True
  db has_unsaved_changes = False

After save_all_dirty_games():
  saved=1, failed=0
  mark_unsaved calls = 1
  db has_unsaved_changes = True

CONFIRMED (F2): real controller falsely marks DB unsaved after save of unedited tagged game
```

### test_f3_snapshot_collision.py — F3 (MISPLACED)

Real `ShowShallowTagsDialog` instantiated offscreen. Two synthetic games both with
`game_number=1`, same `path_key="0"`, same `preset="CLAMP"`, different `cat` fields. Asserts
`_original_snapshot` has only one entry (last writer wins) and identifies which game's snapshot
was displaced.

**Output:**
```
game_1.game_number = 1
game_2.game_number = 1

Rows in dialog: 2
_original_snapshot keys: [(1, '0', 'CLAMP')]
Number of snapshot entries: 1

Collision check:
  game_1 entries cat: 'C'
  game_2 entries cat: 'L'
  snapshot entries cat (last writer wins): 'L'

CONFIRMED (F3): _original_snapshot has 1 entry for key (1, '0', 'CLAMP').
  Game_1's snapshot was overwritten by game_2's.
  ...
  _on_save for game_1 row:
    key used for snapshot lookup: (1, '0', 'CLAMP')
    'original' returned (game_2's data): cat='L'
    game_1's actual stored entries: cat='C'
```

### test_f5_verdict_contamination.py — F5 (MISPLACED)

Real `ShowShallowTagsDialog` instantiated offscreen. Two synthetic game pairs (CLAMP + 3x3), each
pair in separate `DatabaseModel` instances so both games get `game_number=1`. Fabricated verdict
sets: idx 0 → SHALLOW, idx 1 → DEEP. Asserts `is_shallow=True` on the DEEP game after `_on_save()`.

**Output:**
```
CLAMP TEST: game_1 has shallow note, game_2 has deep note
game_1.game_number = 1
game_2.game_number = 1
Notes sent to AI (2 total):
  idx=0, game_number=1, path_key='0', preset=CLAMP, why='No idea why this was bad.'
  idx=1, game_number=1, path_key='0', preset=CLAMP, why='Hung the knight on c3 to the bishop on a5.'
Fabricated shallow_keys: frozenset({(1, '0', 'CLAMP', '')})
classified_keys:         frozenset({(1, '0', 'CLAMP', '')})
Dialog rows: 2
  row 0: game id=4545426976, game_number=1, path_key='0', has_chip=YES
  row 1: game id=4544652432, game_number=1, path_key='0', has_chip=YES
After Save:
  game_1 (note: 'No idea why this was bad.') → is_shallow = True
  game_2 (note: 'Hung the knight on c3 to the bishop on a5.') → is_shallow = True
CONFIRMED (F5/CLAMP): game_2's DEEP note was stamped is_shallow=True

3x3 TEST: game_1 Why1 = generic, game_2 Why1 = specific
After Save:
  game_3 → is_shallow = True
  game_4 → is_shallow = True
CONFIRMED (F5/3x3): game_4's SPECIFIC Why1 was stamped is_shallow=True

OVERALL: F5 CONFIRMED for both CLAMP and 3x3.
```

### Leads confirmed by reading only

| Lead | Finding | Key locations |
|---|---|---|
| L2 search copies | DESIGN QUESTION | `search_controller.py:154–202`; `database_controller.py:502,573,607,632` |
| L5 reload dead code | DESIGN QUESTION | `database_controller.py:1116`; no callers found |
| L6 sort safety | NO RISK | `database_model.py:443–448`; all controller caches use `id(game)` |
| F6 PDF/clipboard | SILENT FAILURE | `detail_chess_log_charts_view.py:73,631,817–819,881–883`; 3-tuple never found in frozenset of 4-tuples |

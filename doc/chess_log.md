# Chess Log

Human-authored move logging layer — player self-diagnosis, complementing CARA's engine-based classification. Players log up to three "moments" per game with a category and optional note.

See also: `doc/chess_log_charts.md` for the Charts tab (reporting and narrative); `chess-log-design-doc.md` §3.2–3.4 for the full preset design; `doc/chess_log_integrity.md` for the data-integrity audit (caching, write paths, findings).

## Storage format

`CARAChessLog` / `CARAChessLogInfo` / `CARAChessLogChecksum` PGN header triple (same gzip+base64 pattern as Annotations and Notes). Payload is JSON keyed by variation path (`encode_path` from `app/utils/pgn_variation_path.py`). One path = one moment; the 3-moment cap counts distinct non-empty path keys, not total entries (so a CCT moment with two letters = 1 moment).

Chess Log writes only its own `CARAChessLog*` headers — it does **not** inject anything into `CARAGameTags`. The `has_chess_log_tags` field on `GameData` (set from the presence of `CARAChessLog` in the PGN at load time) drives the **Log** column in the database panel independently of any game-tag chip.

### CARA-namespaced PGN tags (all read-only in metadata view and model)

- `CARAAnalysisData` / `CARAAnalysisInfo` / `CARAAnalysisChecksum` — per-move engine data
- `CARAAnnotations` / `CARAAnnotationsInfo` / `CARAAnnotationsChecksum` — board drawing annotations
- `CARANotes` / `CARANotesInfo` / `CARANotesChecksum` — whole-game text notes
- `CARAChessLog` / `CARAChessLogInfo` / `CARAChessLogChecksum` — Chess Log moments
- `CARAGameTags` — whole-game chip tags (independent of Chess Log)

## Vocabulary

"Moment" in all user-facing text; `tag`/`tagged` is acceptable in internal code. Avoids collision with `CARAGameTags` whole-game chips.

## Log column

`COL_LOG = 18` in `DatabaseModel` — shows `✓` for games where `has_chess_log_tags` is `True`. Sits between Annotated/Notes and Source DB in the column order. Backed by `"CARAChessLog": DatabaseModel.COL_LOG` in the metadata controller's header-tag map, so the column lights up whenever the PGN carries a `CARAChessLog` header.

Column width key: `"col_log"` in `ui.panels.database.table.column_widths` (all three theme files). Existing saved column profiles that predate `col_log` get it appended automatically (see `ColumnProfile.get_column_order`).

## Presets

Three presets: **CLAMP**, **CCT**, **3x3**. The player selects one active preset in the Chess Log Settings dialog (Chess Log menu → "Chess Log Settings…"), mirroring the Engines/AI Summary setup pattern. CLAMP and CCT both allow multiple letters per moment.

3x3 is the sole preset with free-form text at log time. Its four Whys use GM Noel Studer's exact wording:
- "Why did I choose that move?"
- "Why is my move not ideal?"
- "Why is the better move better than my chosen move?"
- "What do I do in the future so this doesn't happen again?"

Storage keys: `Why1` / `Why2` / `Why3` / `Why4`. These strings are defined once in `app/utils/chess_log_prompts.py` (`THREE_BY_THREE_PROMPTS` dict) and imported by `moment_dialog.py`, `show_tags_dialog.py`, and `chess_log_pdf_service.py`.

The active preset can change over time — a library may end up with moments logged under more than one preset. This is expected, not an error.

## Logging behavior

### Zero-category save (CLAMP, CCT)

If no chips are checked but the why-field has content, the moment saves as a single entry with `cat=""` — genuinely uncategorized, not a fake "Other" category. Zero chips + empty why keeps OK blocked (hint shown).

### "More than three moments?" nag

When a player tries to add a *new* path (a fresh moment, not re-logging an existing one) and the game already has ≥ 3 logged moments, a soft "Are you sure?" dialog fires. The nag fires **before** Log This Moment opens (checked in `DetailMovesListView._on_tag_moment` via `ChessLogController.should_confirm_extra_moment`) so the user is asked before investing typing effort.

Once shown, the nag is suppressed for:
- The rest of the session (`_nag_shown_this_session: bool`, global across all games).
- All future sessions for that specific game (`_nag_shown_by_game: Dict[int, bool]`, persisted in the `CARAChessLog` payload as `"nag_shown": true`).

Persistence follows the explicit-save convention: the flag rides with the next Ctrl+Alt+L save; if the user never saves the game, the flag is lost along with the moment itself. Re-logging an existing path (adding a second preset's entries to an already-logged move) never counts as a new moment and never triggers the nag.

## User interface

### Entry point

First-time users: Chess Log → Chess Log Settings to pick their preset (CLAMP, CCT, or 3x3). Then right-click a move in the Moves List → "Log this moment…". Save via Chess Log menu → "Save Chess Log to current game" (`Ctrl+Alt+L`). Clear via `Ctrl+Shift+L`.

### Moves-list context menu structure (right-click on any move)

1. Column profile (submenu)
2. --- separator ---
3. Copy value
4. Edit Comments (conditional — only when clicking a Comment cell)
5. --- separator ---
6. Log this moment…
7. **Show Logged Moments** — opens `ShowTagsDialog` scoped to the current game, sorted by ply ascending then preset in canonical order (CLAMP → CCT → 3x3). Enabled iff the game has at least one logged entry. Disabled with tooltip "No logged moments in this game." when the game has zero moments.
8. --- separator ---
9. Copy Table as CSV / TSV (4 actions)

### Show Logged Moments dialog

`app/views/dialogs/show_tags_dialog.py`, class `ShowTagsDialog`. Parameterized for single-game or multi-game — pass `games=[game]` for single-game (context-menu path), `games=[g1, g2, …]` for multi-game ("Show Logged Moments for All Games" menu path). Each row represents one (move, preset) pair: board miniature, category checkboxes (blank for 3x3), why-note text. All fields editable on open.

**Buffered editing** — OK persists changes to the in-memory cache via `replace_entries_at_path_for_game`; Cancel discards all edits. Multi-game usage inserts a game-header label (`White - Black Result (Date - N moves)`) between each game's rows; single-game usage shows no header. Zero-category saves (`cat=""`) round-trip correctly through OK. `ignore_shallow` and `ignore_text_hash` fields are transparently preserved through edits.

Rows whose entries carry `is_shallow=True` or `is_vague=True` render chip labels. `ShowTagsDialog` computes chip visibility per-row from stored entry flags and passes `show_ignore_checkbox=True` to `_TagRowWidget`. The "Shallow" chip (red) shows when `is_shallow`; the "Vague" chip (amber) shows when `is_vague`. Both chips are visible in `ShowTagsDialog` (from stored entry flags) and in `ShowShallowTagsDialog` (pre-stamped at dialog open from key membership). Chip colors and text from `ui.dialogs.shallow.labels.{shallow,vague_lesson}`; colors in theme files, text/tooltip in `config.json`.

**Chip-eligibility rule (B4)**: `Shallow` may only render on entries with `cat ∈ {Why1,Why2,Why3}`; `Vague` may only render on entries with `cat == "Why4"`. Legacy data that stored `is_shallow` on a Why4 entry, or `is_vague` on a Why1-3 entry, is ignored at render time — the chip never appears on the wrong answer.

**Chip placement**: CLAMP/CCT chips render in the move-header row (unchanged). 3x3 chips render in a fixed-width column to the **right of the answer box**, top-aligned with the answer, with the Ignore checkbox stacked below the chip. The question line contains only the question text — no chip. A Why without a chip uses the full answer width. No ⚠️ triangle anywhere.

**Ignored entries (B10a)**: an entry with `ignore_shallow=True` and a matching `ignore_text_hash` renders its chip at 40% opacity with a ticked `☑ Ignore` checkbox in `ShowTagsDialog`. Unticking Ignore and clicking OK/Save clears all three stored fields (`ignore_shallow`, `ignore_text_hash`, and the chip flag `is_shallow`/`is_vague`). This is the only place a user can undo an Ignore without editing the answer text.

**Chip fade on edit (#67)**: the first edit to an answer's text starts a `QParallelAnimationGroup` + `QGraphicsOpacityEffect` animation that fades the chip (and, for 3x3, the entire `chip_col_widget` containing the chip and Ignore checkbox) from opacity 1 → 0 over `ui.dialogs.show_tags.chip_fade_ms` milliseconds (default 500), then hides the widget. For CLAMP/CCT the chip(s) and Ignore checkbox each get their own animation in the group; there is no layout resize. This is **display-only**: no verdict data is touched during editing. Data clearing still happens at Save via `clear_verdict_if_text_changed()` — which compares the current text against the text stored at dialog open. Consequence: if the user restores the exact original text before saving, the verdict (`is_shallow`/`is_vague`) is preserved and the chip reappears on reopen. The per-answer `_faded_cats` set prevents retriggering the animation on subsequent edits. Cancel discards all edits and the chip is back on reopen; Save with changed text removes the chip on reopen. Applies to both `ShowTagsDialog` and `ShowShallowTagsDialog` (shared `_TagRowWidget`).

**Export to PDF** button (left of the button row) exports on-screen rows WYSIWYG — including in-progress buffered edits — via `ChessLogPDFService`. Rows are paginated atomically (no row straddles a page break); multi-game exports include per-game headers kept with their first row.

`_TagRowWidget.snapshot()` captures the live widget state into a `TagRowSnapshot` dataclass (`app/models/chess_log_snapshot.py`) used by the exporter. `TagRowSnapshot` carries: `best_move: Optional[chess.Move]` (default `None`) resolved at row-construction time via `resolve_best_move_for_path` (`app/utils/chess_log_best_move.py`); `is_shallow: bool` and `is_vague: bool` (both default `False`) so the PDF renderer can draw chips without re-reading the entries list; and `is_flipped: bool` for WYSIWYG board orientation.

**Miniature board scale and arrows** — Chess Log review dialogs (Show Logged Moments and Check Logs) follow View → Miniature Boards → Chess Log (one surface for both). Scale presets: 1.0×, 1.25×, 1.5×, 1.75×, 2.0× (default 1.25× — no visible change for existing users). Arrow toggles: "Show Played Move" (yellow) and "Show Best Alternative Move" (reddish), both on by default. Scale and arrow settings are read once when each dialog opens (not live-updated, since both dialogs are modal `exec()`). The PDF export (`ChessLogPDFService`) deliberately ignores these settings and always renders both arrows at a fixed print-quality size, matching Game Report PDF behavior. The Chess Log submenu stays visible even when the Chess Log tab is hidden via View → Show/Hide, because its boards live in dialogs reached from the top-level Chess Log menu.

Each row's board thumbnail uses `MiniChessBoardWidget.set_played_and_best(played, best)`: played move in yellow, best move in reddish. The played arrow is suppressed when Show Played Move is off; the best arrow is suppressed when Show Best Alternative Move is off, when `best_move` is None, or when best equals played.

**Miniature board orientation** — each row's board is oriented so the **mover at the logged ply** is at the bottom. Orientation is derived per row from `pre_board.turn` inside `node_info()` (`app/views/dialogs/_tag_row_helpers.py`): `mover_is_black = pre_board.turn == chess.BLACK`. No player-selection dependency — works correctly on first open, for right-click Show Logged Moments, and for CCT entries at either color. Independent of the main detail board's flip toggle.

### "Show Logged Moments for All Games"

Chess Log menu item (after "Save Chess Logs for all games"): opens `ShowTagsDialog` scoped to every game in the active database that has at least one logged entry (`has_chess_log_tags=True`). Buffered editing — OK writes, Cancel discards. Handler: `MainWindow._show_chess_logs_for_all_games`.

### "Show Shallow/Vague Logs"

Chess Log menu item (after "Show Logged Moments for All Games"): opens `ShowShallowTagsDialog` in **Saved mode**, showing all stored `is_shallow`/`is_vague` entries across the active database — no new AI call. Handler: `MainWindow._show_saved_shallow_logs`.

Differences from a live Check Logs run: window title is "Shallow/Vague Logs"; `classified_keys` is `frozenset()` (stale-clear Phase b and Phase c are both no-ops — **no `check_hash` or `_check_run` is written on Save**); `check_run_info` is `None` (the dialog reads `_check_run` per game at PDF-export time only). Shows a message box if no logged games exist, and a different message box if no checked entries are found (checked = has `check_hash`, `is_shallow`/`is_vague`, or honoured `ignore_shallow`). The unchecked-notes banner (notes without a valid `check_hash`) is shown only in Saved mode — never during a live Check Logs run.

### Moves List highlight

Chess Log menu → "Highlight Logged Moments in Moves List" (checkable toggle): when on, moves that have at least one logged entry in the current game's in-memory cache render a themed "logged moment" icon (`app/resources/icons/chess_log_moment.svg`) to the **left** of the move text in the Moves List. Returned via `Qt.DecorationRole` on `COL_WHITE` / `COL_BLACK`; Qt's default delegate handles the left-of-text placement — no custom delegate. Tinting follows the Moves List's own theme colors (normal move-text color on regular rows; `active_move.text_color` on the current-move row; `selection_text_color` via the icon's `QIcon.Mode.Selected` pixmap when a row is selected), rebuilt from `ChessLogMomentIconProvider` on each theme change. The state is persisted to `user_settings.json` under `chess_log_settings.highlight_chess_log_moves_in_list` and restored on startup. The highlight is applied by `MovesListModel.set_highlight_chess_log_moves` and refreshed automatically via `notify_chess_log_changed` whenever Chess Log entries are added, saved, or cleared.

**No emoji on Chess Log surfaces.** All Chess Log indicators that would otherwise be pictographic characters ship as themed SVGs loaded through `app/utils/themed_icon.py`, so they recolor with the active theme and render identically across platforms.

## Dialog theming

`MomentDialog`, `ShowTagsDialog`, and `ShowShallowTagsDialog` use separate config namespaces. `MomentDialog` uses `ui.dialogs.moment`; `ShowTagsDialog` and `ShowShallowTagsDialog` use `ui.dialogs.show_tags` for font family/size and text-edit heights, and continue to use `ui.dialogs.moment` for colors (background, text, border, separator, inputs.background/border). `ChessLogSettingsDialog` uses `ui.dialogs.chess_log_settings`. All blocks exist in all three theme JSON files (`style_default`, `style_light`, `style_scholar`) with theme-appropriate `$_ref` tokens, so the dialogs repaint correctly when CARA's theme is changed.

Every color used in these dialogs' `setStyleSheet` calls must be read from config (via `dc.get(...)`) — **no hardcoded `rgb(…)` literals are permitted**.

All four dialogs are opened via `.exec()` (modal), so "repaint on next open" matches `BulkOperationsDialog`'s behavior; no theme-changed signal infrastructure is needed.

### MomentDialog layout

`MomentDialog` (used by all three presets — CLAMP, CCT, 3x3) is user-resizable via CARA's standard themed resize grip (`install_themed_dialog_resize_grip`). Dialog height is layout-driven; there is no fixed height. Spacing, margins, chip minimum widths, and text-field minimum heights are all theme-driven config under `ui.dialogs.moment` — specifically `layout.margins`, `layout.spacing`, `bottom_button_top_padding`, `buttons.spacing`, `chips.min_width`, `chips.cct_min_width`, `why.minimum_height`, and `three_by_three.edit_minimum_height`. All new sizing keys are registered in `_REQUIRED_CONFIG_KEY_PATHS` and present in all three theme files. 3x3 answer fields use equal stretch factors so they share vertical space when the dialog is enlarged.

### ShowTagsDialog / ShowShallowTagsDialog layout

Both dialogs render rows through the shared `_TagRowWidget`, which reads its font and height config from `ui.dialogs.show_tags.*`:

| Key | Default | Purpose |
| --- | --- | --- |
| `label_font_family` | `"Helvetica Neue"` | Row header + 3x3 prompt labels |
| `label_font_size` | `11` | Row header font size (scaled via `scale_font_size`) |
| `inputs.font_family` | `"Helvetica Neue"` | `_FitTextEdit` (why + 3x3 answers) |
| `inputs.font_size` | `11` | Text-edit font size (scaled) |
| `fit_min_lines` | `1` | Minimum visible lines for all answer boxes |
| `fit_max_lines` | `6` | Maximum visible lines before scrolling |

**Fit-to-text answer boxes**: answer fields use `_FitTextEdit` (a `QPlainTextEdit` subclass) that sizes itself to its content within `[fit_min_lines, fit_max_lines]`. Height updates on `contentsChanged` and on resize (so re-wrapping updates the box). Beyond `fit_max_lines`, the box stops growing and scrolls. The old static min-height approach is replaced. Font sizes use `QFont.setFont()` (not stylesheet px values) so they scale correctly on HiDPI displays. Both dialogs are user-resizable via `install_themed_dialog_resize_grip`. All six keys are registered in `_REQUIRED_CONFIG_KEY_PATHS` and verified in `tests/config/test_theme_coverage.py` (`_SHOW_TAGS_DIALOG_KEYS`). Fonts must not be read from the `moment` namespace — keep the two namespaces independent so tuning one dialog doesn't silently affect the other.

## Controller API

### ChessLogController helpers

- `game_has_any_tags() -> bool` — True iff `_cached_paths_data` has any non-empty entry list.
- `replace_entries_at_path(path_key, preset, entries, view=None)` — replaces entries for the given preset at that path; preserves other presets. In-memory only.
- `replace_entries_at_path_for_game(game, path_key, preset, entries)` — same but takes a `GameData` object; correctly routes to either the active single-game cache or the multi-game cache depending on which game is active. Used by `ShowTagsDialog._on_save` and `ShowShallowTagsDialog._on_save`. In-memory only; does not mark the DB unsaved. **This is the only method that explicitly marks a game dirty** (populates `_dirty_games`).
- `save_games(games: Iterable) -> Tuple[int, int]` — writes `game.pgn` for each game via `_save_single_game`, marks the owning database unsaved, clears `_dirty_games` for each saved game. Returns `(n_saved, n_failed)`. Called by dialog Save handlers to commit all edits made in that dialog session. The commit granularity is the **game**: `save_games([game])` writes the full pending cache for that game — including any unsaved Log-this-Moment edits on the same game — in a single `store_tags` call. Chess Log edits on the same game cannot be committed selectively.

## Caching & Database-Switch

### Per-game cache keying

`ChessLogController` maintains several in-memory caches, all keyed by **`id(game)`** (Python object identity), not by `game.game_number`:

| Field | Purpose |
|---|---|
| `_cached_paths_data` / `_cached_game_id` | Single-slot cache for the currently active game |
| `_multi_cache: Dict[int, Dict[str, List[Dict]]]` | Inactive games loaded for ShowTagsDialog / ShowShallowTagsDialog |
| `_dirty_games: Dict[int, GameData]` | Games with in-memory edits pending `save_all_dirty_games()` |
| `_nag_shown_by_game: Dict[int, bool]` | Per-game session flag for the "more than three moments?" nag |
| `_cached_original_paths: Dict[int, Dict[str, List[Dict]]]` | On-disk snapshot captured at load; passed as `original_paths=` to the save-side orphan guard |
| `_resolved_cache: Dict[int, Tuple[int, str, Dict]]` | Memoized orphan-filtered view — `(write_version, pgn_blake2b_hex, resolved_dict)` |
| `_cache_version_by_game: Dict[int, int]` | Write counter per game; bumped by every in-memory mutation; reset to 0 on `_load_into_cache` |

**Why `id(game)` and not `game.game_number`?** Each database assigns `game_number` as a sequential integer starting at 1. Two databases can (and do in practice) produce `GameData` objects with identical `game_number` values. Using `id(game)` (the Python object's memory address) is collision-impossible because different objects have different identities, and the cache dicts hold references so GC cannot reuse the address while the entry lives.

### Database-switch behaviour

`ChessLogController` connects to `DatabasePanelModel.active_database_changed` via `_connect_to_database_panel_model()` (called at the end of `__init__`). On each switch, `_on_active_database_changed()`:

1. **Flushes** the outgoing active game's real edits into `_multi_cache` + `_dirty_games` — but only if `_outgoing_has_real_edits()` returns True. This helper compares `_cached_paths_data` against `load_tags(_cached_game)` (the outgoing game's own disk snapshot), **not** against `has_unsaved_changes()` which reads the game model's current `active_game` — which may already be `None` or the newly-switched game by the time the handler runs.
2. **Clears** the active-game pointers (`_cached_paths_data`, `_cached_game_id`, `_cached_game`).
3. **Prunes** `_dirty_games` entries whose `GameData` is no longer in any open database (via `_prune_dirty_games_against_open_databases`). This handles reload (`reload_database_from_file`) and close events — stale object references cannot be written to by `save_all_dirty_games`.
4. **Preserves** the rest of `_dirty_games` byte-for-byte; drops cache-only entries (`_multi_cache`, `_nag_shown_by_game`, `_cached_original_paths`, `_resolved_cache`, `_cache_version_by_game`) for gids no longer in `_dirty_games`.

The same flush-and-prune logic runs in `_on_active_game_changed(game=None)` for clipboard-clear, database-close, and reload events.

### Save model

Chess Log has two distinct commit layers:

- **Cache edits** (`add_moment_at_active_path`, `replace_entries_at_path`, `replace_entries_at_path_for_game`) — in-memory only. No tab pulse. The edit lands in `_cached_paths_data` or `_multi_cache` and the game is added to `_dirty_games`.
- **Save operations** — write `game.pgn` and mark the owning database unsaved (tab pulse):
  - **Log this Moment → Save Chess Log for Current Game** (`save_tags_for_current_game`) — commits the active game's cache.
  - **Save Chess Logs for All Games** (`save_all_dirty_games`) — commits every game in `_dirty_games`.
  - **Dialog Save** (`save_games(games)`) — commits each game passed in. Called by `ShowTagsDialog._on_save` and `ShowShallowTagsDialog._on_save`.

**Dialog Save/Cancel semantics:**

- `ShowTagsDialog` (Show Logged Moments): **Save** applies every changed row by calling `replace_entries_at_path_for_game` for each, then calls `save_games(affected_games)`. **Cancel** (and the window close button) discards all row edits — nothing was written to the controller cache, so reject is a true no-op.
- `ShowShallowTagsDialog` (Check Logs): **Save** stamps `is_shallow=True` / `is_vague=True` per-entry (using the B4 chip-eligibility rule: Shallow only on Why1/Why2/Why3 entries; Vague only on Why4), clears both stale flags on entries in `classified_keys` that were classified neither shallow nor vague this run (per-entry for 3x3, per-`(gn,pk,preset)` for CLAMP/CCT), then calls `save_games(affected_games)`. **Cancel** discards all pending verdicts. The dialog's Save is the **only** place `is_shallow` and `is_vague` are committed; `_on_shallow_thread_ready` emits `shallow_ready(shallow_keys, vague_keys, classified_keys, usage)` without writing to the cache.
- The "touchable set" (`classified_keys`) is the authoritative scope for the shallow dialog's clear-stale-flag loop. Entries with `ignore_shallow=True` and a matching `ignore_text_hash`, entries the classifier could not parse, and entries with no `why`-note were excluded from the classifier run and are **never** touched by the dialog's Save — clearing them would silently violate the user's intent.

**Dirty-marking**: databases are marked unsaved only from `_save_single_game` (called by `save_tags_for_current_game`, `save_all_dirty_games`, and `save_games`) and from `clear_tags_for_current_game`. The three edit methods do **not** mark the DB unsaved. Between a Log-this-Moment OK and the user running one of the Save commands, there is no visible indicator that Chess Log work is pending — the design deliberately defers the pulse to the explicit save step.

**Commit granularity**: `save_games([game])` calls `store_tags(game, full_cache_for_game)` — the full pending cache for that game, not just the dialog's edits. If the user had a pending Log-this-Moment edit on game A and then edits game A's note in Show Logged Moments and clicks Save, both edits land in `game.pgn` in a single commit. This is intentional: Chess Log edits on the same game cannot be committed selectively.

### Orphan path_keys

A **path_key** in a game's `CARAChessLog` payload is an **orphan** if its decoded path (e.g. `(99, 0)`) cannot be walked to a node in that game's current move tree. Orphans arise legitimately when moves are edited after a moment was logged, and also from the historical `game_number` collision bug.

Policy:
- **Load side**: `ChessLogStorageService.load_resolved_paths(game)` returns only the path_keys that resolve in the parsed chess game; orphans are logged at WARNING and excluded. `load_tags(game)` still returns the full dict byte-for-byte for save-time round-trip preservation.
- **Save side**: `ChessLogStorageService.store_tags(..., original_paths=...)` refuses to write **new** orphan path_keys (logged at ERROR) but passes through **pre-existing** orphan keys unchanged, so historical data is never silently destroyed. All production save paths route through `_save_single_game`, which supplies `original_paths=self._cached_original_paths.get(gid)`. After a successful save the snapshot is refreshed from disk via `load_tags(game)` — **not** from the `paths_data` dict just written — so a refused orphan stays "new" on the next save and is refused again.
- **Feature code (resolved view)**: `get_tags_for_current_game()`, `get_tags_for_game()`, and `should_confirm_extra_moment()` consume `_resolved_view(raw, game)` — an orphan-filtered copy memoized per `id(game)`. The memoization key is `(write_version, blake2b-16 hash of game.pgn)`. The content hash (not `len(pgn)`) is used so same-length move substitutions (e.g. `Nf3` → `Nc3`) also invalidate the cache. The method always returns a **shallow copy** of the memoized dict so caller mutation cannot corrupt the cache. Background service callers (charts aggregation, narrative prompt, charts controller fallback) call `load_resolved_paths` directly — they read from disk and never see in-session edits, so the one-level disk filter is correct.
- **Display**: `ShowTagsDialog` and `ShowShallowTagsDialog` detect orphan rows by checking `move_label == path_key` (the fallback when `node_at_path` returns `None` in `_tag_row_helpers.node_info`), skip them silently, and append a single notice at the bottom of the dialog listing the count of unreachable moments.

## Single source of truth

Every piece of Chess Log data has exactly one owner. The rules (from #88):

1. **One owner.** Exactly one store holds the authoritative value, in memory and/or in the PGN.
2. **One write path.** Every change goes through one method of the owner.
3. **One read path.** Every reader goes through the owner's accessor.
4. **Derived data stays derived.** Caches, flags, counts and memoized views are computed from the owner on read, or invalidated by the owner's write method — never by the caller.
5. **What you see is what Save writes.** Pending state is part of the truth; no view shows older or newer data than Save would write, and no view saves as a side effect.

Abbreviations: **CLC** = `ChessLogController`; **CCC** = `ChessLogChartsController`; **CLSS** = `ChessLogStorageService`; **USS** = `UserSettingsService` (settings owner). Guard tests are named `Class.test` in the file shown; the files are listed under "Guard files" below.

| Data | Owner | Write path | Read path | Derived values → invalidated by | Views learn via | Guard tests |
|---|---|---|---|---|---|---|
| Logged moments | CLC: `_cached_paths_data` (active game) / `_multi_cache` (others); on disk, the `CARAChessLog` tag | `_write_store` (reached from `add_moment_at_active_path`, `replace_entries_at_path[_for_game]`, `clear_tags_for_current_game`); persisted only by `_save_single_game` | `get_tags_for_current_game`, `get_tags_for_game`, `get_entries_at_active_path`; background readers use `CLSS.load_resolved_paths` / `load_tags` | `_resolved_cache` (keyed by write version + PGN hash), `_cache_version_by_game`, `_cached_original_paths` → bumped by `_write_store`, refreshed by `_save_single_game` | `chess_log_changed(game)`; `metadata_updated` after a save of the active game | `TestWriteStoreIsOnlyMutationPath` (controller tests: store/clear callers, `_cached_paths_data`, `_multi_cache`, orphan removal); `TestSinglePayloadDecoder.test_decoder_is_called_from_exactly_one_place`; `TestNoDirectNotifications`; `TestChessLogControllerStoreIsPrivate` (owner guards) |
| `has_chess_log_tags` (and the Moves List icon / Log column) | CLC `_write_store` in memory; `CLSS.store_tags` / `clear_tags` after a write; `game_data_updates_for_header_tag` on load, which asks `CLSS.has_moments` | the three above, nowhere else | `game.has_chess_log_tags` | Log-column `dataChanged` on transition → `_write_store` | `chess_log_changed`; Moves List icon refresh for the active game | `TestWriteStoreIsOnlyMutationPath.test_has_chess_log_tags_assignment_only_in_allowlist`, `…test_load_tags_does_not_set_has_chess_log_tags`; `TestHeaderSyncChessLogFlag` |
| Entry flags: `is_shallow`, `is_vague`, `check_hash`, `ignore_shallow`, `ignore_text_hash` | The entry dicts inside the logged moments (same owner as the row above) | Built as copies in `ShowTagsDialog` / `ShowShallowTagsDialog`, committed through `replace_entries_at_path_for_game` + `save_games`; `CLSS.make_entry` for new entries | `CLSS.entry_has_flag`, `is_entry_checked`, `is_entry_ignore_honoured`, `compute_check_hash` | Flags count as checked only while `check_hash` matches the text → recomputed on read | as for logged moments | `TestEntryFlagWritersAreTheEditPaths` (owner guards); `TestIsEntryChecked`, `TestComputeCheckHash`, `TestMakeEntryCheckHash` |
| `nag_shown` (per game) | CLC `_nag_shown_by_game` / the payload | `should_confirm_extra_moment` (session), persisted by `_save_single_game` | `CLSS.load_nag_shown` at `_load_into_cache` | none | none | `TestChessLogControllerStoreIsPrivate.test_nag_flag_written_only_by_load_and_confirm` |
| `_check_run` (model, date of the last Check Logs run) | The payload; CLC `_pending_check_runs` until saved | `set_check_run_for_game` (queue); consumed by `_save_single_game` | `get_check_run_for_game` (pending first, then `CLSS.load_check_run`) | none | none | `TestCheckRunReadThroughController.test_no_view_calls_storage_load_check_run`; `TestChessLogControllerStoreIsPrivate.test_pending_check_runs_written_only_by_set_and_save` |
| Narrative Summary text, flags, usage, counts, model label, timestamp | CCC `_cached_narrative*` | `_on_narrative_thread_ready` / `_on_narrative_thread_failed`; cleared only by `_clear_result_cache` | `get_last_narrative_result`, `get_last_narrative_metadata` | Counts are computed from the request-time snapshot (`_narrative_request_games/_snapshot`), so they describe the same data as the text → cleared on source, player, colour or game-set change | `narrative_ready` / `narrative_failed`; `results_invalidated` | `TestChartsTabStateIsWrittenByItsController`; `TestViewKeepsNoCopiesGuard`; `TestNarrativeCountsFromRequestSnapshot`; `TestThemeRebuildReadsFromController` |
| Check Logs session result (shallow keys, vague keys, usage, model label, timestamp) | CCC `_cached_shallow_*` / `_cached_vague_keys` | `_finish_shallow_run` (every finished run, including the no-notes run); cleared only by `_clear_result_cache`; saved flags are written by the dialog's Save through CLC | `get_last_shallow_result`, `get_cached_shallow_model_label`, `get_cached_shallow_timestamp` | none (a pair of frozensets, never `None`) | `shallow_ready` / `shallow_failed` / `shallow_partial`; `results_invalidated` | `TestChartsTabStateIsWrittenByItsController`; `TestViewKeepsNoCopiesGuard.test_only_the_controller_clear_method_resets_results`; `TestNoNotesRunLeavesNothingStale`; `TestB4EmptyNotesPathLeavesControllerCacheStale` |
| Narrative model override | CCC `_narrative_model_override` | `set_narrative_model_override`; reset by `on_ai_settings_changed` when the provider changes | `get_narrative_model_override` | model list and default model are read live from USS | `ai_model_changed`, `ai_configured_changed` | `TestChartsTabStateIsWrittenByItsController`; `test_chess_log_model_settings.py` |
| Chess Log AI timeout (#90) | USS: `chess_log.ai_timeout_seconds` | `CCC.set_narrative_timeout_seconds` → `update_chess_log_settings` | `CCC.get_narrative_timeout_seconds` (read live, config default when absent) | none | none; the view restores the spin box from the getter | `TestNoSharedKeyInChessLogCode`; `TestChessLogSettingsHaveOneWritePath` (owner guards) |
| Tokens limit | CCC `_narrative_token_limit` | `set_narrative_token_limit` | `get_narrative_token_limit` | none | none; the view restores the spin box from the getter | `TestB6TokensSpinNotRestored.test_default_limit_literal_defined_once`; `TestChartsTabStateIsWrittenByItsController` |
| Chess Log settings (active preset, charts preferences, list highlight) | USS (`chess_log` section) | `update_chess_log_settings` | `get_chess_log()`; the charts controller reads AI settings live, holding no snapshot | none | `chess_log_charts_changed`, `ai_settings_changed` | `TestB7AISettingsSnapshotStale.test_controller_has_no_user_settings_snapshot_attribute`; `TestChessLogSettingsHaveOneWritePath` |
| Chess Log tab state: source, player, colour filter, charted game set, skip counts, last chart outcome, player list | CCC: `_source_selection`, `_current_player` + `_player_explicit_selected`, `_color_filter`, `_last_game_set_key`, `_last_chart_events`, `_last_players`. The game set is not stored: `_resolve_games()` re-resolves it each time | `set_source_selection`, `set_player_selection`, `clear_player_selection`, `set_color_filter`; chart outcome from the aggregation worker's signals; list from `_on_players_ready` | `get_source_selection`, `get_source_label`, `get_player_display_name`, `has_player_selected`, `get_last_chart_events`, `get_last_players` | Results, narrative and Check Logs cache → `_clear_result_cache`; player list → dropped on source change | `charts_*`, `players_ready`, `player_selection_cleared`, `results_invalidated`; a rebuilt view restores from the getters with signals blocked | `TestChartsTabStateIsWrittenByItsController`; `TestViewKeepsNoCopiesGuard.test_export_methods_never_read_the_combo_boxes`; `TestColorFilterInvalidatesResults`; `TestB3PlayerComboSilentClear`; `TestThemeRebuildRestoresSelectors` |
| Mini-board options | USS (Philipp's settings; Chess Log reads them through one helper) | not written by Chess Log | `chess_log_miniboard_settings()` in `_tag_row_helpers.py` | defaults come from the settings owner's `normalize_*` functions | none | `TestChessLogMiniboardSettings` (helper used by both dialogs, no literal default scale) |
| Exports (Copy log text / HTML, PDF report, narrative PDF) | CCC for the narrative and the Check Logs section; CLC for the moments | none — they only read | `get_check_log_moments` (saved flags for the charted games and the selected player), `get_last_narrative_result`, `get_player_display_name`, `get_source_description` | none | none | `TestThreeFormatsAgree`; `TestOnlySavedFlagsAreExported`; `TestExportScope`; `TestViewKeepsNoCopiesGuard` |
| Check Logs header counts | CLSS predicates `entry_has_flag` / `is_entry_checked`; CLC `get_shallow_vague_keys`, `count_unchecked_answers`; `compute_narrative_counts` in `chess_log_stats_service` | none — computed on read | the same accessors | computed from the stored flags every time | none | `TestExportScope.test_count_agrees_with_narrative_header`, `…test_agrees_with_show_shallow_vague_logs`; `TestIsEntryChecked`; `TestNarrativeCountsFromRequestSnapshot` |

**Guard files.** `tests/test_chess_log_owner_guards_88.py` (owner guards), `tests/test_chess_log_ssot_audit_88.py` (`TestB…`), `tests/test_chess_log_exports_91.py`, `tests/test_chess_log_ai_timeout_90.py`, `tests/controllers/test_chess_log_controller.py`, `tests/controllers/test_chess_log_changed_signal.py`, `tests/controllers/test_chess_log_charts_controller.py`, `tests/controllers/test_chess_log_model_settings.py`, `tests/services/test_chess_log_storage_service.py`, `tests/utils/test_game_data_header_sync_chess_log.py`, `tests/views/test_show_shallow_tags_dialog.py`, `tests/views/test_chess_log_miniboard_settings_helper.py`.

**Adding data.** Any new piece of Chess Log data gets a row in this table and a guard test in `tests/test_chess_log_owner_guards_88.py` (or next to the owner's other tests) that fails when code outside the owner writes it or reads around the accessor. Decide the owner, the single write method and the accessor before writing a view; if a view needs a value after a rebuild, it reads it from the owner rather than keeping its own copy. Where a source-level guard is impractical, say why in the row.

### Moment text renderer (#93)

`app/services/chess_log_moment_renderer.py` is the one place a logged moment's copyable text is built, in both clipboard flavors (plain text and HTML). Callers: the Chess Log tab's "Copy log to clipboard" and Show Shallow/Vague Logs' "Copy to clipboard".

- Callers pass `MomentRef(game, path_key, preset)`; the renderer reads entries and flags through the controller's `get_tags_for_game` at render time and keeps no copy. Games appear in first-appearance order; moments within a game in ply order.
- Show Shallow/Vague Logs in live mode (before Save) passes `entries_for=`, built from the dialog's own `_pending_entries(i)` — the same method Save uses — so its copy shows unsaved verdicts, text edits and Ignore state exactly as Save would write them. Saved mode and the Chess Log tab copy use saved entries only.
- Whole moment is listed; flagged answers are marked after the answer text. 3x3 answers are labeled with their question text (`THREE_BY_THREE_PROMPTS`), e.g. `Why did I choose that move? ... [Shallow]`; a blank answer shows only the question. Markers: `[Shallow]`, `[Vague]`, both as `[Shallow] [Vague]`. The HTML flavor draws the same markers as chips.
- Saved flags only. An answer whose Ignore is honoured (`is_entry_ignore_honoured`, which also drops Ignore when the text changed since) is unmarked.
- The move comes from `_tag_row_helpers.node_info` (`32. g5` / `32… g5`). A moment whose move cannot be located reads "Unknown move" (`display_move_label`, also used for the tab's PDF rows); a path key is never printed.
- Guards: `tests/test_chess_log_moment_guards_93.py`.

## Change notification (`chess_log_changed`)

`ChessLogController` is a `QObject` and the only thing that announces Chess Log changes.
It emits `chess_log_changed(game)` from `_write_store` (Log, Clear, dialog edits; pending
edits count) and from `_save_single_game` (after a successful persist). A save of many
games emits once per game. Subscribers:

- **Moves List view** — refreshes tag icons when the changed game is the active game.
- **Chess Log tab controller** (`ChessLogChartsController`) — one debounced
  (`_data_changed_debounce`) refresh of the player dropdown and, if a player is selected,
  the charts, using a fresh tag snapshot. The same debounce also fires on the open
  databases' `stats_relevant_data_change` (games added/removed/updated).

The Chess Log tab controller announces its own state to its view with `charts_*`, `players_ready`,
`player_selection_cleared` and `results_invalidated`, the last emitted only by `_clear_result_cache`
(see "Single source of truth"). Callers must not notify views themselves; `tests/controllers/test_chess_log_changed_signal.py`
guards against it. `_save_single_game` still emits `metadata_updated`: the PGN and Metadata
views display the `CARAChessLog` tag it writes.

## Key files

- `app/services/chess_log_storage_service.py`
- `app/controllers/chess_log_controller.py`
- `app/views/dialogs/moment_dialog.py`
- `app/views/dialogs/chess_log_settings_dialog.py`
- `app/views/menus/chess_log_menu.py`
- `app/utils/chess_log_prompts.py` — `THREE_BY_THREE_PROMPTS` dict
- `app/utils/pgn_variation_path.py` — `encode_path`

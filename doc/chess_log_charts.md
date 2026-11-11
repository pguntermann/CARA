# Chess Log Charts

Reporting and visualization layer for Chess Log — the detail tab (index 9, F10) that lets players see how their mistake mix shifts over time and get an AI narrative summary.

## Show/Hide

The Chess Log tab can be hidden via **View → Show/Hide → Chess Log**. Hiding it removes the tab and disables F10; the Time series settings submenu (and its preceding separator) in the Chess Log menu are also hidden. The top-level Chess Log menu itself remains visible so logging operations (Settings, Clear, Save, Show Logged Moments, Highlight) still work from the Moves List. Showing the tab again restores all three. The choice persists across restarts.

**Presets in scope**: CLAMP, CCT, and 3x3. Charts show only CLAMP and CCT (3x3 has no comparable category axis). The Check Logs classifier supports all three presets.

See also: `doc/chess_log.md` for the tagging layer itself.

## Charting widget

Stacked vertical `ChessLogCategoryChartWidget` instances (one per preset) in a `QScrollArea`. Each is a fresh `QPainter` widget — not a subclass of `MoveQualityOverTimeChartWidget`. The four scaffolding helpers from `player_stats_service.py` (`_game_date_ordinal_for_trends`, `_ordinal_target_bin_count`, `_ordinal_fallback_mode`, `_calendar_bin_center_time_pct`) are reused; the bin-filling functions are fresh count-based implementations in `chess_log_stats_service.py`.

Legend always shows the full canonical set for CLAMP (C,L,A,M,P) and CCT (Checks,Captures,Threats) — categories absent from the data appear dimmed (no line drawn, greyed text, 40% alpha swatch). Stale chart clears immediately on source/player/color change (via `charts_loading` signal); no visible loading indicator is shown. Player/color-filter changes are debounced (100ms) to prevent rapid-click flicker.

**Player selection is required** — changing Data Source does not auto-chart; the Player dropdown starts unselected and shows "Select a player…" in the chart area until the user makes an explicit choice.

**Player scope: own moves only.** Every player-scoped view uses only the moments logged on the selected player's own moves in the games they played — never moments on the opponent's moves in those games. This covers the charts and their undated/3x3 messages (`aggregate`), the Narrative Summary's why-notes, category counts and "no data" check (`build_prompt`, `generate_narrative`), the report header counts (`compute_narrative_counts`), the report's Check Logs section (`ChessLogChartsController.get_check_log_moments`) and the Player list (`get_all_players`, which credits each player only for their own moves). All of them call the one filter, `own_moves_paths(game, paths_data, player_cf)` in `app/utils/chess_log_color_scoping.py`, which takes a move's side from the path-key length (`color_from_path_key`); no view reads the side itself (guarded by `tests/test_chess_log_own_moves_scope.py`). With no player, or a player on both sides of a game, nothing is filtered; a player not in the game has no own moves. Whole-game notes from the Notes tab are per game, so they are included for every game the player played. Check Logs and Show Shallow/Vague Logs are not player-scoped: they work on the whole Data Source or active database.

## Time series settings menu

Chess Log → "Time series settings": 6-item, 3-group menu mirroring Player Stats exactly.

- **Group A — Binning**: "Progression bins" (8/12/16/24/32, default 16) and "Binning mode" (quantile/equal_width, default quantile).
- **Group B — X axis**: "X axis layout" (uniform_bins/gap_compressed/calendar_linear, default uniform_bins) and "Max gap segment (calendar days)" (14/28/50/100, default 28).
- **Group C — Line**: "Progression line style" (smooth/straight, default smooth) and "Smoothing strength" (0.5/1.0/1.5/2.0, default 1.0).

All 6 settings persist under `user_settings.chess_log.charts.{target_progression_bins, ordinal_fallback_mode, progression_x_axis_mode, compress_gap_max_segment_days, progression_line_style, progression_line_smooth_strength}` — leaf names aligned with Player Stats. Settings module: `app/services/chess_log_charts_user.py`. `normalize_chess_log_charts_settings()` handles settings migration on first load.

## Widget rendering

`ChessLogCategoryChartWidget` supports three x-axis layouts:

- `uniform_bins` — bins spaced evenly by index.
- `gap_compressed` — uses `GapCompressedTimeLayout` (built from bin center ordinals in `set_series`) so long game-free spans compress horizontally.
- `calendar_linear` — real fixed calendar-tick axis: `_draw_calendar_axis()` generates monthly gridlines from the full ordinal range (`ChessLogPresetSeries.t_min`/`t_max`) and `_bin_x()` places each bin at its calendar center via `ordinal_to_chart_x()` — identical coordinate systems by construction.

Smooth Catmull-Rom lines via `smooth_polyline_path()` when `series.progression_line_style == "smooth"`. `ChessLogPresetSeries` carries `t_min`/`t_max` populated by `_bin_preset()` in `chess_log_stats_service.py`.

**Check Logs PDF header**: three header lines below the logo — `Source: <source label>: <pgn-stem>[, …]`, `Generated: YYYY-MM-DD HH:MM`, `AI model: <model-id>`. For a live Check Logs run the date is taken from `_cached_shallow_timestamp` (UTC ISO-8601 captured when `shallow_ready` fires, displayed in local time). For "Show Shallow/Vague Logs" the date and model are read from each shown game's `_check_run` payload at PDF-export time: no `_check_run` on any shown game → `AI model: Saved Check Logs results`; all shown games share the same run → model+date from that run; mixed runs → most recent run's model + " (mixed runs)" and most recent date. No warning triangle (⚠️) anywhere in Check Logs PDFs.

## Shared helpers

**Shared chart helpers** (`app/views/widgets/_chart_layout_helpers.py`): `smooth_polyline_path`, `ordinal_to_chart_x`, `calendar_axis_ticks`, `effective_calendar_mode`, `week_start_monday_ordinal`, `GapCompressedTimeLayout`, `build_gap_compressed_time_layout` — used by both `ChessLogCategoryChartWidget` and the Player Stats chart widgets. A third chart tab can import from this module without creating a third copy.

**Shared menu base** (`app/views/menus/_radio_menu_controller.py`): `RadioMenuController` is the abstract base for both `ChessLogChartsMenuController` and `PlayerStatsTimeSeriesMenuController`. It owns all 6 action groups, `attach_to_parent_menu`, `sync_from_settings`, and all 6 handler methods (`_on_target_bins_selected`, `_on_ordinal_mode_selected`, `_on_x_axis_mode_selected`, `_on_gap_segment_days_selected`, `_on_line_style_selected`, `_on_smooth_strength_selected`). Subclasses only implement `_read_settings() -> Dict` and `_apply(key, value)`. Player Stats menu also adds `append_to_context_menu`. Handler methods that require the action objects guard with `RuntimeError("call _ensure_actions() first")` instead of bare asserts so the error survives Python's `-O` flag and names the violated precondition explicitly.

## Narrative

LLM-gated (same provider config as AI Summary). Prompt assembled from a per-preset glossary block, trend-binned category counts (4 bins via `aggregate()`), why-notes, and whole-game notes. `_parse_response` always returns `(narrative, [])`. `generate_narrative()` returns a `NarrativeResult` frozen dataclass: `success: bool`, `text: str`, `shallow_flags: List[str]` (always `[]`), `usage: Optional[TokenUsage]`, `model: str`. LLM-not-configured state shows a rich-text hint label (`_ai_hint`) with the text "Configure an AI provider in AI Summary → <a>AI Model Settings</a> to enable narrative summaries." — clicking the link calls `main_window._show_ai_model_settings()` via `_on_ai_hint_link_clicked`. All narrative controls are disabled until AI is configured — no restart needed (AI Model Settings close triggers `set_user_settings`). The AI state is seeded at app startup (not only on dialog close), so the hint correctly reflects the user's saved provider settings from first view. Link color per theme: `ui.panels.detail.chess_log_charts.colors.link`.

### Narrative prompt structure (assembled in `chess_log_narrative_service.build_prompt`)

1. `## Glossary — <preset>` block for each preset present in the data (verbatim definitions only — never paraphrase or invent). CLAMP has full text (C=Checks, L=Loose Pieces and Loose Squares, A=Alignments, M=Mobility Restrictions, P=Passed Pawns). CCT has full text (Checks reuses CLAMP's Checks definition verbatim; Captures reuses CLAMP's L definition with commas replacing em dashes; Threats is Paul's new definition). Note: both Checks and Captures start with C, so a CCT rule in `_SYSTEM_PROMPT` tells the model to always use the full category name, never a bare letter. A second CCT rule tells the model that CCT tags are bidirectional — a tag may describe the player's candidate move OR the opponent's prior move; always read the why-note to tell which. 3x3 does not get a letter glossary; it gets a `## Why-note structure — 3x3` block (via `_format_3x3_structure` / `_3X3_STRUCTURE_BLOCK`) that explains GM Noël Studer's four Why-questions in numbered order and states that the four answers form one connected reasoning chain: Why1=intent, Why2=what was wrong with the chosen move, Why3=why the better move is better (often the same underlying point as Why2 restated from a different angle, not always a distinct second step), Why4=lesson for next time. Either Why2 or Why3, or both, may be blank — treated as unanswered, not a break in the chain. In addition, `build_prompt` injects a `_3X3_MOMENT_SENTINEL` tuple into the `why_notes` list before each moment's block of Why-answers; `_format_why_notes` detects the sentinel and emits a `_3X3_MOMENT_FRAMING` line that repeats the chain relationship inline, immediately before each moment's notes, so the model sees the framing at the point in the prompt where it reads the actual data.
2. `## Category counts by preset (over time)` — 4 trend bins from `aggregate(chart_cfg={"target_progression_bins": 4, "min_games_per_ordinal_bin": 1})`. Fallback to flat totals + note when aggregate returns empty (no dated games).
3. Why-notes and whole-game notes. A note-normalization one-liner above the whole-game notes section instructs the model to treat them as illustrative color only, not primary evidence.
4. Narrative instruction: three sections in order — `## Patterns & Recurrent Themes` (GFM bullets, 2–4 per theme, bold lead-in; no CLAMP letter/% framing), `## Tactical Breakdown` (pipe table: `Skill | Observed Issue | Strategic Impact`; Skill = generic chess concepts — King Safety, Piece Coordination, etc.; **never** CLAMP/CCT/3x3 vocab in Skill column), `## Key Takeaways` (1–3 prose paragraphs, bold lead-in, anchored to verbatim player quote). Rules: full move+color citation required (`16. b4, White vs Black`); ≤ 1–2 verbatim quotes per section. Both surfaces render `**bold**` and `##` natively; pipe table via `setMarkdown` / `_draw_pipe_table_paginated`; bullets via `_draw_bullet_line_paginated`. Default token limit: **12000**. Constants: `_SYSTEM_PROMPT` and `_NARRATIVE_STEP` in `chess_log_narrative_service.py`; no `mode` param.

### Thinking/adaptive-reasoning gate

`generate_narrative` (`chess_log_narrative_service.py`) and `classify_notes` (`chess_log_shallow_service.py`) detect next-gen Anthropic models with default adaptive thinking (Sonnet 5, Opus 5) and pass `thinking={"type": "disabled"}` on the `AIService.send_message` call via `AIService.disable_thinking_for(model)`. Detection is a case-insensitive substring check — `"sonnet-5" in model` or `"opus-5" in model` — so dated variants like `claude-opus-5-20260901` are also caught. All other providers and model families receive `thinking=None` (no change). `AIService.send_message` and `AIService._send_anthropic_message` both accept the optional `thinking: Dict | None` kwarg; it is added to the Anthropic request body when set and ignored for OpenAI/custom endpoints.

Models that reject `thinking.type.disabled` outright cause a 400 with a recognizable message. When `AIService._send_anthropic_message` receives such a 400, it retries the request exactly once with a model-specific replacement, and caches the model ID for the remainder of the process so subsequent calls skip straight to the replacement without a failed first attempt. Models that still accept `disabled` (Opus 5, Sonnet 5) are byte-for-byte unchanged. Any other 400 is returned immediately without retrying. Two replacement strategies are in use: Opus 5.5, Fable 5, Mythos 5, and similar models whose 400 message says `"thinking.type.disabled" is not supported` get `thinking: {type: "adaptive"}` + top-level `output_config: {effort: "low"}`; Sonnet 5.5, whose 400 message says to send `between_tools` instead of `disabled`, gets `thinking: {type: "between_tools"}` with no `output_config` (the API default effort of `"high"` is within the allowed range for `between_tools`).

### Narrative panel controls (visible when AI is configured)

Model combo (ephemeral, lists models for the active provider from `ai_models.{provider}.models`), Timeout spinner (10–600s; Chess Log's own setting, persisted as `user_settings.chess_log.ai_timeout_seconds`, default **120** from `ui.panels.detail.chess_log_charts.ai.default_timeout_seconds` in `config.json`; used by both Narrative Summary and Check Logs; independent of AI Summary's `ai_summary.request_timeout_seconds` — changing either leaves the other untouched), Tokens spinner (256–99999, default **12000**, ephemeral — not persisted to user_settings).

A **"Check Logs"** button (`_show_shallow_btn`) sits between the model/timeout/tokens row and the generate button — enabled when AI is configured and both Source and Player are selected. A single **"Generate Narrative"** button (`_generate_btn`) triggers narrative generation; clicking disables it, sets the edit to "Generating…", then calls `request_narrative()` on the controller. It re-enables when `narrative_ready` or `narrative_failed` fires.

Clicking "Check Logs" disables the button, starts a `BusySpinner` and shows "Checking logs…" to the right, then calls `request_flag_shallow_notes()` on the controller. The spinner and label clear on `shallow_ready` / `shallow_failed`. If both key sets are empty, shows "Nothing Flagged" (with the partial-run notice when some notes could not be read); when the run checked at least one answer (`classified_keys` non-empty) the message has **Save** and **Cancel** (`SaveCancelMessageDialog`) — Save calls `save_clean_check_run`, which records the checked answers through `commit_check_record` (the same writer as the dialog's Save, no rows), Cancel or closing stores nothing; a run that checked nothing shows a plain message. Otherwise opens `ShowShallowTagsDialog` (window title "Check Logs").

**Token usage labels.** Two right-aligned `QLabel` instances appear after runs: `_narrative_token_label` (below `_narrative_edit`) and `_shallow_token_label` (below the Check Logs row). Lifecycle: cleared when a request *starts* and when a request *fails* — never show stale counts. Format when usage is reported: `Tokens: {in:,} in / {out:,} out`; appends ` / {thinking:,} thinking` when `reasoning_tokens > 0`. When usage is absent from the provider response: `Token usage not reported by this provider`. Styled via `ui.panels.detail.chess_log_charts.token_usage_label.{color, font_size}` in all three theme JSONs (registered in `config_loader`; covered by `test_theme_coverage`). Labels are pure view widgets — not passed to `ChessLogPDFService`; a PDF absence test in `tests/services/test_chess_log_pdf_service.py` confirms this.

**Signal arity.** `narrative_ready = pyqtSignal(str, list, object)` carries `(text, shallow_flags, usage: Optional[TokenUsage])`; `shallow_ready = pyqtSignal(object, object, object, object)` carries `(shallow_keys, vague_keys, classified_keys, usage: Optional[TokenUsage])`. All three key sets use **4-tuple** `(game, path_key, preset, cat)` keys where `game` is the **GameData object** (Python identity, not `game_number`): CLAMP/CCT use `cat=""` (empty string); 3x3 uses `cat` in `{"Why1","Why2","Why3","Why4"}`. `classified_keys` is a `frozenset` of 4-tuples that were parsed this run (the "touchable set"); `shallow_keys ∪ vague_keys ⊆ classified_keys`. `vague_keys` is always empty for CLAMP/CCT notes. Both thread classes and the controller class use these arities. Every consumer (`_on_narrative_ready`, `_on_shallow_ready`, all test stubs) must accept all arguments.

The controller's `get_available_models()` / `get_default_narrative_model()` / `get_narrative_timeout_seconds()` drive the view; `set_narrative_*()` setters update the in-memory state (timeout also persists to `chess_log.ai_timeout_seconds`, read live at each request).

### Narrative sanitization

`sanitize_narrative_markdown(text)` in `chess_log_narrative_service.py` is the single gate that cleans LLM output before it reaches either rendering surface. It drops (1) bare thematic-break lines (`---`/`***`/`___` alone on a line — the PDF renderer has no HR branch and would draw them as literal text) and (2) pipe-table body rows whose any cell is empty after stripping (defense in depth against blank Strategic Impact cells the model occasionally emits). Both `detail_chess_log_charts_view._on_narrative_ready` (the `setMarkdown` call) and `ChessLogPDFService._draw_narrative_paginated` call it on the raw string so both surfaces are guaranteed identical clean input. Table separator rows (`| --- | --- | --- |`) are preserved — the thematic-break rule requires no `|` in the line.

### Narrative rendering

`ChessLogPDFService._draw_narrative_paginated` is block-aware: (1) `##` headings via `_section_heading`; (2) pipe tables via `_draw_pipe_table_paginated` — bordered QPainter cells, filled header row, word-wrapped body cells, column widths from `table_col_widths_pct` (default `[20, 40, 40]`); (3) GFM bullets via `_draw_bullet_line_paginated` — hanging-indent `•` with `_draw_wrapped_spans`. All blocks atomic (measure → `_ensure_space` → draw); prose falls to `_parse_bold_spans`. Screen: `setMarkdown`; errors: `setPlainText`. Pipe table: header row and Skill column always bold; other cells via `_parse_bold_spans`. `_measure_bullet_line` uses `_count_cell_lines` (not `boundingRect`) — `boundingRect` underestimates height for bold lead-ins, causing overlap. PDF header: logo ≤ 36pt; HR at `max(text_bottom, logo_bottom + 4)`; `export_charts_report` adds "Generated: YYYY-MM-DD HH:MM" after Source.

## Check Logs

### Check Logs dialog

`app/views/dialogs/show_shallow_tags_dialog.py`, class `ShowShallowTagsDialog` (internal name unchanged). Two entry points:

- **Live Check Logs** (window title "Check Logs"): opened from `_on_shallow_ready` after a classifier run; receives `classified_keys` (frozenset of 4-tuples the AI touched), `shallow_keys ∪ vague_keys` (flagged subset), and `check_run_info` (`{"model": …, "date": …}` built from `_cached_shallow_timestamp`).
- **Show Shallow/Vague Logs** (window title "Shallow/Vague Logs"): opened from *Chess Log → Show Shallow/Vague Logs*; collects rows with stored `is_shallow`/`is_vague` across all games in the active database. `classified_keys` is `frozenset()` (no AI ran), so stale-clear Phase b and Phase c are both no-ops — **no `check_hash` or `_check_run` is written on Save**.

Displays rows whose 4-tuple keys `(game, path_key, preset, cat)` are in `shallow_keys ∪ vague_keys`. For 3x3 a moment row appears if **any** of its cat-level keys is flagged; for CLAMP/CCT the row appears when `(game, pk, preset, "")` is flagged.

**Save/Cancel model**: edits are buffered in row widgets until the user clicks **Save**. Save stamps `is_shallow=True` / `is_vague=True` per-entry (per 4-tuple key membership), clears stale flags on classified-clean entries (scoped to `classified_keys` only — entries the classifier didn't touch are never modified), then calls `save_games()`. For 3x3, stale-clear operates per-entry: only entries whose exact `(gn, pk, "3x3", cat)` key is in `classified_keys` but not in `flagged_keys` get their flags cleared; entries outside `classified_keys` are untouched. **Cancel** and the window close button discard all edits. **Export to PDF** button (left of button row) calls `ChessLogPDFService.export_tags(..., is_shallow_only=True)` with a WYSIWYG snapshot of current row state; PDF title "Chess Log — Check Logs", filename segment "CheckLogs".

**Unchecked-notes banner** (Saved mode only): when `_is_saved_mode` is `True` (i.e. `classified_keys` is empty), a banner label is shown at the top of the dialog if `count_unchecked_answers() > 0`. Text: `"{N} note{s} {have/hasn't} been checked yet (new or edited since the last Check Logs). Run Check Logs to check them."` Counting unit: **CLAMP/CCT count per distinct `why` text per moment** (mirrors `build_notes` — one note shared across C and L counts once); **3x3 counts per-answer**. Entries with a valid `check_hash`, a legacy `is_shallow`/`is_vague` flag, or a honoured `ignore_shallow` are considered checked. Banner colors come from `ui.dialogs.shallow.unchecked_banner.{background_color,text_color}` in the theme files. The banner is **never** shown during a live Check Logs run.

**Row display**: CLAMP/CCT rows show **Ignore** in the move-header row (`show_ignore_checkbox=True`). 3x3 rows show per-answer Ignore checkboxes stacked below the chip in the chip column (right of the answer box). No ⚠️ triangle anywhere. `ShowShallowTagsDialog._setup_ui()` pre-stamps entries per-entry (via `_stamp_entries`) before constructing `_TagRowWidget`, so chip labels appear during the current run even before Save.

**Row chips**: chip placement is per-preset. CLAMP/CCT: chips render in the move-header row (unchanged). 3x3: chips render in a fixed-width column to the **right of the answer box**, top-aligned with the answer; the Ignore checkbox is stacked below the chip. The question line contains only the question text. A Why without a chip uses the full answer width. **Chip-eligibility rule (B4)**: `Shallow` may only render on entries with `cat ∈ {Why1,Why2,Why3}`; `Vague` may only render on `cat = Why4`. Legacy data that stored `is_shallow` on Why4 or `is_vague` on Why1-3 is ignored at render time. Chip colors and text from `ui.dialogs.shallow.labels.{shallow,vague_lesson}` — colors in theme files, text/tooltip in `config.json`. `ShowTagsDialog` (Show Logged Moments) also shows chips from stored flags; ignored entries render the chip at 40% opacity with a ticked Ignore checkbox so the user can untick from there (B10a).

**Help icon**: a ⓘ `QToolButton` in the dialog header (via `app/utils/help_icon.py`) opens a modal with the text from `ui.dialogs.shallow.help_text` in `config.json`. Wording explains each chip's meaning, when Ignore stops a chip from returning, and the edit→hash-mismatch auto-clear rule.

**Stale chips**: a chip in ShowTagsDialog (Show Logged Moments) can only be stale when the AI changed its verdict without the text being edited — because editing an answer already clears its chip before Check Logs can run. A chip that survives to ShowTagsDialog reflects the AI's last verdict on unchanged text.

Each row's miniature board is oriented so the mover at the tagged ply is at the bottom — see the "Miniature board orientation" note in `doc/chess_log.md`. The `_export_pdf_report` path on `DetailChessLogChartsView` synthesizes `TagRowSnapshot` objects directly (bypassing the dialog) and populates `is_flipped` from `node_info()` the same way, so charts-tab PDF exports orient Check Logs rows identically.

### `ignore_shallow` schema field

Added to entry dicts via `ChessLogStorageService.make_entry(preset, cat, why, ignore_shallow=False)`. Omitted from the dict when `False` (backward-compatible — old entries read as `ignore_shallow=False` via `.get("ignore_shallow", False)`). Preserved through controller round-trips: both `replace_entries_at_path` and `replace_entries_at_path_for_game` pass `ignore_shallow=bool(e.get("ignore_shallow"))` when reconstructing entries via `make_entry`. `_TagRowWidget` without `show_ignore_checkbox` transparently carries the original moment-level flag through `get_current_entries()`.

**`ignore_text_hash`**: SHA-256 hex digest of `why.strip()` at the moment the user ticked Ignore. Stored alongside `ignore_shallow=True` via `make_entry(... ignore_text_hash=...)`. Ignore is only honoured when `ignore_text_hash` is present **and** matches `sha256(current_why.strip())`. A mismatch means the answer was edited after Ignore was set — all three fields (`ignore_shallow`, `ignore_text_hash`, and the chip flag) are cleared automatically and the entry is re-judged on the next Check Logs run. Entries with `ignore_shallow=True` but no `ignore_text_hash` (written before this field existed) show the chip once; the stale Ignore is cleared on first Save.

**Editing an answer clears its chip and Ignore**: whenever Show Logged Moments saves a change and the answer text differs from what was stored, `_TagRowWidget.get_current_entries()` calls `ChessLogStorageService.clear_verdict_if_text_changed()` to strip `is_shallow`, `is_vague`, `ignore_shallow`, and `ignore_text_hash` from that entry before writing. Applies to 3x3 answers and CLAMP/CCT notes alike; only the entry whose text changed is affected. Check Logs judges the new text fresh on the next run.

### `is_shallow` schema field

Added to entry dicts via `ChessLogStorageService.make_entry(preset, cat, why, is_shallow=False)`. Omitted when `False` (backward-compatible). **Written by `ShowShallowTagsDialog._on_save()`** (Save-deferred — no longer written directly by the controller after classification). Persisted to the PGN via the normal Save Chess Log flow (same lifecycle as `ignore_shallow`). Both `_TagRowWidget._preserved_is_shallow` and `get_current_entries()` carry the flag through edits so it survives round-trips in both dialogs.

**CLAMP/CCT**: `is_shallow` is written per `(game, path_key, preset)` key. A position tagged with two CLAMP letters (e.g. C and L) produces two entries; the classifier returns a single verdict for that key and both entries get `is_shallow=True`.

**3x3**: `is_shallow` is written per-entry, keyed by the 4-tuple `(game, path_key, "3x3", cat)`. Only entries with `cat ∈ {Why1,Why2,Why3}` receive `is_shallow=True` — a GENERIC verdict on a Why answer does not affect Why4. The B4 chip-eligibility rule also enforces this at render time.

### `is_vague` schema field

Added to entry dicts via `ChessLogStorageService.make_entry(preset, cat, why, is_vague=False)`. Omitted when `False` (backward-compatible). Mirrors `is_shallow` end-to-end: same Save-defer contract, same round-trip carriers (`_preserved_is_vague`, `get_current_entries()`), same stale-clear scope in `ShowShallowTagsDialog._on_save()`.

`is_vague=True` is only ever set for 3x3 notes. CLAMP/CCT classifier never emits `vague_keys` — `vague_keys` is always `frozenset()` for those presets.

**Per-answer rules** (applied in Python after the 3x3 classifier reply, never by the model):

Each answer is judged independently — no answer can rescue or cancel another verdict. The old "real lesson rescues a generic Why" rule is removed.

| Answer | Verdict | `is_shallow` | `is_vague` |
|--------|---------|-------------|------------|
| Why1, Why2, or Why3 | SPECIFIC | false | false |
| Why1, Why2, or Why3 | GENERIC | **true** | false |
| Why1, Why2, or Why3 | BLANK | false | false |
| Why4 (Lesson) | REAL | false | false |
| Why4 (Lesson) | FILLER | false | **true** |
| Why4 (Lesson) | BLANK | false | false |

Rules: for Why1–3, `is_shallow = (verdict == "GENERIC")`; for Why4, `is_vague = (verdict == "FILLER")`. BLANK is never flagged. A GENERIC Why3 does not make Why4 vague; a REAL Why4 does not rescue a GENERIC Why1.

**Repair for broken storage** (`_stamp_entries` inference + `inference_repair_needed`): a prior bug in `ShowShallowTagsDialog._on_save()` part (b) stale-clear could strip `is_vague` from a Why4 entry while leaving `ignore_shallow=True` (dropped flag shape). The C1 fix in `_stamp_entries` infers `is_vague=True` for any 3x3 entry whose Ignore is honoured but whose chip flag is absent, so the chip appears correctly in the dialog. Part (a) of `_on_save` detects this shape via `inference_repair_needed` and forces a Save even when the user made no changes, writing `is_vague=True` back to storage on first open. Part (b) stale-clear now guards honoured-Ignore entries (`not is_entry_ignore_honoured(e)`) so it cannot re-create the broken shape.

### `check_hash` entry field

A 16-character lowercase hex string — the first 16 characters of `SHA-256(why.strip().encode("utf-8")).hexdigest()`. Written per-entry on `ShowShallowTagsDialog._on_save()` alongside `is_shallow`/`is_vague`. Omitted when absent (backward-compatible — entries without it are treated as unchecked by `is_entry_checked()`).

**Purpose**: lets the dialog (and "Show Shallow/Vague Logs") tell at a glance whether the AI verdict on record matches the current answer text. `is_entry_checked()` returns `True` when the stored hash matches `SHA-256(why.strip())[:16]`, when legacy `is_shallow`/`is_vague` flags are set (pre-hash entries), or when the entry's Ignore flag is honoured. Parse failures leave the entry unchecked regardless of hash.

`check_hash` is **never cleared on text edit** — `clear_verdict_if_text_changed()` strips `is_shallow`, `is_vague`, `ignore_shallow`, and `ignore_text_hash`, but not `check_hash` (the hash is stale once the text changes, but there is no harm in leaving it; it will simply mismatch and the entry will show as unchecked until the next Check Logs run writes a fresh hash).

Shared helper: `ChessLogStorageService.compute_check_hash(why: str) -> str` — call this rather than inlining the SHA-256 expression.

### `_check_run` payload key

Top-level key in the PGN `[ChessLog ...]` payload (sibling of `paths`, `preset`, etc.). Shape:

```json
{"model": "claude-sonnet-4-6", "date": "2026-10-30T14:23:45Z"}
```

`date` is UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`), captured when `shallow_ready` fires in `_on_shallow_thread_ready`. Written by `ShowShallowTagsDialog._on_save()` Phase c for every game that was saved during the run. Read by `ChessLogStorageService.load_check_run(game) -> Optional[Dict]`.

PDF uses the stored date converted to local time via `_format_check_run_date()` in `show_shallow_tags_dialog.py`. "Show Shallow/Vague Logs" reads `_check_run` per shown game at PDF-export time — see **Check Logs PDF header** above for the single/mixed/no-run logic.

### `request_flag_shallow_notes()` in `ChessLogChartsController`

Spawns `ChessLogShallowThread`; on completion captures a UTC ISO-8601 timestamp (`_cached_shallow_timestamp`) and caches `shallow_keys`, `vague_keys`, `classified_keys`, and `usage` in `_cached_shallow_keys`, `_cached_vague_keys`, `_cached_shallow_usage`; emits `shallow_ready(shallow_keys, vague_keys, classified_keys, usage)`. **Does not write `is_shallow`/`is_vague`** — that is Save-deferred to `ShowShallowTagsDialog._on_save()`. Emits `shallow_failed(str)` on error; `shallow_partial(str)` then `shallow_ready(...)` on partial-parse. Skips entries where `ignore_shallow=True` **and** `ignore_text_hash` matches `sha256(current_why.strip())` (hash mismatch = Ignore lapsed, entry is re-sent). For 3x3, a moment is sent if any of its answers is not ignored; all four answers are always included so the model sees context; verdicts for ignored answers are discarded before key expansion. A moment where every non-blank answer is ignored is not sent. Public accessor `get_chess_log_controller()` exposes the underlying `ChessLogController` to the view.

**3-way terminal branch** (#98): `ChessLogShallowThread.run()` emits exactly one of: (a) nothing could be read → `shallow_failed(msg)` only, with N the total number of notes sent; (b) some unreadable (flagged or not) → `shallow_partial(msg)` then `shallow_ready(...)`; (c) clean → `shallow_ready(...)` only. A partial run that flagged nothing reaches the Nothing Flagged message with the partial notice and Save/Cancel; `shallow_failed` is never emitted together with `shallow_ready`.

### `ChessLogShallowService` — classifier service

Classification logic in `app/services/chess_log_shallow_service.py`. `ChessLogShallowThread` is a thin QThread wrapper that makes **two** API calls (one for CLAMP/CCT via `classify_notes()`, one for 3x3 via `classify_notes_3x3()`) and merges results before emitting signals.

**CLAMP/CCT classifier** (`classify_notes`): sends notes built as `(idx, gn, pk, preset, why)` 5-tuples to `prompts.chess_log.classifier`. Reply format: `<idx>: SHALLOW` or `<idx>: DEEP`. Line-anchored MULTILINE regex `_LINE_RE`; preprocesses glued blocks (SHALLOW/DEEP immediately followed by a digit). Returns `ShallowResult(shallow_keys, classified_keys, vague_keys=frozenset(), ...)`.

**3x3 classifier** (`classify_notes_3x3`): sends notes built as `(idx, gn, pk, "3x3", why1, why2, why3, why4)` 8-tuples to `prompts.chess_log.classifier_3x3`. Empty answers are sent as `(blank)`. The classifier_3x3 prompt body (see `prompts.chess_log.classifier_3x3` in `config.json`) contains `{why1_q}`/`{why2_q}`/`{why3_q}`/`{why4_q}` placeholders filled at build time from `THREE_BY_THREE_PROMPTS` in `app/utils/chess_log_prompts.py` — same wording the 3x3 dialog shows. The v2 prompt provides richer INTENT and LESSON rubrics: INTENT is SPECIFIC when the answer identifies the concrete plan or piece, GENERIC when it names a vague category without concrete detail, and BLANK when the answer is empty or a non-answer; LESSON is REAL when it names a concrete, transferable rule, FILLER when it is a platitude or truism that could apply to any mistake, and BLANK when absent. Full text is in `config.json`. Reply format: `<idx>: WHY1=<SPECIFIC|GENERIC|BLANK> WHY2=<SPECIFIC|GENERIC|BLANK> WHY3=<SPECIFIC|GENERIC|BLANK> LESSON=<REAL|FILLER|BLANK>`. Line-anchored MULTILINE regex `_LINE_RE_3X3`; requires all four fields on the same line in order. Prose mid-sentence is rejected (the entire line must be the verdict). After parsing, Python expands each 4-tuple verdict into per-cat 4-tuple keys: `(gn, pk, "3x3", "Why1")` in `shallow_keys` iff WHY1==GENERIC, `(gn, pk, "3x3", "Why4")` in `vague_keys` iff LESSON==FILLER, etc. Verdicts for ignored answers (hash-matched) are discarded before key expansion. (See per-answer rules table in the `is_vague` section above.)

**Unparsed indices**: an index is "parsed" when the reply contains a matching verdict line with all required fields. Unparsed indices are never flagged — they remain unflagged. `ShallowResult.unparsed_indices` carries them. When non-empty: `shallow_partial(msg)` then `shallow_ready(...)`. When none could be read: `shallow_failed(msg)` only (some read and none flagged is a partial run, not a failure). **B11 defensive fix**: when `result.success == False`, `ChessLogShallowThread.run()` treats all notes in that call as unparsed regardless of `unparsed_indices` — a failed call contributes nothing to `classified_keys`.

**Token budget**: `max(2000, n_notes * 60 + 500)` for CLAMP/CCT; `max(2000, n_notes * 90 + 500)` for 3x3 — the four-field reply is roughly 3× longer per note than the SHALLOW/DEEP response. Applied separately to each classifier call.

**Diagnostic logging**: on any parse failure, logs model, stop_reason, block_count, block_types, usage, and first 4000 chars of reply. ERROR for all-fail, DEBUG for partial-fail. Each classifier call logs at DEBUG before dispatch: model id and thinking payload.

## Undated game skipping

Games whose `Date` header is `????.??.??` (or any value that `_game_date_ordinal_for_trends` cannot resolve) cannot be placed on the time axis. The aggregation pipeline handles them as follows:

- **CLAMP/CCT moments in undated games** are counted but not charted. The count is returned as `AggregateResult.n_undated_clamp_cct`.
- **3x3 moments** are noted via `AggregateResult.has_3x3` (regardless of date); undated 3x3 games do not increment `n_undated_clamp_cct`.

`ChessLogAggregationWorker` uses these fields — `has_any_moments()` is removed:

| Scenario | Signal emitted |
|---|---|
| Dated CLAMP/CCT data present | `charts_updated(series_dict)` then `charts_skipped(n_undated_clamp_cct)` |
| Only undated CLAMP/CCT games (n > 0) | `charts_unavailable("no_dated_clamp_cct:N:B")` where N=count, B=1 if has_3x3 |
| No CLAMP/CCT; only 3x3 | `charts_unavailable("no_chartable_preset")` |
| No moments at all | `charts_unavailable("no_data")` |

When `charts_updated` is emitted, the view shows the charts and — if `n > 0` — a one-line skip note immediately below. The note text is `"{N} game(s) not charted: no date."` (singular "game" when N=1). The note is styled with `hint_text` color and cleared on every `_clear_charts()` call. It does not appear in PDF exports or clipboard copies.

When `charts_unavailable("no_dated_clamp_cct:N:B")` is emitted, the placeholder text is:

```
No chart data for this selection.
N game(s) with CLAMP/CCT moments has/have no date, and charts need dated games.
[3x3 moments are not shown in charts — use Generate Narrative Summary below.]  ← only when B=1
```

**`AggregateResult`** is a plain dataclass (no dict protocol) returned by `aggregate()` in `chess_log_stats_service.py`. Fields: `series: Dict[str, ChessLogPresetSeries]`, `n_undated_clamp_cct: int`, `has_3x3: bool`. All callers access `result.series` explicitly. `has_any_moments()` is deleted.

## Right-click context menu

`app/views/menus/chess_log_charts_context_menu.py`: right-clicking any chart widget or the narrative panel opens a three-action menu.

- *Copy section to clipboard* — for charts, inserts a placeholder line ("Category chart \<preset\>: see Chess Log Charts tab"); for the narrative panel, inserts the current narrative text verbatim.
- *Copy log to clipboard* — text of all charts (as placeholder lines) + narrative + the saved Check Logs flags (see below); format: one line per (game / move / preset / cat / why).
- *Export PDF Report* — same content as Copy Log (text and HTML) as a PDF: chart widgets via `widget.grab()` embedded as images, narrative as text, shallow-tag row cards with atomic pagination.

Each `ChessLogCategoryChartWidget` and the narrative `QFrame` carry a `section_name` property (`f"chart_{preset}"` / `"narrative"`) used for hit-testing in `contextMenuEvent`. `_narrative_edit` uses `Qt.ContextMenuPolicy.NoContextMenu` so right-clicks bubble up rather than opening the built-in text-edit menu.

**Result store and exports (#91)**: `ChessLogChartsController` is the only store for the tab's results — the narrative text and its metadata, the session Check Logs result as a `(shallow, vague)` pair of frozensets (empty, never `None`), the selected player (`get_player_display_name()`) and the data source (`get_source_label()` / `get_source_description()`). `DetailChessLogChartsView` keeps no copies; it reads from the controller on demand, including after a theme rebuild (`apply_theme()` builds a fresh view on the same controller). `_clear_result_cache()` is the only thing that clears results and it emits `results_invalidated`; the view's handler only resets the display. Source, player and colour change handlers go through it, and so does every Check Logs run that finishes, including the "no notes to classify" run (`_finish_shallow_run`).

**Exports list saved Check Logs flags only.** Copy log as text, Copy log as HTML and the PDF report share one builder: `ChessLogChartsController.get_check_log_moments()` returns a `CheckLogMoment` per moment carrying a saved `is_shallow` / `is_vague` flag (`ChessLogController.get_shallow_vague_keys` + `ChessLogStorageService.entry_has_flag`), limited to the charted games and the selected player (same scope as the narrative header's flagged count). The view turns those moments into text lines or `TagRowSnapshot` rows, so all three formats list the same moments with the same chip flags. A classifier verdict that was Cancelled (never saved), or whose entry was edited afterwards, is never exported; the exports, Show Shallow/Vague Logs and the narrative header count therefore always agree. The session result in the controller is not used by exports; it only restores the Check Logs token label after a rebuild.

**Result cache across view rebuilds**: `ChessLogChartsController` caches the most recent successful narrative (`_cached_narrative`, `_cached_narrative_flags`, `_cached_narrative_usage`) and Check Logs result (`_cached_shallow_keys`, `_cached_vague_keys`, `_cached_shallow_usage`). `DetailChessLogChartsView.set_controller()` reads this cache and restores the display, so a theme change (which rebuilds the central widget) does not lose the narrative or Check Logs results. The cache is cleared on database switch, source change, and player change — events that genuinely invalidate the data — but not on cosmetic actions like theme switching or resizing.

## PDF export

**Export PDF Report source label**: the PDF header reads `Source: <source label>: <pgn-stem>[, <pgn-stem>...]`. The filename list is built by `ChessLogChartsController.get_current_source_filenames()`, which mirrors the `_resolve_games` selection logic (active database → 1 name; all open → N names). `DatabaseModel.display_name` (Path stem or "Clipboard") is used for each entry.

**Tag row cards in PDFs** are sized dynamically: `card_h = pad*2 + header_h + 4 + max(board_sz, body_content_h)`. `body_content_h` is measured via `painter.boundingRect`: for CLAMP/CCT, checkboxes×line_h vs. word-wrapped why-text; for 3x3, the sum of four Why-block heights where each block = one full-width prompt line + `max(answer_height, chip_column_height)`, plus a blank spacer line (`body_line_h`) after Why1/Why2/Why3 but **not** after Why4/Lesson. For 3x3 the chip is drawn in a fixed-width right column beside the answer (top-aligned); the question line spans the full width with no chip. A blank Why still renders its question line. `_measure_tag_row_height` and the Phase 1 measure inside `_draw_tag_row` must use identical logic — a discrepancy causes pagination overflows. Cards are never taller than content requires. The helper `ChessLogPDFService._measure_tag_row_height(painter, content, row)` is called both by `_draw_tag_row` (for `_ensure_space`) and by `export_tags` / `export_charts_report` (for the `keep_with` parameter in `_section_heading`, ensuring game headers never orphan from their first row).

**Chess Log PDF print theme**: `ChessLogPDFService.__init__` extracts `ui.panels.detail.chess_log_charts.pdf_report` and passes it as `report_cfg` to `BasePDFReportService.__init__`, which deep-merges it over `ui.pdf`. The `pdf_report` block is defined in all three theme JSON files under `chess_log_charts.pdf_report.colors`; values are print-safe (dark ink on light page) and identical across themes. Callers pass `config` only — no API change.

**Tech debt** (`widget.grab()` chart quality): `ChessLogPDFService.export_charts_report` embeds charts as screen-resolution pixmaps from `widget.grab()`. Player Stats re-renders charts natively via QPainter from series data. If PDF chart quality is inadequate, the upgrade path is a native-QPainter pipeline in `ChessLogPDFService` — flagged as tech debt; the existing path is upgradeable without API changes.

### Narrative Summary PDF and Charts report header (#72)

**Narrative Summary PDF** — context menu item "Export Narrative Summary" → `DetailChessLogChartsView._export_narrative_pdf` → `ChessLogPDFService.export_narrative_report`.

- Title: "Chess Log — Narrative Summary". File name: `CARA-ChessLogNarrativeSummary-{player}-{ts}.pdf` (player name sanitised; no player → timestamp only).
- Header lines: `Player:`, `Source:`, the counts line, `Generated:`, `AI model:`.
- The counts line format is `N games · G with logged moments · M moments · S Shallow` (or `S Shallow/Vague` when any counted moment is 3x3). Counts follow the player scope rule above (own moves only, via `own_moves_paths`), the same as the charts and narrative under them. A moment is the group of entries at one (path_key, preset) pair. S counts moments with any Shallow or Vague flag (`is_shallow=True` or `is_vague=True`); **Ignored flags count** — the Ignore checkbox does not reduce S. This matches the rule used by `ChessLogController.get_shallow_vague_keys` (Show Shallow/Vague Logs). Moments that have never been through Check Logs (no `is_shallow`/`is_vague`) are not counted in S. The label is "Shallow" when every counted moment is CLAMP/CCT; "Shallow/Vague" when any is 3x3 (including mixed-method sets). `shallow_flag_label(has_3x3)` in `chess_log_stats_service.py` returns the label string.
- All five values (N, G, M, S, has_3x3), plus the generation timestamp and model label, are captured at narrative-generation time inside `ChessLogChartsController._on_narrative_thread_ready` via `compute_narrative_counts` (in `chess_log_stats_service.py`) and stored in `_cached_narrative_counts`, `_cached_narrative_generated_at`, `_cached_narrative_model_label`. The model label is pre-captured in `_pending_narrative_model_label` at `request_narrative()` time so it reflects the model that was actually sent. `get_last_narrative_metadata()` surfaces all seven values to the view.
- Cache lifecycle matches the narrative text: cleared on source, player, or database change; survives theme rebuilds.

**Charts tab Export PDF Report** (title unchanged: "Chess Log Charts", file name unchanged) shows the same header lines when a narrative has been generated: Player, Source, counts, Generated (the narrative's generation time), AI model. When no narrative has been generated, only Player, Source, and `Generated:` (the current export time) appear — no counts and no AI model line.

## HTML clipboard export (#73)

Four Chess Log copy actions write **dual-flavor** clipboard data (HTML + plain text via `QMimeData.setHtml` / `QMimeData.setText`). Apps that understand HTML (Notion, chess.com forums, Mail) paste the rich version; plain-text destinations get the raw text.

### Actions and their HTML structure

| Action | Entry point | HTML title |
|---|---|---|
| Charts tab — Copy section (narrative) | `DetailChessLogChartsView._copy_section_to_clipboard("narrative")` | same header as Narrative Summary PDF |
| Charts tab — Copy log | `DetailChessLogChartsView._copy_log_to_clipboard()` | same header as Charts report PDF |
| ShowTagsDialog — Copy to clipboard | `ShowTagsDialog._on_copy_to_clipboard()` | `Chess Log — Logged Moments` |
| ShowShallowTagsDialog — Copy to clipboard | `ShowShallowTagsDialog._on_copy_to_clipboard()` | `Chess Log — Check Logs` |

Non-narrative chart sections (e.g. "Copy section → chart_CLAMP") keep plain-text-only behavior — no HTML added.

### `ChessLogHTMLService` (`app/services/chess_log_html_service.py`)

Stateless service instantiated with `config` (the merged application config). Constructor reads chip label strings from `config.ui.dialogs.shallow.labels`.

**Public methods**:
- `narrative_html(player_name, source_label, narrative_text, *, n_games=0, g_games=0, m_moments=0, s_flagged=0, has_3x3=False, generated_at="", model_label="")` → full HTML string
- `charts_log_html(player_name, source_label, chart_preset_names, narrative_text, check_log_groups, *, n_games=0, g_games=0, m_moments=0, s_flagged=0, has_3x3=False, generated_at="", model_label="")` → full HTML string
- `logged_moments_html(tag_groups)` → full HTML string (prefixed `<h2>Chess Log — Logged Moments</h2><hr>`)
- `logged_moments_plain(tag_groups)` → plain-text string matching existing PDF format
- `check_logs_html(tag_groups, *, source_label="", model_label="", generated_at="")` → full HTML string
- `check_logs_plain(tag_groups, *, source_label="", model_label="", generated_at="")` → plain-text string matching existing PDF format

The dialog copy buttons copy the dialog's current state, including unsaved edits, the same as Export to PDF — both call the same `_build_tag_groups()` which reads from `row_widget.snapshot()`.

**Tag row layout**:
- **3x3**: `<p><strong>move</strong></p>` then for each Why: `<p><strong>question</strong> [chip]</p>` + optional `<p>answer</p>` (stacked paragraphs — no table).
- **CLAMP/CCT**: `<p><strong>move</strong>&nbsp;<strong>cats</strong>&nbsp;[chip]</p>` + optional `<p>note</p>`.

`<hr>` separates report header from game groups, and appears between games (not before the first or after the last).

### Pipe-table handling in narrative HTML

Philipp's `markdown_to_html.py` handles most markdown but not GFM pipe tables. `ChessLogHTMLService` contains its own `_split_narrative_blocks()` + `_gfm_table_to_html()` to detect and convert pipe-table blocks; other blocks are passed to `markdown_to_html(block, heading_level_offset=1)` so `##` headings become `<h3>` (not `<h1>`). `markdown_to_html.py` is never modified — all authorship belongs to Philipp Guntermann.

### Chip colors (WCAG AA)

Shallow and vague chips use high-contrast colors so they are readable on both light and dark HTML backgrounds.

| Chip | Background | Contrast vs white text |
|---|---|---|
| Shallow | `#9a4400` (dark orange) | ≈ 6.6 : 1 |
| Vague | `#1d4ed8` (dark blue) | ≈ 6.7 : 1 |

Both exceed the WCAG AA threshold of 4.5:1. All `html.escape()` calls in the service use `quote=False` so apostrophes in Why-question text stay as literal `'` rather than being encoded to `&#x27;`.

### Tests

End-to-end clipboard tests: `tests/views/test_chess_log_clipboard.py` (6 classes — one per copy action, plus chip-lookup verification for CLAMP and 3x3). These verify actual `QMimeData` HTML and plain-text contents, not just the generator in isolation. The chip-lookup tests build `shallow_keys`/`vague_keys` through the classifier's real parse step (`_parse_verdicts` / `_parse_3x3_verdicts`) rather than hand-written tuples.

Unit tests for the HTML service: `tests/services/test_chess_log_html_service.py`. Includes `TestGameHeaderText`, which compares `game_header_text()` output byte-for-byte against the original inline format for a game with all fields and one with missing fields.

## Multi-game cache and save-all

**Save Chess Logs for all games** (Chess Log menu, no shortcut): saves every game in `ChessLogController._dirty_games` via `ChessLogStorageService.store_tags` directly — does NOT flip the active game. Handler: `MainWindow._save_chess_logs_for_all_games` → `chess_log_controller.save_all_dirty_games()`. Reports count of saved/failed games in the status bar. Cache coherency across active-game transitions: Rule A (activation promotes from multi-cache before hitting disk) and Rule B (deactivation flushes single-game cache into multi-cache) ensure edits to inactive games are never silently discarded.

**Multi-game cache in ChessLogController**: `_multi_cache: Dict[int, Dict[str, List[Dict]]]` (keyed by game_number) holds moments for games not currently active; `_dirty_games: Dict[int, GameData]` tracks which games have unpersisted edits. Public API: `get_tags_for_game(game)`, `replace_entries_at_path_for_game(game, path_key, preset, entries)`, `save_all_dirty_games() -> Tuple[int, int]`, `has_dirty_games() -> bool`. A game lives in exactly one store at a time — single-game cache when active, multi-cache when not.

## Theming

`DetailChessLogChartsView` reads all colors from `ui.panels.detail.chess_log_charts` in the merged config. Color values live exclusively in the three theme JSON files (`style_default`, `style_light`, `style_scholar`) under `ui.panels.detail.chess_log_charts.{chart,colors,pdf_report,category_colors}` — **never in `config.json`**, because `config.json` takes precedence in the merge and would block style overrides.

The tab is non-modal (embedded in the central widget); `MainWindow.apply_theme()` calls `takeCentralWidget()` + `_setup_ui()`, which destroys and rebuilds the entire central widget including this tab — so a fresh `__init__` with the new config IS the live-update mechanism; no theme-changed signal is needed.

`BusySpinner` color and all `setStyleSheet` colors must be config-driven (`_apply_styling` reads from `colors.*`).

**Theme coverage test**: `tests/config/test_theme_coverage.py` asserts that all curated `chess_log_charts.*` key paths exist in all three theme files — add new color keys there whenever a new config-driven color is introduced. Manual QA via `debug.enable_debug_rand_colors: true` (in `config.json:1087`) can be used to confirm no hardcoded colors survive theme switching.

## Shared utilities

**BusySpinner**: `app/views/widgets/busy_spinner.py` is the single canonical spinner widget used throughout Chess Log (Charts tab, dialogs) and by `BulkOperationsDialog`.

**AI provider config**: `app/utils/ai_provider_config.py` — shared helpers used by both Chess Log Charts and AI Summary: `is_ai_configured`, `resolve_default_provider`, `get_available_models` (plain model-ID list for the active provider), and `get_active_provider_label` (display label "OpenAI" / "Anthropic" / "Custom"). Model-selection logic lives here, not in the controllers.

## AI integration

### Prompt storage in `config.json`

All LLM prompt strings live under a top-level `prompts` section with two siblings:

```
prompts.chess_log.narrative_system        — system prompt passed to AIService
prompts.chess_log.narrative_preamble      — user message template (4 placeholders)
prompts.chess_log.narrative_step          — appended after the preamble
prompts.chess_log.narrative_glossaries    — dict: {"CLAMP": "…", "CCT": "…", "3x3": ""}
prompts.chess_log.narrative_3x3_structure — Why-note structure block
prompts.chess_log.narrative_3x3_moment_framing — per-moment inline framing line
prompts.chess_log.classifier              — CLAMP/CCT classifier prompt (SHALLOW/DEEP per note)
prompts.chess_log.classifier_3x3          — 3x3 classifier prompt (INTENT/LESSON per moment)
prompts.ai_chat.system_preamble           — AI Chat system prompt preamble
prompts.ai_chat.formatting_rules          — AI Chat formatting directives
```

`classifier_3x3` body contains `{why1_q}`/`{why2_q}`/`{why3_q}`/`{why4_q}` placeholders. These are filled at build time in `classify_notes_3x3()` from `THREE_BY_THREE_PROMPTS` in `app/utils/chess_log_prompts.py` — the same wording the 3x3 dialog shows. If the Why-question wording ever changes, the classifier prompt tracks it automatically; no config edit needed.

All 12 keys are registered in `ConfigLoader._REQUIRED_CONFIG_KEY_PATHS` — a missing key causes a `ValueError` at startup with a clear message naming the absent path, not a silent KeyError mid-request.

`_generate_initial_prompt()` in `ai_chat_controller.py` stays in Python: it embeds live FEN, PGN, ply index, and optional analysis JSON via f-strings. There is no equivalent for Chess Log's assembly either — `build_prompt()` and `classify_notes()` read prompts from config but all data interpolation happens in Python.

### Placeholder contract

`narrative_preamble` uses Python `.format()` with four named placeholders:

- `{glossary_section}` — preset glossary + 3x3 structure block, or `\n` if none
- `{category_counts_block}` — 4-bin trend table from `aggregate()`
- `{why_notes_block}` — player's why-notes, one per line; sentinel separates moments
- `{game_notes_block}` — whole-game notes, or "(no whole-game notes)"

`ConfigLoader._validate_prompt_placeholders()` checks all four are present using `string.Formatter().parse()` at startup — a load-time error, not a silent mid-run KeyError.

**Why this differs from the Elo validation pattern**: Elo has `value_on_error` as a graceful fallback when a key is missing. Prompts have no equivalent — a missing `{placeholder}` silently drops that section from the assembled prompt with no error; an extra `{placeholder}` (unknown key) raises `KeyError` inside a `QThread` mid-request, leaving the UI blank with no message. The load-time validator makes either failure loud at startup instead of silent at runtime.

### Missing-config guards

`generate_narrative()` checks `(config or {}).get("prompts", {}).get("chess_log")` before calling `build_prompt()`. If the section is absent it returns `NarrativeResult(success=False, text="Chess Log prompts are missing from config.json — reinstall or restore the file.")` without touching the network. `classify_notes()` does the same, returning a `ShallowResult(success=False, …)`. `AIChatController.send_message()` emits `error_occurred` and returns `False` before appending any message to the conversation. The guards fire before state is mutated — they mirror the existing model-config checks at lines 476–484 of `ai_chat_controller.py`.

Tests: `TestNarrativeMissingConfig`, `TestClassifyNotesMissingConfig`, `TestAIChatMissingConfig` in the relevant test files.

### `THREE_BY_THREE_PROMPTS` and config divergence

The four Why-question strings in `app/utils/chess_log_prompts.py` (`THREE_BY_THREE_PROMPTS`) are the live source for the moment dialog, tags dialog, and PDF export. `prompts.chess_log.narrative_3x3_structure` must contain each verbatim — `test_config_3x3_structure_matches_three_by_three_prompts` enforces this at test time. Editing a Why question without updating `config.json` produces a test failure.

### Editing prompts

Multi-line prompt strings are stored as single JSON string values with `\n` escapes (e.g. `"Line one.\nLine two."`). This is JSON's native format — no array-join trick — but it makes hand-editing in a text editor awkward: the entire prompt appears as one long line. To edit, search for a distinctive phrase, make the change, and keep the `\n` separators intact. A JSON formatter (e.g. `python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))" < config.json`) can pretty-print the file temporarily for easier editing, though the committed form stays compact.

## Manual test checklist

### What Paul can test before the PR

1. **HTML clipboard — Charts narrative copy**: generate a narrative, right-click → "Copy section" (narrative section). Paste into Notion or Mail: the section heading renders as a bold heading, bullet points render as a bulleted list, and the Tactical Breakdown renders as a formatted table with column headers. Paste into TextEdit (plain-text mode): the raw markdown appears — `##` prefix on the heading, `|` pipes in the table — with no HTML tags. For chess.com: use the forum's normal post editor (not its HTML source view) — paste there and the heading/table should render.

2. **HTML clipboard — Charts "Copy log"**: right-click → "Copy log to clipboard". Paste into Notion: a large bold "Chess Log — [player]" heading appears at the top, followed by one line per chart section and any narrative. Paste into a plain-text editor: the text starts with "Chess Log —", no HTML markup visible.

3. **HTML clipboard — Logged Moments**: open Show Logged Moments. Click "Copy to clipboard". Paste into Notion: the game line (White − Black, result, date) appears bold, followed by each moment as a bold move number and category, with any note below it; if a moment was flagged by Check Logs, a colored "Shallow" or "Vague" badge appears inline. Paste into a plain-text editor: no bold formatting markers, no HTML, just the move and note text.

4. **HTML clipboard — Check Logs**: after a Check Logs run, open Show Shallow/Vague Logs. Click "Copy to clipboard". Paste into Notion: a bold "Check Logs" heading appears, followed by the source filename and model name, then each flagged moment with its colored "Shallow" or "Vague" badge. Paste into a plain-text editor: the "Chess Log — Check Logs" line appears first, then source, then the moment lines — no HTML markup.

5. **Copy buttons enabled/disabled state**: open Show Logged Moments on a game with no moments — "Copy to clipboard" button is greyed out and unclickable. Same for Show Shallow/Vague Logs opened with no flagged notes.

6. **Unsaved edits**: in Show Logged Moments, edit a why-note in a row without saving. Click "Copy to clipboard". Paste into Notion — the edited text appears, not the last-saved text. Same behavior as Export to PDF.

7. **Narrative Summary** — run on the logged-game library and compare output quality with the pre-change baseline. The golden fixture tests in `tests/services/test_chess_log_prompts_config_roundtrip.py` prove prompt assembly is byte-identical before and after the config move; the comparison is a spot-check for quality, not a byte diff.

8. **AI Chat** — run a normal analysis session. The golden fixture tests in `tests/services/test_ai_chat_prompts_golden.py` prove system_prompt assembly is byte-identical.

9. **Prompt editing** — open `app/config/config.json`, append a visible marker to `prompts.chess_log.narrative_system` (e.g. `" [TEST]"` at the end). Restart CARA, run Narrative Summary, verify the marker appears in the AI's reply or in the logs. Revert the change. Repeat for `prompts.ai_chat.system_preamble`.

10. **Token labels** — confirm `Tokens: N in / M out` appears below the narrative and near the Check Logs button after each run. Confirm both labels clear when a new run starts and when a run fails. Export the narrative to PDF and confirm no "Tokens:" text appears in the exported file.

11. **Placeholder validator** — edit `narrative_preamble` in `config.json` to remove one of the four required placeholders (e.g. delete `{glossary_section}`). Restart CARA — it should fail at startup with a clear error naming the missing placeholder. Restore the file.

12. **Failure notice** — close the network connection or use a bad API key; confirm the failure message ("Couldn't reach …" or "API key missing …") appears in the UI rather than a blank panel.

### What's left for Philipp at PR review

1. **Local endpoint (CUSTOM provider)** — test both Narrative Summary and Check Logs against LM Studio / llama.cpp / Ollama in OpenAI-compatible mode. Paul does not have a local endpoint set up. Automated CUSTOM-path coverage is in `tests/services/test_ai_service_custom_provider.py` but live-endpoint testing is deferred to PR review.

2. **Garbled classifier reply from a small local model** — deliberately point at a tiny model that returns prose. Confirm the UI shows "Check Logs Error" / "N notes couldn't be classified — left unchanged" and no notes are flagged. Mocked coverage is in `tests/services/test_chess_log_shallow_service.py`; this is the live-endpoint equivalent.

3. **Provider Paul doesn't have a key for** — test any cloud provider Paul doesn't have configured; confirm the error notice appears.

4. **Multi-line prompt editing** — hand-edit a prompt in `config.json`, restart, confirm the edit is picked up. A reformatter (`python3 -m json.tool config.json`) can pretty-print the file to make editing easier.

5. **Placeholder validator message quality** — remove a required placeholder, restart, confirm the error message is clear enough for a non-developer to act on.

## Key files

- `app/services/chess_log_stats_service.py`
- `app/services/chess_log_narrative_service.py`
- `app/services/chess_log_pdf_service.py`
- `app/services/chess_log_html_service.py` — HTML + plain-text clipboard generation for all four copy actions
- `app/controllers/chess_log_charts_controller.py`
- `app/controllers/chess_log_controller.py`
- `app/views/detail_chess_log_charts_view.py`
- `app/views/widgets/chess_log_category_chart_widget.py`
- `app/views/widgets/busy_spinner.py`
- `app/views/menus/chess_log_charts_context_menu.py`
- `app/views/dialogs/_tag_row_helpers.py` — holds `game_header_text`, `node_info`, `ply_for_path`; `_TagRowWidget` itself lives in `show_tags_dialog.py`
- `app/views/dialogs/show_tags_dialog.py`
- `app/views/dialogs/show_shallow_tags_dialog.py`
- `app/utils/ai_provider_config.py`
- `app/utils/chess_log_best_move.py` — `resolve_best_move_for_path` (reads `CARAAnalysisData` for the best move at a tagged position)

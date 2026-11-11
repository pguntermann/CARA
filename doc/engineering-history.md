# Engineering History

Completed migrations, resolved incidents, and "we used to do X" context that no longer needs to be enforced but is useful background for understanding why things are the way they are.

---

## BusySpinner consolidation (2026-09-21)

A private `_BusySpinner` class existed inside `bulk_operations_dialog.py`. It was extracted to `app/views/widgets/busy_spinner.py` as the public `BusySpinner` class and all call sites were updated to import from there. Any pre-migration code you find referencing a private `_BusySpinner` is stale.

---

## `request_flag_shallow_notes` — replaced synchronous predecessor

`ChessLogChartsController.request_flag_shallow_notes()` replaced an earlier synchronous `flag_shallow_notes()` method when shallow classification was moved to a background thread (`ChessLogShallowThread`). The synchronous version no longer exists.

---

## Shared chart helpers — extracted from `detail_player_stats_view.py`

`smooth_polyline_path`, `ordinal_to_chart_x`, `calendar_axis_ticks`, `GapCompressedTimeLayout`, and related helpers were originally private to `detail_player_stats_view.py`. They were extracted to `app/views/widgets/_chart_layout_helpers.py` when Chess Log Charts was added, so both chart tabs could share them without duplication. If you encounter an old import path pointing into `detail_player_stats_view`, update it.

---

## Narrative prompt — shallow-note flagging removed

An earlier version of the narrative prompt included a "step 2" that asked the LLM to flag shallow notes inline. This was removed; shallow-note flagging is now a separate flow (`request_flag_shallow_notes`). `_parse_response` in `chess_log_narrative_service.py` has always returned `(narrative, [])` since this change — the empty list is vestigial from the old two-value contract.

---

## Chess Log charts settings key names — migration

The early `user_settings.chess_log.charts` block used shorter key names that didn't align with the Player Stats naming convention, and `x_axis_mode` used different value strings. `normalize_chess_log_charts_settings()` in `chess_log_charts_user.py` migrates both on first load. Any user_settings.json created before the alignment migration will be silently upgraded on startup.

---

## Configuration loading — `.get()` pattern tech debt

ConfigLoader was designed to strictly validate all keys at startup, but mid-project the convention shifted to using `.get(..., default)` patterns in code rather than registering everything. The strict validation rule was never retroactively applied to existing code. The ConfigLoader refactor remains on the backlog. This is why you'll find `.get()` patterns throughout the existing codebase — it's known tech debt, not an inconsistency to fix in passing. The rule for new code is: register every new key in ConfigLoader.

---

## AI provider config helpers — extracted from `AIChatController`

`is_ai_configured()` and `resolve_default_provider()` in `app/utils/ai_provider_config.py` were extracted from inline logic in `AIChatController.get_default_model` when Chess Log Charts needed the same check. Before extraction, each consumer had its own inline copy.

---

## Git push rule — superseded narrower predecessor

The rule "never run `git push` without first showing Paul the exact commits and getting explicit confirmation" supersedes an earlier, narrower rule that only required confirmation for upstream PRs. The narrower rule proved insufficient after a push to the fork's own `origin` was made without confirmation. The current rule covers all pushes universally.

---

## Compaction-resume incident — origin of the multi-part directive rule

The CLAUDE.md rule about not assuming a multi-part directive is complete after compaction was added after a specific incident: following a session compaction, an investigate-then-report step was silently skipped in favor of jumping directly to the last visible action (a push). The investigation results were never surfaced to Paul.

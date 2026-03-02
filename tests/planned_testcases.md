# Unit Test Cases

## Already implemented

| Test module / suite | Location | Coverage |
|----------------------|----------|----------|
| PGN formatter | `tests/pgn/test_formatter.py` | PGN formatting (headers, comments, variations, annotations, move numbers) |
| PGN filter and remove | `tests/pgn/test_filter_and_remove.py` | Combining show/hide filtering with removal operations |
| PGN filtering comprehensive | `tests/pgn/test_filtering_comprehensive.py` | Systematic combinations of filter flags (metadata, comments, variations, annotations, results) |
| PGN highlighting | `tests/pgn/test_highlighting.py` | PGN display with variations/annotations/results filtered (Qt-dependent; skipped in CI) |
| PGN removal order | `tests/pgn/test_removal_order.py` | Order of removal operations (non-standard tags, comments, variations, annotations) |
| Positional heatmap rules | `tests/positional_heatmap/test_rules_comprehensive.py` | Backward pawn, doubled pawn, isolated pawn, king safety, passed pawn, piece activity, undeveloped piece, weak square |
| Highlight rules (all) | `tests/highlight_rules/test_all_highlight_rules.py` | Discovery runner for all highlight-rule tests |
| Decoy rule | `tests/highlight_rules/decoy/test_decoy_bc4_should_match.py` | Decoy rule match |
| Blunder rule | `tests/highlight_rules/blunder/test_blunder_Re2_should_not_match.py` | Blunder rule no-match |
| Interference rule | `tests/highlight_rules/interference/test_interference_*.py` | Interference rule match / no-match |
| Knight outpost rule | `tests/highlight_rules/knight_outpost/test_knight_outpost_Nxd4_should_not_match.py` | Knight outpost no-match |
| Material imbalance rule | `tests/highlight_rules/material_imbalance/test_material_imbalance_qxc5_should_not_match.py` | Material imbalance no-match |
| Pawn storm rule | `tests/highlight_rules/pawn_storm/test_pawn_storm_a5_should_not_match.py` | Pawn storm no-match |
| Breakthrough sacrifice rule | `tests/highlight_rules/breakthrough_sacrifice/test_breakthrough_sacrifice_Bxg4_should_not_match.py` | Breakthrough sacrifice no-match |
| Tactical sequence rule | `tests/highlight_rules/tactical_sequence/test_tactical_sequence_Bxg4_should_match.py` | Tactical sequence match |
| Time control utils | `tests/utils/test_time_control_utils.py` | TimeControl parsing, base seconds, TC type (Bullet/Blitz/Rapid/Classical) |
| Date matcher | `tests/services/test_date_matcher.py` | PGN date parsing and comparison (parse_date, date_equals, date_before, date_after, date_contains) |
| Material tracker | `tests/utils/test_material_tracker.py` | Material balance, material loss, captured piece letter, material count, count_pieces |

## Planned (not yet implemented)

Components identified as candidates for additional unit tests. Items 1–3 in the table below are implemented (see above); the rest are planned.

| # | Component | Location | Status | Rationale |
|---|-----------|----------|--------|-----------|
| 1 | **Time control parsing / TC type** | `app/utils/time_control_utils.py` | **Implemented** (`tests/utils/test_time_control_utils.py`) | `_parse_base_seconds`, `get_base_seconds`, `get_tc_type`; many edge cases (N, N+inc, M/N, "?", "Blitz", etc.). Pure functions, easy to test. |
| 2 | **Date matcher** | `app/services/date_matcher.py` | **Implemented** (`tests/services/test_date_matcher.py`) | `parse_date`, `date_equals`, `date_before`, `date_after`, `date_contains` for PGN partial dates ("2025.??.??"). All static, no I/O. |
| 3 | **Material tracker** | `app/utils/material_tracker.py` | **Implemented** (`tests/utils/test_material_tracker.py`) | `calculate_material_balance`, `calculate_material_loss`, `get_captured_piece_letter`, `calculate_material_count`, `count_pieces`. Board-in, numbers out; good for regressions. |
| 4 | **Path resolver** | `app/utils/path_resolver.py` | | `resolve_data_file_path`, `get_user_data_directory`, `has_write_access`, `get_app_resource_path`. Can be tested with temp dirs and/or env; critical for portable vs app-root behavior. |
| 5 | **Path display utils** | `app/utils/path_display_utils.py` | | `truncate_text_middle`, `truncate_path_for_display`. String-in, string-out; avoid UI regressions. |
| 6 | **Markdown-to-HTML** | `app/utils/markdown_to_html.py` | | `markdown_to_html`, `_process_inline`, `_heading_id`. Headings, lists, links, bold, code; no deps, many edge cases. |
| 7 | **Config loader validation** | `app/config/config_loader.py` | | `_validate`, `_get_required_keys`, `_has_key`. Validation logic for required keys; test with minimal JSON configs (valid / missing keys). |
| 8 | **PGN service parsing / normalization** | `app/services/pgn_service.py` | | `_normalize_pgn_text`, `_parse_game_chunk`, `_extract_game_data` (or equivalent), game splitting. Core for import; test with malformed PGN and blank-line edge cases. |
| 9 | **Game summary service (stats)** | `app/services/game_summary_service.py` | | Accuracy/CPL/phase stats from move lists, phase boundaries, `PlayerStatistics` / `PhaseStatistics` construction. Pure logic on lists/dicts; no engine. |
| 10 | **UCI communication (parsing only)** | `app/services/uci_communication_service.py` | | Parsing of engine output (e.g. `info`, `bestmove`, `id`, `uciok`). Test with fixed strings; no subprocess. |
| 11 | **PgnCleaningService** | `app/services/pgn_cleaning_service.py` | | `remove_variations_from_game`, `remove_annotations_from_game`, `remove_results_from_game` (or similar). Same domain as existing PGN tests; easy to add. |
| 12 | **Database search (query building)** | `app/services/database_search_service.py` | | Building of search/filter criteria from UI state (date range, player, result, etc.) if done in service. Test criteria dict/object shape. |
| 13 | **Bulk replace (pattern / replacement)** | `app/services/bulk_replace_service.py` | | Pattern matching and replacement logic for tag/value (e.g. regex, literal). Isolate from DB; test with sample game dicts or PGN snippets. |
| 14 | **Deduplication service** | `app/services/deduplication_service.py` | | Duplicate detection (e.g. by position, moves, headers). Test with small game sets; no DB. |
| 15 | **Table CSV/TSV export** | `app/utils/table_export.py` | | `table_to_delimited`, `_quote_field` (delimiter, quoting). String/table-in, string-out. |
| 16 | **Rule explanation / summary formatters** | `app/utils/rule_explanation_formatter.py`, `app/utils/summary_text_formatter.py` | | Formatting of rule explanations or summary text from structured data. Test with fixed inputs and expected strings. |
| 17 | **Opening service (ECO/name lookup)** | `app/services/opening_service.py` | | Mapping position or move list to opening code/name if done in-process. Test with known positions or move sequences. |
| 18 | **Error pattern service** | `app/services/error_pattern_service.py` | | Matching or classifying error messages/patterns. Test with sample messages and expected categories. |
| 19 | **Additional game highlight rules** | `app/services/game_highlights/rules/*.py` | | Only a few rules have tests (decoy, blunder, interference, etc.). Add tests for e.g. fork, pin, skewer, tactical_sequence, breakthrough_sacrifice, material_imbalance, pawn_storm, knight_outpost (match vs no-match cases). |
| 20 | **Config loader key helpers** | `app/config/config_loader.py` | | `_has_key` (dotted path), `_get_required_keys` consistency with schema. Test with minimal dicts and known required keys. |

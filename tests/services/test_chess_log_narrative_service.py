"""Tests for chess_log_narrative_service.

Monkeypatches AIService.send_message to capture the prompt that was assembled
and to return controlled responses without making live API calls.

Assertions focus on prompt *content* — that the required pieces are present —
and on response *parsing* — that _parse_response always returns empty flags.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import json as _json
from app.models.database_model import GameData
from app.services.ai_service import AIResult
from app.services.chess_log_storage_service import ChessLogStorageService
from app.services.chess_log_narrative_service import (
    _bin_month_label,
    _format_trend_counts,
    build_prompt,
    generate_narrative,
    sanitize_narrative_markdown,
    _parse_response,
)
from app.utils.path_resolver import get_app_resource_path as _get_resource_path

# Load real config; pass to build_prompt()/generate_narrative() so assembled
# prompts contain full template text for content-based assertions.
with open(_get_resource_path("app/config/config.json"), "r", encoding="utf-8") as _f:
    _CONFIG = _json.load(_f)

# Module-level aliases from config — preserves existing test assertions that
# reference these names directly without changing every assertion site.
_cl = _CONFIG["prompts"]["chess_log"]
_SYSTEM_PROMPT = _cl["narrative_system"]
_NARRATIVE_STEP = _cl["narrative_step"]
_PRESET_GLOSSARIES = _cl["narrative_glossaries"]
_3X3_STRUCTURE_BLOCK = _cl["narrative_3x3_structure"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(
    white: str = "Alice",
    black: str = "Bob",
    date: str = "2025.06.01",
    entries_per_path: dict | None = None,
    notes: str = "",
) -> GameData:
    pgn = (
        f'[Event "Test"]\n'
        f'[Site "?"]\n'
        f'[Date "{date}"]\n'
        f'[Round "?"]\n'
        f'[White "{white}"]\n'
        f'[Black "{black}"]\n'
        f'[Result "*"]\n'
        f'\n1. e4 e5 2. Nf3 Nc6 *\n'
    )
    game = GameData(game_number=1, pgn=pgn, white=white, black=black, date=date)
    if entries_per_path:
        ChessLogStorageService.store_tags(game, entries_per_path)
    if notes:
        from app.services.notes_storage_service import NotesStorageService
        NotesStorageService.store_notes(game, notes)
    return game


def _clamp(cat: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("CLAMP", cat, why)


def _cct(cat: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("CCT", cat, why)


def _threex(key: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("3x3", key, why)


# ---------------------------------------------------------------------------
# build_prompt — category counts
# ---------------------------------------------------------------------------

class TestBuildPromptCategoryCounts(unittest.TestCase):

    def test_category_count_in_prompt(self):
        game = _make_game(entries_per_path={
            "0": [_clamp("C"), _clamp("L"), _clamp("C")],
        })
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", prompt)
        # New format: percentages, not raw "C:N" counts
        self.assertIn("%", prompt)
        # C appears twice, L once → C 67%, L 33%
        self.assertIn("C 67%", prompt)
        self.assertIn("L 33%", prompt)

    def test_uncategorized_labelled_in_prompt(self):
        game = _make_game(entries_per_path={"0": [_clamp("")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("uncategorized", prompt.lower())

    def test_multiple_presets_both_in_prompt(self):
        game = _make_game(entries_per_path={
            "0": [_clamp("M")],
            "0.0": [_cct("Checks")],
        })
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", prompt)
        self.assertIn("CCT", prompt)

    def test_no_moments_produces_no_moments_placeholder(self):
        game = _make_game()  # no tags
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("no moments tagged", prompt)


# ---------------------------------------------------------------------------
# build_prompt — why-notes
# ---------------------------------------------------------------------------

class TestBuildPromptWhyNotes(unittest.TestCase):

    def test_why_note_present_in_prompt(self):
        game = _make_game(entries_per_path={
            "0": [_clamp("C", "I rushed without checking the whole board")],
        })
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("rushed without checking", prompt)

    def test_empty_why_not_in_prompt(self):
        game = _make_game(entries_per_path={"0": [_clamp("C", "")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertNotIn("C/uncategorized", prompt)
        # No why-notes section body (only the placeholder)
        self.assertIn("no notes written", prompt)

    def test_why_note_label_includes_preset_and_cat(self):
        game = _make_game(entries_per_path={
            "0": [_clamp("L", "I miscounted the tempo")],
        })
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP/L", prompt)


# ---------------------------------------------------------------------------
# build_prompt — whole-game notes
# ---------------------------------------------------------------------------

class TestBuildPromptGameNotes(unittest.TestCase):

    def test_game_note_present_in_prompt(self):
        game = _make_game(notes="Played aggressively but missed the counterplay.")
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("aggressively", prompt)

    def test_no_game_notes_shows_placeholder(self):
        game = _make_game()
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("no whole-game notes", prompt)


# ---------------------------------------------------------------------------
# build_prompt — player filter
# ---------------------------------------------------------------------------

class TestBuildPromptPlayerFilter(unittest.TestCase):

    def test_player_filter_excludes_unrelated_games(self):
        g1 = _make_game(white="Alice", black="Bob",
                        entries_per_path={"0": [_clamp("C", "note from alice")]})
        g2 = _make_game(white="Carlos", black="Dave",
                        entries_per_path={"0": [_clamp("L", "note from carlos")]})
        prompt = build_prompt([g1, g2], player="Alice", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("note from alice", prompt)
        self.assertNotIn("note from carlos", prompt)

    def test_empty_player_includes_all(self):
        g1 = _make_game(white="Alice", black="Bob",
                        entries_per_path={"0": [_clamp("C", "alice note")]})
        g2 = _make_game(white="Carlos", black="Dave",
                        entries_per_path={"0": [_clamp("L", "carlos note")]})
        prompt = build_prompt([g1, g2], player="", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("alice note", prompt)
        self.assertIn("carlos note", prompt)


# ---------------------------------------------------------------------------
# build_prompt — glossary
# ---------------------------------------------------------------------------

class TestBuildPromptGlossary(unittest.TestCase):

    def test_clamp_glossary_emitted_when_clamp_data_present(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("Checks", prompt)
        self.assertIn("Loose Pieces and Squares", prompt)
        self.assertIn("Alignments", prompt)
        self.assertIn("Mobility Restrictions", prompt)
        self.assertIn("Passed Pawns", prompt)

    def test_clamp_glossary_uses_verbatim_source_text(self):
        # Guards against future paraphrase drift by pinning distinctive phrases
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("knight's reach", prompt)
        self.assertIn("handing them one", prompt)
        self.assertIn("boxed in by their candidate move", prompt)

    def test_no_glossary_when_no_data(self):
        game = _make_game()  # no tags → no preset in data
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertNotIn("## Glossary", prompt)

    def test_glossary_only_for_presets_in_data(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("## Glossary — CLAMP", prompt)
        self.assertNotIn("## Glossary — CCT", prompt)
        self.assertNotIn("## Glossary — 3x3", prompt)

    def test_glossary_registry_extensible(self):
        self.assertIsInstance(_PRESET_GLOSSARIES, dict)
        self.assertIn("CLAMP", _PRESET_GLOSSARIES)
        self.assertTrue(len(_PRESET_GLOSSARIES["CLAMP"]) > 0)
        self.assertIn("CCT", _PRESET_GLOSSARIES)
        self.assertIn("3x3", _PRESET_GLOSSARIES)
        self.assertNotIn("Custom", _PRESET_GLOSSARIES)


# ---------------------------------------------------------------------------
# build_prompt — trend counts
# ---------------------------------------------------------------------------

class TestBuildPromptTrendCounts(unittest.TestCase):

    def test_category_counts_by_preset_are_trend_binned(self):
        # 8 games across 8 different months → multiple time bins
        dates_and_cats = [
            ("2025.02.01", "C"), ("2025.03.01", "L"),
            ("2025.04.01", "A"), ("2025.05.01", "M"),
            ("2025.06.01", "P"), ("2025.07.01", "C"),
            ("2025.08.01", "L"), ("2025.09.01", "A"),
        ]
        games = [
            _make_game(date=d, entries_per_path={"0": [_clamp(cat)]})
            for d, cat in dates_and_cats
        ]
        prompt = build_prompt(games, config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        # Multiple "N moments)" occurrences confirm trend structure, not flat totals
        self.assertGreaterEqual(prompt.count("moments)"), 2)
        # "Bin 1", "Bin 2", etc. must not appear — periods use calendar labels.
        # (The instruction text contains the literal string "Bin N" as an example,
        # which is fine — it's a numbered form like "Bin 1" that must be absent.)
        self.assertNotIn("Bin 1", prompt)
        self.assertNotIn("Bin 2", prompt)
        self.assertNotIn("Bin 3", prompt)
        self.assertNotIn("Bin 4", prompt)

    def test_trend_falls_back_gracefully_when_aggregator_empty(self):
        # PGN "????.??.??" → _game_date_ordinal_for_trends returns None
        # → aggregate skips the game → series_map empty → fallback to flat counts
        game = _make_game(date="????.??.??", entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)  # must not raise
        self.assertIn("trend data unavailable", prompt)
        self.assertIn("CLAMP", prompt)


# ---------------------------------------------------------------------------
# build_prompt — note normalization
# ---------------------------------------------------------------------------

class TestBuildPromptNoteNormalization(unittest.TestCase):

    def test_note_normalization_instruction_present(self):
        game = _make_game(notes="Played aggressively but missed the counterplay.")
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("illustrative color only", prompt)

    def test_note_normalization_precedes_whole_game_notes_section(self):
        game = _make_game(notes="Some game note.")
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        norm_idx = prompt.lower().find("illustrative color only")
        notes_idx = prompt.find("## Whole-game notes")
        self.assertGreater(notes_idx, norm_idx,
                           "note-normalization instruction must come before ## Whole-game notes")


# ---------------------------------------------------------------------------
# build_prompt — system prompt instructions
# ---------------------------------------------------------------------------

class TestSystemPromptInstructions(unittest.TestCase):
    """Tests that key _SYSTEM_PROMPT instructions are present (verbatim phrase checks)."""

    def _get_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def test_calendar_label_instruction_present(self):
        sp = self._get_system_prompt()
        self.assertIn("Never use generic placeholder language like 'periods' or 'bins'", sp)

    def test_key_takeaways_section_instruction_present(self):
        sp = self._get_system_prompt()
        self.assertIn("## Patterns & Recurrent Themes", sp)
        self.assertIn("## Tactical Breakdown", sp)
        self.assertIn("## Key Takeaways", sp)
        self.assertIn("must never be dropped", sp)

    def test_system_prompt_declares_three_sections_in_order(self):
        sp = self._get_system_prompt()
        themes_pos = sp.find("## Patterns & Recurrent Themes")
        breakdown_pos = sp.find("## Tactical Breakdown")
        takeaways_pos = sp.find("## Key Takeaways")
        self.assertGreater(themes_pos, -1, "## Patterns & Recurrent Themes not found")
        self.assertGreater(breakdown_pos, -1, "## Tactical Breakdown not found")
        self.assertGreater(takeaways_pos, -1, "## Key Takeaways not found")
        self.assertLess(themes_pos, breakdown_pos, "Themes must precede Breakdown")
        self.assertLess(breakdown_pos, takeaways_pos, "Breakdown must precede Takeaways")

    def test_system_prompt_has_citation_format_rule(self):
        sp = self._get_system_prompt()
        self.assertIn("full move+color pairing", sp)
        self.assertIn("NotThePainter vs mattsartin", sp)

    def test_system_prompt_has_quote_density_cap(self):
        sp = self._get_system_prompt()
        self.assertIn("1 to 2", sp)
        self.assertIn("per theme", sp)

    def test_period_listing_instruction_present(self):
        sp = self._get_system_prompt()
        self.assertIn("do not mechanically list every period's name", sp)
        self.assertNotIn("lifetime", sp.lower())

    def test_calendar_label_prompt_contains_no_bin_n(self):
        # A multi-bin scenario: the assembled prompt's category-count section
        # must contain real month text, not the literal "Bin 1" etc.
        dates_and_cats = [
            ("2025.06.01", "C"), ("2025.07.01", "L"),
            ("2025.08.01", "A"), ("2025.09.01", "M"),
        ]
        games = [
            _make_game(date=d, entries_per_path={"0": [_clamp(cat)]})
            for d, cat in dates_and_cats
        ]
        prompt = build_prompt(games, config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertNotIn("Bin 1", prompt)
        self.assertNotIn("Bin 2", prompt)
        # Real month names are present
        self.assertRegex(prompt, r"(January|February|March|April|May|June|"
                                  r"July|August|September|October|November|December)")


# ---------------------------------------------------------------------------
# build_prompt — narrative instruction
# ---------------------------------------------------------------------------

class TestBuildPromptNarrativeInstruction(unittest.TestCase):

    def test_narrative_step_asks_for_three_sections_in_order(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("## Patterns & Recurrent Themes", prompt)
        self.assertIn("## Tactical Breakdown", prompt)
        self.assertIn("## Key Takeaways", prompt)
        # Headers appear in the correct order
        themes_pos = prompt.find("## Patterns & Recurrent Themes")
        breakdown_pos = prompt.find("## Tactical Breakdown")
        takeaways_pos = prompt.find("## Key Takeaways")
        self.assertLess(themes_pos, breakdown_pos)
        self.assertLess(breakdown_pos, takeaways_pos)
        # Patterns uses bullet format; Key Takeaways uses prose
        self.assertIn("2 to 4 bullets", prompt)
        self.assertIn("1 to 3 short paragraphs", prompt)
        self.assertIn("not a numbered or bulleted list", prompt)
        # Table format cue present
        self.assertIn("| Skill | Observed Issue | Strategic Impact |", prompt)
        # Old two-section header must be gone
        self.assertNotIn("## Narrative Summary", prompt)
        self.assertNotIn("5 to 8 paragraphs", prompt)
        self.assertNotIn("3–5 paragraphs", prompt)
        self.assertNotIn("3 to 5 items", prompt)


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse(unittest.TestCase):

    def test_no_sentinel_returns_full_response_and_empty_flags(self):
        narrative, flags = _parse_response("Great reflection on your games.")
        self.assertEqual(narrative, "Great reflection on your games.")
        self.assertEqual(flags, [])

    def test_parse_response_always_returns_empty_flags(self):
        # Even when the LLM still outputs an "Also flagged" section, flags == []
        response_with_sentinel = (
            "You show progress.\n\n"
            "## Also flagged\n"
            "- 'I blundered' under Blunder: restates the category\n"
        )
        for response in ("Plain narrative.", response_with_sentinel):
            with self.subTest(response=response[:30]):
                _, flags = _parse_response(response)
                self.assertEqual(flags, [])


# ---------------------------------------------------------------------------
# generate_narrative (integration through monkeypatch)
# ---------------------------------------------------------------------------

class TestGenerateNarrative(unittest.TestCase):

    def _game_with_clamp(self) -> GameData:
        return _make_game(entries_per_path={
            "0": [_clamp("C", "I blundered a piece because I stopped calculating")],
            "0.0": [_clamp("L", "I rushed a pawn push")],
        })

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_success_returns_narrative_and_empty_flags(self, MockAIService):
        response_text = (
            "You have been logging Calculation mistakes frequently.\n\n"
            "## Also flagged\n"
            "- 'I blundered a piece': partially restates the category\n"
        )
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=True, text=response_text, error=None, usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        result = generate_narrative(
            games=[self._game_with_clamp()],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        self.assertTrue(result.success)
        self.assertIn("Calculation", result.text)
        # Shallow-note flagging removed: flags always empty
        self.assertEqual(result.shallow_flags, [])

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_api_failure_returns_false(self, MockAIService):
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=False, text="", error="Connection error", usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        result = generate_narrative(
            games=[self._game_with_clamp()],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        self.assertFalse(result.success)
        self.assertIn("Connection error", result.text)
        self.assertEqual(result.shallow_flags, [])

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_prompt_sent_contains_why_note(self, MockAIService):
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=True, text="Solid work.", error=None, usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        generate_narrative(
            games=[self._game_with_clamp()],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        call_args = mock_service.send_message.call_args
        messages = call_args[1].get("messages") or call_args[0][3]
        user_message = next(m["content"] for m in messages if m["role"] == "user")
        self.assertIn("stopped calculating", user_message)

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_system_prompt_included(self, MockAIService):
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=True, text="Good.", error=None, usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        generate_narrative(
            games=[self._game_with_clamp()],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        call_args = mock_service.send_message.call_args
        system_prompt = call_args[1].get("system_prompt")
        self.assertIsNotNone(system_prompt)
        self.assertTrue(len(system_prompt) > 0)

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_custom_provider_passes_base_url(self, MockAIService):
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=True, text="OK.", error=None, usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        generate_narrative(
            games=[self._game_with_clamp()],
            provider="custom",
            model="llama3",
            api_key="",
            base_url_override="http://localhost:11434",
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        call_args = mock_service.send_message.call_args
        base_url = call_args[1].get("base_url_override")
        self.assertEqual(base_url, "http://localhost:11434")

    def test_no_games_returns_false(self):
        result = generate_narrative(
            games=[],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )
        self.assertFalse(result.success)
        self.assertIn("No Chess Log data", result.text)
        self.assertEqual(result.shallow_flags, [])

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_timeout_passed_to_send_message(self, MockAIService):
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=True, text="Good work.", error=None, usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        generate_narrative(
            games=[self._game_with_clamp()],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            timeout_seconds=120,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        call_kwargs = mock_service.send_message.call_args[1]
        self.assertEqual(call_kwargs.get("timeout_seconds"), 120)

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_token_limit_passed_to_send_message(self, MockAIService):
        mock_service = MagicMock()
        mock_service.send_message.return_value = AIResult(success=True, text="Good work.", error=None, usage=None, model="gpt-4o")
        MockAIService.return_value = mock_service

        generate_narrative(
            games=[self._game_with_clamp()],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            token_limit=4000,
            config=_CONFIG,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )

        call_kwargs = mock_service.send_message.call_args[1]
        self.assertEqual(call_kwargs.get("token_limit"), 4000)


# ---------------------------------------------------------------------------
# _bin_month_label — natural calendar labels
# ---------------------------------------------------------------------------

class TestBinMonthLabel(unittest.TestCase):

    def test_same_month_same_year(self):
        self.assertEqual(_bin_month_label("2025-06-01", "2025-06-30"), "June 2025")

    def test_adjacent_months_same_year(self):
        self.assertEqual(_bin_month_label("2025-06-01", "2025-07-15"), "June-July 2025")

    def test_non_adjacent_months_same_year(self):
        self.assertEqual(_bin_month_label("2025-03-01", "2025-08-31"), "March-August 2025")

    def test_cross_year_uses_short_names(self):
        label = _bin_month_label("2025-12-01", "2026-01-31")
        self.assertIn("Dec", label)
        self.assertIn("Jan", label)
        self.assertIn("2025", label)
        self.assertIn("2026", label)

    def test_invalid_date_falls_back_to_raw(self):
        result = _bin_month_label("????.??.??", "2025-06-30")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_both_invalid_falls_back(self):
        result = _bin_month_label("????.??.??", "????.??.??")
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# _format_trend_counts — percentages, overall average, no "Bin N"
# ---------------------------------------------------------------------------

class TestFormatTrendCounts(unittest.TestCase):

    def _make_series_map(self, bins_data: list) -> dict:
        """bins_data: list of (lab0, lab1, counts_dict) tuples."""
        from app.services.chess_log_stats_service import ChessLogCategoryBin, ChessLogPresetSeries
        bins = [
            ChessLogCategoryBin(
                time_pct=float(i * 25),
                total=sum(counts.values()),
                lab0=lab0,
                lab1=lab1,
                counts=dict(counts),
            )
            for i, (lab0, lab1, counts) in enumerate(bins_data)
        ]
        all_cats = sorted({cat for _, _, cts in bins_data for cat in cts})
        series = ChessLogPresetSeries(preset="CLAMP", categories=all_cats, bins=bins)
        return {"CLAMP": series}

    def test_percentages_not_raw_counts(self):
        # 3 C, 1 L in a single bin → C 75%, L 25%
        sm = self._make_series_map([("2025-06-01", "2025-06-30", {"C": 3, "L": 1})])
        text = _format_trend_counts(sm)
        self.assertIn("75%", text)
        self.assertIn("25%", text)
        self.assertNotIn("C:3", text)
        self.assertNotIn("L:1", text)

    def test_overall_average_present(self):
        sm = self._make_series_map([
            ("2025-06-01", "2025-06-30", {"C": 3, "L": 1}),
            ("2025-07-01", "2025-07-31", {"C": 1, "L": 3}),
        ])
        text = _format_trend_counts(sm)
        self.assertIn("Overall average:", text)
        self.assertNotIn("Lifetime average:", text)

    def test_overall_average_is_total_weighted(self):
        # Bin 1: C=9, L=1 (total 10). Bin 2: C=1, L=999 (total 1000).
        # Total-weighted: C = 10/1010 ≈ 1%, L = 1000/1010 ≈ 99%.
        # Average-of-pcts: C = (90% + 0.1%)/2 ≈ 45% — clearly wrong.
        sm = self._make_series_map([
            ("2025-06-01", "2025-06-30", {"C": 9, "L": 1}),
            ("2025-07-01", "2025-07-31", {"C": 1, "L": 999}),
        ])
        text = _format_trend_counts(sm)
        # Overall average line must show C 1% and L 99% (total-weighted)
        avg_line = next(l for l in text.splitlines() if "Overall average" in l)
        self.assertIn("C 1%", avg_line)
        self.assertIn("L 99%", avg_line)

    def test_no_bin_n_in_output(self):
        sm = self._make_series_map([
            ("2025-06-01", "2025-06-30", {"C": 2}),
            ("2025-07-01", "2025-07-31", {"C": 3}),
        ])
        text = _format_trend_counts(sm)
        self.assertNotIn("Bin 1", text)
        self.assertNotIn("Bin 2", text)
        self.assertNotIn("Bin ", text)

    def test_bin_line_uses_month_label(self):
        sm = self._make_series_map([
            ("2025-06-01", "2025-06-30", {"C": 2}),
            ("2025-07-01", "2025-07-31", {"C": 3}),
        ])
        text = _format_trend_counts(sm)
        self.assertIn("June 2025", text)
        self.assertIn("July 2025", text)

    def test_calendar_label_instruction_in_prompt(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn('"Bin N"', prompt)
        self.assertIn("never", prompt.lower())

    def test_zero_count_categories_omitted(self):
        # Only C appears — A, L, M, P should not appear in output
        sm = self._make_series_map([("2025-06-01", "2025-06-30", {"C": 4})])
        text = _format_trend_counts(sm)
        self.assertNotIn("L ", text)
        self.assertNotIn("A ", text)


# ---------------------------------------------------------------------------
# No input cap — all notes reach the prompt
# ---------------------------------------------------------------------------

class TestBuildPromptNoCap(unittest.TestCase):

    def test_all_why_notes_present_beyond_old_cap(self):
        # 50 distinct why-notes exceeds the old _MAX_WHY_NOTES = 40 cap.
        # All must appear in the assembled prompt.
        entries = [_clamp("C", f"unique why note index {i}") for i in range(50)]
        game = _make_game(entries_per_path={"0": entries})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        for i in range(50):
            self.assertIn(f"unique why note index {i}", prompt,
                          msg=f"Note {i} missing — input cap may still be active")

    def test_all_game_notes_present_beyond_old_cap(self):
        # 12 games each with a distinct game note exceeds old _MAX_GAME_NOTES = 10.
        # All game notes must appear in the assembled prompt.
        games = [
            _make_game(
                date=f"2025.0{(i % 9) + 1}.{(i // 9) * 10 + 1:02d}",
                notes=f"game level note index {i}",
                entries_per_path={"0": [_clamp("C")]},
            )
            for i in range(12)
        ]
        prompt = build_prompt(games, config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        for i in range(12):
            self.assertIn(f"game level note index {i}", prompt,
                          msg=f"Game note {i} missing — input cap may still be active")


# ---------------------------------------------------------------------------
# Truncation notice — max_tokens with partial text (ai_service layer)
# ---------------------------------------------------------------------------

class TestAnthropicTruncationNotice(unittest.TestCase):
    """_send_anthropic_message appends a visible notice when stop_reason='max_tokens'
    and the response contains partial text content."""

    def _make_anthropic_response(self, text: str, stop_reason: str) -> "MagicMock":
        import json
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"x"
        mock_response.json.return_value = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason,
            "usage": {"input_tokens": 100, "output_tokens": 2000},
        }
        return mock_response

    @patch("app.services.ai_service.requests.post")
    def test_truncation_notice_appended_when_max_tokens_with_text(self, mock_post):
        from app.services.ai_service import AIService
        mock_post.return_value = self._make_anthropic_response(
            text="You show progress in checks but", stop_reason="max_tokens"
        )
        service = AIService()
        result = service._send_anthropic_message(
            model="claude-sonnet-4-6",
            api_key="sk-test",
            messages=[{"role": "user", "content": "Analyse my games."}],
        )
        self.assertTrue(result.success)
        self.assertIn("You show progress in checks but", result.text)
        self.assertIn("cut off", result.text.lower())
        self.assertIn("token limit", result.text.lower())

    @patch("app.services.ai_service.requests.post")
    def test_no_truncation_notice_on_end_turn(self, mock_post):
        from app.services.ai_service import AIService
        mock_post.return_value = self._make_anthropic_response(
            text="Great work overall.", stop_reason="end_turn"
        )
        service = AIService()
        result = service._send_anthropic_message(
            model="claude-sonnet-4-6",
            api_key="sk-test",
            messages=[{"role": "user", "content": "Analyse my games."}],
        )
        self.assertTrue(result.success)
        self.assertEqual(result.text, "Great work overall.")

    @patch("app.services.ai_service.requests.post")
    def test_error_returned_when_max_tokens_no_text(self, mock_post):
        from app.services.ai_service import AIService
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"x"
        mock_response.json.return_value = {
            "content": [{"type": "thinking", "thinking": "reasoning..."}],
            "stop_reason": "max_tokens",
        }
        mock_post.return_value = mock_response
        service = AIService()
        result = service._send_anthropic_message(
            model="claude-sonnet-4-6",
            api_key="sk-test",
            messages=[{"role": "user", "content": "Analyse my games."}],
        )
        self.assertFalse(result.success)
        self.assertIn("token limit", (result.error or "").lower())


# ---------------------------------------------------------------------------
# generate_narrative — thinking parameter gating
# ---------------------------------------------------------------------------

class TestGenerateNarrativeThinkingGating(unittest.TestCase):
    """generate_narrative must pass thinking={"type":"disabled"} for next-gen
    models (Sonnet 5, Opus 5) and thinking=None for all others."""

    def _run(self, model: str, game):
        captured = {}

        def fake_send(self_svc, provider, model, api_key, messages,
                      system_prompt=None, token_limit=None,
                      base_url_override=None, timeout_seconds=60,
                      thinking=None):
            from app.services.ai_service import AIResult
            captured["thinking"] = thinking
            return AIResult(
                success=True,
                text="## Narrative Summary\nOK\n\n## Key Takeaways\n- OK",
                error=None, usage=None, model=model,
            )

        with patch("app.services.chess_log_narrative_service.AIService.send_message", fake_send):
            generate_narrative(
                [game],
                provider="anthropic",
                model=model,
                api_key="sk-test",
                base_url_override=None,
                config=_CONFIG,
                get_tags_for_game=ChessLogStorageService.load_resolved_paths,
            )
        return captured.get("thinking")

    def test_sonnet5_disables_thinking(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        self.assertEqual(self._run("claude-sonnet-5", game), {"type": "disabled"})

    def test_opus5_disables_thinking(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        self.assertEqual(self._run("claude-opus-5", game), {"type": "disabled"})

    def test_sonnet46_does_not_disable_thinking(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        self.assertIsNone(self._run("claude-sonnet-4-6", game))

    def test_opus47_does_not_disable_thinking(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        self.assertIsNone(self._run("claude-opus-4-7", game))

    def test_dated_sonnet5_variant_disables_thinking(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        self.assertEqual(self._run("claude-sonnet-5-20260901", game), {"type": "disabled"})


# ---------------------------------------------------------------------------
# CCT glossary — content and conditional emission
# ---------------------------------------------------------------------------

class TestCCTGlossary(unittest.TestCase):

    def test_cct_glossary_appears_when_cct_data_present(self):
        game = _make_game(entries_per_path={"0": [_cct("Checks")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("## Glossary — CCT", prompt)

    def test_cct_glossary_threats_definition_verbatim(self):
        game = _make_game(entries_per_path={"0": [_cct("Threats")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("forces the opponent to respond defensively on their very next turn", prompt)

    def test_cct_glossary_checks_wording(self):
        game = _make_game(entries_per_path={"0": [_cct("Checks")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("C — Checks: A checking move", prompt)

    def test_cct_glossary_captures_wording(self):
        game = _make_game(entries_per_path={"0": [_cct("Captures")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("C — Captures: A piece or square left undefended", prompt)

    def test_cct_glossary_absent_when_no_cct_data(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertNotIn("## Glossary — CCT", prompt)


# ---------------------------------------------------------------------------
# 3x3 structural block — content and conditional emission
# ---------------------------------------------------------------------------

class Test3x3StructureBlock(unittest.TestCase):

    def test_3x3_block_appears_when_3x3_data_present(self):
        game = _make_game(entries_per_path={"0": [_threex("Why1", "I saw a threat")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("## Why-note structure — 3x3", prompt)

    def test_3x3_block_contains_exact_studer_questions(self):
        game = _make_game(entries_per_path={"0": [_threex("Why1", "text")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("1. Why did I choose that move?", prompt)
        self.assertIn("2. Why is my move not ideal?", prompt)
        self.assertIn("3. Why is the better move better than my chosen move?", prompt)
        self.assertIn("4. What do I do in the future so this doesn't happen again?", prompt)

    def test_3x3_block_questions_in_order(self):
        game = _make_game(entries_per_path={"0": [_threex("Why2", "text")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        idx1 = prompt.find("1. Why did I choose that move?")
        idx2 = prompt.find("2. Why is my move not ideal?")
        idx3 = prompt.find("3. Why is the better move better than my chosen move?")
        idx4 = prompt.find("4. What do I do in the future so this doesn't happen again?")
        self.assertLess(idx1, idx2)
        self.assertLess(idx2, idx3)
        self.assertLess(idx3, idx4)

    def test_3x3_block_studer_attribution_present(self):
        game = _make_game(entries_per_path={"0": [_threex("Why3", "text")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("GM Noel Studer", prompt)

    def test_3x3_block_absent_when_no_3x3_data(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertNotIn("## Why-note structure — 3x3", prompt)

    def test_3x3_structure_block_constant_matches_questions(self):
        self.assertIn("1. Why did I choose that move?", _3X3_STRUCTURE_BLOCK)
        self.assertIn("2. Why is my move not ideal?", _3X3_STRUCTURE_BLOCK)
        self.assertIn("3. Why is the better move better than my chosen move?", _3X3_STRUCTURE_BLOCK)
        self.assertIn("4. What do I do in the future so this doesn't happen again?", _3X3_STRUCTURE_BLOCK)

    def test_3x3_block_has_no_source_inconsistency_hedging(self):
        self.assertNotIn("three questions", _3X3_STRUCTURE_BLOCK)

    def test_config_3x3_structure_matches_three_by_three_prompts(self):
        from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
        structure_block = _CONFIG["prompts"]["chess_log"]["narrative_3x3_structure"]
        for key, value in THREE_BY_THREE_PROMPTS.items():
            self.assertIn(
                value,
                structure_block,
                f"THREE_BY_THREE_PROMPTS[{key!r}] not found verbatim in "
                "prompts.chess_log.narrative_3x3_structure — edit both together",
            )


# ---------------------------------------------------------------------------
# 3x3 end-to-end prompt-building
# ---------------------------------------------------------------------------

class Test3x3NarrativePromptBuilding(unittest.TestCase):

    def test_3x3_only_game_produces_full_three_section_prompt(self):
        game = _make_game(entries_per_path={
            "0": [
                _threex("Why1", "I saw a discovered attack"),
                _threex("Why2", "It dropped my rook"),
                _threex("Why3", "Nf4 covers both squares"),
                _threex("Why4", "I will slow down and check for pins"),
            ],
        })
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        # Structure block present
        self.assertIn("## Why-note structure — 3x3", prompt)
        # All four answers flow through _format_why_notes
        self.assertIn("I saw a discovered attack", prompt)
        self.assertIn("It dropped my rook", prompt)
        self.assertIn("Nf4 covers both squares", prompt)
        self.assertIn("I will slow down and check for pins", prompt)
        # Three-section narrative instruction present
        self.assertIn("## Patterns & Recurrent Themes", prompt)
        self.assertIn("## Tactical Breakdown", prompt)
        self.assertIn("## Key Takeaways", prompt)

    def test_3x3_game_notes_included_in_prompt(self):
        game = _make_game(
            entries_per_path={"0": [_threex("Why1", "I rushed the attack")]},
            notes="Overall I played too fast in the middlegame.",
        )
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("Overall I played too fast in the middlegame.", prompt)


# ---------------------------------------------------------------------------
# _SYSTEM_PROMPT — CCT disambiguation and bidirectional-framing rules
# ---------------------------------------------------------------------------

class TestSystemPromptCCTRules(unittest.TestCase):

    def _get_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def test_letter_disambiguation_rule_present(self):
        sp = self._get_system_prompt()
        self.assertIn("never use a bare letter as shorthand", sp)
        self.assertIn("Checks, Captures, Threats", sp)

    def test_bidirectional_framing_rule_present(self):
        sp = self._get_system_prompt()
        self.assertIn("a tag can describe either side of the board", sp)
        self.assertIn("do not assume a tag always means", sp)

    def test_skill_column_forbids_clamp_labels(self):
        sp = self._get_system_prompt()
        self.assertIn("Do NOT use CLAMP letters", sp)
        self.assertNotIn("Use the exact CLAMP/CCT/3x3 category or question labels", sp)

    def test_skill_column_requires_generic_concept_labels(self):
        sp = self._get_system_prompt()
        self.assertIn("| Skill | Observed Issue | Strategic Impact |", sp)
        self.assertIn("King Safety", sp)


# ---------------------------------------------------------------------------
# _system_prompt — bullet directive and bold lead-in directive
# ---------------------------------------------------------------------------

class TestBulletAndLeadInDirectives(unittest.TestCase):

    def _sp(self) -> str:
        return _SYSTEM_PROMPT

    def test_patterns_directive_requires_bullet_list(self):
        sp = self._sp()
        self.assertIn("markdown bullet list", sp)
        self.assertIn("2 to 4 bullet", sp)

    def test_patterns_directive_forbids_sub_bullets(self):
        sp = self._sp()
        self.assertIn("Do NOT nest bullets", sp)

    def test_key_takeaways_directive_forbids_bullets(self):
        sp = self._sp()
        self.assertIn("not a numbered or bulleted list", sp)

    def test_patterns_directive_requires_bold_lead_in(self):
        sp = self._sp()
        self.assertIn("bold sentence-fragment lead-in", sp)

    def test_key_takeaways_directive_requires_bold_lead_in(self):
        # Both Patterns AND Key Takeaways should have bold lead-in instructions
        sp = self._sp()
        # Key Takeaways section description
        takeaways_pos = sp.find("Key Takeaways section")
        lead_in_pos = sp.find("bold sentence-fragment lead-in", takeaways_pos)
        self.assertGreater(lead_in_pos, -1, "bold lead-in not found after Key Takeaways directive")


# ---------------------------------------------------------------------------
# Missing config — clear failure, not empty request
# ---------------------------------------------------------------------------

class TestNarrativeMissingConfig(unittest.TestCase):

    def test_generate_narrative_empty_config_returns_failure(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        result = generate_narrative(
            [game],
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="sk-test",
            base_url_override=None,
            config={},
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )
        self.assertFalse(result.success)
        self.assertIn("config.json", result.text)

    def test_generate_narrative_none_config_returns_failure(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        result = generate_narrative(
            [game],
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="sk-test",
            base_url_override=None,
            config=None,
            get_tags_for_game=ChessLogStorageService.load_resolved_paths,
        )
        self.assertFalse(result.success)
        self.assertIn("config.json", result.text)


# ---------------------------------------------------------------------------
# sanitize_narrative_markdown
# ---------------------------------------------------------------------------

class TestSanitizeNarrativeMarkdown(unittest.TestCase):

    def test_drops_bare_thematic_break_dashes(self):
        text = "Before.\n\n---\n\nAfter."
        result = sanitize_narrative_markdown(text)
        lines = result.split("\n")
        self.assertNotIn("---", lines)
        self.assertIn("Before.", result)
        self.assertIn("After.", result)

    def test_drops_thematic_break_stars(self):
        text = "A.\n***\nB."
        result = sanitize_narrative_markdown(text)
        self.assertNotIn("***", result)

    def test_drops_thematic_break_underscores(self):
        text = "A.\n___\nB."
        result = sanitize_narrative_markdown(text)
        self.assertNotIn("___", result)

    def test_preserves_surrounding_prose(self):
        text = "Introduction.\n\n---\n\nConclusion."
        result = sanitize_narrative_markdown(text)
        self.assertIn("Introduction.", result)
        self.assertIn("Conclusion.", result)

    def test_preserves_table_separator_row(self):
        text = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Calculation | Missed fork | Lost material |\n"
        )
        result = sanitize_narrative_markdown(text)
        self.assertIn("| --- | --- | --- |", result)
        self.assertIn("Calculation", result)

    def test_drops_body_row_with_empty_strategic_impact(self):
        text = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Calculation | Missed fork |  |\n"
            "| King Safety | Neglected king | Exposure |\n"
        )
        result = sanitize_narrative_markdown(text)
        self.assertNotIn("Missed fork", result)
        self.assertIn("Neglected king", result)
        self.assertIn("Exposure", result)

    def test_drops_body_row_with_empty_observed_issue(self):
        text = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Pawn Structure |  | Lost structure |\n"
        )
        result = sanitize_narrative_markdown(text)
        self.assertNotIn("Lost structure", result)

    def test_preserves_fully_populated_body_rows(self):
        text = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| King Safety | Castle delay | King exposed |\n"
            "| Calculation | Missed tactic | Material lost |\n"
        )
        result = sanitize_narrative_markdown(text)
        self.assertIn("Castle delay", result)
        self.assertIn("Missed tactic", result)


# ---------------------------------------------------------------------------
# Prompt enforcement clauses
# ---------------------------------------------------------------------------

class TestPromptEnforcementClauses(unittest.TestCase):

    def test_system_prompt_forbids_empty_strategic_impact(self):
        self.assertIn("Strategic Impact is empty", _SYSTEM_PROMPT)

    def test_system_prompt_instructs_drop_row_over_blank_cell(self):
        self.assertIn("drop the row", _SYSTEM_PROMPT)

    def test_narrative_step_reinforces_three_column_rule(self):
        self.assertIn("Strategic Impact", _NARRATIVE_STEP)
        self.assertIn("drop the row", _NARRATIVE_STEP)


# ---------------------------------------------------------------------------
# Orphan exclusion (test 18)
# ---------------------------------------------------------------------------

class TestBuildPromptExcludesOrphans(unittest.TestCase):
    """build_prompt uses load_resolved_paths — why-notes from orphan entries must
    not appear in the assembled prompt."""

    def test_build_prompt_excludes_orphan_why_notes(self):
        """A game with one resolvable entry (why='real note') and one orphan entry
        (why='ghost note') must produce a prompt containing 'real note' but not
        'ghost note'."""
        game = _make_game(
            entries_per_path={
                "0":     [_clamp("C", "real note")],
                "99999": [_clamp("M", "ghost note")],   # orphan
            },
        )
        prompt = build_prompt([game], config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("real note", prompt)
        self.assertNotIn("ghost note", prompt)


if __name__ == "__main__":
    unittest.main()

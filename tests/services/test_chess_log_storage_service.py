"""Unit tests for ChessLogStorageService."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.pgn_tag_compression import compress_and_encode_from_str

MINIMAL_PGN = (
    '[Event "Test"]\n'
    '[Site "?"]\n'
    '[Date "2026.08.24"]\n'
    '[Round "?"]\n'
    '[White "White"]\n'
    '[Black "Black"]\n'
    '[Result "*"]\n'
    '\n*\n'
)


def make_game(pgn: str = MINIMAL_PGN) -> GameData:
    return GameData(game_number=1, pgn=pgn)


def _store_and_reload(game: GameData, paths_data: dict) -> dict:
    """Helper: store paths_data, then load back from the same game object."""
    assert ChessLogStorageService.store_tags(game, paths_data)
    return ChessLogStorageService.load_tags(game)


class TestCountTags(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ChessLogStorageService.count_tags({}), 0)

    def test_three_paths_one_entry_each(self):
        data = {
            "0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "", "created": "x"}],
            "0.0": [{"id": "b", "preset": "CLAMP", "cat": "L", "why": "", "created": "x"}],
            "0.0.0": [{"id": "c", "preset": "CLAMP", "cat": "A", "why": "", "created": "x"}],
        }
        self.assertEqual(ChessLogStorageService.count_tags(data), 3)

    def test_one_path_three_entries_counts_as_one(self):
        """CCT moment with three letters = 3 entries under one path = 1 moment."""
        data = {
            "0": [
                {"id": "a", "preset": "CCT", "cat": "C", "why": "", "created": "x"},
                {"id": "b", "preset": "CCT", "cat": "C2", "why": "", "created": "x"},
                {"id": "c", "preset": "CCT", "cat": "T", "why": "", "created": "x"},
            ]
        }
        self.assertEqual(ChessLogStorageService.count_tags(data), 1)

    def test_empty_list_path_not_counted(self):
        """A path key whose list was emptied (residue after deletion) should not count."""
        data = {
            "0": [],
            "0.0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "", "created": "x"}],
        }
        self.assertEqual(ChessLogStorageService.count_tags(data), 1)


class TestRoundTrip(unittest.TestCase):
    def test_store_and_load(self):
        game = make_game()
        paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M", "test note")],
        }
        loaded = _store_and_reload(game, paths_data)
        self.assertIn("0", loaded)
        entry = loaded["0"][0]
        self.assertEqual(entry["preset"], "CLAMP")
        self.assertEqual(entry["cat"], "M")
        self.assertEqual(entry["why"], "test note")
        self.assertIn("id", entry)
        self.assertIn("created", entry)

    def test_has_flag_set_after_store(self):
        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0": [ChessLogStorageService.make_entry("CCT", "C")]
        })
        self.assertTrue(game.has_chess_log_tags)

    def test_cct_multiple_entries_same_path(self):
        """Two CCT entries on the same path survive round-trip."""
        game = make_game()
        paths_data = {
            "0.0": [
                ChessLogStorageService.make_entry("CCT", "C", "missed check"),
                ChessLogStorageService.make_entry("CCT", "T", "missed check"),
            ]
        }
        loaded = _store_and_reload(game, paths_data)
        self.assertEqual(len(loaded["0.0"]), 2)
        self.assertEqual(ChessLogStorageService.count_tags(loaded), 1)

    def test_unicode_why_survives(self):
        game = make_game()
        why = "Турнир — кастинг ферзя"
        paths_data = {"0": [ChessLogStorageService.make_entry("custom", "Тест", why)]}
        loaded = _store_and_reload(game, paths_data)
        self.assertEqual(loaded["0"][0]["why"], why)

    def test_empty_paths_round_trip(self):
        game = make_game()
        loaded = _store_and_reload(game, {})
        self.assertEqual(loaded, {})
        self.assertFalse(game.has_chess_log_tags)

    def test_pars_data_keyed_by_path(self):
        """Sideline path key survives round-trip."""
        game = make_game()
        paths_data = {
            "0.1.0": [ChessLogStorageService.make_entry("CLAMP", "C", "variation note")]
        }
        loaded = _store_and_reload(game, paths_data)
        self.assertIn("0.1.0", loaded)


class TestMissingTag(unittest.TestCase):
    def test_missing_tag_returns_empty(self):
        game = make_game()
        result = ChessLogStorageService.load_tags(game)
        self.assertEqual(result, {})
        self.assertFalse(game.has_chess_log_tags)

    def test_has_chess_log_tags_false_when_absent(self):
        game = make_game()
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(game))

    def test_has_chess_log_tags_true_after_store(self):
        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0": [ChessLogStorageService.make_entry("CLAMP", "P")]
        })
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game))


class TestChecksumCorruptionRecovery(unittest.TestCase):
    def test_corrupt_checksum_returns_empty_pgn_unchanged(self):
        """load_tags returns {} on checksum mismatch and leaves game.pgn untouched."""
        game = make_game()
        paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "L")]}
        ChessLogStorageService.store_tags(game, paths_data)
        # Corrupt the checksum in the PGN text.
        game.pgn = game.pgn.replace(
            f'[{ChessLogStorageService.TAG_CHECKSUM} "',
            f'[{ChessLogStorageService.TAG_CHECKSUM} "BAD',
        )
        pgn_before = game.pgn
        result = ChessLogStorageService.load_tags(game)
        self.assertEqual(result, {})
        # PGN must be byte-identical — load_tags is a pure read.
        self.assertEqual(game.pgn, pgn_before, "load_tags must not mutate game.pgn")
        # Corrupt tag is still present (not stripped by the read).
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game))

    def test_corrupt_payload_returns_empty_pgn_unchanged(self):
        """load_tags returns {} on bad payload and leaves game.pgn untouched."""
        game = make_game()
        paths_data = {"0": [ChessLogStorageService.make_entry("CCT", "C")]}
        ChessLogStorageService.store_tags(game, paths_data)
        # Replace encoded payload with garbage (invalid base64).
        import re
        game.pgn = re.sub(
            rf'\[{ChessLogStorageService.TAG_NAME} "[^"]*"\]',
            f'[{ChessLogStorageService.TAG_NAME} "!!!notbase64!!!"]',
            game.pgn,
        )
        pgn_before = game.pgn
        result = ChessLogStorageService.load_tags(game)
        self.assertEqual(result, {})
        self.assertEqual(game.pgn, pgn_before, "load_tags must not mutate game.pgn")

    def test_corrupt_tag_replaced_on_save(self):
        """After a corrupt tag, saving with a new moment replaces it; saving with no moments removes it."""
        import re
        # --- Save with moment replaces corrupt tag ---
        game = make_game()
        ChessLogStorageService.store_tags(
            game, {"0": [ChessLogStorageService.make_entry("CLAMP", "L")]}, {}
        )
        game.pgn = game.pgn.replace(
            f'[{ChessLogStorageService.TAG_CHECKSUM} "',
            f'[{ChessLogStorageService.TAG_CHECKSUM} "BAD',
        )
        new_data = {"1": [ChessLogStorageService.make_entry("CLAMP", "M", "saved")]}
        ok = ChessLogStorageService.store_tags(game, new_data, {})
        self.assertTrue(ok)
        result = ChessLogStorageService.load_tags(game)
        self.assertEqual(ChessLogStorageService.count_tags(result), 1)
        self.assertEqual(result["1"][0]["why"], "saved")

        # --- Save with no moments removes the tag ---
        game2 = make_game()
        ChessLogStorageService.store_tags(
            game2, {"0": [ChessLogStorageService.make_entry("CLAMP", "L")]}, {}
        )
        game2.pgn = re.sub(
            rf'\[{ChessLogStorageService.TAG_CHECKSUM} "[^"]*"\]',
            f'[{ChessLogStorageService.TAG_CHECKSUM} "BAD999"]',
            game2.pgn,
        )
        ok2 = ChessLogStorageService.clear_tags(game2)
        self.assertTrue(ok2)
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(game2))


class TestClearTags(unittest.TestCase):
    def test_clear_removes_tags(self):
        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0": [ChessLogStorageService.make_entry("CLAMP", "A")]
        })
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game))
        ChessLogStorageService.clear_tags(game)
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(game))
        self.assertFalse(game.has_chess_log_tags)
        result = ChessLogStorageService.load_tags(game)
        self.assertEqual(result, {})


class TestThreeByThreeRoundTrip(unittest.TestCase):
    """3x3 moments use cat='Why1'/'Why2'/'Why3'/'Why4'; ordering must be preserved."""

    def test_all_four_whys_round_trip_in_order(self):
        game = make_game()
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "I wanted to attack"),
            ChessLogStorageService.make_entry("3x3", "Why2", "It lost a tempo"),
            ChessLogStorageService.make_entry("3x3", "Why3", "Engine moves centrally"),
            ChessLogStorageService.make_entry("3x3", "Why4", "Slow down in future"),
        ]
        paths_data = {"0": entries}
        loaded = _store_and_reload(game, paths_data)
        self.assertIn("0", loaded)
        loaded_entries = loaded["0"]
        self.assertEqual(len(loaded_entries), 4)
        self.assertEqual([e["cat"] for e in loaded_entries], ["Why1", "Why2", "Why3", "Why4"])
        self.assertEqual(loaded_entries[0]["why"], "I wanted to attack")
        self.assertEqual(loaded_entries[1]["why"], "It lost a tempo")
        self.assertEqual(loaded_entries[2]["why"], "Engine moves centrally")
        self.assertEqual(loaded_entries[3]["why"], "Slow down in future")

    def test_partial_whys_preserve_order(self):
        """Why1 + Why3 only (Why2/Why4 skipped) — order must be Why1 then Why3."""
        game = make_game()
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "First answer"),
            ChessLogStorageService.make_entry("3x3", "Why3", "Third answer"),
        ]
        paths_data = {"0": entries}
        loaded = _store_and_reload(game, paths_data)
        loaded_entries = loaded["0"]
        self.assertEqual([e["cat"] for e in loaded_entries], ["Why1", "Why3"])

    def test_why4_only_round_trips(self):
        game = make_game()
        entries = [ChessLogStorageService.make_entry("3x3", "Why4", "Check for pins")]
        paths_data = {"0": entries}
        loaded = _store_and_reload(game, paths_data)
        loaded_entries = loaded["0"]
        self.assertEqual(len(loaded_entries), 1)
        self.assertEqual(loaded_entries[0]["cat"], "Why4")
        self.assertEqual(loaded_entries[0]["why"], "Check for pins")

    def test_threexthree_counts_as_one_moment(self):
        game = make_game()
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "a"),
            ChessLogStorageService.make_entry("3x3", "Why2", "b"),
            ChessLogStorageService.make_entry("3x3", "Why3", "c"),
        ]
        paths_data = {"0": entries}
        loaded = _store_and_reload(game, paths_data)
        self.assertEqual(ChessLogStorageService.count_tags(loaded), 1)

    def test_preset_field_preserved(self):
        game = make_game()
        paths_data = {"0": [ChessLogStorageService.make_entry("3x3", "Why1", "answer")]}
        loaded = _store_and_reload(game, paths_data)
        self.assertEqual(loaded["0"][0]["preset"], "3x3")


class TestMakeEntryIgnoreShallow(unittest.TestCase):
    def test_ignore_shallow_false_omits_field(self):
        entry = ChessLogStorageService.make_entry("CLAMP", "C")
        self.assertNotIn("ignore_shallow", entry)

    def test_ignore_shallow_true_includes_field(self):
        entry = ChessLogStorageService.make_entry("CLAMP", "C", ignore_shallow=True)
        self.assertIn("ignore_shallow", entry)
        self.assertTrue(entry["ignore_shallow"])

    def test_ignore_shallow_roundtrips_through_store_load(self):
        game = make_game()
        entries = [
            ChessLogStorageService.make_entry("CLAMP", "C", "note", ignore_shallow=True),
            ChessLogStorageService.make_entry("CLAMP", "L"),
        ]
        loaded = _store_and_reload(game, {"0": entries})
        shallow_entry = next(e for e in loaded["0"] if e.get("cat") == "C")
        normal_entry = next(e for e in loaded["0"] if e.get("cat") == "L")
        self.assertTrue(shallow_entry.get("ignore_shallow"))
        self.assertNotIn("ignore_shallow", normal_entry)


class TestClearVerdictIfTextChanged(unittest.TestCase):
    """clear_verdict_if_text_changed removes chip/Ignore fields iff text changed."""

    def _entry(self, why="note", is_shallow=False, is_vague=False,
               ignore_shallow=False, ignore_text_hash=None):
        e = ChessLogStorageService.make_entry("3x3", "Why4", why,
                                              is_shallow=is_shallow,
                                              is_vague=is_vague,
                                              ignore_shallow=ignore_shallow,
                                              ignore_text_hash=ignore_text_hash)
        return e

    def test_text_unchanged_preserves_all_fields(self):
        e = self._entry("note", is_vague=True, ignore_shallow=True, ignore_text_hash="h")
        result = ChessLogStorageService.clear_verdict_if_text_changed(e, "note")
        self.assertTrue(result.get("is_vague"))
        self.assertTrue(result.get("ignore_shallow"))
        self.assertEqual(result.get("ignore_text_hash"), "h")

    def test_text_changed_clears_all_four_fields(self):
        e = self._entry("old", is_shallow=True, is_vague=True,
                        ignore_shallow=True, ignore_text_hash="h")
        result = ChessLogStorageService.clear_verdict_if_text_changed(e, "old")
        # Sanity: unchanged → still present
        self.assertIn("is_shallow", result)
        result2 = ChessLogStorageService.clear_verdict_if_text_changed(result, "different")
        self.assertNotIn("is_shallow", result2)
        self.assertNotIn("is_vague", result2)
        self.assertNotIn("ignore_shallow", result2)
        self.assertNotIn("ignore_text_hash", result2)

    def test_whitespace_only_difference_counts_as_unchanged(self):
        e = self._entry("note", is_vague=True, ignore_shallow=True, ignore_text_hash="h")
        result = ChessLogStorageService.clear_verdict_if_text_changed(e, "  note  ")
        self.assertTrue(result.get("is_vague"))

    def test_non_verdict_fields_preserved_after_change(self):
        e = self._entry("old", is_vague=True, ignore_shallow=True)
        e["id"] = "my-uuid"
        e["preset"] = "3x3"
        e["cat"] = "Why4"
        result = ChessLogStorageService.clear_verdict_if_text_changed(e, "new text")
        self.assertEqual(result["id"], "my-uuid")
        self.assertEqual(result["why"], "old")
        self.assertEqual(result["preset"], "3x3")

    def test_returns_same_dict_when_unchanged(self):
        e = self._entry("note", is_vague=True)
        result = ChessLogStorageService.clear_verdict_if_text_changed(e, "note")
        self.assertIs(result, e)


class TestNoneAndInvalidGame(unittest.TestCase):
    def test_none_game(self):
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(None))
        self.assertEqual(ChessLogStorageService.load_tags(None), {})
        self.assertFalse(ChessLogStorageService.store_tags(None, {}))

    def test_game_with_none_pgn(self):
        game = make_game(pgn=None)
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(game))
        self.assertEqual(ChessLogStorageService.load_tags(game), {})


class TestNagShown(unittest.TestCase):
    def test_store_tags_writes_nag_shown_true(self):
        game = make_game()
        paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "M")]}
        ChessLogStorageService.store_tags(game, paths_data, nag_shown=True)
        self.assertTrue(ChessLogStorageService.load_nag_shown(game))

    def test_store_tags_omits_nag_shown_key_when_false(self):
        """nag_shown=False must not write the key at all (backward-compat)."""
        game = make_game()
        paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "M")]}
        ChessLogStorageService.store_tags(game, paths_data, nag_shown=False)
        import re
        from app.utils.pgn_tag_compression import decode_and_decompress_to_str
        import chess.pgn
        from io import StringIO
        chess_game = chess.pgn.read_game(StringIO(game.pgn))
        encoded = chess_game.headers[ChessLogStorageService.TAG_NAME]
        payload = json.loads(decode_and_decompress_to_str(encoded))
        self.assertNotIn("nag_shown", payload)

    def test_load_nag_shown_defaults_false_for_missing_tag(self):
        game = make_game()
        self.assertFalse(ChessLogStorageService.load_nag_shown(game))

    def test_load_nag_shown_defaults_false_for_missing_key(self):
        """Payload with only 'paths' (no 'nag_shown') returns False."""
        game = make_game()
        ChessLogStorageService.store_tags(game, {}, nag_shown=False)
        self.assertFalse(ChessLogStorageService.load_nag_shown(game))

    def test_nag_shown_survives_round_trip_with_paths(self):
        """nag_shown=True must coexist with paths round-tripping correctly."""
        game = make_game()
        paths_data = {"0": [ChessLogStorageService.make_entry("CCT", "Threats", "fork")]}
        ChessLogStorageService.store_tags(game, paths_data, nag_shown=True)
        loaded = ChessLogStorageService.load_tags(game)
        self.assertIn("0", loaded)
        self.assertEqual(loaded["0"][0]["cat"], "Threats")
        self.assertTrue(ChessLogStorageService.load_nag_shown(game))

    def test_load_nag_shown_returns_false_for_none_game(self):
        self.assertFalse(ChessLogStorageService.load_nag_shown(None))

    def test_load_nag_shown_returns_false_for_none_pgn(self):
        game = make_game(pgn=None)
        self.assertFalse(ChessLogStorageService.load_nag_shown(game))


class TestRemoveChessLogTagsLogsOnFailure(unittest.TestCase):
    """Phase 7: _remove_chess_log_tags logs a warning on failure instead of silently swallowing."""

    def test_warning_logged_on_cleanup_failure(self):
        from unittest.mock import patch, MagicMock
        import chess.pgn as _pgn_mod
        game = make_game()
        mock_svc = MagicMock()
        with patch(
            "app.services.chess_log_storage_service.LoggingService.get_instance",
            return_value=mock_svc,
        ), patch.object(_pgn_mod, "read_game", side_effect=IOError("disk error")):
            ChessLogStorageService._remove_chess_log_tags(game)
        mock_svc.warning.assert_called_once()
        self.assertIn("Chess Log tag cleanup failed", mock_svc.warning.call_args.args[0])


class TestNoChipInCARAGameTags(unittest.TestCase):
    """After removing chip injection, Chess Log saves must never touch CARAGameTags."""

    def _cara_game_tags(self, game: GameData) -> str:
        import chess.pgn
        from io import StringIO
        g = chess.pgn.read_game(StringIO(game.pgn))
        return g.headers.get("CARAGameTags", "") if g else ""

    def test_store_tags_does_not_add_chip_to_cara_game_tags(self):
        game = make_game()
        paths = {"0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "", "created": "x"}]}
        ChessLogStorageService.store_tags(game, paths)
        self.assertNotIn("🏷", self._cara_game_tags(game))

    def test_store_tags_preserves_existing_cara_game_tags_unchanged(self):
        pgn = (
            '[Event "Test"]\n[Site "?"]\n[Date "2026.01.01"]\n'
            '[Round "?"]\n[White "W"]\n[Black "B"]\n[Result "*"]\n'
            '[CARAGameTags "Rapid;London"]\n\n*\n'
        )
        game = make_game(pgn)
        paths = {"0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "", "created": "x"}]}
        ChessLogStorageService.store_tags(game, paths)
        self.assertEqual(self._cara_game_tags(game), "Rapid;London")

    def test_load_tags_with_legacy_chip_in_pgn_returns_moments_unchanged(self):
        """Legacy PGN that has 🏷 in CARAGameTags still loads moments correctly."""
        import json, gzip, base64
        paths = {"0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "test", "created": "x"}]}
        json_text = json.dumps({"_v": 1, "paths": paths})
        data_bytes = json_text.encode("utf-8")
        encoded = base64.b64encode(gzip.compress(data_bytes, compresslevel=9)).decode("ascii")
        from app.utils.pgn_tag_compression import compute_checksum
        checksum = compute_checksum(data_bytes)
        pgn = (
            '[Event "Test"]\n[Site "?"]\n[Date "2026.01.01"]\n'
            '[Round "?"]\n[White "W"]\n[Black "B"]\n[Result "*"]\n'
            f'[CARAGameTags "🏷;Rapid"]\n'
            f'[CARAChessLog "{encoded}"]\n'
            f'[CARAChessLogChecksum "{checksum}"]\n\n*\n'
        )
        game = make_game(pgn)
        loaded = ChessLogStorageService.load_tags(game)
        self.assertEqual(loaded, paths)


class TestClearTagsPreservesCARAGameTags(unittest.TestCase):
    """clear_tags must not touch CARAGameTags (re-serialises via chess.pgn but only removes the
    three CARAChessLog* headers)."""

    def _cara_game_tags_from_pgn(self, game: GameData) -> str:
        import chess.pgn
        from io import StringIO
        g = chess.pgn.read_game(StringIO(game.pgn))
        return g.headers.get("CARAGameTags", "") if g else ""

    def test_clear_tags_preserves_manual_game_tags(self):
        pgn = (
            '[Event "Test"]\n[Site "?"]\n[Date "2026.01.01"]\n'
            '[Round "?"]\n[White "W"]\n[Black "B"]\n[Result "*"]\n'
            '[CARAGameTags "Favourite;London"]\n\n*\n'
        )
        game = make_game(pgn)
        paths = {"0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "", "created": "x"}]}
        ChessLogStorageService.store_tags(game, paths)
        ChessLogStorageService.clear_tags(game)
        self.assertEqual(self._cara_game_tags_from_pgn(game), "Favourite;London")

    def test_clear_tags_no_game_tags_stays_empty(self):
        game = make_game()
        paths = {"0": [{"id": "a", "preset": "CLAMP", "cat": "M", "why": "", "created": "x"}]}
        ChessLogStorageService.store_tags(game, paths)
        ChessLogStorageService.clear_tags(game)
        self.assertEqual(self._cara_game_tags_from_pgn(game), "")


class TestHasChessLogTagsFlag(unittest.TestCase):
    """has_chess_log_tags is True/False at load, after store, and after clear.
    Does not bleed between sibling games.

    _extract_game_data filters out 0-move games, so load-time tests must use a
    PGN that has at least one move.
    """

    # Minimal one-move PGN without any CARA headers.
    ONE_MOVE_PGN = (
        '[Event "Test"]\n[Site "?"]\n[Date "2026.01.01"]\n'
        '[Round "?"]\n[White "W"]\n[Black "B"]\n[Result "*"]\n'
        '\n1. e4 *\n'
    )

    def _extract(self, pgn_text: str) -> dict:
        import chess.pgn
        from io import StringIO
        from app.services.pgn_service import PgnService
        chess_game = chess.pgn.read_game(StringIO(pgn_text))
        result = PgnService._extract_game_data(chess_game, pgn_text)
        self.assertIsNotNone(result, "PGN was filtered out by _extract_game_data (needs at least one move)")
        return result

    def _pgn_with_chess_log(self) -> str:
        """Build a one-move PGN that has a CARAChessLog header."""
        game = make_game(self.ONE_MOVE_PGN)
        paths = {"0": [ChessLogStorageService.make_entry("CLAMP", "C", "")]}
        ChessLogStorageService.store_tags(game, paths)
        return game.pgn

    def test_true_at_load_when_chess_log_header_present(self):
        game_dict = self._extract(self._pgn_with_chess_log())
        self.assertTrue(game_dict.get("has_chess_log_tags", False))

    def test_false_at_load_when_no_chess_log_header(self):
        game_dict = self._extract(self.ONE_MOVE_PGN)
        self.assertFalse(game_dict.get("has_chess_log_tags", False))

    def test_true_after_store_with_moments(self):
        game = make_game()
        paths = {"0": [ChessLogStorageService.make_entry("CLAMP", "M", "")]}
        ChessLogStorageService.store_tags(game, paths)
        self.assertTrue(game.has_chess_log_tags)

    def test_false_after_store_with_empty_paths(self):
        game = make_game()
        ChessLogStorageService.store_tags(game, {})
        self.assertFalse(game.has_chess_log_tags)

    def test_false_after_clear(self):
        game = make_game()
        paths = {"0": [ChessLogStorageService.make_entry("CLAMP", "A", "")]}
        ChessLogStorageService.store_tags(game, paths)
        self.assertTrue(game.has_chess_log_tags)
        ChessLogStorageService.clear_tags(game)
        self.assertFalse(game.has_chess_log_tags)

    def test_no_bleed_between_sibling_games(self):
        """Extracting an untagged game does not affect a tagged game's flag."""
        tagged_dict = self._extract(self._pgn_with_chess_log())
        untagged_dict = self._extract(self.ONE_MOVE_PGN)
        self.assertTrue(tagged_dict.get("has_chess_log_tags", False))
        self.assertFalse(untagged_dict.get("has_chess_log_tags", False))


ONE_MOVE_PGN = (
    '[Event "Test"]\n'
    '[Site "?"]\n'
    '[Date "2026.08.24"]\n'
    '[Round "?"]\n'
    '[White "White"]\n'
    '[Black "Black"]\n'
    '[Result "*"]\n'
    '\n1. e4 *\n'
)


class TestLoadResolvedPaths(unittest.TestCase):
    """load_resolved_paths hides orphan path_keys from feature code while
    leaving them in the on-disk PGN (load_tags byte-for-byte round-trip)."""

    def test_load_tags_round_trip_preserves_orphans_but_hides_them_from_resolved_view(self):
        """Full dict from load_tags contains both resolvable and orphan keys.
        Resolved view from load_resolved_paths contains only the resolvable key.
        LoggingService.warning is called exactly once for the orphan.
        """
        game = GameData(game_number=7, pgn=ONE_MOVE_PGN)
        # "0" resolves (first move exists); "99.0" is an orphan (no 100th variation)
        paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M", "good tag")],
            "99.0": [ChessLogStorageService.make_entry("CCT", "C", "orphan tag")],
        }
        # Store without guard (original_paths=None) so the orphan gets written
        ChessLogStorageService.store_tags(game, paths_data)

        # Full dict must contain both
        full = ChessLogStorageService.load_tags(game)
        self.assertIn("0", full)
        self.assertIn("99.0", full)

        mock_svc = MagicMock()
        with patch(
            "app.services.chess_log_storage_service.LoggingService.get_instance",
            return_value=mock_svc,
        ):
            resolved = ChessLogStorageService.load_resolved_paths(game)

        # Resolved view must contain only the good tag
        self.assertIn("0", resolved)
        self.assertNotIn("99.0", resolved)
        self.assertEqual(resolved["0"][0]["cat"], "M")
        # Warning logged exactly once for the orphan
        mock_svc.warning.assert_called_once()
        warning_msg = mock_svc.warning.call_args.args[0]
        self.assertIn("99.0", warning_msg)
        self.assertIn("orphan", warning_msg)

    def test_load_resolved_paths_returns_empty_for_no_chess_log_tag(self):
        game = GameData(game_number=1, pgn=ONE_MOVE_PGN)
        resolved = ChessLogStorageService.load_resolved_paths(game)
        self.assertEqual(resolved, {})

    def test_load_resolved_paths_all_valid_no_warnings(self):
        game = GameData(game_number=1, pgn=ONE_MOVE_PGN)
        paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "C")]}
        ChessLogStorageService.store_tags(game, paths_data)
        mock_svc = MagicMock()
        with patch(
            "app.services.chess_log_storage_service.LoggingService.get_instance",
            return_value=mock_svc,
        ):
            resolved = ChessLogStorageService.load_resolved_paths(game)
        self.assertIn("0", resolved)
        mock_svc.warning.assert_not_called()


class TestStoreSideOrphanGuard(unittest.TestCase):
    """store_tags with original_paths refuses newly-added orphan path_keys
    but passes through pre-existing orphans (data preservation policy)."""

    def test_save_refuses_new_orphan_but_preserves_pre_existing_orphan(self):
        """One pre-existing orphan ('99.0') passes through.
        One new resolvable key ('0') is written.
        One new orphan ('99.1') is refused and logged at ERROR."""
        game = GameData(game_number=3, pgn=ONE_MOVE_PGN)

        # Establish a pre-existing orphan on disk
        initial = {
            "99.0": [ChessLogStorageService.make_entry("CLAMP", "M", "old-orphan")],
        }
        ChessLogStorageService.store_tags(game, initial)  # no guard, writes orphan
        original_paths = ChessLogStorageService.load_tags(game)
        self.assertIn("99.0", original_paths)

        # Now try to add a resolvable key + a new orphan key
        new_paths = {
            "99.0": original_paths["99.0"],             # pre-existing orphan
            "0": [ChessLogStorageService.make_entry("CCT", "C", "new-good")],    # new, resolves
            "99.1": [ChessLogStorageService.make_entry("CCT", "T", "new-orphan")],  # new, orphan
        }

        mock_svc = MagicMock()
        with patch(
            "app.services.chess_log_storage_service.LoggingService.get_instance",
            return_value=mock_svc,
        ):
            ok = ChessLogStorageService.store_tags(
                game, new_paths, original_paths=original_paths
            )

        self.assertTrue(ok)
        # ERROR logged exactly once — for the refused new orphan
        mock_svc.error.assert_called_once()
        error_msg = mock_svc.error.call_args.args[0]
        self.assertIn("99.1", error_msg)
        self.assertIn("refusing", error_msg)

        # Reload and check the written PGN
        written = ChessLogStorageService.load_tags(game)
        self.assertIn("99.0", written)   # pre-existing orphan preserved
        self.assertIn("0", written)       # new resolvable key written
        self.assertNotIn("99.1", written) # new orphan refused

    def test_store_without_original_paths_applies_no_guard(self):
        """Backward-compat: when original_paths is None, orphan keys are written
        without error (existing behaviour before the guard was added)."""
        game = GameData(game_number=1, pgn=ONE_MOVE_PGN)
        paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "C")],
            "99.0": [ChessLogStorageService.make_entry("CLAMP", "M", "orphan")],
        }
        mock_svc = MagicMock()
        with patch(
            "app.services.chess_log_storage_service.LoggingService.get_instance",
            return_value=mock_svc,
        ):
            ok = ChessLogStorageService.store_tags(game, paths_data)  # no original_paths

        self.assertTrue(ok)
        mock_svc.error.assert_not_called()
        loaded = ChessLogStorageService.load_tags(game)
        self.assertIn("0", loaded)
        self.assertIn("99.0", loaded)  # orphan written without guard


class TestComputeCheckHash(unittest.TestCase):
    """compute_check_hash: 16 hex chars, sha256, strips whitespace."""

    def test_returns_16_hex_chars(self):
        h = ChessLogStorageService.compute_check_hash("hello")
        self.assertEqual(len(h), 16)
        self.assertRegex(h, r'^[0-9a-f]{16}$')

    def test_uses_sha256_first_16(self):
        import hashlib
        text = "I attacked too early"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(ChessLogStorageService.compute_check_hash(text), expected)

    def test_strips_whitespace_before_hashing(self):
        h_clean = ChessLogStorageService.compute_check_hash("hello")
        h_padded = ChessLogStorageService.compute_check_hash("  hello  ")
        self.assertEqual(h_clean, h_padded)

    def test_different_texts_differ(self):
        h1 = ChessLogStorageService.compute_check_hash("abc")
        h2 = ChessLogStorageService.compute_check_hash("xyz")
        self.assertNotEqual(h1, h2)

    def test_empty_string(self):
        h = ChessLogStorageService.compute_check_hash("")
        self.assertEqual(len(h), 16)


class TestIsEntryChecked(unittest.TestCase):
    """is_entry_checked covers: check_hash match/mismatch, legacy flags, ignored, no-hash."""

    def _make(self, why="some text", **kwargs):
        e = {"why": why}
        e.update(kwargs)
        return e

    def test_check_hash_match_returns_true(self):
        h = ChessLogStorageService.compute_check_hash("need to slow down")
        e = self._make(why="need to slow down", check_hash=h)
        self.assertTrue(ChessLogStorageService.is_entry_checked(e))

    def test_check_hash_with_whitespace_mismatch_text_returns_true(self):
        h = ChessLogStorageService.compute_check_hash("need to slow down")
        e = self._make(why="  need to slow down  ", check_hash=h)
        self.assertTrue(ChessLogStorageService.is_entry_checked(e))

    def test_check_hash_mismatch_returns_false(self):
        h = ChessLogStorageService.compute_check_hash("different text")
        e = self._make(why="actual text", check_hash=h)
        self.assertFalse(ChessLogStorageService.is_entry_checked(e))

    def test_is_shallow_legacy_returns_true(self):
        e = self._make(is_shallow=True)
        self.assertTrue(ChessLogStorageService.is_entry_checked(e))

    def test_is_vague_legacy_returns_true(self):
        e = self._make(is_vague=True)
        self.assertTrue(ChessLogStorageService.is_entry_checked(e))

    def test_ignore_honoured_returns_true(self):
        import hashlib
        text = "I need to double-check before moving"
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        e = self._make(why=text, ignore_shallow=True, ignore_text_hash=h)
        self.assertTrue(ChessLogStorageService.is_entry_checked(e))

    def test_no_hash_no_flags_returns_false(self):
        e = self._make()
        self.assertFalse(ChessLogStorageService.is_entry_checked(e))

    def test_empty_why_no_flags_returns_false(self):
        e = self._make(why="")
        self.assertFalse(ChessLogStorageService.is_entry_checked(e))

    def test_edit_breaks_check_hash_unchecked(self):
        orig_text = "I attacked too early"
        h = ChessLogStorageService.compute_check_hash(orig_text)
        edited = {"why": "I edited this note", "check_hash": h}
        self.assertFalse(ChessLogStorageService.is_entry_checked(edited))

    def test_restore_text_rechecks(self):
        orig_text = "I attacked too early"
        h = ChessLogStorageService.compute_check_hash(orig_text)
        restored = {"why": orig_text, "check_hash": h}
        self.assertTrue(ChessLogStorageService.is_entry_checked(restored))


class TestMakeEntryCheckHash(unittest.TestCase):
    """make_entry includes check_hash when passed; omits it when absent/None."""

    def test_check_hash_included_when_provided(self):
        e = ChessLogStorageService.make_entry("CLAMP", "C", "text", check_hash="abc123")
        self.assertEqual(e.get("check_hash"), "abc123")

    def test_check_hash_omitted_when_none(self):
        e = ChessLogStorageService.make_entry("CLAMP", "C", "text", check_hash=None)
        self.assertNotIn("check_hash", e)

    def test_check_hash_omitted_when_not_provided(self):
        e = ChessLogStorageService.make_entry("CLAMP", "C", "text")
        self.assertNotIn("check_hash", e)


class TestEntryHasFlag(unittest.TestCase):
    """entry_has_flag: is_shallow/is_vague; Ignored counts; check_hash not consulted."""

    def test_is_shallow_true_returns_true(self):
        self.assertTrue(ChessLogStorageService.entry_has_flag({"is_shallow": True}))

    def test_is_vague_true_returns_true(self):
        self.assertTrue(ChessLogStorageService.entry_has_flag({"is_vague": True}))

    def test_neither_flag_returns_false(self):
        self.assertFalse(ChessLogStorageService.entry_has_flag({"why": "some note"}))

    def test_is_shallow_with_ignore_still_returns_true(self):
        e = {"is_shallow": True, "ignore_shallow": True}
        self.assertTrue(ChessLogStorageService.entry_has_flag(e))

    def test_stale_check_hash_with_is_shallow_returns_true(self):
        # Hash of old text doesn't match current 'why', but entry_has_flag ignores
        # check_hash — only is_shallow/is_vague matter; stale entry still flagged.
        stale_hash = ChessLogStorageService.compute_check_hash("old text")
        e = {"why": "edited text", "check_hash": stale_hash, "is_shallow": True}
        self.assertTrue(ChessLogStorageService.entry_has_flag(e))

    def test_stale_check_hash_without_flag_returns_false(self):
        # Stale hash alone does not make entry flagged.
        stale_hash = ChessLogStorageService.compute_check_hash("old text")
        e = {"why": "edited text", "check_hash": stale_hash}
        self.assertFalse(ChessLogStorageService.entry_has_flag(e))


class TestCheckRun(unittest.TestCase):
    """load_check_run and store_tags _check_run round-trip."""

    def test_load_check_run_returns_none_when_absent(self):
        game = make_game()
        ChessLogStorageService.store_tags(game, {})
        self.assertIsNone(ChessLogStorageService.load_check_run(game))

    def test_load_check_run_returns_none_for_none_game(self):
        self.assertIsNone(ChessLogStorageService.load_check_run(None))

    def test_load_check_run_returns_none_when_no_tag(self):
        game = make_game()
        self.assertIsNone(ChessLogStorageService.load_check_run(game))

    def test_store_and_load_check_run_round_trip(self):
        game = make_game()
        run = {"model": "Anthropic claude-sonnet-4-6", "date": "2026-10-30T14:23:45Z"}
        ChessLogStorageService.store_tags(game, {}, check_run=run)
        loaded = ChessLogStorageService.load_check_run(game)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["model"], run["model"])
        self.assertEqual(loaded["date"], run["date"])

    def test_check_run_preserved_when_not_supplied_on_save(self):
        game = make_game()
        run = {"model": "Anthropic claude-sonnet-4-6", "date": "2026-10-30T14:23:45Z"}
        ChessLogStorageService.store_tags(game, {}, check_run=run)
        # Second save without check_run= should preserve existing _check_run
        ChessLogStorageService.store_tags(game, {"0": [ChessLogStorageService.make_entry("CLAMP", "C")]})
        loaded = ChessLogStorageService.load_check_run(game)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["model"], run["model"])

    def test_check_run_not_written_when_no_prior_run(self):
        game = make_game()
        ChessLogStorageService.store_tags(game, {})
        self.assertIsNone(ChessLogStorageService.load_check_run(game))

    def test_check_run_updated_on_explicit_write(self):
        game = make_game()
        run1 = {"model": "Model A", "date": "2026-10-01T10:00:00Z"}
        run2 = {"model": "Model B", "date": "2026-10-30T14:23:45Z"}
        ChessLogStorageService.store_tags(game, {}, check_run=run1)
        ChessLogStorageService.store_tags(game, {}, check_run=run2)
        loaded = ChessLogStorageService.load_check_run(game)
        self.assertEqual(loaded["model"], "Model B")

    def test_check_run_survives_along_with_paths(self):
        game = make_game()
        paths = {"0": [ChessLogStorageService.make_entry("CLAMP", "L", "why text",
                                                          check_hash="abcdef1234567890")]}
        run = {"model": "X", "date": "2026-10-30T12:00:00Z"}
        ChessLogStorageService.store_tags(game, paths, check_run=run)
        loaded_paths = ChessLogStorageService.load_tags(game)
        loaded_run = ChessLogStorageService.load_check_run(game)
        self.assertIn("0", loaded_paths)
        self.assertEqual(loaded_paths["0"][0].get("check_hash"), "abcdef1234567890")
        self.assertIsNotNone(loaded_run)
        self.assertEqual(loaded_run["model"], "X")


class TestDatabaseOpenFlagCorrection(unittest.TestCase):
    """3-game open: flag ✓ only for a valid, non-empty tag.

    Exercises the path that sets has_chess_log_tags at database open time:
    PgnService._extract_game_data → ChessLogStorageService.has_moments(headers).

    Assertions follow the directive:
    - Only game 1 gets ✓; game 2 (empty tag) and game 3 (corrupt tag) do not.
    - Every game's PGN is byte-identical after the open (no PGN mutations).
    - load_tags on game 3 leaves its PGN unchanged.
    - Saving game 3 with a new moment replaces the corrupt tag with a valid one.
    """

    @staticmethod
    def _make_pgn(white: str, tag_pgn: str = "") -> str:
        base = (
            f'[Event "Test"]\n'
            f'[Site "?"]\n'
            f'[Date "2026.01.01"]\n'
            f'[Round "?"]\n'
            f'[White "{white}"]\n'
            f'[Black "Black"]\n'
            f'[Result "*"]\n'
        )
        if tag_pgn:
            base += tag_pgn + "\n"
        base += "\n1. e4 e5 *\n"
        return base

    def _build_games(self):
        """Return (game1_pgn, game2_pgn, game3_pgn) with valid / empty / corrupt tags."""
        import re

        # Game 1: valid tag with 1 moment.
        g1 = GameData(game_number=1, pgn=self._make_pgn("Valid"))
        ChessLogStorageService.store_tags(
            g1, {"0": [ChessLogStorageService.make_entry("CLAMP", "M", "hi")]}, {}
        )
        game1_pgn = g1.pgn

        # Game 2: empty tag — present in PGN but encodes zero moments.
        g2 = GameData(game_number=2, pgn=self._make_pgn("EmptyTag"))
        ChessLogStorageService.store_tags(g2, {}, {})
        game2_pgn = g2.pgn

        # Game 3: corrupt checksum.
        g3 = GameData(game_number=3, pgn=self._make_pgn("CorruptTag"))
        ChessLogStorageService.store_tags(
            g3, {"0": [ChessLogStorageService.make_entry("CLAMP", "L", "corrupt")]}, {}
        )
        game3_pgn = g3.pgn.replace(
            f'[{ChessLogStorageService.TAG_CHECKSUM} "',
            f'[{ChessLogStorageService.TAG_CHECKSUM} "BAD',
        )
        return game1_pgn, game2_pgn, game3_pgn

    def _extract(self, pgn_text: str, game_number: int):
        """Run through the real database-open path for one game."""
        import chess.pgn
        from io import StringIO
        from app.services.pgn_service import PgnService
        chess_game = chess.pgn.read_game(StringIO(pgn_text))
        self.assertIsNotNone(chess_game)
        result = PgnService._extract_game_data(chess_game, original_pgn_text=pgn_text)
        self.assertIsNotNone(result)
        return result

    def test_flags_at_database_open(self):
        game1_pgn, game2_pgn, game3_pgn = self._build_games()

        d1 = self._extract(game1_pgn, 1)
        d2 = self._extract(game2_pgn, 2)
        d3 = self._extract(game3_pgn, 3)

        self.assertTrue(d1["has_chess_log_tags"],
                        "game 1 (valid, 1 moment) must show ✓")
        self.assertFalse(d2["has_chess_log_tags"],
                         "game 2 (empty tag, 0 moments) must not show ✓")
        self.assertFalse(d3["has_chess_log_tags"],
                         "game 3 (corrupt tag) must not show ✓")

        # Show All filter: only game 1 would appear.
        games = [
            GameData(game_number=i, pgn=d["pgn"],
                     has_chess_log_tags=d["has_chess_log_tags"])
            for i, d in enumerate([d1, d2, d3], 1)
        ]
        visible = [g for g in games if g.has_chess_log_tags]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].game_number, 1)

    def test_pgn_byte_identical_after_open(self):
        """_extract_game_data must not mutate any game's PGN."""
        game1_pgn, game2_pgn, game3_pgn = self._build_games()
        for pgn, label in [(game1_pgn, "valid"), (game2_pgn, "empty"), (game3_pgn, "corrupt")]:
            d = self._extract(pgn, 0)
            # _extract_game_data rstrips; normalise before comparison.
            self.assertEqual(d["pgn"], pgn.rstrip(),
                             f"{label}: PGN must be byte-identical after open")

    def test_load_tags_on_corrupt_game_does_not_mutate_pgn(self):
        """load_tags on game 3 must not change its PGN."""
        _, _, game3_pgn = self._build_games()
        game3 = GameData(game_number=3, pgn=game3_pgn)
        pgn_before = game3.pgn
        ChessLogStorageService.load_tags(game3)
        self.assertEqual(game3.pgn, pgn_before,
                         "load_tags must not mutate game.pgn on corrupt tag")

    def test_save_replaces_corrupt_tag(self):
        """Logging a moment on game 3 and saving replaces the corrupt tag."""
        _, _, game3_pgn = self._build_games()
        game3 = GameData(game_number=3, pgn=game3_pgn)
        # Verify load_tags sees nothing (corrupt).
        self.assertEqual(ChessLogStorageService.load_tags(game3), {})
        # Save a new moment.
        new_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "C", "new")]}
        ok = ChessLogStorageService.store_tags(game3, new_data, {})
        self.assertTrue(ok)
        result = ChessLogStorageService.load_tags(game3)
        self.assertEqual(ChessLogStorageService.count_tags(result), 1)
        self.assertEqual(result["0"][0]["why"], "new",
                         "new moment written correctly after corrupt tag replaced")


if __name__ == "__main__":
    unittest.main()

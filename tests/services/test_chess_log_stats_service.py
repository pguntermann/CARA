"""Tests for ChessLogStatsService aggregation."""

from __future__ import annotations

import unittest

from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService
from app.services.chess_log_stats_service import (
    CHARTED_PRESETS,
    UNCATEGORIZED,
    AggregateResult,
    ChessLogCategoryBin,
    ChessLogPresetSeries,
    aggregate,
    compute_narrative_counts,
    get_all_players,
    shallow_flag_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_PGN = (
    '[Event "Test"]\n'
    '[Site "?"]\n'
    '[Date "{date}"]\n'
    '[Round "?"]\n'
    '[White "{white}"]\n'
    '[Black "{black}"]\n'
    '[Result "*"]\n'
    '\n1. e4 e5 2. Nf3 Nc6 3. Bb5 *\n'
)

# Five path_keys that all resolve in _BASE_PGN (used by _game_with_cats helpers).
# Avoids orphan warnings from str(i) integer keys that have no matching move.
_DEEP_KEYS = ["0", "0.0", "0.0.0", "0.0.0.0", "0.0.0.0.0"]


def _make_game(
    white: str = "Alice",
    black: str = "Bob",
    date: str = "2025.01.15",
    entries_per_path: dict | None = None,
) -> GameData:
    pgn = _BASE_PGN.format(white=white, black=black, date=date)
    game = GameData(game_number=1, pgn=pgn, white=white, black=black, date=date)
    if entries_per_path:
        ChessLogStorageService.store_tags(game, entries_per_path)
    return game


def _clamp_entry(cat: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("CLAMP", cat, why)


def _cct_entry(cat: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("CCT", cat, why)


def _threexthree_entry(cat: str, why: str) -> dict:
    return ChessLogStorageService.make_entry("3x3", cat, why)


# ---------------------------------------------------------------------------
# Basic aggregation
# ---------------------------------------------------------------------------

class TestBasicAggregation(unittest.TestCase):

    def _one_game(self, entries_per_path, player="Alice", color_filter="both"):
        game = _make_game(white="Alice", black="Bob", date="2025.06.01",
                          entries_per_path=entries_per_path)
        return aggregate([game], player=player, color_filter=color_filter, get_tags_for_game=ChessLogStorageService.load_resolved_paths)

    def test_single_clamp_moment_returns_one_preset(self):
        result = self._one_game({"0": [_clamp_entry("C")]})
        self.assertIn("CLAMP", result.series)
        self.assertEqual(len(result.series), 1)

    def test_clamp_moment_count_correct(self):
        result = self._one_game({"0": [_clamp_entry("C"), _clamp_entry("L")]})
        series = result.series["CLAMP"]
        total = sum(b.total for b in series.bins)
        self.assertEqual(total, 2)

    def test_uncategorized_moment_surfaces_as_empty_key(self):
        result = self._one_game({"0": [_clamp_entry("")]})
        series = result.series["CLAMP"]
        self.assertIn(UNCATEGORIZED, series.categories)
        all_counts = {}
        for b in series.bins:
            for cat, cnt in b.counts.items():
                all_counts[cat] = all_counts.get(cat, 0) + cnt
        self.assertEqual(all_counts.get(UNCATEGORIZED, 0), 1)

    def test_uncategorized_is_last_in_categories(self):
        result = self._one_game({"0": [_clamp_entry("C"), _clamp_entry("")]})
        cats = result.series["CLAMP"].categories
        self.assertEqual(cats[-1], UNCATEGORIZED)

    def test_no_games_returns_empty(self):
        self.assertEqual(aggregate([], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths).series, {})

    def test_game_with_no_chess_log_tags_skipped(self):
        game = _make_game(white="Alice", black="Bob", date="2025.06.01")
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.series, {})


# ---------------------------------------------------------------------------
# Preset separation
# ---------------------------------------------------------------------------

class TestPresetSeparation(unittest.TestCase):

    def _mixed_game(self):
        return _make_game(
            white="Alice", black="Bob", date="2025.06.01",
            entries_per_path={
                "0": [_clamp_entry("C")],
                "0.0": [_cct_entry("Checks")],
            },
        )

    def test_two_presets_produce_two_series(self):
        result = aggregate([self._mixed_game()], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", result.series)
        self.assertIn("CCT", result.series)
        self.assertEqual(len(result.series), 2)

    def test_presets_not_mixed(self):
        result = aggregate([self._mixed_game()], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        clamp_cats = set().union(*(b.counts.keys() for b in result.series["CLAMP"].bins))
        cct_cats = set().union(*(b.counts.keys() for b in result.series["CCT"].bins))
        self.assertNotIn("Checks", clamp_cats)
        self.assertNotIn("C", cct_cats)

    def test_3x3_excluded(self):
        game = _make_game(
            white="Alice", black="Bob", date="2025.06.01",
            entries_per_path={"0": [_threexthree_entry("Why1", "reason")]},
        )
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertNotIn("3x3", result.series)

    def test_3x3_alongside_clamp_clamp_present_3x3_absent(self):
        game = _make_game(
            white="Alice", black="Bob", date="2025.06.01",
            entries_per_path={
                "0": [_clamp_entry("M")],
                "0.0": [_threexthree_entry("Why1", "thought")],
            },
        )
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", result.series)
        self.assertNotIn("3x3", result.series)


# ---------------------------------------------------------------------------
# Player filter
# ---------------------------------------------------------------------------

class TestPlayerFilter(unittest.TestCase):

    def _two_games(self):
        g1 = _make_game(white="Alice", black="Bob", date="2025.01.01",
                        entries_per_path={"0": [_clamp_entry("C")]})
        g2 = _make_game(white="Carlos", black="Alice", date="2025.02.01",
                        entries_per_path={"0": [_clamp_entry("L")]})
        g3 = _make_game(white="Carlos", black="Bob", date="2025.03.01",
                        entries_per_path={"0": [_clamp_entry("M")]})
        return [g1, g2, g3]

    def test_player_filter_excludes_games_without_player(self):
        result = aggregate(self._two_games(), player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        total = sum(b.total for b in result.series["CLAMP"].bins)
        self.assertEqual(total, 2)  # g1 and g2, not g3

    def test_color_filter_white_only(self):
        result = aggregate(self._two_games(), player="Alice", color_filter="white", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        total = sum(b.total for b in result.series["CLAMP"].bins)
        self.assertEqual(total, 1)  # only g1 (Alice is White)

    def test_color_filter_black_only(self):
        result = aggregate(self._two_games(), player="Alice", color_filter="black", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        total = sum(b.total for b in result.series["CLAMP"].bins)
        self.assertEqual(total, 1)  # only g2 (Alice is Black)

    def test_no_player_includes_all_games(self):
        result = aggregate(self._two_games(), player="", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        total = sum(b.total for b in result.series["CLAMP"].bins)
        self.assertEqual(total, 3)

    def test_player_name_case_insensitive(self):
        result = aggregate(self._two_games(), player="alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        total = sum(b.total for b in result.series["CLAMP"].bins)
        self.assertEqual(total, 2)


# ---------------------------------------------------------------------------
# Mixed-preset history across multiple games
# ---------------------------------------------------------------------------

class TestMixedPresetHistory(unittest.TestCase):

    def test_two_games_different_presets_produces_two_series(self):
        g1 = _make_game(white="Alice", black="Bob", date="2025.01.01",
                        entries_per_path={"0": [_clamp_entry("C")]})
        g2 = _make_game(white="Alice", black="Bob", date="2025.02.01",
                        entries_per_path={"0": [_cct_entry("Threats")]})
        result = aggregate([g1, g2], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", result.series)
        self.assertIn("CCT", result.series)

    def test_categories_from_same_preset_across_games_merged(self):
        g1 = _make_game(white="Alice", black="Bob", date="2025.01.01",
                        entries_per_path={"0": [_clamp_entry("C")]})
        g2 = _make_game(white="Alice", black="Bob", date="2025.02.01",
                        entries_per_path={"0": [_clamp_entry("L")]})
        result = aggregate([g1, g2], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        cats = result.series["CLAMP"].categories
        self.assertIn("C", cats)
        self.assertIn("L", cats)


# ---------------------------------------------------------------------------
# Canonical preset ordering (Item 7)
# ---------------------------------------------------------------------------

class TestCanonicalCategoryOrder(unittest.TestCase):

    def _game_with_cats(self, preset: str, cats: list[str], make_entry_fn) -> GameData:
        paths = {_DEEP_KEYS[i]: [make_entry_fn(c)] for i, c in enumerate(cats)}
        return _make_game(white="Alice", black="Bob", date="2025.06.01",
                          entries_per_path=paths)

    def test_clamp_canonical_order_regardless_of_tag_order(self):
        # Tag in reverse canonical order (P, M, A, L, C)
        game = self._game_with_cats("CLAMP", ["P", "M", "A", "L", "C"], _clamp_entry)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        cats = result.series["CLAMP"].categories
        self.assertEqual(cats, ["C", "L", "A", "M", "P"])

    def test_cct_canonical_order_regardless_of_tag_order(self):
        game = self._game_with_cats("CCT", ["Threats", "Checks", "Captures"], _cct_entry)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        cats = result.series["CCT"].categories
        self.assertEqual(cats, ["Checks", "Captures", "Threats"])

    def test_clamp_partial_subset_canonical_order(self):
        # CLAMP always seeds all 5 canonical categories even when only a subset is tagged.
        game = self._game_with_cats("CLAMP", ["P", "C"], _clamp_entry)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        cats = result.series["CLAMP"].categories
        self.assertEqual(cats, ["C", "L", "A", "M", "P"])

    def test_uncategorized_always_last_in_canonical_order(self):
        paths = {
            "0": [_clamp_entry("P")],
            "0.0": [_clamp_entry("")],
            "0.0.0": [_clamp_entry("C")],
        }
        game = _make_game(white="Alice", black="Bob", date="2025.06.01",
                          entries_per_path=paths)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        cats = result.series["CLAMP"].categories
        self.assertEqual(cats[-1], "")
        self.assertEqual(cats[0], "C")


# ---------------------------------------------------------------------------
# Canonical category always present for CLAMP/CCT (Bug 4 fix)
# ---------------------------------------------------------------------------

class TestCanonicalCategoryAlwaysPresent(unittest.TestCase):
    """CLAMP and CCT seed all canonical categories even if absent from data."""

    def _game_with_cats(self, preset: str, cats: list[str], make_entry_fn) -> GameData:
        paths = {_DEEP_KEYS[i]: [make_entry_fn(c)] for i, c in enumerate(cats)}
        return _make_game(white="Alice", black="Bob", date="2025.06.01",
                          entries_per_path=paths)

    def test_clamp_missing_categories_seeded(self):
        game = self._game_with_cats("CLAMP", ["C"], _clamp_entry)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.series["CLAMP"].categories, ["C", "L", "A", "M", "P"])

    def test_cct_missing_categories_seeded(self):
        game = self._game_with_cats("CCT", ["Threats"], _cct_entry)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.series["CCT"].categories, ["Checks", "Captures", "Threats"])

    def test_clamp_seeded_cats_have_zero_counts_in_bins(self):
        # Seeded categories absent from data must appear in categories list
        # with zero counts across all bins.
        game = self._game_with_cats("CLAMP", ["C"], _clamp_entry)
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        series = result.series["CLAMP"]
        for absent_cat in ("L", "A", "M", "P"):
            self.assertIn(absent_cat, series.categories)
            for b in series.bins:
                self.assertEqual(b.counts.get(absent_cat, 0), 0)


# ---------------------------------------------------------------------------
# Date filtering: games with undateable dates are skipped
# ---------------------------------------------------------------------------

class TestDateFiltering(unittest.TestCase):

    def test_game_with_unknown_date_skipped(self):
        game = _make_game(white="Alice", black="Bob", date="????.??.??",
                          entries_per_path={"0": [_clamp_entry("C")]})
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.series, {})

    def test_game_with_partial_date_included(self):
        game = _make_game(white="Alice", black="Bob", date="2025.??.??",
                          entries_per_path={"0": [_clamp_entry("C")]})
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", result.series)


# ---------------------------------------------------------------------------
# get_all_players
# ---------------------------------------------------------------------------

class TestGetAllPlayers(unittest.TestCase):
    """get_all_players mirrors Player Stats: threshold >= 2 tagged games, sort by count desc then name.

    Path key conventions (from pgn_variation_path.py):
      "0"   → length 1 (odd)  → White just moved
      "0.0" → length 2 (even) → Black just moved
    """

    # White's move tagged, Black's move tagged, or both.
    _WHITE_TAG = {"0": [_clamp_entry("C")]}
    _BLACK_TAG = {"0.0": [_clamp_entry("C")]}
    _BOTH_TAG  = {"0": [_clamp_entry("C")], "0.0": [_clamp_entry("C")]}

    def _white_tagged(self, white="Alice", black="Bob", date="2025.01.15"):
        """Game where only White's move is tagged."""
        return _make_game(white=white, black=black, date=date, entries_per_path=self._WHITE_TAG)

    def _black_tagged(self, white="Alice", black="Bob", date="2025.01.15"):
        """Game where only Black's move is tagged."""
        return _make_game(white=white, black=black, date=date, entries_per_path=self._BLACK_TAG)

    def _both_tagged(self, white="Alice", black="Bob", date="2025.01.15"):
        """Game where both colors have tagged moves."""
        return _make_game(white=white, black=black, date=date, entries_per_path=self._BOTH_TAG)

    def _untagged(self, white="Alice", black="Bob", date="2025.01.15"):
        return _make_game(white=white, black=black, date=date)

    def _names(self, games):
        return [name for name, _ in get_all_players(games, get_tags_for_game=ChessLogStorageService.load_resolved_paths)]

    # --- per-color correctness (the bug being fixed) ---

    def test_only_white_tagged_credits_white_not_black(self):
        # NotThePainter (White) tags their own moves; kpepin (Black) tags nothing.
        games = [
            self._white_tagged("NotThePainter", "kpepin", "2025.01.01"),
            self._white_tagged("NotThePainter", "kpepin", "2025.02.01"),
        ]
        names = self._names(games)
        self.assertIn("NotThePainter", names)
        self.assertNotIn("kpepin", names)  # kpepin's moves were never tagged

    def test_only_black_tagged_credits_black_not_white(self):
        games = [
            self._black_tagged("Alice", "Bob", "2025.01.01"),
            self._black_tagged("Alice", "Bob", "2025.02.01"),
        ]
        names = self._names(games)
        self.assertIn("Bob", names)
        self.assertNotIn("Alice", names)

    def test_both_colors_tagged_credits_both(self):
        games = [
            self._both_tagged("Alice", "Bob", "2025.01.01"),
            self._both_tagged("Alice", "Bob", "2025.02.01"),
        ]
        names = self._names(games)
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)

    def test_untagged_game_credits_neither(self):
        games = [self._untagged("Alice", "Bob")] * 5
        self.assertEqual(get_all_players(games, get_tags_for_game=ChessLogStorageService.load_resolved_paths), [])

    # --- threshold filter ---

    def test_player_with_one_tagged_game_excluded(self):
        games = [self._white_tagged("Alice", "Bob")]
        self.assertNotIn("Alice", self._names(games))

    def test_player_with_two_tagged_games_included(self):
        games = [
            self._white_tagged("Alice", "Opp1", "2025.01.01"),
            self._white_tagged("Alice", "Opp2", "2025.02.01"),
        ]
        self.assertIn("Alice", self._names(games))

    def test_untagged_games_do_not_count_toward_threshold(self):
        # 1 white-tagged + 1 untagged → still only 1 qualifying → excluded
        games = [
            self._white_tagged("Alice", "Bob", "2025.01.01"),
            self._untagged("Alice", "Carlos", "2025.02.01"),
        ]
        self.assertNotIn("Alice", self._names(games))

    def test_empty_names_excluded(self):
        # White name is empty; only Alice (Black) has tagged moves
        games = [
            self._black_tagged(white="", black="Alice", date="2025.01.01"),
            self._black_tagged(white="", black="Alice", date="2025.02.01"),
        ]
        self.assertNotIn("", self._names(games))
        self.assertIn("Alice", self._names(games))

    def test_no_games_returns_empty(self):
        self.assertEqual(get_all_players([], get_tags_for_game=ChessLogStorageService.load_resolved_paths), [])

    def test_returns_tuples_of_name_and_count(self):
        games = [
            self._white_tagged("Alice", "Opp1", "2025.01.01"),
            self._white_tagged("Alice", "Opp2", "2025.02.01"),
        ]
        result = get_all_players(games, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result[0], ("Alice", 2))

    # --- sort order ---

    def test_sorted_by_count_descending(self):
        # Alice (White) has 3 tagged games; Bob (White) has 2.
        games = [
            self._white_tagged("Alice", "Opp1", "2025.01.01"),
            self._white_tagged("Alice", "Opp2", "2025.02.01"),
            self._white_tagged("Alice", "Opp3", "2025.03.01"),
            self._white_tagged("Bob", "Opp4", "2025.04.01"),
            self._white_tagged("Bob", "Opp5", "2025.05.01"),
        ]
        names = self._names(games)
        self.assertEqual(names.index("Alice"), 0)
        self.assertEqual(names.index("Bob"), 1)

    def test_ties_broken_by_name_ascending(self):
        games = [
            self._white_tagged("Alice", "Opp1", "2025.01.01"),
            self._white_tagged("Alice", "Opp2", "2025.02.01"),
            self._white_tagged("Carlos", "Opp3", "2025.03.01"),
            self._white_tagged("Carlos", "Opp4", "2025.04.01"),
        ]
        names = self._names(games)
        self.assertLess(names.index("Alice"), names.index("Carlos"))

    def test_3x3_only_player_with_two_games_qualifies(self):
        """A player with 2 games tagged using 3x3 must appear in the dropdown."""
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "I attacked too early")
        g1 = _make_game(white="Alice", black="Bob", date="2025.01.01",
                        entries_per_path={"0": [entry]})
        entry2 = ChessLogStorageService.make_entry("3x3", "Why2", "It lost a tempo")
        g2 = _make_game(white="Alice", black="Bob", date="2025.02.01",
                        entries_per_path={"0": [entry2]})
        names = self._names([g1, g2])
        self.assertIn("Alice", names)

    def test_mixed_preset_one_each_does_not_qualify(self):
        """1 CLAMP game + 1 3x3 game = no single preset reaches threshold of 2."""
        clamp_entry = _clamp_entry("C")
        threex_entry = ChessLogStorageService.make_entry("3x3", "Why1", "text")
        g1 = _make_game(white="Alice", black="Bob", date="2025.01.01",
                        entries_per_path={"0": [clamp_entry]})
        g2 = _make_game(white="Alice", black="Bob", date="2025.02.01",
                        entries_per_path={"0": [threex_entry]})
        names = self._names([g1, g2])
        self.assertNotIn("Alice", names)

    def test_mixed_preset_two_clamp_plus_one_3x3_qualifies(self):
        """2 CLAMP + 1 3x3 — CLAMP reaches threshold so player qualifies."""
        clamp_entry = _clamp_entry("C")
        threex_entry = ChessLogStorageService.make_entry("3x3", "Why1", "text")
        g1 = _make_game(white="Alice", black="Bob", date="2025.01.01",
                        entries_per_path={"0": [clamp_entry]})
        g2 = _make_game(white="Alice", black="Bob", date="2025.02.01",
                        entries_per_path={"0": [clamp_entry]})
        g3 = _make_game(white="Alice", black="Bob", date="2025.03.01",
                        entries_per_path={"0": [threex_entry]})
        names = self._names([g1, g2, g3])
        self.assertIn("Alice", names)


# ---------------------------------------------------------------------------
# Binning mode routing (chart_cfg.ordinal_fallback_mode)
# ---------------------------------------------------------------------------

class TestBinningModeRouting(unittest.TestCase):
    """ordinal_fallback_mode in chart_cfg independently controls quantile vs equal_width."""

    def _make_games(self) -> list:
        """10 tagged games spread sparsely across a year — unequal-density distribution."""
        months = [1, 1, 1, 1, 1, 6, 7, 10, 11, 12]  # 5 in Jan, 5 spread
        games = []
        for month in months:
            g = _make_game(
                white="Alice", black="Bob",
                date=f"2026.{month:02d}.15",
                entries_per_path={"0": [_clamp_entry("C")]},
            )
            games.append(g)
        return games

    def test_quantile_mode_produces_equal_count_bins(self):
        games = self._make_games()
        cfg = {"target_progression_bins": 2, "ordinal_fallback_mode": "quantile",
               "min_games_per_ordinal_bin": 1, "max_ordinal_bins": 120}
        result = aggregate(games, player="Alice", chart_cfg=cfg, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        bins = result.series["CLAMP"].bins
        totals = [b.total for b in bins]
        # quantile splits evenly (within ±1) across N moments
        self.assertAlmostEqual(totals[0], totals[-1], delta=1)

    def test_equal_width_mode_places_bins_by_date_span(self):
        games = self._make_games()
        cfg = {"target_progression_bins": 2, "ordinal_fallback_mode": "equal_width",
               "min_games_per_ordinal_bin": 1, "max_ordinal_bins": 120}
        result = aggregate(games, player="Alice", chart_cfg=cfg, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        bins = result.series["CLAMP"].bins
        # equal_width splits the calendar; dense Jan cluster → all 5 Jan moments in bin 0
        totals = [b.total for b in bins]
        self.assertGreater(totals[0], totals[-1])

    def test_binning_mode_does_not_affect_series_rendering_fields(self):
        games = self._make_games()
        cfg = {"target_progression_bins": 2, "ordinal_fallback_mode": "quantile",
               "min_games_per_ordinal_bin": 1, "max_ordinal_bins": 120}
        result = aggregate(games, player="Alice", chart_cfg=cfg, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        series = result.series["CLAMP"]
        # Rendering fields are defaults — aggregate() doesn't set them
        self.assertEqual(series.progression_x_axis_mode, "uniform_bins")
        self.assertEqual(series.compress_gap_max_segment_days, 28)
        self.assertEqual(series.progression_line_style, "smooth")
        self.assertAlmostEqual(series.progression_line_smooth_strength, 1.0)


# ---------------------------------------------------------------------------
# ChessLogPresetSeries rendering fields
# ---------------------------------------------------------------------------

class TestPresetSeriesRenderingFields(unittest.TestCase):
    """aggregate(get_tags_for_game=ChessLogStorageService.load_resolved_paths) leaves rendering fields at defaults; callers set them."""

    def _one_game_result(self):
        game = _make_game(
            white="Alice", black="Bob",
            date="2026.01.15",
            entries_per_path={"0": [_clamp_entry("C")]},
        )
        return aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)

    def test_default_x_axis_layout(self):
        result = self._one_game_result()
        self.assertEqual(result.series["CLAMP"].progression_x_axis_mode, "uniform_bins")

    def test_default_max_gap_segment_days(self):
        result = self._one_game_result()
        self.assertEqual(result.series["CLAMP"].compress_gap_max_segment_days, 28)

    def test_default_line_style(self):
        result = self._one_game_result()
        self.assertEqual(result.series["CLAMP"].progression_line_style, "smooth")

    def test_default_smoothing_strength(self):
        result = self._one_game_result()
        self.assertAlmostEqual(result.series["CLAMP"].progression_line_smooth_strength, 1.0)

    def test_rendering_fields_are_mutable(self):
        result = self._one_game_result()
        series = result.series["CLAMP"]
        series.progression_x_axis_mode = "gap_compressed"
        series.progression_line_style = "straight"
        self.assertEqual(series.progression_x_axis_mode, "gap_compressed")
        self.assertEqual(series.progression_line_style, "straight")


class TestCalendarLinearTimePct(unittest.TestCase):
    """Regression: time_pct must be calendar-proportional, not bin-rank-based.

    Root cause of the Calendar Linear == Uniform Bins visual bug: if time_pct
    were based on bin index rather than actual calendar position, switching from
    Uniform Bins to Calendar Linear would produce an identical rendering.

    Tests pass chart_cfg with min_games_per_ordinal_bin=1 so that 10 test games
    produce 10 bins (one per game) rather than 3 (the default min_per=3 collapses
    sparse test data and can produce bins that straddle the April-July gap).
    """

    _CHART_CFG = {
        "target_progression_bins": 10,
        "min_games_per_ordinal_bin": 1,
        "max_ordinal_bins": 120,
        "ordinal_fallback_mode": "quantile",
    }

    def _gappy_games(self) -> list:
        """5 moments in April 2026, 5 in July 2026, nothing in May/June."""
        games = []
        april_dates = ["2026.04.01", "2026.04.08", "2026.04.15", "2026.04.22", "2026.04.29"]
        july_dates  = ["2026.07.01", "2026.07.08", "2026.07.15", "2026.07.22", "2026.07.29"]
        for d in april_dates + july_dates:
            games.append(_make_game(
                white="Alice", black="Bob", date=d,
                entries_per_path={"0": [_clamp_entry("C")]},
            ))
        return games

    def test_april_bins_have_low_time_pct(self):
        result = aggregate(self._gappy_games(), player="Alice", chart_cfg=self._CHART_CFG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        bins = result.series["CLAMP"].bins
        april_bins = [b for b in bins if b.lab0 < "2026-05"]
        self.assertTrue(len(april_bins) > 0)
        for b in april_bins:
            self.assertLess(b.time_pct, 30.0, f"April bin has time_pct={b.time_pct:.1f}%, expected < 30%")

    def test_july_bins_have_high_time_pct(self):
        result = aggregate(self._gappy_games(), player="Alice", chart_cfg=self._CHART_CFG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        bins = result.series["CLAMP"].bins
        july_bins = [b for b in bins if b.lab0 >= "2026-07"]
        self.assertTrue(len(july_bins) > 0)
        for b in july_bins:
            self.assertGreater(b.time_pct, 70.0, f"July bin has time_pct={b.time_pct:.1f}%, expected > 70%")

    def test_large_gap_in_time_pct_between_clusters(self):
        """The gap between last April bin and first July bin must exceed 50pp."""
        result = aggregate(self._gappy_games(), player="Alice", chart_cfg=self._CHART_CFG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        bins = sorted(result.series["CLAMP"].bins, key=lambda b: b.time_pct)
        april_bins = [b for b in bins if b.lab0 < "2026-05"]
        july_bins  = [b for b in bins if b.lab0 >= "2026-07"]
        self.assertTrue(april_bins and july_bins)
        last_april_pct = max(b.time_pct for b in april_bins)
        first_july_pct = min(b.time_pct for b in july_bins)
        gap = first_july_pct - last_april_pct
        self.assertGreater(gap, 50.0, f"Gap between clusters is only {gap:.1f}pp — time_pct may be rank-based")

    def test_time_pct_not_evenly_spaced(self):
        """time_pct values must NOT be uniformly distributed for gappy data."""
        result = aggregate(self._gappy_games(), player="Alice", chart_cfg=self._CHART_CFG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        bins = sorted(result.series["CLAMP"].bins, key=lambda b: b.time_pct)
        pcts = [b.time_pct for b in bins]
        gaps = [pcts[i + 1] - pcts[i] for i in range(len(pcts) - 1)]
        max_gap = max(gaps)
        avg_gap = sum(gaps) / len(gaps)
        # Calendar-proportional data has a large gap (May/June) relative to average spacing
        self.assertGreater(
            max_gap, avg_gap * 3,
            f"Max inter-bin gap ({max_gap:.1f}pp) not >> avg ({avg_gap:.1f}pp) — may be evenly spaced"
        )


# ---------------------------------------------------------------------------
# ChessLogPresetSeries t_min / t_max date extent (Commit 1 — calendar axis)
# ---------------------------------------------------------------------------

class TestSeriesDateExtent(unittest.TestCase):
    """aggregate(get_tags_for_game=ChessLogStorageService.load_resolved_paths) populates t_min/t_max with the raw ordinal range."""

    def _games_with_dates(self, dates: list[str]) -> list:
        return [
            _make_game(
                white="Alice", black="Bob",
                date=d.replace("-", "."),
                entries_per_path={"0": [_clamp_entry("C")]},
            )
            for d in dates
        ]

    def test_single_game_t_min_equals_t_max(self):
        from datetime import date
        games = self._games_with_dates(["2026-06-15"])
        result = aggregate(games, player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        series = result.series["CLAMP"]
        expected = date.fromisoformat("2026-06-15").toordinal()
        self.assertEqual(series.t_min, expected)
        self.assertEqual(series.t_max, expected)

    def test_t_min_is_earliest_game_ordinal(self):
        from datetime import date
        games = self._games_with_dates(["2026-04-01", "2026-07-15", "2026-12-31"])
        result = aggregate(games, player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        series = result.series["CLAMP"]
        self.assertEqual(series.t_min, date.fromisoformat("2026-04-01").toordinal())

    def test_t_max_is_latest_game_ordinal(self):
        from datetime import date
        games = self._games_with_dates(["2026-04-01", "2026-07-15", "2026-12-31"])
        result = aggregate(games, player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        series = result.series["CLAMP"]
        self.assertEqual(series.t_max, date.fromisoformat("2026-12-31").toordinal())

    def test_t_min_t_max_independent_of_binning_mode(self):
        from datetime import date
        dates = ["2026-01-01", "2026-01-15", "2026-06-01", "2026-12-31"]
        games = self._games_with_dates(dates)
        cfg_q = {"ordinal_fallback_mode": "quantile", "target_progression_bins": 2,
                 "min_games_per_ordinal_bin": 1, "max_ordinal_bins": 120}
        cfg_e = {"ordinal_fallback_mode": "equal_width", "target_progression_bins": 2,
                 "min_games_per_ordinal_bin": 1, "max_ordinal_bins": 120}
        r_q = aggregate(games, player="Alice", chart_cfg=cfg_q, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        r_e = aggregate(games, player="Alice", chart_cfg=cfg_e, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(r_q.series["CLAMP"].t_min, r_e.series["CLAMP"].t_min)
        self.assertEqual(r_q.series["CLAMP"].t_max, r_e.series["CLAMP"].t_max)
        self.assertEqual(r_q.series["CLAMP"].t_min, date.fromisoformat("2026-01-01").toordinal())
        self.assertEqual(r_q.series["CLAMP"].t_max, date.fromisoformat("2026-12-31").toordinal())

    def test_equal_width_skipped_bins_do_not_affect_t_min_t_max(self):
        """equal_width may skip empty bins; t_min/t_max must still be the raw data extremes."""
        from datetime import date
        dates = ["2026-01-01", "2026-12-31"]
        games = self._games_with_dates(dates)
        cfg = {"ordinal_fallback_mode": "equal_width", "target_progression_bins": 10,
               "min_games_per_ordinal_bin": 1, "max_ordinal_bins": 120}
        result = aggregate(games, player="Alice", chart_cfg=cfg, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        series = result.series["CLAMP"]
        self.assertEqual(series.t_min, date.fromisoformat("2026-01-01").toordinal())
        self.assertEqual(series.t_max, date.fromisoformat("2026-12-31").toordinal())


# ---------------------------------------------------------------------------
# Orphan exclusion (test 17)
# ---------------------------------------------------------------------------

class TestAggregateExcludesOrphans(unittest.TestCase):
    """aggregate(get_tags_for_game=ChessLogStorageService.load_resolved_paths) uses load_resolved_paths — orphan path_keys must not be counted."""

    def test_aggregate_excludes_orphan_path_keys(self):
        """A game with one resolvable CLAMP entry and one orphan CLAMP entry must
        produce a series with exactly 1 moment, not 2."""
        game = _make_game(
            white="Alice",
            black="Bob",
            date="2025.06.01",
            entries_per_path={
                "0":     [_clamp_entry("C")],
                "99999": [_clamp_entry("M")],   # orphan
            },
        )
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertIn("CLAMP", result.series)
        total_moments = sum(b.total for b in result.series["CLAMP"].bins)
        self.assertEqual(total_moments, 1)


# ---------------------------------------------------------------------------
# compute_narrative_counts
# ---------------------------------------------------------------------------

class TestComputeNarrativeCounts(unittest.TestCase):
    """Tests for compute_narrative_counts — N/G/M/S counting logic."""

    _BASE_PGN = (
        '[Event "Test"]\n[Site "?"]\n[Date "2025.06.01"]\n'
        '[Round "?"]\n[White "{white}"]\n[Black "{black}"]\n'
        '[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 *\n'
    )
    # Depth-1 path = White move; depth-2 path = Black move.
    _WHITE_PATH = "0"          # path_key depth 1 → White's move
    _BLACK_PATH = "0.0"        # path_key depth 2 → Black's move

    def _make_game(self, white="Alice", black="Bob", entries_per_path=None):
        pgn = self._BASE_PGN.format(white=white, black=black)
        game = GameData(game_number=1, pgn=pgn, white=white, black=black, date="2025.06.01")
        if entries_per_path:
            ChessLogStorageService.store_tags(game, entries_per_path)
        return game

    def _get_tags(self, game):
        return ChessLogStorageService.load_resolved_paths(game)

    def _counts(self, games, player="Alice", color_filter="both"):
        return compute_narrative_counts(games, player, color_filter, self._get_tags)

    def test_no_games(self):
        n, g, m, s, has_3x3 = self._counts([])
        self.assertEqual((n, g, m, s, has_3x3), (0, 0, 0, 0, False))

    def test_game_no_moments_counts_n_not_g(self):
        game = self._make_game()   # no entries_per_path → has_chess_log_tags=False
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual(n, 1)
        self.assertEqual(g, 0)
        self.assertEqual(m, 0)
        self.assertEqual(s, 0)
        self.assertFalse(has_3x3)

    def test_unflagged_clamp_moment_not_counted_in_s(self):
        # No is_shallow/is_vague → never-checked → s=0
        e = ChessLogStorageService.make_entry("CLAMP", "C", "why text")
        game = self._make_game(entries_per_path={self._WHITE_PATH: [e]})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 0, False))

    def test_shallow_flagged_clamp_counted_in_s(self):
        # is_shallow=True → counted in s
        e = ChessLogStorageService.make_entry("CLAMP", "C", "why", is_shallow=True)
        game = self._make_game(entries_per_path={self._WHITE_PATH: [e]})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 1, False))

    def test_shallow_ignored_still_counted_in_s(self):
        # is_shallow=True, ignore_shallow=True → Ignored flag still counts in s
        e = ChessLogStorageService.make_entry(
            "CLAMP", "C", "why", is_shallow=True, ignore_shallow=True
        )
        game = self._make_game(entries_per_path={self._WHITE_PATH: [e]})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 1, False))

    def test_3x3_vague_lesson_counted_in_s(self):
        # Why4 with is_vague=True → counted in s; has_3x3=True
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "w1"),
            ChessLogStorageService.make_entry("3x3", "Why2", "w2"),
            ChessLogStorageService.make_entry("3x3", "Why3", "w3"),
            ChessLogStorageService.make_entry("3x3", "Why4", "w4", is_vague=True),
        ]
        game = self._make_game(entries_per_path={self._WHITE_PATH: entries})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 1, True))

    def test_3x3_shallow_why2_ignored_still_counted_in_s(self):
        # Why2 is_shallow=True, Ignored → Ignored flag still counts in s; has_3x3=True
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "w1"),
            ChessLogStorageService.make_entry(
                "3x3", "Why2", "w2", is_shallow=True, ignore_shallow=True
            ),
            ChessLogStorageService.make_entry("3x3", "Why3", "w3"),
            ChessLogStorageService.make_entry("3x3", "Why4", "w4"),
        ]
        game = self._make_game(entries_per_path={self._WHITE_PATH: entries})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 1, True))

    def test_opponent_moment_excluded(self):
        # Black-path moment when filtering for Alice (White) → excluded from m and s
        e = ChessLogStorageService.make_entry("CLAMP", "C", "why")
        game = self._make_game(entries_per_path={self._BLACK_PATH: [e]})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual(n, 1)
        self.assertEqual(g, 0)
        self.assertEqual(m, 0)
        self.assertEqual(s, 0)
        self.assertFalse(has_3x3)

    def test_multiple_flags_on_one_moment_count_once(self):
        # CLAMP moment with multiple entries, each is_shallow=True → still s=1
        entries = [
            ChessLogStorageService.make_entry("CLAMP", "C", "note1", is_shallow=True),
            ChessLogStorageService.make_entry("CLAMP", "L", "note2", is_shallow=True),
        ]
        game = self._make_game(entries_per_path={self._WHITE_PATH: entries})
        n, g, m, s, has_3x3 = self._counts([game])
        self.assertEqual(s, 1)

    def test_never_checked_moment_not_counted_in_s(self):
        # No is_shallow/is_vague set → never-checked → s=0
        e = ChessLogStorageService.make_entry("CLAMP", "C", "note without check")
        game = self._make_game(entries_per_path={self._WHITE_PATH: [e]})
        n, g, m, s, _ = self._counts([game])
        self.assertEqual(s, 0)

    def test_combined_set_exact_counts(self):
        """Full test: N=6, G=5, M=5, S=4, has_3x3=True.

        g2 (CLAMP Shallow) and g3 (CLAMP Shallow Ignored) both count in s — Ignored
        flags count.  g4 (3x3 Vague) and g5 (3x3 Shallow Ignored) likewise.
        g1 (CLAMP unflagged) does not.
        """
        # Game 1: Alice White, White path unflagged CLAMP (s=0), Black path excluded
        g1 = self._make_game(entries_per_path={
            self._WHITE_PATH: [ChessLogStorageService.make_entry("CLAMP", "C", "why")],
            self._BLACK_PATH: [ChessLogStorageService.make_entry("CLAMP", "C", "opp")],
        })
        # Game 2: Alice White, White path CLAMP Shallow (s+1)
        g2 = self._make_game(entries_per_path={
            self._WHITE_PATH: [ChessLogStorageService.make_entry(
                "CLAMP", "C", "why", is_shallow=True
            )],
        })
        # Game 3: Alice White, White path CLAMP Shallow Ignored (s+1 — Ignored counts)
        g3 = self._make_game(entries_per_path={
            self._WHITE_PATH: [ChessLogStorageService.make_entry(
                "CLAMP", "C", "why", is_shallow=True, ignore_shallow=True
            )],
        })
        # Game 4: Alice White, 3x3 with Vague Lesson (s+1, has_3x3=True)
        g4 = self._make_game(entries_per_path={
            self._WHITE_PATH: [
                ChessLogStorageService.make_entry("3x3", "Why1", "w1"),
                ChessLogStorageService.make_entry("3x3", "Why2", "w2"),
                ChessLogStorageService.make_entry("3x3", "Why3", "w3"),
                ChessLogStorageService.make_entry("3x3", "Why4", "w4", is_vague=True),
            ],
        })
        # Game 5: Alice White, 3x3 Why2 Shallow Ignored (s+1 — Ignored counts)
        g5 = self._make_game(entries_per_path={
            self._WHITE_PATH: [
                ChessLogStorageService.make_entry("3x3", "Why1", "w1"),
                ChessLogStorageService.make_entry(
                    "3x3", "Why2", "w2", is_shallow=True, ignore_shallow=True
                ),
                ChessLogStorageService.make_entry("3x3", "Why3", "w3"),
                ChessLogStorageService.make_entry("3x3", "Why4", "w4"),
            ],
        })
        # Game 6: Alice White, no chess log tags
        g6 = self._make_game()

        n, g, m, s, has_3x3 = self._counts([g1, g2, g3, g4, g5, g6])
        self.assertEqual(n, 6, f"N expected 6, got {n}")
        self.assertEqual(g, 5, f"G expected 5, got {g}")
        self.assertEqual(m, 5, f"M expected 5, got {m}")
        self.assertEqual(s, 4, f"S expected 4, got {s}")
        self.assertTrue(has_3x3, "has_3x3 expected True")

    def test_player_not_in_game_excluded_from_n(self):
        game = self._make_game(white="Charlie", black="Bob")
        n, g, m, s, _ = self._counts([game], player="Alice")
        self.assertEqual(n, 0)


# ---------------------------------------------------------------------------
# shallow_flag_label
# ---------------------------------------------------------------------------

class TestShallowFlagLabel(unittest.TestCase):
    def test_clamp_cct_only_label_is_shallow(self):
        self.assertEqual(shallow_flag_label(False), "Shallow")

    def test_has_3x3_label_is_shallow_vague(self):
        self.assertEqual(shallow_flag_label(True), "Shallow/Vague")


# ---------------------------------------------------------------------------
# AggregateResult skip-count and has_3x3 fields
# ---------------------------------------------------------------------------

class TestAggregateSkipCounting(unittest.TestCase):

    def _dated_clamp_game(self, date="2025.01.15"):
        return _make_game(date=date, entries_per_path={"0": [_clamp_entry("C")]})

    def _undated_clamp_game(self):
        return _make_game(date="????.??.??", entries_per_path={"0": [_clamp_entry("C")]})

    def _undated_3x3_game(self):
        return _make_game(date="????.??.??",
                          entries_per_path={"0": [_threexthree_entry("Why1", "because")]})

    def test_no_undated_games_produces_zero_skip_count(self):
        game = self._dated_clamp_game()
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.n_undated_clamp_cct, 0)

    def test_one_undated_clamp_game_counted(self):
        result = aggregate([self._undated_clamp_game()], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.n_undated_clamp_cct, 1)

    def test_multiple_undated_games_all_counted(self):
        games = [self._undated_clamp_game() for _ in range(4)]
        result = aggregate(games, player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.n_undated_clamp_cct, 4)

    def test_mix_dated_and_undated_counts_only_undated(self):
        dated = [self._dated_clamp_game() for _ in range(3)]
        undated = [self._undated_clamp_game() for _ in range(2)]
        result = aggregate(dated + undated, player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.n_undated_clamp_cct, 2)
        self.assertIn("CLAMP", result.series)

    def test_undated_3x3_does_not_count_in_skip_count(self):
        result = aggregate([self._undated_3x3_game()], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.n_undated_clamp_cct, 0)

    def test_has_3x3_false_when_no_3x3_data(self):
        game = self._dated_clamp_game()
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertFalse(result.has_3x3)

    def test_has_3x3_true_when_3x3_present(self):
        game = _make_game(entries_per_path={"0": [_threexthree_entry("Why1", "because")]})
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertTrue(result.has_3x3)

    def test_has_3x3_true_alongside_clamp(self):
        game = _make_game(entries_per_path={
            "0": [_clamp_entry("C")],
            "0.0": [_threexthree_entry("Why1", "x")],
        })
        result = aggregate([game], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertTrue(result.has_3x3)
        self.assertIn("CLAMP", result.series)

    def test_undated_game_not_matched_by_player_not_counted(self):
        game = _make_game(white="Alice", black="Bob", date="????.??.??",
                          entries_per_path={"0": [_clamp_entry("C")]})
        result = aggregate([game], player="Carol", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertEqual(result.n_undated_clamp_cct, 0)

    def test_all_undated_returns_empty_series_with_count(self):
        games = [self._undated_clamp_game() for _ in range(4)]
        result = aggregate(games, player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertFalse(bool(result.series))
        self.assertEqual(result.n_undated_clamp_cct, 4)

    def test_has_3x3_true_on_undated_game(self):
        result = aggregate([self._undated_3x3_game()], player="Alice", get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        self.assertTrue(result.has_3x3)


if __name__ == "__main__":
    unittest.main()

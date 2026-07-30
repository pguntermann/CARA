"""Unit tests for encyclopedia free-text search ranking / folding helpers."""

from __future__ import annotations

import unittest

from app.services.opening_encyclopedia_service import (
    _SEARCH_RANK_ALIAS,
    _SEARCH_RANK_ECO,
    _SEARCH_RANK_ID_OR_FAMILY,
    _SEARCH_RANK_NAME_PREFIX,
    _SEARCH_RANK_NAME_SUBSTRING,
    _fold_search_text,
    _search_match_rank,
)


class SearchFoldTests(unittest.TestCase):
    def test_fold_strips_apostrophe_and_colon(self) -> None:
        self.assertEqual(
            _fold_search_text("Queen's Gambit Declined: Tarrasch"),
            "queens gambit declined tarrasch",
        )
        self.assertEqual(_fold_search_text("Qgd: Semi-Tarrasch"), "qgd semitarrasch")


class SearchRankTests(unittest.TestCase):
    def test_display_name_beats_alias(self) -> None:
        rank = _search_match_rank(
            "queens gambit declined tarrasch",
            display_name="queens gambit declined tarrasch defense",
            opening_id="qgd tarrasch",
            family_id="qgd",
            eco_codes="d32",
            aliases=("queens gambit declined tarrasch defense",),
        )
        self.assertEqual(rank, _SEARCH_RANK_NAME_PREFIX)

    def test_alias_only_match(self) -> None:
        rank = _search_match_rank(
            "queens gambit declined tarrasch",
            display_name="tarrasch defense",
            opening_id="tarrasch defense",
            family_id="",
            eco_codes="d32",
            aliases=("queens gambit declined tarrasch defense",),
        )
        self.assertEqual(rank, _SEARCH_RANK_ALIAS)

    def test_id_rank_between_name_and_alias(self) -> None:
        rank = _search_match_rank(
            "qgd tarrasch",
            display_name="something else",
            opening_id="qgd tarrasch",
            family_id="",
            eco_codes="",
            aliases=("queens gambit declined tarrasch defense",),
        )
        self.assertEqual(rank, _SEARCH_RANK_ID_OR_FAMILY)

    def test_eco_rank(self) -> None:
        rank = _search_match_rank(
            "d32",
            display_name="other",
            opening_id="other",
            family_id="",
            eco_codes="d32 d34",
            aliases=(),
        )
        self.assertEqual(rank, _SEARCH_RANK_ECO)

    def test_substring_name(self) -> None:
        rank = _search_match_rank(
            "tarrasch",
            display_name="queens gambit declined tarrasch defense",
            opening_id="x",
            family_id="",
            eco_codes="",
            aliases=(),
        )
        self.assertEqual(rank, _SEARCH_RANK_NAME_SUBSTRING)

    def test_no_match(self) -> None:
        rank = _search_match_rank(
            "najdorf",
            display_name="french defense",
            opening_id="french defense",
            family_id="french defense",
            eco_codes="c00",
            aliases=("french defense classical",),
        )
        self.assertIsNone(rank)


if __name__ == "__main__":
    unittest.main()

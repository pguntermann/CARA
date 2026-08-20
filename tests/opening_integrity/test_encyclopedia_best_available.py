"""Encyclopedia lookup must not degrade name classification; FEN may only help."""

from __future__ import annotations

import unittest
from typing import List, Optional, Tuple

import chess

from app.services.opening_encyclopedia_service import (
    EncyclopediaEntry,
    _is_ancestor_opening,
)
from app.services.opening_service import OpeningService, fen_after_sans, parse_move_sans

from tests.opening_integrity.helpers import (
    SKIP_IN_CI,
    SKIP_REASON,
    display_tuple,
    encyclopedia_service,
    iter_base_rows,
    load_tests_if_not_ci as load_tests,
    opening_service,
)

_TAIMANOV_FOUR_KNIGHTS_FEN = (
    "r1bqkb1r/p2p1ppp/2p1p3/3nP3/8/2N5/PPP2PPP/R1BQKB1R w KQkq - 1 8"
)
_TAIMANOV_FOUR_KNIGHTS_NAME = (
    "Sicilian: Taimanov, Four Knights, 6.Nxc6 bxc6 7.e5 Nd5"
)
_MISS_FEN = "8/8/8/8/8/8/8/8 w - - 0 1"


def _oid(entry: Optional[EncyclopediaEntry]) -> Optional[str]:
    return None if entry is None else entry.opening_id


@unittest.skipIf(SKIP_IN_CI, SKIP_REASON)
class TestEncyclopediaBestAvailable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.enc = encyclopedia_service()
        cls.enc._ensure_loaded()
        cls.opening = opening_service()
        cls.rows = iter_base_rows(cls.opening)

    def test_name_only_fixtures_keep_current_chooser(self) -> None:
        cases: List[Tuple[str, str, str]] = [
            ("Queen's Pawn Game: Colle System", "D05", "colle-system"),
            ("Queen's Pawn: Modern", "A40", "modern-defense"),
            (
                "Italian Game: Giuoco Pianissimo, Italian Four Knights Variation",
                "C50",
                "giuoco-pianissimo/italian-four-knights",
            ),
            (
                "Sicilian: Closed, Grand Prix, 3...e6 4.Nf3 d5",
                "B23",
                "sicilian-defense/grand-prix-attack",
            ),
            (_TAIMANOV_FOUR_KNIGHTS_NAME, "B45", "sicilian-defense/four-knights"),
        ]
        for name, eco, opening_id in cases:
            with self.subTest(name=name, eco=eco):
                entry = self.enc.lookup(name, eco)
                self.assertIsNotNone(entry)
                self.assertEqual(entry.opening_id, opening_id)

    def test_fen_does_not_replace_four_knights_with_taimanov(self) -> None:
        name_only = self.enc.lookup(_TAIMANOV_FOUR_KNIGHTS_NAME, "B45")
        with_fen = self.enc.lookup(
            _TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN
        )
        self.assertEqual(_oid(name_only), "sicilian-defense/four-knights")
        self.assertEqual(_oid(with_fen), _oid(name_only))

    def test_pending_stub_still_falls_back(self) -> None:
        entry = self.enc.lookup("Evans Gambit Declined", "C51")
        self.assertIsNotNone(entry)
        self.assertTrue(entry.used_fallback)
        self.assertFalse(entry.used_nearest)

    def test_fen_fills_empty_name(self) -> None:
        entry = self.enc.lookup("", "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN)
        self.assertEqual(_oid(entry), "sicilian-defense/four-knights")

    def test_unknown_fen_does_not_change_name_lookup(self) -> None:
        name_only = self.enc.lookup(_TAIMANOV_FOUR_KNIGHTS_NAME, "B45")
        with_miss = self.enc.lookup(
            _TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_MISS_FEN
        )
        self.assertEqual(_oid(with_miss), _oid(name_only))

    def test_fen_never_degrades_name_lookup_across_book(self) -> None:
        """FEN may fill a miss or deepen to a descendant; never a sibling/other family.

        Also checks that every resolved article is a ready encyclopedia row.
        """
        degrade: List[str] = []
        not_ready: List[str] = []
        filled = 0
        deepened = 0
        with_article = 0
        none = 0
        ready_hits = 0
        for row in self.rows:
            name_entry = self.enc.lookup(row.name, row.eco)
            fen_entry = self.enc.lookup(row.name, row.eco, fen=row.fen)
            name_id = _oid(name_entry)
            fen_id = _oid(fen_entry)
            chosen = fen_entry if fen_entry is not None else name_entry
            if chosen is not None:
                ready_hits += 1
                raw = self.enc._openings.get(chosen.opening_id) or {}
                if not self.enc._is_ready(raw):
                    not_ready.append(chosen.opening_id)
            if name_id is None:
                none += 1
                if fen_id is not None:
                    filled += 1
                continue
            with_article += 1
            if fen_id is None:
                degrade.append(f"lost article {row.eco} {row.name!r}")
            elif fen_id != name_id:
                if _is_ancestor_opening(name_id, fen_id):
                    deepened += 1
                else:
                    degrade.append(
                        f"{row.eco} {row.name!r}: {name_id} -> {fen_id}"
                    )
            if len(degrade) >= 25 and len(not_ready) >= 10:
                break
        self.assertGreater(with_article, 0)
        self.assertGreater(ready_hits, 0)
        self.assertEqual(not_ready, [], msg=f"non-ready articles: {not_ready}")
        self.assertEqual(
            degrade,
            [],
            msg=(
                f"FEN degraded name lookup ({len(degrade)} shown). "
                f"with_article={with_article} none={none} "
                f"filled={filled} deepened={deepened}"
            ),
        )

    def test_miniature_uses_article_tabiya_not_explorer_fen(self) -> None:
        """Dialog miniature is ``tabiya_fen(opening_id)``, not the classified ply."""
        entry = self.enc.lookup(
            _TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.opening_id, "sicilian-defense/four-knights")
        tabiya = self.enc.tabiya_fen(entry.opening_id)
        self.assertIsNotNone(tabiya)
        board = chess.Board(tabiya)
        self.assertTrue(board.is_valid())
        self.assertNotEqual(
            OpeningService.book_key(tabiya or ""),
            OpeningService.book_key(_TAIMANOV_FOUR_KNIGHTS_FEN),
        )
        expected = fen_after_sans(
            parse_move_sans("1. e4 c5 2. Nf3 e6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 Nc6")
        )
        self.assertEqual(
            OpeningService.book_key(tabiya or ""),
            OpeningService.book_key(expected or ""),
        )
        labeled = display_tuple(self.opening, tabiya or "")
        self.assertIsNotNone(labeled)
        self.assertIn("Four Knights", labeled[1])

    def test_bird_and_italian_tabiya_are_valid_book_positions(self) -> None:
        cases = (
            ("Bird Opening", None, "bird-opening", ["f4"]),
            (
                "Italian Game: Giuoco Pianissimo, Italian Four Knights Variation",
                "C50",
                "giuoco-pianissimo/italian-four-knights",
                None,
            ),
        )
        for name, eco, opening_id, sans in cases:
            with self.subTest(opening_id=opening_id):
                entry = self.enc.lookup(name, eco)
                self.assertIsNotNone(entry)
                self.assertEqual(entry.opening_id, opening_id)
                tabiya = self.enc.tabiya_fen(entry.opening_id)
                self.assertIsNotNone(tabiya)
                self.assertTrue(chess.Board(tabiya).is_valid())
                if sans:
                    expected = fen_after_sans(sans)
                    self.assertEqual(
                        OpeningService.book_key(tabiya or ""),
                        OpeningService.book_key(expected or ""),
                    )


if __name__ == "__main__":
    unittest.main()

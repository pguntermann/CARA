"""Tests for encyclopedia tabiya FEN selection from ECO book rows."""

from __future__ import annotations

import os
import sys
import unittest

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.opening_encyclopedia_service import (
    OpeningEncyclopediaService,
    prefer_rows_matching_display_name,
)
from app.services.opening_service import (
    EcoBookRow,
    OpeningService,
    compute_tabiya_fen,
    fen_after_sans,
    parse_move_sans,
    prefer_largest_move_order_cluster,
)


def _row(moves: str, *, name: str = "Test Opening", eco: str = "B90") -> EcoBookRow:
    sans = parse_move_sans(moves)
    fen = fen_after_sans(sans)
    assert fen is not None, f"illegal moves: {moves!r}"
    return EcoBookRow(fen=fen, name=name, eco=eco, moves=moves)


class TestParseMoveSans(unittest.TestCase):
    def test_numbered_line(self) -> None:
        self.assertEqual(parse_move_sans("1. e4 e5 2. Nf3"), ["e4", "e5", "Nf3"])

    def test_lichess_path_uses_parser(self) -> None:
        self.assertEqual(
            OpeningService.lichess_moves_path("1. e4 e5 2. Nf3"),
            "e4_e5_Nf3",
        )


class TestComputeTabiyaFen(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertIsNone(compute_tabiya_fen([]))

    def test_single_row(self) -> None:
        row = _row("1. e4 c5")
        self.assertEqual(compute_tabiya_fen([row]), row.fen)

    def test_shallowest_among_later_named_plies(self) -> None:
        root = _row("1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6")
        later = _row("1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3")
        self.assertEqual(compute_tabiya_fen([later, root]), root.fen)

    def test_sibling_lines_pop_to_common_parent(self) -> None:
        be3 = _row("1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3")
        bg5 = _row("1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Bg5")
        parent = fen_after_sans(
            parse_move_sans("1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6")
        )
        self.assertEqual(compute_tabiya_fen([be3, bg5]), parent)

    def test_transpositions_dedup_to_one_fen(self) -> None:
        a = _row("1. e4 e5 2. Nf3 Nc6 3. Bc4")
        b = _row("1. e4 e5 2. Bc4 Nc6 3. Nf3")
        self.assertEqual(OpeningService.book_key(a.fen), OpeningService.book_key(b.fen))
        chosen = compute_tabiya_fen([a, b])
        self.assertEqual(OpeningService.book_key(chosen or ""), OpeningService.book_key(a.fen))

    def test_unrelated_lines_do_not_pop_to_start(self) -> None:
        e4 = _row("1. e4 e5")
        d4 = _row("1. d4 d5")
        chosen = compute_tabiya_fen([e4, d4])
        start = OpeningService.book_key(chess.Board().fen())
        self.assertIsNotNone(chosen)
        self.assertNotEqual(OpeningService.book_key(chosen or ""), start)
        self.assertIn(OpeningService.book_key(chosen or ""), {
            OpeningService.book_key(e4.fen),
            OpeningService.book_key(d4.fen),
        })

    def test_parent_uses_common_prefix_not_shallowest_sideline(self) -> None:
        """Family root: a shallow sideline must not steal the diagram."""
        jaw = _row("1. e4 d6 2. d4 Nf6 3. f3")
        anti = _row("1. e4 d6 2. d4 Nf6 3. Nc3 Nbd7 4. f4")
        bayonet = _row("1. e4 d6 2. d4 Nf6 3. Nc3 Nbd7 4. g4")
        defining = fen_after_sans(parse_move_sans("1. e4 d6 2. d4 Nf6"))
        chosen = compute_tabiya_fen([jaw, anti, bayonet], family=True)
        self.assertEqual(
            OpeningService.book_key(chosen or ""),
            OpeningService.book_key(defining or ""),
        )
        self.assertNotEqual(
            OpeningService.book_key(chosen or ""),
            OpeningService.book_key(jaw.fen),
        )

    def test_named_entry_ignores_deeper_move_order(self) -> None:
        """Lion via 1.e4 e5 must not collapse with 1.e4 d6 transpositions to 1.e4."""
        classical = _row("1. e4 e5 2. Nf3 d6 3. d4 Nf6 4. Nc3 Nbd7")
        claw = _row("1. e4 d6 2. d4 Nf6 3. Nc3 c6 4. Be2 Nbd7 5. Nf3 e5 6. O-O Be7")
        chosen = compute_tabiya_fen([classical, claw])
        self.assertEqual(chosen, classical.fen)
        self.assertNotEqual(
            OpeningService.book_key(chosen or ""),
            OpeningService.book_key(fen_after_sans(["e4"]) or ""),
        )


class TestPreferRowsMatchingDisplayName(unittest.TestCase):
    def test_prefers_title_matched_rows(self) -> None:
        title = _row("1. Nf3 d5 2. g3", name="King's Indian Attack", eco="A07")
        alias = _row("1. Nf3 Nf6 2. g3", name="Reti: KIA", eco="A05")
        preferred = prefer_rows_matching_display_name(
            [alias, title], "King's Indian Attack"
        )
        self.assertEqual(preferred, [title])
        chosen = compute_tabiya_fen(preferred)
        self.assertEqual(
            OpeningService.book_key(chosen or ""),
            OpeningService.book_key(title.fen),
        )

    def test_falls_back_when_no_title_match(self) -> None:
        alias = _row("1. Nf3 Nf6 2. g3", name="Reti: KIA", eco="A05")
        rows = [alias]
        self.assertEqual(
            prefer_rows_matching_display_name(rows, "King's Indian Attack"),
            rows,
        )

    def test_prefix_comma_when_no_exact_title(self) -> None:
        unpin = _row(
            "1. e4 c5 2. Nf3 g6 3. d4 Bg7 4. Nc3 Qa5 5. Bd2",
            name="Pterodactyl Defense: Sicilian, Unpin",
            eco="B27",
        )
        comma = _row(
            "1. e4 g6 2. d4 Bg7 3. Nc3 c5 4. Nf3 Qa5 5. Be3",
            name="Pterodactyl Defense, Sicilian",
            eco="B06",
        )
        preferred = prefer_rows_matching_display_name(
            [comma, unpin], "Pterodactyl Defense: Sicilian"
        )
        self.assertEqual(preferred, [unpin])

    def test_exact_title_wins_over_comma_children(self) -> None:
        root = _row("1. d4 d5", name="Queen's Pawn Game", eco="D00")
        child = _row(
            "1. d4 g6",
            name="Queen's Pawn Game: Modern Defense",
            eco="A40",
        )
        preferred = prefer_rows_matching_display_name(
            [root, child], "Queen's Pawn Game"
        )
        self.assertEqual(preferred, [root])

    def test_space_is_not_a_title_continuation(self) -> None:
        attack = _row("1. Nf3 d5 2. g3", name="King's Indian Attack", eco="A07")
        other = _row("1. d4 Nf6 2. c4 e6", name="Nimzo-Indian Defense", eco="E20")
        rows = [attack, other]
        self.assertEqual(
            prefer_rows_matching_display_name(rows, "King's Indian"),
            rows,
        )


class TestPreferLargestMoveOrderCluster(unittest.TestCase):
    def test_keeps_majority_branch_when_lcp_is_one_ply(self) -> None:
        c5_a = _row(
            "1. e4 c5 2. Nf3 g6 3. d4 Bg7 4. Nc3 Qa5 5. Bd2",
            name="Pterodactyl Defense: Sicilian, Unpin",
        )
        c5_b = _row(
            "1. e4 c5 2. Nf3 g6 3. d4 Bg7 4. Nc3 Qa5 5. Be3",
            name="Pterodactyl Defense: Sicilian, Anhanguera",
        )
        g6 = _row(
            "1. e4 g6 2. d4 Bg7 3. Nc3 c5 4. Nf3 Qa5 5. Bc4",
            name="Pterodactyl Defense: Sicilian, Siroccopteryx",
        )
        clustered = prefer_largest_move_order_cluster([g6, c5_a, c5_b])
        self.assertEqual(clustered, [c5_a, c5_b])
        chosen = compute_tabiya_fen(clustered)
        expected = fen_after_sans(
            parse_move_sans("1. e4 c5 2. Nf3 g6 3. d4 Bg7 4. Nc3 Qa5")
        )
        self.assertEqual(
            OpeningService.book_key(chosen or ""),
            OpeningService.book_key(expected or ""),
        )

    def test_leaves_coherent_lines_unchanged(self) -> None:
        a = _row("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5")
        b = _row("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6")
        rows = [a, b]
        self.assertEqual(prefer_largest_move_order_cluster(rows), rows)


class TestEncyclopediaTabiyaFen(unittest.TestCase):
    def setUp(self) -> None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.svc = OpeningEncyclopediaService(
            {
                "resources": {
                    "encyclopedia_db_path": os.path.join(
                        root, "app/resources/encyclopedia/openings.db"
                    ),
                    "ecolists_path": "app/resources/ecolists",
                }
            }
        )

    def test_bird_opening_has_valid_tabiya(self) -> None:
        fen = self.svc.tabiya_fen("bird-opening")
        self.assertIsNotNone(fen)
        board = chess.Board(fen)
        self.assertTrue(board.is_valid())
        self.assertNotEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(chess.Board().fen()),
        )

    def test_parent_diagram_differs_from_named_child(self) -> None:
        parent = self.svc.tabiya_fen("bird-opening")
        child = self.svc.tabiya_fen("bird-opening/williams-gambit")
        self.assertIsNotNone(parent)
        if child:
            self.assertNotEqual(
                OpeningService.book_key(parent or ""),
                OpeningService.book_key(child),
            )

    def test_philidor_lion_uses_classical_named_line(self) -> None:
        fen = self.svc.tabiya_fen("philidor-defense/lion")
        expected = fen_after_sans(
            parse_move_sans("1. e4 e5 2. Nf3 d6 3. d4 Nf6 4. Nc3 Nbd7")
        )
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(expected or ""),
        )
        self.assertNotEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(fen_after_sans(["e4"]) or ""),
        )

    def test_lion_defense_parent_has_defining_tabiya(self) -> None:
        fen = self.svc.tabiya_fen("lion-defense")
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(
                fen_after_sans(parse_move_sans("1. e4 d6 2. d4 Nf6")) or ""
            ),
        )
        child = self.svc.tabiya_fen("lion-defense/anti-philidor")
        self.assertIsNotNone(child)
        self.assertNotEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(child or ""),
        )

    def test_unknown_id_returns_none(self) -> None:
        self.assertIsNone(self.svc.tabiya_fen("not-an-opening"))
        self.assertIsNone(self.svc.tabiya_fen(""))

    def test_kings_indian_attack_does_not_collapse_to_nf3(self) -> None:
        """Alias Reti:KIA lines must not pop the KIA family diagram to 1.Nf3."""
        fen = self.svc.tabiya_fen("kings-indian-attack")
        expected = fen_after_sans(parse_move_sans("1. Nf3 d5 2. g3"))
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(expected or ""),
        )
        self.assertNotEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(fen_after_sans(["Nf3"]) or ""),
        )

    def test_pterodactyl_sicilian_uses_c5_move_order(self) -> None:
        """Colon Sicilian lines must not mix with Modern 1.e4 g6 into 1.e4."""
        fen = self.svc.tabiya_fen("pterodactyl-defense/sicilian")
        expected = fen_after_sans(
            parse_move_sans("1. e4 c5 2. Nf3 g6 3. d4 Bg7")
        )
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(expected or ""),
        )
        self.assertNotEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(fen_after_sans(["e4"]) or ""),
        )

    def test_kings_pawn_game_tabiya_is_e4(self) -> None:
        fen = self.svc.tabiya_fen("kings-pawn-game")
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(fen_after_sans(["e4"]) or ""),
        )

    def test_queens_pawn_game_tabiya_is_d4(self) -> None:
        fen = self.svc.tabiya_fen("queens-pawn-game")
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(fen_after_sans(["d4"]) or ""),
        )

    def test_richter_veresov_tabiya_is_after_bg5(self) -> None:
        """Family article: curated DB links must beat descendant SAN-prefix collapse."""
        fen = self.svc.tabiya_fen("richter-veresov-attack")
        expected = fen_after_sans(
            parse_move_sans("1. d4 Nf6 2. Nc3 d5 3. Bg5")
        )
        self.assertIsNotNone(fen)
        self.assertEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(expected or ""),
        )
        self.assertNotEqual(
            OpeningService.book_key(fen or ""),
            OpeningService.book_key(fen_after_sans(["d4"]) or ""),
        )

    def test_tabiya_uses_exact_opening_eco_entry_links(self) -> None:
        """When DB links share the article title, tabiya must come from those rows."""
        self.svc._ensure_loaded()
        failures: List[str] = []
        for oid, raw in self.svc._openings.items():
            if not self.svc._is_ready(raw):
                continue
            display = str(raw.get("display_name") or "")
            linked = self.svc._eco_book_rows_for_exact_title(oid, display)
            if not linked:
                continue
            expected = self.svc._compute_tabiya_from_rows(linked, display)
            actual = self.svc.tabiya_fen(oid)
            if OpeningService.book_key(actual or "") != OpeningService.book_key(
                expected or ""
            ):
                failures.append(oid)
        self.assertEqual(failures, [], msg=f"tabiya mismatches: {failures[:10]}")


if __name__ == "__main__":
    unittest.main()

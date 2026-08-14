"""Missed-tactic ranking: PV1 on the before-board, not the highlight composer."""

from __future__ import annotations

import os
import sys
import unittest

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.moveslist_model import MoveData
from app.services.game_summary_service import (
    CriticalMove,
    GameSummaryService,
    format_missed_tactic_line,
)
from app.services.missed_tactic_ranking import (
    fen_before_for_ply,
    format_missed_tactic_selection_reason,
    missed_kind_label,
    mover_already_lost,
)
from app.utils.summary_text_formatter import SummaryTextFormatter
from tests.highlight_rules.helpers import moves_from_pgn

# Knight on f5: Nd6 forks Qb7 and Rc8 without check or capture.
QUIET_FORK_FEN = "2r3k1/1q6/8/5N2/8/8/8/4K3 w - - 0 10"
# Qe8# is mate; Kf1 is the played miss (king starts on g1).
MATE_FEN = "6k1/5ppp/8/8/8/8/5PPP/4Q1K1 w - - 0 20"
# Qxd5 takes an undefended queen.
CAPTURE_FEN = "4k3/8/8/3q4/8/8/8/3QK3 w - - 0 10"
# Qh5+ checks without capturing or mating.
CHECK_FEN = "4k3/8/8/8/8/8/8/4K2Q w - - 0 10"


def _svc() -> GameSummaryService:
    return GameSummaryService({})


def _with_white_before(fen: str, row: MoveData, *, eval_black: str = "") -> list:
    prev = MoveData(
        move_number=max(1, row.move_number - 1),
        black_move="a6",
        fen_black=fen,
        eval_black=eval_black,
    )
    return [prev, row]


def _played_from_fen(
    fen: str,
    played: str,
    *,
    assess: str = "Miss",
    cpl: str = "180",
    best: str = "",
    eval_after: str = "-2.00",
) -> MoveData:
    moves = moves_from_pgn(
        played,
        starting_fen=fen,
        analysis={
            chess.Board(fen).fullmove_number: {
                "white": {
                    "cpl": cpl,
                    "assess": assess,
                    "best": best,
                    "eval": eval_after,
                }
            }
        },
    )
    return moves[0]


class TestFenBeforeForPly(unittest.TestCase):
    def test_white_uses_previous_fen_black(self) -> None:
        prev = MoveData(move_number=9, black_move="a6", fen_black=QUIET_FORK_FEN)
        row = MoveData(move_number=10, white_move="Ke2", fen_white="dummy")
        self.assertEqual(fen_before_for_ply([prev, row], 1, True), QUIET_FORK_FEN)

    def test_black_uses_same_row_fen_white(self) -> None:
        row = MoveData(
            move_number=10,
            white_move="Qd4",
            black_move="Ke7",
            fen_white=CHECK_FEN,
        )
        self.assertEqual(fen_before_for_ply([row], 0, False), CHECK_FEN)

    def test_index0_white_starting_fen_when_played_matches(self) -> None:
        board = chess.Board()
        board.push_san("e4")
        row = MoveData(move_number=1, white_move="e4", fen_white=board.fen())
        self.assertEqual(fen_before_for_ply([row], 0, True), chess.STARTING_FEN)

    def test_index0_white_skips_non_starting_position(self) -> None:
        row = _played_from_fen(QUIET_FORK_FEN, "Ke2", best="Nd6")
        self.assertIsNone(fen_before_for_ply([row], 0, True))


class TestFindTopMissedTactics(unittest.TestCase):
    def test_quiet_fork_without_capture_or_check(self) -> None:
        row = _played_from_fen(QUIET_FORK_FEN, "Ke2", best="Nd6")
        self.assertNotIn("x", "Nd6")
        self.assertNotIn("+", "Nd6")
        self.assertNotIn("#", "Nd6")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(QUIET_FORK_FEN, row), is_white=True, count=3
        )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].move_notation, "10. Ke2")
        self.assertEqual(top[0].best_move, "Nd6")
        self.assertEqual(top[0].tactic_type, "fork")
        self.assertEqual(format_missed_tactic_line(top[0]), "Missed: Nd6 (fork)")
        self.assertIn("Missed fork", top[0].selection_reason)
        self.assertIn("Engine line: Nd6", top[0].selection_reason)

    def test_check_fork_still_counts_as_named_tactic(self) -> None:
        fen = "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 10"
        row = _played_from_fen(fen, "Ke2", best="Nc7+")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(fen, row), is_white=True, count=3
        )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].best_move, "Nc7+")
        self.assertEqual(top[0].tactic_type, "fork")
        self.assertEqual(format_missed_tactic_line(top[0]), "Missed: Nc7+ (fork)")

    def test_missed_mate_outranks_fork(self) -> None:
        fork_row = _played_from_fen(QUIET_FORK_FEN, "Ke2", cpl="400", best="Nd6")
        mate_row = _played_from_fen(
            MATE_FEN, "Kf1", assess="Blunder", cpl="100", best="Qe8#"
        )
        moves = (
            _with_white_before(QUIET_FORK_FEN, fork_row)
            + _with_white_before(MATE_FEN, mate_row)
        )
        top = _svc()._find_top_missed_tactics(moves, is_white=True, count=3)
        self.assertGreaterEqual(len(top), 2)
        self.assertEqual(top[0].tactic_type, "mate")
        self.assertEqual(top[0].best_move, "Qe8#")
        self.assertEqual(top[1].tactic_type, "fork")

    def test_capture_is_accepted_without_named_tactic(self) -> None:
        row = _played_from_fen(CAPTURE_FEN, "Ke2", best="Qxd5")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(CAPTURE_FEN, row), is_white=True, count=3
        )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].best_move, "Qxd5")
        self.assertIn(top[0].tactic_type, ("capture", "fork", "skewer", "pin"))
        self.assertTrue(format_missed_tactic_line(top[0]).startswith("Missed: Qxd5"))

    def test_skips_capture_when_target_is_adequately_defended(self) -> None:
        # Black queen on d5 is attacked by White's queen and defended by a pawn on e6.
        fen = "4k3/8/4p3/3q4/8/8/8/3QK3 w - - 0 10"
        row = _played_from_fen(fen, "Ke2", best="Qxd5")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(fen, row), is_white=True, count=3
        )
        self.assertEqual(top, [])

    def test_keeps_capture_when_attackers_outnumber_defenders(self) -> None:
        # Queen + knight attack d5; only the e6-pawn defends.
        fen = "4k3/8/4p3/3q4/8/2N5/8/3QK3 w - - 0 10"
        row = _played_from_fen(fen, "Ke2", best="Qxd5")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(fen, row), is_white=True, count=3
        )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].tactic_type, "capture")
        self.assertEqual(top[0].best_move, "Qxd5")

    def test_bare_check_is_not_accepted(self) -> None:
        row = _played_from_fen(CHECK_FEN, "Ke2", best="Qh5+")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(CHECK_FEN, row), is_white=True, count=3
        )
        self.assertEqual(top, [])

    def test_skips_book_and_inaccuracy_and_played_pv1(self) -> None:
        book = _played_from_fen(
            QUIET_FORK_FEN, "Ke2", assess="Book Move", best="Nd6"
        )
        inaccuracy = _played_from_fen(
            QUIET_FORK_FEN, "Ke2", assess="Inaccuracy", cpl="80", best="Nd6"
        )
        played_pv1 = _played_from_fen(
            QUIET_FORK_FEN, "Nd6", assess="Miss", best="Nd6"
        )
        svc = _svc()
        self.assertEqual(
            svc._find_top_missed_tactics(
                _with_white_before(QUIET_FORK_FEN, book), is_white=True, count=3
            ),
            [],
        )
        self.assertEqual(
            svc._find_top_missed_tactics(
                _with_white_before(QUIET_FORK_FEN, inaccuracy), is_white=True, count=3
            ),
            [],
        )
        self.assertEqual(
            svc._find_top_missed_tactics(
                _with_white_before(QUIET_FORK_FEN, played_pv1), is_white=True, count=3
            ),
            [],
        )

    def test_skips_already_lost_desperation(self) -> None:
        row = _played_from_fen(QUIET_FORK_FEN, "Ke2", best="Nd6")
        moves = _with_white_before(QUIET_FORK_FEN, row, eval_black="-6.00")
        self.assertTrue(mover_already_lost(-600.0, True))
        top = _svc()._find_top_missed_tactics(moves, is_white=True, count=3)
        self.assertEqual(top, [])

    def test_caps_at_three(self) -> None:
        fork_row = _played_from_fen(QUIET_FORK_FEN, "Ke2", cpl="500", best="Nd6")
        mate_row = _played_from_fen(
            MATE_FEN, "Kf1", assess="Blunder", cpl="400", best="Qe8#"
        )
        capture_row = _played_from_fen(CAPTURE_FEN, "Ke2", cpl="300", best="Qxd5")
        # Bare check must not fill a slot.
        check_row = _played_from_fen(CHECK_FEN, "Ke2", cpl="200", best="Qh5+")
        moves = (
            _with_white_before(QUIET_FORK_FEN, fork_row)
            + _with_white_before(MATE_FEN, mate_row)
            + _with_white_before(CAPTURE_FEN, capture_row)
            + _with_white_before(CHECK_FEN, check_row)
        )
        top = _svc()._find_top_missed_tactics(moves, is_white=True, count=3)
        self.assertEqual(len(top), 3)
        self.assertEqual([m.best_move for m in top], ["Qe8#", "Nd6", "Qxd5"])
        self.assertNotIn("Qh5+", [m.best_move for m in top])

    def test_collapses_same_engine_move_to_best_ranked_ply(self) -> None:
        first = _played_from_fen(QUIET_FORK_FEN, "Ke2", cpl="180", best="Nd6")
        first.move_number = 42
        second = _played_from_fen(QUIET_FORK_FEN, "Ke2", cpl="250", best="Nd6")
        second.move_number = 43
        moves = _with_white_before(QUIET_FORK_FEN, first) + _with_white_before(
            QUIET_FORK_FEN, second
        )
        top = _svc()._find_top_missed_tactics(moves, is_white=True, count=10)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].move_number, 43)
        self.assertEqual(top[0].best_move, "Nd6")
        self.assertAlmostEqual(top[0].cpl, 250.0)

    def test_collapses_same_tactic_from_different_origin_squares(self) -> None:
        # Same queen fork landing on c7, but from different origin squares (as in
        # Qc7+ remaining PV1 after the queen moved between plies).
        from app.services.missed_tactic_ranking import (
            RankedMissedTactic,
            _collapse_duplicate_pv1,
        )

        early = RankedMissedTactic(
            move_number=46,
            move_notation="46. h6",
            cpl=180.0,
            assessment="Mistake",
            evaluation="-1.50",
            best_move="Qc7+",
            tactic_type="fork",
            selection_reason="",
            pv_uci="c2c7",
        )
        late = RankedMissedTactic(
            move_number=49,
            move_notation="49. Qg5+",
            cpl=320.0,
            assessment="Blunder",
            evaluation="-4.00",
            best_move="Qc7+",
            tactic_type="fork",
            selection_reason="",
            pv_uci="c4c7",
        )
        # Pre-sorted like select_top_missed_tactics: better CPL first.
        ranked = [
            (1, -320.0, 0.0, 1, late),
            (1, -180.0, 0.0, 0, early),
        ]
        unique = _collapse_duplicate_pv1(ranked)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0].move_number, 49)
        self.assertEqual(unique[0].best_move, "Qc7+")
        self.assertEqual(unique[0].pv_uci, "c4c7")

    def test_collapses_captures_of_the_same_hanging_unit(self) -> None:
        queen_take = "4k3/8/8/3q4/8/8/8/3QK3 w - - 0 10"
        knight_take = "4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 11"
        first = _played_from_fen(queen_take, "Ke2", cpl="180", best="Qxd5")
        first.move_number = 10
        second = _played_from_fen(knight_take, "Ke2", cpl="220", best="Nxd5")
        second.move_number = 11
        moves = _with_white_before(queen_take, first) + _with_white_before(
            knight_take, second
        )
        top = _svc()._find_top_missed_tactics(moves, is_white=True, count=10)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].best_move, "Nxd5")
        self.assertEqual(top[0].move_number, 11)

    def test_skips_capture_when_player_already_captured(self) -> None:
        # Hanging black queen on d5; player takes a pawn with the knight instead.
        fen = "4k3/8/8/3q4/4p3/2N5/8/3QK3 w - - 0 10"
        row = _played_from_fen(fen, "Nxe4", best="Qxd5")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(fen, row), is_white=True, count=3
        )
        self.assertEqual(top, [])

    def test_keeps_capture_when_player_did_not_capture(self) -> None:
        row = _played_from_fen(CAPTURE_FEN, "Ke2", best="Qxd5")
        top = _svc()._find_top_missed_tactics(
            _with_white_before(CAPTURE_FEN, row), is_white=True, count=3
        )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].tactic_type, "capture")

    def test_black_uses_same_row_fen_white(self) -> None:
        fen = "R3K3/8/8/8/8/8/8/4k2q b - - 0 10"
        moves = moves_from_pgn(
            "Ke2",
            starting_fen=fen,
            analysis={
                10: {
                    "black": {
                        "cpl": "220",
                        "assess": "Mistake",
                        "best": "Qxa8",
                        "eval": "+5.00",
                    }
                }
            },
        )
        self.assertTrue(moves[0].fen_white)
        top = _svc()._find_top_missed_tactics(moves, is_white=False, count=3)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].best_move, "Qxa8")
        self.assertEqual(top[0].tactic_type, "capture")


class TestMissedTacticDisplay(unittest.TestCase):
    def test_format_missed_tactic_line_and_tooltip(self) -> None:
        move = CriticalMove(
            10,
            "10. Ke2",
            180.0,
            "Miss",
            "-2.00",
            best_move="Nd6",
            tactic_type="fork",
            selection_reason=format_missed_tactic_selection_reason(
                played="Ke2",
                pv1="Nd6",
                assessment="Miss",
                cpl=180.0,
                kind="fork",
            ),
        )
        self.assertEqual(format_missed_tactic_line(move), "Missed: Nd6 (fork)")
        self.assertEqual(
            format_missed_tactic_line(
                CriticalMove(1, "1. a3", 100.0, "Miss", "", best_move="Qxh7#", tactic_type="mate")
            ),
            "Missed: Qxh7# (mate)",
        )
        self.assertEqual(missed_kind_label("discovered_attack"), "discovered attack")

    def test_clipboard_includes_missed_tactics(self) -> None:
        from app.services.game_summary_service import (
            GameSummary,
            PhaseStatistics,
            PlayerStatistics,
        )

        empty_stats = PlayerStatistics(
            total_moves=0,
            analyzed_moves=0,
            book_moves=0,
            brilliant_moves=0,
            best_moves=0,
            good_moves=0,
            inaccuracies=0,
            mistakes=0,
            misses=0,
            blunders=0,
            average_cpl=0.0,
            median_cpl=0.0,
            min_cpl=0.0,
            max_cpl=0.0,
            accuracy=0.0,
            estimated_elo=0,
            best_move_percentage=0.0,
            top3_move_percentage=0.0,
            blunder_rate=0.0,
        )
        empty_phase = PhaseStatistics(
            moves=0,
            average_cpl=0.0,
            accuracy=0.0,
            book_moves=0,
            brilliant_moves=0,
            best_moves=0,
            good_moves=0,
            inaccuracies=0,
            mistakes=0,
            misses=0,
            blunders=0,
        )
        missed = CriticalMove(
            10, "10. Ke2", 180.0, "Miss", "-2.00", best_move="Nd6", tactic_type="fork"
        )
        summary = GameSummary(
            white_stats=empty_stats,
            black_stats=empty_stats,
            white_opening=empty_phase,
            white_middlegame=empty_phase,
            white_endgame=empty_phase,
            black_opening=empty_phase,
            black_middlegame=empty_phase,
            black_endgame=empty_phase,
            white_top_worst=[],
            white_top_best=[],
            black_top_worst=[],
            black_top_best=[],
            white_missed_tactics=[missed],
            black_missed_tactics=[],
            evaluation_data=[],
            opening_end=15,
            middlegame_end=40,
            endgame_type=None,
            endgame_type_group=None,
            highlights=[],
            white_accuracy_curve=[],
            black_accuracy_curve=[],
        )
        text = "\n".join(
            SummaryTextFormatter.format_critical_moments(summary, "Alice", "Bob")
        )
        self.assertIn("Alice (White) - Missed Tactics:", text)
        self.assertIn("10. Ke2 (Miss)", text)
        self.assertIn("Missed: Nd6 (fork)", text)
        self.assertNotIn("Bob (Black) - Missed Tactics:", text)


if __name__ == "__main__":
    unittest.main()

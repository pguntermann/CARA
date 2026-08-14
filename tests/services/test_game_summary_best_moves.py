"""Top-best-move ranking: class, tactic, only-move, CPL, then discounted eval gain."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.moveslist_model import MoveData
from app.services.best_move_ranking import format_best_move_selection_reason
from app.services.game_summary_service import (
    CriticalMove,
    GameSummaryService,
    _EVAL_IMPROVEMENT_CAP_CP,
    format_best_move_stat,
    format_cp_gain,
)
from tests.highlight_rules.helpers import moves_from_pgn


def _svc() -> GameSummaryService:
    return GameSummaryService({})


def _white(
    number: int,
    san: str,
    *,
    assess: str = "Best Move",
    cpl: str = "0",
    cpl_2: str = "",
    eval_white: str = "",
    eval_black: str = "",
    capture: str = "",
    fen_white: str = "",
) -> MoveData:
    return MoveData(
        move_number=number,
        white_move=san,
        black_move="a6",
        assess_white=assess,
        cpl_white=cpl,
        cpl_white_2=cpl_2,
        eval_white=eval_white,
        eval_black=eval_black,
        white_capture=capture,
        fen_white=fen_white,
    )


class TestFindTopBestMoves(unittest.TestCase):
    def test_equal_cpl_ranks_by_eval_improvement(self) -> None:
        # White-before for move N is previous row's eval_black.
        moves = [
            _white(1, "e4", eval_white="+0.20", eval_black="+0.20"),  # +20
            _white(2, "d4", eval_white="+1.50", eval_black="+0.20"),  # +130
            _white(3, "c4", eval_white="+0.50"),  # +30
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertEqual(
            [m.move_notation for m in top],
            ["2. d4", "3. c4", "1. e4"],
        )
        self.assertAlmostEqual(top[0].eval_improvement, 130.0)
        self.assertEqual(format_cp_gain(top[0].eval_improvement), "CP gain: +130")

    def test_brilliant_outranks_larger_eval_gain(self) -> None:
        moves = [
            _white(1, "Nf3", assess="Best Move", eval_white="+2.00", eval_black="+0.05"),
            _white(2, "Bxh7+", assess="Brilliant", eval_white="+0.10"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=2)
        self.assertEqual(top[0].move_notation, "2. Bxh7+")
        self.assertEqual(top[1].move_notation, "1. Nf3")

    def test_best_move_outranks_good_move_with_equal_cpl(self) -> None:
        moves = [
            _white(21, "Bxe5", assess="Best Move", eval_white="+0.50", eval_black="+0.20"),
            _white(25, "Rxd8+", assess="Good Move", eval_white="+6.00", eval_black="+0.50"),
            _white(32, "Rxe5", assess="Best Move", eval_white="+8.00", eval_black="+2.00"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        # Captures get ranking-gain 0, so the two Best Moves keep game order.
        self.assertEqual(
            [m.move_notation for m in top],
            ["21. Bxe5", "32. Rxe5", "25. Rxd8+"],
        )

    def test_lower_cpl_outranks_larger_eval_gain(self) -> None:
        moves = [
            _white(1, "Qd4", assess="Good Move", cpl="40", eval_white="+2.00", eval_black="0.00"),
            _white(2, "Qd5", assess="Best Move", cpl="0", eval_white="+0.10"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=2)
        self.assertEqual([m.move_notation for m in top], ["2. Qd5", "1. Qd4"])

    def test_book_moves_excluded(self) -> None:
        moves = [
            _white(1, "e4", assess="Book Move", eval_white="+0.30", eval_black="+0.30"),
            _white(2, "Nf3", eval_white="+0.40"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertEqual([m.move_notation for m in top], ["2. Nf3"])

    def test_mate_jump_is_capped(self) -> None:
        svc = _svc()
        moves = [_white(1, "Qh5", eval_white="M2")]
        gain = svc._eval_improvement_cp(moves, 0, True)
        self.assertEqual(gain, _EVAL_IMPROVEMENT_CAP_CP)

    def test_format_cp_gain(self) -> None:
        self.assertEqual(format_cp_gain(0.0), "CP gain: 0")
        self.assertEqual(format_cp_gain(130.4), "CP gain: +130")
        self.assertEqual(format_cp_gain(-12.0), "CP gain: 0")
        self.assertEqual(format_cp_gain(-500.0), "CP gain: 0")

    def test_format_best_move_stat_uses_cpl_when_not_best_or_brilliant(self) -> None:
        best = CriticalMove(1, "1. d4", 0.0, "Best Move", "+1.50", eval_improvement=130.0)
        brilliant = CriticalMove(2, "2. Bxh7+", 0.0, "Brilliant (3,4)", "+0.10", eval_improvement=-500.0)
        good = CriticalMove(3, "3. Qd4", 40.0, "Good Move", "+2.00", eval_improvement=200.0)
        self.assertEqual(format_best_move_stat(best), "CP gain: +130")
        self.assertEqual(format_best_move_stat(brilliant), "CP gain: 0")
        self.assertEqual(format_best_move_stat(good), "CPL: 40")

    def test_black_improvement_uses_inverted_eval(self) -> None:
        moves = [
            MoveData(
                move_number=10,
                white_move="Qd4",
                black_move="Qxd4",
                eval_white="+1.00",
                eval_black="+0.20",
                cpl_black="0",
                assess_black="Best Move",
            )
        ]
        svc = _svc()
        self.assertAlmostEqual(svc._eval_improvement_cp(moves, 0, False), 80.0)
        top = svc._find_top_best_moves(moves, is_white=False, count=1)
        self.assertEqual(top[0].move_notation, "10. Qxd4")
        self.assertAlmostEqual(top[0].eval_improvement, 80.0)

    def test_search_noise_does_not_outrank_real_gain(self) -> None:
        moves = [
            _white(1, "a3", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "Kf4", eval_white="+38.20", eval_black="+0.30"),
            _white(3, "Nf5", eval_white="+1.80"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertEqual(top[0].move_notation, "3. Nf5")
        self.assertAlmostEqual(top[0].eval_improvement, 150.0)
        self.assertAlmostEqual(top[1].eval_improvement, 20.0)
        self.assertEqual(top[1].move_notation, "1. a3")

    def test_capture_eval_jump_does_not_outrank_quiet_gain(self) -> None:
        moves = [
            _white(1, "a3", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "Rxe5", eval_white="+8.00", eval_black="+0.20"),
            _white(3, "Nf5", eval_white="+1.50"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertEqual(
            [m.move_notation for m in top],
            ["3. Nf5", "1. a3", "2. Rxe5"],
        )
        self.assertAlmostEqual(top[2].eval_improvement, 500.0)

    def test_already_winning_conversion_does_not_outrank_real_gain(self) -> None:
        moves = [
            _white(1, "a3", eval_white="+6.00", eval_black="+6.00"),
            _white(2, "h3", eval_white="+8.00", eval_black="+0.30"),
            _white(3, "Nf5", eval_white="+1.80"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertEqual(top[0].move_notation, "3. Nf5")
        self.assertAlmostEqual(top[0].eval_improvement, 150.0)

    def test_only_move_outranks_equal_best(self) -> None:
        moves = [
            _white(1, "e4", eval_white="+0.20"),
            _white(2, "d4", eval_white="+0.40", eval_black="+0.20", cpl_2="80"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=2)
        self.assertEqual([m.move_notation for m in top], ["2. d4", "1. e4"])

    def test_fills_from_best_before_including_good(self) -> None:
        moves = [
            _white(1, "e4", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "d4", eval_white="+0.40", eval_black="+0.20"),
            _white(3, "c4", eval_white="+0.50", eval_black="+0.20"),
            _white(4, "Qh5", assess="Good Move", eval_white="+6.00"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        notations = [m.move_notation for m in top]
        self.assertNotIn("4. Qh5", notations)
        self.assertEqual(len(notations), 3)

    def test_good_fills_when_fewer_than_three_best(self) -> None:
        moves = [
            _white(1, "e4", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "d4", eval_white="+1.50", eval_black="+0.20"),
            _white(3, "Qh5", assess="Good Move", eval_white="+0.50"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertEqual(
            [m.move_notation for m in top],
            ["2. d4", "1. e4", "3. Qh5"],
        )

    def test_fork_outranks_quiet_best_with_larger_gain(self) -> None:
        quiet = _white(9, "a3", eval_white="+2.00", eval_black="+0.00")
        fork_rows = moves_from_pgn(
            "Nc7+",
            starting_fen="r3k3/8/8/1N6/8/8/8/4K3 w - - 0 10",
            analysis={10: {"white": {"cpl": "0", "assess": "Best Move", "eval": "+0.50"}}},
        )
        top = _svc()._find_top_best_moves([quiet] + fork_rows, is_white=True, count=2)
        self.assertEqual(top[0].move_notation, "10. Nc7+")
        self.assertEqual(top[1].move_notation, "9. a3")

    def test_good_fork_does_not_outrank_quiet_best(self) -> None:
        quiet = _white(9, "a3", eval_white="+0.40", eval_black="+0.00")
        fork_rows = moves_from_pgn(
            "Nc7+",
            starting_fen="r3k3/8/8/1N6/8/8/8/4K3 w - - 0 10",
            analysis={10: {"white": {"cpl": "20", "assess": "Good Move", "eval": "+0.50"}}},
        )
        top = _svc()._find_top_best_moves([quiet] + fork_rows, is_white=True, count=2)
        self.assertEqual(top[0].move_notation, "9. a3")
        self.assertEqual(top[1].move_notation, "10. Nc7+")


class TestBestMoveSelectionReason(unittest.TestCase):
    def test_format_covers_class_tactic_only_move_and_ignored_gain(self) -> None:
        text = format_best_move_selection_reason(
            assessment="Best Move",
            tactic_type="fork",
            only_move=True,
            only_move_cpl2=80.0,
            display_gain=500.0,
            gain_ignored="capture",
        )
        self.assertEqual(
            text,
            "Chosen as a Best Move\n"
            "Tactic: fork\n"
            "Only engine move (next-best CPL 80)\n"
            "Eval jump ignored: capture",
        )

    def test_format_brilliant_and_good_filler(self) -> None:
        self.assertEqual(
            format_best_move_selection_reason(assessment="Brilliant (3,4)"),
            "Chosen as a Brilliant move\nCP gain 0 counted in ranking",
        )
        self.assertEqual(
            format_best_move_selection_reason(
                assessment="Good Move", is_filler=True
            ),
            "Good Move included to fill the top 3",
        )

    def test_fork_tooltip_names_the_tactic(self) -> None:
        quiet = _white(9, "a3", eval_white="+2.00", eval_black="+0.00")
        fork_rows = moves_from_pgn(
            "Nc7+",
            starting_fen="r3k3/8/8/1N6/8/8/8/4K3 w - - 0 10",
            analysis={10: {"white": {"cpl": "0", "assess": "Best Move", "eval": "+0.50"}}},
        )
        top = _svc()._find_top_best_moves([quiet] + fork_rows, is_white=True, count=1)
        self.assertIn("Chosen as a Best Move", top[0].selection_reason)
        self.assertIn("Tactic: fork", top[0].selection_reason)

    def test_capture_tooltip_says_eval_jump_ignored(self) -> None:
        moves = [
            _white(1, "a3", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "Rxe5", eval_white="+8.00", eval_black="+0.20"),
            _white(3, "Nf5", eval_white="+1.50"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        rxe5 = next(m for m in top if m.move_notation == "2. Rxe5")
        self.assertIn("Eval jump ignored: capture", rxe5.selection_reason)

    def test_only_move_tooltip(self) -> None:
        moves = [
            _white(1, "e4", eval_white="+0.20"),
            _white(2, "d4", eval_white="+0.40", eval_black="+0.20", cpl_2="80"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=1)
        self.assertIn("Only engine move (next-best CPL 80)", top[0].selection_reason)

    def test_good_filler_tooltip(self) -> None:
        moves = [
            _white(1, "e4", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "d4", eval_white="+1.50", eval_black="+0.20"),
            _white(3, "Qh5", assess="Good Move", eval_white="+0.50"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        self.assertIn("fill the top 3", top[2].selection_reason)

    def test_search_noise_tooltip(self) -> None:
        moves = [
            _white(1, "a3", eval_white="+0.20", eval_black="+0.20"),
            _white(2, "Kf4", eval_white="+38.20", eval_black="+0.30"),
            _white(3, "Nf5", eval_white="+1.80"),
        ]
        top = _svc()._find_top_best_moves(moves, is_white=True, count=3)
        kf4 = next(m for m in top if m.move_notation == "2. Kf4")
        self.assertIn("Eval jump ignored: search noise", kf4.selection_reason)

    def test_quiet_best_tooltip_includes_counted_gain(self) -> None:
        text = format_best_move_selection_reason(
            assessment="Best Move",
            display_gain=10.0,
        )
        self.assertEqual(
            text,
            "Chosen as a Best Move\nCP gain +10 counted in ranking",
        )

    def test_wrap_tooltip_preserves_newlines(self) -> None:
        from app.utils.tooltip_utils import wrap_tooltip_text

        html = wrap_tooltip_text("Chosen as a Best Move\nTactic: fork")
        self.assertIn("white-space: nowrap", html)
        self.assertIn("Chosen as a Best Move", html)
        self.assertIn("Tactic: fork", html)


if __name__ == "__main__":
    unittest.main()

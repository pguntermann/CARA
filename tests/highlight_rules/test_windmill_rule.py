"""Unit tests for WindmillRule."""

import unittest

from app.models.moveslist_model import MoveData
from app.services.game_highlights.rules.windmill_rule import WindmillRule
from tests.highlight_rules.helpers import evaluate_rule_sequence, find_highlights


def _row(
    move_number: int,
    *,
    white_move: str = "",
    white_capture: str = "",
    black_move: str = "",
    black_capture: str = "",
    eval_white: str = "",
    eval_black: str = "",
) -> MoveData:
    return MoveData(
        move_number=move_number,
        white_move=white_move,
        white_capture=white_capture,
        black_move=black_move,
        black_capture=black_capture,
        eval_white=eval_white,
        eval_black=eval_black,
        cpl_white="0" if white_move else "",
        cpl_black="0" if black_move else "",
    )


class TestWindmillRule(unittest.TestCase):
    """Windmill: 3+ consecutive check-captures by the same side."""

    def test_should_match_when_white_has_three_check_captures_in_a_row(self):
        moves = [
            _row(10, white_move="Rxe7+", white_capture="p", black_move="Kf8", eval_white="+1.0"),
            _row(11, white_move="Rxf7+", white_capture="p", black_move="Kg8", eval_white="+2.0"),
            _row(12, white_move="Rxg7+", white_capture="p", black_move="Kh8", eval_white="+3.0"),
        ]
        highlights = evaluate_rule_sequence(WindmillRule({}), moves)
        matching = [
            h
            for h in highlights
            if h.rule_type == "windmill" and h.is_white
        ]
        self.assertTrue(matching, "Expected a white windmill after three check-captures")
        self.assertEqual(matching[0].move_number, 10)
        self.assertEqual(matching[0].move_number_end, 12)
        self.assertIn("windmill", matching[0].description.lower())

    def test_should_not_match_when_only_two_check_captures_occur(self):
        moves = [
            _row(10, white_move="Rxe7+", white_capture="p", black_move="Kf8", eval_white="+1.0"),
            _row(11, white_move="Rxf7+", white_capture="p", black_move="Kg8", eval_white="+2.0"),
            _row(12, white_move="Kg2", black_move="Kh7", eval_white="+2.0"),
        ]
        highlights = evaluate_rule_sequence(WindmillRule({}), moves)
        matching = find_highlights(highlights, move_number=10, rule_type="windmill", side="white")
        self.assertFalse(
            matching,
            "Two check-captures are not enough for a windmill highlight",
        )


if __name__ == "__main__":
    unittest.main()

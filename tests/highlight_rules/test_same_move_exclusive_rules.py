"""Unit tests for same-move exclusive highlight groups."""

import unittest

from app.services.game_highlights.base_rule import GameHighlight
from app.services.game_highlights.highlight_detector import HighlightDetector


def _h(rule_type: str, priority: int, description: str = "") -> GameHighlight:
    return GameHighlight(
        move_number=23,
        is_white=True,
        move_notation="23. Rd7",
        description=description or rule_type,
        priority=priority,
        rule_type=rule_type,
    )


class TestSameMoveExclusiveRules(unittest.TestCase):
    """Exclusive sibling rule_types keep the higher-priority highlight."""

    def test_battery_suppresses_doubled_on_open_file(self):
        # Priority-sorted like combine_same_move_highlights.
        highlights = [
            _h("battery", 35, "White created a battery on the d file"),
            _h("doubled_on_open_file", 28, "White doubled on the open d-file"),
        ]
        kept = HighlightDetector._prefer_exclusive_same_move_rules(highlights)
        types = [h.rule_type for h in kept]
        self.assertEqual(types, ["battery"])

    def test_fork_suppresses_skewer(self):
        highlights = [
            _h("fork", 45),
            _h("skewer", 40),
        ]
        kept = HighlightDetector._prefer_exclusive_same_move_rules(highlights)
        self.assertEqual([h.rule_type for h in kept], ["fork"])

    def test_captured_undefended_suppresses_tactical_resource(self):
        # Even if tactical_resource has higher priority (clearly best = 28),
        # an undefended capture should win the exclusive group.
        highlights = [
            _h("tactical_resource", 28, "White found a clearly best tactical resource"),
            _h("captured_undefended_piece", 26, "White captured an undefended pawn"),
        ]
        kept = HighlightDetector._prefer_exclusive_same_move_rules(highlights)
        self.assertEqual([h.rule_type for h in kept], ["captured_undefended_piece"])

    def test_tactical_sequence_suppresses_forcing_combination_and_resource(self):
        highlights = [
            _h("forcing_combination", 45),
            _h("tactical_sequence", 42),
            _h("tactical_resource", 25),
        ]
        kept = HighlightDetector._prefer_exclusive_same_move_rules(highlights)
        self.assertEqual([h.rule_type for h in kept], ["tactical_sequence"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for TempoGainRule."""

import unittest

from app.services.game_highlights.rules.tempo_gain_rule import TempoGainRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestTempoGainRule(unittest.TestCase):
    """Tempo gain: good threatening move followed by a poor opponent reply."""

    def test_should_match_when_attack_threat_gets_poor_reply(self):
        # 3. Bb5 attacks the knight; Black's inaccurate a6 spends the tempo poorly.
        moves = moves_from_pgn(
            "e4 e5 Nf3 Nc6 Bb5 a6",
            analysis={3: {"white": {"cpl": "5"}, "black": {"cpl": "80"}}},
        )
        highlights = evaluate_rule(TempoGainRule({}), moves, move_number=3)
        matching = find_highlights(
            highlights, move_number=3, rule_type="tempo_gain", side="white"
        )
        self.assertTrue(matching, "Expected tempo gain on 3. Bb5")
        self.assertIn("tempo", matching[0].description.lower())

    def test_should_not_match_when_opponent_replies_well(self):
        moves = moves_from_pgn(
            "e4 e5 Nf3 Nc6 Bb5 a6",
            analysis={3: {"white": {"cpl": "5"}, "black": {"cpl": "20"}}},
        )
        highlights = evaluate_rule(TempoGainRule({}), moves, move_number=3)
        matching = find_highlights(
            highlights, move_number=3, rule_type="tempo_gain", side="white"
        )
        self.assertFalse(
            matching,
            "Tempo gain should not fire when the opponent's reply CPL is only 20",
        )

    def test_should_not_match_when_move_only_collects_material(self):
        # Capturing the queen wins material; it does not leave a new threat.
        fen = "rn2k1r1/1b1p1p2/1q1bpn2/p1PP3p/2B1P3/2P1BN2/1PQN1PPP/R4RK1 w q - 1 16"
        moves = moves_from_pgn(
            "cxb6 exd5",
            starting_fen=fen,
            analysis={
                16: {
                    "white": {"cpl": "0", "eval": "+8.2"},
                    "black": {"cpl": "83", "eval": "+9.1"},
                },
            },
        )
        highlights = evaluate_rule(TempoGainRule({}), moves, move_number=16)
        matching = find_highlights(
            highlights, move_number=16, rule_type="tempo_gain", side="white"
        )
        self.assertFalse(
            matching,
            "Collecting a forked queen should not count as gaining a tempo",
        )

    def test_should_not_match_when_poor_reply_ignores_the_threat(self):
        # Rf4 attacks Nf5, but Black's Bxf3 ignores that and takes elsewhere.
        moves = moves_from_pgn(
            "Rf4 Bxf3",
            starting_fen="r7/2p1kpb1/2b3pr/p3Pn2/2N1R2P/5N2/PPP2P1R/2K5 w - - 3 24",
            analysis={
                24: {
                    "white": {"cpl": "18", "eval": "-5.1"},
                    "black": {"cpl": "86", "eval": "-4.2"},
                },
            },
        )
        highlights = evaluate_rule(TempoGainRule({}), moves, move_number=24)
        matching = find_highlights(
            highlights, move_number=24, rule_type="tempo_gain", side="white"
        )
        self.assertFalse(
            matching,
            "An inaccurate reply that ignores the threatened piece is not a tempo gain",
        )


if __name__ == "__main__":
    unittest.main()

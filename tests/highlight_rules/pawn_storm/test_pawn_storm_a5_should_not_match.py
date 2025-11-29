"""Test case: Pawn Storm a5 - should NOT detect pawn storm on move 11."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_pawn_storm_a5_should_not_match():
    """Test that a5 (move 11) is NOT detected as a pawn storm."""
    print(f"\n{'='*80}")
    print("TEST: Pawn Storm a5 (move 11) - Should NOT detect pawn storm")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("pawn_storm_a5_should_not_match.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check that no pawn storm highlight exists
    matching = find_highlights(highlights, move_number=11, rule_type="pawn_storm", side="black")
    
    if matching:
        print("[FAIL] Move 11: Pawn storm incorrectly detected")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        explain_failure(11, "pawn_storm", "black", game_data, highlights)
    
    assert not matching, "Pawn storm should not be detected for move 11...a5"


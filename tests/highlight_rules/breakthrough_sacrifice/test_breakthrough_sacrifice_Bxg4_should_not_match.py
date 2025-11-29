"""Test case: Breakthrough Sacrifice Bxg4 - should NOT detect sacrifice on move 25."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_breakthrough_sacrifice_Bxg4_should_not_match():
    """Test that Bxg4 (move 25) is NOT detected as a breakthrough sacrifice.
    
    The move 25.Bxg4 is part of a forced tactical sequence (Bxg4, Ne6+, Nxd8)
    that wins material. White never gives up material without immediately
    getting it back - this is a tactical sequence, not a sacrifice.
    """
    print(f"\n{'='*80}")
    print("TEST: Breakthrough Sacrifice Bxg4 (move 25) - Should NOT detect sacrifice")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("sacrifice_breakthrough_should_not_match_Bxg4.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check that no breakthrough_sacrifice highlight exists for this move
    matching = find_highlights(highlights, move_number=25, rule_type="breakthrough_sacrifice", side="white")
    
    if matching:
        print("[FAIL] Move 25: Breakthrough sacrifice incorrectly detected")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        explain_failure(25, "breakthrough_sacrifice", "white", game_data, highlights)
    
    assert not matching, "Breakthrough sacrifice should not be detected for move 25.Bxg4"


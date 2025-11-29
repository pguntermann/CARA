"""Test case: Knight Outpost Nxd4 - should NOT detect knight outpost on move 9."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_knight_outpost_Nxd4_should_not_match():
    """Test that black's Nxd4 (move 9) is NOT detected as a knight outpost."""
    print(f"\n{'='*80}")
    print("TEST: Knight Outpost Nxd4 (move 9, black) - Should NOT detect knight outpost")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("knight_outpost_should_not_match_...Nxd4.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check that no knight_outpost highlight exists for black's move on move 9
    matching = find_highlights(highlights, move_number=9, rule_type="knight_outpost", side="black")
    
    if matching:
        print("[FAIL] Move 9: Knight outpost incorrectly detected for black's Nxd4")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        explain_failure(9, "knight_outpost", "black", game_data, highlights)
    
    assert not matching, "Knight outpost should not be detected for move 9...Nxd4 (black)"


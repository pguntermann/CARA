"""Test case: Decoy Bc4 - should detect decoy on move 17."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_decoy_bc4_should_match():
    """Test that Bc4 (move 17) is detected as a decoy."""
    print(f"\n{'='*80}")
    print("TEST: Decoy Bc4 (move 17) - Should detect decoy")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("decoy_bc4_should_match.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check for expected highlight
    matching = find_highlights(highlights, move_number=17, rule_type="decoy", side="white")
    
    if not matching:
        print("[FAIL] Move 17: Decoy NOT detected")
        explain_failure(17, "decoy", "white", game_data, highlights)
    
    assert matching, "Decoy should be detected for move 17.Bc4"


"""Test case: Blunder Re2 - should NOT detect blundered piece on move 35."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_blunder_Re2_should_not_match():
    """Test that Re2 (move 35) is NOT detected as a blundered piece."""
    print(f"\n{'='*80}")
    print("TEST: Blunder Re2 (move 35) - Should NOT detect blundered piece")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("blunder_Re2_should_not_match.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check that no blundered_piece highlight exists for this move
    matching = find_highlights(highlights, move_number=35, rule_type="blundered_piece", side="white")
    
    if matching:
        print("[FAIL] Move 35: Blundered piece incorrectly detected")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        explain_failure(35, "blundered_piece", "white", game_data, highlights)
    
    assert not matching, "Blundered piece should not be detected for move 35.Re2"


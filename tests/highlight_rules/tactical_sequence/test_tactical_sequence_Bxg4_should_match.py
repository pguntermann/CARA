"""Test case: Tactical Sequence Bxg4 - should detect tactical sequence on move 25."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_tactical_sequence_Bxg4_should_match():
    """Test that Bxg4 (move 25) is detected as a tactical sequence.
    
    The move 25.Bxg4 is part of a forced tactical sequence (Bxg4, Ne6+, Nxd8)
    that wins material. White never gives up material without immediately
    getting it back - this is a tactical sequence, not a sacrifice.
    """
    print(f"\n{'='*80}")
    print("TEST: Tactical Sequence Bxg4 (move 25) - Should detect tactical sequence")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("tactical_sequence_Bxg4_should_match.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check for expected highlight
    matching = find_highlights(highlights, move_number=25, rule_type="tactical_sequence", side="white")
    
    if not matching:
        print("[FAIL] Move 25: Tactical sequence NOT detected")
        explain_failure(25, "tactical_sequence", "white", game_data, highlights)
    
    assert matching, "Tactical sequence should be detected for move 25.Bxg4"


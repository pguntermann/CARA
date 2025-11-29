"""Test case: Material Imbalance Qxc5 - should NOT detect rook for minor piece trade on move 30 because it's a Best Move."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_material_imbalance_qxc5_should_not_match():
    """Test that Qxc5 (move 30) is NOT detected as a material imbalance because it's marked as Best Move.
    
    The rule now filters out Best Move assessments since those are positional sacrifices,
    not material imbalances.
    """
    print(f"\n{'='*80}")
    print("TEST: Material Imbalance Qxc5 (move 30) - Should NOT detect (Best Move filter)")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("material_imbalance_qxc5_should_not_match.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check that no highlight was generated (should be filtered out)
    matching = find_highlights(highlights, move_number=30, rule_type="material_imbalance", side="black")
    
    if matching:
        print("[FAIL] Move 30: Material imbalance incorrectly detected (should be filtered)")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        explain_failure(30, "material_imbalance", "black", game_data, highlights)
    
    assert not matching, "Material imbalance should not be detected for move 30.Qxc5 (Best Move filter)"


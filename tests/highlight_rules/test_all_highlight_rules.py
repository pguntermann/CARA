"""Run all highlight rule test cases."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import all test cases
from tests.highlight_rules.decoy.test_decoy_bc4_should_match import test_decoy_bc4_should_match
from tests.highlight_rules.material_imbalance.test_material_imbalance_qxc5_should_not_match import test_material_imbalance_qxc5_should_not_match
from tests.highlight_rules.pawn_storm.test_pawn_storm_a5_should_not_match import test_pawn_storm_a5_should_not_match
from tests.highlight_rules.blunder.test_blunder_Re2_should_not_match import test_blunder_Re2_should_not_match
from tests.highlight_rules.interference.test_interference_Bxb7_should_not_match import test_interference_Bxb7_should_not_match
from tests.highlight_rules.interference.test_interference_Qd3_should_not_match import test_interference_Qd3_should_not_match
from tests.highlight_rules.breakthrough_sacrifice.test_breakthrough_sacrifice_Bxg4_should_not_match import test_breakthrough_sacrifice_Bxg4_should_not_match
from tests.highlight_rules.tactical_sequence.test_tactical_sequence_Bxg4_should_match import test_tactical_sequence_Bxg4_should_match
from tests.highlight_rules.knight_outpost.test_knight_outpost_Nxd4_should_not_match import test_knight_outpost_Nxd4_should_not_match


def run_all_tests():
    """Run all highlight rule tests."""
    print(f"\n{'='*80}")
    print("HIGHLIGHT RULES TEST SUITE")
    print(f"{'='*80}\n")
    
    tests = [
        ("Decoy Bc4 (should match)", test_decoy_bc4_should_match),
        ("Material Imbalance Qxc5 (should not match - Best Move filter)", test_material_imbalance_qxc5_should_not_match),
        ("Pawn Storm a5 (should not match)", test_pawn_storm_a5_should_not_match),
        ("Blunder Re2 (should not match - blundered piece)", test_blunder_Re2_should_not_match),
        ("Interference Bxb7 (should not match - capture removes defender, not interference)", test_interference_Bxb7_should_not_match),
        ("Interference Qd3 (should not match - improves coordination without blocking lines)", test_interference_Qd3_should_not_match),
        ("Breakthrough Sacrifice Bxg4 (should not match - forced tactical sequence, not sacrifice)", test_breakthrough_sacrifice_Bxg4_should_not_match),
        ("Tactical Sequence Bxg4 (should match - forced tactical sequence that wins material)", test_tactical_sequence_Bxg4_should_match),
        ("Knight Outpost Nxd4 (should not match - capture move, not an outpost)", test_knight_outpost_Nxd4_should_not_match),
        # Add more tests here as they are created
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = test_func()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")
    print(f"{'='*80}\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)


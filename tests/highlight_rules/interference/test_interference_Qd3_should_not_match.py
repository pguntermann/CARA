"""Test case: Interference Qd3 - should NOT be flagged as interference."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))  # noqa

from tests.highlight_rules.helpers import (  # pylint: disable=wrong-import-position
    load_test_game,
    run_highlight_detection,
    find_highlights,
    explain_failure,
)


def test_interference_Qd3_should_not_match():
    """Move 29.Qd3 merely improves coordination and must not be flagged."""
    print(f"\n{'='*80}")
    print("TEST: Interference Qd3 (move 29) - Should NOT detect interference")
    print(f"{'='*80}")

    game_data = load_test_game("interference_should_not_match_Qd3.json")
    highlights = run_highlight_detection(game_data)
    matching = find_highlights(highlights, move_number=29, rule_type="interference", side="white")

    if matching:
        print("[FAIL] Move 29: Interference incorrectly detected")
        for highlight in matching:
            print(f"      Description: {highlight.description}")
            print(f"      Priority: {highlight.priority}")
        explain_failure(29, "interference", "white", game_data, highlights)

    assert not matching, "Interference should not be detected for move 29.Qd3"


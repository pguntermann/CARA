# Highlight Rules Testing Framework

This directory contains the testing framework for game highlight detection rules.

## Structure

```
tests/highlight_rules/
├── games/                          # JSON game files (pretty-printed)
│   ├── decoy_bc4_should_match.json
│   └── ...
├── decoy/                          # Decoy rule tests
│   ├── test_decoy_bc4_should_match.py
│   └── ...
├── fork/                           # Fork rule tests
├── pin/                            # Pin rule tests
├── helpers.py                      # Shared test utilities
├── test_all_highlight_rules.py     # Combined test runner
└── README.md                       # This file
```

## Test File Naming Convention

- **Should match**: `test_<rule>_<description>_should_match.py`
- **Should not match**: `test_<rule>_<description>_should_not_match.py`

Example:
- `test_decoy_bc4_should_match.py` - Tests that move 17. Bc4 is detected as a decoy
- `test_decoy_rc8_should_not_match.py` - Tests that move 20. ...Rc8 is NOT detected as a decoy

## Game Data Format

Game files are stored as pretty-printed JSON in `games/`. Each file contains a full array of `MoveData` objects that can be copied directly from the application.

### Creating a Test Game File

1. Copy the full game JSON from the application
2. Save it as `games/<descriptive_name>.json`
3. Ensure it's pretty-printed (not minified)

## Writing a Test Case

### Example: Should Match Test

```python
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
    
    if matching:
        print(f"[PASS] Move 17: Decoy detected")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        return True
    else:
        print(f"[FAIL] Move 17: Decoy NOT detected")
        explain_failure(17, "decoy", "white", game_data, highlights)
        return False


if __name__ == "__main__":
    success = test_decoy_bc4_should_match()
    sys.exit(0 if success else 1)
```

### Example: Should Not Match Test

```python
"""Test case: Decoy Rc8 - should NOT detect decoy on move 20."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection, 
    find_highlights, explain_failure
)


def test_decoy_rc8_should_not_match():
    """Test that Rc8 (move 20) is NOT detected as a decoy."""
    print(f"\n{'='*80}")
    print("TEST: Decoy Rc8 (move 20) - Should NOT detect decoy")
    print(f"{'='*80}")
    
    # Load test game
    game_data = load_test_game("decoy_rc8_should_not_match.json")
    
    # Run detection
    highlights = run_highlight_detection(game_data)
    
    # Check that no decoy highlight exists
    matching = find_highlights(highlights, move_number=20, rule_type="decoy", side="black")
    
    if not matching:
        print(f"[PASS] Move 20: Decoy correctly NOT detected")
        return True
    else:
        print(f"[FAIL] Move 20: Decoy incorrectly detected")
        for h in matching:
            print(f"      Description: {h.description}")
            print(f"      Priority: {h.priority}")
        explain_failure(20, "decoy", "black", game_data, highlights)
        return False


if __name__ == "__main__":
    success = test_decoy_rc8_should_not_match()
    sys.exit(0 if success else 1)
```

## Helper Functions

### `load_test_game(filename: str) -> List[MoveData]`

Loads a test game from JSON file in `games/` directory and converts to `MoveData` list.

### `run_highlight_detection(moves: List[MoveData]) -> List[GameHighlight]`

Runs the full highlight detection pipeline on a list of moves and returns all highlights.

### `find_highlights(highlights: List[GameHighlight], move_number: int, rule_type: str, side: Optional[str] = None) -> List[GameHighlight]`

Finds highlights matching specific criteria:
- `move_number`: Move number to match
- `rule_type`: Rule type (e.g., "decoy", "fork", "pin")
- `side`: Optional side filter ("white" or "black")

### `explain_failure(move_number: int, rule_type: str, side: str, moves: List[MoveData], highlights: List[GameHighlight]) -> None`

Provides detailed failure analysis for debugging, including:
- Move details (CPL, assessment, material, capture)
- FEN positions
- Follow-up moves
- All highlights found for the move
- Material analysis (for tactical rules)

## Running Tests

### Run Individual Test

```bash
python tests/highlight_rules/decoy/test_decoy_bc4_should_match.py
```

### Run All Tests

```bash
python tests/highlight_rules/test_all_highlight_rules.py
```

## Adding New Tests

1. Create a new game file in `games/` (if needed)
2. Create a test file in the appropriate rule subfolder (e.g., `decoy/`, `fork/`)
3. Add the test function to `test_all_highlight_rules.py`

Example:
```python
from tests.highlight_rules.decoy.test_decoy_rc8_should_not_match import test_decoy_rc8_should_not_match

tests = [
    ...
    ("Decoy Rc8 (should not match)", test_decoy_rc8_should_not_match),
]
```

## Failure Debugging

When a test fails, `explain_failure()` provides comprehensive debugging information:
- Move details and context
- Material calculations
- FEN positions
- Follow-up moves
- All highlights found
- Comparison with expected values

This information should be sufficient to trace bugs quickly without needing to add additional debug output to the rule code itself.


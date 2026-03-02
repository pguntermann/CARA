# Test suite

All tests use the standard library `unittest` and are discoverable with:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run from the **project root** so that `app` is on the import path.

## Folder and filename scheme

| Folder | Purpose | Naming |
|--------|---------|--------|
| **tests/pgn/** | PGN formatter, filtering, removal, highlighting | `test_<topic>.py` (e.g. `test_formatter.py`, `test_filter_and_remove.py`) |
| **tests/positional_heatmap/** | Positional heatmap evaluation rules | `test_rules_comprehensive.py` |
| **tests/highlight_rules/** | Game highlight rules (decoy, blunder, etc.) | One subfolder per rule; `test_<rule>_<case>.py` (e.g. `test_decoy_bc4_should_match.py`) |

- All test modules match the pattern **`test_*.py`** so `unittest discover` finds them.
- One test **file** per feature or rule; one **class** per test case group; method names **`test_*`** for each test.

## Running a subset

- Only PGN tests:  
  `python -m unittest discover -s tests/pgn -p "test_*.py" -v`
- Only positional heatmap:  
  `python -m unittest discover -s tests/positional_heatmap -p "test_*.py" -v`
- Only highlight rules:  
  `python -m unittest discover -s tests/highlight_rules -p "test_*.py" -v`  
  or run `python tests/highlight_rules/test_all_highlight_rules.py`

## Qt / CI

- **tests/pgn/test_highlighting.py** depends on Qt and is skipped unless `RUN_QT_TESTS=1`; it is always skipped when `CI=true` (e.g. in GitHub Actions).

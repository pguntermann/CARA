"""Run all highlight rule tests via unittest.

When run directly, discovers and runs only tests under tests/highlight_rules/.
All tests are also discovered by: python -m unittest discover -s tests -p "test_*.py"
"""

import os
import sys
import unittest

# Project root on path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


if __name__ == "__main__":
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(start_dir))
    suite = loader.discover(start_dir, pattern="test_*.py", top_level_dir=project_root)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

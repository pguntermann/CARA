"""Tests for single-pass bulk plan worker."""

import unittest

from app.controllers.bulk_operations_controller import (
    MODE_ADD_TAG,
    MODE_CLEAN,
    MODE_OVERWRITE,
    MODE_REMOVE_TAGS,
    BulkOperation,
)
from app.services.bulk_operation_stats import BulkProcessingOutcome
from app.services.bulk_plan_service import (
    _process_game_for_plan,
    plan_requires_position_reindex,
    plan_step_from_operation,
)


SAMPLE_PGN = """[Event "Test"]
[Site "Nowhere"]
[Date "2024.01.01"]
[Round "1"]
[White "A"]
[Black "B"]
[Result "1-0"]
[ECO "C20"]
[Annotator "Old"]

1. e4 e5 2. Nf3 {comment} Nc6 1-0
"""


def _steps(*ops: BulkOperation):
    return tuple(plan_step_from_operation(op) for op in ops)


class TestBulkPlanService(unittest.TestCase):
    def test_plan_ops_never_require_position_reindex(self) -> None:
        header_and_clean = _steps(
            BulkOperation(mode=MODE_OVERWRITE, tags=("White",), replace_text="A"),
            BulkOperation(mode=MODE_CLEAN, remove_comments=True, remove_variations=True),
        )
        self.assertFalse(plan_requires_position_reindex(header_and_clean))
        variations_only = _steps(
            BulkOperation(mode=MODE_CLEAN, remove_variations=True),
        )
        self.assertFalse(plan_requires_position_reindex(variations_only))

    def test_plan_remove_then_add_recreates_tag(self) -> None:
        steps = _steps(
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Annotator",)),
            BulkOperation(mode=MODE_ADD_TAG, tags=("Annotator",), replace_text="New"),
        )
        new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
        self.assertEqual(outcome, BulkProcessingOutcome.UPDATED)
        self.assertIsNotNone(new_pgn)
        assert new_pgn is not None
        self.assertIn('[Annotator "New"]', new_pgn)
        self.assertNotIn('[Annotator "Old"]', new_pgn)

    def test_plan_overwrite_then_remove(self) -> None:
        steps = _steps(
            BulkOperation(mode=MODE_OVERWRITE, tags=("ECO",), replace_text="B20"),
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("ECO",)),
        )
        new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
        self.assertEqual(outcome, BulkProcessingOutcome.UPDATED)
        self.assertIsNotNone(new_pgn)
        assert new_pgn is not None
        self.assertTrue("ECO" not in new_pgn or '[ECO "' not in new_pgn)
        self.assertEqual(updates.get("eco"), "")

    def test_plan_noop_is_skipped(self) -> None:
        steps = _steps(
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("NonexistentTag",)),
        )
        new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
        self.assertEqual(outcome, BulkProcessingOutcome.SKIPPED)
        self.assertIsNone(new_pgn)

    def test_plan_clean_removes_comments(self) -> None:
        steps = _steps(
            BulkOperation(mode=MODE_CLEAN, remove_comments=True),
        )
        new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
        self.assertEqual(outcome, BulkProcessingOutcome.UPDATED)
        self.assertIsNotNone(new_pgn)
        assert new_pgn is not None
        self.assertNotIn("{comment}", new_pgn)

    def test_plan_header_then_clean_keeps_header_change(self) -> None:
        steps = _steps(
            BulkOperation(mode=MODE_OVERWRITE, tags=("Annotator",), replace_text="X"),
            BulkOperation(mode=MODE_CLEAN, remove_comments=True),
        )
        new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
        self.assertEqual(outcome, BulkProcessingOutcome.UPDATED)
        self.assertIsNotNone(new_pgn)
        assert new_pgn is not None
        self.assertIn('[Annotator "X"]', new_pgn)
        self.assertNotIn("{comment}", new_pgn)


if __name__ == "__main__":
    unittest.main()

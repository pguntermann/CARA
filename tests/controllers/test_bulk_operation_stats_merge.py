"""Tests for multi-step bulk stats merging (plan + Smart Update)."""

import unittest
from unittest.mock import MagicMock

from app.controllers.bulk_operations_controller import BulkOperationsController
from app.services.bulk_operation_stats import BulkOperationStats


class TestMergeStepStats(unittest.TestCase):
    def _controller(self, n: int) -> BulkOperationsController:
        ctrl = BulkOperationsController(
            {},
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        ctrl._games_in_scope = [MagicMock() for _ in range(n)]
        return ctrl

    def test_eco_skips_do_not_erase_plan_updates(self) -> None:
        ctrl = self._controller(3)
        g1, g2, g3 = (id(g) for g in ctrl._games_in_scope)
        plan = BulkOperationStats(
            True, 3, 3, 0, 0,
            updated_game_ids=(g1, g2, g3),
        )
        eco = BulkOperationStats(
            True, 3, 1, 0, 2,
            updated_game_ids=(g1,),  # only one ECO change
        )
        merged = ctrl._merge_step_stats([plan, eco])
        self.assertEqual(merged.games_processed, 3)
        self.assertEqual(merged.games_updated, 3)
        self.assertEqual(merged.games_failed, 0)
        self.assertEqual(merged.games_skipped, 0)

    def test_skipped_only_when_never_updated(self) -> None:
        ctrl = self._controller(3)
        g1, g2, g3 = (id(g) for g in ctrl._games_in_scope)
        plan = BulkOperationStats(
            True, 3, 2, 0, 1,
            updated_game_ids=(g1, g2),
        )
        eco = BulkOperationStats(
            True, 3, 0, 0, 3,
            updated_game_ids=(),
        )
        merged = ctrl._merge_step_stats([plan, eco])
        self.assertEqual(merged.games_updated, 2)
        self.assertEqual(merged.games_skipped, 1)
        self.assertNotIn(g3, merged.updated_game_ids)


if __name__ == "__main__":
    unittest.main()

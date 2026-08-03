"""Tests for bulk operation plan serialize/deserialize helpers."""

from __future__ import annotations

import unittest

from app.controllers.bulk_operations_controller import (
    MODE_CLEAN,
    MODE_FIND_REPLACE,
    MODE_OVERWRITE,
    BulkOperation,
)
from app.utils.bulk_operation_plan import (
    bulk_operation_from_dict,
    bulk_operation_to_dict,
    normalize_plan_name,
    plan_operations_from_dicts,
    plan_operations_to_dicts,
)


class TestBulkOperationPlanSerialization(unittest.TestCase):
    def test_round_trip_find_replace(self) -> None:
        op = BulkOperation(
            mode=MODE_FIND_REPLACE,
            tags=("White", "Black"),
            find_text="Smith",
            replace_text="Smyth",
            case_sensitive=True,
            use_regex=False,
        )
        restored = bulk_operation_from_dict(bulk_operation_to_dict(op))
        self.assertEqual(restored, op)

    def test_round_trip_clean(self) -> None:
        op = BulkOperation(
            mode=MODE_CLEAN,
            remove_comments=True,
            remove_variations=True,
        )
        restored = bulk_operation_from_dict(bulk_operation_to_dict(op))
        self.assertEqual(restored, op)

    def test_rejects_invalid_operation(self) -> None:
        self.assertIsNone(bulk_operation_from_dict({"mode": MODE_FIND_REPLACE, "tags": []}))
        self.assertIsNone(bulk_operation_from_dict("not-a-dict"))
        self.assertIsNone(bulk_operation_from_dict({"mode": "nope"}))

    def test_plan_list_round_trip(self) -> None:
        ops = [
            BulkOperation(mode=MODE_OVERWRITE, tags=("Event",), replace_text="Open"),
            BulkOperation(mode=MODE_CLEAN, remove_annotations=True),
        ]
        raw = plan_operations_to_dicts(ops)
        restored, error = plan_operations_from_dicts(raw)
        self.assertIsNone(error)
        self.assertEqual(restored, ops)

    def test_plan_list_rejects_empty_and_corrupt(self) -> None:
        ops, err = plan_operations_from_dicts([])
        self.assertEqual(ops, [])
        self.assertIsNotNone(err)

        ops, err = plan_operations_from_dicts({"not": "a list"})
        self.assertEqual(ops, [])
        self.assertIsNotNone(err)

        ops, err = plan_operations_from_dicts([{"mode": MODE_CLEAN}])
        self.assertEqual(ops, [])
        self.assertIsNotNone(err)

    def test_normalize_plan_name(self) -> None:
        self.assertEqual(normalize_plan_name("  Cleanup  "), "Cleanup")
        self.assertEqual(normalize_plan_name("   "), "")


if __name__ == "__main__":
    unittest.main()

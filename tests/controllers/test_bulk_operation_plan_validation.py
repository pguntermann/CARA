"""Tests for bulk operation plan conflict validation."""

import unittest

from app.controllers.bulk_operations_controller import (
    MODE_ADD_TAG,
    MODE_CLEAN,
    MODE_COPY,
    MODE_FIND_REPLACE,
    MODE_OVERWRITE,
    MODE_REMOVE_TAGS,
    BulkOperation,
    format_bulk_plan_issues,
    validate_bulk_operation_plan,
)


class TestBulkOperationPlanValidation(unittest.TestCase):
    def test_remove_then_overwrite_same_tag_is_conflict(self) -> None:
        ops = [
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("WhiteElo",)),
            BulkOperation(mode=MODE_OVERWRITE, tags=("WhiteElo",), replace_text="2700"),
        ]
        issues = validate_bulk_operation_plan(ops)
        self.assertEqual(len(issues), 1)
        self.assertIn("removed", issues[0].message)
        self.assertIn("WhiteElo", issues[0].message)

    def test_remove_then_add_same_tag_is_ok(self) -> None:
        ops = [
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Annotator",)),
            BulkOperation(mode=MODE_ADD_TAG, tags=("Annotator",), replace_text="CARA"),
        ]
        self.assertEqual(validate_bulk_operation_plan(ops), [])

    def test_remove_then_copy_from_source_is_conflict(self) -> None:
        ops = [
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Date",)),
            BulkOperation(mode=MODE_COPY, tags=("EventDate",), source_tag="Date"),
        ]
        issues = validate_bulk_operation_plan(ops)
        self.assertEqual(len(issues), 1)
        self.assertIn("copies from", issues[0].message)
        self.assertIn("Date", issues[0].message)

    def test_double_overwrite_warns_about_superseded_write(self) -> None:
        ops = [
            BulkOperation(mode=MODE_OVERWRITE, tags=("White",), replace_text="A"),
            BulkOperation(mode=MODE_OVERWRITE, tags=("White",), replace_text="B"),
        ]
        issues = validate_bulk_operation_plan(ops)
        self.assertEqual(len(issues), 1)
        self.assertIn("overwritten", issues[0].message)

    def test_remove_result_then_smart_update_is_conflict(self) -> None:
        ops = [BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Result",))]
        issues = validate_bulk_operation_plan(ops, has_result_update=True)
        self.assertEqual(len(issues), 1)
        self.assertIn("Smart Update (Result)", issues[0].message)

    def test_overwrite_result_then_smart_update_warns(self) -> None:
        ops = [BulkOperation(mode=MODE_OVERWRITE, tags=("Result",), replace_text="1-0")]
        issues = validate_bulk_operation_plan(ops, has_result_update=True)
        self.assertEqual(len(issues), 1)
        self.assertIn("Smart Update (Result)", issues[0].message)
        self.assertIn("already modified", issues[0].message)

    def test_clean_does_not_conflict_with_header_ops(self) -> None:
        ops = [
            BulkOperation(
                mode=MODE_CLEAN,
                remove_comments=True,
                remove_non_standard_tags=True,
            ),
            BulkOperation(mode=MODE_OVERWRITE, tags=("ECO",), replace_text="C20"),
        ]
        self.assertEqual(validate_bulk_operation_plan(ops), [])

    def test_find_replace_after_remove_is_conflict(self) -> None:
        ops = [
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Site",)),
            BulkOperation(
                mode=MODE_FIND_REPLACE,
                tags=("Site",),
                find_text="Online",
                replace_text="Internet",
            ),
        ]
        issues = validate_bulk_operation_plan(ops)
        self.assertEqual(len(issues), 1)
        self.assertIn("Site", issues[0].message)

    def test_format_bulk_plan_issues_includes_continue_prompt(self) -> None:
        ops = [
            BulkOperation(mode=MODE_REMOVE_TAGS, tags=("ECO",)),
            BulkOperation(mode=MODE_OVERWRITE, tags=("ECO",), replace_text="B20"),
        ]
        text = format_bulk_plan_issues(validate_bulk_operation_plan(ops))
        self.assertIn("potential conflicts", text)
        self.assertIn("Continue anyway?", text)
        self.assertIn("• ", text)


if __name__ == "__main__":
    unittest.main()

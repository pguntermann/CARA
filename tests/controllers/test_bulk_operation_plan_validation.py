"""Tests for bulk operation plan conflict validation."""

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


def test_remove_then_overwrite_same_tag_is_conflict():
    ops = [
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("WhiteElo",)),
        BulkOperation(mode=MODE_OVERWRITE, tags=("WhiteElo",), replace_text="2700"),
    ]
    issues = validate_bulk_operation_plan(ops)
    assert len(issues) == 1
    assert "removed" in issues[0].message
    assert "WhiteElo" in issues[0].message


def test_remove_then_add_same_tag_is_ok():
    ops = [
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Annotator",)),
        BulkOperation(mode=MODE_ADD_TAG, tags=("Annotator",), replace_text="CARA"),
    ]
    assert validate_bulk_operation_plan(ops) == []


def test_remove_then_copy_from_source_is_conflict():
    ops = [
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Date",)),
        BulkOperation(mode=MODE_COPY, tags=("EventDate",), source_tag="Date"),
    ]
    issues = validate_bulk_operation_plan(ops)
    assert len(issues) == 1
    assert "copies from" in issues[0].message
    assert "Date" in issues[0].message


def test_double_overwrite_warns_about_superseded_write():
    ops = [
        BulkOperation(mode=MODE_OVERWRITE, tags=("White",), replace_text="A"),
        BulkOperation(mode=MODE_OVERWRITE, tags=("White",), replace_text="B"),
    ]
    issues = validate_bulk_operation_plan(ops)
    assert len(issues) == 1
    assert "overwritten" in issues[0].message


def test_remove_result_then_smart_update_is_conflict():
    ops = [BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Result",))]
    issues = validate_bulk_operation_plan(ops, has_result_update=True)
    assert len(issues) == 1
    assert "Smart Update (Result)" in issues[0].message


def test_overwrite_result_then_smart_update_warns():
    ops = [BulkOperation(mode=MODE_OVERWRITE, tags=("Result",), replace_text="1-0")]
    issues = validate_bulk_operation_plan(ops, has_result_update=True)
    assert len(issues) == 1
    assert "Smart Update (Result)" in issues[0].message
    assert "already modified" in issues[0].message


def test_clean_does_not_conflict_with_header_ops():
    ops = [
        BulkOperation(mode=MODE_CLEAN, remove_comments=True, remove_non_standard_tags=True),
        BulkOperation(mode=MODE_OVERWRITE, tags=("ECO",), replace_text="C20"),
    ]
    assert validate_bulk_operation_plan(ops) == []


def test_find_replace_after_remove_is_conflict():
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
    assert len(issues) == 1
    assert "Site" in issues[0].message


def test_format_bulk_plan_issues_includes_continue_prompt():
    ops = [
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("ECO",)),
        BulkOperation(mode=MODE_OVERWRITE, tags=("ECO",), replace_text="B20"),
    ]
    text = format_bulk_plan_issues(validate_bulk_operation_plan(ops))
    assert "potential conflicts" in text
    assert "Continue anyway?" in text
    assert "• " in text

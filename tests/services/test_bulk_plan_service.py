"""Tests for single-pass bulk plan worker."""

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


def test_plan_remove_then_add_recreates_tag():
    steps = _steps(
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("Annotator",)),
        BulkOperation(mode=MODE_ADD_TAG, tags=("Annotator",), replace_text="New"),
    )
    new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
    assert outcome == BulkProcessingOutcome.UPDATED
    assert new_pgn is not None
    assert '[Annotator "New"]' in new_pgn
    assert '[Annotator "Old"]' not in new_pgn


def test_plan_overwrite_then_remove():
    steps = _steps(
        BulkOperation(mode=MODE_OVERWRITE, tags=("ECO",), replace_text="B20"),
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("ECO",)),
    )
    new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
    assert outcome == BulkProcessingOutcome.UPDATED
    assert new_pgn is not None
    assert "ECO" not in new_pgn or '[ECO "' not in new_pgn
    assert updates.get("eco") == ""


def test_plan_noop_is_skipped():
    steps = _steps(
        BulkOperation(mode=MODE_REMOVE_TAGS, tags=("NonexistentTag",)),
    )
    new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
    assert outcome == BulkProcessingOutcome.SKIPPED
    assert new_pgn is None


def test_plan_clean_removes_comments():
    steps = _steps(
        BulkOperation(mode=MODE_CLEAN, remove_comments=True),
    )
    new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
    assert outcome == BulkProcessingOutcome.UPDATED
    assert new_pgn is not None
    assert "{comment}" not in new_pgn


def test_plan_header_then_clean_keeps_header_change():
    steps = _steps(
        BulkOperation(mode=MODE_OVERWRITE, tags=("Annotator",), replace_text="X"),
        BulkOperation(mode=MODE_CLEAN, remove_comments=True),
    )
    new_pgn, updates, outcome = _process_game_for_plan(SAMPLE_PGN, steps)
    assert outcome == BulkProcessingOutcome.UPDATED
    assert new_pgn is not None
    assert '[Annotator "X"]' in new_pgn
    assert "{comment}" not in new_pgn

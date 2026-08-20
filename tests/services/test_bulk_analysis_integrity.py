"""Bulk analysis post-game best-move integrity check."""

from __future__ import annotations

from app.controllers.bulk_analysis_controller import (
    bulk_analysis_dialog_messages,
    format_incomplete_analysis_message,
)
from app.models.database_model import GameData
from app.models.moveslist_model import MoveData
from app.services.bulk_analysis_service import BulkAnalysisService


def _ply(move_number: int, is_white: bool, move_san: str = "") -> dict:
    return {"move_number": move_number, "is_white_move": is_white, "move_san": move_san}


def test_book_and_best_moves_do_not_count() -> None:
    moves = [_ply(1, True, "e4"), _ply(1, False, "e5"), _ply(2, True, "Nf3")]
    analyzed = [
        MoveData(
            1,
            white_move="e4",
            black_move="e5",
            assess_white="Book Move",
            assess_black="Book Move",
        ),
        MoveData(
            2,
            white_move="Nf3",
            assess_white="Best Move",
            best_white="",
        ),
    ]
    assert BulkAnalysisService.count_missing_best_moves(moves, analyzed) == 0


def test_non_best_without_san_counts() -> None:
    moves = [_ply(1, True, "e4"), _ply(1, False, "d5")]
    analyzed = [
        MoveData(
            1,
            white_move="e4",
            black_move="d5",
            assess_white="Best Move",
            assess_black="Inaccuracy",
            best_white="e4",
            best_black="",
        )
    ]
    assert BulkAnalysisService.count_missing_best_moves(moves, analyzed) == 1


def test_skipped_plies_count() -> None:
    moves = [_ply(1, True, "e4"), _ply(1, False, "e5"), _ply(2, True, "Nf3")]
    analyzed = [
        MoveData(
            1,
            white_move="e4",
            black_move="e5",
            assess_white="Good Move",
            assess_black="Good Move",
            best_white="e4",
            best_black="e5",
        )
    ]
    assert BulkAnalysisService.count_missing_best_moves(moves, analyzed) == 1


def test_threshold_from_config() -> None:
    assert BulkAnalysisService.missing_best_move_threshold({}) == 0
    config = {
        "ui": {
            "dialogs": {
                "bulk_analysis_dialog": {
                    "integrity_check": {"max_missing_best_moves": 2}
                }
            }
        }
    }
    assert BulkAnalysisService.missing_best_move_threshold(config) == 2
    assert BulkAnalysisService.missing_best_move_threshold(
        {"ui": {"dialogs": {"bulk_analysis_dialog": {"integrity_check": {"max_missing_best_moves": -3}}}}}
    ) == 0


def test_game_label_format() -> None:
    game = GameData(
        game_number=48,
        white="Kramnik",
        black="Carlsen",
        result="1-0",
        date="1994.??.??",
        moves=39,
    )
    assert (
        BulkAnalysisService.format_game_label(game)
        == "game Nr. 48 Kramnik - Carlsen 1-0 (1994.??.?? - 39 moves)"
    )


def test_integrity_fail_dump_marks_missing_best() -> None:
    game = GameData(
        game_number=48,
        white="Kramnik",
        black="Carlsen",
        result="1-0",
        date="1994.??.??",
        moves=2,
    )
    moves = [_ply(1, True, "e4"), _ply(1, False, "d5")]
    analyzed = [
        MoveData(
            1,
            white_move="e4",
            black_move="d5",
            assess_white="Best Move",
            assess_black="Inaccuracy",
            best_white="e4",
            best_black="",
        )
    ]
    dump = BulkAnalysisService.format_integrity_fail_dump(game, moves, analyzed)
    assert "game Nr. 48" in dump
    assert "[MISSING_BEST]" in dump
    assert "1... d5" in dump


def test_incomplete_message_uses_html_and_game_label() -> None:
    game = GameData(
        game_number=48,
        white="Kramnik",
        black="Carlsen <test>",
        result="1-0",
        date="1994.??.??",
        moves=39,
    )
    template = "Failed on {game_label}.<br><br>Use <b>Re-analyze already analyzed games</b>."
    body = format_incomplete_analysis_message(template, game)
    assert "<br><br>" in body
    assert "<b>Re-analyze already analyzed games</b>" in body
    assert "game Nr. 48 Kramnik - Carlsen &lt;test&gt; 1-0" in body
    assert "{game_label}" not in body


def test_messages_use_config_values() -> None:
    config = {
        "ui": {
            "dialogs": {
                "bulk_analysis_dialog": {
                    "messages": {
                        "cancelled_by_user": "Stopped.",
                        "incomplete_analysis_title": "Incomplete",
                        "incomplete_analysis": "Standby. Re-run analysis.",
                        "standby_warning": "Turn off sleep.",
                    }
                }
            }
        }
    }
    messages = bulk_analysis_dialog_messages(config)
    assert messages["cancelled_by_user"] == "Stopped."
    assert messages["incomplete_analysis_title"] == "Incomplete"
    assert messages["incomplete_analysis"] == "Standby. Re-run analysis."
    assert messages["standby_warning"] == "Turn off sleep."


def test_messages_fall_back_when_missing() -> None:
    messages = bulk_analysis_dialog_messages({})
    assert messages["cancelled_by_user"]
    assert messages["incomplete_analysis_title"]
    assert "stand-by" in messages["incomplete_analysis"].lower()
    assert "<br>" in messages["incomplete_analysis"]
    assert "{game_label}" in messages["incomplete_analysis"]
    assert "standby" in messages["standby_warning"].lower()
    assert "power-saving" in messages["standby_warning"].lower()
    assert "battery" in messages["standby_warning"].lower()

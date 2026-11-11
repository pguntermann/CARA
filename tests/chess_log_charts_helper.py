"""Test stand-in for the ChessLogController the charts controller requires.

ChessLogChartsController.get_tags_for_game() needs an injected Chess Log
controller (C5).  Tests that build a charts controller around real PGN games
use ``StorageBackedChessLogController``, which answers from the games' PGNs.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from app.services.chess_log_storage_service import ChessLogStorageService


class StorageBackedChessLogController(QObject):
    """Minimal ChessLogController stub: resolved moments straight from the PGN.

    Carries the real controller's ``chess_log_changed`` signal, which the
    charts controller subscribes to on injection.
    """

    chess_log_changed = pyqtSignal(object)

    def get_tags_for_game(self, game):
        return ChessLogStorageService.load_resolved_paths(game)

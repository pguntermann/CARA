"""Test stand-in for the ChessLogController the charts controller requires.

ChessLogChartsController.get_tags_for_game() needs an injected Chess Log
controller (C5).  Tests that build a charts controller around real PGN games
use ``StorageBackedChessLogController``, which answers from the games' PGNs.
"""

from __future__ import annotations

from app.services.chess_log_storage_service import ChessLogStorageService


class StorageBackedChessLogController:
    """Minimal ChessLogController stub: resolved moments straight from the PGN."""

    def get_tags_for_game(self, game):
        return ChessLogStorageService.load_resolved_paths(game)

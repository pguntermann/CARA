"""Unit tests for DatabaseModel."""

from __future__ import annotations

import unittest


class TestDatabaseModelDisplayName(unittest.TestCase):
    def _make_model(self, file_path=None):
        from app.models.database_model import DatabaseModel
        return DatabaseModel(file_path=file_path)

    def test_display_name_returns_stem_for_file_path(self):
        model = self._make_model("/home/user/games/PaulChessGames.pgn")
        self.assertEqual(model.display_name, "PaulChessGames")

    def test_display_name_returns_clipboard_for_none(self):
        model = self._make_model(None)
        self.assertEqual(model.display_name, "Clipboard")

    def test_display_name_stem_strips_extension(self):
        model = self._make_model("/data/MyGames-2026.pgn")
        self.assertEqual(model.display_name, "MyGames-2026")


class TestDatabaseModelLogColumn(unittest.TestCase):
    """Tests for the COL_LOG column added to separate Chess Log from CARAGameTags."""

    @classmethod
    def setUpClass(cls):
        import sys
        # PyQt6 application instance is needed to construct QAbstractTableModel.
        from PyQt6.QtWidgets import QApplication
        if not QApplication.instance():
            cls._app = QApplication(sys.argv)
        else:
            cls._app = None

    def _make_model_with_games(self, has_log_values):
        """Return a DatabaseModel pre-populated with GameData rows.

        has_log_values: list of bool — one entry per game.
        """
        from app.models.database_model import DatabaseModel, GameData
        model = DatabaseModel(file_path=None)
        for i, has_log in enumerate(has_log_values):
            game = GameData(
                game_number=i + 1,
                white=f"White{i}",
                black=f"Black{i}",
                has_chess_log_tags=has_log,
            )
            model._games.append(game)
        return model

    # -- constant --

    def test_col_log_constant_value(self):
        from app.models.database_model import DatabaseModel
        self.assertEqual(DatabaseModel.COL_LOG, 22)

    def test_col_source_db_value(self):
        from app.models.database_model import DatabaseModel
        self.assertEqual(DatabaseModel.COL_SOURCE_DB, 18)

    def test_col_pgn_value(self):
        from app.models.database_model import DatabaseModel
        self.assertEqual(DatabaseModel.COL_PGN, 21)

    # -- data() --

    def test_data_returns_checkmark_when_has_chess_log_tags_true(self):
        from app.models.database_model import DatabaseModel
        from PyQt6.QtCore import Qt
        model = self._make_model_with_games([True])
        idx = model.index(0, DatabaseModel.COL_LOG)
        self.assertEqual(model.data(idx, Qt.ItemDataRole.DisplayRole), "✓")

    def test_data_returns_empty_when_has_chess_log_tags_false(self):
        from app.models.database_model import DatabaseModel
        from PyQt6.QtCore import Qt
        model = self._make_model_with_games([False])
        idx = model.index(0, DatabaseModel.COL_LOG)
        self.assertEqual(model.data(idx, Qt.ItemDataRole.DisplayRole), "")

    # -- headerData() --

    def test_header_data_returns_log_for_col_log(self):
        from app.models.database_model import DatabaseModel
        from PyQt6.QtCore import Qt
        model = self._make_model_with_games([])
        header = model.headerData(
            DatabaseModel.COL_LOG,
            Qt.Orientation.Horizontal,
            Qt.ItemDataRole.DisplayRole,
        )
        self.assertEqual(header, "Log")

    # -- sort() --

    def test_sort_by_col_log_puts_logged_games_first_descending(self):
        from app.models.database_model import DatabaseModel
        from PyQt6.QtCore import Qt
        model = self._make_model_with_games([False, True, False, True])
        model.sort(DatabaseModel.COL_LOG, Qt.SortOrder.DescendingOrder)
        # After descending sort, True rows come first.
        has_log_values = [
            model._games[r].has_chess_log_tags for r in range(len(model._games))
        ]
        self.assertEqual(has_log_values[:2], [True, True])
        self.assertEqual(has_log_values[2:], [False, False])

    def test_sort_by_col_log_puts_logged_games_last_ascending(self):
        from app.models.database_model import DatabaseModel
        from PyQt6.QtCore import Qt
        model = self._make_model_with_games([True, False, True])
        model.sort(DatabaseModel.COL_LOG, Qt.SortOrder.AscendingOrder)
        has_log_values = [
            model._games[r].has_chess_log_tags for r in range(len(model._games))
        ]
        self.assertEqual(has_log_values[0], False)
        self.assertEqual(has_log_values[1:], [True, True])


if __name__ == "__main__":
    unittest.main()

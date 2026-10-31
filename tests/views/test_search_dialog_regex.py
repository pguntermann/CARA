"""Search criteria row: matches regex operator and pattern field."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QWidget

from app.config.config_loader import ConfigLoader
from app.models.search_criteria import SearchCriteria, SearchField, SearchOperator
from app.views.dialogs.regex_editor_dialog import RegexEditorDialog
from app.views.dialogs.search_dialog import CriteriaRowWidget, SearchDialog
from app.views.widgets.regex_syntax import regex_token_colors


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _operators(row: CriteriaRowWidget) -> list[str]:
    combo = row.operator_combo
    return [combo.itemText(i) for i in range(combo.count())]


class TestSearchCriteriaRegex(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt = _app()
        cls.config = ConfigLoader().load()

    def test_operator_is_offered_on_text_fields_only(self) -> None:
        parent = QWidget()
        row = CriteriaRowWidget(self.config, parent=parent)
        self.assertIn("matches regex", _operators(row))
        for field in ("Black", "Date", "Event", "Site", "ECO", "TimeControl", "TC Type", "Custom PGN header tag"):
            row.field_combo.setCurrentText(field)
            self.assertIn("matches regex", _operators(row), field)
        for field in ("Result", "WhiteElo", "BlackElo", "Analyzed", "Annotated", "Game tags", "Position", "Position (fuzzy)"):
            row.field_combo.setCurrentText(field)
            self.assertNotIn("matches regex", _operators(row), field)
        parent.close()

    def test_pattern_field_highlights_and_validates(self) -> None:
        parent = QWidget()
        row = CriteriaRowWidget(self.config, parent=parent)
        row.show()
        _app().processEvents()
        self.assertFalse(row._regex_action.isVisible())
        row.operator_combo.setCurrentText("matches regex")
        self.assertTrue(row._regex_action.isVisible())
        self.assertFalse(row._regex_action.icon().isNull())
        self.assertEqual(row.value_input._edit.placeholderText(), "Regular expression")
        row.value_input.setText(r"\d+")
        _app().processEvents()
        colors = regex_token_colors(self.config)
        painted_escape = row.value_input.token_color_at(0)
        painted_plus = row.value_input.token_color_at(2)
        assert painted_escape is not None and painted_plus is not None
        self.assertEqual(
            (painted_escape.red(), painted_escape.green(), painted_escape.blue()),
            (colors["escape"].red(), colors["escape"].green(), colors["escape"].blue()),
        )
        self.assertEqual(
            (painted_plus.red(), painted_plus.green(), painted_plus.blue()),
            (colors["quantifier"].red(), colors["quantifier"].green(), colors["quantifier"].blue()),
        )
        criterion = row.get_criterion()
        assert criterion is not None
        self.assertEqual(criterion.operator, SearchOperator.MATCHES_REGEX)
        self.assertEqual(criterion.value, r"\d+")

        row.value_input.setText("(")
        self.assertIsNone(row.get_criterion())
        self.assertEqual(row.get_last_validation_error(), "That regular expression is not valid.")
        row.value_input.setText("  ")
        self.assertIsNone(row.get_criterion())
        self.assertEqual(row.get_last_validation_error(), "Enter a regular expression.")

        row.operator_combo.setCurrentText("contains")
        self.assertFalse(row._regex_action.isVisible())
        self.assertIsNone(row.value_input.token_color_at(0))
        self.assertEqual(row.value_input._edit.placeholderText(), "Value...")
        parent.close()

    def test_time_control_regex_keeps_the_pattern_string(self) -> None:
        parent = QWidget()
        row = CriteriaRowWidget(self.config, parent=parent)
        row.field_combo.setCurrentText("TimeControl")
        row.operator_combo.setCurrentText("matches regex")
        row.value_input.setText(r"\d+\+\d+")
        criterion = row.get_criterion()
        assert criterion is not None
        self.assertEqual(criterion.field, SearchField.TIMECONTROL)
        self.assertEqual(criterion.value, r"\d+\+\d+")
        row.set_criterion(criterion)
        self.assertEqual(row.operator_combo.currentText(), "matches regex")
        self.assertEqual(row.value_input.text(), r"\d+\+\d+")
        parent.close()

    def test_editor_is_not_painted_with_the_row_group_border(self) -> None:
        search = SearchDialog(self.config, None, [])
        row = search.criteria_rows[0]
        self.assertIn("border-left", row.styleSheet())
        captured = {}

        def _capture(*_args, **kwargs):
            captured["parent"] = kwargs.get("parent")
            return None

        import app.views.dialogs.search_dialog as search_dialog_module

        original = search_dialog_module.edit_regex
        search_dialog_module.edit_regex = _capture
        try:
            row._open_regex_editor()
        finally:
            search_dialog_module.edit_regex = original
        self.assertIs(captured["parent"], search)
        editor = RegexEditorDialog(
            self.config,
            pattern="^$",
            replacement="",
            case_sensitive=False,
            show_replace=False,
            parent=captured["parent"],
        )
        editor.resize(640, 480)
        editor.show()
        _app().processEvents()
        image = editor.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
        blue = 0
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.blue() > color.red() + 40 and color.blue() > 90 and color.red() < 140:
                    blue += 1
        self.assertEqual(blue, 0)
        editor.close()
        search.close()


if __name__ == "__main__":
    unittest.main()

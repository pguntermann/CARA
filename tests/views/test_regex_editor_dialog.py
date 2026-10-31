"""Regex editor dialog and the bulk-operations Find-field action."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QMenu, QScrollArea, QWidget

from app.config.config_loader import ConfigLoader
from app.utils.path_resolver import get_app_resource_path
from app.views.dialogs.bulk_operations_dialog import _OperationEditorOverlay
from app.views.dialogs.regex_editor_dialog import RegexEditorDialog
from app.views.style.grab_friendly_scrollbar import GrabFriendlyScrollBar
from app.views.widgets.regex_syntax import regex_token_colors


class _MemoryLibrary:
    def __init__(self) -> None:
        self.saved: dict = {}

    def get_saved_regexes(self) -> dict:
        return dict(self.saved)

    def update_saved_regexes(self, saved: dict) -> None:
        self.saved = dict(saved)


def _highlighted(dialog: RegexEditorDialog) -> list:
    return [selection.cursor.selectedText() for selection in dialog.sample_edit.extraSelections()]


def _menu_labels(menu: QMenu) -> list[str]:
    labels: list[str] = []
    for action in menu.actions():
        child = action.menu()
        if child is not None:
            labels.extend(_menu_labels(child))
        elif action.text():
            labels.append(action.text())
    return labels


def _menu_action(menu: QMenu, label: str):
    for action in menu.actions():
        child = action.menu()
        if child is not None:
            found = _menu_action(child, label)
            if found is not None:
                return found
        elif action.text() == label:
            return action
    return None


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestRegexEditorConfig(unittest.TestCase):
    def test_each_theme_loads_the_editor(self) -> None:
        self._qt = _app()
        loader = ConfigLoader()
        for style_ref in (
            "app/config/style_default.config.json",
            "app/config/style_light.config.json",
            "app/config/style_scholar.config.json",
        ):
            config = loader.load_with_style_override(style_ref)
            section = config["ui"]["dialogs"]["regex_editor"]
            self.assertGreaterEqual(len(section["block_groups"]), 4)
            icon = get_app_resource_path(section["find_action"]["icon_svg"])
            self.assertTrue(Path(icon).is_file())
            self.assertEqual(len(section["explain_style"]["kinds"]["escape"]["token_color"]), 3)
            self.assertNotIn("syntax", section["pattern"])
            self.assertEqual(len(section["find_action"]["icon_tint"]), 3)
            self.assertIsInstance(section["block_groups"], list)
            self.assertIsInstance(section["library_buttons"], dict)
            self.assertGreaterEqual(len(section["examples"]), 1)
            examples_icon = get_app_resource_path(section["library_buttons"]["examples_icon_svg"])
            self.assertTrue(Path(examples_icon).is_file())
            self.assertNotIn("title_style", section)
            self.assertNotIn("replace", section)
            self.assertNotIn("result", section)


class TestRegexEditorDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt = _app()
        cls.config = ConfigLoader().load()

    def test_saved_regex_can_be_loaded_and_removed(self) -> None:
        library = _MemoryLibrary()
        dialog = RegexEditorDialog(
            self.config,
            pattern="",
            replacement="",
            case_sensitive=False,
            settings=library,
        )
        dialog.show()
        _app().processEvents()
        self.assertEqual(dialog._save_button.text(), "")
        self.assertEqual(dialog._blocks_button.text(), "")
        self.assertFalse(dialog._save_button.icon().isNull())
        self.assertFalse(dialog._load_button.icon().isNull())
        self.assertFalse(dialog._blocks_button.icon().isNull())
        save_mid = dialog._save_button.mapTo(dialog, dialog._save_button.rect().center())
        blocks_mid = dialog._blocks_button.mapTo(dialog, dialog._blocks_button.rect().center())
        self.assertLess(abs(save_mid.y() - blocks_mid.y()), 8)
        self.assertLess(blocks_mid.x(), save_mid.x())
        separator = dialog.findChild(QFrame, "regexLibrarySeparator")
        self.assertIsNotNone(separator)
        assert separator is not None
        sep_mid = separator.mapTo(dialog, separator.rect().center()).x()
        self.assertLess(blocks_mid.x(), sep_mid)
        self.assertLess(sep_mid, save_mid.x())
        examples_mid = dialog._examples_button.mapTo(dialog, dialog._examples_button.rect().center())
        self.assertEqual(dialog._examples_button.text(), "")
        self.assertFalse(dialog._examples_button.icon().isNull())
        self.assertLess(blocks_mid.x(), examples_mid.x())
        self.assertLess(examples_mid.x(), sep_mid)
        self.assertTrue(dialog._save_button.isEnabled())
        dialog.pattern_edit.setPlainText("(")
        self.assertFalse(dialog._save_button.isEnabled())
        dialog.controller.store_pattern("Digits", r"\d+")
        dialog.pattern_edit.setPlainText("^$")
        menu = dialog._library_menu()
        labels = [action.text() for action in menu.actions() if action.menu() is None and not action.isSeparator()]
        self.assertIn("Digits", labels)
        remove = next(action.menu() for action in menu.actions() if action.menu() is not None)
        assert remove is not None
        self.assertEqual([action.text() for action in remove.actions()], ["Digits"])
        dialog._load_named("Digits")
        self.assertEqual(dialog.pattern_edit.toPlainText(), r"\d+")
        self.assertTrue(dialog._save_button.isEnabled())
        dialog.controller.remove_pattern("Digits")
        self.assertEqual(dialog.controller.saved_names(), [])
        dialog.close()

    def test_pattern_highlight_uses_the_explanation_token_colors(self) -> None:
        dialog = RegexEditorDialog(self.config, pattern="", replacement="", case_sensitive=False)
        colors = dialog._syntax_colors()
        kinds = dialog._cfg["explain_style"]["kinds"]
        for kind in ("group", "quantifier", "escape", "anchor", "any", "alternation", "set", "range", "error", "literal"):
            token = tuple(int(channel) for channel in kinds[kind]["token_color"][:3])
            self.assertEqual((colors[kind].red(), colors[kind].green(), colors[kind].blue()), token)
        dialog.close()

    def test_pattern_field_is_focused_only_after_the_dialog_is_shown(self) -> None:
        dialog = RegexEditorDialog(self.config, pattern="", replacement="", case_sensitive=False)
        self.assertIsNone(dialog.focusWidget())
        self.assertEqual(dialog.pattern_edit.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertFalse(dialog.pattern_edit.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled))
        self.assertFalse(dialog.sample_edit.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled))
        dialog.show()
        focused = False
        for _ in range(5):
            _app().processEvents()
            if dialog.focusWidget() is dialog.pattern_edit:
                focused = True
                break
        self.assertTrue(focused)
        self.assertEqual(dialog.pattern_edit.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertEqual(dialog.sample_edit.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertTrue(dialog.pattern_edit.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled))
        self.assertTrue(dialog.sample_edit.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled))
        dialog.close()

    def test_empty_pattern_opens_on_the_configured_template(self) -> None:
        dialog = RegexEditorDialog(
            self.config,
            pattern="",
            replacement="",
            case_sensitive=False,
        )
        self.assertEqual(dialog.pattern_edit.toPlainText(), "^$")
        self.assertEqual(dialog.pattern_edit.textCursor().position(), 1)
        dialog.close()

    def test_invalid_pattern_disables_ok_until_it_compiles(self) -> None:
        dialog = RegexEditorDialog(
            self.config,
            pattern="(",
            replacement="N",
            case_sensitive=False,
            sample="id 12",
        )
        self.assertFalse(dialog._ok_button.isEnabled())
        self.assertEqual(_highlighted(dialog), [])
        dialog.pattern_edit.setPlainText(r"\d+")
        self.assertTrue(dialog._ok_button.isEnabled())
        self.assertEqual(_highlighted(dialog), ["12"])
        dialog._on_ok()
        self.assertIsNotNone(dialog.result)
        assert dialog.result is not None
        self.assertEqual(dialog.result.pattern, r"\d+")
        self.assertEqual(dialog.result.replacement, "N")
        dialog.close()

    def test_preview_follows_the_caller_case_flag(self) -> None:
        sensitive = RegexEditorDialog(
            self.config, pattern="a", replacement="", case_sensitive=True, sample="A"
        )
        self.assertEqual(_highlighted(sensitive), [])
        sensitive.close()
        ignored = RegexEditorDialog(
            self.config, pattern="a", replacement="b", case_sensitive=False, sample="A"
        )
        self.assertEqual(_highlighted(ignored), ["A"])
        ignored.close()

    def test_sample_highlights_the_group_not_the_whole_line(self) -> None:
        dialog = RegexEditorDialog(
            self.config,
            pattern=r"^(.*?)\s*-\s*.*$",
            replacement="",
            case_sensitive=True,
            sample="Ok - World - Next",
        )
        self.assertEqual(_highlighted(dialog), ["Ok"])
        dialog.close()

    def test_example_menu_loads_the_pattern_and_its_sample(self) -> None:
        dialog = RegexEditorDialog(self.config, pattern="", replacement="", case_sensitive=False)
        dialog.show()
        _app().processEvents()
        menu = dialog._examples_menu()
        labels = _menu_labels(menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            ["Players", "Events and sites", "Dates", "Openings", "Clocks"],
        )
        self.assertIn("Player titles (GM/IM/FM/…)", labels)
        self.assertIn("Several spellings of a name", labels)
        self.assertIn("A last name", labels)
        self.assertIn("A first name", labels)
        self.assertIn("Last name starts with", labels)
        self.assertIn("Last name with van, von, or de", labels)
        self.assertIn("Games from one year", labels)
        self.assertIn("ECO letter group", labels)
        self.assertIn("Clock with an increment", labels)
        titles = _menu_action(menu, "Player titles (GM/IM/FM/…)")
        titles.trigger()
        self.assertIn("GM", dialog.pattern_edit.toPlainText())
        self.assertEqual(dialog.sample_edit.toPlainText(), "GM Magnus Carlsen")
        self.assertTrue(any("GM" in text for text in _highlighted(dialog)))
        selected = dialog.pattern_edit.textCursor().selectedText()
        self.assertIn("GM", selected)
        self.assertIn("WGM", selected)
        dialog.close()

    def test_building_block_menu_inserts_the_chosen_block(self) -> None:
        dialog = RegexEditorDialog(self.config, pattern="foo", replacement="", case_sensitive=False)
        self.assertEqual(dialog.windowTitle(), "Edit regular expression")
        self.assertFalse(any(label.text() == "Edit regular expression" for label in dialog.findChildren(QLabel)))
        self.assertFalse(any(label.text() == "Replace with" for label in dialog.findChildren(QLabel)))
        self.assertFalse(any(label.text() == "Pattern" for label in dialog.findChildren(QLabel)))
        menu = dialog._blocks_menu()
        assert isinstance(menu, QMenu)
        categories = [action.text() for action in menu.actions() if action.menu() is not None]
        self.assertEqual(categories, ["Characters", "Anchors", "Quantifiers", "Groups", "Sets"])
        groups = next(action.menu() for action in menu.actions() if action.text() == "Groups")
        assert groups is not None
        lookaround = next(action.menu() for action in groups.actions() if action.text() == "Lookaround")
        assert lookaround is not None
        self.assertIn("Lookahead", [action.text() for action in lookaround.actions()])
        characters = next(action.menu() for action in menu.actions() if action.text() == "Characters")
        assert characters is not None
        digit = next(action for action in characters.actions() if action.text() == "Digit")
        code = digit.defaultWidget().findChild(QLabel, "regexBlockCode")
        name = digit.defaultWidget().findChild(QLabel, "regexBlockName")
        assert code is not None and name is not None
        self.assertEqual(name.text(), "Digit")
        escape = dialog._syntax_colors()["escape"]
        self.assertIn(f"rgb({escape.red()}, {escape.green()}, {escape.blue()})", code.text())
        self.assertIn(r"\d", code.text())
        row = digit.defaultWidget()
        row.set_hovered(True)
        self.assertTrue(row.is_hovered())
        hover = dialog._menu_color("hover_background_color", (55, 55, 60))
        self.assertEqual(tuple(row._hover_background), tuple(hover))
        cursor = dialog.pattern_edit.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        dialog.pattern_edit.setTextCursor(cursor)
        group = next(action for action in groups.actions() if action.text() == "Group")
        group.trigger()
        self.assertEqual(dialog.pattern_edit.toPlainText(), "(foo)")
        dialog.close()

    def test_explanation_panel_describes_the_pattern(self) -> None:
        dialog = RegexEditorDialog(
            self.config,
            pattern=r"([A-Z])\w+",
            replacement="",
            case_sensitive=True,
        )
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertTrue(any("Capturing group #1" in text for text in labels))
        self.assertTrue(any("Character set" in text for text in labels))
        self.assertTrue(any(text == r"\w" for text in labels))
        self.assertTrue(any("1 or more" in text for text in labels))
        dialog.close()

    def test_explanation_stays_above_the_fields_when_the_window_is_short(self) -> None:
        dialog = RegexEditorDialog(
            self.config,
            pattern=r".*?\(([^)]+)\)\s*.*",
            replacement=r"\1",
            case_sensitive=False,
            sample="sample",
        )
        dialog.show()
        _app().processEvents()
        pattern_bottom = dialog.pattern_edit.mapTo(dialog, dialog.pattern_edit.rect().bottomLeft()).y()
        explain_top = dialog._explain_scroll.mapTo(dialog, dialog._explain_scroll.rect().topLeft()).y()
        explain_bottom = dialog._explain_scroll.mapTo(dialog, dialog._explain_scroll.rect().bottomLeft()).y()
        sample_top = dialog.sample_edit.mapTo(dialog, dialog.sample_edit.rect().topLeft()).y()
        sample_bottom = dialog.sample_edit.mapTo(dialog, dialog.sample_edit.rect().bottomLeft()).y()
        ok_bottom = dialog._ok_button.mapTo(dialog, dialog._ok_button.rect().bottomLeft()).y()
        self.assertLess(pattern_bottom, explain_top)
        self.assertLess(explain_bottom, sample_top)
        self.assertLess(sample_bottom, ok_bottom)
        self.assertLess(ok_bottom, dialog.rect().bottom())
        self.assertEqual(dialog.width(), dialog.minimumWidth())
        explain_scroll = dialog.findChild(QScrollArea, "regexExplainScroll")
        self.assertIsNotNone(explain_scroll)
        assert explain_scroll is not None
        explain_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        _app().processEvents()
        bar = explain_scroll.verticalScrollBar()
        self.assertIsInstance(bar, GrabFriendlyScrollBar)
        self.assertEqual(bar.width(), int(self.config["ui"]["styles"]["scrollbar"]["width"]))
        bar_right = bar.mapTo(explain_scroll, bar.rect().bottomRight())
        bar_top = bar.mapTo(explain_scroll, bar.rect().topLeft())
        self.assertGreaterEqual(bar_right.x(), explain_scroll.rect().right() - 1)
        self.assertLessEqual(bar_top.y(), 1)
        self.assertGreaterEqual(bar_right.y(), explain_scroll.rect().bottom() - 1)
        border = int(dialog._cfg["explain_style"]["border_width"])
        scroll_right = explain_scroll.mapTo(dialog._explain_scroll, explain_scroll.rect().topRight())
        self.assertGreaterEqual(scroll_right.x(), dialog._explain_scroll.rect().right() - border)
        self.assertEqual(dialog.pattern_edit.height(), int(dialog._cfg["pattern"]["min_height"]))
        sample_height = int(dialog._cfg["sample"]["min_height"])
        self.assertEqual(dialog.sample_edit.height(), sample_height)
        explain_before = dialog._explain_scroll.height()
        self.assertGreaterEqual(explain_before, int(dialog._cfg["explain_style"]["min_height"]))
        dialog.resize(dialog.width(), dialog.height() + 80)
        _app().processEvents()
        self.assertEqual(dialog.sample_edit.height(), sample_height)
        self.assertEqual(dialog.pattern_edit.height(), int(dialog._cfg["pattern"]["min_height"]))
        self.assertGreaterEqual(dialog._explain_scroll.height(), explain_before + 70)
        self.assertLess(dialog._blocks_button.mapTo(dialog, dialog._blocks_button.rect().bottomLeft()).y(), pattern_bottom)
        dialog.close()

    def test_match_only_hides_replacement(self) -> None:
        dialog = RegexEditorDialog(
            self.config,
            pattern="a",
            replacement="kept",
            case_sensitive=False,
            show_replace=False,
        )
        self.assertFalse(any(label.text() == "Result" for label in dialog.findChildren(QLabel)))
        dialog._on_ok()
        assert dialog.result is not None
        self.assertEqual(dialog.result.replacement, "kept")
        dialog.close()


class TestBulkFindRegexAction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt = _app()
        cls.config = ConfigLoader().load()

    def test_trailing_action_follows_the_regex_checkbox(self) -> None:
        parent = QWidget()
        overlay = _OperationEditorOverlay(self.config, ["White", "Black"], ["White"], ["White"], parent)
        action = overlay._regex_edit_action
        self.assertFalse(action.isVisible())
        self.assertFalse(action.icon().isNull())
        overlay.regex_check.setChecked(True)
        self.assertTrue(action.isVisible())
        overlay.regex_check.setChecked(False)
        self.assertFalse(action.isVisible())
        overlay.show()
        _app().processEvents()
        regex_x = overlay.regex_check.mapTo(overlay, overlay.regex_check.rect().center()).x()
        case_x = overlay.case_check.mapTo(overlay, overlay.case_check.rect().center()).x()
        self.assertLess(regex_x, case_x)
        self.assertIn("font-weight: 700", overlay.regex_check.styleSheet())
        self.assertNotIn("font-weight:", overlay.case_check.styleSheet())
        overlay.find_input.setText(r"\d+")
        self.assertIsNone(overlay.find_input.token_color_at(0))
        overlay.regex_check.setChecked(True)
        _app().processEvents()
        colors = regex_token_colors(self.config)
        painted_escape = overlay.find_input.token_color_at(0)
        painted_plus = overlay.find_input.token_color_at(2)
        assert painted_escape is not None and painted_plus is not None
        self.assertEqual(
            (painted_escape.red(), painted_escape.green(), painted_escape.blue()),
            (colors["escape"].red(), colors["escape"].green(), colors["escape"].blue()),
        )
        self.assertEqual(
            (painted_plus.red(), painted_plus.green(), painted_plus.blue()),
            (colors["quantifier"].red(), colors["quantifier"].green(), colors["quantifier"].blue()),
        )
        overlay.regex_check.setChecked(False)
        self.assertIsNone(overlay.find_input.token_color_at(0))
        overlay.close()
        parent.close()


if __name__ == "__main__":
    unittest.main()

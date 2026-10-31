"""RegexEditorController applies the caller flag, limits, and status copy."""

from __future__ import annotations

import unittest

from app.config.config_loader import ConfigLoader
from app.controllers.regex_editor_controller import RegexEditorController
from app.services.regex_editor_service import RegexBlock


class _MemoryLibrary:
    def __init__(self) -> None:
        self.saved: dict = {}

    def get_saved_regexes(self) -> dict:
        return dict(self.saved)

    def update_saved_regexes(self, saved: dict) -> None:
        self.saved = dict(saved)


def _config() -> dict:
    return {
        "ui": {
            "dialogs": {
                "regex_editor": {
                    "empty_template": "^$",
                    "max_sample_chars": 100,
                    "max_highlighted_matches": 2,
                    "block_groups": [
                        {
                            "id": "groups",
                            "label": "Groups",
                            "blocks": [
                                {
                                    "id": "group",
                                    "label": "Group",
                                    "insert": "(text)",
                                    "select_text": "text",
                                    "tooltip": "A group.",
                                }
                            ],
                        }
                    ],
                }
            }
        }
    }


class TestRegexEditorController(unittest.TestCase):
    def test_preview_uses_the_caller_case_flag_and_limits(self) -> None:
        controller = RegexEditorController(_config(), case_sensitive=True, show_replace=True, replacement="")
        preview = controller.preview("a", "X", "aA")
        self.assertEqual(preview.result, "XA")
        self.assertEqual(preview.matches, ("a",))

        capped = controller.preview("a", "", "aaa")
        self.assertTrue(capped.matches_capped)
        self.assertEqual(capped.matches, ("a", "a"))

    def test_accept_keeps_the_passed_replacement_when_replace_is_hidden(self) -> None:
        controller = RegexEditorController(
            _config(), case_sensitive=False, show_replace=False, replacement="kept"
        )
        preview = controller.preview("a", "ignored", "A")
        self.assertEqual(preview.result, "kept")
        values = controller.accepted_values("a", "ignored", "A")
        self.assertIsNotNone(values)
        assert values is not None
        self.assertEqual(values.replacement, "kept")
        self.assertIsNone(controller.accepted_values("(", "ignored", "A"))

    def test_insert_block_wraps_a_selection(self) -> None:
        controller = RegexEditorController(_config(), case_sensitive=False, show_replace=True, replacement="")
        block = next(item for item in controller.blocks() if item.id == "group")
        self.assertIsInstance(block, RegexBlock)
        text, start, end = controller.insert_block("ab", 0, 2, block)
        self.assertEqual(text, "(ab)")
        self.assertEqual(text[start:end], "ab")

    def test_explanation_uses_configured_sentences_and_case_flag(self) -> None:
        controller = RegexEditorController(
            ConfigLoader().load(),
            case_sensitive=True,
            show_replace=True,
            replacement="",
        )
        nodes = controller.explain(r"([A-Z])\w+")
        group = nodes[0]
        self.assertIn("Capturing group #1", group.text)
        charset = group.children[0]
        self.assertIn("Character set", charset.text)
        self.assertIn('range "A" to "Z"', charset.children[0].text)
        self.assertIn("Case sensitive", charset.children[0].text)
        self.assertIn("Word", nodes[1].text)
        self.assertIn("1 or more", nodes[2].text)

        ignored = RegexEditorController(
            ConfigLoader().load(),
            case_sensitive=False,
            show_replace=True,
            replacement="",
        )
        ranged = ignored.explain(r"[A-Z]")[0].children[0]
        self.assertIn("Ignores case", ranged.text)
        self.assertNotIn("Case sensitive", ranged.text)

    def test_empty_pattern_uses_the_configured_template(self) -> None:
        controller = RegexEditorController(
            ConfigLoader().load(),
            case_sensitive=False,
            show_replace=True,
            replacement="",
        )
        self.assertEqual(controller.starting_pattern(""), ("^$", 1))
        self.assertEqual(controller.starting_pattern(r"\d+"), (r"\d+", None))

        custom = _config()
        custom["ui"]["dialogs"]["regex_editor"]["empty_template"] = ".*"
        overridden = RegexEditorController(custom, case_sensitive=False, show_replace=True, replacement="")
        self.assertEqual(overridden.starting_pattern(""), (".*", 2))

    def test_library_saves_loads_and_removes(self) -> None:
        library = _MemoryLibrary()
        controller = RegexEditorController(
            _config(), case_sensitive=False, show_replace=True, replacement="", settings=library
        )
        self.assertFalse(controller.pattern_can_be_saved("("))
        self.assertTrue(controller.pattern_can_be_saved(r"\d+"))
        controller.store_pattern("  Digits  ", r"\d+")
        controller.store_pattern("", r"\d+")
        self.assertEqual(controller.saved_names(), ["Digits"])
        self.assertEqual(controller.saved_pattern("Digits"), r"\d+")
        self.assertTrue(controller.library_has("Digits"))
        self.assertFalse(controller.replaces_current_pattern("^$"))
        self.assertTrue(controller.replaces_current_pattern(r"\w+"))
        controller.remove_pattern("Digits")
        self.assertEqual(controller.saved_names(), [])

    def test_empty_pattern_is_not_accepted(self) -> None:
        controller = RegexEditorController(_config(), case_sensitive=False, show_replace=True, replacement="")
        preview = controller.preview("", "", "")
        self.assertTrue(preview.empty)
        self.assertIsNone(controller.accepted_values("", "", ""))


if __name__ == "__main__":
    unittest.main()

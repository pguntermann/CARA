"""Tests for bulk find/replace regex presets loaded from config."""

import json
import re
import unittest
from pathlib import Path

from app.utils.bulk_regex_presets import (
    CUSTOM_PRESET_ID,
    find_preset_by_id,
    load_bulk_regex_presets,
    match_preset_id,
)


def _config_from_disk() -> dict:
    path = Path(__file__).resolve().parents[2] / "app" / "config" / "config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _apply(find: str, replace: str, value: str) -> str:
    return re.sub(find, replace, value)


class TestBulkRegexPresets(unittest.TestCase):
    def test_load_presets_from_config_json(self) -> None:
        presets = load_bulk_regex_presets(_config_from_disk())
        self.assertEqual(presets[0].id, CUSTOM_PRESET_ID)
        self.assertIsNotNone(find_preset_by_id(presets, "keep_capture"))
        self.assertIsNotNone(find_preset_by_id(presets, "keep_before_dash"))

    def test_keep_before_dash_preset(self) -> None:
        presets = load_bulk_regex_presets(_config_from_disk())
        preset = find_preset_by_id(presets, "keep_before_dash")
        self.assertIsNotNone(preset)
        assert preset is not None
        self.assertEqual(
            _apply(preset.find, preset.replace, "Wijk aan Zee - Masters"),
            "Wijk aan Zee",
        )
        self.assertEqual(
            _apply(preset.find, preset.replace, "Wijk aan Zee-Masters"),
            "Wijk aan Zee",
        )

    def test_keep_after_dash_preset(self) -> None:
        presets = load_bulk_regex_presets(_config_from_disk())
        preset = find_preset_by_id(presets, "keep_after_dash")
        self.assertIsNotNone(preset)
        assert preset is not None
        self.assertEqual(
            _apply(preset.find, preset.replace, "Wijk aan Zee - Masters"),
            "Masters",
        )
        self.assertEqual(
            _apply(preset.find, preset.replace, "Wijk aan Zee-Masters"),
            "Masters",
        )

    def test_keep_in_parens_preset(self) -> None:
        presets = load_bulk_regex_presets(_config_from_disk())
        preset = find_preset_by_id(presets, "keep_in_parens")
        self.assertIsNotNone(preset)
        assert preset is not None
        self.assertEqual(
            _apply(preset.find, preset.replace, "Olympiad (Open)"),
            "Open",
        )

    def test_keep_capture_literal_substring(self) -> None:
        presets = load_bulk_regex_presets(_config_from_disk())
        preset = find_preset_by_id(presets, "keep_capture")
        self.assertIsNotNone(preset)
        assert preset is not None
        find = preset.find.replace("text to keep", "Candidates")
        self.assertEqual(
            _apply(find, preset.replace, "FIDE Candidates Tournament 2024"),
            "Candidates",
        )

    def test_match_preset_id_roundtrip(self) -> None:
        presets = load_bulk_regex_presets(_config_from_disk())
        preset = find_preset_by_id(presets, "keep_year")
        self.assertIsNotNone(preset)
        assert preset is not None
        self.assertEqual(
            match_preset_id(presets, preset.find, preset.replace),
            "keep_year",
        )
        self.assertEqual(
            match_preset_id(presets, "custom", r"\1"),
            CUSTOM_PRESET_ID,
        )

    def test_missing_presets_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "regex_presets"):
            load_bulk_regex_presets({"ui": {"dialogs": {"bulk_operations": {}}}})

    def test_invalid_find_regex_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid find regex"):
            load_bulk_regex_presets(
                {
                    "ui": {
                        "dialogs": {
                            "bulk_operations": {
                                "regex_presets": [
                                    {
                                        "id": "bad",
                                        "label": "Bad",
                                        "find": "(",
                                        "replace": "",
                                    }
                                ]
                            }
                        }
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()

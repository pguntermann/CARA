"""Verify that every Chess Log dialog config key is present in all three theme files."""

from __future__ import annotations

import unittest


def _load_config(style_ref: str) -> dict:
    from app.config.config_loader import ConfigLoader
    return ConfigLoader().load_with_style_override(style_ref)


_MOMENT_KEYS = [
    "background_color",
    "border_color",
    "text_color",
    "hint_color",
    "muted_color",
    "separator_color",
    "label_font_family",
    "label_font_size",
    "chip_bg_color",
    "chip_selected_color",
    "chip_text_color",
    "chip_border_color",
    "chip_hover_border_color",
]

_MOMENT_INPUT_KEYS = [
    "font_family",
    "font_size",
    "text_color",
    "background_color",
    "border_color",
    "focus_border_color",
]

_CHESS_LOG_SETTINGS_KEYS = [
    "background_color",
    "border_color",
    "text_color",
]


class TestMomentDialogKeysInAllThemes(unittest.TestCase):
    def _check_theme(self, style_ref: str) -> None:
        config = _load_config(style_ref)
        dc = config.get("ui", {}).get("dialogs", {}).get("moment")
        self.assertIsNotNone(dc, f"ui.dialogs.moment missing in {style_ref}")
        for key in _MOMENT_KEYS:
            self.assertIn(key, dc, f"ui.dialogs.moment.{key} missing in {style_ref}")
        inp = dc.get("inputs")
        self.assertIsNotNone(inp, f"ui.dialogs.moment.inputs missing in {style_ref}")
        for key in _MOMENT_INPUT_KEYS:
            self.assertIn(key, inp, f"ui.dialogs.moment.inputs.{key} missing in {style_ref}")

    def test_default_theme(self):
        self._check_theme("style_default.config.json")

    def test_light_theme(self):
        self._check_theme("style_light.config.json")

    def test_scholar_theme(self):
        self._check_theme("style_scholar.config.json")


class TestChessLogSettingsKeysInAllThemes(unittest.TestCase):
    def _check_theme(self, style_ref: str) -> None:
        config = _load_config(style_ref)
        dc = config.get("ui", {}).get("dialogs", {}).get("chess_log_settings")
        self.assertIsNotNone(dc, f"ui.dialogs.chess_log_settings missing in {style_ref}")
        for key in _CHESS_LOG_SETTINGS_KEYS:
            self.assertIn(key, dc, f"ui.dialogs.chess_log_settings.{key} missing in {style_ref}")

    def test_default_theme(self):
        self._check_theme("style_default.config.json")

    def test_light_theme(self):
        self._check_theme("style_light.config.json")

    def test_scholar_theme(self):
        self._check_theme("style_scholar.config.json")


_CHESS_LOG_CHARTS_CHART_KEYS = [
    "background_color",
    "grid_color",
    "axis_color",
    "text_color",
    "title_color",
]

_CHESS_LOG_CHARTS_COLORS_KEYS = [
    "background",
    "text",
    "input_background",
    "border",
    "hint_text",
    "spinner_color",
]

_CHESS_LOG_CHARTS_CATEGORY_PRESETS = {
    "CLAMP": ["C", "L", "A", "M", "P"],
    "CCT": ["C", "C2", "T"],
}


class TestChessLogChartsKeysInAllThemes(unittest.TestCase):
    def _check_theme(self, style_ref: str) -> None:
        config = _load_config(style_ref)
        cl = config.get("ui", {}).get("panels", {}).get("detail", {}).get("chess_log_charts")
        self.assertIsNotNone(cl, f"ui.panels.detail.chess_log_charts missing in {style_ref}")

        chart = cl.get("chart", {})
        for key in _CHESS_LOG_CHARTS_CHART_KEYS:
            self.assertIn(key, chart, f"chess_log_charts.chart.{key} missing in {style_ref}")

        colors = cl.get("colors", {})
        for key in _CHESS_LOG_CHARTS_COLORS_KEYS:
            self.assertIn(key, colors, f"chess_log_charts.colors.{key} missing in {style_ref}")

        cat_colors = cl.get("category_colors", {})
        for preset, cats in _CHESS_LOG_CHARTS_CATEGORY_PRESETS.items():
            self.assertIn(preset, cat_colors,
                          f"chess_log_charts.category_colors.{preset} missing in {style_ref}")
            for cat in cats:
                self.assertIn(cat, cat_colors[preset],
                              f"chess_log_charts.category_colors.{preset}.{cat} missing in {style_ref}")

    def test_default_theme(self):
        self._check_theme("app/config/style_default.config.json")

    def test_light_theme(self):
        self._check_theme("app/config/style_light.config.json")

    def test_scholar_theme(self):
        self._check_theme("app/config/style_scholar.config.json")


if __name__ == "__main__":
    unittest.main()

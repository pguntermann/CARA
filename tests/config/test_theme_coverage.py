"""Phase 8: verify that Chess Log config paths exist in all three theme files.

Does NOT load via ConfigLoader (no $ref expansion needed) — just checks key
existence so a missing entry is caught before the app is launched.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any


_REPO = Path(__file__).resolve().parents[2]
_STYLE_FILES = [
    _REPO / "app/config/style_default.config.json",
    _REPO / "app/config/style_light.config.json",
    _REPO / "app/config/style_scholar.config.json",
]

_CHESS_LOG_CHARTS_COLOR_KEYS = [
    "ui.panels.detail.chess_log_charts.colors.background",
    "ui.panels.detail.chess_log_charts.colors.text",
    "ui.panels.detail.chess_log_charts.colors.input_background",
    "ui.panels.detail.chess_log_charts.colors.border",
    "ui.panels.detail.chess_log_charts.colors.hint_text",
    "ui.panels.detail.chess_log_charts.colors.link",
    "ui.panels.detail.chess_log_charts.colors.spinner_color",
]

_CHESS_LOG_CHARTS_PDF_KEYS = [
    "ui.panels.detail.chess_log_charts.pdf_report.colors.warning_fill",
    "ui.panels.detail.chess_log_charts.pdf_report.colors.warning_outline",
    "ui.panels.detail.chess_log_charts.pdf_report.table_col_widths_pct",
]

_CHESS_LOG_CHARTS_CHART_KEYS = [
    "ui.panels.detail.chess_log_charts.chart.background_color",
    "ui.panels.detail.chess_log_charts.chart.grid_color",
    "ui.panels.detail.chess_log_charts.chart.axis_color",
    "ui.panels.detail.chess_log_charts.chart.text_color",
    "ui.panels.detail.chess_log_charts.chart.title_color",
]

_CHESS_LOG_CHARTS_TOKEN_LABEL_KEYS = [
    "ui.panels.detail.chess_log_charts.token_usage_label.color",
    "ui.panels.detail.chess_log_charts.token_usage_label.font_size",
]

_DATABASE_COLUMN_WIDTH_KEYS = [
    "ui.panels.database.table.column_widths.col_log",
]

_MOMENT_DIALOG_LAYOUT_KEYS = [
    "ui.dialogs.moment.game_header.background_color",
    "ui.dialogs.moment.game_header.text_color",
    "ui.dialogs.moment.game_header.padding_vertical",
    "ui.dialogs.moment.game_header.padding_horizontal",
    "ui.dialogs.moment.game_header.top_spacing",
    "ui.dialogs.moment.bottom_button_top_padding",
    "ui.dialogs.moment.buttons.spacing",
    "ui.dialogs.moment.chips.cct_min_width",
    "ui.dialogs.moment.chips.min_width",
    "ui.dialogs.moment.layout.margins",
    "ui.dialogs.moment.layout.spacing",
    "ui.dialogs.moment.why.minimum_height",
    "ui.dialogs.moment.three_by_three.edit_minimum_height",
]

_SHOW_TAGS_DIALOG_KEYS = [
    "ui.dialogs.show_tags.label_font_family",
    "ui.dialogs.show_tags.label_font_size",
    "ui.dialogs.show_tags.inputs.font_family",
    "ui.dialogs.show_tags.inputs.font_size",
    "ui.dialogs.show_tags.fit_min_lines",
    "ui.dialogs.show_tags.fit_max_lines",
]

_SHALLOW_CHIP_KEYS = [
    "ui.dialogs.shallow.labels.shallow.background_color",
    "ui.dialogs.shallow.labels.shallow.text_color",
    "ui.dialogs.shallow.labels.vague_lesson.background_color",
    "ui.dialogs.shallow.labels.vague_lesson.text_color",
    "ui.dialogs.shallow.unchecked_banner.background_color",
    "ui.dialogs.shallow.unchecked_banner.text_color",
]

_PDF_CHESS_LOG_KEYS = [
    "ui.pdf.chess_log.card_fill",
]

_ALL_PATHS = (
    _CHESS_LOG_CHARTS_COLOR_KEYS
    + _CHESS_LOG_CHARTS_PDF_KEYS
    + _CHESS_LOG_CHARTS_CHART_KEYS
    + _CHESS_LOG_CHARTS_TOKEN_LABEL_KEYS
    + _DATABASE_COLUMN_WIDTH_KEYS
    + _MOMENT_DIALOG_LAYOUT_KEYS
    + _SHOW_TAGS_DIALOG_KEYS
    + _SHALLOW_CHIP_KEYS
    + _PDF_CHESS_LOG_KEYS
)


def _get_nested(d: Any, dotted_path: str) -> bool:
    """Return True iff the dotted key path exists in the nested dict."""
    parts = dotted_path.split(".")
    cur = d
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


class TestChessLogThemeCoverage(unittest.TestCase):
    """All curated Chess Log config paths must be present in every theme file."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._themes: dict[str, Any] = {}
        for path in _STYLE_FILES:
            with open(path, encoding="utf-8") as fh:
                cls._themes[path.name] = json.load(fh)

    def _check_path(self, dotted_path: str) -> None:
        for name, cfg in self._themes.items():
            with self.subTest(theme=name, path=dotted_path):
                self.assertTrue(
                    _get_nested(cfg, dotted_path),
                    f"{name} is missing key path: {dotted_path}",
                )

    def test_chess_log_charts_color_keys_present(self):
        for path in _CHESS_LOG_CHARTS_COLOR_KEYS:
            self._check_path(path)

    def test_chess_log_charts_pdf_keys_present(self):
        for path in _CHESS_LOG_CHARTS_PDF_KEYS:
            self._check_path(path)

    def test_chess_log_charts_chart_keys_present(self):
        for path in _CHESS_LOG_CHARTS_CHART_KEYS:
            self._check_path(path)

    def test_chess_log_charts_token_usage_label_keys_present(self):
        for path in _CHESS_LOG_CHARTS_TOKEN_LABEL_KEYS:
            self._check_path(path)

    def test_database_column_width_keys_present(self):
        for path in _DATABASE_COLUMN_WIDTH_KEYS:
            self._check_path(path)

    def test_moment_dialog_layout_keys_present(self):
        for path in _MOMENT_DIALOG_LAYOUT_KEYS:
            self._check_path(path)

    def test_show_tags_dialog_keys_present(self):
        for path in _SHOW_TAGS_DIALOG_KEYS:
            self._check_path(path)

    def test_pdf_chess_log_keys_present(self):
        for path in _PDF_CHESS_LOG_KEYS:
            self._check_path(path)

    def test_shallow_chip_keys_present(self):
        for path in _SHALLOW_CHIP_KEYS:
            self._check_path(path)


if __name__ == "__main__":
    unittest.main()

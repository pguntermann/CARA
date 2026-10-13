"""KPI tip builder for Game Summary key statistics."""

import unittest

from app.views.widgets.kpi_explain_popup import build_kpi_tip, load_kpi_tip_visual_style


def _sample_config() -> dict:
    return {
        "ui": {
            "panels": {
                "detail": {
                    "summary": {
                        "key_statistics": {
                            "kpi_tip": {
                                "wrap_width": 320,
                                "band_table_desc_wrap": 160,
                                "content_spacing": 5,
                                "value_hint": {
                                    "underline_style": "dotted",
                                    "underline_style_hover": "solid",
                                    "underline_color": [1, 2, 3],
                                    "underline_color_hover": [4, 5, 6],
                                },
                                "scale": {
                                    "min_width": 240,
                                    "preferred_height": 50,
                                    "bar_height": 10,
                                    "bar_top": 8,
                                    "bar_corner_radius": 2,
                                    "horizontal_inset": 3,
                                },
                                "band_table": {
                                    "horizontal_spacing": 7,
                                    "vertical_spacing": 2,
                                    "swatch_size": 8,
                                    "header_color_delta": -20,
                                },
                                "band_colors_cool_to_warm": [
                                    [10, 20, 30],
                                    [40, 50, 60],
                                ],
                            },
                            "kpi_tips": {
                                "average_cpl": {
                                    "title": "Average CPL",
                                    "explanation": "Average centipawns lost per move.",
                                    "note": "Approximate guide.",
                                    "scale_min": 0,
                                    "scale_max": 80,
                                    "higher_is_better": False,
                                    "unit": "CPL",
                                    "bands": [
                                        {
                                            "label": "GM / Elite",
                                            "end": 15,
                                            "description": "Near-engine precision",
                                        },
                                        {
                                            "label": "Amateur",
                                            "end": 80,
                                            "description": "Casual play",
                                        },
                                    ],
                                },
                                "accuracy": {
                                    "title": "Accuracy",
                                    "explanation": "Accuracy score.",
                                    "note": "Approximate guide.",
                                    "scale_min": 50,
                                    "scale_max": 100,
                                    "higher_is_better": True,
                                    "unit": "%",
                                    "bands": [
                                        {"label": "Amateur", "end": 75},
                                        {"label": "GM / Elite", "end": 100},
                                    ],
                                },
                            },
                        }
                    }
                }
            }
        }
    }


class TestBuildKpiTip(unittest.TestCase):
    def test_average_cpl_from_config(self) -> None:
        tip = build_kpi_tip("average_cpl", 22.5, "22.5", _sample_config())
        self.assertIsNotNone(tip)
        assert tip is not None
        self.assertEqual(tip.title, "Average CPL")
        self.assertFalse(tip.higher_is_better)
        self.assertEqual(tip.value, 22.5)
        self.assertEqual(len(tip.bands), 2)
        self.assertEqual(tip.bands[0].description, "Near-engine precision")
        self.assertEqual(tip.bands[1].description, "Casual play")
        self.assertIn("centipawn", tip.explanation.lower())

    def test_missing_config_returns_none(self) -> None:
        self.assertIsNone(build_kpi_tip("average_cpl", 1.0, "1"))

    def test_unknown_kpi_returns_none(self) -> None:
        self.assertIsNone(build_kpi_tip("not_a_kpi", 1.0, "1", _sample_config()))

    def test_config_title(self) -> None:
        tip = build_kpi_tip("accuracy", 91.0, "91.0%", _sample_config())
        self.assertIsNotNone(tip)
        assert tip is not None
        self.assertEqual(tip.title, "Accuracy")
        self.assertTrue(tip.higher_is_better)


class TestLoadKpiTipVisualStyle(unittest.TestCase):
    def test_loads_theme_values(self) -> None:
        style = load_kpi_tip_visual_style(_sample_config())
        self.assertEqual(style.wrap_width, 320)
        self.assertEqual(style.scale_min_width, 240)
        self.assertEqual(style.band_table_swatch_size, 8)
        self.assertEqual(style.band_colors_cool_to_warm, ((10, 20, 30), (40, 50, 60)))
        self.assertEqual(style.value_underline_style, "dotted")
        self.assertEqual(style.value_underline_color, (1, 2, 3))
        self.assertEqual(style.value_underline_color_hover, (4, 5, 6))

    def test_defaults_without_config(self) -> None:
        style = load_kpi_tip_visual_style(None)
        self.assertEqual(style.wrap_width, 340)
        self.assertEqual(len(style.band_colors_cool_to_warm), 5)


if __name__ == "__main__":
    unittest.main()

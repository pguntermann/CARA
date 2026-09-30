"""Placement and theme parsing for the linked-move hover popup."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from app.config.config_loader import ConfigLoader
from app.views.style.tooltip import load_tooltip_style
from app.views.widgets.move_link_popup import (
    MoveLinkPopup,
    MoveLinkTip,
    clamp_caret_center,
    place_move_link_popup,
    position_board_arrows,
    uci_from_san,
)


class TestMoveLinkPopupPlacement(unittest.TestCase):
    def test_places_below_and_aims_caret_at_anchor_center(self) -> None:
        x, y, edge, caret_x = place_move_link_popup(
            anchor_left=100,
            anchor_top=100,
            anchor_width=40,
            anchor_height=16,
            popup_width=80,
            popup_height=50,
            screen_left=0,
            screen_top=0,
            screen_right=800,
            screen_bottom=600,
            caret_size=8,
            anchor_gap=4,
            border_radius=5,
            border_width=1,
        )
        self.assertEqual(edge, "top")
        self.assertEqual(y, 120)
        self.assertEqual(x + caret_x, 120)

    def test_flips_above_when_below_does_not_fit(self) -> None:
        _x, y, edge, _caret_x = place_move_link_popup(
            anchor_left=100,
            anchor_top=560,
            anchor_width=40,
            anchor_height=16,
            popup_width=80,
            popup_height=50,
            screen_left=0,
            screen_top=0,
            screen_right=800,
            screen_bottom=600,
            caret_size=8,
            anchor_gap=4,
            border_radius=5,
            border_width=1,
        )
        self.assertEqual(edge, "bottom")
        self.assertEqual(y, 560 - 4 - 50)

    def test_caret_stays_clear_of_rounded_corners(self) -> None:
        self.assertEqual(clamp_caret_center(2, 200, 8, 5, 1), 8 + 5 + 1)
        self.assertEqual(clamp_caret_center(190, 200, 8, 5, 1), 200 - (8 + 5 + 1))
        self.assertEqual(clamp_caret_center(40, 200, 8, 5, 1), 40)


class TestTooltipStyleBoardFlag(unittest.TestCase):
    def test_style_configs_expose_the_board_switch(self) -> None:
        loader = ConfigLoader()
        for style_ref in (
            "app/config/style_default.config.json",
            "app/config/style_light.config.json",
            "app/config/style_scholar.config.json",
        ):
            config = loader.load_with_style_override(style_ref)
            style = load_tooltip_style(config)
            self.assertTrue(style.show_position_board)
            self.assertGreaterEqual(style.position_board_size, 48)
            self.assertGreaterEqual(style.caret_size, 4)
            self.assertTrue(style.show_best_alternative_arrow)
            self.assertEqual(len(style.played_move_arrow_color), 3)
            self.assertEqual(len(style.best_alternative_arrow_color), 3)
            self.assertNotEqual(style.played_move_arrow_color, style.best_alternative_arrow_color)
            self.assertNotEqual(style.played_move_arrow_color, (0, 0, 255))

    def test_board_can_be_disabled(self) -> None:
        style = load_tooltip_style(
            {"ui": {"styles": {"tooltip": {"show_position_board": False}}}}
        )
        self.assertFalse(style.show_position_board)

    def test_arrow_colors_and_alternative_arrow_can_be_disabled(self) -> None:
        style = load_tooltip_style(
            {
                "ui": {
                    "styles": {
                        "tooltip": {
                            "played_move_arrow_color": [255, 255, 0],
                            "show_best_alternative_arrow": False,
                            "best_alternative_arrow_color": [200, 0, 100],
                        }
                    }
                }
            }
        )
        self.assertEqual(style.played_move_arrow_color, (255, 255, 0))
        self.assertFalse(style.show_best_alternative_arrow)
        self.assertEqual(style.best_alternative_arrow_color, (200, 0, 100))

    def test_position_board_arrows_use_played_color_and_skip_a_matching_alternative(self) -> None:
        both = position_board_arrows(
            played_uci="e2e4",
            alternative_uci="d2d4",
            played_color=(255, 255, 0),
            alternative_color=(200, 0, 100),
            show_alternative=True,
        )
        self.assertEqual([move.uci() for move, _color in both], ["e2e4", "d2d4"])
        self.assertEqual(both[0][1], [255, 255, 0])
        self.assertEqual(both[1][1], [200, 0, 100])
        same = position_board_arrows(
            played_uci="e2e4",
            alternative_uci="e2e4",
            played_color=(255, 255, 0),
            alternative_color=(200, 0, 100),
            show_alternative=True,
        )
        self.assertEqual([move.uci() for move, _color in same], ["e2e4"])
        hidden = position_board_arrows(
            played_uci="e2e4",
            alternative_uci="d2d4",
            played_color=(255, 255, 0),
            alternative_color=(200, 0, 100),
            show_alternative=False,
        )
        self.assertEqual([move.uci() for move, _color in hidden], ["e2e4"])

    def test_uci_from_san(self) -> None:
        start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.assertEqual(uci_from_san(start, "e4"), "e2e4")
        self.assertEqual(uci_from_san(start, "Nxe3"), "")
        self.assertEqual(uci_from_san(start, ""), "")
        self.assertEqual(uci_from_san("", "e4"), "")

    def test_popup_opens_without_a_board_when_disabled(self) -> None:
        _app = QApplication.instance() or QApplication([])
        popup = MoveLinkPopup(
            {"ui": {"styles": {"tooltip": {"show_position_board": False, "hover_delay_ms": 0}}}},
        )
        self.assertIsNone(popup._board)
        anchor = QLabel("12. Nf3")
        anchor.show()
        popup.present(
            anchor,
            MoveLinkTip(
                title="12. Nf3",
                subtitle="Best Move",
                details=(("Tactic", "fork"), ("CP gain", "+10 counted in ranking")),
            ),
            is_flipped=False,
        )
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup._title.text(), "12. Nf3")
        self.assertEqual(popup._subtitle.text(), "Best Move")
        popup.present(
            anchor,
            MoveLinkTip(title="1. e4", subtitle="Miss", details=(("CPL", "1"),)),
            is_flipped=False,
        )
        short_width = popup.width()
        popup.present(
            anchor,
            MoveLinkTip(
                title="21. b6",
                subtitle="Missed capture",
                details=(
                    ("Engine line", "Nxe3"),
                    ("Played", "b6 (Miss)"),
                    ("CPL", "154"),
                ),
            ),
            is_flipped=False,
        )
        self.assertGreater(popup.width(), short_width)
        self.assertGreaterEqual(popup._subtitle.width(), popup._subtitle.minimumWidth())
        self.assertLessEqual(popup._title.y() + popup._title.height(), popup._subtitle.y())
        self.assertFalse(popup._title.geometry().intersects(popup._subtitle.geometry()))
        self._assert_values_share_a_column(popup)
        popup.hide()
        anchor.hide()

    def test_second_hover_with_board_does_not_stack_detail_rows(self) -> None:
        _app = QApplication.instance() or QApplication([])
        popup = MoveLinkPopup(
            {
                "ui": {
                    "styles": {
                        "tooltip": {
                            "show_position_board": True,
                            "position_board_size": 112,
                            "hover_delay_ms": 0,
                        }
                    }
                }
            }
        )
        anchor = QLabel("21. b6")
        anchor.resize(40, 16)
        anchor.show()
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        popup.present(
            anchor,
            MoveLinkTip(
                title="1. e4",
                subtitle="Miss",
                details=(("CPL", "12"),),
                fen=fen,
                arrow_uci="e2e4",
            ),
            is_flipped=False,
        )
        popup.present(
            anchor,
            MoveLinkTip(
                title="21. b6",
                subtitle="Missed capture",
                details=(
                    ("Engine line", "Nxe3"),
                    ("Played", "b6 (Miss)"),
                    ("CPL", "154"),
                ),
                fen=fen,
                arrow_uci="e2e4",
            ),
            is_flipped=False,
        )
        self.assertFalse(popup._title.geometry().intersects(popup._subtitle.geometry()))
        self._assert_values_share_a_column(popup)
        popup.hide()
        anchor.hide()

    def _assert_values_share_a_column(self, popup: MoveLinkPopup) -> None:
        value_xs = []
        name_widths = []
        previous_y = -1
        for index in range(popup._details_layout.count()):
            row = popup._details_layout.itemAt(index).widget()
            name = row.layout().itemAt(0).widget()
            value = row.layout().itemAt(1).widget()
            self.assertFalse(name.geometry().intersects(value.geometry()))
            self.assertEqual(value.x() - (name.x() + name.width()), row.layout().spacing())
            self.assertGreater(row.y(), previous_y)
            value_xs.append(value.x())
            name_widths.append(name.width())
            previous_y = row.y()
        self.assertEqual(len(set(value_xs)), 1)
        self.assertEqual(len(set(name_widths)), 1)

    def test_board_draws_played_arrow_and_a_different_alternative(self) -> None:
        _app = QApplication.instance() or QApplication([])
        popup = self._arrow_popup(show_alternative=True)
        anchor = QLabel("21. b6")
        anchor.resize(40, 16)
        anchor.show()
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        popup.present(
            anchor,
            MoveLinkTip(
                title="21. b6",
                subtitle="Missed capture",
                fen=fen,
                arrow_uci="e2e4",
                alternative_uci="d2d4",
            ),
            is_flipped=False,
        )
        arrows = popup._board._arrows
        self.assertEqual([move.uci() for move, _color in arrows], ["e2e4", "d2d4"])
        self.assertEqual(list(arrows[0][1]), [255, 255, 0])
        self.assertEqual(list(arrows[1][1]), [200, 0, 100])

        popup.present(
            anchor,
            MoveLinkTip(
                title="1. e4",
                subtitle="Best Move",
                fen=fen,
                arrow_uci="e2e4",
                alternative_uci="e2e4",
            ),
            is_flipped=False,
        )
        self.assertEqual([move.uci() for move, _color in popup._board._arrows], ["e2e4"])
        popup.hide()
        anchor.hide()

    def test_long_subtitle_wraps_inside_the_popup(self) -> None:
        _app = QApplication.instance() or QApplication([])
        popup = self._arrow_popup(show_alternative=False)
        anchor = QLabel("12. Nf3")
        anchor.show()
        description = (
            "White secured the bishop pair by exchanging the light-squared bishop "
            "and leaving Black with doubled pawns on the queenside"
        )
        popup.present(
            anchor,
            MoveLinkTip(title="12. Nf3", subtitle=description, details=(("CPL", "18"),)),
            is_flipped=False,
        )
        self.assertLessEqual(popup._subtitle.width(), 280)
        self.assertGreater(popup._subtitle.height(), popup._title.height())
        self.assertFalse(popup._title.geometry().intersects(popup._subtitle.geometry()))
        self._assert_values_share_a_column(popup)
        popup.hide()
        anchor.hide()

    def test_best_alternative_arrow_can_be_turned_off(self) -> None:
        _app = QApplication.instance() or QApplication([])
        popup = self._arrow_popup(show_alternative=False)
        anchor = QLabel("21. b6")
        anchor.show()
        popup.present(
            anchor,
            MoveLinkTip(
                title="21. b6",
                subtitle="Miss",
                fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                arrow_uci="e2e4",
                alternative_uci="d2d4",
            ),
            is_flipped=False,
        )
        arrows = popup._board._arrows
        self.assertEqual([move.uci() for move, _color in arrows], ["e2e4"])
        self.assertEqual(list(arrows[0][1]), [255, 255, 0])
        popup.hide()
        anchor.hide()

    def _arrow_popup(self, *, show_alternative: bool) -> MoveLinkPopup:
        return MoveLinkPopup(
            {
                "ui": {
                    "styles": {
                        "tooltip": {
                            "show_position_board": True,
                            "position_board_size": 112,
                            "hover_delay_ms": 0,
                            "played_move_arrow_color": [255, 255, 0],
                            "show_best_alternative_arrow": show_alternative,
                            "best_alternative_arrow_color": [200, 0, 100],
                        }
                    }
                }
            }
        )


if __name__ == "__main__":
    unittest.main()

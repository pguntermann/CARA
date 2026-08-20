"""Game Info header view for main panel."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.services.opening_encyclopedia_service import OpeningEncyclopediaService
from app.services.opening_service import OPENING_STARTING, OPENING_UNKNOWN
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.themed_icon import SVG_MENU_INFO, themed_icon_from_svg
from app.views.dialogs.opening_encyclopedia_dialog import OpeningEncyclopediaDialog


class MainGameInfoView(QWidget):
    """Game information header view displaying player names, ELOs, and opening."""

    # Emitted when menu/context "Opening Encyclopedia" should enable/disable
    # (encyclopedia DB available + resolvable entry for current opening).
    encyclopedia_openable_changed = pyqtSignal(bool)

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the game info view.

        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        self.config = config
        self._encyclopedia = OpeningEncyclopediaService.get_instance(config)
        self._current_eco = ""
        self._current_name = ""
        self._current_fen = ""
        self._encyclopedia_openable = False
        self._setup_ui()
        self._refresh_encyclopedia_openable(emit=True)

    def _encyclopedia_link_config(self) -> Dict[str, Any]:
        # Prefer gameinfo-local settings; fall back to Opening Explorer link config.
        ui = self.config.get("ui", {})
        gameinfo = ui.get("panels", {}).get("main", {}).get("gameinfo", {})
        local = gameinfo.get("encyclopedia_link", {})
        if isinstance(local, dict) and local:
            return local
        explorer = ui.get("panels", {}).get("detail", {}).get("opening_explorer", {})
        remote = explorer.get("encyclopedia_link", {})
        return remote if isinstance(remote, dict) else {}

    def _setup_ui(self) -> None:
        """Setup the game info UI."""
        layout = QVBoxLayout(self)

        # Get gameinfo config
        ui_config = self.config.get("ui", {})
        panel_config = ui_config.get("panels", {}).get("main", {})
        gameinfo_config = panel_config.get("gameinfo", {})

        # Padding: left, top, right, bottom (Qt setContentsMargins order)
        padding = gameinfo_config.get("padding", [10, 18, 10, 10])
        self._margin_base_ltrb = (int(padding[0]), int(padding[1]), int(padding[2]), int(padding[3]))
        layout.setContentsMargins(*self._margin_base_ltrb)
        self._outer_layout = layout
        spacing = gameinfo_config.get("spacing", 8)
        layout.setSpacing(spacing)

        # Get font settings
        font_family = resolve_font_family(gameinfo_config.get("font_family", "Helvetica Neue"))
        player_name_size = int(scale_font_size(gameinfo_config.get("player_name_size", 16)))
        player_elo_size = int(scale_font_size(gameinfo_config.get("player_elo_size", 12)))
        opening_size = int(scale_font_size(gameinfo_config.get("opening_size", 14)))
        text_color = gameinfo_config.get("text_color", [240, 240, 240])
        self._text_color = list(text_color) if isinstance(text_color, (list, tuple)) else [240, 240, 240]

        # Get colors
        color_rgb = f"rgb({self._text_color[0]}, {self._text_color[1]}, {self._text_color[2]})"

        # Players row (both on same line)
        players_layout = QHBoxLayout()
        players_layout.setSpacing(8)
        players_layout.addStretch()

        white_name_font = QFont(font_family, player_name_size)
        white_elo_font = QFont(font_family, player_elo_size)

        self.white_name_label = QLabel("Player 1")
        self.white_name_label.setFont(white_name_font)
        self.white_name_label.setStyleSheet(f"color: {color_rgb}; font-weight: 600;")
        players_layout.addWidget(self.white_name_label)

        self.white_elo_label = QLabel("(1800)")
        self.white_elo_label.setFont(white_elo_font)
        self.white_elo_label.setStyleSheet(f"color: {color_rgb};")
        players_layout.addWidget(self.white_elo_label)

        # Result (replaces separator)
        result_config = gameinfo_config.get("result", {})
        result_size = int(scale_font_size(result_config.get("font_size", gameinfo_config.get("player_name_size", 16))))
        result_font = QFont(font_family, result_size)

        self.result_label = QLabel("*")
        self.result_label.setFont(result_font)
        self.result_label.setStyleSheet(f"color: {color_rgb}; font-weight: 600;")
        players_layout.addWidget(self.result_label)

        black_name_font = QFont(font_family, player_name_size)
        black_elo_font = QFont(font_family, player_elo_size)

        self.black_name_label = QLabel("Player 2")
        self.black_name_label.setFont(black_name_font)
        self.black_name_label.setStyleSheet(f"color: {color_rgb}; font-weight: 600;")
        players_layout.addWidget(self.black_name_label)

        self.black_elo_label = QLabel("(2000)")
        self.black_elo_label.setFont(black_elo_font)
        self.black_elo_label.setStyleSheet(f"color: {color_rgb};")
        players_layout.addWidget(self.black_elo_label)

        players_layout.addStretch()
        layout.addLayout(players_layout)

        # Opening row
        opening_layout = QHBoxLayout()
        opening_layout.setSpacing(6)
        opening_layout.addStretch()

        opening_font = QFont(font_family, opening_size)

        self.opening_label = QLabel("A00 - Unknown Opening")
        self.opening_label.setFont(opening_font)
        self.opening_label.setStyleSheet(f"color: {color_rgb};")
        opening_layout.addWidget(self.opening_label)

        enc_cfg = self._encyclopedia_link_config()
        self._encyclopedia_enabled = bool(enc_cfg.get("enabled", True))
        tooltip = str(enc_cfg.get("tooltip", "Opening encyclopedia"))
        btn_size = int(enc_cfg.get("button_size", max(18, opening_size + 6)))
        icon_size = max(12, btn_size - 6)

        self._encyclopedia_btn = QToolButton()
        self._encyclopedia_btn.setToolTip(tooltip)
        self._encyclopedia_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._encyclopedia_btn.setAutoRaise(True)
        self._encyclopedia_btn.setFixedSize(btn_size, btn_size)
        self._encyclopedia_btn.setIconSize(QSize(icon_size, icon_size))
        self._encyclopedia_btn.setVisible(False)
        icon = themed_icon_from_svg(SVG_MENU_INFO, self._text_color)
        if icon.isNull():
            self._encyclopedia_btn.setText("ⓘ")
            self._encyclopedia_btn.setStyleSheet(
                f"""
                QToolButton {{
                    color: {color_rgb};
                    background: transparent;
                    border: none;
                    padding: 0px;
                    font-size: {max(10, opening_size - 2)}pt;
                }}
                QToolButton:hover {{
                    background: transparent;
                }}
                """
            )
        else:
            self._encyclopedia_btn.setIcon(icon)
            self._encyclopedia_btn.setStyleSheet(
                """
                QToolButton {
                    background: transparent;
                    border: none;
                    padding: 0px;
                }
                QToolButton:hover {
                    background: transparent;
                }
                """
            )
        self._encyclopedia_btn.clicked.connect(self._open_encyclopedia)
        opening_layout.addWidget(self._encyclopedia_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        opening_layout.addStretch()
        layout.addLayout(opening_layout)

        # Center align layout
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_centering_margin_extras(self, extra_left: int, extra_right: int) -> None:
        """Add horizontal margin so content can align with the board column (extras >= 0)."""
        l0, t0, r0, b0 = self._margin_base_ltrb
        el = max(0, int(extra_left))
        er = max(0, int(extra_right))
        self._outer_layout.setContentsMargins(l0 + el, t0, r0 + er, b0)

    def set_white_player(self, name: str, elo: int) -> None:
        """Set white player name and ELO.

        Args:
            name: Player name.
            elo: Player ELO rating.
        """
        self.white_name_label.setText(name)
        self.white_elo_label.setText(f"({elo})")

    def set_black_player(self, name: str, elo: int) -> None:
        """Set black player name and ELO.

        Args:
            name: Player name.
            elo: Player ELO rating.
        """
        self.black_name_label.setText(name)
        self.black_elo_label.setText(f"({elo})")

    def set_result(self, result: str) -> None:
        """Set game result.

        Args:
            result: Game result (e.g., "1-0", "0-1", "1/2-1/2", "*").
        """
        # Format result for display
        if result == "1-0":
            display_result = "1 - 0"
        elif result == "0-1":
            display_result = "0 - 1"
        elif result == "1/2-1/2":
            display_result = "1/2 - 1/2"
        else:
            # Default to "*" for unknown/unfinished games
            display_result = "*"

        self.result_label.setText(display_result)

    def set_opening(self, eco: str, name: str, fen: Optional[str] = None) -> None:
        """Set opening ECO code and name.

        Args:
            eco: ECO code (e.g., "A00").
            name: Opening name (e.g., "Unknown Opening").
            fen: Last named eco-book FEN, when known.
        """
        self._current_eco = eco or ""
        self._current_name = name or ""
        self._current_fen = (fen or "").strip()
        self.opening_label.setText(f"{eco} - {name}")
        self._refresh_encyclopedia_openable(emit=True)
        self._update_encyclopedia_button()

    def is_encyclopedia_openable(self) -> bool:
        """True when Board/context Opening Encyclopedia should be enabled.

        Requires: encyclopedia DB available, a real opening name (not Starting /
        Unknown), and a resolvable encyclopedia entry for name+ECO.
        """
        return bool(self._encyclopedia_openable)

    def _compute_encyclopedia_openable(self) -> bool:
        if not self._encyclopedia.available:
            return False
        if not self._current_name:
            return False
        if self._current_name in (OPENING_UNKNOWN.name, OPENING_STARTING.name):
            return False
        return self._encyclopedia.has_entry(
            self._current_name, self._current_eco, fen=self._current_fen or None
        )

    def _refresh_encyclopedia_openable(self, *, emit: bool) -> None:
        openable = self._compute_encyclopedia_openable()
        if openable == self._encyclopedia_openable:
            return
        self._encyclopedia_openable = openable
        if emit:
            self.encyclopedia_openable_changed.emit(openable)

    def _update_encyclopedia_button(self) -> None:
        # Header ⓘ also requires the link toggle and a visible game-info header.
        show = (
            self._encyclopedia_enabled
            and self.isVisible()
            and self._encyclopedia_openable
        )
        self._encyclopedia_btn.setVisible(show)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        # Visibility of the header itself may change via board model; refresh icon.
        self._update_encyclopedia_button()

    def _open_encyclopedia(self) -> None:
        self.open_encyclopedia()

    def open_encyclopedia(self) -> None:
        """Open the encyclopedia for the current opening (same as the info button)."""
        if not self.is_encyclopedia_openable():
            return
        entry = self._encyclopedia.lookup(
            self._current_name, self._current_eco, fen=self._current_fen or None
        )
        if entry is None:
            return
        OpeningEncyclopediaDialog.show_entry(
            self.config,
            entry,
            self._encyclopedia,
            parent=self.window(),
        )

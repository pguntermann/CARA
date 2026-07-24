"""Opening Explorer detail view — path to current ply and book continuations."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

import chess
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.game_model import GameModel
from app.services.opening_service import (
    OPENING_STARTING,
    OPENING_UNKNOWN,
    OpeningContinuation,
    OpeningPathStep,
    OpeningService,
)
from app.utils.external_open import open_url
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget

_DENSITY_ORDER = ("compact", "comfortable", "gallery")
# Coalesce move + board.position signals (and rapid ply steps) without feeling laggy.
_REFRESH_COALESCE_MS = 25
# If the board view never emits navigation_settled (no widget connected), still refresh.
_REFRESH_SETTLED_FALLBACK_MS = 450
_DENSITY_FALLBACK_PRESETS: Dict[str, Dict[str, Any]] = {
    "compact": {
        "mini_size": 96,
        "hero_size": 112,
        "row_spacing": 6,
        "flow_boards": False,
    },
    "comfortable": {
        "mini_size": 128,
        "hero_size": 160,
        "row_spacing": 8,
        "flow_boards": False,
    },
    "gallery": {
        "mini_size": 140,
        "hero_size": 180,
        "row_spacing": 10,
        "flow_boards": True,
    },
}


def _as_box(value: Any, default: Sequence[int]) -> tuple[int, int, int, int]:
    """Normalize a 4-int margins/padding list from config."""
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
    return (int(default[0]), int(default[1]), int(default[2]), int(default[3]))


def _as_pair(value: Any, default: Sequence[int]) -> tuple[int, int]:
    """Normalize a 2-int padding pair from config."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (int(value[0]), int(value[1]))
    return (int(default[0]), int(default[1]))


def _mini_board_border_size(config: Dict[str, Any]) -> int:
    """Outer frame width from shared ui.styles.mini_board (px each side)."""
    border = (
        config.get("ui", {})
        .get("styles", {})
        .get("mini_board", {})
        .get("border", {})
    )
    if isinstance(border, dict) and "size" in border:
        return max(0, int(border["size"]))
    return 4


def _mini_board_outer_size(config: Dict[str, Any], board_size: int) -> int:
    """Full mini-board widget size including border on both sides."""
    return int(board_size) + 2 * _mini_board_border_size(config)


def _open_lichess_url(url: str) -> None:
    if not url:
        return
    open_url(QUrl(url), context="opening_explorer.lichess")


def _make_lichess_button(*, colors: Dict[str, Any], tooltip: str, on_click) -> QToolButton:
    btn = QToolButton()
    btn.setText("↗")
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoRaise(True)
    size = int(colors.get("expand_button_size", 28))
    font_size = max(12, int(colors.get("expand_font_size", 16)) - 2)
    btn.setFixedSize(size, size)
    tc = colors["text"]
    mc = colors["muted"]
    btn.setStyleSheet(
        f"""
        QToolButton {{
            color: rgb({tc[0]}, {tc[1]}, {tc[2]});
            background: transparent;
            border: none;
            padding: 0px;
            font-size: {font_size}pt;
            font-weight: bold;
        }}
        QToolButton:hover {{
            color: rgb({tc[0]}, {tc[1]}, {tc[2]});
            background: transparent;
        }}
        QToolButton:disabled {{
            color: rgb({mc[0]}, {mc[1]}, {mc[2]});
        }}
        """
    )
    btn.clicked.connect(on_click)
    return btn


def _format_san_line(sans: Sequence[str]) -> str:
    """Format SAN plies as a compact move list (1.e4 e5 2.Nf3 …)."""
    if not sans:
        return "Start"
    parts: List[str] = []
    for i, san in enumerate(sans):
        if i % 2 == 0:
            parts.append(f"{(i // 2) + 1}.{san}")
        else:
            parts.append(san)
    return " ".join(parts)


class _FlowWrap(QWidget):
    """Wrapping flow container (chips or gallery cards) with no scrollbar / frame.

    When ``uniform_size`` is set, items are placed on a regular column grid using
    that cell size (avoids ragged gallery rows from mixed sizeHints).
    """

    def __init__(self, spacing: int = 4, parent=None) -> None:
        super().__init__(parent)
        self._spacing = int(spacing)
        self._items: List[QWidget] = []
        self._uniform_size: Optional[QSize] = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def clear_items(self) -> None:
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items = []
        self.setMinimumHeight(0)
        self.updateGeometry()

    def set_uniform_size(self, size: Optional[QSize]) -> None:
        self._uniform_size = QSize(size) if size is not None else None

    def set_items(self, items: List[QWidget]) -> None:
        self.clear_items()
        self._items = list(items)
        for item in self._items:
            item.setParent(self)
            if self._uniform_size is not None:
                item.setFixedSize(self._uniform_size)
            item.show()
        self._layout_items()
        self.updateGeometry()

    # Back-compat aliases used by breadcrumb code paths.
    def clear_chips(self) -> None:
        self.clear_items()

    def set_chips(self, chips: List[QToolButton]) -> None:
        self._uniform_size = None
        self.set_items(list(chips))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_items()

    def sizeHint(self) -> QSize:
        return QSize(200, max(1, self.minimumHeight()))

    def _layout_items(self) -> None:
        if not self._items:
            self.setMinimumHeight(0)
            return
        w_total = max(1, int(self.width()))
        spacing = max(1, int(self._spacing))

        if self._uniform_size is not None:
            cw = max(1, int(self._uniform_size.width()))
            ch = max(1, int(self._uniform_size.height()))
            cols = max(1, (w_total + spacing) // (cw + spacing))
            for i, item in enumerate(self._items):
                col = i % cols
                row = i // cols
                x = col * (cw + spacing)
                y = row * (ch + spacing)
                item.setGeometry(int(x), int(y), int(cw), int(ch))
            rows = (len(self._items) + cols - 1) // cols
            self.setMinimumHeight(int(rows * ch + max(0, rows - 1) * spacing))
            return

        x = 0
        y = 0
        line_h = 0
        for item in self._items:
            try:
                item.ensurePolished()
                item.adjustSize()
            except Exception:
                pass
            sh = item.sizeHint()
            cw = max(int(item.minimumWidth()), int(sh.width()), 1)
            ch = max(int(item.minimumHeight()), int(sh.height()), 1)
            if x > 0 and x + cw > w_total:
                x = 0
                y += line_h + spacing
                line_h = 0
            item.setGeometry(int(x), int(y), int(min(cw, w_total)), int(ch))
            x += min(cw, w_total) + spacing
            line_h = max(line_h, ch)
        self.setMinimumHeight(int(y + line_h))


# Keep old name as alias for readability at call sites that still say "breadcrumb".
_BreadcrumbWrap = _FlowWrap


class DetailOpeningExplorerView(QWidget):
    """Detail tab: opening lines played to the current ply, plus expandable book continuations."""

    def __init__(
        self,
        config: Dict[str, Any],
        game_model: Optional[GameModel] = None,
        game_controller=None,
        opening_service: Optional[OpeningService] = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._game_controller = None
        self._opening_service = opening_service
        self._path_show_all = False
        self._last_game_id: Any = None
        self._path_height_anim: Optional[QPropertyAnimation] = None
        self._cont_fade_anim: Optional[QPropertyAnimation] = None
        self._path_layout_is_flow = False
        self._current_path_row: Optional[QWidget] = None
        self._focused_continuation: Optional[QWidget] = None
        self._refresh_dirty = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_COALESCE_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self._load_config()
        self._setup_ui()
        if game_controller is not None:
            self.set_game_controller(game_controller)
        if game_model is not None:
            self.set_game_model(game_model)

    def _explorer_config(self) -> Dict[str, Any]:
        return (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("opening_explorer", {})
        )

    def _load_config(self) -> None:
        cfg = self._explorer_config()
        self._row_spacing = int(cfg.get("row_spacing", 8))
        self._section_spacing = int(cfg.get("section_spacing", 12))
        self._padding = cfg.get("padding", [8, 8, 8, 8])
        if not isinstance(self._padding, list) or len(self._padding) < 4:
            self._padding = [8, 8, 8, 8]

        tabs = self.config.get("ui", {}).get("panels", {}).get("detail", {}).get("tabs", {})
        self._font_family = resolve_font_family(tabs.get("font_family", "Helvetica Neue"))
        self._font_size = scale_font_size(cfg.get("font_size", tabs.get("font_size", 10)))
        self._title_font_size = scale_font_size(cfg.get("title_font_size", 11))

        colors = cfg.get("colors", {})
        self._title_color = colors.get("title", [200, 200, 200])
        self._text_color = colors.get("text", [200, 200, 200])
        self._muted_color = colors.get("muted", [150, 150, 155])
        self._gap_color = colors.get("gap", [200, 160, 100])
        self._row_bg = colors.get("row_background", [45, 45, 50])
        self._row_border = colors.get("row_border", [60, 60, 65])
        self._current_badge_bg = colors.get("current_badge_background", [70, 90, 130])
        self._current_badge_text = colors.get("current_badge_text", [240, 240, 240])
        self._played_next_badge_bg = colors.get("played_next_badge_background", [90, 120, 80])
        self._played_next_badge_text = colors.get("played_next_badge_text", [240, 240, 240])
        self._current_row_border = colors.get("current_row_border", [110, 140, 190])
        self._chip_bg = colors.get("chip_background", self._row_bg)
        self._chip_border = colors.get("chip_border", self._row_border)
        self._chip_active_bg = colors.get("chip_active_background", self._current_badge_bg)
        self._chip_active_text = colors.get("chip_active_text", self._current_badge_text)
        self._pane_bg = tabs.get("pane_background", [40, 40, 45])

        self._show_arrows = bool(cfg.get("show_move_arrows", True))
        self._max_depth = int(cfg.get("max_continuation_depth", OpeningService.MAX_CONTINUATION_DEPTH))
        self._empty_text = cfg.get("placeholder_text_no_game", "No game selected.")
        self._focus_dim_opacity = float(cfg.get("focus_dim_opacity", 0.38))

        expand_cfg = cfg.get("expand_button", {})
        self._expand_font_size = int(scale_font_size(expand_cfg.get("font_size", 16)))
        self._expand_button_size = int(expand_cfg.get("size", 28))

        lichess_cfg = cfg.get("lichess_link", {})
        self._lichess_link_enabled = bool(lichess_cfg.get("enabled", True))
        self._lichess_link_tooltip = str(
            lichess_cfg.get("tooltip", "Open this opening on Lichess")
        )

        path_section = cfg.get("path_section", {})
        self._expanded_tail_count = int(path_section.get("expanded_tail_count", 4))
        self._animation_duration_ms = int(path_section.get("animation_duration_ms", 180))
        self._fade_duration_ms = int(path_section.get("fade_duration_ms", 120))
        if not hasattr(self, "_path_expanded"):
            self._path_expanded = not bool(path_section.get("collapsed_by_default", False))

        density_cfg = cfg.get("density", {})
        default_density = str(density_cfg.get("default", "gallery")).lower()
        presets_cfg = density_cfg.get("presets", {})
        self._density_presets: Dict[str, Dict[str, Any]] = {}
        for mode in _DENSITY_ORDER:
            fallback = _DENSITY_FALLBACK_PRESETS[mode]
            raw = presets_cfg.get(mode, {}) if isinstance(presets_cfg, dict) else {}
            if not isinstance(raw, dict):
                raw = {}
            self._density_presets[mode] = {
                "mini_size": int(raw.get("mini_size", fallback["mini_size"])),
                "hero_size": int(raw.get("hero_size", fallback["hero_size"])),
                "row_spacing": int(raw.get("row_spacing", fallback["row_spacing"])),
                "flow_boards": bool(raw.get("flow_boards", fallback["flow_boards"])),
            }

        layout_cfg = cfg.get("layout", {})
        if not isinstance(layout_cfg, dict):
            layout_cfg = {}
        self._path_header_spacing = int(layout_cfg.get("path_header_spacing", 6))
        self._path_compact_spacing = int(layout_cfg.get("path_compact_spacing", 6))
        self._breadcrumb_spacing = int(layout_cfg.get("breadcrumb_spacing", 4))

        path_step_cfg = layout_cfg.get("path_step", {})
        if not isinstance(path_step_cfg, dict):
            path_step_cfg = {}
        gallery_cfg = path_step_cfg.get("gallery", {})
        if not isinstance(gallery_cfg, dict):
            gallery_cfg = {}
        self._gallery_tile_extra_width = int(gallery_cfg.get("tile_extra_width", 24))
        self._gallery_tile_extra_height = int(gallery_cfg.get("tile_extra_height", 56))

        if not hasattr(self, "_density_mode"):
            self._density_mode = default_density if default_density in self._density_presets else "gallery"
        self._apply_density_preset()
        # Shared mini-board size feeds the comfortable preset baseline.
        cfg_mini = (
            self.config.get("ui", {}).get("styles", {}).get("mini_board", {}).get("size")
        )
        if cfg_mini is not None and self._density_mode == "comfortable":
            comfort = self._density_presets.get("comfortable", _DENSITY_FALLBACK_PRESETS["comfortable"])
            hero_extra = int(comfort["hero_size"]) - int(comfort["mini_size"])
            self._mini_size = int(cfg_mini)
            self._hero_size = int(cfg_mini) + max(0, hero_extra)

        placeholder = cfg.get("placeholder", {})
        self._placeholder_text_color = placeholder.get("text_color", [150, 150, 150])
        self._placeholder_font_size = int(scale_font_size(placeholder.get("font_size", 14)))
        self._placeholder_padding = int(placeholder.get("padding", 20))

    def _apply_density_preset(self) -> None:
        preset = self._density_presets.get(
            self._density_mode,
            self._density_presets.get("comfortable", _DENSITY_FALLBACK_PRESETS["comfortable"]),
        )
        self._mini_size = int(preset["mini_size"])
        self._hero_size = int(preset["hero_size"])
        self._row_spacing = int(preset["row_spacing"])
        self._horizontal_path = bool(preset.get("flow_boards", False))
        self._flow_boards = self._horizontal_path

    def _continuation_colors(self) -> Dict[str, Any]:
        return {
            "text": self._text_color,
            "muted": self._muted_color,
            "row_bg": self._row_bg,
            "row_border": self._row_border,
            "badge_bg": self._current_badge_bg,
            "badge_text": self._current_badge_text,
            "played_next_badge_bg": self._played_next_badge_bg,
            "played_next_badge_text": self._played_next_badge_text,
            "font_family": self._font_family,
            "font_size": self._font_size,
            "expand_font_size": self._expand_font_size,
            "expand_button_size": self._expand_button_size,
            "lichess_link_enabled": self._lichess_link_enabled,
            "lichess_link_tooltip": self._lichess_link_tooltip,
        }

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(
            int(self._padding[0]),
            int(self._padding[1]),
            int(self._padding[2]),
            int(self._padding[3]),
        )
        self._content_layout.setSpacing(self._section_spacing)

        self._path_header_row = QWidget()
        self._path_header_row.setVisible(False)
        self._path_header_row.setCursor(Qt.CursorShape.PointingHandCursor)
        path_header_layout = QHBoxLayout(self._path_header_row)
        path_header_layout.setContentsMargins(0, 0, 0, 0)
        path_header_layout.setSpacing(self._path_header_spacing)

        self._path_toggle = QToolButton()
        self._path_toggle.setCheckable(True)
        self._path_toggle.setChecked(self._path_expanded)
        self._path_toggle.setAutoRaise(True)
        self._path_toggle.setFixedSize(self._expand_button_size, self._expand_button_size)
        self._path_toggle.toggled.connect(self._on_path_toggled)
        path_header_layout.addWidget(self._path_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self._path_header = QLabel("Lines until here")
        path_header_layout.addWidget(self._path_header, 1, Qt.AlignmentFlag.AlignVCenter)

        # Explicit three-way density switch (Compact | Comfort | Gallery).
        self._density_switch = QWidget()
        density_layout = QHBoxLayout(self._density_switch)
        density_layout.setContentsMargins(0, 0, 0, 0)
        density_layout.setSpacing(0)
        self._density_group = QButtonGroup(self)
        self._density_group.setExclusive(True)
        self._density_buttons: Dict[str, QToolButton] = {}
        density_labels = (("compact", "Compact"), ("comfortable", "Comfort"), ("gallery", "Gallery"))
        for mode, label in density_labels:
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setAutoRaise(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Board density: {label}")
            self._density_group.addButton(btn)
            self._density_buttons[mode] = btn
            density_layout.addWidget(btn)
            btn.clicked.connect(lambda checked=False, m=mode: self._on_density_selected(m))
        path_header_layout.addWidget(self._density_switch, 0, Qt.AlignmentFlag.AlignVCenter)

        self._path_header_row.mousePressEvent = self._path_header_mouse_press  # type: ignore[method-assign]

        # Compact context always visible when a path exists (summary + breadcrumbs).
        self._path_compact = QWidget()
        self._path_compact.setVisible(False)
        compact_layout = QVBoxLayout(self._path_compact)
        compact_layout.setContentsMargins(0, 0, 0, 0)
        compact_layout.setSpacing(self._path_compact_spacing)

        self._path_summary = QLabel("")
        self._path_summary.setWordWrap(True)
        self._path_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        compact_layout.addWidget(self._path_summary)

        self._breadcrumb_wrap = _BreadcrumbWrap(spacing=self._breadcrumb_spacing)
        self._breadcrumb_wrap.setVisible(False)
        compact_layout.addWidget(self._breadcrumb_wrap)

        # Expandable board gallery. List modes use a vertical stack; gallery uses a
        # wrapping flow (no nested scroll area / border — outer detail scroll handles overflow).
        self._path_boards_host = QWidget()
        self._path_boards_host.setVisible(False)
        self._path_boards_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._boards_host_layout = QVBoxLayout(self._path_boards_host)
        self._boards_host_layout.setContentsMargins(0, 0, 0, 0)
        self._boards_host_layout.setSpacing(self._row_spacing)

        self._path_show_earlier_btn = QToolButton()
        self._path_show_earlier_btn.setAutoRaise(True)
        self._path_show_earlier_btn.setVisible(False)
        self._path_show_earlier_btn.clicked.connect(self._on_show_all_path)
        self._boards_host_layout.addWidget(self._path_show_earlier_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self._path_wrap = QWidget()
        self._path_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._path_container = QVBoxLayout(self._path_wrap)
        self._path_container.setContentsMargins(0, 0, 0, 0)
        self._path_container.setSpacing(self._row_spacing)
        self._boards_host_layout.addWidget(self._path_wrap)

        self._path_flow = _FlowWrap(spacing=self._row_spacing)
        self._path_flow.setVisible(False)
        self._boards_host_layout.addWidget(self._path_flow)
        self._path_layout_is_flow = False

        self._cont_header = QLabel("Lines from here")
        self._cont_header.setVisible(False)
        self._cont_wrap = QWidget()
        self._cont_container = QVBoxLayout(self._cont_wrap)
        self._cont_container.setContentsMargins(0, 0, 0, 0)
        self._cont_container.setSpacing(self._row_spacing)

        # Summary/breadcrumbs stay visible; expand header sits directly above the boards it toggles.
        self._content_layout.addWidget(self._path_compact)
        self._content_layout.addWidget(self._path_header_row)
        self._content_layout.addWidget(self._path_boards_host)
        self._content_layout.addWidget(self._cont_header)
        self._content_layout.addWidget(self._cont_wrap)
        self._content_layout.addStretch(1)
        scroll.setWidget(self._content)
        root.addWidget(scroll)

        self._empty_label = QLabel(self._empty_text)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._empty_label)

        self._apply_styling()
        self._sync_path_toggle_chrome(animate=False)
        self._update_density_switch()
        self._set_empty_visible(True)

    def _apply_styling(self) -> None:
        bg = self._pane_bg
        self.setStyleSheet(
            f"DetailOpeningExplorerView {{ background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); }}"
        )
        self._content.setStyleSheet(f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});")

        from app.views.style import StyleManager

        scroll_cfg = self._explorer_config().get("scroll_area", {})
        border_offset = int(scroll_cfg.get("border_color_offset", 20))
        border_color = [
            min(255, bg[0] + border_offset),
            min(255, bg[1] + border_offset),
            min(255, bg[2] + border_offset),
        ]
        StyleManager.style_scroll_area(
            self._scroll,
            self.config,
            bg,
            border_color,
            0,
        )

        title_c = self._title_color
        title_font = QFont(self._font_family, int(self._title_font_size))
        title_font.setBold(True)
        for header in (self._path_header, self._cont_header):
            header.setFont(title_font)
            header.setStyleSheet(
                f"color: rgb({title_c[0]}, {title_c[1]}, {title_c[2]}); background: transparent;"
            )
        tc = self._text_color
        mc = self._muted_color
        tool_ss = f"""
            QToolButton {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                background: transparent;
                border: none;
                padding: 0px;
                font-size: {self._expand_font_size}pt;
                font-weight: bold;
            }}
            QToolButton:checked {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                background: transparent;
            }}
            QToolButton:hover {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                background: transparent;
            }}
        """
        self._path_toggle.setStyleSheet(tool_ss)
        self._style_density_switch()
        self._path_show_earlier_btn.setStyleSheet(
            f"""
            QToolButton {{
                color: rgb({mc[0]}, {mc[1]}, {mc[2]});
                background: transparent;
                border: none;
                padding: 2px 0px;
                font-size: {max(8, int(self._font_size))}pt;
            }}
            QToolButton:hover {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
            }}
            """
        )
        self._path_summary.setFont(QFont(self._font_family, int(self._font_size)))
        self._path_summary.setStyleSheet(
            f"color: rgb({tc[0]}, {tc[1]}, {tc[2]}); background: transparent;"
        )
        pc = self._placeholder_text_color
        self._empty_label.setStyleSheet(
            f"""
            QLabel {{
                color: rgb({pc[0]}, {pc[1]}, {pc[2]});
                font-size: {self._placeholder_font_size}pt;
                padding: {self._placeholder_padding}px;
                background: transparent;
            }}
            """
        )

    def _style_density_switch(self) -> None:
        """Style the Compact | Comfort | Gallery segmented control."""
        tc = self._text_color
        mc = self._muted_color
        border = self._row_border
        inactive_bg = self._row_bg
        active_bg = self._chip_active_bg
        active_tc = self._chip_active_text
        font_pt = max(8, int(self._font_size))
        modes = list(_DENSITY_ORDER)
        for i, mode in enumerate(modes):
            btn = self._density_buttons[mode]
            radius_left = "4px" if i == 0 else "0px"
            radius_right = "4px" if i == len(modes) - 1 else "0px"
            # Overlap borders between segments so the group reads as one control.
            margin_left = "-1px" if i > 0 else "0px"
            btn.setStyleSheet(
                f"""
                QToolButton {{
                    color: rgb({mc[0]}, {mc[1]}, {mc[2]});
                    background-color: rgb({inactive_bg[0]}, {inactive_bg[1]}, {inactive_bg[2]});
                    border: 1px solid rgb({border[0]}, {border[1]}, {border[2]});
                    border-top-left-radius: {radius_left};
                    border-bottom-left-radius: {radius_left};
                    border-top-right-radius: {radius_right};
                    border-bottom-right-radius: {radius_right};
                    margin-left: {margin_left};
                    padding: 3px 10px;
                    font-size: {font_pt}pt;
                }}
                QToolButton:hover {{
                    color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                }}
                QToolButton:checked {{
                    color: rgb({active_tc[0]}, {active_tc[1]}, {active_tc[2]});
                    background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                    border-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                    font-weight: bold;
                }}
                """
            )

    def _update_density_switch(self) -> None:
        for mode, btn in self._density_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(mode == self._density_mode)
            btn.blockSignals(False)

    def _on_density_selected(self, mode: str) -> None:
        if mode not in self._density_presets or mode == self._density_mode:
            self._update_density_switch()
            return
        self._density_mode = mode
        self._apply_density_preset()
        self._update_density_switch()
        self._path_container.setSpacing(self._row_spacing)
        self.refresh()

    def _sync_path_toggle_chrome(self, *, animate: bool = True) -> None:
        self._path_toggle.blockSignals(True)
        self._path_toggle.setChecked(self._path_expanded)
        self._path_toggle.blockSignals(False)
        self._path_toggle.setText("▾" if self._path_expanded else "▸")
        self._apply_path_boards_visibility(self._path_expanded, animate=animate)

    def _stop_path_anim(self) -> None:
        if self._path_height_anim is not None:
            try:
                self._path_height_anim.finished.disconnect()
            except TypeError:
                pass
            self._path_height_anim.stop()
            self._path_height_anim.deleteLater()
            self._path_height_anim = None
        # Drop any leftover opacity effect from a prior fade.
        if self._path_boards_host.graphicsEffect() is not None:
            self._path_boards_host.setGraphicsEffect(None)

    def _configure_path_scroll_for_density(self) -> None:
        """Show list stack or wrapping gallery flow (no nested scrollers)."""
        use_flow = bool(self._flow_boards)
        self._path_layout_is_flow = use_flow
        self._path_wrap.setVisible(not use_flow)
        self._path_flow.setVisible(use_flow)
        self._path_flow._spacing = max(1, int(self._row_spacing))
        self._boards_host_layout.setSpacing(self._row_spacing)
        self._path_container.setSpacing(self._row_spacing)
        self._path_boards_host.updateGeometry()

    def _apply_path_boards_visibility(self, expanded: bool, *, animate: bool = False) -> None:
        """Show/hide path boards; height comes from content (no max-height animation)."""
        self._stop_path_anim()
        self._path_boards_host.setMinimumHeight(0)
        self._path_boards_host.setMaximumHeight(16777215)

        if not expanded:
            self._path_boards_host.setVisible(False)
            return

        self._configure_path_scroll_for_density()
        self._path_boards_host.setVisible(True)
        self._path_boards_host.updateGeometry()

        if not animate or self._animation_duration_ms <= 0:
            return

        effect = QGraphicsOpacityEffect(self._path_boards_host)
        effect.setOpacity(0.0)
        self._path_boards_host.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(self._animation_duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _finished() -> None:
            if self._path_boards_host.graphicsEffect() is effect:
                self._path_boards_host.setGraphicsEffect(None)
            self._path_height_anim = None

        anim.finished.connect(_finished)
        self._path_height_anim = anim
        anim.start()

    def _on_path_toggled(self, checked: bool) -> None:
        self._path_expanded = bool(checked)
        self._sync_path_toggle_chrome(animate=True)

    def _on_show_all_path(self) -> None:
        self._path_show_all = True
        self.refresh()

    def _path_header_mouse_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            child = self._path_header_row.childAt(event.position().toPoint())
            if child is self._path_toggle or child is self._density_switch:
                return
            if isinstance(child, QToolButton):
                return
            # Clicks on density segments (nested under the switch widget).
            w = child
            while w is not None:
                if w is self._density_switch:
                    return
                w = w.parentWidget()
            self._path_toggle.toggle()

    def _set_empty_visible(self, visible: bool) -> None:
        if visible:
            self._empty_label.setText(self._empty_text)
            self._empty_label.show()
            self._scroll.hide()
            self._path_header_row.setVisible(False)
            self._path_compact.setVisible(False)
            self._apply_path_boards_visibility(False, animate=False)
            self._cont_header.setVisible(False)
            self._cont_wrap.setVisible(False)
        else:
            self._empty_label.hide()
            self._scroll.show()
            self._cont_wrap.setVisible(True)

    def set_game_model(self, model: GameModel) -> None:
        if self._game_model is not None:
            try:
                self._game_model.active_game_changed.disconnect(self._on_game_or_ply_changed)
                self._game_model.active_move_changed.disconnect(self._on_game_or_ply_changed)
            except TypeError:
                pass
        self._game_model = model
        if model is not None:
            model.active_game_changed.connect(self._on_game_or_ply_changed)
            model.active_move_changed.connect(self._on_game_or_ply_changed)
        self._request_refresh()

    def set_game_controller(self, game_controller) -> None:
        self._disconnect_board_signals()
        self._game_controller = game_controller
        if game_controller is not None and self._opening_service is None:
            self._opening_service = getattr(game_controller, "opening_service", None)
        self._connect_board_signals()
        self._request_refresh()

    def set_opening_service(self, opening_service: OpeningService) -> None:
        self._opening_service = opening_service
        self._request_refresh()

    def _board_model(self):
        if self._game_controller is None:
            return None
        board_controller = getattr(self._game_controller, "board_controller", None)
        if board_controller is None:
            return None
        return board_controller.get_board_model()

    def _connect_board_signals(self) -> None:
        board_model = self._board_model()
        if board_model is None:
            return
        try:
            board_model.flip_state_changed.connect(self._on_flip_changed)
        except TypeError:
            pass
        try:
            # Paste FEN (and other board-only position changes) clear the active game.
            board_model.position_changed.connect(self._on_game_or_ply_changed)
        except TypeError:
            pass
        try:
            board_model.navigation_settled.connect(self._on_navigation_settled)
        except TypeError:
            pass

    def _disconnect_board_signals(self) -> None:
        board_model = self._board_model()
        if board_model is None:
            return
        try:
            board_model.flip_state_changed.disconnect(self._on_flip_changed)
        except TypeError:
            pass
        try:
            board_model.position_changed.disconnect(self._on_game_or_ply_changed)
        except TypeError:
            pass
        try:
            board_model.navigation_settled.disconnect(self._on_navigation_settled)
        except TypeError:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.on_became_visible()

    def on_became_visible(self) -> None:
        """Refresh immediately if content went stale while this tab was hidden."""
        if self._refresh_dirty:
            self.refresh()

    def _on_game_or_ply_changed(self, *_args) -> None:
        """Mark stale; defer rebuild until the board finishes any piece-move animation."""
        self._refresh_dirty = True
        if not self.isVisible():
            self._refresh_timer.stop()
            return
        # Prefer navigation_settled; this is only a safety net if that never arrives.
        self._refresh_timer.setInterval(_REFRESH_SETTLED_FALLBACK_MS)
        self._refresh_timer.start()

    def _on_flip_changed(self, *_args) -> None:
        """Flip does not animate pieces — refresh as soon as the tab is visible."""
        self._refresh_dirty = True
        if not self.isVisible():
            self._refresh_timer.stop()
            return
        self._refresh_timer.setInterval(_REFRESH_COALESCE_MS)
        self._refresh_timer.start()

    def _on_navigation_settled(self) -> None:
        """Board view finished applying the position (post animation) — coalesce refresh."""
        if not self._refresh_dirty:
            return
        if not self.isVisible():
            self._refresh_timer.stop()
            return
        self._refresh_timer.setInterval(_REFRESH_COALESCE_MS)
        self._refresh_timer.start()

    def _request_refresh(self) -> None:
        """Refresh now if visible; otherwise wait until the tab is shown."""
        self._refresh_dirty = True
        if self.isVisible():
            self.refresh()
        else:
            self._refresh_timer.stop()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child = item.layout()
            if child is not None:
                self._clear_layout(child)

    def _game_identity(self, game) -> Any:
        if game is None:
            return None
        return id(game)

    def _maybe_reset_path_prefs_for_game(self, game) -> None:
        game_id = self._game_identity(game)
        if game_id != self._last_game_id:
            self._last_game_id = game_id
            self._path_show_all = False
            path_section = self._explorer_config().get("path_section", {})
            self._path_expanded = not bool(path_section.get("collapsed_by_default", False))

    def _fade_continuations_in(self) -> None:
        # No-op: opacity effects on the continuation host caused blank gaps on macOS.
        if self._cont_fade_anim is not None:
            try:
                self._cont_fade_anim.finished.disconnect()
            except TypeError:
                pass
            self._cont_fade_anim.stop()
            self._cont_fade_anim.deleteLater()
            self._cont_fade_anim = None

    def _ensure_path_layout_orientation(self) -> None:
        """Clear path board containers for a fresh rebuild."""
        self._clear_layout(self._path_container)
        self._path_flow.clear_items()
        self._configure_path_scroll_for_density()

    def _set_breadcrumbs(self, path: List[OpeningPathStep], current_ply: int) -> None:
        if not path:
            self._breadcrumb_wrap.clear_chips()
            self._breadcrumb_wrap.setVisible(False)
            return

        active_idx = 0
        for i, step in enumerate(path):
            if step.ply_index <= current_ply:
                active_idx = i

        chips: List[QToolButton] = []
        for i, step in enumerate(path):
            chip = QToolButton()
            chip.setAutoRaise(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            name = step.display.name
            if len(name) > 28:
                name = name[:27] + "…"
            eco = step.display.eco
            label = f"{eco} · {name}" if eco else name
            chip.setText(label)
            chip.setToolTip(step.display.label)
            chip.clicked.connect(lambda checked=False, p=step.ply_index: self._navigate_to_ply(p))

            bg = self._chip_active_bg if i == active_idx else self._chip_bg
            border = self._current_row_border if i == active_idx else self._chip_border
            tc = self._chip_active_text if i == active_idx else self._text_color
            chip.setStyleSheet(
                f"""
                QToolButton {{
                    color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                    background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                    border: 1px solid rgb({border[0]}, {border[1]}, {border[2]});
                    border-radius: 10px;
                    padding: 2px 8px;
                    font-size: {max(8, int(self._font_size) - 1)}pt;
                }}
                QToolButton:hover {{
                    background-color: rgb({self._chip_active_bg[0]}, {self._chip_active_bg[1]}, {self._chip_active_bg[2]});
                    color: rgb({self._chip_active_text[0]}, {self._chip_active_text[1]}, {self._chip_active_text[2]});
                }}
                """
            )
            try:
                text_w = chip.fontMetrics().horizontalAdvance(label)
            except Exception:
                text_w = len(label) * 7
            chip.setMinimumWidth(int(text_w + 20))
            chips.append(chip)

        self._breadcrumb_wrap.set_chips(chips)
        self._breadcrumb_wrap.setVisible(True)

    def _on_continuation_focus(self, node: QWidget, focused: bool) -> None:
        """Highlight the expanded continuation; avoid QGraphicsOpacityEffect (macOS bugs)."""
        self._focused_continuation = node if focused else None
        accent = self._current_row_border
        for i in range(self._cont_container.count()):
            w = self._cont_container.itemAt(i).widget()
            if w is None:
                continue
            if w.graphicsEffect() is not None:
                w.setGraphicsEffect(None)
            if hasattr(w, "set_focus_highlight"):
                w.set_focus_highlight(bool(focused and w is node), accent)

    def refresh(self) -> None:
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
        self._refresh_dirty = False
        self._stop_path_anim()
        self._fade_continuations_in()
        self._ensure_path_layout_orientation()
        self._current_path_row = None
        self._focused_continuation = None

        if self._opening_service is None:
            self._set_empty_visible(True)
            return

        # No active game: explore from the current board FEN (paste FEN / empty board).
        game = self._game_model.active_game if self._game_model else None
        ply = 0
        if game is not None and self._game_model is not None:
            ply = int(self._game_model.get_active_move_ply() or 0)

        self._maybe_reset_path_prefs_for_game(game)
        self._set_empty_visible(False)
        self._path_header_row.setVisible(True)
        self._cont_header.setVisible(True)
        self._path_compact.setVisible(True)

        board_model = self._board_model()
        is_flipped = bool(board_model.is_flipped) if board_model is not None else False

        if game is not None:
            pgn = game.pgn or ""
            fens, sans, ucis = self._opening_service.replay_mainline_to_ply(pgn, ply)
        else:
            # Board-only position (e.g. Paste FEN): use that FEN as the explorer root.
            board_fen = board_model.get_fen() if board_model is not None else chess.Board().fen()
            fens, sans, ucis = [board_fen], [], []
            pgn = ""

        path = self._opening_service.build_path_from_replay(fens, sans, ucis)
        # Chevron only for now; board visibility is applied after content exists.
        self._path_toggle.blockSignals(True)
        self._path_toggle.setChecked(self._path_expanded)
        self._path_toggle.blockSignals(False)
        self._path_toggle.setText("▾" if self._path_expanded else "▸")

        current_fen = fens[-1] if fens else chess.Board().fen()
        current_display = self._opening_service.lookup_opening_display(current_fen)
        # Starting position is not in ECO tables but is a valid book root with many continuations.
        if current_display is None and OpeningService.is_standard_start_fen(current_fen):
            current_display = OPENING_STARTING
        in_book = current_display is not None and current_display is not OPENING_UNKNOWN

        next_uci: Optional[str] = None
        next_san: Optional[str] = None
        if game is not None and in_book:
            _fens_n, sans_n, ucis_n = self._opening_service.replay_mainline_to_ply(pgn, ply + 1)
            if len(ucis_n) > len(ucis):
                next_uci = ucis_n[-1]
                next_san = sans_n[-1] if sans_n else None

        # While out of book, don't keep appending middlegame SANs to the summary —
        # only show moves through the last book position on the line (rejoins included).
        if in_book:
            summary_moves = _format_san_line(sans)
        else:
            book_end = self._opening_service.last_in_book_index(fens)
            summary_moves = _format_san_line(sans[:book_end])
        if current_display is not None and in_book:
            summary = f"{summary_moves}  ·  {current_display.label}"
        elif path and not in_book:
            summary = f"{summary_moves}  ·  {path[-1].display.label}  ·  Out of book"
        elif current_display is not None:
            summary = f"{summary_moves}  ·  {current_display.label}"
        else:
            summary = f"{summary_moves}  ·  Out of book"
        self._path_summary.setText(summary)
        self._set_breadcrumbs(path, ply)

        visible_path = path
        hidden_count = 0
        if (
            not self._path_show_all
            and self._expanded_tail_count > 0
            and len(path) > self._expanded_tail_count
        ):
            hidden_count = len(path) - self._expanded_tail_count
            visible_path = path[-self._expanded_tail_count :]

        if hidden_count > 0:
            self._path_show_earlier_btn.setVisible(True)
            self._path_show_earlier_btn.setText(
                f"Show {hidden_count} earlier opening step{'s' if hidden_count != 1 else ''}…"
            )
        else:
            self._path_show_earlier_btn.setVisible(False)

        path_flow_items: List[QWidget] = []
        for step in visible_path:
            if step.gap_before is not None and not self._flow_boards:
                self._path_container.addWidget(self._make_gap_label(step.gap_before.summary))
            is_current = bool(
                in_book
                and current_display == step.display
                and not any(
                    s.ply_index > step.ply_index and s.display == current_display
                    for s in path
                )
            )
            # Gallery uses uniform tile size (current step highlighted by badge/border, not size).
            board_size = self._mini_size if self._flow_boards else (
                self._hero_size if is_current else self._mini_size
            )
            row = _OpeningStepRow(
                config=self.config,
                explorer_cfg=self._explorer_config(),
                fen=step.fen,
                title=step.display.label,
                subtitle=self._format_step_subtitle(step),
                move_uci=step.move_uci,
                is_flipped=is_flipped,
                is_current=is_current,
                mini_size=board_size,
                show_arrow=self._show_arrows,
                on_activate=lambda p=step.ply_index: self._navigate_to_ply(p),
                lichess_url=(
                    self._opening_service.lichess_url_for_fen(step.fen)
                    if self._lichess_link_enabled
                    else None
                ),
                colors={
                    "text": self._text_color,
                    "muted": self._muted_color,
                    "row_bg": self._row_bg,
                    "row_border": self._current_row_border if is_current else self._row_border,
                    "badge_bg": self._current_badge_bg,
                    "badge_text": self._current_badge_text,
                    "font_family": self._font_family,
                    "font_size": self._font_size,
                    "expand_font_size": self._expand_font_size,
                    "expand_button_size": self._expand_button_size,
                    "lichess_link_tooltip": self._lichess_link_tooltip,
                },
                compact_horizontal=self._flow_boards,
            )
            if self._flow_boards:
                path_flow_items.append(row)
            else:
                self._path_container.addWidget(row)
            if is_current:
                self._current_path_row = row

        if self._flow_boards:
            board_outer = _mini_board_outer_size(self.config, self._mini_size)
            # Card chrome: horizontal margins + configured gallery tile extras.
            tile_w = int(board_outer + self._gallery_tile_extra_width)
            tile_h = int(board_outer + self._gallery_tile_extra_height)
            self._path_flow.set_uniform_size(QSize(tile_w, tile_h))
            self._path_flow.set_items(path_flow_items)
        else:
            self._path_flow.set_uniform_size(None)

        # Apply visibility only after boards exist (prevents clipped/empty height).
        self._apply_path_boards_visibility(self._path_expanded, animate=False)

        self._clear_layout(self._cont_container)
        if not in_book:
            empty = QLabel("Out of book — no book continuations from this position.")
            empty.setStyleSheet(
                f"color: rgb({self._muted_color[0]}, {self._muted_color[1]}, {self._muted_color[2]});"
                " background: transparent;"
            )
            empty.setFont(QFont(self._font_family, int(self._font_size)))
            self._cont_container.addWidget(empty)
        else:
            conts = self._opening_service.continuations(current_fen)
            if not conts:
                empty = QLabel("No known book continuations from this position.")
                empty.setStyleSheet(
                    f"color: rgb({self._muted_color[0]}, {self._muted_color[1]}, {self._muted_color[2]});"
                    " background: transparent;"
                )
                empty.setFont(QFont(self._font_family, int(self._font_size)))
                self._cont_container.addWidget(empty)
            else:
                played_node: Optional[_ContinuationNode] = None
                for cont in conts:
                    is_played_next = bool(next_uci and cont.move_uci == next_uci)
                    node = _ContinuationNode(
                        config=self.config,
                        explorer_cfg=self._explorer_config(),
                        opening_service=self._opening_service,
                        continuation=cont,
                        is_flipped=is_flipped,
                        depth=1,
                        max_depth=self._max_depth,
                        mini_size=self._mini_size,
                        show_arrow=self._show_arrows,
                        colors=self._continuation_colors(),
                        is_played_next=is_played_next,
                        played_next_label=(
                            f"Played next → {next_san}" if is_played_next and next_san else "Played next →"
                        ),
                        on_expand_changed=self._on_continuation_focus,
                    )
                    self._cont_container.addWidget(node)
                    if is_played_next:
                        played_node = node
                if played_node is not None:
                    played_node.set_expanded(True, notify_focus=False)

        if self._current_path_row is not None and self._path_expanded:
            QTimer.singleShot(0, self._scroll_current_into_view)

    def _scroll_current_into_view(self) -> None:
        row = self._current_path_row
        if row is None:
            return
        try:
            self._scroll.ensureWidgetVisible(row, 20, 20)
        except Exception:
            pass

    def _format_step_subtitle(self, step: OpeningPathStep) -> str:
        if step.move_san is None or step.full_move_number is None:
            return "Start"
        prefix = f"{step.full_move_number}." if step.is_white_move else f"{step.full_move_number}..."
        return f"{prefix} {step.move_san}"

    def _make_gap_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(QFont(self._font_family, int(self._font_size)))
        c = self._gap_color
        label.setStyleSheet(f"color: rgb({c[0]}, {c[1]}, {c[2]}); background: transparent; padding: 2px 4px;")
        return label

    def _navigate_to_ply(self, ply_index: int) -> None:
        if self._game_controller is None:
            return
        try:
            self._game_controller.navigate_to_ply(int(ply_index))
        except Exception:
            pass


class _OpeningStepRow(QFrame):
    """Clickable path row with embedded mini board."""

    def __init__(
        self,
        *,
        config: Dict[str, Any],
        explorer_cfg: Dict[str, Any],
        fen: str,
        title: str,
        subtitle: str,
        move_uci: Optional[str],
        is_flipped: bool,
        is_current: bool,
        mini_size: int,
        show_arrow: bool,
        on_activate,
        colors: Dict[str, Any],
        lichess_url: Optional[str] = None,
        compact_horizontal: bool = False,
    ) -> None:
        super().__init__()
        self._on_activate = on_activate
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed if compact_horizontal else QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        bg = colors["row_bg"]
        border = colors["row_border"]
        layout_cfg = explorer_cfg.get("layout", {})
        if not isinstance(layout_cfg, dict):
            layout_cfg = {}
        step_cfg = layout_cfg.get("path_step", {})
        if not isinstance(step_cfg, dict):
            step_cfg = {}
        gallery_cfg = step_cfg.get("gallery", {})
        if not isinstance(gallery_cfg, dict):
            gallery_cfg = {}

        margins = _as_box(step_cfg.get("margins"), (8, 6, 8, 6))
        spacing = int(step_cfg.get("spacing", 10))
        text_spacing = int(step_cfg.get("text_spacing", 2))
        title_row_spacing = int(step_cfg.get("title_row_spacing", 4))
        border_radius = int(step_cfg.get("border_radius", 4))
        border_w = int(
            step_cfg.get("current_border_width", 2)
            if is_current
            else step_cfg.get("border_width", 1)
        )
        badge_radius = int(step_cfg.get("badge_border_radius", 3))
        badge_pad = _as_pair(step_cfg.get("badge_padding"), (1, 6))
        text_top = int(gallery_cfg.get("text_top_margin", 2)) if compact_horizontal else 0
        badge_reserve = int(gallery_cfg.get("current_title_badge_reserve", 36))
        tile_extra_w = int(gallery_cfg.get("tile_extra_width", 24))
        tile_extra_h = int(gallery_cfg.get("tile_extra_height", 56))

        self.setStyleSheet(
            f"""
            _OpeningStepRow {{
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                border: {border_w}px solid rgb({border[0]}, {border[1]}, {border[2]});
                border-radius: {border_radius}px;
            }}
            """
        )

        layout = QVBoxLayout(self) if compact_horizontal else QHBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)

        board = MiniChessBoardWidget(
            config,
            fen,
            is_flipped=is_flipped,
            embedded=True,
            size_override=mini_size,
        )
        if move_uci and show_arrow:
            try:
                board.set_move(chess.Move.from_uci(move_uci), True)
            except Exception:
                pass
        layout.addWidget(board, alignment=Qt.AlignmentFlag.AlignHCenter if compact_horizontal else Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, text_top, 0, 0)
        text_col.setSpacing(text_spacing)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(title_row_spacing)
        title_label = QLabel(title)
        title_label.setFont(QFont(colors["font_family"], int(colors["font_size"])))
        if compact_horizontal:
            title_label.setWordWrap(False)
            # Leave room for the "Now" badge when present.
            title_w = max(40, mini_size - (badge_reserve if is_current else 0))
            title_label.setMaximumWidth(title_w)
            metrics = title_label.fontMetrics()
            title_label.setText(
                metrics.elidedText(title, Qt.TextElideMode.ElideRight, title_w)
            )
        else:
            title_label.setWordWrap(True)
        tc = colors["text"]
        title_label.setStyleSheet(f"color: rgb({tc[0]}, {tc[1]}, {tc[2]}); background: transparent; border: none;")
        title_row.addWidget(title_label, 1)
        if is_current:
            badge = QLabel("Now")
            badge.setFont(QFont(colors["font_family"], max(8, int(colors["font_size"]) - 1)))
            bb = colors["badge_bg"]
            bt = colors["badge_text"]
            badge.setStyleSheet(
                f"color: rgb({bt[0]}, {bt[1]}, {bt[2]}); background-color: rgb({bb[0]}, {bb[1]}, {bb[2]});"
                f" border-radius: {badge_radius}px; padding: {badge_pad[0]}px {badge_pad[1]}px;"
            )
            title_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        text_col.addLayout(title_row)

        sub = QLabel(subtitle)
        sub.setFont(QFont(colors["font_family"], int(colors["font_size"])))
        mc = colors["muted"]
        sub.setStyleSheet(f"color: rgb({mc[0]}, {mc[1]}, {mc[2]}); background: transparent; border: none;")
        text_col.addWidget(sub)
        if not compact_horizontal:
            text_col.addStretch(1)
        layout.addLayout(text_col, 0 if compact_horizontal else 1)

        if lichess_url and not compact_horizontal:
            layout.addWidget(
                _make_lichess_button(
                    colors=colors,
                    tooltip=str(colors.get("lichess_link_tooltip", "Open this opening on Lichess")),
                    on_click=lambda checked=False, u=lichess_url: _open_lichess_url(u),
                ),
                0,
                Qt.AlignmentFlag.AlignTop,
            )

        if compact_horizontal:
            # Uniform card tile for gallery grid (include mini-board border).
            board_outer = _mini_board_outer_size(config, mini_size)
            self.setFixedSize(board_outer + tile_extra_w, board_outer + tile_extra_h)
            # One card-level tooltip only (child tooltips look unstyled / native).
            tip = title if not subtitle or subtitle == "Start" else f"{title}\n{subtitle}"
            self.setToolTip(tip)
            for child in (board, title_label, sub):
                child.setToolTip("")
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if is_current:
                badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._on_activate:
            child = self.childAt(event.position().toPoint())
            if child is not None and isinstance(child, QToolButton):
                return
            self._on_activate()
        super().mouseReleaseEvent(event)


class _ContinuationNode(QWidget):
    """Expandable continuation row with embedded mini board and lazy children."""

    def __init__(
        self,
        *,
        config: Dict[str, Any],
        explorer_cfg: Dict[str, Any],
        opening_service: OpeningService,
        continuation: OpeningContinuation,
        is_flipped: bool,
        depth: int,
        max_depth: int,
        mini_size: int,
        show_arrow: bool,
        colors: Dict[str, Any],
        is_played_next: bool = False,
        played_next_label: str = "Played next →",
        on_expand_changed: Optional[Callable[["_ContinuationNode", bool], None]] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._explorer_cfg = explorer_cfg
        self._opening_service = opening_service
        self._continuation = continuation
        self._is_flipped = is_flipped
        self._depth = depth
        self._max_depth = max_depth
        self._mini_size = mini_size
        self._show_arrow = show_arrow
        self._colors = colors
        self._on_expand_changed = on_expand_changed
        self._children_loaded = False
        self._notify_focus = True
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        cont_layout = explorer_cfg.get("layout", {})
        if not isinstance(cont_layout, dict):
            cont_layout = {}
        cont_cfg = cont_layout.get("continuation", {})
        if not isinstance(cont_cfg, dict):
            cont_cfg = {}
        self._cont_layout_cfg = cont_cfg
        root.setSpacing(int(cont_cfg.get("root_spacing", 4)))

        header = QFrame()
        self._header = header
        self._base_border = list(colors["row_border"])
        self._base_bg = list(colors["row_bg"])
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._apply_header_chrome(highlighted=False)
        h = QHBoxLayout(header)
        h.setContentsMargins(*_as_box(cont_cfg.get("header_margins"), (8, 6, 8, 6)))
        h.setSpacing(int(cont_cfg.get("header_spacing", 8)))

        expand_size = int(colors.get("expand_button_size", 28))
        expand_font = int(colors.get("expand_font_size", 16))
        can_expand = depth < max_depth and bool(
            opening_service.continuations(continuation.fen_after, limit=1)
        )
        self._can_expand = can_expand

        self._expand = QToolButton()
        self._expand.setText("▸" if can_expand else "")
        self._expand.setCheckable(can_expand)
        self._expand.setChecked(False)
        self._expand.setAutoRaise(True)
        self._expand.setEnabled(can_expand)
        self._expand.setFixedSize(expand_size, expand_size)
        if not can_expand:
            self._expand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        tc = colors["text"]
        self._expand.setStyleSheet(
            f"""
            QToolButton {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                background: transparent;
                border: none;
                padding: 0px;
                font-size: {expand_font}pt;
                font-weight: bold;
            }}
            QToolButton:checked {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                background: transparent;
            }}
            QToolButton:hover {{
                color: rgb({tc[0]}, {tc[1]}, {tc[2]});
                background: transparent;
            }}
            QToolButton:disabled {{
                color: transparent;
                background: transparent;
                border: none;
            }}
            """
        )
        if can_expand:
            self._expand.toggled.connect(self._on_toggled)
        h.addWidget(self._expand, 0, Qt.AlignmentFlag.AlignVCenter)

        board = MiniChessBoardWidget(
            config,
            continuation.fen_after,
            is_flipped=is_flipped,
            embedded=True,
            size_override=mini_size,
        )
        if show_arrow:
            try:
                board.set_move(chess.Move.from_uci(continuation.move_uci), True)
            except Exception:
                pass
        h.addWidget(board, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        move_row = QHBoxLayout()
        move_label = QLabel(continuation.san)
        move_label.setFont(QFont(colors["font_family"], int(colors["font_size"])))
        tc = colors["text"]
        move_label.setStyleSheet(f"color: rgb({tc[0]}, {tc[1]}, {tc[2]}); background: transparent; border: none;")
        move_row.addWidget(move_label, 0)
        if is_played_next:
            badge = QLabel(played_next_label)
            badge.setFont(QFont(colors["font_family"], max(8, int(colors["font_size"]) - 1)))
            bb = colors.get("played_next_badge_bg", [90, 120, 80])
            bt = colors.get("played_next_badge_text", [240, 240, 240])
            step_cfg = (
                explorer_cfg.get("layout", {}).get("path_step", {})
                if isinstance(explorer_cfg.get("layout"), dict)
                else {}
            )
            if not isinstance(step_cfg, dict):
                step_cfg = {}
            badge_radius = int(step_cfg.get("badge_border_radius", 3))
            badge_pad = _as_pair(step_cfg.get("badge_padding"), (1, 6))
            badge.setStyleSheet(
                f"color: rgb({bt[0]}, {bt[1]}, {bt[2]}); background-color: rgb({bb[0]}, {bb[1]}, {bb[2]});"
                f" border-radius: {badge_radius}px; padding: {badge_pad[0]}px {badge_pad[1]}px;"
            )
            move_row.addWidget(badge, 0)
        move_row.addStretch(1)
        text_col.addLayout(move_row)
        name_label = QLabel(continuation.display.label)
        name_label.setWordWrap(True)
        name_label.setFont(QFont(colors["font_family"], int(colors["font_size"])))
        mc = colors["muted"]
        name_label.setStyleSheet(f"color: rgb({mc[0]}, {mc[1]}, {mc[2]}); background: transparent; border: none;")
        text_col.addWidget(name_label)
        text_col.addStretch(1)
        h.addLayout(text_col, 1)

        if colors.get("lichess_link_enabled", True):
            url = opening_service.lichess_url_for_fen(continuation.fen_after)
            h.addWidget(
                _make_lichess_button(
                    colors=colors,
                    tooltip=str(colors.get("lichess_link_tooltip", "Open this opening on Lichess")),
                    on_click=lambda checked=False, u=url: _open_lichess_url(u),
                ),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )

        root.addWidget(header)

        self._children_host = QWidget()
        self._children_layout = QVBoxLayout(self._children_host)
        indent = int(self._cont_layout_cfg.get("children_left_indent", 18))
        self._children_layout.setContentsMargins(indent, 0, 0, 0)
        self._children_layout.setSpacing(int(self._cont_layout_cfg.get("children_spacing", 6)))
        self._children_host.setVisible(False)
        root.addWidget(self._children_host)

    def _apply_header_chrome(self, *, highlighted: bool, accent: Optional[List[int]] = None) -> None:
        bg = self._base_bg
        border = accent if highlighted and accent else self._base_border
        cfg = getattr(self, "_cont_layout_cfg", {})
        width = int(
            cfg.get("header_highlight_border_width", 2)
            if highlighted
            else cfg.get("header_border_width", 1)
        )
        radius = int(cfg.get("header_border_radius", 4))
        self._header.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                border: {width}px solid rgb({border[0]}, {border[1]}, {border[2]});
                border-radius: {radius}px;
            }}
            """
        )

    def set_focus_highlight(self, highlighted: bool, accent: Optional[List[int]] = None) -> None:
        self._apply_header_chrome(highlighted=highlighted, accent=accent)

    def set_expanded(self, expanded: bool, *, notify_focus: bool = True) -> None:
        if not self._can_expand:
            return
        self._notify_focus = notify_focus
        if self._expand.isChecked() == expanded:
            if expanded:
                self._on_toggled(True)
            self._notify_focus = True
            return
        self._expand.setChecked(expanded)
        self._notify_focus = True

    def _on_toggled(self, checked: bool) -> None:
        if not self._can_expand:
            return
        self._expand.setText("▾" if checked else "▸")
        if checked and not self._children_loaded and self._depth < self._max_depth:
            self._load_children()
        self._children_host.setVisible(checked)
        if (
            getattr(self, "_notify_focus", True)
            and self._on_expand_changed is not None
            and self._depth == 1
        ):
            self._on_expand_changed(self, checked)

    def _load_children(self) -> None:
        self._children_loaded = True
        conts = self._opening_service.continuations(self._continuation.fen_after)
        for cont in conts:
            child = _ContinuationNode(
                config=self._config,
                explorer_cfg=self._explorer_cfg,
                opening_service=self._opening_service,
                continuation=cont,
                is_flipped=self._is_flipped,
                depth=self._depth + 1,
                max_depth=self._max_depth,
                mini_size=self._mini_size,
                show_arrow=self._show_arrow,
                colors=self._colors,
                on_expand_changed=None,
            )
            self._children_layout.addWidget(child)

"""Opening Explorer detail view — path to current ply and book continuations."""

from __future__ import annotations

from typing import Any, Dict, Optional

import chess
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
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
    OpeningContinuation,
    OpeningPathStep,
    OpeningService,
)
from app.utils.external_open import open_url
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget


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
        self._mini_size = int(cfg.get("mini_board", {}).get("size", 128))
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
        self._pane_bg = tabs.get("pane_background", [40, 40, 45])

        self._show_arrows = bool(cfg.get("show_move_arrows", True))
        self._max_depth = int(cfg.get("max_continuation_depth", OpeningService.MAX_CONTINUATION_DEPTH))
        self._empty_text = cfg.get("placeholder_text_no_game", "No game selected.")

        expand_cfg = cfg.get("expand_button", {})
        self._expand_font_size = int(scale_font_size(expand_cfg.get("font_size", 16)))
        self._expand_button_size = int(expand_cfg.get("size", 28))

        lichess_cfg = cfg.get("lichess_link", {})
        self._lichess_link_enabled = bool(lichess_cfg.get("enabled", True))
        self._lichess_link_tooltip = str(
            lichess_cfg.get("tooltip", "Open this opening on Lichess")
        )

        path_section = cfg.get("path_section", {})
        # Remember user toggle across refreshes; seed from config once.
        if not hasattr(self, "_path_expanded"):
            self._path_expanded = not bool(path_section.get("collapsed_by_default", False))

        placeholder = cfg.get("placeholder", {})
        self._placeholder_text_color = placeholder.get("text_color", [150, 150, 150])
        self._placeholder_font_size = int(scale_font_size(placeholder.get("font_size", 14)))
        self._placeholder_padding = int(placeholder.get("padding", 20))

    def _continuation_colors(self) -> Dict[str, Any]:
        return {
            "text": self._text_color,
            "muted": self._muted_color,
            "row_bg": self._row_bg,
            "row_border": self._row_border,
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
        path_header_layout.setSpacing(6)

        self._path_toggle = QToolButton()
        self._path_toggle.setCheckable(True)
        self._path_toggle.setChecked(self._path_expanded)
        self._path_toggle.setAutoRaise(True)
        self._path_toggle.setFixedSize(self._expand_button_size, self._expand_button_size)
        self._path_toggle.toggled.connect(self._on_path_toggled)
        path_header_layout.addWidget(self._path_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self._path_header = QLabel("Lines until here")
        path_header_layout.addWidget(self._path_header, 1, Qt.AlignmentFlag.AlignVCenter)
        self._path_header_row.mousePressEvent = self._path_header_mouse_press  # type: ignore[method-assign]

        self._path_wrap = QWidget()
        self._path_container = QVBoxLayout(self._path_wrap)
        self._path_container.setContentsMargins(0, 0, 0, 0)
        self._path_container.setSpacing(self._row_spacing)
        self._path_wrap.setVisible(self._path_expanded)

        self._cont_header = QLabel("Lines from here")
        self._cont_header.setVisible(False)
        self._cont_wrap = QWidget()
        self._cont_container = QVBoxLayout(self._cont_wrap)
        self._cont_container.setContentsMargins(0, 0, 0, 0)
        self._cont_container.setSpacing(self._row_spacing)

        self._content_layout.addWidget(self._path_header_row)
        self._content_layout.addWidget(self._path_wrap)

        self._content_layout.addWidget(self._cont_header)
        self._content_layout.addWidget(self._cont_wrap)

        self._content_layout.addStretch(1)
        scroll.setWidget(self._content)
        root.addWidget(scroll)

        # Full-pane empty state (matches Game Summary / Annotations placeholder style)
        self._empty_label = QLabel(self._empty_text)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._empty_label)

        self._apply_styling()
        self._sync_path_toggle_chrome()
        self._set_empty_visible(True)

    def _apply_styling(self) -> None:
        bg = self._pane_bg
        self.setStyleSheet(
            f"DetailOpeningExplorerView {{ background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); }}"
        )
        self._content.setStyleSheet(f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});")
        title_c = self._title_color
        title_font = QFont(self._font_family, int(self._title_font_size))
        title_font.setBold(True)
        for header in (self._path_header, self._cont_header):
            header.setFont(title_font)
            header.setStyleSheet(
                f"color: rgb({title_c[0]}, {title_c[1]}, {title_c[2]}); background: transparent;"
            )
        tc = self._text_color
        self._path_toggle.setStyleSheet(
            f"""
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

    def _sync_path_toggle_chrome(self) -> None:
        self._path_toggle.blockSignals(True)
        self._path_toggle.setChecked(self._path_expanded)
        self._path_toggle.blockSignals(False)
        self._path_toggle.setText("▾" if self._path_expanded else "▸")
        self._path_wrap.setVisible(self._path_expanded)

    def _on_path_toggled(self, checked: bool) -> None:
        self._path_expanded = bool(checked)
        self._sync_path_toggle_chrome()

    def _path_header_mouse_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Ignore presses on the tool button itself (it handles its own toggle).
            child = self._path_header_row.childAt(event.position().toPoint())
            if child is self._path_toggle:
                return
            self._path_toggle.toggle()

    def _set_empty_visible(self, visible: bool) -> None:
        if visible:
            self._empty_label.setText(self._empty_text)
            self._empty_label.show()
            self._scroll.hide()
            self._path_header_row.setVisible(False)
            self._path_wrap.setVisible(False)
            self._cont_header.setVisible(False)
        else:
            self._empty_label.hide()
            self._scroll.show()
            self._sync_path_toggle_chrome()

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
        self.refresh()

    def set_game_controller(self, game_controller) -> None:
        self._disconnect_board_flip()
        self._game_controller = game_controller
        if game_controller is not None and self._opening_service is None:
            self._opening_service = getattr(game_controller, "opening_service", None)
        self._connect_board_flip()
        self.refresh()

    def set_opening_service(self, opening_service: OpeningService) -> None:
        self._opening_service = opening_service
        self.refresh()

    def _board_model(self):
        if self._game_controller is None:
            return None
        board_controller = getattr(self._game_controller, "board_controller", None)
        if board_controller is None:
            return None
        return board_controller.get_board_model()

    def _connect_board_flip(self) -> None:
        board_model = self._board_model()
        if board_model is None:
            return
        try:
            board_model.flip_state_changed.connect(self._on_game_or_ply_changed)
        except TypeError:
            pass

    def _disconnect_board_flip(self) -> None:
        board_model = self._board_model()
        if board_model is None:
            return
        try:
            board_model.flip_state_changed.disconnect(self._on_game_or_ply_changed)
        except TypeError:
            pass

    def _on_game_or_ply_changed(self, *_args) -> None:
        self.refresh()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child = item.layout()
            if child is not None:
                self._clear_layout(child)

    def refresh(self) -> None:
        self._clear_layout(self._path_container)
        self._clear_layout(self._cont_container)

        game = self._game_model.active_game if self._game_model else None
        if game is None or self._opening_service is None:
            self._set_empty_visible(True)
            return

        self._set_empty_visible(False)
        self._path_header_row.setVisible(True)
        self._cont_header.setVisible(True)
        self._sync_path_toggle_chrome()

        ply = 0
        if self._game_model is not None:
            ply = int(self._game_model.get_active_move_ply() or 0)

        fens, sans, ucis = self._opening_service.replay_mainline_to_ply(game.pgn or "", ply)
        path = self._opening_service.build_path_from_replay(fens, sans, ucis)
        board_model = self._board_model()
        is_flipped = bool(board_model.is_flipped) if board_model is not None else False
        # Continuations must use the same mainline ply FEN as the path, not the
        # live board (which can diverge during exploration / brief desyncs).
        current_fen = fens[-1] if fens else chess.Board().fen()
        current_display = self._opening_service.lookup_opening_display(current_fen)
        in_book = current_display is not None

        for step in path:
            if step.gap_before is not None:
                self._path_container.addWidget(self._make_gap_label(step.gap_before.summary))
            # "Now" only while the current ply is still this named book opening.
            # Path mini boards always keep the opening milestone FEN (no live mirroring).
            is_current = bool(
                in_book
                and current_display == step.display
                and not any(
                    s.ply_index > step.ply_index and s.display == current_display
                    for s in path
                )
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
                mini_size=self._mini_size,
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
                    "row_border": self._row_border,
                    "badge_bg": self._current_badge_bg,
                    "badge_text": self._current_badge_text,
                    "font_family": self._font_family,
                    "font_size": self._font_size,
                    "expand_font_size": self._expand_font_size,
                    "expand_button_size": self._expand_button_size,
                    "lichess_link_tooltip": self._lichess_link_tooltip,
                },
            )
            self._path_container.addWidget(row)

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
                for cont in conts:
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
                    )
                    self._cont_container.addWidget(node)

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
    ) -> None:
        super().__init__()
        self._on_activate = on_activate
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        bg = colors["row_bg"]
        border = colors["row_border"]
        self.setStyleSheet(
            f"""
            _OpeningStepRow {{
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                border: 1px solid rgb({border[0]}, {border[1]}, {border[2]});
                border-radius: 4px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        mini_cfg = explorer_cfg.get("mini_board", {})
        board = MiniChessBoardWidget(
            config,
            fen,
            is_flipped=is_flipped,
            embedded=True,
            size_override=mini_size,
            mini_board_config=mini_cfg if isinstance(mini_cfg, dict) else {},
        )
        if move_uci and show_arrow:
            try:
                board.set_move(chess.Move.from_uci(move_uci), True)
            except Exception:
                pass
        layout.addWidget(board, alignment=Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_row = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setFont(QFont(colors["font_family"], int(colors["font_size"])))
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
                " border-radius: 3px; padding: 1px 6px;"
            )
            title_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        text_col.addLayout(title_row)

        sub = QLabel(subtitle)
        sub.setFont(QFont(colors["font_family"], int(colors["font_size"])))
        mc = colors["muted"]
        sub.setStyleSheet(f"color: rgb({mc[0]}, {mc[1]}, {mc[2]}); background: transparent; border: none;")
        text_col.addWidget(sub)
        text_col.addStretch(1)
        layout.addLayout(text_col, 1)

        if lichess_url:
            layout.addWidget(
                _make_lichess_button(
                    colors=colors,
                    tooltip=str(colors.get("lichess_link_tooltip", "Open this opening on Lichess")),
                    on_click=lambda checked=False, u=lichess_url: _open_lichess_url(u),
                ),
                0,
                Qt.AlignmentFlag.AlignTop,
            )

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
        self._children_loaded = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QFrame()
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bg = colors["row_bg"]
        border = colors["row_border"]
        header.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                border: 1px solid rgb({border[0]}, {border[1]}, {border[2]});
                border-radius: 4px;
            }}
            """
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)

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
            # Same footprint as the chevron so boards stay column-aligned.
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


        mini_cfg = explorer_cfg.get("mini_board", {})
        board = MiniChessBoardWidget(
            config,
            continuation.fen_after,
            is_flipped=is_flipped,
            embedded=True,
            size_override=mini_size,
            mini_board_config=mini_cfg if isinstance(mini_cfg, dict) else {},
        )
        if show_arrow:
            try:
                board.set_move(chess.Move.from_uci(continuation.move_uci), True)
            except Exception:
                pass
        h.addWidget(board, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        move_label = QLabel(continuation.san)
        move_label.setFont(QFont(colors["font_family"], int(colors["font_size"])))
        tc = colors["text"]
        move_label.setStyleSheet(f"color: rgb({tc[0]}, {tc[1]}, {tc[2]}); background: transparent; border: none;")
        text_col.addWidget(move_label)
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
        self._children_layout.setContentsMargins(18, 0, 0, 0)
        self._children_layout.setSpacing(6)
        self._children_host.setVisible(False)
        root.addWidget(self._children_host)

    def _on_toggled(self, checked: bool) -> None:
        if not self._can_expand:
            return
        self._expand.setText("▾" if checked else "▸")
        if checked and not self._children_loaded and self._depth < self._max_depth:
            self._load_children()
        self._children_host.setVisible(checked)

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
            )
            self._children_layout.addWidget(child)

"""Evaluation bar widget for displaying position evaluation."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.models.evaluation_model import EvaluationModel
from app.services.logging_service import LoggingService
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style.tooltip import load_tooltip_style

Rgb = Tuple[int, int, int]


def _rgb_from_cfg(value: Any, fallback: Rgb) -> Rgb:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback


class EvalBarValueTip(QWidget):
    """Large-font hover tip showing the current evaluation score."""

    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chrome = load_tooltip_style(config)
        board_cfg = config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
        tip_cfg = board_cfg.get("evaluation_bar", {}).get("tooltip", {})
        if not isinstance(tip_cfg, dict):
            tip_cfg = {}

        self._enabled = bool(tip_cfg.get("enabled", True))
        self._anchor_gap = max(0, int(tip_cfg.get("anchor_gap", 8) or 8))
        self._padding = max(4, int(tip_cfg.get("padding", self._chrome.padding) or self._chrome.padding))
        self._hover_delay_ms = max(
            0, int(tip_cfg.get("hover_delay_ms", self._chrome.hover_delay_ms) or 0)
        )
        self._decimals = max(0, int(tip_cfg.get("decimals", 2) or 2))
        font_size = max(10, int(tip_cfg.get("font_size", 22) or 22))
        font_weight = str(tip_cfg.get("font_weight", "bold") or "bold").strip().lower()
        equal = _rgb_from_cfg(tip_cfg.get("text_color_equal"), self._chrome.text)
        self._color_positive = _rgb_from_cfg(tip_cfg.get("text_color_positive"), equal)
        self._color_negative = _rgb_from_cfg(tip_cfg.get("text_color_negative"), equal)
        self._color_equal = equal
        self._last_text = ""
        self._last_sign = 0

        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        family = resolve_font_family(self._chrome.font_family)
        value_font = QFont(family, max(10, scale_font_size(font_size)))
        value_font.setBold(font_weight == "bold")

        self._label = QLabel("", self)
        self._label.setFont(value_font)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_label_color(self._color_equal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self._padding, self._padding, self._padding, self._padding)
        layout.addWidget(self._label)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def hover_delay_ms(self) -> int:
        return self._hover_delay_ms

    @property
    def decimals(self) -> int:
        return self._decimals

    def color_for_sign(self, sign: int) -> Rgb:
        if sign > 0:
            return self._color_positive
        if sign < 0:
            return self._color_negative
        return self._color_equal

    def present(
        self,
        anchor: QWidget,
        text: str,
        *,
        sign: int = 0,
        cursor_global: Optional[QPoint] = None,
    ) -> None:
        if not self._enabled or not anchor.isVisible():
            return
        if text != self._last_text or sign != self._last_sign:
            self._label.setText(text)
            self._set_label_color(self.color_for_sign(sign))
            metrics = QFontMetrics(self._label.font())
            text_w = metrics.boundingRect(text).width() + 4
            text_h = metrics.height() + 2
            self.setFixedSize(
                max(1, text_w + 2 * self._padding),
                max(1, text_h + 2 * self._padding),
            )
            self._last_text = text
            self._last_sign = sign

        tip_w = self.width()
        tip_h = self.height()
        screen = QGuiApplication.screenAt(anchor.mapToGlobal(anchor.rect().center()))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        cursor_pos = cursor_global if cursor_global is not None else QCursor.pos()
        y = cursor_pos.y() - tip_h // 2
        x = anchor.mapToGlobal(QPoint(anchor.width() + self._anchor_gap, 0)).x()
        # Prefer right of bar; flip left if it would leave the screen.
        if x + tip_w > avail.right():
            x = anchor.mapToGlobal(QPoint(0, 0)).x() - self._anchor_gap - tip_w
        y = max(avail.top(), min(y, avail.bottom() - tip_h + 1))
        x = max(avail.left(), min(x, avail.right() - tip_w + 1))
        self.move(x, y)
        if not self.isVisible():
            self.show()
            self.raise_()

    def hide_tip(self) -> None:
        self._last_text = ""
        self.hide()

    def _set_label_color(self, rgb: Rgb) -> None:
        self._label.setStyleSheet(
            f"color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); "
            "background: transparent; border: none;"
        )

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg = self._chrome.background
        border = self._chrome.border
        radius = float(self._chrome.border_radius)
        inset = max(0.5, self._chrome.border_width / 2.0)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(inset, inset, self.width() - 2 * inset, self.height() - 2 * inset),
            radius,
            radius,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*bg))
        painter.drawPath(path)
        if self._chrome.border_width > 0:
            pen = QPen(QColor(*border))
            pen.setWidth(self._chrome.border_width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)


class EvaluationBarWidget(QWidget):
    """Widget displaying evaluation bar with white/black bars."""
    
    def __init__(self, config: Dict[str, Any], evaluation_model: Optional[EvaluationModel] = None) -> None:
        """Initialize the evaluation bar widget.
        
        Args:
            config: Configuration dictionary.
            evaluation_model: Optional EvaluationModel to observe.
        """
        super().__init__()
        self.config = config
        self._evaluation_model: Optional[EvaluationModel] = None
        self._is_flipped = False
        
        # Animation state
        self._displayed_value: float = 0.0  # Currently displayed evaluation value
        self._target_value: float = 0.0  # Target evaluation value
        self._animation_start_time: float = 0.0
        self._animation_start_value: float = 0.0
        self._animation_duration_ms: int = 300
        self._animation_timer: Optional[QTimer] = None
        self._is_animating: bool = False

        # Line styling
        self._center_line_color = QColor(128, 128, 128)
        self._center_line_width = 1
        self._center_line_style = Qt.PenStyle.SolidLine
        self._division_marks_color = QColor(128, 128, 128)
        self._division_marks_width = 1
        self._division_marks_style = Qt.PenStyle.DashLine

        self._value_tip = EvalBarValueTip(config, self)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_value_tip)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        
        self._load_config()
        self._setup_ui()
        
        # Connect to model if provided
        if evaluation_model:
            self.set_evaluation_model(evaluation_model)
    
    def _load_config(self) -> None:
        """Load configuration from config dictionary."""
        board_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
        eval_config = board_config.get("evaluation_bar", {})

        def _qcolor_from_cfg(value: Any, default: QColor) -> QColor:
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                try:
                    return QColor(int(value[0]), int(value[1]), int(value[2]))
                except (TypeError, ValueError):
                    return default
            return default

        def _pen_style_from_cfg(value: Any, default: Qt.PenStyle) -> Qt.PenStyle:
            if not isinstance(value, str):
                return default
            key = value.strip().lower()
            mapping = {
                "solid": Qt.PenStyle.SolidLine,
                "solidline": Qt.PenStyle.SolidLine,
                "dash": Qt.PenStyle.DashLine,
                "dashline": Qt.PenStyle.DashLine,
                "dot": Qt.PenStyle.DotLine,
                "dotline": Qt.PenStyle.DotLine,
                "dashdot": Qt.PenStyle.DashDotLine,
                "dashdotline": Qt.PenStyle.DashDotLine,
                "dashdotdot": Qt.PenStyle.DashDotDotLine,
                "dashdotdotline": Qt.PenStyle.DashDotDotLine,
            }
            return mapping.get(key, default)
        
        # Named bar_width so it does not shadow QWidget.width().
        self.bar_width = int(eval_config.get("width", 30) or 30)
        scale_max = eval_config.get("scale_max", 10.0)
        # Safety check: ensure scale_max is never 0 or negative to prevent division by zero
        if scale_max <= 0:
            scale_max = 10.0  # Use safe default
        self.scale_max = scale_max
        self.divisions = eval_config.get("divisions", [1, 2, 3, 5, 10])
        self._animation_duration_ms = eval_config.get("animation_duration_ms", 300)
        
        colors_config = eval_config.get("colors", {})
        self.white_color = QColor(*colors_config.get("white", [255, 255, 255]))
        self.black_color = QColor(*colors_config.get("black", [0, 0, 0]))

        center_cfg = eval_config.get("center_line", {})
        if isinstance(center_cfg, dict):
            self._center_line_color = _qcolor_from_cfg(center_cfg.get("color"), self._center_line_color)
            self._center_line_width = int(center_cfg.get("width", self._center_line_width) or self._center_line_width)
            self._center_line_style = _pen_style_from_cfg(center_cfg.get("style"), self._center_line_style)

        division_cfg = eval_config.get("division_marks", {})
        if isinstance(division_cfg, dict):
            self._division_marks_color = _qcolor_from_cfg(division_cfg.get("color"), self._division_marks_color)
            self._division_marks_width = int(division_cfg.get("width", self._division_marks_width) or self._division_marks_width)
            self._division_marks_style = _pen_style_from_cfg(division_cfg.get("style"), self._division_marks_style)
        
        # Set fixed width
        self.setFixedWidth(self.bar_width)
        
        # Setup animation timer
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._update_animation)
        self._animation_timer.setInterval(16)  # ~60 FPS
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setMinimumSize(self.bar_width, 100)
        self.setMaximumSize(self.bar_width, 16777215)  # Max height
    
    def set_evaluation_model(self, model: EvaluationModel) -> None:
        """Set the evaluation model to observe.
        
        Args:
            model: EvaluationModel instance.
        """
        if self._evaluation_model:
            # Disconnect from old model
            try:
                self._evaluation_model.evaluation_changed.disconnect(self._on_evaluation_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._evaluation_model = model
        
        if self._evaluation_model:
            # Connect to new model
            self._evaluation_model.evaluation_changed.connect(self._on_evaluation_changed)
            # Initialize with current value
            self._on_evaluation_changed()
    
    def set_flipped(self, is_flipped: bool) -> None:
        """Set board flip state.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if self._is_flipped != is_flipped:
            self._is_flipped = is_flipped
            # When board flips, the evaluation should NOT change
            # The evaluation always represents the same position (from White's perspective)
            # The bar should visually rotate with the board, but the evaluation meaning stays the same
            # So we don't need to flip any values - just update the display
            self.update()
    
    def _on_evaluation_changed(self) -> None:
        """Handle evaluation change from model."""
        if not self._evaluation_model:
            return
        
        # Get target evaluation value (always from White's perspective)
        # Evaluation should not flip when board flips - it always represents the same position
        target_value = self._evaluation_model.get_evaluation_value(self.scale_max)

        # Debug mate-0 mismatches (manual-analysis terminal positions)
        try:
            if bool(getattr(self._evaluation_model, "is_mate", False)) and int(getattr(self._evaluation_model, "mate_moves", 0)) == 0:
                LoggingService.get_instance().debug(
                    "EvalBarWidget target "
                    f"widget_id={id(self)} visible={self.isVisible()} "
                    f"centipawns={getattr(self._evaluation_model, 'centipawns', None)} "
                    f"is_mate={getattr(self._evaluation_model, 'is_mate', None)} "
                    f"mate_moves={getattr(self._evaluation_model, 'mate_moves', None)} "
                    f"scale_max={self.scale_max} target_value={target_value} displayed={self._displayed_value}"
                )
        except Exception:
            pass
        
        # Start animation to target value
        self._start_animation(target_value)
        if self._value_tip.isVisible():
            self._show_value_tip()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        if not self._value_tip.enabled:
            return
        delay = self._value_tip.hover_delay_ms
        if delay <= 0:
            self._show_value_tip()
        else:
            self._hover_timer.start(delay)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_timer.stop()
        self._value_tip.hide_tip()
        super().leaveEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._hover_timer.stop()
        self._value_tip.hide_tip()
        super().hideEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        if not self._value_tip.enabled:
            return
        # Keep the tip glued to the pointer while moving along the bar.
        if self._value_tip.isVisible():
            self._show_value_tip(cursor_global=event.globalPosition().toPoint())
        elif not self._hover_timer.isActive():
            self._hover_timer.start(self._value_tip.hover_delay_ms)

    def _show_value_tip(self, cursor_global: Optional[QPoint] = None) -> None:
        model = self._evaluation_model
        if model is None or not self.underMouse():
            return
        text = model.format_display(self._value_tip.decimals)
        self._value_tip.present(
            self,
            text,
            sign=self._evaluation_sign(model),
            cursor_global=cursor_global,
        )

    @staticmethod
    def _evaluation_sign(model: EvaluationModel) -> int:
        """+1 white advantage, -1 black advantage, 0 equal."""
        if model.is_mate:
            if model.mate_moves > 0:
                return 1
            if model.mate_moves < 0:
                return -1
            return 1 if model.centipawns >= 0 else -1
        if abs(model.centipawns) < 0.5:
            return 0
        return 1 if model.centipawns > 0 else -1
    
    def _start_animation(self, target_value: float) -> None:
        """Start animation to target value.
        
        Args:
            target_value: Target evaluation value to animate to.
        """
        # If target is same as current, no animation needed, but still repaint.
        # This matters for rapid terminal-position updates (e.g. mate-0 synthetic streams)
        # where we may receive repeated identical values; skipping repaint can leave stale pixels.
        if abs(self._displayed_value - target_value) < 0.001:
            self._displayed_value = target_value
            self._target_value = target_value
            self.update()
            return
        
        # Set target
        self._target_value = target_value
        
        # If not animating, start animation
        if not self._is_animating:
            self._animation_start_value = self._displayed_value
            self._animation_start_time = time.time()
            self._is_animating = True
            self._animation_timer.start()
        else:
            # If already animating, continue from current displayed value
            self._animation_start_value = self._displayed_value
    
    def _update_animation(self) -> None:
        """Update animation frame."""
        if not self._is_animating:
            return
        
        current_time = time.time()
        elapsed_ms = (current_time - self._animation_start_time) * 1000.0
        
        if elapsed_ms >= self._animation_duration_ms:
            # Animation complete
            self._displayed_value = self._target_value
            self._is_animating = False
            self._animation_timer.stop()
            self.update()
        else:
            # Interpolate between start and target
            progress = elapsed_ms / self._animation_duration_ms
            # Use easing curve for smooth animation (ease-out)
            # Simple ease-out: 1 - (1 - t)^3
            eased_progress = 1.0 - (1.0 - progress) ** 3
            
            # Interpolate value
            self._displayed_value = self._animation_start_value + (self._target_value - self._animation_start_value) * eased_progress
            self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the evaluation bar.
        
        Args:
            event: Paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        center_y = height / 2.0
        
        # Use animated displayed value
        eval_value = self._displayed_value
        
        # Safety check: ensure scale_max is never 0 to prevent division by zero
        if self.scale_max <= 0:
            self.scale_max = 10.0  # Use safe default
        
        # Calculate bar heights
        # Positive = white advantage (top), negative = black advantage (bottom)
        white_height = 0.0
        black_height = 0.0
        
        if eval_value > 0:
            # White advantage
            white_height = (eval_value / self.scale_max) * center_y
            black_height = 0.0
        elif eval_value < 0:
            # Black advantage
            white_height = 0.0
            black_height = (abs(eval_value) / self.scale_max) * center_y
        else:
            # Equal position
            white_height = 0.0
            black_height = 0.0
        
        # Draw black bar (bottom half)
        if black_height > 0:
            black_rect = QRectF(0, center_y, width, black_height)
            painter.fillRect(black_rect, QBrush(self.black_color))
        
        # Draw white bar (top half)
        if white_height > 0:
            white_rect = QRectF(0, center_y - white_height, width, white_height)
            painter.fillRect(white_rect, QBrush(self.white_color))
        
        # Draw center line
        center_pen = QPen(self._center_line_color, self._center_line_width, self._center_line_style)
        painter.setPen(center_pen)
        painter.drawLine(0, int(center_y), width, int(center_y))
        
        # Draw division marks
        division_pen = QPen(self._division_marks_color, self._division_marks_width, self._division_marks_style)
        painter.setPen(division_pen)
        
        for division in self.divisions:
            # Positive division (white advantage)
            div_y = center_y - (division / self.scale_max) * center_y
            if div_y > 0:
                painter.drawLine(0, int(div_y), width, int(div_y))
            
            # Negative division (black advantage)
            div_y = center_y + (division / self.scale_max) * center_y
            if div_y < height:
                painter.drawLine(0, int(div_y), width, int(div_y))


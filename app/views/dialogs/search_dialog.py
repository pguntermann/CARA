"""Search dialog for searching games in databases."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
    QWidget,
    QScrollArea,
    QSpacerItem,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QPalette, QColor, QFont, QShowEvent, QFontMetrics
from typing import Optional, Dict, Any, List, Tuple, Callable

from app.models.search_criteria import SearchCriteria, SearchField, SearchOperator, LogicOperator, SearchQuery
from app.models.database_model import DatabaseModel

from app.services.game_tags_service import GameTagsService
from app.utils.font_utils import resolve_font_family, scale_font_size


class _ChipWrapContainer(QWidget):
    """Manual wrap layout container for chip buttons."""

    def __init__(self, spacing: int, parent=None) -> None:
        super().__init__(parent)
        self._spacing = int(spacing)
        self._chips: List[QPushButton] = []

    def set_chips(self, chips: List[QPushButton]) -> None:
        self._chips = chips
        self._layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout()

    def _layout(self) -> None:
        if not self._chips:
            self.setMinimumHeight(1)
            return
        w_total = max(1, int(self.width()))
        x = 0
        y = 0
        line_h = 0
        spacing = max(1, int(self._spacing))
        for chip in self._chips:
            try:
                chip.ensurePolished()
                chip.adjustSize()
            except Exception:
                pass
            sh = chip.sizeHint()
            cw = max(int(chip.minimumWidth()), int(sh.width()), 1)
            ch = max(int(chip.minimumHeight()), int(sh.height()), 1)
            if x > 0 and x + cw > w_total:
                x = 0
                y += line_h + spacing
                line_h = 0
            chip.setGeometry(int(x), int(y), int(min(cw, w_total)), int(ch))
            chip.show()
            x += min(cw, w_total) + spacing
            line_h = max(line_h, ch)
        self.setMinimumHeight(int(y + line_h))


class _TagsChipPickerPopup(QFrame):
    """Popup that shows tag chips for multi-select."""

    def __init__(
        self,
        config: Dict[str, Any],
        selected_tags: List[str],
        on_change: Callable[[List[str]], None],
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.config = config
        self._selected = list(selected_tags or [])
        self._on_change = on_change
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Prevent macOS blue focus accent indicators on popup panels.
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        except Exception:
            pass

        # Use the same chip config as the board tag widget for consistency.
        board_cfg = (self.config.get("ui", {}) or {}).get("panels", {}).get("main", {}).get("board", {})
        tags_cfg = board_cfg.get("game_tags_widget", {}) if isinstance(board_cfg, dict) else {}
        self.flow_spacing = int(tags_cfg.get("flow_spacing", 6))
        chip_cfg = tags_cfg.get("chip", {}) if isinstance(tags_cfg.get("chip", {}), dict) else {}
        self.chip_border_radius = int(chip_cfg.get("border_radius", 10))
        self.chip_padding = chip_cfg.get("padding", [2, 8])  # [v, h]
        self.chip_min_height = int(chip_cfg.get("minimum_height", 22))
        self.chip_unmanaged_bg = chip_cfg.get("unmanaged_background_color", [95, 95, 100])

        font_family_raw = chip_cfg.get("font_family", "Helvetica Neue")
        self.chip_font_family = resolve_font_family(font_family_raw)
        self.chip_font_size = int(scale_font_size(chip_cfg.get("font_size", 11)))
        self.chip_font_weight = str(chip_cfg.get("font_weight", "bold")).strip().lower()

        dlg_cfg = (self.config.get("ui", {}) or {}).get("dialogs", {}).get("search", {})
        bg = dlg_cfg.get("background_color", [40, 40, 45])
        border = dlg_cfg.get("border_color", [60, 60, 65])
        tag_picker_cfg = dlg_cfg.get("tag_picker", {}) if isinstance(dlg_cfg.get("tag_picker", {}), dict) else {}
        self._selected_border_color = tag_picker_cfg.get("selected_border_color", [70, 90, 130])
        self._selected_border_width = int(tag_picker_cfg.get("selected_border_width", 2))
        self._bg = QColor(*bg) if isinstance(bg, list) else QColor(40, 40, 45)
        self._border = QColor(*border) if isinstance(border, list) else QColor(60, 60, 65)

        self._popup_width = int(tag_picker_cfg.get("popup_width", 360))
        self._popup_max_height = int(tag_picker_cfg.get("popup_max_height", 260))
        self._layout_margins = tag_picker_cfg.get("popup_layout_margins", [10, 10, 10, 10])
        self._layout_spacing = int(tag_picker_cfg.get("popup_layout_spacing", 8))
        self._extra_height = int(tag_picker_cfg.get("popup_extra_height", 16))

        # Ensure the popup itself is opaque (macOS can otherwise render popups as translucent).
        try:
            self.setAutoFillBackground(True)
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.Window, self._bg)
            self.setPalette(pal)
        except Exception:
            pass

        self.setStyleSheet(
            "QFrame {"
            f"  background-color: rgb({self._bg.red()},{self._bg.green()},{self._bg.blue()});"
            f"  border: 1px solid rgb({self._border.red()},{self._border.green()},{self._border.blue()});"
            "  border-radius: 6px;"
            "}"
            # Make the interior a single uniform panel (macOS overlay scrollbars can look like a blue line).
            "QAbstractScrollArea:focus { outline: none; }"
            "QWidget:focus { outline: none; }"
            "QPushButton:focus { outline: none; }"
        )

        layout = QVBoxLayout(self)
        try:
            m = self._layout_margins
            layout.setContentsMargins(int(m[0]), int(m[1]), int(m[2]), int(m[3]))
        except Exception:
            layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(int(self._layout_spacing))

        self._root = QWidget()
        self._root.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Ensure inner widgets do not paint a separate background (avoids "inner panel" shade).
        try:
            self._root.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        except Exception:
            pass
        self._root.setAutoFillBackground(False)
        self._root.setStyleSheet("background: transparent; border: none;")
        self._root_layout = QVBoxLayout(self._root)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(8)

        # Single chip flow: built-in first, then custom (no captions).
        self._wrap = _ChipWrapContainer(self.flow_spacing, self._root)
        try:
            self._wrap.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        except Exception:
            pass
        self._wrap.setAutoFillBackground(False)
        self._wrap.setStyleSheet("background: transparent; border: none;")
        self._root_layout.addWidget(self._wrap)
        layout.addWidget(self._root, 1)

        # Width/height are config-driven.
        self.setFixedWidth(int(self._popup_width))
        # Ensure the chip wrap container lays out using the correct width immediately.
        try:
            m = self.layout().contentsMargins()
            inner_w = max(1, int(self._popup_width - m.left() - m.right()))
            self._root.setFixedWidth(inner_w)
            self._wrap.setFixedWidth(inner_w)
            self._wrap.resize(inner_w, max(1, self._wrap.height()))
        except Exception:
            pass
        self._rebuild()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Reflow after the popup has a real size on screen, so height can shrink to content.
        def _reflow() -> None:
            try:
                m = self.layout().contentsMargins()
                inner_w = max(1, int(self.width() - m.left() - m.right()))
                self._root.setFixedWidth(inner_w)
                self._wrap.setFixedWidth(inner_w)
                self._wrap.resize(inner_w, max(1, self._wrap.height()))
            except Exception:
                pass
            self._sync_height()

        QTimer.singleShot(0, _reflow)

    def _sync_height(self, *, max_height: int | None = None) -> None:
        """Fit popup height to chip content (no scroll view on macOS)."""
        try:
            # Ensure layout has run and _wrap updated its minimum height.
            self._root.adjustSize()
            self._wrap.adjustSize()
        except Exception:
            pass
        contents_h = int(max(1, self._wrap.minimumHeight()))
        margins = self.layout().contentsMargins() if self.layout() else None
        mh = (int(margins.top()) + int(margins.bottom())) if margins else 20
        # Add a little breathing room for layout spacing.
        target = int(contents_h + mh + int(self._extra_height))
        max_h = int(max_height) if max_height is not None else int(getattr(self, "_popup_max_height", 260))
        if max_h > 0:
            target = min(max_h, target)
        target = max(1, target)
        self.setFixedHeight(int(target))

    def _rebuild(self) -> None:
        defs = GameTagsService(self.config).get_definitions()
        builtins = [d for d in defs if getattr(d, "builtin", False)]
        customs = [d for d in defs if not getattr(d, "builtin", False)]

        selected = {t.casefold() for t in self._selected}

        def mk_chip(name: str, rgb: Tuple[int, int, int]) -> QPushButton:
            btn = QPushButton(name, self._root)
            btn.setCheckable(True)
            btn.setChecked(name.casefold() in selected)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            try:
                btn.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
            except Exception:
                pass
            self._style_chip(btn, QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])))
            btn.toggled.connect(lambda checked, n=name: self._toggle(n, checked))
            return btn

        chips = [mk_chip(d.name, d.color) for d in builtins] + [mk_chip(d.name, d.color) for d in customs]

        for w in self._wrap.findChildren(QPushButton):
            w.setParent(None)
            w.deleteLater()
        for c in chips:
            c.setParent(self._wrap)
        self._wrap.set_chips(chips)
        self._sync_height()

    def _toggle(self, name: str, checked: bool) -> None:
        cur = list(self._selected)
        key = name.casefold()
        if checked:
            if all(t.casefold() != key for t in cur):
                cur.append(name)
        else:
            cur = [t for t in cur if t.casefold() != key]
        self._selected = cur
        if callable(self._on_change):
            self._on_change(list(self._selected))

    def _style_chip(self, chip: QPushButton, color: QColor) -> None:
        chip.setMinimumHeight(int(self.chip_min_height))
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        chip.setFlat(True)

        font = QFont(self.chip_font_family, self.chip_font_size)
        if self.chip_font_weight in ("bold", "700", "800", "900"):
            font.setBold(True)
        chip.setFont(font)

        bg = f"rgb({color.red()}, {color.green()}, {color.blue()})"
        lum = 0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()
        text = "rgb(15, 15, 18)" if lum > 150 else "rgb(245, 245, 245)"
        pad_v = int(self.chip_padding[0]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 1 else 2
        pad_h = int(self.chip_padding[1]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 2 else 8

        fm = QFontMetrics(font)
        chip.setMinimumWidth(int(fm.horizontalAdvance(chip.text()) + 2 * pad_h + 8))

        # Checked state uses configurable blue outline.
        sel = self._selected_border_color if isinstance(self._selected_border_color, list) else [70, 90, 130]
        sel_w = max(1, int(self._selected_border_width))
        sel_css = f"rgba({int(sel[0])}, {int(sel[1])}, {int(sel[2])}, 255)"
        chip.setStyleSheet(
            "QPushButton {"
            f"  background-color: {bg};"
            f"  color: {text};"
            f"  border-radius: {int(self.chip_border_radius)}px;"
            f"  padding: {pad_v}px {pad_h}px;"
            "  border: 1px solid rgba(0,0,0,0);"
            "}"
            "QPushButton:hover {"
            "  border: 1px solid rgba(255,255,255,0.30);"
            "}"
            "QPushButton:checked {"
            f"  border: {sel_w}px solid {sel_css};"
            "}"
            "QPushButton:checked:hover {"
            f"  border: {sel_w}px solid {sel_css};"
            "}"
        )




class CriteriaRowWidget(QWidget):
    """Widget representing a single search criterion row."""
    
    removed = pyqtSignal()  # Emitted when remove button is clicked
    
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize criteria row widget.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self._load_config()
        self._setup_ui()
        self._apply_styling()
    
    def _load_config(self) -> None:
        """Load configuration values."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        
        # Inputs
        inputs_config = dialog_config.get("inputs", {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        input_font_family_raw = inputs_config.get("font_family", "Cascadia Mono")
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = QColor(*inputs_config.get("text_color", [240, 240, 240]))
        self.input_bg_color = QColor(*inputs_config.get("background_color", [30, 30, 35]))
        self.input_border_color = QColor(*inputs_config.get("border_color", [60, 60, 65]))
        self.input_focus_border_color = QColor(*inputs_config.get("focus_border_color", [70, 90, 130]))
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_height = buttons_config.get("height", 30)
        self.small_button_width = buttons_config.get("small_width", 80)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        self.label_font_family = labels_config.get("font_family", "Helvetica Neue")
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.label_font_size = scale_font_size(labels_config.get("font_size", 11))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
    
    def _setup_ui(self) -> None:
        """Setup the criteria row UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(8)
        
        # Logic connector (AND/OR) - hidden for first row
        self.logic_combo = QComboBox()
        self.logic_combo.addItems(["AND", "OR"])
        self.logic_combo.setCurrentText("AND")
        self.logic_combo.setFixedWidth(70)
        self.logic_combo.setVisible(False)  # Hidden by default
        layout.addWidget(self.logic_combo)
        
        # Field selector
        self.field_combo = QComboBox()
        self.field_combo.addItems([
            "White", "Black", "WhiteElo", "BlackElo", "Result", "Date", 
            "Event", "Site", "ECO", "TimeControl", "TC Type", "Analyzed", "Annotated", "Tags", "Custom PGN Tag"
        ])
        self.field_combo.setFixedWidth(120)
        self.field_combo.currentTextChanged.connect(self._on_field_changed)
        layout.addWidget(self.field_combo)
        
        # Operator selector
        self.operator_combo = QComboBox()
        self.operator_combo.addItems(["contains", "equals", "starts with", "ends with"])
        self.operator_combo.setFixedWidth(140)  # Increased from 100
        layout.addWidget(self.operator_combo)
        
        # Value input
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Value...")
        self.value_input.setMinimumWidth(100)  # Reduced from 150
        self.value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.value_input)

        # Tags picker (hidden by default; used when field == "Tags")
        self._selected_tags: List[str] = []
        self.tags_picker_btn = QPushButton("Select tags…")
        self.tags_picker_btn.setVisible(False)
        self.tags_picker_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tags_picker_btn.clicked.connect(self._open_tags_picker_popup)
        layout.addWidget(self.tags_picker_btn)
        self._tags_popup: Optional[_TagsChipPickerPopup] = None
        
        # Custom tag name input (hidden by default)
        self.custom_tag_input = QLineEdit()
        self.custom_tag_input.setPlaceholderText("Tag name...")
        self.custom_tag_input.setFixedWidth(120)
        self.custom_tag_input.setVisible(False)
        layout.addWidget(self.custom_tag_input)
        
        # Remove button (smaller to match input field height)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.removed.emit)
        layout.addWidget(self.remove_btn)
        
        # Initialize operators for the default field selection (after all widgets are created)
        self._on_field_changed(self.field_combo.currentText())
    
    def _on_field_changed(self, field_text: str) -> None:
        """Handle field selection change."""
        # Update operators based on field type
        self.operator_combo.clear()

        # Close popup when switching fields
        try:
            if self._tags_popup is not None:
                self._tags_popup.close()
        except Exception:
            pass
        
        if field_text in ["Analyzed", "Annotated"]:
            self.operator_combo.addItems(["is", "is not"])
            # Keep value input visible but disable it for boolean fields
            self.value_input.setVisible(True)
            self.value_input.setEnabled(False)
            self.value_input.clear()
            self.value_input.setPlaceholderText("")
            self.custom_tag_input.setVisible(False)
        elif field_text in ["WhiteElo", "BlackElo"]:
            self.operator_combo.addItems([
                "equals", "not equals", "greater than", "less than", 
                "greater than or equal", "less than or equal"
            ])
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.value_input.setPlaceholderText("Value...")
            self.custom_tag_input.setVisible(False)
        elif field_text == "TimeControl":
            self.operator_combo.addItems([
                "equals", "not equals", "greater than", "less than",
                "greater than or equal", "less than or equal",
                "is empty", "is not empty"
            ])
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.value_input.setPlaceholderText("Base seconds (e.g. 300, 600)")
            self.custom_tag_input.setVisible(False)
        elif field_text == "Date":
            self.operator_combo.addItems([
                "contains", "equals", "not equals", "before", "after"
            ])
            self.value_input.setPlaceholderText("YYYY.MM.DD (use ?? for unknown)")
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.custom_tag_input.setVisible(False)
        elif field_text == "Custom PGN Tag":
            self.operator_combo.addItems(["contains", "equals", "not equals", "starts with", "ends with"])
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.value_input.setPlaceholderText("Value...")
            self.custom_tag_input.setVisible(True)
        elif field_text == "Tags":
            self.operator_combo.addItems(["contains", "does not contain"])
            self.value_input.setVisible(False)
            self.tags_picker_btn.setVisible(True)
            self._sync_tags_picker_label()
            self.custom_tag_input.setVisible(False)
        else:
            # Text fields
            self.operator_combo.addItems([
                "contains", "equals", "not equals", "starts with", "ends with", 
                "is empty", "is not empty"
            ])
            self.value_input.setPlaceholderText("Value...")
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.tags_picker_btn.setVisible(False)
            self.custom_tag_input.setVisible(False)
    
    def _apply_styling(self) -> None:
        """Apply styling to widgets."""
        # Get button styling config
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {}).get("buttons", {})
        button_bg_offset = buttons_config.get("background_offset", 20)
        button_hover_offset = buttons_config.get("hover_background_offset", 30)
        button_pressed_offset = buttons_config.get("pressed_background_offset", 10)
        button_border_radius = buttons_config.get("border_radius", 3)
        button_padding = buttons_config.get("padding", 5)
        
        # Get dialog background color for button styling
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        text_color = dialog_config.get("text_color", [200, 200, 200])
        font_family = dialog_config.get("font_family", "Helvetica Neue")
        font_size = dialog_config.get("font_size", 11)
        
        # Apply button styling using StyleManager (uses unified config)
        # Use smaller padding for the Remove button to match input field height better
        from app.views.style import StyleManager
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {}).get("buttons", {})
        border_color = buttons_config.get("border_color", [60, 60, 65])
        # Use smaller padding (3px) for inline button
        StyleManager.style_buttons(
            [self.remove_btn, self.tags_picker_btn],
            self.config,
            bg_color,
            border_color,
            padding=3
        )
        
        # Apply combobox styling using StyleManager
        # Get selection colors from config (use defaults if not available)
        inputs_config = self.config.get('ui', {}).get('dialogs', {}).get('search', {}).get('inputs', {})
        selection_bg = inputs_config.get('selection_background_color', [70, 90, 130])
        selection_text = inputs_config.get('selection_text_color', [240, 240, 240])
        
        comboboxes = [self.field_combo, self.operator_combo, self.logic_combo]
        text_color = [self.input_text_color.red(), self.input_text_color.green(), self.input_text_color.blue()]
        bg_color = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        border_color = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        focus_border_color = [self.input_focus_border_color.red(), self.input_focus_border_color.green(), self.input_focus_border_color.blue()]
        
        StyleManager.style_comboboxes(
            comboboxes,
            self.config,
            text_color,
            self.input_font_family,
            self.input_font_size,
            bg_color,
            border_color,
            focus_border_color,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=self.input_border_radius,
            padding=self.input_padding,
            editable=False
        )
        
        # Apply unified line edit styling using StyleManager
        # Get padding from config (preserve existing format for alignment)
        # self.input_padding is already in [horizontal, vertical] format from _load_config
        input_padding = self.input_padding if isinstance(self.input_padding, list) and len(self.input_padding) == 2 else [8, 6]
        
        # Use dialog-specific background color and font to match combobox styling
        bg_color = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        border_color = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        focus_border_color = [self.input_focus_border_color.red(), self.input_focus_border_color.green(), self.input_focus_border_color.blue()]
        
        StyleManager.style_line_edits(
            [self.value_input, self.custom_tag_input],
            self.config,
            font_family=self.input_font_family,  # Match original dialog font
            font_size=self.input_font_size,  # Match original dialog font size
            bg_color=bg_color,  # Match combobox background color
            border_color=border_color,  # Match combobox border color
            focus_border_color=focus_border_color,  # Match combobox focus border color
            padding=input_padding  # Preserve existing padding for alignment
        )
        
        # Set Remove button height to match input field height
        # Use the combo box height as reference since it has the same styling
        self.field_combo.updateGeometry()
        combo_height = self.field_combo.sizeHint().height()
        if combo_height <= 0:
            # Fallback: calculate from font metrics
            from PyQt6.QtGui import QFontMetrics, QFont
            font = QFont(self.input_font_family, self.input_font_size)
            fm = QFontMetrics(font)
            text_height = fm.height()
            combo_height = text_height + (self.input_padding[1] * 2) + 2
        self.remove_btn.setFixedSize(self.small_button_width, combo_height)
        self.tags_picker_btn.setFixedHeight(combo_height)
    
    def get_criterion(self) -> Optional[SearchCriteria]:
        """Get SearchCriteria from this row.
        
        Returns:
            SearchCriteria instance or None if invalid.
        """
        field_text = self.field_combo.currentText()
        operator_text = self.operator_combo.currentText()
        value_text = self.value_input.text().strip()
        custom_tag = self.custom_tag_input.text().strip() if self.custom_tag_input.isVisible() else None
        logic_text = self.logic_combo.currentText()
        
        # Map field text to SearchField enum
        field_map = {
            "White": SearchField.WHITE,
            "Black": SearchField.BLACK,
            "WhiteElo": SearchField.WHITE_ELO,
            "BlackElo": SearchField.BLACK_ELO,
            "Result": SearchField.RESULT,
            "Date": SearchField.DATE,
            "Event": SearchField.EVENT,
            "Site": SearchField.SITE,
            "ECO": SearchField.ECO,
            "TimeControl": SearchField.TIMECONTROL,
            "TC Type": SearchField.TC_TYPE,
            "Analyzed": SearchField.ANALYZED,
            "Annotated": SearchField.ANNOTATED,
            "Tags": SearchField.TAGS,
            "Custom PGN Tag": SearchField.CUSTOM_TAG,
        }
        field = field_map.get(field_text)
        if field is None:
            return None
        
        # Map operator text to SearchOperator enum
        operator_map = {
            "contains": SearchOperator.CONTAINS,
            "equals": SearchOperator.EQUALS,
            "not equals": SearchOperator.NOT_EQUALS,
            "does not contain": SearchOperator.DOES_NOT_CONTAIN,
            "starts with": SearchOperator.STARTS_WITH,
            "ends with": SearchOperator.ENDS_WITH,
            "is empty": SearchOperator.IS_EMPTY,
            "is not empty": SearchOperator.IS_NOT_EMPTY,
            "greater than": SearchOperator.GREATER_THAN,
            "less than": SearchOperator.LESS_THAN,
            "greater than or equal": SearchOperator.GREATER_THAN_OR_EQUAL,
            "less than or equal": SearchOperator.LESS_THAN_OR_EQUAL,
            "before": SearchOperator.DATE_BEFORE,
            "after": SearchOperator.DATE_AFTER,
            "is": SearchOperator.IS_TRUE,
            "is not": SearchOperator.IS_FALSE,
        }
        operator = operator_map.get(operator_text)
        if operator is None:
            return None
        
        # Map text "equals" to appropriate enum based on field type
        if operator == SearchOperator.EQUALS:
            if field in [SearchField.WHITE_ELO, SearchField.BLACK_ELO, SearchField.TIMECONTROL]:
                operator = SearchOperator.EQUALS_NUM
            elif field == SearchField.DATE:
                operator = SearchOperator.DATE_EQUALS
        
        # Map text "not equals" to appropriate enum based on field type
        if operator == SearchOperator.NOT_EQUALS:
            if field in [SearchField.WHITE_ELO, SearchField.BLACK_ELO, SearchField.TIMECONTROL]:
                operator = SearchOperator.NOT_EQUALS_NUM
            elif field == SearchField.DATE:
                operator = SearchOperator.DATE_NOT_EQUALS
        
        # Get value (handle special cases)
        if field in [SearchField.ANALYZED, SearchField.ANNOTATED]:
            value = True  # Value doesn't matter for boolean
        elif operator in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
            value = None
        elif field == SearchField.TAGS:
            value = list(self._selected_tags)
            if not value:
                return None
        elif field == SearchField.TIMECONTROL and operator not in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
            # Parse TimeControl value as integer (base seconds)
            try:
                value = int(value_text.strip()) if value_text.strip() else None
            except ValueError:
                value = None
        else:
            value = value_text
        
        # Get logic operator
        logic_op = LogicOperator.AND if logic_text == "AND" else LogicOperator.OR
        
        return SearchCriteria(
            field=field,
            operator=operator,
            value=value,
            logic_operator=logic_op,
            custom_tag_name=custom_tag if field == SearchField.CUSTOM_TAG else None
        )
    
    def set_group_start(self, is_start: bool, group_level: int = 0) -> None:
        """Mark this row as a group start.
        
        Args:
            is_start: True if this is a group start.
            group_level: Nesting level.
        """
        # Visual indication could be added here (indentation, background color)
        pass
    
    def set_criterion(self, criterion: SearchCriteria) -> None:
        """Set the criterion values from a SearchCriteria object.
        
        Args:
            criterion: SearchCriteria to populate this row with.
        """
        # Map SearchField enum to field text
        field_map = {
            SearchField.WHITE: "White",
            SearchField.BLACK: "Black",
            SearchField.WHITE_ELO: "WhiteElo",
            SearchField.BLACK_ELO: "BlackElo",
            SearchField.RESULT: "Result",
            SearchField.DATE: "Date",
            SearchField.EVENT: "Event",
            SearchField.SITE: "Site",
            SearchField.ECO: "ECO",
            SearchField.TIMECONTROL: "TimeControl",
            SearchField.TC_TYPE: "TC Type",
            SearchField.ANALYZED: "Analyzed",
            SearchField.ANNOTATED: "Annotated",
            SearchField.TAGS: "Tags",
            SearchField.CUSTOM_TAG: "Custom PGN Tag",
        }
        field_text = field_map.get(criterion.field)
        if field_text:
            self.field_combo.setCurrentText(field_text)
            # Trigger field change to update operators
            self._on_field_changed(field_text)
        
        # Map SearchOperator enum to operator text
        operator_map = {
            SearchOperator.CONTAINS: "contains",
            SearchOperator.EQUALS: "equals",
            SearchOperator.NOT_EQUALS: "not equals",
            SearchOperator.DOES_NOT_CONTAIN: "does not contain",
            SearchOperator.STARTS_WITH: "starts with",
            SearchOperator.ENDS_WITH: "ends with",
            SearchOperator.IS_EMPTY: "is empty",
            SearchOperator.IS_NOT_EMPTY: "is not empty",
            SearchOperator.EQUALS_NUM: "equals",
            SearchOperator.NOT_EQUALS_NUM: "not equals",
            SearchOperator.GREATER_THAN: "greater than",
            SearchOperator.LESS_THAN: "less than",
            SearchOperator.GREATER_THAN_OR_EQUAL: "greater than or equal",
            SearchOperator.LESS_THAN_OR_EQUAL: "less than or equal",
            SearchOperator.DATE_EQUALS: "equals",
            SearchOperator.DATE_NOT_EQUALS: "not equals",
            SearchOperator.DATE_BEFORE: "before",
            SearchOperator.DATE_AFTER: "after",
            SearchOperator.DATE_CONTAINS: "contains",
            SearchOperator.IS_TRUE: "is",
            SearchOperator.IS_FALSE: "is not",
        }
        operator_text = operator_map.get(criterion.operator)
        if operator_text and operator_text in [self.operator_combo.itemText(i) for i in range(self.operator_combo.count())]:
            self.operator_combo.setCurrentText(operator_text)
        
        # Set value (if applicable)
        if criterion.value is not None and criterion.operator not in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
            if criterion.field not in [SearchField.ANALYZED, SearchField.ANNOTATED]:
                if criterion.field == SearchField.TAGS and isinstance(criterion.value, list):
                    self._selected_tags = [str(x) for x in criterion.value if str(x).strip()]
                    self._sync_tags_picker_label()
                else:
                    self.value_input.setText(str(criterion.value))
        
        # Set custom tag if applicable
        if criterion.field == SearchField.CUSTOM_TAG and criterion.custom_tag_name:
            self.custom_tag_input.setText(criterion.custom_tag_name)
        
        # Set logic operator
        if criterion.logic_operator:
            logic_text = "AND" if criterion.logic_operator == LogicOperator.AND else "OR"
            self.logic_combo.setCurrentText(logic_text)

    def _sync_tags_picker_label(self) -> None:
        if not getattr(self, "_selected_tags", None):
            self.tags_picker_btn.setText("Select tags…")
        elif len(self._selected_tags) == 1:
            self.tags_picker_btn.setText(self._selected_tags[0])
        else:
            self.tags_picker_btn.setText(f"{len(self._selected_tags)} tags")

    def _open_tags_picker_popup(self) -> None:
        """Open chip-based popup picker for tags."""
        # Toggle behavior: if already open, close.
        if self._tags_popup is not None and self._tags_popup.isVisible():
            self._tags_popup.close()
            return

        def on_change(new_tags: List[str]) -> None:
            self._selected_tags = new_tags
            self._sync_tags_picker_label()

        self._tags_popup = _TagsChipPickerPopup(
            self.config,
            selected_tags=list(self._selected_tags),
            on_change=on_change,
            parent=self,
        )

        dlg_cfg = (self.config.get("ui", {}) or {}).get("dialogs", {}).get("search", {})
        tag_picker_cfg = dlg_cfg.get("tag_picker", {}) if isinstance(dlg_cfg.get("tag_picker", {}), dict) else {}
        anchor_gap_y = int(tag_picker_cfg.get("popup_anchor_gap_y", 24))
        flip_gap_y = int(tag_picker_cfg.get("popup_flip_gap_y", 12))
        prefer_below_min_space = int(tag_picker_cfg.get("popup_min_bottom_space_to_prefer_below", 140))

        # Position popup below the button (explicitly), and clamp to the current screen.
        from PyQt6.QtCore import QPoint
        p = self.tags_picker_btn.mapToGlobal(QPoint(0, self.tags_picker_btn.height()))
        x = int(p.x())
        # Leave plenty of room for the popup's border/shadow so it doesn't collide with the button (macOS).
        y = int(p.y() + anchor_gap_y)
        try:
            scr = self.tags_picker_btn.screen()
            geom = scr.availableGeometry() if scr is not None else None
        except Exception:
            geom = None
        if geom is not None:
            # Keep within horizontal bounds.
            x = max(int(geom.left()), min(x, int(geom.right() - self._tags_popup.width())))
            # Clamp height to available screen space and choose open direction.
            bottom_space = int(geom.bottom() - y)
            top = int(self.tags_picker_btn.mapToGlobal(QPoint(0, 0)).y())
            top_space = int(top - int(geom.top()) - anchor_gap_y)
            # Prefer opening below; if not enough space, open above.
            if bottom_space < prefer_below_min_space and top_space > bottom_space:
                # Open above the button.
                self._tags_popup._sync_height(max_height=max(1, top_space))
                y = int(top - self._tags_popup.height() - flip_gap_y)
                y = max(int(geom.top()), y)
            else:
                self._tags_popup._sync_height(max_height=max(1, bottom_space))
        self._tags_popup.move(int(x), int(y))
        self._tags_popup.show()

    def _toggle_selected_tag(self, tag_name: str, checked: bool) -> None:
        name = str(tag_name or "").strip()
        if not name:
            return
        cur = list(self._selected_tags or [])
        key = name.casefold()
        if checked:
            if all(t.casefold() != key for t in cur):
                cur.append(name)
        else:
            cur = [t for t in cur if t.casefold() != key]
        self._selected_tags = cur
        self._sync_tags_picker_label()
    
    def set_group_end(self, is_end: bool) -> None:
        """Mark this row as a group end.
        
        Args:
            is_end: True if this is a group end.
        """
        # Visual indication could be added here
        pass
    
    def set_indentation(self, level: int) -> None:
        """Set visual indentation level.
        
        Args:
            level: Indentation level (0 = no indent).
        """
        # Add left margin for indentation
        layout = self.layout()
        if layout:
            margins = layout.contentsMargins()
            layout.setContentsMargins(level * 20, margins.top(), margins.right(), margins.bottom())
            
            # Add visual indicator (vertical line) for indented rows
            if level > 0:
                # Create a visual separator widget if it doesn't exist
                if not hasattr(self, '_indent_widget'):
                    from PyQt6.QtWidgets import QFrame
                    self._indent_widget = QFrame(self)
                    self._indent_widget.setFrameShape(QFrame.Shape.VLine)
                    self._indent_widget.setFrameShadow(QFrame.Shadow.Sunken)
                    self._indent_widget.setStyleSheet("QFrame { color: rgba(100, 120, 160, 100); max-width: 2px; }")
                    self._indent_widget.setFixedWidth(2)
                    layout.insertWidget(0, self._indent_widget)
                self._indent_widget.setVisible(True)
            elif hasattr(self, '_indent_widget'):
                self._indent_widget.setVisible(False)


class SearchDialog(QDialog):
    """Dialog for searching games in databases."""
    
    # Class variable to store last search query in memory (session-only)
    _last_search_query: Optional[SearchQuery] = None
    
    def __init__(self, config: Dict[str, Any], 
                 active_database: Optional[DatabaseModel],
                 all_databases: List[DatabaseModel],
                 parent=None) -> None:
        """Initialize the search dialog.
        
        Args:
            config: Configuration dictionary.
            active_database: Currently active database (None if none).
            all_databases: List of all open databases.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.active_database = active_database
        self.all_databases = all_databases
        self.search_query: Optional[SearchQuery] = None
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('search', {})
        width = dialog_config.get('width', 800)
        height = dialog_config.get('height', 600)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Search Games")
        
        # Add initial criterion row or restore last search query
        if SearchDialog._last_search_query is not None:
            self._restore_last_search()
        else:
            self._add_criterion_row(is_group_start=True)
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get("width", 800)
        self.dialog_height = dialog_config.get("height", 600)
        
        # Background color
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.bg_color = QColor(bg_color[0], bg_color[1], bg_color[2])
        
        # Text color
        text_color = dialog_config.get("text_color", [200, 200, 200])
        self.text_color = QColor(text_color[0], text_color[1], text_color[2])
        
        # Font
        from app.utils.font_utils import scale_font_size
        font_size = dialog_config.get("font_size", 11)
        self.font_family = dialog_config.get("font_family", "Helvetica Neue")
        self.font_size = scale_font_size(font_size)
        
        # Layout
        layout_config = dialog_config.get("layout", {})
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])
        self.layout_spacing = layout_config.get("spacing", 15)
        
        # Spacing
        spacing_config = dialog_config.get("spacing", {})
        self.section_spacing = spacing_config.get("section", 15)
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)
        self.small_button_width = buttons_config.get("small_width", 100)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        self.label_font_family = labels_config.get("font_family", "Helvetica Neue")
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.label_font_size = scale_font_size(labels_config.get("font_size", 11))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        
        # Groups
        groups_config = dialog_config.get("groups", {})
        # Use unified default if not specified in dialog config
        bg_color = groups_config.get("background_color")
        if bg_color is None:
            # Get unified default
            styles_config = self.config.get('ui', {}).get('styles', {})
            group_box_config = styles_config.get('group_box', {})
            bg_color = group_box_config.get('background_color')
        # Handle transparent background (None) - create a transparent QColor
        if bg_color is None:
            self.group_bg_color = QColor(0, 0, 0, 0)  # Transparent
        else:
            self.group_bg_color = QColor(*bg_color)
        self.group_border_color = QColor(*groups_config.get("border_color", [60, 60, 65]))
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        main_layout = QVBoxLayout(self)
        # Set spacing to 0 to disable automatic spacing - we'll use explicit spacing instead
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3]
        )
        
        # Search Scope section
        scope_group = QGroupBox("Search Scope")
        scope_layout = QHBoxLayout()
        scope_layout.setSpacing(8)
        
        self.scope_button_group = QButtonGroup(self)
        self.active_radio = QRadioButton("Active database")
        self.all_radio = QRadioButton("All open databases")
        self.scope_button_group.addButton(self.active_radio, 0)
        self.scope_button_group.addButton(self.all_radio, 1)
        
        # Set default based on availability
        if self.active_database:
            self.active_radio.setChecked(True)
        else:
            self.all_radio.setChecked(True)
            self.active_radio.setEnabled(False)
        
        scope_layout.addWidget(self.active_radio)
        scope_layout.addWidget(self.all_radio)
        scope_layout.addStretch()
        scope_group.setLayout(scope_layout)
        main_layout.addWidget(scope_group)
        
        main_layout.addSpacing(self.section_spacing)
        
        # Search Criteria section
        criteria_group = QGroupBox("Search Criteria")
        criteria_layout = QVBoxLayout()
        criteria_layout.setSpacing(8)
        
        # Scroll area for criteria rows
        from PyQt6.QtWidgets import QFrame
        self.criteria_scroll_area = QScrollArea()
        self.criteria_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.criteria_scroll_area.setWidgetResizable(True)
        self.criteria_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.criteria_container = QWidget()
        self.criteria_layout = QVBoxLayout(self.criteria_container)
        self.criteria_layout.setSpacing(5)
        self.criteria_layout.setContentsMargins(5, 5, 5, 5)
        self.criteria_layout.addStretch()
        
        self.criteria_scroll_area.setWidget(self.criteria_container)
        criteria_layout.addWidget(self.criteria_scroll_area)
        
        # Buttons for managing criteria
        criteria_buttons_layout = QHBoxLayout()
        criteria_buttons_layout.setSpacing(self.button_spacing)
        criteria_buttons_layout.addStretch()
        
        self.start_group_btn = QPushButton("Start Group")
        self.start_group_btn.setFixedSize(self.button_width, self.button_height)
        self.start_group_btn.clicked.connect(self._on_start_group_clicked)
        criteria_buttons_layout.addWidget(self.start_group_btn)
        
        self.end_group_btn = QPushButton("End Group")
        self.end_group_btn.setFixedSize(self.button_width, self.button_height)
        self.end_group_btn.clicked.connect(self._on_end_group_clicked)
        criteria_buttons_layout.addWidget(self.end_group_btn)
        
        self.add_criterion_btn = QPushButton("Add Criterion")
        self.add_criterion_btn.setFixedSize(self.button_width, self.button_height)
        self.add_criterion_btn.clicked.connect(self._add_criterion_row)
        criteria_buttons_layout.addWidget(self.add_criterion_btn)
        
        criteria_layout.addLayout(criteria_buttons_layout)
        criteria_group.setLayout(criteria_layout)
        main_layout.addWidget(criteria_group)
        
        # Buttons at bottom
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(self.button_spacing)
        buttons_layout.addStretch()
        
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        buttons_layout.addWidget(self.search_btn)
        
        # Add spacing before buttons
        main_layout.addSpacing(self.section_spacing)
        main_layout.addLayout(buttons_layout)
        
        # Track criteria rows
        self.criteria_rows: List[CriteriaRowWidget] = []
        self.group_starts: List[int] = []  # Track which rows are group starts
        self.group_ends: List[int] = []  # Track which rows are group ends
        self.group_levels: Dict[int, int] = {}  # Track group nesting levels
    
    def _add_criterion_row(self, is_group_start: bool = False) -> None:
        """Add a new criterion row.
        
        Args:
            is_group_start: If True, mark this row as a group start.
        """
        row = CriteriaRowWidget(self.config, self)
        row.removed.connect(lambda: self._remove_criterion_row(row))
        
        # Insert before stretch
        count = self.criteria_layout.count()
        self.criteria_layout.insertWidget(count - 1, row)
        idx = len(self.criteria_rows)
        self.criteria_rows.append(row)
        
        # Mark as group start if requested
        if is_group_start:
            # Calculate group level (count how many groups we're nested in)
            group_level = 0
            for start_idx in sorted(self.group_starts):
                if start_idx < idx:
                    group_level = self.group_levels.get(start_idx, 0) + 1
                else:
                    break
            self.group_starts.append(idx)
            self.group_levels[idx] = group_level
        
        # Show logic connector for all rows except first
        if len(self.criteria_rows) > 1:
            row.logic_combo.setVisible(True)
        
        # Update visual indicators
        self._update_group_indentation()
    
    def _remove_criterion_row(self, row: CriteriaRowWidget) -> None:
        """Remove a criterion row.
        
        Args:
            row: CriteriaRowWidget to remove.
        """
        if row in self.criteria_rows:
            idx = self.criteria_rows.index(row)
            self.criteria_rows.remove(row)
            self.criteria_layout.removeWidget(row)
            row.deleteLater()
            
            # Remove from group tracking
            if idx in self.group_starts:
                self.group_starts.remove(idx)
                if idx in self.group_levels:
                    del self.group_levels[idx]
            if idx in self.group_ends:
                self.group_ends.remove(idx)
            
            # Update indices for remaining groups
            new_group_starts = []
            new_group_ends = []
            new_group_levels = {}
            for old_idx in self.group_starts:
                if old_idx < idx:
                    new_group_starts.append(old_idx)
                    if old_idx in self.group_levels:
                        new_group_levels[old_idx] = self.group_levels[old_idx]
                elif old_idx > idx:
                    new_group_starts.append(old_idx - 1)
                    if old_idx in self.group_levels:
                        new_group_levels[old_idx - 1] = self.group_levels[old_idx]
            for old_idx in self.group_ends:
                if old_idx < idx:
                    new_group_ends.append(old_idx)
                elif old_idx > idx:
                    new_group_ends.append(old_idx - 1)
            
            self.group_starts = new_group_starts
            self.group_ends = new_group_ends
            self.group_levels = new_group_levels
            
            # Update logic connector visibility
            if len(self.criteria_rows) > 0:
                self.criteria_rows[0].logic_combo.setVisible(False)
                if len(self.criteria_rows) > 1:
                    self.criteria_rows[1].logic_combo.setVisible(True)
            
            # Update visual indicators
            self._update_group_indentation()
    
    def _on_start_group_clicked(self) -> None:
        """Handle Start Group button click - adds a new criterion row marked as group start."""
        self._add_criterion_row(is_group_start=True)
    
    def _on_end_group_clicked(self) -> None:
        """Handle End Group button click - marks the last criterion as group end."""
        if not self.criteria_rows:
            return
        
        idx = len(self.criteria_rows) - 1
        
        # Find matching group start (most recent start before this end)
        matching_start = None
        
        for start_idx in sorted(self.group_starts, reverse=True):
            if start_idx < idx:
                # Check if there's already an end for this start
                has_end = any(end_idx > start_idx and end_idx <= idx for end_idx in self.group_ends)
                if not has_end:
                    matching_start = start_idx
                    break
        
        if matching_start is not None:
            # Add group end marker
            if idx not in self.group_ends:
                self.group_ends.append(idx)
        
        # Update visual indicators
        self.update_group_visuals()
    
    def _update_group_indentation(self) -> None:
        """Update visual indentation for grouped rows."""
        self.update_group_visuals()
    
    def update_group_visuals(self) -> None:
        """Update all visual indicators for groups."""
        # Calculate indentation for each row based on group nesting
        for i, row in enumerate(self.criteria_rows):
            # Calculate how many groups this row is nested in
            indent_level = 0
            current_group_start = None
            
            for start_idx in sorted(self.group_starts):
                if start_idx <= i:
                    # Find matching end for this start
                    matching_end = None
                    for end_idx in sorted(self.group_ends):
                        if end_idx > start_idx:
                            # Check if there's a nested start between start_idx and end_idx
                            has_nested_start = any(s > start_idx and s < end_idx for s in self.group_starts)
                            if not has_nested_start:
                                matching_end = end_idx
                                break
                    
                    # If this row is between start and end (or end not found yet), it's in this group
                    if matching_end is None or matching_end >= i:
                        if start_idx < i:
                            indent_level += 1
                        if start_idx == i:
                            current_group_start = start_idx
                else:
                    break
            
            # Apply indentation
            row.set_indentation(indent_level)
            
            # Visual indicator: add background color and border for grouped rows
            base_style = ""
            if i in self.group_starts:
                # Group start: left border
                base_style += "QWidget { border-left: 3px solid rgba(100, 150, 255, 150); padding-left: 5px; }"
            if i in self.group_ends:
                # Group end: right border
                base_style += "QWidget { border-right: 3px solid rgba(100, 150, 255, 150); padding-right: 5px; }"
            if indent_level > 0:
                # Nested rows: subtle background
                base_style += "QWidget { background-color: rgba(70, 90, 130, 20); }"
            
            if base_style:
                row.setStyleSheet(base_style)
            else:
                row.setStyleSheet("")
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json."""
        # Background color
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Group box styling (matching bulk replace dialog)
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        groups_config = dialog_config.get("groups", {})
        dialog_bg = dialog_config.get("background_color", [40, 40, 45])
        dialog_border = dialog_config.get("border_color", [60, 60, 65])
        
        group_bg_color = groups_config.get("background_color")  # None = use unified default
        group_border_color = groups_config.get("border_color", dialog_border) if "border_color" in groups_config else dialog_border
        group_border_width = groups_config.get("border_width", 1)
        group_border_radius = groups_config.get("border_radius", 5)
        from app.utils.font_utils import resolve_font_family, scale_font_size
        from app.views.style import StyleManager
        group_title_font_family = resolve_font_family(groups_config.get("title_font_family", "Helvetica Neue"))
        group_title_font_size = scale_font_size(groups_config.get("title_font_size", 11))
        group_title_color = groups_config.get("title_color", [240, 240, 240])
        group_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        group_margin_top = groups_config.get("margin_top", 10)
        group_padding_top = groups_config.get("padding_top", 5)
        group_title_left = groups_config.get("title_left", 10)
        group_title_padding = groups_config.get("title_padding", [0, 5])
        
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=group_border_color,
                border_width=group_border_width,
                border_radius=group_border_radius,
                bg_color=group_bg_color,
                margin_top=group_margin_top,
                padding_top=group_padding_top,
                title_font_family=group_title_font_family,
                title_font_size=group_title_font_size,
                title_color=group_title_color,
                title_left=group_title_left,
                title_padding=group_title_padding,
                content_margins=group_content_margins
            )
        
        # Apply radio button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        radio_buttons = list(self.findChildren(QRadioButton))
        if radio_buttons:
            StyleManager.style_radio_buttons(radio_buttons, self.config)
        
        # Scroll area styling
        inputs_config = dialog_config.get("inputs", {})
        input_bg = inputs_config.get("background_color", [30, 30, 35])
        input_border = inputs_config.get("border_color", [60, 60, 65])
        input_border_radius = inputs_config.get("border_radius", 3)
        
        # Apply scrollbar styling using StyleManager
        if hasattr(self, 'criteria_scroll_area'):
            from app.views.style import StyleManager
            StyleManager.style_scroll_area(
                self.criteria_scroll_area,
                self.config,
                input_bg,
                input_border,
                input_border_radius
            )
            # Set palette on scroll area viewport to prevent macOS override
            viewport = self.criteria_scroll_area.viewport()
            if viewport:
                viewport_palette = viewport.palette()
                viewport_palette.setColor(viewport.backgroundRole(), QColor(*input_bg))
                viewport.setPalette(viewport_palette)
                viewport.setAutoFillBackground(True)
        
        # Apply button styling using StyleManager (uses unified config)
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {}).get("buttons", {})
        border_color = buttons_config.get("border_color", [60, 60, 65])
        bg_color_list = [self.bg_color.red(), self.bg_color.green(), self.bg_color.blue()]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        # Get all main dialog buttons (exclude remove buttons from CriteriaRowWidget)
        all_buttons = self.findChildren(QPushButton)
        # Filter out remove buttons (they're styled separately in CriteriaRowWidget with smaller padding)
        main_buttons = [btn for btn in all_buttons if btn.text() != "Remove"]
        
        StyleManager.style_buttons(
            main_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=self.button_width,
            min_height=self.button_height
        )
    
    def _on_search_clicked(self) -> None:
        """Handle search button click."""
        # Automatically close the last unclosed group if needed
        if self.criteria_rows and self.group_starts:
            # Find the last group start that doesn't have a corresponding end
            last_unclosed_start = None
            for start_idx in sorted(self.group_starts, reverse=True):
                # Check if this start has an end
                has_end = any(end_idx > start_idx for end_idx in self.group_ends)
                if not has_end:
                    last_unclosed_start = start_idx
                    break
            
            # If there's an unclosed group, close it at the last row
            if last_unclosed_start is not None:
                last_row_idx = len(self.criteria_rows) - 1
                if last_row_idx not in self.group_ends:
                    self.group_ends.append(last_row_idx)
                # Update visual indicators
                self.update_group_visuals()
        
        # Collect criteria from rows
        criteria: List[SearchCriteria] = []
        
        # Collect all criteria and mark group starts/ends
        for i, row in enumerate(self.criteria_rows):
            criterion = row.get_criterion()
            if criterion is None:
                continue
            
            # Check if this row is a group start
            if i in self.group_starts:
                criterion.is_group_start = True
                criterion.group_level = self.group_levels.get(i, 0)
            
            # Check if this row is a group end
            if i in self.group_ends:
                criterion.is_group_end = True
                # Find matching group start to get level
                for start_idx in sorted(self.group_starts, reverse=True):
                    if start_idx < i:
                        criterion.group_level = self.group_levels.get(start_idx, 0)
                        break
            
            criteria.append(criterion)
        
        # Determine scope
        scope = "active" if self.active_radio.isChecked() else "all"
        
        # Create search query
        self.search_query = SearchQuery(scope=scope, criteria=criteria)
        
        # Save to memory for next time
        SearchDialog._last_search_query = self.search_query
        
        self.accept()
    
    def get_search_query(self) -> Optional[SearchQuery]:
        """Get the search query.
        
        Returns:
            SearchQuery instance or None if dialog was cancelled.
        """
        return self.search_query
    
    def _restore_last_search(self) -> None:
        """Restore the last search query from memory."""
        if SearchDialog._last_search_query is None:
            return
        
        query = SearchDialog._last_search_query
        
        # Restore scope
        if query.scope == "active":
            self.active_radio.setChecked(True)
        else:
            self.all_radio.setChecked(True)
        
        # Clear existing criteria rows
        for row in self.criteria_rows[:]:
            self._remove_criterion_row(row)
        
        # Clear group tracking
        self.group_starts.clear()
        self.group_ends.clear()
        self.group_levels.clear()
        
        # Rebuild criteria rows from saved query
        for i, criterion in enumerate(query.criteria):
            # Add row (will be at index i)
            is_group_start = criterion.is_group_start
            self._add_criterion_row(is_group_start=is_group_start)
            
            # Restore group level if this is a group start
            if is_group_start:
                self.group_levels[i] = criterion.group_level
            
            # Set the criterion values
            row = self.criteria_rows[i]
            row.set_criterion(criterion)
            
            # Show logic connector for all rows except first
            if i > 0:
                row.logic_combo.setVisible(True)
            
            # Mark group end if needed
            if criterion.is_group_end:
                self.group_ends.append(i)
        
        # Update visual indicators
        self._update_group_indentation()


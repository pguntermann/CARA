"""Bulk operations dialog for database header-tag and PGN cleaning ops."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPalette,
    QShowEvent,
    QResizeEvent,
    QCloseEvent,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.controllers.bulk_operations_controller import (
    MODE_ADD_TAG,
    MODE_CLEAN,
    MODE_COPY,
    MODE_FIND_REPLACE,
    MODE_LABELS,
    MODE_OVERWRITE,
    MODE_REMOVE_TAGS,
    BulkOperation,
    BulkOperationsController,
    format_bulk_plan_issues,
    sanitize_tag_name,
    validate_bulk_operation,
    validate_bulk_operation_plan,
)
from app.utils.bulk_operation_plan import (
    normalize_plan_name,
    plan_operations_from_dicts,
    plan_operations_to_dicts,
)
from app.utils.bulk_regex_presets import (
    CUSTOM_PRESET_ID,
    find_preset_by_id,
    load_bulk_regex_presets,
    match_preset_id,
)
from app.models.database_model import DatabaseModel
from app.utils.bulk_operation_summary import (
    format_bulk_operation_counts,
    format_bulk_operation_summary_plain,
)
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.path_display_utils import truncate_path_for_display, truncate_text_middle
from app.utils.themed_icon import themed_icon_from_svg



class _OperationListRow(QFrame):
    """Clickable operations-list row that reports selection / activation."""

    selected = pyqtSignal(int)
    activated = pyqtSignal(int)

    def __init__(self, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._index = index
        self.setObjectName("operations_list_row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._index)
        super().mouseDoubleClickEvent(event)


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


class _PgnTagsChipPickerPopup(QFrame):
    """Popup that shows PGN header tag chips for multi-select."""

    def __init__(
        self,
        config: Dict[str, Any],
        available_tags: List[str],
        selected_tags: List[str],
        on_change: Callable[[List[str]], None],
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.config = config
        self._available_tags = list(available_tags or [])
        self._selected = list(selected_tags or [])
        self._on_change = on_change
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        except Exception:
            pass

        board_cfg = (self.config.get("ui", {}) or {}).get("panels", {}).get("main", {}).get("board", {})
        tags_cfg = board_cfg.get("game_tags_widget", {}) if isinstance(board_cfg, dict) else {}
        self.flow_spacing = int(tags_cfg.get("flow_spacing", 6))
        chip_cfg = tags_cfg.get("chip", {}) if isinstance(tags_cfg.get("chip", {}), dict) else {}
        self.chip_border_radius = int(chip_cfg.get("border_radius", 10))
        self.chip_padding = chip_cfg.get("padding", [2, 8])
        self.chip_min_height = int(chip_cfg.get("minimum_height", 22))
        self.chip_unmanaged_bg = chip_cfg.get("unmanaged_background_color", [95, 95, 100])
        self.chip_font_family = resolve_font_family(chip_cfg.get("font_family", "Helvetica Neue"))
        self.chip_font_size = int(scale_font_size(chip_cfg.get("font_size", 11)))
        self.chip_font_weight = str(chip_cfg.get("font_weight", "bold")).strip().lower()

        dlg_cfg = (self.config.get("ui", {}) or {}).get("dialogs", {}).get("bulk_operations", {})
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

        try:
            self.setAutoFillBackground(True)
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.Window, self._bg)
            self.setPalette(pal)
        except Exception:
            pass

        self.setObjectName("bulk_tags_chip_picker")
        self.setStyleSheet(
            "#bulk_tags_chip_picker {"
            f"  background-color: rgb({self._bg.red()},{self._bg.green()},{self._bg.blue()});"
            f"  border: 1px solid rgb({self._border.red()},{self._border.green()},{self._border.blue()});"
            "  border-radius: 6px;"
            "}"
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

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._root = QWidget()
        self._root.setAutoFillBackground(False)
        self._root.setStyleSheet("background: transparent; border: none;")
        root_layout = QVBoxLayout(self._root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self._wrap = _ChipWrapContainer(self.flow_spacing, self._root)
        self._wrap.setStyleSheet("background: transparent; border: none;")
        root_layout.addWidget(self._wrap)
        # Do not add a stretch: with setWidgetResizable(True), the scroll widget
        # must keep a minimum height larger than the viewport for the scrollbar.
        self._scroll.setWidget(self._root)
        layout.addWidget(self._scroll, 1)

        self.setFixedWidth(int(self._popup_width))
        try:
            m = self.layout().contentsMargins()
            # Leave room for the vertical scrollbar when content overflows.
            inner_w = max(1, int(self._popup_width - m.left() - m.right() - 14))
            self._root.setMinimumWidth(inner_w)
            self._wrap.setFixedWidth(inner_w)
        except Exception:
            pass

        try:
            from app.views.style import StyleManager

            StyleManager.style_scroll_area(
                self._scroll,
                self.config,
                [self._bg.red(), self._bg.green(), self._bg.blue()],
                [self._border.red(), self._border.green(), self._border.blue()],
                3,
                include_scroll_area_border=False,
            )
        except Exception:
            pass
        self._rebuild()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        def _reflow() -> None:
            try:
                m = self.layout().contentsMargins()
                bar_w = 14
                if self._scroll.verticalScrollBar().isVisible():
                    bar_w = max(bar_w, int(self._scroll.verticalScrollBar().sizeHint().width()))
                inner_w = max(1, int(self.width() - m.left() - m.right() - bar_w))
                self._wrap.setFixedWidth(inner_w)
                self._root.setMinimumWidth(inner_w)
            except Exception:
                pass
            self._sync_height()

        QTimer.singleShot(0, _reflow)

    def _sync_height(self, *, max_height: int | None = None) -> None:
        try:
            self._wrap._layout()
            self._root.adjustSize()
            self._wrap.adjustSize()
        except Exception:
            pass
        contents_h = int(max(1, self._wrap.minimumHeight()))
        try:
            self._wrap.setMinimumHeight(contents_h)
            self._root.setMinimumHeight(contents_h)
        except Exception:
            pass
        margins = self.layout().contentsMargins() if self.layout() else None
        mh = (int(margins.top()) + int(margins.bottom())) if margins else 20
        natural = int(contents_h + mh + int(self._extra_height))
        max_h = int(max_height) if max_height is not None else int(self._popup_max_height)
        if max_h > 0:
            self.setFixedHeight(max(1, min(max_h, natural)))
        else:
            self.setFixedHeight(max(1, natural))
        # Force a scrollbar when chips exceed the capped popup height. Minimum
        # height on the scroll widget prevents Qt from collapsing content.
        needs_scroll = natural > self.height()
        try:
            self._scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
                if needs_scroll
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            if needs_scroll:
                self._scroll.verticalScrollBar().setVisible(True)
        except Exception:
            pass

    def _rebuild(self) -> None:
        selected = {t.casefold() for t in self._selected}
        rgb = self.chip_unmanaged_bg if isinstance(self.chip_unmanaged_bg, list) else [95, 95, 100]

        def mk_chip(name: str) -> QPushButton:
            btn = QPushButton(name, self._root)
            btn.setCheckable(True)
            btn.setChecked(name.casefold() in selected)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_chip(btn, QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])))
            btn.toggled.connect(lambda checked, n=name: self._toggle(n, checked))
            return btn

        chips = [mk_chip(tag) for tag in self._available_tags]
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
        sel = self._selected_border_color if isinstance(self._selected_border_color, list) else [70, 90, 130]
        sel_w = max(1, int(self._selected_border_width))
        sel_css = f"rgba({int(sel[0])}, {int(sel[1])}, {int(sel[2])}, 255)"
        chip.setStyleSheet(
            "QPushButton {"
            f"  background-color: {bg}; color: {text};"
            f"  border-radius: {int(self.chip_border_radius)}px;"
            f"  padding: {pad_v}px {pad_h}px; border: 1px solid rgba(0,0,0,0);"
            "}"
            "QPushButton:hover { border: 1px solid rgba(255,255,255,0.30); }"
            f"QPushButton:checked {{ border: {sel_w}px solid {sel_css}; }}"
            f"QPushButton:checked:hover {{ border: {sel_w}px solid {sel_css}; }}"
        )


class _OperationEditorOverlay(QWidget):
    """Dimmed overlay with a spacious form for one operation."""

    saved = pyqtSignal(object)  # BulkOperation
    cancelled = pyqtSignal()

    def __init__(
        self,
        config: Dict[str, Any],
        available_tags: List[str],
        add_tag_options: List[str],
        removable_tags: List[str],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.available_tags = list(available_tags or [])
        self.add_tag_options = list(add_tag_options or [])
        self.removable_tags = list(removable_tags or [])
        self._selected_tags: List[str] = []
        self._tags_popup: Optional[_PgnTagsChipPickerPopup] = None
        self._edit_index: Optional[int] = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._load_config()
        self._setup_ui()
        self._apply_styling()

    def _load_config(self) -> None:
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_operations", {})
        overlay_cfg = dialog_config.get("overlay", {})
        self.overlay_dim = overlay_cfg.get("dim_color", [0, 0, 0, 150])
        self.card_bg = QColor(*overlay_cfg.get("card_background_color", dialog_config.get("background_color", [40, 40, 45])))
        self.card_border = QColor(*overlay_cfg.get("card_border_color", dialog_config.get("border_color", [60, 60, 65])))
        self.card_radius = int(overlay_cfg.get("card_border_radius", 8))
        self.card_width = int(overlay_cfg.get("card_width", 560))
        self.card_margins = overlay_cfg.get("card_margins", [28, 26, 28, 24])
        self.card_spacing = int(overlay_cfg.get("card_spacing", 20))
        self.form_vertical_spacing = int(overlay_cfg.get("form_vertical_spacing", 16))
        self.form_horizontal_spacing = int(overlay_cfg.get("form_horizontal_spacing", 16))
        self.mode_spacing = int(overlay_cfg.get("mode_spacing", 22))
        self.buttons_top_spacing = int(overlay_cfg.get("buttons_top_spacing", 8))
        self.label_min_width = int(overlay_cfg.get("label_min_width", 88))

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(labels_config.get("font_family", "Helvetica Neue"))
        self.label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))

        inputs_config = dialog_config.get("inputs", {})
        self.input_font_family = resolve_font_family(inputs_config.get("font_family", "Cascadia Mono"))
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = QColor(*inputs_config.get("text_color", [240, 240, 240]))
        self.input_bg_color = QColor(*inputs_config.get("background_color", [30, 30, 35]))
        self.input_border_color = QColor(*inputs_config.get("border_color", [60, 60, 65]))
        self.input_focus_border_color = QColor(*inputs_config.get("focus_border_color", [70, 90, 130]))
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])
        self.input_min_height = int(inputs_config.get("minimum_height", 30))

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 120))
        self.button_height = int(buttons_config.get("height", 30))
        self.button_spacing = int(buttons_config.get("spacing", 10))
        self.dialog_bg = dialog_config.get("background_color", [40, 40, 45])
        self.dialog_border = dialog_config.get("border_color", [60, 60, 65])

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("bulk_operations_editor_card")
        self.card.setFixedWidth(self.card_width)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(
            int(self.card_margins[0]),
            int(self.card_margins[1]),
            int(self.card_margins[2]),
            int(self.card_margins[3]),
        )
        card_layout.setSpacing(self.card_spacing)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(self.form_horizontal_spacing)
        self.mode_label = QLabel("Operation")
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(MODE_LABELS[MODE_FIND_REPLACE], MODE_FIND_REPLACE)
        self.mode_combo.addItem(MODE_LABELS[MODE_OVERWRITE], MODE_OVERWRITE)
        self.mode_combo.addItem(MODE_LABELS[MODE_COPY], MODE_COPY)
        self.mode_combo.insertSeparator(self.mode_combo.count())
        self.mode_combo.addItem(MODE_LABELS[MODE_ADD_TAG], MODE_ADD_TAG)
        self.mode_combo.addItem(MODE_LABELS[MODE_REMOVE_TAGS], MODE_REMOVE_TAGS)
        self.mode_combo.insertSeparator(self.mode_combo.count())
        self.mode_combo.addItem(MODE_LABELS[MODE_CLEAN], MODE_CLEAN)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._mode_row = self._make_field_row(self.mode_label, self.mode_combo)
        card_layout.addWidget(self._mode_row)

        # Field rows in a vertical stack (equal spacing; order rebuilt per mode so
        # hidden fields never sit between two visible ones).
        self._fields_host = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_host)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(self.form_vertical_spacing)
        self._fields_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.tags_label = QLabel("Tags")
        self.tags_picker_btn = QPushButton()
        self.tags_picker_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tags_picker_btn.clicked.connect(self._open_tags_picker)
        self._tags_row = self._make_field_row(self.tags_label, self.tags_picker_btn)

        self.tag_name_label = QLabel("Tag name")
        self.tag_name_combo = QComboBox()
        self.tag_name_combo.setEditable(True)
        self.tag_name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.tag_name_combo.addItems(self.add_tag_options)
        if self.tag_name_combo.lineEdit() is not None:
            self.tag_name_combo.lineEdit().setPlaceholderText("Select or type a new tag…")
            self.tag_name_combo.lineEdit().returnPressed.connect(self._on_save)
        self._tag_name_row = self._make_field_row(self.tag_name_label, self.tag_name_combo)

        self.value_source_label = QLabel("Fill from")
        self.value_source_combo = QComboBox()
        self.value_source_combo.addItem("Fixed value", "fixed")
        self.value_source_combo.addItem("Copy from tag", "copy")
        self.value_source_combo.currentIndexChanged.connect(self._on_value_source_changed)
        self._value_source_row = self._make_field_row(self.value_source_label, self.value_source_combo)

        self.source_label = QLabel("Source")
        self.source_combo = QComboBox()
        self._fill_source_combo(self.available_tags)
        self._source_row = self._make_field_row(self.source_label, self.source_combo)

        self.find_label = QLabel("Find")
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Text to find")
        self.find_input.returnPressed.connect(self._on_save)
        self.find_input.textEdited.connect(self._on_find_replace_edited)
        self._find_row = self._make_field_row(self.find_label, self.find_input)

        self.replace_label = QLabel("Replace")
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replacement text")
        self.replace_input.returnPressed.connect(self._on_save)
        self.replace_input.textEdited.connect(self._on_find_replace_edited)
        self._replace_row = self._make_field_row(self.replace_label, self.replace_input)

        self.preset_label = QLabel("Preset")
        self.preset_combo = QComboBox()
        self._regex_presets = load_bulk_regex_presets(self.config)
        for preset in self._regex_presets:
            self.preset_combo.addItem(preset.label, preset.id)
            tip = (preset.tooltip or "").strip()
            if tip:
                self.preset_combo.setItemData(
                    self.preset_combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole
                )
        self.preset_combo.currentIndexChanged.connect(self._on_regex_preset_changed)
        self._preset_row = self._make_field_row(self.preset_label, self.preset_combo)
        self._applying_regex_preset = False

        self.options_label = QLabel("Options")
        options_wrap = QWidget()
        options_layout = QHBoxLayout(options_wrap)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(22)
        self.case_check = QCheckBox("Case sensitive")
        self.regex_check = QCheckBox("Use regex")
        self.regex_check.toggled.connect(self._on_regex_toggled)
        options_layout.addWidget(self.case_check)
        options_layout.addWidget(self.regex_check)
        options_layout.addStretch(1)
        self._options_row = self._make_field_row(self.options_label, options_wrap)

        self.clean_label = QLabel("Remove")
        clean_wrap = QWidget()
        clean_layout = QVBoxLayout(clean_wrap)
        clean_layout.setContentsMargins(0, 0, 0, 0)
        clean_layout.setSpacing(6)
        clean_row1 = QHBoxLayout()
        clean_row1.setContentsMargins(0, 0, 0, 0)
        clean_row1.setSpacing(18)
        clean_row2 = QHBoxLayout()
        clean_row2.setContentsMargins(0, 0, 0, 0)
        clean_row2.setSpacing(18)
        self.clean_comments_check = QCheckBox("Comments")
        self.clean_variations_check = QCheckBox("Variations")
        self.clean_nonstd_check = QCheckBox("Non-standard tags")
        self.clean_annotations_check = QCheckBox("Annotations")
        clean_row1.addWidget(self.clean_comments_check)
        clean_row1.addWidget(self.clean_variations_check)
        clean_row1.addStretch(1)
        clean_row2.addWidget(self.clean_nonstd_check)
        clean_row2.addWidget(self.clean_annotations_check)
        clean_row2.addStretch(1)
        clean_layout.addLayout(clean_row1)
        clean_layout.addLayout(clean_row2)
        self._clean_row = self._make_field_row(
            self.clean_label, clean_wrap, fixed_height=self.input_min_height * 2 + 8
        )

        self._all_field_rows = [
            self._tags_row,
            self._tag_name_row,
            self._value_source_row,
            self._source_row,
            self._options_row,
            self._preset_row,
            self._find_row,
            self._replace_row,
            self._clean_row,
        ]
        card_layout.addWidget(self._fields_host)
        # Absorb space when fewer rows are shown so the card height stays fixed.
        card_layout.addStretch(1)

        if self.buttons_top_spacing > 0:
            card_layout.addSpacing(self.buttons_top_spacing)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(self.button_spacing)
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn = QPushButton("Add")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setDefault(False)
        self.save_btn.setAutoDefault(True)
        self.save_btn.setDefault(True)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.save_btn.clicked.connect(self._on_save)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        card_layout.addLayout(buttons)

        root.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)
        # Defer mode layout until after styling + fixed-height lock.

    def _make_field_row(
        self, label: QLabel, field: QWidget, fixed_height: Optional[int] = None
    ) -> QWidget:
        """One label+control row with a consistent control height."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(self.form_horizontal_spacing)
        label.setMinimumWidth(self.label_min_width)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(label, 0)
        row_layout.addWidget(field, 1)
        row.setFixedHeight(int(fixed_height) if fixed_height is not None else self.input_min_height)
        return row

    def _fill_source_combo(self, tags: List[str]) -> None:
        current = self.source_combo.currentText() if self.source_combo.count() else ""
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItems(tags)
        if current and self.source_combo.findText(current) >= 0:
            self.source_combo.setCurrentText(current)
        elif "Date" in tags:
            self.source_combo.setCurrentText("Date")
        elif tags:
            self.source_combo.setCurrentIndex(0)
        self.source_combo.blockSignals(False)

    def _relayout_field_rows(self) -> None:
        """Place only the active rows, in order, with uniform spacing."""
        mode = self._current_mode()
        ordered: List[QWidget] = []
        if mode in (MODE_FIND_REPLACE, MODE_OVERWRITE, MODE_COPY, MODE_REMOVE_TAGS):
            ordered.append(self._tags_row)
        if mode == MODE_ADD_TAG:
            ordered.append(self._tag_name_row)
            ordered.append(self._value_source_row)
            if self.value_source_combo.currentData() == "copy":
                ordered.append(self._source_row)
            else:
                ordered.append(self._replace_row)
        elif mode == MODE_COPY:
            ordered.append(self._source_row)
        elif mode == MODE_FIND_REPLACE:
            ordered.append(self._options_row)
            if self.regex_check.isChecked():
                ordered.append(self._preset_row)
            ordered.extend([self._find_row, self._replace_row])
        elif mode == MODE_OVERWRITE:
            ordered.append(self._replace_row)
        elif mode == MODE_CLEAN:
            ordered.append(self._clean_row)

        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(self._fields_host)

        ordered_set = set(ordered)
        for row in self._all_field_rows:
            if row not in ordered_set:
                row.hide()
        for row in ordered:
            row.show()
            self._fields_layout.addWidget(row)

    def paintEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtGui import QPainter

        painter = QPainter(self)
        dim = self.overlay_dim if isinstance(self.overlay_dim, list) else [0, 0, 0, 150]
        a = int(dim[3]) if len(dim) > 3 else 150
        painter.fillRect(self.rect(), QColor(int(dim[0]), int(dim[1]), int(dim[2]), a))
        super().paintEvent(event)

    def _current_mode(self) -> str:
        data = self.mode_combo.currentData()
        return str(data) if data else MODE_FIND_REPLACE

    def _set_mode(self, mode: str) -> None:
        idx = self.mode_combo.findData(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

    def _on_value_source_changed(self, *_args) -> None:
        if self._current_mode() != MODE_ADD_TAG:
            return
        if self.value_source_combo.currentData() == "fixed":
            self.replace_label.setText("Value")
            self.replace_input.setPlaceholderText("Value to set")
        self._relayout_field_rows()

    def _on_mode_changed(self, *_args) -> None:
        mode = self._current_mode()
        is_overwrite = mode == MODE_OVERWRITE
        is_find = mode == MODE_FIND_REPLACE
        is_add = mode == MODE_ADD_TAG
        is_copy = mode == MODE_COPY

        self.tags_label.setText("Tags")

        if is_overwrite or (is_add and self.value_source_combo.currentData() == "fixed"):
            self.replace_label.setText("Value")
            self.replace_input.setPlaceholderText("Value to set")
        else:
            self.replace_label.setText("Replace")
            self.replace_input.setPlaceholderText("Replacement text")

        if is_add or is_copy:
            self._fill_source_combo(self.available_tags)

        if mode == MODE_REMOVE_TAGS:
            removable = set(self.removable_tags)
            self._selected_tags = [t for t in self._selected_tags if t in removable]
            self._sync_tags_label()

        if not is_find:
            self.case_check.setChecked(False)
            self.regex_check.setChecked(False)
            self._reset_regex_preset_to_custom()

        self._update_find_replace_placeholders()
        self._relayout_field_rows()

    def _on_regex_toggled(self, checked: bool) -> None:
        if not checked:
            self._reset_regex_preset_to_custom()
        self._update_find_replace_placeholders()
        if self._current_mode() == MODE_FIND_REPLACE:
            self._relayout_field_rows()

    def _reset_regex_preset_to_custom(self) -> None:
        self._applying_regex_preset = True
        try:
            idx = self.preset_combo.findData(CUSTOM_PRESET_ID)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
            self.preset_combo.setToolTip(
                "Choose a starting pattern for common substring keep/extract tasks."
            )
        finally:
            self._applying_regex_preset = False

    def _on_regex_preset_changed(self, *_args) -> None:
        if self._applying_regex_preset:
            return
        preset_id = str(self.preset_combo.currentData() or CUSTOM_PRESET_ID)
        preset = find_preset_by_id(self._regex_presets, preset_id)
        tip = (preset.tooltip if preset else "") or (
            "Choose a starting pattern for common substring keep/extract tasks."
        )
        self.preset_combo.setToolTip(tip)
        if not preset or not preset.id:
            return
        self._applying_regex_preset = True
        try:
            if not self.regex_check.isChecked():
                self.regex_check.setChecked(True)
            self.find_input.setText(preset.find)
            self.replace_input.setText(preset.replace)
        finally:
            self._applying_regex_preset = False
        self.find_input.setFocus()
        if preset.id == "keep_capture" and "text to keep" in self.find_input.text():
            # Select the placeholder inside the capture group for quick editing.
            start = self.find_input.text().find("text to keep")
            if start >= 0:
                self.find_input.setSelection(start, len("text to keep"))

    def _on_find_replace_edited(self, *_args) -> None:
        if self._applying_regex_preset:
            return
        if self.preset_combo.currentData() == CUSTOM_PRESET_ID:
            return
        matched = match_preset_id(
            self._regex_presets, self.find_input.text(), self.replace_input.text()
        )
        if matched == self.preset_combo.currentData():
            return
        self._reset_regex_preset_to_custom()

    def _update_find_replace_placeholders(self) -> None:
        mode = self._current_mode()
        if mode == MODE_FIND_REPLACE and self.regex_check.isChecked():
            self.find_input.setPlaceholderText(r"e.g. (text to keep) or ^.*?(…).*")
            self.replace_input.setPlaceholderText(r"e.g. \1 for the first capture")
            return
        if mode == MODE_OVERWRITE or (
            mode == MODE_ADD_TAG and self.value_source_combo.currentData() == "fixed"
        ):
            self.replace_input.setPlaceholderText("Value to set")
            self.find_input.setPlaceholderText("Text to find")
            return
        self.find_input.setPlaceholderText("Text to find")
        self.replace_input.setPlaceholderText("Replacement text")

    def _tags_for_picker(self) -> List[str]:
        if self._current_mode() == MODE_REMOVE_TAGS:
            return list(self.removable_tags)
        return list(self.available_tags)

    def _sync_tags_label(self) -> None:
        if not self._selected_tags:
            self.tags_picker_btn.setText("Select tags…")
        elif len(self._selected_tags) <= 3:
            self.tags_picker_btn.setText(", ".join(self._selected_tags))
        else:
            self.tags_picker_btn.setText(f"{len(self._selected_tags)} tags selected")
        self.tags_picker_btn.setToolTip(
            ", ".join(self._selected_tags) if self._selected_tags else "Select tags"
        )

    def _open_tags_picker(self) -> None:
        if self._tags_popup is not None and self._tags_popup.isVisible():
            self._tags_popup.close()
            return

        def on_change(tags: List[str]) -> None:
            self._selected_tags = tags
            self._sync_tags_label()

        self._tags_popup = _PgnTagsChipPickerPopup(
            self.config,
            available_tags=self._tags_for_picker(),
            selected_tags=list(self._selected_tags),
            on_change=on_change,
            parent=self,
        )
        dlg_cfg = (self.config.get("ui", {}) or {}).get("dialogs", {}).get("bulk_operations", {})
        tag_picker_cfg = dlg_cfg.get("tag_picker", {}) if isinstance(dlg_cfg.get("tag_picker", {}), dict) else {}
        anchor_gap_y = int(tag_picker_cfg.get("popup_anchor_gap_y", 8))
        p = self.tags_picker_btn.mapToGlobal(QPoint(0, self.tags_picker_btn.height() + anchor_gap_y))
        self._tags_popup.move(p)
        self._tags_popup.show()

    def open_for_add(self) -> None:
        self._edit_index = None
        self.save_btn.setText("Add")
        self._set_mode(MODE_FIND_REPLACE)
        defaults = [t for t in ("White", "Black") if t in self.available_tags]
        self._selected_tags = defaults or (self.available_tags[:1] if self.available_tags else [])
        self._sync_tags_label()
        self.find_input.clear()
        self.replace_input.clear()
        self.case_check.setChecked(False)
        self.regex_check.setChecked(False)
        self._reset_regex_preset_to_custom()
        self.value_source_combo.setCurrentIndex(0)
        self.tag_name_combo.setCurrentIndex(-1)
        self.tag_name_combo.setEditText("")
        if self.tag_name_combo.lineEdit() is not None:
            self.tag_name_combo.lineEdit().setPlaceholderText("Select or type a new tag…")
        for check in (
            self.clean_comments_check,
            self.clean_variations_check,
            self.clean_nonstd_check,
            self.clean_annotations_check,
        ):
            check.setChecked(False)
        self._fill_source_combo(self.available_tags)
        self._on_mode_changed()
        self._show_overlay()
        self._focus_primary_field()

    def open_for_edit(self, index: int, operation: BulkOperation) -> None:
        self._edit_index = index
        self.save_btn.setText("Save")
        self._set_mode(operation.mode)
        self._selected_tags = list(operation.tags)
        self._sync_tags_label()
        self.find_input.setText(operation.find_text)
        self.replace_input.setText(operation.replace_text)
        self.case_check.setChecked(operation.case_sensitive)
        self.regex_check.setChecked(operation.use_regex)
        self._applying_regex_preset = True
        try:
            preset_id = (
                match_preset_id(
                    self._regex_presets, operation.find_text, operation.replace_text
                )
                if operation.use_regex
                else CUSTOM_PRESET_ID
            )
            idx = self.preset_combo.findData(preset_id)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
            preset = find_preset_by_id(self._regex_presets, preset_id)
            self.preset_combo.setToolTip(
                (preset.tooltip if preset and preset.tooltip else None)
                or "Choose a starting pattern for common substring keep/extract tasks."
            )
        finally:
            self._applying_regex_preset = False
        if operation.mode == MODE_ADD_TAG and operation.tags:
            self.tag_name_combo.setCurrentText(operation.tags[0])
            self.value_source_combo.setCurrentIndex(1 if operation.copy_value_from_source else 0)
        if operation.source_tag:
            self.source_combo.setCurrentText(operation.source_tag)
        self.clean_comments_check.setChecked(operation.remove_comments)
        self.clean_variations_check.setChecked(operation.remove_variations)
        self.clean_nonstd_check.setChecked(operation.remove_non_standard_tags)
        self.clean_annotations_check.setChecked(operation.remove_annotations)
        self._on_mode_changed()
        self._show_overlay()
        self._focus_primary_field()

    def _focus_primary_field(self) -> None:
        """Focus the first field the user should fill for the active mode."""
        mode = self._current_mode()
        if mode == MODE_FIND_REPLACE:
            target: QWidget = self.find_input
        elif mode == MODE_ADD_TAG:
            target = self.tag_name_combo
        elif mode == MODE_CLEAN:
            target = self.clean_comments_check
        elif mode in (MODE_COPY, MODE_REMOVE_TAGS):
            target = self.tags_picker_btn
        else:
            target = self.replace_input
        self.replace_input.clearFocus()
        self.find_input.clearFocus()
        QTimer.singleShot(0, target.setFocus)

    def _show_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.save_btn.setDefault(True)
        self.raise_()
        self.show()

    def _on_cancel(self) -> None:
        try:
            if self._tags_popup is not None:
                self._tags_popup.close()
        except Exception:
            pass
        self.save_btn.setDefault(False)
        self.hide()
        self.cancelled.emit()

    def _on_save(self) -> None:
        mode = self._current_mode()
        if mode == MODE_ADD_TAG:
            raw_name = self.tag_name_combo.currentText().strip()
            name = sanitize_tag_name(raw_name)
            copy_from = self.value_source_combo.currentData() == "copy"
            operation = BulkOperation(
                mode=mode,
                tags=(name,) if name else (),
                replace_text="" if copy_from else self.replace_input.text(),
                source_tag=self.source_combo.currentText().strip() if copy_from else "",
                copy_value_from_source=copy_from,
            )
        elif mode == MODE_CLEAN:
            operation = BulkOperation(
                mode=mode,
                remove_comments=self.clean_comments_check.isChecked(),
                remove_variations=self.clean_variations_check.isChecked(),
                remove_non_standard_tags=self.clean_nonstd_check.isChecked(),
                remove_annotations=self.clean_annotations_check.isChecked(),
            )
        elif mode == MODE_REMOVE_TAGS:
            operation = BulkOperation(mode=mode, tags=tuple(self._selected_tags))
        else:
            operation = BulkOperation(
                mode=mode,
                tags=tuple(self._selected_tags),
                find_text=self.find_input.text(),
                replace_text=self.replace_input.text(),
                case_sensitive=self.case_check.isChecked() if mode == MODE_FIND_REPLACE else False,
                use_regex=self.regex_check.isChecked() if mode == MODE_FIND_REPLACE else False,
                source_tag=self.source_combo.currentText().strip() if mode == MODE_COPY else "",
            )
        error = validate_bulk_operation(operation)
        if error:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", error, self.window())
            return
        try:
            if self._tags_popup is not None:
                self._tags_popup.close()
        except Exception:
            pass
        self.save_btn.setDefault(False)
        self.hide()
        self.saved.emit((self._edit_index, operation))

    def _apply_styling(self) -> None:
        from app.views.style import StyleManager

        self.card.setStyleSheet(
            f"#bulk_operations_editor_card {{"
            f"  background-color: rgb({self.card_bg.red()}, {self.card_bg.green()}, {self.card_bg.blue()});"
            f"  border: 1px solid rgb({self.card_border.red()}, {self.card_border.green()}, {self.card_border.blue()});"
            f"  border-radius: {self.card_radius}px;"
            f"}}"
        )

        label_style = (
            f"QLabel {{"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"background-color: transparent;"
            f"}}"
        )
        for label in (
            self.mode_label,
            self.tags_label,
            self.tag_name_label,
            self.value_source_label,
            self.source_label,
            self.find_label,
            self.replace_label,
            self.preset_label,
            self.options_label,
            self.clean_label,
        ):
            label.setStyleSheet(label_style)

        text_color = [self.input_text_color.red(), self.input_text_color.green(), self.input_text_color.blue()]
        bg = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        border = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_operations", {})
        inputs_config = dialog_config.get("inputs", {})
        selection_bg = inputs_config.get("selection_background_color", [70, 90, 130])
        selection_text = inputs_config.get("selection_text_color", [240, 240, 240])
        focus_border = inputs_config.get("focus_border_color", [0, 120, 212])
        padding = self.input_padding if isinstance(self.input_padding, list) and len(self.input_padding) == 2 else [8, 6]

        StyleManager.style_line_edits(
            [self.find_input, self.replace_input],
            self.config,
            font_family=self.input_font_family,
            font_size=self.input_font_size,
            bg_color=bg,
            padding=padding,
        )
        for edit in (self.find_input, self.replace_input):
            edit.setFixedHeight(self.input_min_height)

        StyleManager.style_comboboxes(
            [self.mode_combo, self.source_combo, self.value_source_combo, self.preset_combo],
            self.config,
            text_color,
            self.input_font_family,
            self.input_font_size,
            bg,
            border,
            focus_border,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=self.input_border_radius,
            padding=self.input_padding,
            editable=False,
        )
        StyleManager.style_comboboxes(
            [self.tag_name_combo],
            self.config,
            text_color,
            self.input_font_family,
            self.input_font_size,
            bg,
            border,
            focus_border,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=self.input_border_radius,
            padding=self.input_padding,
            editable=True,
        )
        if self.tag_name_combo.lineEdit() is not None:
            self.tag_name_combo.lineEdit().setPlaceholderText("Select or type a new tag…")
        for combo in (
            self.mode_combo,
            self.source_combo,
            self.tag_name_combo,
            self.value_source_combo,
            self.preset_combo,
        ):
            combo.setFixedHeight(self.input_min_height)

        # Tags control: match line-edit height/width; explicit padding so the label stays centered.
        focus = focus_border if isinstance(focus_border, list) and len(focus_border) >= 3 else [70, 90, 130]
        self.tags_picker_btn.setFlat(True)
        self.tags_picker_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tags_picker_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tags_picker_btn.setMinimumWidth(0)
        self.tags_picker_btn.setMaximumWidth(16777215)
        self.tags_picker_btn.setFixedHeight(self.input_min_height)
        self.tags_picker_btn.setStyleSheet(
            "QPushButton {"
            f"  background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});"
            f"  color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"  border: 1px solid rgb({border[0]}, {border[1]}, {border[2]});"
            f"  border-radius: {self.input_border_radius}px;"
            "  padding: 0px 8px;"
            "  margin: 0px;"
            f"  font-family: \"{self.label_font_family}\";"
            f"  font-size: {self.label_font_size}pt;"
            "  text-align: left;"
            "}"
            "QPushButton:hover {"
            f"  border: 1px solid rgb({focus[0]}, {focus[1]}, {focus[2]});"
            "}"
            "QPushButton:pressed {"
            f"  background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});"
            "}"
            "QPushButton:focus { outline: none; }"
        )

        StyleManager.style_buttons(
            [self.cancel_btn, self.save_btn],
            self.config,
            self.dialog_bg,
            self.dialog_border,
            min_width=self.button_width,
            min_height=self.button_height,
        )
        self.cancel_btn.setFixedHeight(self.button_height)
        self.save_btn.setFixedHeight(self.button_height)

        StyleManager.style_checkboxes(
            [
                self.case_check,
                self.regex_check,
                self.clean_comments_check,
                self.clean_variations_check,
                self.clean_nonstd_check,
                self.clean_annotations_check,
            ],
            self.config,
            [
                self.label_text_color.red(),
                self.label_text_color.green(),
                self.label_text_color.blue(),
            ],
            self.label_font_family,
            self.label_font_size,
            bg,
            border,
            Path(__file__).resolve().parents[2] / "resources" / "icons" / "checkmark.svg",
        )
        self._lock_card_height_to_full_form()
        self._on_mode_changed()
        QWidget.setTabOrder(self.mode_combo, self.tags_picker_btn)
        QWidget.setTabOrder(self.tags_picker_btn, self.case_check)
        QWidget.setTabOrder(self.case_check, self.regex_check)
        QWidget.setTabOrder(self.regex_check, self.preset_combo)
        QWidget.setTabOrder(self.preset_combo, self.find_input)
        QWidget.setTabOrder(self.find_input, self.replace_input)
        QWidget.setTabOrder(self.replace_input, self.cancel_btn)
        QWidget.setTabOrder(self.cancel_btn, self.save_btn)

    def _lock_card_height_to_full_form(self) -> None:
        """Pin card height to the tallest mode (Find / Replace) so mode switches don't resize."""
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(self._fields_host)
        for row in (
            self._tags_row,
            self._options_row,
            self._preset_row,
            self._find_row,
            self._replace_row,
        ):
            row.show()
            self._fields_layout.addWidget(row)
        for row in (
            self._tag_name_row,
            self._value_source_row,
            self._source_row,
            self._clean_row,
        ):
            row.hide()
        # Preset stays visible so the locked height includes the regex-on form.
        self.card.adjustSize()
        hint_h = int(self.card.sizeHint().height())
        if hint_h > 0:
            self.card.setFixedHeight(hint_h)


class _BusySpinner(QWidget):
    """Animated circular spinner for modal busy overlays."""

    def __init__(
        self,
        *,
        color: QColor,
        track_color: Optional[QColor] = None,
        size: int = 40,
        line_width: int = 3,
        span_degrees: int = 110,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._track_color = track_color
        self._line_width = max(2, int(line_width))
        self._span_degrees = max(60, min(270, int(span_degrees)))
        self._angle = 0
        side = max(24, int(size))
        self.setFixedSize(side, side)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtGui import QPainter, QPen
        from PyQt6.QtCore import QRectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = self._line_width / 2.0 + 1.0
        rect = QRectF(inset, inset, self.width() - 2 * inset, self.height() - 2 * inset)

        if self._track_color is not None:
            track_pen = QPen(self._track_color, float(self._line_width), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(track_pen)
            painter.drawEllipse(rect)

        pen = QPen(self._color, float(self._line_width), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, int((-self._angle) * 16), int(self._span_degrees) * 16)


class _ProgressOverlay(QWidget):
    """Dimmed overlay with a spinner while bulk operations run, then a compact summary."""

    cancel_requested = pyqtSignal()
    accept_requested = pyqtSignal()  # success → close dialog
    dismiss_requested = pyqtSignal()  # cancel/fail → return to form

    def __init__(self, config: Dict[str, Any], parent: QWidget) -> None:
        super().__init__(parent)
        self.config = config
        self._phase = "running"  # running | success | dismiss
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._load_config()
        self._setup_ui()
        self._apply_styling()

    def _load_config(self) -> None:
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_operations", {})
        overlay_cfg = dialog_config.get("overlay", {})
        progress_cfg = dialog_config.get("progress", {})

        self.overlay_dim = overlay_cfg.get("dim_color", [0, 0, 0, 150])
        self.card_bg = QColor(
            *overlay_cfg.get("card_background_color", dialog_config.get("background_color", [40, 40, 45]))
        )
        self.card_border = QColor(
            *overlay_cfg.get("card_border_color", dialog_config.get("border_color", [60, 60, 65]))
        )
        self.card_radius = int(overlay_cfg.get("card_border_radius", 8))
        self.card_width = int(progress_cfg.get("card_width", 360))
        self.card_margins = progress_cfg.get(
            "card_margins",
            overlay_cfg.get("card_margins", [28, 28, 28, 24]),
        )
        self.card_spacing = int(progress_cfg.get("card_spacing", 16))
        self.buttons_top_spacing = int(
            progress_cfg.get("buttons_top_spacing", overlay_cfg.get("buttons_top_spacing", 8))
        )

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(labels_config.get("font_family", "Helvetica Neue"))
        self.label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        self.title_font_size = int(
            scale_font_size(progress_cfg.get("title_font_size", labels_config.get("font_size", 11)))
        )
        # Summary uses the same body label size/color as the rest of the dialog.
        self.summary_font_size = int(
            scale_font_size(progress_cfg.get("summary_font_size", labels_config.get("font_size", 11)))
        )
        self.summary_text_color = QColor(
            *progress_cfg.get(
                "summary_text_color",
                [
                    self.label_text_color.red(),
                    self.label_text_color.green(),
                    self.label_text_color.blue(),
                ],
            )
        )

        spinner_color = progress_cfg.get(
            "spinner_color",
            dialog_config.get("operations_list", {}).get("selected_background_color", [70, 90, 130]),
        )
        track = progress_cfg.get("spinner_track_color")
        self.spinner_color = QColor(*spinner_color)
        self.spinner_track_color = QColor(*track) if isinstance(track, list) and len(track) >= 3 else None
        self.spinner_size = int(progress_cfg.get("spinner_size", 40))
        self.spinner_line_width = int(progress_cfg.get("spinner_line_width", 3))
        self.spinner_span_degrees = int(progress_cfg.get("spinner_span_degrees", 110))

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 120))
        self.button_height = int(buttons_config.get("height", 30))
        self.dialog_bg = dialog_config.get("background_color", [40, 40, 45])
        self.dialog_border = dialog_config.get("border_color", [60, 60, 65])

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("bulk_operations_progress_card")
        self.card.setFixedWidth(self.card_width)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(
            int(self.card_margins[0]),
            int(self.card_margins[1]),
            int(self.card_margins[2]),
            int(self.card_margins[3]),
        )
        card_layout.setSpacing(self.card_spacing)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.spinner = _BusySpinner(
            color=self.spinner_color,
            track_color=self.spinner_track_color,
            size=self.spinner_size,
            line_width=self.spinner_line_width,
            span_degrees=self.spinner_span_degrees,
        )
        spinner_row = QHBoxLayout()
        spinner_row.setContentsMargins(0, 0, 0, 0)
        spinner_row.addStretch(1)
        spinner_row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)
        spinner_row.addStretch(1)
        card_layout.addLayout(spinner_row)

        self.title_label = QLabel("Running operations…")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(self.title_label)

        self.step_label = QLabel("")
        self.step_label.setWordWrap(True)
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.step_label.hide()
        card_layout.addWidget(self.step_label)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.summary_label.hide()
        card_layout.addWidget(self.summary_label)

        if self.buttons_top_spacing > 0:
            card_layout.addSpacing(self.buttons_top_spacing)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        self.action_button = QPushButton("Cancel")
        self.action_button.setAutoDefault(False)
        self.action_button.setDefault(False)
        self.action_button.clicked.connect(self._on_action_clicked)
        buttons.addWidget(self.action_button)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)

        root.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtGui import QPainter

        painter = QPainter(self)
        dim = self.overlay_dim if isinstance(self.overlay_dim, list) else [0, 0, 0, 150]
        a = int(dim[3]) if len(dim) > 3 else 150
        painter.fillRect(self.rect(), QColor(int(dim[0]), int(dim[1]), int(dim[2]), a))
        super().paintEvent(event)

    def _apply_styling(self) -> None:
        from app.views.style import StyleManager

        self.card.setStyleSheet(
            f"#bulk_operations_progress_card {{"
            f"  background-color: rgb({self.card_bg.red()}, {self.card_bg.green()}, {self.card_bg.blue()});"
            f"  border: 1px solid rgb({self.card_border.red()}, {self.card_border.green()}, {self.card_border.blue()});"
            f"  border-radius: {self.card_radius}px;"
            f"}}"
        )

        title_style = (
            f"QLabel {{ color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()}); "
            f"font-family: {self.label_font_family}; font-size: {self.title_font_size}pt; font-weight: 600; "
            f"background: transparent; }}"
        )
        summary_style = (
            f"QLabel {{ color: rgb({self.summary_text_color.red()}, {self.summary_text_color.green()}, {self.summary_text_color.blue()}); "
            f"font-family: {self.label_font_family}; font-size: {self.summary_font_size}pt; background: transparent; }}"
        )
        self.title_label.setStyleSheet(title_style)
        self.step_label.setStyleSheet(summary_style)
        self.summary_label.setStyleSheet(summary_style)

        StyleManager.style_buttons(
            [self.action_button],
            self.config,
            self.dialog_bg,
            self.dialog_border,
            min_width=self.button_width,
            min_height=self.button_height,
        )
        self.action_button.setFixedHeight(self.button_height)

    def open_running(self) -> None:
        self._phase = "running"
        self.title_label.setText("Running operations…")
        self.set_step("")
        self.set_live_stats(0, 0, 0, 0)
        self.spinner.start()
        self.spinner.show()
        self.action_button.setText("Cancel")
        self.action_button.setEnabled(True)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self.show()

    def set_status(self, message: str) -> None:
        """Optional title update while running (e.g. Cancelling…)."""
        if self._phase == "running" and message:
            self.title_label.setText(message)

    def set_step(self, step_text: str) -> None:
        """Show the active plan step under the title."""
        text = (step_text or "").strip()
        if text:
            self.step_label.setText(text)
            self.step_label.show()
        else:
            self.step_label.clear()
            self.step_label.hide()

    def set_live_stats(
        self,
        games_processed: int,
        games_updated: int,
        games_failed: int,
        games_skipped: int,
    ) -> None:
        """Update running counters shown under the spinner."""
        self.summary_label.setText(
            format_bulk_operation_counts(
                games_processed,
                games_updated,
                games_failed,
                games_skipped,
            )
        )
        self.summary_label.show()

    def show_complete(self, summary: str) -> None:
        self._phase = "success"
        self.spinner.stop()
        self.spinner.hide()
        self.title_label.setText("Complete")
        self.step_label.hide()
        self.step_label.clear()
        self.summary_label.setText(summary)
        self.summary_label.show()
        self.action_button.setText("Close")
        self.action_button.setEnabled(True)
        self.card.adjustSize()

    def show_cancelled(self) -> None:
        self._phase = "dismiss"
        self.spinner.stop()
        self.spinner.hide()
        self.title_label.setText("Cancelled")
        # Keep step + live counts for context.
        self.summary_label.show()
        self.action_button.setText("Close")
        self.action_button.setEnabled(True)

    def show_failed(self, message: str) -> None:
        self._phase = "dismiss"
        self.spinner.stop()
        self.spinner.hide()
        self.title_label.setText("Failed")
        if not self.summary_label.text().strip():
            self.summary_label.setText(message or "Operation failed")
        self.summary_label.show()
        self.action_button.setText("Close")
        self.action_button.setEnabled(True)

    def _on_action_clicked(self) -> None:
        if self._phase == "success":
            self.spinner.stop()
            self.hide()
            self.accept_requested.emit()
            return
        if self._phase == "dismiss":
            self.spinner.stop()
            self.hide()
            self.dismiss_requested.emit()
            return
        self.action_button.setEnabled(False)
        self.title_label.setText("Cancelling…")
        self.cancel_requested.emit()


class _BulkOperationsWorker(QThread):
    """Runs bulk execute off the UI thread so ProcessPool + Qt stay stable."""

    finished_with_result = pyqtSignal(object)
    failed_with_error = pyqtSignal(str)

    def __init__(
        self,
        controller: BulkOperationsController,
        database: DatabaseModel,
        operations: List[BulkOperation],
        has_result: bool,
        has_eco: bool,
        game_indices: Optional[List[int]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._database = database
        self._operations = operations
        self._has_result = has_result
        self._has_eco = has_eco
        self._game_indices = game_indices

    def run(self) -> None:  # noqa: N802
        try:
            result = self._controller.execute_bulk_operations(
                self._database,
                self._operations,
                self._has_result,
                self._has_eco,
                self._game_indices,
            )
            self.finished_with_result.emit(result)
        except Exception as exc:
            self.failed_with_error.emit(str(exc))


class BulkOperationsDialog(QDialog):
    """Dialog for bulk header-tag and PGN cleaning operations on databases."""

    @dataclass(frozen=True)
    class _RememberedState:
        operations: Tuple[BulkOperation, ...]
        update_result: bool
        update_eco: bool
        selected_games_scope: bool

    _last_state: Optional["BulkOperationsDialog._RememberedState"] = None

    def __init__(
        self,
        config: Dict[str, Any],
        bulk_operations_controller: BulkOperationsController,
        database: Optional[DatabaseModel],
        selected_game_indices: Optional[List[int]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.controller = bulk_operations_controller
        self.database = database
        self.selected_game_indices = selected_game_indices if selected_game_indices else []
        self._pending_operations: List[BulkOperation] = []
        self._row_widgets: List[_OperationListRow] = []
        self._selected_operation_index: Optional[int] = None
        self._operation_in_progress = False
        self._worker: Optional[_BulkOperationsWorker] = None

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self._apply_configured_dialog_size()
        self.setWindowTitle("Bulk Operations")
        self._restore_last_state()

    def _load_config(self) -> None:
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_operations", {})
        self.dialog_width = int(dialog_config.get("width", 640))
        self.scroll_area_height = int(dialog_config.get("scroll_area_height", 160))
        self.bg_color = QColor(*dialog_config.get("background_color", [40, 40, 45]))
        self.text_color = QColor(*dialog_config.get("text_color", [200, 200, 200]))
        self.layout_margins = dialog_config.get("layout", {}).get("margins", [25, 25, 25, 25])
        spacing_config = dialog_config.get("spacing", {})
        self.section_spacing = int(spacing_config.get("section", 14))
        self.result_spacing = int(spacing_config.get("result", 8))
        self.bottom_button_top_padding = int(dialog_config.get("bottom_button_top_padding", 28))

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 120))
        self.button_height = int(buttons_config.get("height", 30))
        self.button_spacing = int(buttons_config.get("spacing", 10))
        self.add_button_icon_svg = str(
            buttons_config.get("add_button_icon_svg", "app/resources/icons/menu_plus.svg")
        )
        self.edit_button_icon_svg = str(
            buttons_config.get("edit_button_icon_svg", "app/resources/icons/pencil.svg")
        )
        self.remove_button_icon_svg = str(
            buttons_config.get("remove_button_icon_svg", "app/resources/icons/menu_trash.svg")
        )
        self.add_button_tooltip = str(buttons_config.get("add_button_tooltip", "Add operation"))
        self.edit_button_tooltip = str(buttons_config.get("edit_button_tooltip", "Edit selected operation"))
        self.remove_button_tooltip = str(
            buttons_config.get("remove_button_tooltip", "Remove selected operation")
        )
        self.clear_button_icon_svg = str(
            buttons_config.get("clear_button_icon_svg", "app/resources/icons/menu_reset.svg")
        )
        self.clear_button_tooltip = str(
            buttons_config.get("clear_button_tooltip", "Clear all operations")
        )
        self.save_button_icon_svg = str(
            buttons_config.get("save_button_icon_svg", "app/resources/icons/save_database.svg")
        )
        self.save_button_tooltip = str(
            buttons_config.get("save_button_tooltip", "Save operations as a named plan")
        )
        self.load_button_icon_svg = str(
            buttons_config.get("load_button_icon_svg", "app/resources/icons/folder_open.svg")
        )
        self.load_button_tooltip = str(
            buttons_config.get("load_button_tooltip", "Load or delete a saved plan")
        )
        self.toolbar_separator_width = int(buttons_config.get("toolbar_separator_width", 1))
        sep_m = buttons_config.get("toolbar_separator_margin", [6, 4, 6, 4])
        self.toolbar_separator_margin = (
            [int(sep_m[0]), int(sep_m[1]), int(sep_m[2]), int(sep_m[3])]
            if isinstance(sep_m, list) and len(sep_m) >= 4
            else [6, 4, 6, 4]
        )
        self.toolbar_icon_px = int(buttons_config.get("remove_button_icon_px", 18))

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(labels_config.get("font_family", "Helvetica Neue"))
        self.label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        self.label_note_font_size = int(scale_font_size(labels_config.get("note_font_size", 10)))
        tint_cfg = buttons_config.get(
            "remove_button_icon_tint_rgb",
            labels_config.get("text_color", [200, 200, 200]),
        )
        self.toolbar_icon_tint = (
            (int(tint_cfg[0]), int(tint_cfg[1]), int(tint_cfg[2]))
            if isinstance(tint_cfg, list) and len(tint_cfg) >= 3
            else (200, 200, 200)
        )

        inputs_config = dialog_config.get("inputs", {})
        self.input_bg_color = QColor(*inputs_config.get("background_color", [30, 30, 35]))
        self.input_border_color = QColor(*inputs_config.get("border_color", [60, 60, 65]))
        self.input_border_radius = inputs_config.get("border_radius", 3)

        list_cfg = dialog_config.get("operations_list", {})
        self.list_empty_text = str(list_cfg.get("empty_text", "No operations yet"))
        self.list_row_min_height = int(list_cfg.get("row_min_height", 34))
        self.list_spacing = int(list_cfg.get("spacing", 4))
        self.list_margins = list_cfg.get("margins", [8, 8, 8, 8])
        self.list_selected_bg = QColor(
            *list_cfg.get("selected_background_color", [70, 90, 130])
        )
        self.list_selected_radius = int(list_cfg.get("selected_border_radius", 4))
        self.list_row_padding = list_cfg.get("row_padding", [8, 4, 8, 4])

    def _get_available_tags(self) -> List[str]:
        return self.controller.get_available_tags(self.database)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3],
        )

        # Target Database
        db_container = QWidget()
        db_container_layout = QVBoxLayout(db_container)
        db_container_layout.setContentsMargins(0, 0, 0, 0)
        db_container_layout.setSpacing(2)

        db_header = QHBoxLayout()
        db_header.setContentsMargins(0, 0, 0, 0)
        db_header.setSpacing(8)
        self._target_db_label = QLabel("Target Database:")
        self._target_db_label.setFont(QFont(self.label_font_family, self.label_font_size))
        db_header.addWidget(self._target_db_label)

        db_name = "Clipboard"
        db_path = None
        if self.database:
            panel_model = self.controller.database_controller.get_panel_model()
            identifier = panel_model.find_database_by_model(self.database)
            if identifier and identifier != "clipboard":
                db_path = identifier
                db_name = Path(identifier).stem

        self.db_name_label = QLabel(f"<b>{db_name}</b>")
        self.db_name_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.db_name_label.setWordWrap(False)
        db_header.addWidget(self.db_name_label)
        db_header.addStretch()
        db_container_layout.addLayout(db_header)

        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        label_width = self._target_db_label.fontMetrics().horizontalAdvance("Target Database:")
        spacer = QWidget()
        spacer.setFixedWidth(label_width + 8)
        path_layout.addWidget(spacer)
        path_font = QFont(self.label_font_family, max(8, self.label_font_size - 2))
        path_h = QFontMetrics(path_font).lineSpacing()
        if db_path:
            self._db_path_full = db_path
            self._db_name_full = db_name
            self.db_path_label = QLabel(
                truncate_path_for_display(
                    db_path,
                    max(80, self.dialog_width - self.layout_margins[0] - self.layout_margins[2] - label_width - 16),
                    path_font,
                )
            )
            self.db_path_label.setToolTip(db_path)
            self.db_path_label.setStyleSheet(
                f"color: rgb({self.text_color.red()}, {self.text_color.green()}, {self.text_color.blue()});"
            )
        else:
            self._db_path_full = None
            self._db_name_full = None
            self.db_path_label = QLabel("")
        self.db_path_label.setFont(path_font)
        self.db_path_label.setFixedHeight(path_h)
        path_layout.addWidget(self.db_path_label)
        path_layout.addStretch()
        path_widget = QWidget()
        path_widget.setLayout(path_layout)
        path_widget.setFixedHeight(path_h)
        db_container_layout.addWidget(path_widget)
        main_layout.addWidget(db_container)
        main_layout.addSpacing(self.section_spacing)

        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_operations", {})
        groups_config = dialog_config.get("groups", {})
        # Tighter content margins for compact groups
        content_margins = groups_config.get("content_margins", [12, 14, 12, 12])

        games_group = QGroupBox("Target Games")
        games_layout = QHBoxLayout()
        games_layout.setContentsMargins(
            content_margins[0], content_margins[1], content_margins[2], content_margins[3]
        )
        games_layout.setSpacing(18)
        self.all_games_radio = QRadioButton("All games")
        self.selected_games_radio = QRadioButton("Selected games")
        group = QButtonGroup(self)
        group.addButton(self.all_games_radio)
        group.addButton(self.selected_games_radio)
        if self.selected_game_indices:
            self.selected_games_radio.setChecked(True)
        else:
            self.all_games_radio.setChecked(True)
        games_layout.addWidget(self.all_games_radio)
        games_layout.addWidget(self.selected_games_radio)
        games_layout.addStretch()
        games_group.setLayout(games_layout)
        main_layout.addWidget(games_group)
        main_layout.addSpacing(self.section_spacing)

        operations_group = QGroupBox("Operations")
        operations_layout = QVBoxLayout()
        operations_layout.setContentsMargins(
            content_margins[0], content_margins[1], content_margins[2], content_margins[3]
        )
        operations_layout.setSpacing(10)

        self.operations_scroll = QScrollArea()
        self.operations_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.operations_scroll.setFixedHeight(self.scroll_area_height)
        self.operations_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.operations_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.operations_scroll.setWidgetResizable(True)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(
            int(self.list_margins[0]),
            int(self.list_margins[1]),
            int(self.list_margins[2]),
            int(self.list_margins[3]),
        )
        self._list_layout.setSpacing(self.list_spacing)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._empty_label = QLabel(self.list_empty_text)
        self._empty_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self._list_layout.addWidget(self._empty_label)
        self._list_layout.addStretch(1)
        self.operations_scroll.setWidget(self._list_widget)
        operations_layout.addWidget(self.operations_scroll)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        self.add_operation_button = QPushButton()
        self.add_operation_button.setObjectName("operations_toolbar_add")
        self.add_operation_button.setToolTip(self.add_button_tooltip)
        self.add_operation_button.setAccessibleName("Add operation")
        self.add_operation_button.clicked.connect(self._on_add_clicked)

        self.edit_operation_button = QPushButton()
        self.edit_operation_button.setObjectName("operations_toolbar_edit")
        self.edit_operation_button.setToolTip(self.edit_button_tooltip)
        self.edit_operation_button.setAccessibleName("Edit selected operation")
        self.edit_operation_button.clicked.connect(self._on_edit_selected_clicked)

        self.remove_operation_button = QPushButton()
        self.remove_operation_button.setObjectName("operations_toolbar_remove")
        self.remove_operation_button.setToolTip(self.remove_button_tooltip)
        self.remove_operation_button.setAccessibleName("Remove selected operation")
        self.remove_operation_button.clicked.connect(self._on_remove_selected_clicked)

        self.clear_operations_button = QPushButton()
        self.clear_operations_button.setObjectName("operations_toolbar_clear")
        self.clear_operations_button.setToolTip(self.clear_button_tooltip)
        self.clear_operations_button.setAccessibleName("Clear all operations")
        self.clear_operations_button.clicked.connect(self._on_clear_all_clicked)

        self.save_plan_button = QPushButton()
        self.save_plan_button.setObjectName("operations_toolbar_save")
        self.save_plan_button.setToolTip(self.save_button_tooltip)
        self.save_plan_button.setAccessibleName("Save operations plan")
        self.save_plan_button.clicked.connect(self._on_save_plan_clicked)

        self.load_plan_button = QPushButton()
        self.load_plan_button.setObjectName("operations_toolbar_load")
        self.load_plan_button.setToolTip(self.load_button_tooltip)
        self.load_plan_button.setAccessibleName("Load operations plan")
        self.load_plan_button.clicked.connect(self._on_load_plan_clicked)

        for btn in (
            self.add_operation_button,
            self.edit_operation_button,
            self.remove_operation_button,
            self.clear_operations_button,
            self.save_plan_button,
            self.load_plan_button,
        ):
            btn.setAutoDefault(False)
            btn.setDefault(False)

        toolbar.addWidget(self.add_operation_button)
        toolbar.addWidget(self.edit_operation_button)
        toolbar.addWidget(self.remove_operation_button)

        self._toolbar_separator = self._make_toolbar_separator("operations_toolbar_separator")
        m = self.toolbar_separator_margin
        toolbar.addSpacing(max(0, m[0]))
        toolbar.addWidget(self._toolbar_separator)
        toolbar.addSpacing(max(0, m[2]))

        toolbar.addWidget(self.clear_operations_button)
        toolbar.addStretch(1)

        self._toolbar_plans_separator = self._make_toolbar_separator(
            "operations_toolbar_plans_separator"
        )
        toolbar.addSpacing(max(0, m[0]))
        toolbar.addWidget(self._toolbar_plans_separator)
        toolbar.addSpacing(max(0, m[2]))
        toolbar.addWidget(self.save_plan_button)
        toolbar.addWidget(self.load_plan_button)
        operations_layout.addLayout(toolbar)
        operations_group.setLayout(operations_layout)
        main_layout.addWidget(operations_group)
        main_layout.addSpacing(self.section_spacing)

        smart_group = QGroupBox("Smart Update")
        smart_layout = QVBoxLayout()
        smart_layout.setContentsMargins(
            content_margins[0], content_margins[1], content_margins[2], content_margins[3]
        )
        smart_layout.setSpacing(self.result_spacing)
        self.update_result_check = QCheckBox("Update Result based on last move evaluation")
        self.update_eco_check = QCheckBox("Update ECO code with played opening ECO")
        smart_layout.addWidget(self.update_result_check)
        smart_layout.addWidget(self.update_eco_check)
        smart_group.setLayout(smart_layout)
        main_layout.addWidget(smart_group)

        buttons = QHBoxLayout()
        buttons.setSpacing(self.button_spacing)
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.apply_button = QPushButton("Apply")
        for btn in (self.cancel_button, self.apply_button):
            btn.setAutoDefault(False)
            btn.setDefault(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.apply_button.clicked.connect(self._on_apply_clicked)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        main_layout.addSpacing(self.bottom_button_top_padding)
        main_layout.addLayout(buttons)

        self._available_tags = self._get_available_tags()
        self._editor = _OperationEditorOverlay(
            self.config,
            self._available_tags,
            self.controller.get_add_tag_options(),
            self.controller.get_removable_tags(self.database),
            self,
        )
        self._editor.saved.connect(self._on_editor_saved)

        self._progress_overlay = _ProgressOverlay(self.config, self)
        self._progress_overlay.cancel_requested.connect(self._on_progress_cancel_requested)
        self._progress_overlay.accept_requested.connect(self._on_progress_accepted)
        self._progress_overlay.dismiss_requested.connect(self._on_progress_dismissed)
        self.controller.progress_updated.connect(self._on_progress_updated)

    def _make_toolbar_separator(self, object_name: str) -> QFrame:
        sep = QFrame()
        sep.setObjectName(object_name)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setLineWidth(1)
        sep.setFixedWidth(max(1, self.toolbar_separator_width))
        sep.setContentsMargins(0, 0, 0, 0)
        return sep

    def _rebuild_operations_list(self) -> None:
        previous_selection = self._selected_operation_index
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # Detach immediately — deleteLater alone leaves the old empty
                # label painted under restored rows until the event loop runs.
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._row_widgets = []
        self._empty_label = None

        label_style = (
            f"QLabel {{ color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()}); "
            f"font-family: {self.label_font_family}; font-size: {self.label_font_size}pt; background: transparent; }}"
        )

        if not self._pending_operations:
            self._selected_operation_index = None
            self._empty_label = QLabel(self.list_empty_text)
            self._empty_label.setFont(QFont(self.label_font_family, self.label_font_size))
            self._empty_label.setStyleSheet(label_style)
            self._list_layout.addWidget(self._empty_label)
            self._list_layout.addStretch(1)
            self._update_toolbar_enabled()
            return

        pad = self.list_row_padding
        for index, operation in enumerate(self._pending_operations):
            row = _OperationListRow(index)
            row.setMinimumHeight(self.list_row_min_height)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(int(pad[0]), int(pad[1]), int(pad[2]), int(pad[3]))
            row_layout.setSpacing(0)

            summary = operation.summary()
            summary_label = QLabel(summary)
            summary_label.setObjectName("operations_summary_label")
            summary_label.setProperty("full_summary", summary)
            summary_label.setToolTip(summary)
            summary_label.setWordWrap(False)
            summary_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            summary_label.setStyleSheet(label_style)
            row_layout.addWidget(summary_label, 1)

            row.selected.connect(self._on_operation_selected)
            row.activated.connect(self._on_edit_clicked)
            self._list_layout.addWidget(row)
            self._row_widgets.append(row)

        self._list_layout.addStretch(1)

        if previous_selection is not None and 0 <= previous_selection < len(self._pending_operations):
            self._selected_operation_index = previous_selection
        elif self._pending_operations:
            self._selected_operation_index = len(self._pending_operations) - 1
        else:
            self._selected_operation_index = None

        self._apply_row_selection_styles()
        self._update_summary_elision()
        self._update_toolbar_enabled()

    def _apply_row_selection_styles(self) -> None:
        sel = self._selected_operation_index
        for index, row in enumerate(self._row_widgets):
            if index == sel:
                row.setStyleSheet(
                    f"QFrame#operations_list_row {{"
                    f" background-color: rgb({self.list_selected_bg.red()}, {self.list_selected_bg.green()}, {self.list_selected_bg.blue()});"
                    f" border-radius: {self.list_selected_radius}px; }}"
                )
            else:
                row.setStyleSheet("QFrame#operations_list_row { background-color: transparent; }")

    def _update_toolbar_enabled(self) -> None:
        busy = self._operation_in_progress
        has_selection = (
            self._selected_operation_index is not None
            and 0 <= int(self._selected_operation_index) < len(self._pending_operations)
        )
        self.add_operation_button.setEnabled(not busy)
        self.edit_operation_button.setEnabled(not busy and has_selection)
        self.remove_operation_button.setEnabled(not busy and has_selection)
        self.clear_operations_button.setEnabled(
            not busy and bool(self._pending_operations)
        )
        self.save_plan_button.setEnabled(not busy and bool(self._pending_operations))
        self.load_plan_button.setEnabled(not busy)

    def _update_summary_elision(self) -> None:
        viewport_w = self.operations_scroll.viewport().width()
        if viewport_w <= 80:
            return
        elide_w = max(40, viewport_w - 24)
        for label in self._list_widget.findChildren(QLabel, "operations_summary_label"):
            full = label.property("full_summary")
            if full:
                label.setText(truncate_text_middle(str(full), elide_w, label.font()))

    def _on_operation_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._pending_operations):
            return
        self._selected_operation_index = index
        self._apply_row_selection_styles()
        self._update_toolbar_enabled()

    def _on_add_clicked(self) -> None:
        self._editor.open_for_add()

    def _on_edit_selected_clicked(self) -> None:
        if self._selected_operation_index is not None:
            self._on_edit_clicked(int(self._selected_operation_index))

    def _on_remove_selected_clicked(self) -> None:
        if self._selected_operation_index is not None:
            self._on_remove_clicked(int(self._selected_operation_index))

    def _on_edit_clicked(self, index: int) -> None:
        if 0 <= index < len(self._pending_operations):
            self._selected_operation_index = index
            self._apply_row_selection_styles()
            self._update_toolbar_enabled()
            self._editor.open_for_edit(index, self._pending_operations[index])

    def _on_remove_clicked(self, index: int) -> None:
        if 0 <= index < len(self._pending_operations):
            del self._pending_operations[index]
            if not self._pending_operations:
                self._selected_operation_index = None
            elif index >= len(self._pending_operations):
                self._selected_operation_index = len(self._pending_operations) - 1
            else:
                self._selected_operation_index = index
            self._rebuild_operations_list()
            self._apply_configured_dialog_size()

    def _on_clear_all_clicked(self) -> None:
        """Clear the operations list only (Smart Update / scope unchanged)."""
        if not self._pending_operations or self._operation_in_progress:
            return
        self._pending_operations.clear()
        self._selected_operation_index = None
        self._rebuild_operations_list()
        self._update_toolbar_enabled()
        self._apply_configured_dialog_size()

    def _on_save_plan_clicked(self) -> None:
        """Prompt for a name and store the current operations list in user settings."""
        if self._operation_in_progress or not self._pending_operations:
            return
        from app.services.user_settings_service import UserSettingsService
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog
        from app.views.dialogs.input_dialog import InputDialog
        from app.views.dialogs.message_dialog import MessageDialog

        name, ok = InputDialog.get_text(
            self.config,
            "Save Plan",
            "Plan name:",
            "",
            self,
        )
        if not ok:
            return
        name = normalize_plan_name(name)
        if not name:
            MessageDialog.show_warning(self.config, "Save Plan", "Please enter a plan name.", self)
            return

        settings = UserSettingsService.get_instance()
        plans = settings.get_bulk_operation_plans()
        if name in plans:
            if not ConfirmationDialog.show_confirmation(
                self.config,
                "Overwrite Plan",
                f'A plan named "{name}" already exists. Overwrite it?',
                self,
            ):
                return

        plans[name] = plan_operations_to_dicts(self._pending_operations)
        settings.update_bulk_operation_plans(plans)

    def _on_load_plan_clicked(self) -> None:
        """Show a menu of saved plans (load) and a Delete plan… submenu."""
        if self._operation_in_progress:
            return
        from app.services.user_settings_service import UserSettingsService
        from app.views.style.menu_bar import apply_menu_styling

        settings = UserSettingsService.get_instance()
        plans = settings.get_bulk_operation_plans()
        names = sorted(plans.keys(), key=lambda n: n.casefold())

        menu = QMenu(self)
        apply_menu_styling(menu, self.config)

        if not names:
            empty = menu.addAction("No saved plans")
            empty.setEnabled(False)
        else:
            for name in names:
                action = menu.addAction(name)
                action.triggered.connect(
                    lambda _checked=False, n=name: self._load_named_plan(n)
                )
            menu.addSeparator()
            delete_menu = menu.addMenu("Delete plan…")
            apply_menu_styling(delete_menu, self.config)
            for name in names:
                delete_action = delete_menu.addAction(name)
                delete_action.triggered.connect(
                    lambda _checked=False, n=name: self._delete_named_plan(n)
                )

        button_pos = self.load_plan_button.mapToGlobal(
            self.load_plan_button.rect().bottomLeft()
        )
        menu.exec(button_pos)

    def _load_named_plan(self, name: str) -> None:
        """Replace the operations list with a saved plan (confirm if non-empty)."""
        if self._operation_in_progress:
            return
        from app.services.user_settings_service import UserSettingsService
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog
        from app.views.dialogs.message_dialog import MessageDialog

        plans = UserSettingsService.get_instance().get_bulk_operation_plans()
        raw = plans.get(name)
        if raw is None:
            MessageDialog.show_warning(
                self.config, "Load Plan", f'Plan "{name}" was not found.', self
            )
            return
        operations, error = plan_operations_from_dicts(raw)
        if error:
            MessageDialog.show_warning(self.config, "Load Plan", error, self)
            return

        if self._pending_operations:
            if not ConfirmationDialog.show_confirmation(
                self.config,
                "Load Plan",
                f'Replace the current operations list with "{name}"?',
                self,
            ):
                return

        self._pending_operations = list(operations)
        self._selected_operation_index = (
            len(self._pending_operations) - 1 if self._pending_operations else None
        )
        self._rebuild_operations_list()
        self._update_toolbar_enabled()
        self._apply_configured_dialog_size()

    def _delete_named_plan(self, name: str) -> None:
        """Confirm and remove a named plan from in-memory user settings."""
        from app.services.user_settings_service import UserSettingsService
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog

        if not ConfirmationDialog.show_confirmation(
            self.config,
            "Delete Plan",
            f'Delete saved plan "{name}"?',
            self,
        ):
            return
        settings = UserSettingsService.get_instance()
        plans = settings.get_bulk_operation_plans()
        if name not in plans:
            return
        del plans[name]
        settings.update_bulk_operation_plans(plans)

    def _remember_current_state(self) -> None:
        """Persist plan + Smart Update + game scope for the next dialog open."""
        BulkOperationsDialog._last_state = BulkOperationsDialog._RememberedState(
            operations=tuple(self._pending_operations),
            update_result=bool(self.update_result_check.isChecked()),
            update_eco=bool(self.update_eco_check.isChecked()),
            selected_games_scope=bool(self.selected_games_radio.isChecked()),
        )

    def _restore_last_state(self) -> None:
        """Restore remembered settings (Search-dialog style in-memory recall)."""
        state = BulkOperationsDialog._last_state
        if state is None:
            return
        self._pending_operations = list(state.operations)
        self._selected_operation_index = (
            len(self._pending_operations) - 1 if self._pending_operations else None
        )
        self.update_result_check.setChecked(state.update_result)
        self.update_eco_check.setChecked(state.update_eco)
        if state.selected_games_scope and self.selected_game_indices:
            self.selected_games_radio.setChecked(True)
        elif state.selected_games_scope and not self.selected_game_indices:
            # No current selection available — keep All games.
            self.all_games_radio.setChecked(True)
        else:
            self.all_games_radio.setChecked(True)
        self._rebuild_operations_list()
        self._update_toolbar_enabled()
        self._apply_configured_dialog_size()

    def done(self, result: int) -> None:  # noqa: N802
        self._remember_current_state()
        super().done(result)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # Ignore window-close while Apply is running so nested processEvents
        # cannot tear down the dialog mid-pass.
        if self._operation_in_progress:
            event.ignore()
            return
        super().closeEvent(event)

    def _on_progress_accepted(self) -> None:
        """Success Close: clear busy flag, remember plan, then close."""
        self._operation_in_progress = False
        self._remember_current_state()
        self.accept()

    def _on_editor_saved(self, payload: object) -> None:
        edit_index, operation = payload  # type: ignore[misc]
        if edit_index is None:
            self._pending_operations.append(operation)
            self._selected_operation_index = len(self._pending_operations) - 1
        elif 0 <= int(edit_index) < len(self._pending_operations):
            self._pending_operations[int(edit_index)] = operation
            self._selected_operation_index = int(edit_index)
        self._rebuild_operations_list()
        self._apply_configured_dialog_size()

    def _apply_configured_dialog_size(self) -> None:
        self.setFixedWidth(int(self.dialog_width))
        lay = self.layout()
        if lay is None:
            return
        h = lay.sizeHint().height()
        if h > 0:
            self.setFixedHeight(h)

    def _apply_styling(self) -> None:
        from app.views.style import StyleManager

        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_operations", {})
        bg = dialog_config.get("background_color", [40, 40, 45])
        border = dialog_config.get("border_color", [60, 60, 65])

        StyleManager.style_buttons(
            [self.apply_button, self.cancel_button],
            self.config,
            bg,
            border,
            min_width=self.button_width,
            min_height=self.button_height,
        )

        toolbar_buttons = [
            self.add_operation_button,
            self.edit_operation_button,
            self.remove_operation_button,
            self.clear_operations_button,
            self.save_plan_button,
            self.load_plan_button,
        ]
        StyleManager.style_buttons(
            toolbar_buttons,
            self.config,
            bg,
            border,
            min_width=None,
            min_height=self.button_height,
        )
        self.add_operation_button.setIcon(
            themed_icon_from_svg(self.add_button_icon_svg, self.toolbar_icon_tint)
        )
        self.edit_operation_button.setIcon(
            themed_icon_from_svg(self.edit_button_icon_svg, self.toolbar_icon_tint)
        )
        self.remove_operation_button.setIcon(
            themed_icon_from_svg(self.remove_button_icon_svg, self.toolbar_icon_tint)
        )
        self.clear_operations_button.setIcon(
            themed_icon_from_svg(self.clear_button_icon_svg, self.toolbar_icon_tint)
        )
        self.save_plan_button.setIcon(
            themed_icon_from_svg(self.save_button_icon_svg, self.toolbar_icon_tint)
        )
        self.load_plan_button.setIcon(
            themed_icon_from_svg(self.load_button_icon_svg, self.toolbar_icon_tint)
        )
        for btn in toolbar_buttons:
            btn.setText("")
            btn.setIconSize(QSize(self.toolbar_icon_px, self.toolbar_icon_px))
            btn.setFixedSize(self.button_height, self.button_height)
        sep_h = max(8, self.button_height - self.toolbar_separator_margin[1] - self.toolbar_separator_margin[3])
        for sep in (self._toolbar_separator, self._toolbar_plans_separator):
            sep.setFixedHeight(sep_h)
            sep.setStyleSheet(
                f"QFrame#{sep.objectName()} {{"
                f"  background-color: rgb({border[0]}, {border[1]}, {border[2]});"
                "  border: 0px; padding: 0px; margin: 0px;"
                "}"
            )
        self._update_toolbar_enabled()

        input_bg = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        input_border = [
            self.input_border_color.red(),
            self.input_border_color.green(),
            self.input_border_color.blue(),
        ]
        StyleManager.style_scroll_area(
            self.operations_scroll,
            self.config,
            input_bg,
            input_border,
            self.input_border_radius,
        )

        groups_config = dialog_config.get("groups", {})
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=groups_config.get("border_color", border),
                border_width=groups_config.get("border_width", 1),
                border_radius=groups_config.get("border_radius", 5),
                bg_color=groups_config.get("background_color"),
                margin_top=groups_config.get("margin_top", 8),
                padding_top=groups_config.get("padding_top", 4),
                title_font_family=resolve_font_family(groups_config.get("title_font_family")),
                title_font_size=scale_font_size(groups_config.get("title_font_size", 11)),
                title_color=groups_config.get("title_color"),
                title_left=groups_config.get("title_left", 10),
                title_padding=groups_config.get("title_padding", [0, 5]),
                content_margins=groups_config.get("content_margins", [12, 14, 12, 12]),
            )

        label_style = (
            f"QLabel {{ color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()}); "
            f"font-family: {self.label_font_family}; font-size: {self.label_font_size}pt; background: transparent; }}"
        )
        overlay_roots = (self._editor, self._progress_overlay)
        for label in self.findChildren(QLabel):
            if any(root is label or root.isAncestorOf(label) for root in overlay_roots):
                continue
            label.setStyleSheet(label_style)

        radios = [
            r
            for r in self.findChildren(QRadioButton)
            if not any(root is r or root.isAncestorOf(r) for root in overlay_roots)
        ]
        if radios:
            StyleManager.style_radio_buttons(radios, self.config)

        checkmark = Path(__file__).resolve().parents[2] / "resources" / "icons" / "checkmark.svg"
        dialog_checks = [
            c
            for c in self.findChildren(QCheckBox)
            if not any(root is c or root.isAncestorOf(c) for root in overlay_roots)
        ]
        StyleManager.style_checkboxes(
            dialog_checks,
            self.config,
            [
                self.label_text_color.red(),
                self.label_text_color.green(),
                self.label_text_color.blue(),
            ],
            self.label_font_family,
            self.label_font_size,
            input_bg,
            input_border,
            checkmark,
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_path_label_truncation()
        self._apply_configured_dialog_size()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_path_label_truncation()
        self._update_summary_elision()
        if self._editor.isVisible():
            self._editor.setGeometry(self.rect())
        if self._progress_overlay.isVisible():
            self._progress_overlay.setGeometry(self.rect())

    def _update_path_label_truncation(self) -> None:
        if getattr(self, "_db_name_full", None) and hasattr(self, "db_name_label"):
            container = self.db_name_label.parent()
            if container:
                name_w = max(40, container.width() - self._target_db_label.width() - 8)
                self.db_name_label.setMaximumWidth(name_w)
                name_font = QFont(self.db_name_label.font())
                name_font.setBold(True)
                self.db_name_label.setText(
                    f"<b>{truncate_text_middle(self._db_name_full, name_w, name_font)}</b>"
                )
                self.db_name_label.setToolTip(self._db_name_full)
        if getattr(self, "_db_path_full", None) and getattr(self, "db_path_label", None):
            self.db_path_label.setText(
                truncate_path_for_display(self._db_path_full, max(80, self.db_path_label.width()), self.db_path_label.font())
            )

    def _on_progress_updated(
        self,
        percent: int,
        message: str,
        games_processed: int,
        games_updated: int,
        games_failed: int,
        games_skipped: int,
        step_label: str,
    ) -> None:
        self._progress_overlay.set_step(step_label)
        if message == "Finishing…":
            self._progress_overlay.set_status(message)
        self._progress_overlay.set_live_stats(
            games_processed,
            games_updated,
            games_failed,
            games_skipped,
        )
        # Do not processEvents here — the worker/QThread keeps the UI loop free.

    def _on_progress_cancel_requested(self) -> None:
        if self._operation_in_progress:
            self.controller.cancel_operation()

    def _on_progress_dismissed(self) -> None:
        self._operation_in_progress = False
        self._set_controls_enabled(True)
        self.apply_button.setEnabled(True)
        self.cancel_button.setText("Cancel")

    def _on_cancel_clicked(self) -> None:
        if self._operation_in_progress:
            self.controller.cancel_operation()
            self._progress_overlay.set_status("Cancelling…")
            return
        self.reject()

    def _on_apply_clicked(self) -> None:
        if not self.database:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "No database selected", self)
            return
        if self._operation_in_progress:
            return

        has_result = self.update_result_check.isChecked()
        has_eco = self.update_eco_check.isChecked()
        if not self._pending_operations and not has_result and not has_eco:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Error",
                "Please add at least one operation, or enable Smart Update",
                self,
            )
            return

        from app.views.dialogs.confirmation_dialog import ConfirmationDialog

        plan_issues = validate_bulk_operation_plan(
            list(self._pending_operations),
            has_result,
            has_eco,
        )
        if plan_issues and not ConfirmationDialog.show_confirmation(
            self.config,
            "Conflicting operations",
            format_bulk_plan_issues(plan_issues),
            self,
        ):
            return

        self._set_controls_enabled(False)
        self._operation_in_progress = True
        self.apply_button.setEnabled(False)
        self._progress_overlay.open_running()
        # Let the overlay paint before starting the worker thread.
        QTimer.singleShot(0, lambda: self._run_operations(has_result, has_eco))

    def _run_operations(self, has_result: bool, has_eco: bool) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        game_indices = None
        if self.selected_games_radio.isChecked():
            game_indices = self.selected_game_indices if self.selected_game_indices else None
        worker = _BulkOperationsWorker(
            self.controller,
            self.database,
            list(self._pending_operations),
            has_result,
            has_eco,
            game_indices,
            self,
        )
        worker.finished_with_result.connect(self._finish_operations)
        worker.failed_with_error.connect(self._on_worker_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_worker_failed(self, message: str) -> None:
        from app.views.dialogs.message_dialog import MessageDialog
        MessageDialog.show_critical(
            self.config,
            "Error",
            f"An error occurred: {message}",
            self,
        )
        self._operation_in_progress = False
        self._progress_overlay.show_failed(message)
        self._worker = None

    def _finish_operations(self, result) -> None:
        self._worker = None
        if not result.success:
            self._operation_in_progress = False
            message = result.error_message or "Operation failed"
            if message == "Cancelled":
                self._progress_overlay.show_cancelled()
            else:
                self._progress_overlay.show_failed(message)
            return

        # UI-thread post-work (unsafe to do inside the worker QThread).
        if result.games_updated > 0 and self.database is not None:
            game_indices = None
            if self.selected_games_radio.isChecked():
                game_indices = self.selected_game_indices if self.selected_game_indices else None
            self.controller._refresh_active_game_if_updated(self.database, game_indices)
            self.controller.database_controller.mark_database_unsaved(self.database)

        self._progress_overlay.show_complete(format_bulk_operation_summary_plain(result))

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.all_games_radio.setEnabled(enabled)
        self.selected_games_radio.setEnabled(enabled)
        self.update_result_check.setEnabled(enabled)
        self.update_eco_check.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.cancel_button.setEnabled(True)
        has_selection = (
            self._selected_operation_index is not None
            and 0 <= int(self._selected_operation_index) < len(self._pending_operations)
        )
        self.add_operation_button.setEnabled(enabled)
        self.edit_operation_button.setEnabled(enabled and has_selection)
        self.remove_operation_button.setEnabled(enabled and has_selection)
        self.clear_operations_button.setEnabled(
            enabled and bool(self._pending_operations)
        )
        self.operations_scroll.setEnabled(enabled)

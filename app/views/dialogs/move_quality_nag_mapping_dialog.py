"""Dialog for configuring move-quality classification → NAG mapping."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.move_quality_nag_mapping_controller import MoveQualityNagMappingController
from app.services.move_quality_nag_service import (
    ASSESSMENT_LABELS,
    QUALITY_NAG_CHOICES,
)
from app.services.pgn_formatter_service import get_nag_text
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.path_resolver import get_app_resource_path
from app.views.style import StyleManager
from app.views.widgets.row_hover_table_widget import RowHoverTableWidget


class MoveQualityNagMappingDialog(QDialog):
    """Configure which quality NAG is written for each move classification."""

    COL_ENABLED = 0
    COL_CLASSIFICATION = 1
    COL_NAG = 2
    COL_MEANING = 3

    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.controller = MoveQualityNagMappingController(config)
        self._row_widgets: Dict[str, Tuple[QCheckBox, QComboBox]] = {}
        self._updating_table = False

        self._load_config()
        self.setWindowTitle(self.window_title)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        self._setup_ui()
        self._apply_styling()
        self._populate_table(self.controller.load_mapping())
        self._apply_configured_dialog_size()

    def _dialog_config(self) -> Dict[str, Any]:
        return self.config.get("ui", {}).get("dialogs", {}).get("move_quality_nag_mapping", {})

    def _load_config(self) -> None:
        dialog_config = self._dialog_config()
        self.window_title = str(dialog_config.get("window_title", "Move Quality NAG Mapping"))
        self.dialog_width = int(dialog_config.get("width", 560))
        self.bottom_button_top_padding = int(dialog_config.get("bottom_button_top_padding", 50))
        self.dialog_minimum_width = dialog_config.get("minimum_width")
        self.dialog_minimum_height = dialog_config.get("minimum_height")

        self.bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.border_color = dialog_config.get("border_color", [60, 60, 65])
        self.text_color = dialog_config.get("text_color", [200, 200, 200])
        self.font_size = scale_font_size(dialog_config.get("font_size", 11))

        layout_config = dialog_config.get("layout", {})
        self.layout_spacing = int(layout_config.get("spacing", 10))
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )

        inputs_config = dialog_config.get("inputs", {})
        self.input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        self.input_border_color = inputs_config.get("border_color", [60, 60, 65])

        table_config = dialog_config.get("table", {})
        self.table_bg_color = table_config.get("background_color", [30, 30, 35])
        self.table_text_color = table_config.get("text_color", [240, 240, 240])
        self.table_border_color = table_config.get("border_color", [60, 60, 65])
        self.table_border_radius = int(table_config.get("border_radius", 3))
        self.table_header_bg = table_config.get(
            "header_background_color", [45, 45, 50]
        )
        self.table_header_text = table_config.get(
            "header_text_color", [200, 200, 200]
        )
        self.table_item_padding = int(table_config.get("item_padding", 5))
        self.table_header_padding = int(table_config.get("header_padding", 5))
        self.table_enabled_width = int(table_config.get("enabled_column_width", 80))
        self.table_classification_width = int(
            table_config.get("classification_column_width", 140)
        )
        self.table_nag_width = int(table_config.get("nag_column_width", 120))
        self.table_row_height = int(table_config.get("row_height", 40))
        self.table_alternating = bool(table_config.get("alternating_row_colors", True))
        self.table_alternate_bg = table_config.get(
            "alternate_background_color",
            [
                max(0, self.table_bg_color[0] + 8),
                max(0, self.table_bg_color[1] + 8),
                max(0, self.table_bg_color[2] + 8),
            ],
        )
        self.table_selection_bg = table_config.get(
            "selection_background_color",
            [
                min(255, self.bg_color[0] + 20),
                min(255, self.bg_color[1] + 20),
                min(255, self.bg_color[2] + 20),
            ],
        )
        self.table_selection_text = table_config.get(
            "selection_text_color", self.table_text_color
        )
        self.table_hover_bg = table_config.get(
            "hover_background_color", self.table_selection_bg
        )
        self.table_hover_text = table_config.get(
            "hover_text_color", self.table_text_color
        )
        _hb = table_config.get("header_section_border", False)
        if isinstance(_hb, str):
            self.table_header_section_border = _hb.strip().lower() in (
                "true",
                "1",
                "yes",
                "on",
            )
        else:
            self.table_header_section_border = bool(_hb)

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 120))
        self.button_height = int(buttons_config.get("height", 30))
        self.button_spacing = int(buttons_config.get("spacing", 10))
        self.button_border_color = buttons_config.get(
            "border_color", self.border_color
        )

    def _apply_configured_dialog_size(self) -> None:
        """Width from config; height from layout size hint."""
        w = int(self.dialog_width)
        if self.dialog_minimum_width is not None:
            w = max(w, int(self.dialog_minimum_width))
        self.setFixedWidth(w)
        lay = self.layout()
        if lay is None:
            return
        h = lay.sizeHint().height()
        if h <= 0:
            return
        if self.dialog_minimum_height is not None:
            h = max(h, int(self.dialog_minimum_height))
        self.setFixedHeight(h)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._populate_table(self.controller.load_mapping())
        self._apply_configured_dialog_size()

    def _setup_ui(self) -> None:
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(self.bg_color[0], self.bg_color[1], self.bg_color[2]),
        )
        self.setPalette(palette)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.layout_spacing)
        margins = self.layout_margins
        main_layout.setContentsMargins(
            int(margins[0]), int(margins[1]), int(margins[2]), int(margins[3])
        )

        self.table = RowHoverTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Enabled", "Classification", "NAG", "Meaning"]
        )
        header_tooltips = {
            self.COL_ENABLED: "Write a quality NAG for this classification",
            self.COL_CLASSIFICATION: "Move quality classification from analysis",
            self.COL_NAG: "Standard quality NAG glyph / code",
            self.COL_MEANING: "Informal NAG description",
        }
        for col, tip in header_tooltips.items():
            item = self.table.horizontalHeaderItem(col)
            if item is not None:
                item.setToolTip(tip)

        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(self.table_alternating)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(self.COL_ENABLED, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(
            self.COL_CLASSIFICATION, QHeaderView.ResizeMode.Fixed
        )
        header.setSectionResizeMode(self.COL_NAG, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_MEANING, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(self.COL_ENABLED, self.table_enabled_width)
        self.table.setColumnWidth(
            self.COL_CLASSIFICATION, self.table_classification_width
        )
        self.table.setColumnWidth(self.COL_NAG, self.table_nag_width)

        v_header = self.table.verticalHeader()
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        v_header.setDefaultSectionSize(self.table_row_height)

        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        main_layout.addWidget(self.table)

        main_layout.addSpacing(self.bottom_button_top_padding)

        button_row = QHBoxLayout()
        button_row.setSpacing(self.button_spacing)

        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._reset_to_defaults)
        button_row.addWidget(self.reset_button)
        button_row.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setDefault(True)
        button_row.addWidget(self.save_button)
        main_layout.addLayout(button_row)

    def _on_table_selection_changed(self) -> None:
        self.table.refresh_row_chrome()

    @staticmethod
    def _meaning_for_nag(nag: Optional[int]) -> str:
        if nag is None:
            return "—"
        try:
            return get_nag_text(int(nag))
        except Exception:
            return "—"

    def _nag_to_combo_index(self, nag: Optional[int]) -> int:
        for i, (_label, value) in enumerate(QUALITY_NAG_CHOICES):
            if value == nag:
                return i
        return 0

    def _item_flags(self) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def _embed_cell_widget(
        self,
        row: int,
        column: int,
        widget: QWidget,
        *,
        center: bool = True,
        margins: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        """Place ``widget`` in a transparent cell container and track hover."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(0)
        # Keep editors vertically centered in the taller row.
        align = Qt.AlignmentFlag.AlignVCenter
        if center:
            align |= Qt.AlignmentFlag.AlignHCenter
            layout.setAlignment(align)
            layout.addWidget(widget)
        else:
            layout.setAlignment(align)
            layout.addWidget(widget, 1)
        self.table.setCellWidget(row, column, container)
        self.table.track_cell_widget(container)

    def _set_meaning_item(self, row: int, nag: Optional[int]) -> None:
        item = self.table.item(row, self.COL_MEANING)
        if item is None:
            item = QTableWidgetItem()
            item.setFlags(self._item_flags())
            self.table.setItem(row, self.COL_MEANING, item)
        item.setText(self._meaning_for_nag(nag))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

    def _on_row_nag_changed(self, label: str, index: int) -> None:
        if self._updating_table:
            return
        combo = self._row_widgets[label][1]
        nag = combo.itemData(index)
        if nag is not None:
            nag = int(nag)
        for row in range(self.table.rowCount()):
            class_item = self.table.item(row, self.COL_CLASSIFICATION)
            if class_item is not None and class_item.text() == label:
                self._set_meaning_item(row, nag)
                break

    def _on_row_enabled_toggled(self, label: str, checked: bool) -> None:
        if self._updating_table:
            return
        _checkbox, combo = self._row_widgets[label]
        combo.setEnabled(checked)

    def _populate_table(self, mapping: Dict[str, Dict[str, Any]]) -> None:
        self._updating_table = True
        self.table.clear_hover()
        self._row_widgets.clear()
        self.table.setRowCount(0)
        self.table.setRowCount(len(ASSESSMENT_LABELS))
        flags = self._item_flags()

        for row, label in enumerate(ASSESSMENT_LABELS):
            entry = mapping.get(label, {})
            enabled = bool(entry.get("enabled", False))
            nag = entry.get("nag")
            if nag is not None:
                try:
                    nag = int(nag)
                except (TypeError, ValueError):
                    nag = None

            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(flags)
            enabled_item.setData(Qt.ItemDataRole.UserRole, label)
            self.table.setItem(row, self.COL_ENABLED, enabled_item)

            checkbox = QCheckBox()
            checkbox.setChecked(enabled)
            checkbox.setToolTip(f"Write a quality NAG when classified as {label}")
            checkbox.toggled.connect(
                lambda checked, lbl=label: self._on_row_enabled_toggled(lbl, checked)
            )
            self._embed_cell_widget(row, self.COL_ENABLED, checkbox, center=True)

            class_item = QTableWidgetItem(label)
            class_item.setFlags(flags)
            class_item.setData(Qt.ItemDataRole.UserRole, label)
            class_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, self.COL_CLASSIFICATION, class_item)

            nag_item = QTableWidgetItem("")
            nag_item.setFlags(flags)
            nag_item.setData(Qt.ItemDataRole.UserRole, label)
            self.table.setItem(row, self.COL_NAG, nag_item)

            combo = QComboBox()
            for choice_label, choice_nag in QUALITY_NAG_CHOICES:
                combo.addItem(choice_label, choice_nag)
            combo.setCurrentIndex(self._nag_to_combo_index(nag))
            combo.setEnabled(enabled)
            combo.currentIndexChanged.connect(
                lambda index, lbl=label: self._on_row_nag_changed(lbl, index)
            )
            # Container keeps StyleManager combo QSS intact when row chrome
            # updates the cell widget stylesheet (same pattern as highlight rules).
            self._embed_cell_widget(
                row,
                self.COL_NAG,
                combo,
                center=False,
                margins=(4, 2, 4, 2),
            )

            self._set_meaning_item(row, nag)
            meaning_item = self.table.item(row, self.COL_MEANING)
            if meaning_item is not None:
                meaning_item.setData(Qt.ItemDataRole.UserRole, label)

            self._row_widgets[label] = (checkbox, combo)

        header_h = max(self.table.horizontalHeader().height(), 28)
        rows_h = self.table_row_height * len(ASSESSMENT_LABELS)
        frame = self.table.frameWidth() * 2
        self.table.setFixedHeight(header_h + rows_h + frame + 2)

        self._updating_table = False
        self._style_table_editors()
        self.table.refresh_row_chrome()

    def _collect_mapping(self) -> Dict[str, Dict[str, Any]]:
        mapping: Dict[str, Dict[str, Any]] = {}
        for label, (checkbox, combo) in self._row_widgets.items():
            nag = combo.currentData()
            if nag is not None:
                nag = int(nag)
            mapping[label] = {"enabled": checkbox.isChecked(), "nag": nag}
        return mapping

    def _reset_to_defaults(self) -> None:
        self.controller.show_progress()
        self.controller.set_status("Resetting move quality NAG mapping to defaults...")
        QApplication.processEvents()
        self._populate_table(self.controller.get_defaults())
        self.controller.hide_progress()
        self.controller.set_status("Move quality NAG mapping reset to defaults")
        QApplication.processEvents()

    def _on_save(self) -> None:
        self.controller.show_progress()
        self.controller.set_status("Saving move quality NAG mapping...")
        QApplication.processEvents()
        self.controller.save_mapping(self._collect_mapping())
        self.controller.hide_progress()
        self.controller.set_status("Move quality NAG mapping saved")
        QApplication.processEvents()
        self.accept()

    def _apply_styling(self) -> None:
        bg = [int(self.bg_color[0]), int(self.bg_color[1]), int(self.bg_color[2])]
        border = [
            int(self.button_border_color[0]),
            int(self.button_border_color[1]),
            int(self.button_border_color[2]),
        ]

        StyleManager.style_buttons(
            [self.reset_button, self.cancel_button, self.save_button],
            self.config,
            bg,
            border,
            min_width=self.button_width,
            min_height=self.button_height,
        )

        header_border = (
            f"border: none; border-bottom: 1px solid rgb({self.table_border_color[0]}, {self.table_border_color[1]}, {self.table_border_color[2]});"
            if self.table_header_section_border
            else "border: none;"
        )
        # ::item:hover uses the same full-row hover color so Windows/macOS native
        # per-cell hover does not paint a second, mismatched highlight.
        table_style = (
            f"QTableWidget {{"
            f"background-color: rgb({self.table_bg_color[0]}, {self.table_bg_color[1]}, {self.table_bg_color[2]});"
            f"alternate-background-color: rgb({self.table_alternate_bg[0]}, {self.table_alternate_bg[1]}, {self.table_alternate_bg[2]});"
            f"color: rgb({self.table_text_color[0]}, {self.table_text_color[1]}, {self.table_text_color[2]});"
            f"border: 1px solid rgb({self.table_border_color[0]}, {self.table_border_color[1]}, {self.table_border_color[2]});"
            f"border-radius: {self.table_border_radius}px;"
            f"gridline-color: transparent;"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.font_size}pt;"
            f"outline: none;"
            f"}}"
            f"QTableWidget::item {{"
            f"padding: {self.table_item_padding}px;"
            f"}}"
            f"QTableWidget::item:hover {{"
            f"background-color: rgb({self.table_hover_bg[0]}, {self.table_hover_bg[1]}, {self.table_hover_bg[2]});"
            f"color: rgb({self.table_hover_text[0]}, {self.table_hover_text[1]}, {self.table_hover_text[2]});"
            f"}}"
            f"QTableWidget::item:selected,"
            f"QTableWidget::item:hover:selected {{"
            f"background-color: rgb({self.table_selection_bg[0]}, {self.table_selection_bg[1]}, {self.table_selection_bg[2]});"
            f"color: rgb({self.table_selection_text[0]}, {self.table_selection_text[1]}, {self.table_selection_text[2]});"
            f"}}"
            f"QHeaderView::section {{"
            f"background-color: rgb({self.table_header_bg[0]}, {self.table_header_bg[1]}, {self.table_header_bg[2]});"
            f"color: rgb({self.table_header_text[0]}, {self.table_header_text[1]}, {self.table_header_text[2]});"
            f"{header_border}"
            f"padding: {self.table_header_padding}px;"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.font_size}pt;"
            f"}}"
        )
        self.table.configure_row_chrome(
            hover_bg=self.table_hover_bg,
            hover_text=self.table_hover_text,
            selection_bg=self.table_selection_bg,
        )
        self.table.setStyleSheet(table_style)
        StyleManager.style_table_scrollbar(
            self.table,
            self.config,
            self.input_bg_color,
            self.input_border_color,
            table_style,
        )

        header = self.table.horizontalHeader()
        if header is not None:
            header_palette = header.palette()
            header_palette.setColor(
                header.backgroundRole(), QColor(*self.table_header_bg)
            )
            header_palette.setColor(
                header.foregroundRole(), QColor(*self.table_header_text)
            )
            header.setPalette(header_palette)
            header.setAutoFillBackground(True)

        self._style_table_editors()

    def _style_table_editors(self) -> None:
        checkmark_path = get_app_resource_path("app/resources/icons/checkmark.svg")
        checkboxes = list(self.findChildren(QCheckBox))
        if checkboxes:
            StyleManager.style_checkboxes(
                checkboxes,
                self.config,
                self.table_text_color,
                self.label_font_family,
                self.font_size,
                self.input_bg_color,
                self.input_border_color,
                checkmark_path,
            )

        comboboxes = list(self.findChildren(QComboBox))
        if not comboboxes:
            return
        # Unified ui.styles defaults (same as other dialogs).
        StyleManager.style_comboboxes(comboboxes, self.config)
        # Leave a few pixels for cell margins so the combo is not clipped.
        combo_min_h = max(26, self.table_row_height - 12)
        for combo in comboboxes:
            combo.setMinimumHeight(combo_min_h)
            combo.setMaximumHeight(combo_min_h)
            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )

"""Manage Game Highlight Rules dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.game_highlight_rules_controller import GameHighlightRulesController
from app.services.game_highlight_rules_service import (
    EffectiveHighlightRule,
    HighlightComposerSettings,
)
from app.services.game_highlights.rule_catalog import (
    PHASE_ENDGAME,
    PHASE_MIDDLEGAME,
    PHASE_OPENING,
    get_category,
    list_builtin_rules,
)
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.tooltip_utils import wrap_tooltip_text
from app.views.dialogs.confirmation_dialog import ConfirmationDialog
from app.views.style import StyleManager
from app.views.widgets.row_hover_table_widget import RowHoverTableWidget


class _ReorderableRulesTable(RowHoverTableWidget):
    """Table that reorders rows via InternalMove while preserving cell widgets."""

    def __init__(self, parent_dialog: "ManageGameHighlightRulesDialog") -> None:
        super().__init__()
        self.parent_dialog = parent_dialog

    def dropEvent(self, event) -> None:  # type: ignore[override]
        if not self.parent_dialog._can_reorder():
            event.ignore()
            return

        order_before: List[str] = []
        for row in range(self.rowCount()):
            item = self.item(row, ManageGameHighlightRulesDialog.COL_RULE)
            if item is None:
                item = self.item(row, ManageGameHighlightRulesDialog.COL_ENABLED)
            if item is None:
                continue
            rule_id = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(rule_id, str) and rule_id:
                order_before.append(rule_id)

        drop_row = self.drop_on(event)
        if drop_row is None:
            drop_row = self.rowCount()

        selected_items = self.selectedItems()
        dragged_rule_id: Optional[str] = None
        source_row: Optional[int] = None
        if selected_items:
            dragged_item = selected_items[0]
            source_row = dragged_item.row()
            dragged_rule_id = dragged_item.data(Qt.ItemDataRole.UserRole)

        if not dragged_rule_id or dragged_rule_id not in order_before:
            event.ignore()
            return

        new_order = order_before.copy()
        new_order.remove(dragged_rule_id)
        if source_row is not None and source_row < drop_row:
            drop_row -= 1
        drop_row = max(0, min(drop_row, len(new_order)))
        new_order.insert(drop_row, dragged_rule_id)

        event.accept()
        self.parent_dialog._apply_reordered_visible(new_order)

    def drop_on(self, event) -> Optional[int]:
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            return self.rowCount()
        item = self.item(index.row(), ManageGameHighlightRulesDialog.COL_RULE)
        if item is None:
            item = self.item(index.row(), ManageGameHighlightRulesDialog.COL_ENABLED)
        if item is None:
            return index.row()
        item_rect = self.visualItemRect(item)
        drop_point = event.position().toPoint()
        if drop_point.y() < item_rect.center().y():
            return index.row()
        return index.row() + 1


class ManageGameHighlightRulesDialog(QDialog):
    """Themed dialog for enabling rules, priority order, phases, and output settings."""

    COL_ENABLED = 0
    COL_CATEGORY = 1
    COL_RULE = 2
    COL_PRIORITY = 3
    COL_OPENING = 4
    COL_MIDDLEGAME = 5
    COL_ENDGAME = 6

    def __init__(
        self,
        config: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        highlights_cfg = (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("summary", {})
            .get("highlights", {})
        )
        default_max_per_phase = int(highlights_cfg.get("max_per_phase", 7))
        self.controller = GameHighlightRulesController(
            self, default_max_per_phase=default_max_per_phase
        )
        self._draft: Dict[str, EffectiveHighlightRule] = {}
        self._draft_order: List[str] = []
        self._visible_rule_ids: List[str] = []
        self._updating_table = False
        self._updating_output = False
        self._output_field_labels: List[QLabel] = []

        self._load_config()
        self.setWindowTitle(self.window_title)
        self.setMinimumSize(self.dialog_minimum_width, self.dialog_minimum_height)
        self.resize(self.dialog_width, self.dialog_height)

        self._setup_ui()
        self._apply_styling()
        self._reload_from_service()
        from app.views.widgets.themed_dialog_size_grip import (
            install_themed_dialog_resize_grip,
        )

        install_themed_dialog_resize_grip(self, self.config)

    def _load_config(self) -> None:
        dialog_config = (
            self.config.get("ui", {})
            .get("dialogs", {})
            .get("manage_game_highlight_rules", {})
        )
        self._dialog_config = dialog_config

        self.window_title = str(
            dialog_config.get("window_title", "Manage Game Highlight Rules")
        )
        self.dialog_width = int(dialog_config.get("width", 780))
        self.dialog_height = int(dialog_config.get("height", 560))
        self.dialog_minimum_width = int(dialog_config.get("minimum_width", 720))
        self.dialog_minimum_height = int(dialog_config.get("minimum_height", 520))
        self.bottom_button_top_padding = int(
            dialog_config.get("bottom_button_top_padding", 50)
        )

        self.bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.border_color = dialog_config.get("border_color", [60, 60, 65])
        self.text_color = dialog_config.get("text_color", [200, 200, 200])
        self.font_size = scale_font_size(dialog_config.get("font_size", 11))

        layout_config = dialog_config.get("layout", {})
        self.layout_spacing = int(layout_config.get("spacing", 10))
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])
        self.composition_section_top_spacing = int(
            layout_config.get("composition_section_top_spacing", 14)
        )

        filter_config = dialog_config.get("filter", {})
        self.filter_placeholder = filter_config.get(
            "placeholder", "Filter by category or rule…"
        )
        self.filter_min_height = int(filter_config.get("minimum_height", 28))

        status_config = dialog_config.get("status", {})
        self.status_font_size = scale_font_size(
            status_config.get("font_size", dialog_config.get("font_size", 11))
        )
        self.status_text_color = status_config.get("text_color", self.text_color)

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )

        inputs_config = dialog_config.get("inputs", {})
        self.input_font_family = resolve_font_family(
            inputs_config.get("font_family", "Helvetica Neue")
        )
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = inputs_config.get("text_color", [240, 240, 240])
        self.input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        self.input_border_color = inputs_config.get("border_color", [60, 60, 65])
        self.input_focus_border_color = inputs_config.get(
            "focus_border_color", [70, 90, 130]
        )
        self.input_border_radius = int(inputs_config.get("border_radius", 3))
        self.input_padding = inputs_config.get("padding", [8, 6])

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
        self.table_category_width = int(table_config.get("category_column_width", 150))
        self.table_priority_width = int(table_config.get("priority_column_width", 80))
        self.table_phase_width = int(table_config.get("phase_column_width", 90))
        self.table_row_height = int(table_config.get("row_height", 28))
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
        self.action_button_width = int(
            buttons_config.get("action_width", buttons_config.get("width", 140))
        )

        groups_config = dialog_config.get("groups", {})
        self.groups_config = groups_config

        fields_config = dialog_config.get("fields", {})
        self.fields_config = fields_config
        self.fields_spacing = int(fields_config.get("spacing", 16))
        self.fields_row_spacing = int(fields_config.get("row_spacing", 8))
        self.fields_input_width = int(fields_config.get("input_width", 56))
        self.fields_label_width = int(fields_config.get("label_width", 120))
        self.fields_column_gap = int(fields_config.get("column_gap", 40))

        output_config = dialog_config.get("output", {})
        self.output_section_title = str(
            output_config.get("section_title", "Highlights composition settings")
        )
        self.output_max_per_phase_label = str(
            output_config.get("max_per_phase_label", "Max per phase")
        )
        self.output_max_per_move_label = str(
            output_config.get("max_per_move_label", "Max per move")
        )
        self.output_cross_phase_penalty_label = str(
            output_config.get("cross_phase_penalty_label", "Priority penalty")
        )
        self.output_cross_phase_min_label = str(
            output_config.get("cross_phase_min_label", "Min. highlights")
        )

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

        filter_row = QHBoxLayout()
        filter_row.setSpacing(self.layout_spacing)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.filter_placeholder)
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumHeight(self.filter_min_height)
        self.filter_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.filter_edit)
        main_layout.addLayout(filter_row)

        self.status_label = QLabel()
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        self.table = _ReorderableRulesTable(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Enabled", "Category", "Rule", "Priority", "Open", "Middle", "End"]
        )
        header_tooltips = {
            self.COL_ENABLED: "Enable or disable the rule",
            self.COL_CATEGORY: "Rule category",
            self.COL_RULE: "Highlight rule",
            self.COL_PRIORITY: "Effective priority (higher is preferred)",
            self.COL_OPENING: "Allow in Opening",
            self.COL_MIDDLEGAME: "Allow in Middlegame",
            self.COL_ENDGAME: "Allow in Endgame",
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
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.COL_ENABLED, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_RULE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_PRIORITY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_OPENING, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_MIDDLEGAME, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_ENDGAME, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_ENABLED, self.table_enabled_width)
        self.table.setColumnWidth(self.COL_CATEGORY, self.table_category_width)
        self.table.setColumnWidth(self.COL_PRIORITY, self.table_priority_width)
        self.table.setColumnWidth(self.COL_OPENING, self.table_phase_width)
        self.table.setColumnWidth(self.COL_MIDDLEGAME, self.table_phase_width)
        self.table.setColumnWidth(self.COL_ENDGAME, self.table_phase_width)

        v_header = self.table.verticalHeader()
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        v_header.setDefaultSectionSize(self.table_row_height)

        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.table, 1)

        main_layout.addSpacing(self.composition_section_top_spacing)
        main_layout.addWidget(self._create_output_section())

        main_layout.addSpacing(self.bottom_button_top_padding)

        button_row = QHBoxLayout()
        button_row.setSpacing(self.button_spacing)

        self.restore_button = QPushButton("Restore Defaults")
        self.restore_button.clicked.connect(self._restore_defaults)
        button_row.addWidget(self.restore_button)

        self.toggle_filtered_button = QPushButton("Enable/Disable Filtered")
        self.toggle_filtered_button.setToolTip(
            "Enable all visible rules if any are off; otherwise disable all visible rules"
        )
        self.toggle_filtered_button.clicked.connect(self._toggle_filtered_enabled)
        button_row.addWidget(self.toggle_filtered_button)

        button_row.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        self.ok_button = QPushButton("Save")
        self.ok_button.clicked.connect(self._on_ok)
        self.ok_button.setDefault(True)
        button_row.addWidget(self.ok_button)
        main_layout.addLayout(button_row)

        self.filter_edit.setFocus()

    def _create_output_section(self) -> QWidget:
        """Composition numerics: limits column | cross-phase column (right-aligned)."""
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        outer = QVBoxLayout(section)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.output_heading = QLabel(self.output_section_title)
        outer.addWidget(self.output_heading)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(self.fields_column_gap)
        columns.setAlignment(Qt.AlignmentFlag.AlignTop)

        limits = QVBoxLayout()
        limits.setContentsMargins(0, 0, 0, 0)
        limits.setSpacing(self.fields_row_spacing)
        limits.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.max_per_phase_spin = self._make_spin(1, 50)
        self.max_per_phase_spin.setToolTip(
            "Maximum number of highlights kept in Opening, Middlegame, and Endgame"
        )
        limits.addLayout(
            self._labeled_spin(self.output_max_per_phase_label, self.max_per_phase_spin)
        )

        self.max_per_move_spin = self._make_spin(1, 5)
        self.max_per_move_spin.setToolTip(
            "When several rules fire on the same half-move, keep at most this many"
        )
        limits.addLayout(
            self._labeled_spin(self.output_max_per_move_label, self.max_per_move_spin)
        )
        columns.addLayout(limits, 0)

        cross_phase = QVBoxLayout()
        cross_phase.setContentsMargins(0, 0, 0, 0)
        cross_phase.setSpacing(self.fields_row_spacing)
        cross_phase.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cross_phase_penalty_spin = self._make_spin(0, 50)
        self.cross_phase_penalty_spin.setToolTip(
            "Priority subtracted when a similar highlight already appeared in an earlier "
            "phase. Set to 0 to disable cross-phase down-ranking."
        )
        cross_phase.addLayout(
            self._labeled_spin(
                self.output_cross_phase_penalty_label,
                self.cross_phase_penalty_spin,
            )
        )

        self.cross_phase_min_spin = self._make_spin(0, 50)
        self.cross_phase_min_spin.setToolTip(
            "Only apply the priority penalty when the phase already has at least this "
            "many highlights"
        )
        cross_phase.addLayout(
            self._labeled_spin(
                self.output_cross_phase_min_label,
                self.cross_phase_min_spin,
            )
        )
        columns.addLayout(cross_phase, 0)
        columns.addStretch(1)

        outer.addLayout(columns)
        return section

    def _make_spin(self, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin.setFixedWidth(self.fields_input_width)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return spin

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedWidth(self.fields_label_width)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._output_field_labels.append(label)
        return label

    def _labeled_spin(self, text: str, spin: QSpinBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)
        label = self._field_label(text)
        row.addWidget(label)
        row.addWidget(spin)
        return row

    def _apply_styling(self) -> None:
        bg = [int(self.bg_color[0]), int(self.bg_color[1]), int(self.bg_color[2])]
        border = [
            int(self.button_border_color[0]),
            int(self.button_border_color[1]),
            int(self.button_border_color[2]),
        ]

        StyleManager.style_buttons(
            [self.restore_button, self.toggle_filtered_button],
            self.config,
            bg,
            border,
            min_width=self.action_button_width,
            min_height=self.button_height,
        )
        # Longer label needs a bit more width than Restore Defaults
        self.toggle_filtered_button.setMinimumWidth(
            max(self.action_button_width, 170)
        )
        StyleManager.style_buttons(
            [self.cancel_button, self.ok_button],
            self.config,
            bg,
            border,
            min_width=self.button_width,
            min_height=self.button_height,
        )

        StyleManager.style_line_edits(
            [self.filter_edit],
            self.config,
            text_color=self.input_text_color,
            font_family=self.input_font_family,
            font_size=self.input_font_size,
            bg_color=self.input_bg_color,
            border_color=self.input_border_color,
            focus_border_color=self.input_focus_border_color,
            border_radius=self.input_border_radius,
            padding=self.input_padding
            if isinstance(self.input_padding, list)
            else [8, 6],
        )

        self.status_label.setStyleSheet(
            f"color: rgb({self.status_text_color[0]}, {self.status_text_color[1]}, {self.status_text_color[2]});"
            f"font-family: '{self.label_font_family}';"
            f"font-size: {self.status_font_size}pt;"
        )

        self._apply_output_styling()

        header_border = (
            f"border: none; border-bottom: 1px solid rgb({self.table_border_color[0]}, {self.table_border_color[1]}, {self.table_border_color[2]});"
            if self.table_header_section_border
            else "border: none;"
        )
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
            # Match full-row hover chrome from RowHoverTableWidget. Without this,
            # Windows paints a native per-cell mouse-over that only the cell under
            # the cursor receives, so that cell looks differently highlighted.
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

    def _apply_output_styling(self) -> None:
        fields_config = self.fields_config
        text_color = fields_config.get("text_color", self.text_color)
        font_size = scale_font_size(fields_config.get("font_size", self.font_size))
        label_style = (
            f"QLabel {{"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"font-family: '{self.label_font_family}';"
            f"background-color: transparent;"
            f"}}"
        )
        heading_style = (
            f"QLabel {{"
            f"color: rgb({self.text_color[0]}, {self.text_color[1]}, {self.text_color[2]});"
            f"font-size: {self.font_size}pt;"
            f"font-family: '{self.label_font_family}';"
            f"font-weight: 600;"
            f"background-color: transparent;"
            f"}}"
        )
        self.output_heading.setStyleSheet(heading_style)
        for label in self._output_field_labels:
            label.setStyleSheet(label_style)

        spinboxes = [
            self.max_per_phase_spin,
            self.max_per_move_spin,
            self.cross_phase_penalty_spin,
            self.cross_phase_min_spin,
        ]
        StyleManager.style_spinboxes(
            spinboxes,
            self.config,
            text_color=self.input_text_color,
            font_family=self.input_font_family,
            font_size=self.input_font_size,
            bg_color=self.input_bg_color,
            border_color=self.input_border_color,
            focus_border_color=self.input_focus_border_color,
            border_radius=self.input_border_radius,
            padding=self.input_padding
            if isinstance(self.input_padding, list)
            else [8, 6],
            hide_buttons=True,
            minimum_height=26,
            use_unified_defaults=False,
        )

    def _style_table_editors(self) -> None:
        app_root = Path(__file__).resolve().parents[2]
        checkmark_path = app_root / "resources" / "icons" / "checkmark.svg"
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

    def _reload_from_service(self) -> None:
        rules = self.controller.list_rules()
        self._draft = {r.rule_id: r for r in rules}
        self._draft_order = [r.rule_id for r in rules]
        self._apply_composer_settings(self.controller.get_composer_settings())
        self._apply_filter(self.filter_edit.text())

    def _apply_composer_settings(self, settings: HighlightComposerSettings) -> None:
        self._updating_output = True
        self.max_per_phase_spin.setValue(int(settings.max_per_phase))
        self.max_per_move_spin.setValue(int(settings.max_per_move))
        self.cross_phase_penalty_spin.setValue(int(settings.cross_phase_penalty))
        self.cross_phase_min_spin.setValue(
            int(settings.cross_phase_penalty_min_highlights)
        )
        self._updating_output = False

    def _collect_composer_settings(self) -> HighlightComposerSettings:
        penalty = int(self.cross_phase_penalty_spin.value())
        return HighlightComposerSettings(
            max_per_phase=int(self.max_per_phase_spin.value()),
            max_per_move=int(self.max_per_move_spin.value()),
            # Always on; not exposed in the UI
            phase_dedupe_enabled=True,
            # Implicit: down-rank when priority penalty > 0
            cross_phase_penalty_enabled=penalty > 0,
            cross_phase_penalty=penalty,
            cross_phase_penalty_min_highlights=int(
                self.cross_phase_min_spin.value()
            ),
        )

    def _filter_active(self) -> bool:
        return bool((self.filter_edit.text() or "").strip())

    def _can_reorder(self) -> bool:
        return not self._filter_active()

    def _on_filter_changed(self, text: str) -> None:
        self._apply_filter(text)

    def _ordered_draft_rules(self) -> List[EffectiveHighlightRule]:
        rules: List[EffectiveHighlightRule] = []
        for rule_id in self._draft_order:
            rule = self._draft.get(rule_id)
            if rule is not None:
                rules.append(rule)
        return rules

    def _apply_filter(self, text: str) -> None:
        ordered = self._ordered_draft_rules()
        visible = self.controller.filter_rules(ordered, text)
        self._visible_rule_ids = [r.rule_id for r in visible]
        self._populate_table(visible)
        self._update_drag_mode()
        self.toggle_filtered_button.setEnabled(bool(self._visible_rule_ids))
        self.status_label.setText(
            self.controller.status_summary(
                visible_count=len(visible),
                total_count=len(self._draft),
                rules=list(self._draft.values()),
                filter_active=self._filter_active(),
            )
        )

    def _toggle_filtered_enabled(self) -> None:
        """Enable all visible rules if any are off; otherwise disable them all."""
        if not self._visible_rule_ids:
            return
        visible_rules = [
            self._draft[rid]
            for rid in self._visible_rule_ids
            if rid in self._draft
        ]
        if not visible_rules:
            return
        enable = not all(r.enabled for r in visible_rules)
        for rule_id in self._visible_rule_ids:
            current = self._draft.get(rule_id)
            if current is None:
                continue
            self._draft[rule_id] = self.controller.with_enabled(current, enable)
        self._apply_filter(self.filter_edit.text())

    def _update_drag_mode(self) -> None:
        if self._can_reorder():
            self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.table.setDragEnabled(True)
        else:
            self.table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
            self.table.setDragEnabled(False)

    def _on_table_selection_changed(self) -> None:
        self.table.refresh_row_chrome()

    def _item_flags(self) -> Qt.ItemFlag:
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        return flags

    def _display_priority_for(self, rule_id: str) -> int:
        """Priority shown in the table for the current draft order."""
        try:
            index = self._draft_order.index(rule_id)
        except ValueError:
            rule = self._draft.get(rule_id)
            return int(rule.default_priority) if rule is not None else 0
        if self._draft_order == self.controller.default_priority_order():
            rule = self._draft.get(rule_id)
            if rule is not None:
                return int(rule.default_priority)
        return self.controller.priority_for_order_index(index)

    def _populate_table(self, rules: List[EffectiveHighlightRule]) -> None:
        self._updating_table = True
        self.table.clear_hover()
        self.table.setRowCount(0)
        self.table.setRowCount(len(rules))
        flags = self._item_flags()

        for row, rule in enumerate(rules):
            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(flags)
            enabled_item.setData(Qt.ItemDataRole.UserRole, rule.rule_id)
            self.table.setItem(row, self.COL_ENABLED, enabled_item)
            enabled_cb = QCheckBox()
            enabled_cb.setChecked(rule.enabled)
            enabled_cb.setToolTip("Enable or disable this highlight rule")
            enabled_cb.toggled.connect(
                lambda checked, rid=rule.rule_id: self._on_enabled_toggled(rid, checked)
            )
            self._center_widget(row, self.COL_ENABLED, enabled_cb)

            cat_item = QTableWidgetItem(rule.category_label)
            cat_item.setFlags(flags)
            cat_item.setData(Qt.ItemDataRole.UserRole, rule.rule_id)
            self.table.setItem(row, self.COL_CATEGORY, cat_item)

            rule_item = QTableWidgetItem(rule.display_name)
            rule_item.setFlags(flags)
            rule_item.setData(Qt.ItemDataRole.UserRole, rule.rule_id)
            tip = rule.description or ""
            if tip:
                rule_item.setToolTip(wrap_tooltip_text(tip))
            self.table.setItem(row, self.COL_RULE, rule_item)

            priority_value = self._display_priority_for(rule.rule_id)
            priority_item = QTableWidgetItem(str(priority_value))
            priority_item.setFlags(flags)
            priority_item.setData(Qt.ItemDataRole.UserRole, rule.rule_id)
            priority_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            priority_item.setToolTip(
                "Higher priority highlights are preferred when limiting per phase"
            )
            self.table.setItem(row, self.COL_PRIORITY, priority_item)

            self._set_phase_checkbox(
                row, self.COL_OPENING, rule, PHASE_OPENING, "Allow in Opening"
            )
            self._set_phase_checkbox(
                row,
                self.COL_MIDDLEGAME,
                rule,
                PHASE_MIDDLEGAME,
                "Allow in Middlegame",
            )
            self._set_phase_checkbox(
                row, self.COL_ENDGAME, rule, PHASE_ENDGAME, "Allow in Endgame"
            )

        self._updating_table = False
        self._style_table_editors()

    def _apply_reordered_visible(self, visible_order: List[str]) -> None:
        """Apply a reordered full list (filter must be inactive)."""
        if self._filter_active():
            return
        # Merge: visible_order is the full list when unfiltered
        known = set(self._draft_order)
        new_order = [rid for rid in visible_order if rid in known]
        for rid in self._draft_order:
            if rid not in new_order:
                new_order.append(rid)
        self._draft_order = new_order
        self._apply_filter(self.filter_edit.text())

    def _center_widget(self, row: int, column: int, widget: QWidget) -> None:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(widget)
        self.table.setCellWidget(row, column, container)
        self.table.track_cell_widget(container)

    def _set_phase_checkbox(
        self,
        row: int,
        column: int,
        rule: EffectiveHighlightRule,
        phase: str,
        tooltip: str,
    ) -> None:
        item = QTableWidgetItem("")
        item.setFlags(self._item_flags())
        item.setData(Qt.ItemDataRole.UserRole, rule.rule_id)
        self.table.setItem(row, column, item)
        cb = QCheckBox()
        applicable = phase in rule.applicable_phases
        cb.setChecked(applicable and phase in rule.phases)
        cb.setEnabled(applicable)
        if applicable:
            cb.setToolTip(tooltip)
        else:
            phase_label = {
                PHASE_OPENING: "opening",
                PHASE_MIDDLEGAME: "middlegame",
                PHASE_ENDGAME: "endgame",
            }.get(phase, phase)
            cb.setToolTip(
                f"Not applicable in the {phase_label} — this rule only runs in: "
                f"{self._format_applicable_phases(rule.applicable_phases)}"
            )
        cb.toggled.connect(
            lambda checked, rid=rule.rule_id, p=phase: self._on_phase_toggled(
                rid, p, checked
            )
        )
        self._center_widget(row, column, cb)

    @staticmethod
    def _format_applicable_phases(phases: Tuple[str, ...]) -> str:
        labels = {
            PHASE_OPENING: "Opening",
            PHASE_MIDDLEGAME: "Middlegame",
            PHASE_ENDGAME: "Endgame",
        }
        return ", ".join(labels.get(p, p) for p in phases)

    def _on_enabled_toggled(self, rule_id: str, checked: bool) -> None:
        if self._updating_table:
            return
        current = self._draft.get(rule_id)
        if current is None:
            return
        self._draft[rule_id] = self.controller.with_enabled(current, checked)
        self._refresh_status_only()

    def _on_phase_toggled(self, rule_id: str, phase: str, checked: bool) -> None:
        if self._updating_table:
            return
        current = self._draft.get(rule_id)
        if current is None:
            return
        updated = self.controller.with_phase(current, phase, checked)
        if updated is current and not checked:
            self._updating_table = True
            self._apply_filter(self.filter_edit.text())
            self._updating_table = False
            return
        self._draft[rule_id] = updated

    def _refresh_status_only(self) -> None:
        visible = self.controller.filter_rules(
            self._ordered_draft_rules(), self.filter_edit.text()
        )
        self.status_label.setText(
            self.controller.status_summary(
                visible_count=len(visible),
                total_count=len(self._draft),
                rules=list(self._draft.values()),
                filter_active=self._filter_active(),
            )
        )

    def _restore_defaults(self) -> None:
        dlg = ConfirmationDialog(
            self.config,
            "Restore default highlight settings",
            (
                "Restore all highlight rules and composition settings to their defaults "
                "(enabled, priority order, phases, and limits)?\n\n"
                "Changes are kept when you click Save."
            ),
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        draft: Dict[str, EffectiveHighlightRule] = {}
        for meta in list_builtin_rules():
            category = get_category(meta.category_id)
            draft[meta.id] = EffectiveHighlightRule(
                rule_id=meta.id,
                display_name=meta.display_name,
                description=meta.description,
                category_id=meta.category_id,
                category_label=category.label if category else meta.category_id,
                enabled=meta.default_enabled,
                priority=meta.default_priority,
                phases=meta.default_phases,
                applicable_phases=meta.applicable_phases,
                default_enabled=meta.default_enabled,
                default_priority=meta.default_priority,
                default_phases=meta.default_phases,
                priority_overridden=False,
            )
        self._draft = draft
        self._draft_order = self.controller.default_priority_order()
        self._apply_composer_settings(self.controller.default_composer_settings())
        self._apply_filter(self.filter_edit.text())

    def _on_ok(self) -> None:
        self.controller.save_rules(
            list(self._draft.values()),
            self._draft_order,
            self._collect_composer_settings(),
        )
        self.accept()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.filter_edit is not None:
            self.filter_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

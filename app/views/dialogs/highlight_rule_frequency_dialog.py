"""Dialog showing highlight-rule hit frequency for the active database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.models.database_model import GameData
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style import StyleManager

HighlightHit = Tuple[GameData, int]  # (game, ref_ply)
OpenHitsCallback = Callable[[str, str, List[HighlightHit]], None]


@dataclass(frozen=True)
class HighlightFrequencyRow:
    """One rule row in the frequency overview."""

    rule_id: str
    display_name: str
    enabled: bool
    games_hit: int
    games_pct: float
    hits: int
    hit_locations: Tuple[HighlightHit, ...]


class HighlightRuleFrequencyDialog(QDialog):
    """Tabular overview of rule frequency; click Hits to open Search Results."""

    COL_RULE = 0
    COL_STATUS = 1
    COL_GAMES = 2
    COL_PCT = 3
    COL_HITS = 4

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        db_label: str,
        scanned: int,
        skipped: int,
        total_highlights: int,
        rows: Sequence[HighlightFrequencyRow],
        source_name: str,
        on_open_hits: Optional[OpenHitsCallback] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._rows = list(rows)
        self._source_name = source_name
        self._on_open_hits = on_open_hits
        self._load_config()

        self.setWindowTitle(self.window_title)
        self.setMinimumSize(self.dialog_minimum_width, self.dialog_minimum_height)
        self.resize(self.dialog_width, self.dialog_height)

        self._setup_ui(db_label, scanned, skipped, total_highlights)
        self._apply_styling()
        self._populate_table()

    def _load_config(self) -> None:
        dialog_config = (
            self.config.get("ui", {})
            .get("dialogs", {})
            .get("highlight_rule_frequency", {})
        )
        # Fall back to manage-rules styling when no dedicated config exists.
        fallback = (
            self.config.get("ui", {})
            .get("dialogs", {})
            .get("manage_game_highlight_rules", {})
        )
        merged = {**fallback, **dialog_config}

        self.window_title = str(
            dialog_config.get("window_title", "Highlight Rule Frequency")
        )
        self.dialog_width = int(dialog_config.get("width", merged.get("width", 780)))
        self.dialog_height = int(dialog_config.get("height", merged.get("height", 560)))
        self.dialog_minimum_width = int(
            dialog_config.get("minimum_width", merged.get("minimum_width", 720))
        )
        self.dialog_minimum_height = int(
            dialog_config.get("minimum_height", merged.get("minimum_height", 480))
        )
        self.bottom_button_top_padding = int(
            dialog_config.get(
                "bottom_button_top_padding",
                merged.get("bottom_button_top_padding", 50),
            )
        )

        self.bg_color = merged.get("background_color", [40, 40, 45])
        self.border_color = merged.get("border_color", [60, 60, 65])
        self.text_color = merged.get("text_color", [200, 200, 200])
        self.muted_text_color = dialog_config.get(
            "muted_text_color", [150, 150, 155]
        )
        self.link_color = dialog_config.get("link_color", [150, 180, 255])
        self.font_size = scale_font_size(merged.get("font_size", 11))
        labels_config = merged.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )

        layout_config = merged.get("layout", {})
        self.layout_spacing = int(layout_config.get("spacing", 10))
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])

        table_config = merged.get("table", {})
        self.table_bg_color = table_config.get("background_color", [35, 35, 40])
        self.table_alternate_bg = table_config.get(
            "alternate_background_color", [42, 42, 48]
        )
        self.table_text_color = table_config.get("text_color", self.text_color)
        self.table_border_color = table_config.get("border_color", self.border_color)
        self.table_border_radius = int(table_config.get("border_radius", 4))
        self.table_item_padding = int(table_config.get("item_padding", 6))
        self.table_selection_bg = table_config.get(
            "selection_background_color", [60, 90, 140]
        )
        self.table_selection_text = table_config.get(
            "selection_text_color", [240, 240, 240]
        )
        self.table_header_bg = table_config.get("header_background_color", [50, 50, 55])
        self.table_header_text = table_config.get("header_text_color", [220, 220, 220])
        self.table_header_padding = int(table_config.get("header_padding", 6))
        self.table_header_section_border = bool(
            table_config.get("header_section_border", True)
        )

        buttons_config = merged.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 100))
        self.button_height = int(buttons_config.get("height", 28))
        self.input_bg_color = merged.get("input_background_color", [50, 50, 55])
        self.input_border_color = merged.get("input_border_color", self.border_color)

    def _setup_ui(
        self,
        db_label: str,
        scanned: int,
        skipped: int,
        total_highlights: int,
    ) -> None:
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(self.bg_color[0], self.bg_color[1], self.bg_color[2]),
        )
        self.setPalette(palette)

        layout = QVBoxLayout(self)
        layout.setSpacing(self.layout_spacing)
        layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3],
        )

        skipped_bit = f", {skipped} skipped" if skipped else ""
        summary = (
            f"Database: {db_label}  ·  Scanned {scanned} analyzed game(s)"
            f"{skipped_bit}  ·  {total_highlights} highlight hits\n"
            "Click a Hits value to open those positions in Search Results."
        )
        self.summary_label = QLabel(summary)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Rule", "Status", "Games", "Games %", "Hits"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.cellClicked.connect(self._on_cell_clicked)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.COL_RULE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_GAMES, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_PCT, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_HITS, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, stretch=1)

        layout.addSpacing(self.bottom_button_top_padding)
        button_row = QHBoxLayout()
        button_row.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setFixedSize(self.button_width, self.button_height)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

    def _apply_styling(self) -> None:
        label_style = (
            f"QLabel {{"
            f"color: rgb({self.text_color[0]}, {self.text_color[1]}, {self.text_color[2]});"
            f"font-family: '{self.label_font_family}';"
            f"font-size: {self.font_size}pt;"
            f"background-color: transparent;"
            f"}}"
        )
        self.summary_label.setStyleSheet(label_style)

        header_border = (
            f"border: none; border-bottom: 1px solid "
            f"rgb({self.table_border_color[0]}, {self.table_border_color[1]}, "
            f"{self.table_border_color[2]});"
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
            f"QTableWidget::item:selected {{"
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
        self.table.setStyleSheet(table_style)
        StyleManager.style_table_scrollbar(
            self.table,
            self.config,
            self.input_bg_color,
            self.input_border_color,
            table_style,
        )
        StyleManager.style_buttons(
            [self.close_button],
            self.config,
            self.bg_color,
            self.border_color,
            self.text_color,
        )

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            rule_item = QTableWidgetItem(f"{row.display_name} ({row.rule_id})")
            rule_item.setData(Qt.ItemDataRole.UserRole, row.rule_id)
            self.table.setItem(row_index, self.COL_RULE, rule_item)

            status_item = QTableWidgetItem("enabled" if row.enabled else "disabled")
            if not row.enabled:
                status_item.setForeground(
                    QColor(
                        self.muted_text_color[0],
                        self.muted_text_color[1],
                        self.muted_text_color[2],
                    )
                )
            self.table.setItem(row_index, self.COL_STATUS, status_item)

            games_item = QTableWidgetItem(str(row.games_hit))
            games_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row_index, self.COL_GAMES, games_item)

            pct_item = QTableWidgetItem(f"{row.games_pct:.2f}%")
            pct_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row_index, self.COL_PCT, pct_item)

            hits_item = QTableWidgetItem(str(row.hits))
            hits_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            hits_item.setData(Qt.ItemDataRole.UserRole, row.rule_id)
            hits_item.setData(Qt.ItemDataRole.UserRole + 1, list(row.hit_locations))
            if row.hits > 0:
                hits_item.setForeground(
                    QColor(self.link_color[0], self.link_color[1], self.link_color[2])
                )
                font = QFont(hits_item.font())
                font.setUnderline(True)
                hits_item.setFont(font)
                hits_item.setToolTip("Open these positions in Search Results")
            self.table.setItem(row_index, self.COL_HITS, hits_item)

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column != self.COL_HITS or self._on_open_hits is None:
            return
        hits_item = self.table.item(row, self.COL_HITS)
        if hits_item is None:
            return
        rule_id = hits_item.data(Qt.ItemDataRole.UserRole)
        locations = hits_item.data(Qt.ItemDataRole.UserRole + 1) or []
        if not rule_id or not locations:
            return
        self.accept()
        self._on_open_hits(str(rule_id), self._source_name, list(locations))

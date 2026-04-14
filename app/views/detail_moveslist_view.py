"""Moves List view for detail panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableView, QStyledItemDelegate, QMenu, QApplication, QDialog
from PyQt6.QtCore import Qt, QModelIndex, QTimer, QPoint
from PyQt6.QtGui import QPalette, QColor, QBrush, QAction, QKeySequence, QFont
from typing import Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.controllers.database_controller import DatabaseController

from app.utils.table_export import table_to_delimited, get_visual_column_indices, get_copy_table_config
from app.utils.font_utils import resolve_font_family, scale_font_size

from app.models.moveslist_model import MovesListModel
from app.models.game_model import GameModel
from app.controllers.game_controller import GameController
from app.controllers.column_profile_controller import ColumnProfileController
from app.models.column_profile_model import (COL_NUM, COL_WHITE, COL_BLACK, COL_EVAL_WHITE, COL_EVAL_BLACK, 
                                             COL_CPL_WHITE, COL_CPL_BLACK, COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3,
                                             COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_BEST_WHITE, 
                                             COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3, COL_BEST_BLACK_2, COL_BEST_BLACK_3,
                                             COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3, COL_WHITE_DEPTH, COL_BLACK_DEPTH,
                                             COL_WHITE_SELDEPTH, COL_BLACK_SELDEPTH,
                                             COL_ECO, COL_OPENING, COL_COMMENT, COL_WHITE_CAPTURE, COL_BLACK_CAPTURE,
                                             COL_WHITE_MATERIAL, COL_BLACK_MATERIAL, COL_FEN_WHITE, COL_FEN_BLACK)


class DetailMovesListView(QWidget):
    """Moves list view displaying chess moves in a table."""
    
    def __init__(self, config: Dict[str, Any], moveslist_model: Optional[MovesListModel] = None,
                 game_model: Optional[GameModel] = None, game_controller: Optional[GameController] = None) -> None:
        """Initialize the moves list view.
        
        Args:
            config: Configuration dictionary.
            moveslist_model: Optional MovesListModel to observe.
                           If provided, view will automatically update when model changes.
            game_model: Optional GameModel to observe for active move changes.
            game_controller: Optional GameController for navigating to specific plies.
        """
        super().__init__()
        self.config = config
        self._moveslist_model: Optional[MovesListModel] = None
        self._game_model: Optional[GameModel] = None
        self._game_controller: Optional[GameController] = None
        self._database_controller: Optional["DatabaseController"] = None
        self._column_profile_controller: Optional[ColumnProfileController] = None
        self._active_move_ply: int = 0
        self._setup_ui()
        
        # Connect to models if provided
        if moveslist_model:
            self.set_model(moveslist_model)
        
        if game_model:
            self.set_game_model(game_model)
        
        if game_controller:
            self.set_game_controller(game_controller)
    
    def set_database_controller(self, controller: Optional["DatabaseController"]) -> None:
        """Set database controller for persisting PGN edits (update row, mark unsaved)."""
        self._database_controller = controller
    
    def _setup_ui(self) -> None:
        """Setup the moves list UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create table view
        self.moves_table = QTableView()
        self.moves_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.moves_table.customContextMenuRequested.connect(self._on_moves_table_context_menu)
        layout.addWidget(self.moves_table)
        
        # Model will be set via set_model() method
        # Column widths and resize modes will be configured when model is set
        
        # Configure table view appearance for dark theme
        self._configure_table_styling()
    
    def _configure_table_styling(self) -> None:
        """Configure table view styling for dark theme."""
        ui_config = self.config.get('ui', {})
        tabs_config = ui_config.get('panels', {}).get('detail', {}).get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        norm_text = normal.get('text', [200, 200, 200])
        
        # Get table styling from config
        table_config = ui_config.get('panels', {}).get('detail', {}).get('moveslist', {}).get('table', {})
        table_font_family_raw = table_config.get("font_family", "Helvetica Neue")
        table_font_size_raw = table_config.get("font_size", 10)
        header_font_family_raw = table_config.get("header_font_family", table_font_family_raw)
        header_font_size_raw = table_config.get("header_font_size", table_font_size_raw)
        header_bg = table_config.get('header_background_color', [45, 45, 50])
        header_text = table_config.get('header_text_color', [200, 200, 200])
        header_border = table_config.get('header_border_color', [60, 60, 65])
        gridline_color = table_config.get('gridline_color', [60, 60, 65])
        selection_bg = table_config.get('selection_background_color', [70, 90, 130])
        selection_text = table_config.get('selection_text_color', [240, 240, 240])

        # Fonts (apply explicitly so tables don't inherit OS defaults)
        self._table_font = QFont(
            resolve_font_family(table_font_family_raw),
            int(scale_font_size(table_font_size_raw)),
        )
        self._header_font = QFont(
            resolve_font_family(header_font_family_raw),
            int(scale_font_size(header_font_size_raw)),
        )
        self.moves_table.setFont(self._table_font)
        
        header_bg_color = QColor(header_bg[0], header_bg[1], header_bg[2])
        header_text_color = QColor(header_text[0], header_text[1], header_text[2])
        
        stylesheet = f"""
            QTableView {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                gridline-color: rgb({gridline_color[0]}, {gridline_color[1]}, {gridline_color[2]});
                selection-background-color: rgb({selection_bg[0]}, {selection_bg[1]}, {selection_bg[2]});
                selection-color: rgb({selection_text[0]}, {selection_text[1]}, {selection_text[2]});
            }}
            QHeaderView {{
                background-color: rgb({header_bg[0]}, {header_bg[1]}, {header_bg[2]});
            }}
            QHeaderView::section {{
                background-color: rgb({header_bg[0]}, {header_bg[1]}, {header_bg[2]});
                color: rgb({header_text[0]}, {header_text[1]}, {header_text[2]});
                padding: 4px;
                border: 1px solid rgb({header_border[0]}, {header_border[1]}, {header_border[2]});
                font-weight: 500;
            }}
            QTableCornerButton::section {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                border: none;
            }}
        """
        self.moves_table.setStyleSheet(stylesheet)
        
        # Apply scrollbar styling using StyleManager
        from app.views.style import StyleManager
        StyleManager.style_table_view_scrollbar(
            self.moves_table,
            self.config,
            pane_bg,
            gridline_color,
            stylesheet
        )
        
        # Also set palette on header views to prevent macOS override
        horizontal_header = self.moves_table.horizontalHeader()
        if horizontal_header:
            horizontal_header.setFont(self._header_font)
            header_palette = horizontal_header.palette()
            header_palette.setColor(horizontal_header.backgroundRole(), header_bg_color)
            header_palette.setColor(horizontal_header.foregroundRole(), header_text_color)
            horizontal_header.setPalette(header_palette)
            horizontal_header.setAutoFillBackground(True)
        
        # Set palette on vertical header to prevent macOS override
        vertical_header = self.moves_table.verticalHeader()
        if vertical_header:
            vertical_header.setFont(self._header_font)
            vertical_header_palette = vertical_header.palette()
            vertical_header_palette.setColor(vertical_header.backgroundRole(), header_bg_color)
            vertical_header_palette.setColor(vertical_header.foregroundRole(), header_text_color)
            vertical_header.setPalette(vertical_header_palette)
            vertical_header.setAutoFillBackground(True)
        
        # Style corner button widget directly (it's a child widget of the table)
        # The corner button is created by QAbstractScrollArea and can be accessed
        # after the table is shown, but we can style it via stylesheet which should be sufficient
    
    def set_model(self, model: MovesListModel) -> None:
        """Set the moves list model to observe.
        
        Args:
            model: The MovesListModel instance to observe.
        """
        # Disconnect old signals if model was previously set
        if hasattr(self, 'moves_table') and self.moves_table:
            try:
                header = self.moves_table.horizontalHeader()
                header.sectionResized.disconnect(self._on_column_resized)
            except (TypeError, RuntimeError):
                # Signals not connected or already disconnected, ignore
                pass
        
        self._moveslist_model = model
        
        # Set model on table view
        self.moves_table.setModel(model)

        # Some Qt styles reset view/header fonts when a model is attached.
        # Re-apply after setting the model so config-driven fonts always win.
        if hasattr(self, "_table_font"):
            self.moves_table.setFont(self._table_font)
        if hasattr(self, "_header_font"):
            header = self.moves_table.horizontalHeader()
            if header:
                header.setFont(self._header_font)
            vheader = self.moves_table.verticalHeader()
            if vheader:
                vheader.setFont(self._header_font)
        
        # Get header and enable column reordering
        header = self.moves_table.horizontalHeader()
        header.setSectionsMovable(True)  # Enable drag and drop column reordering
        
        # Connect to header resize events to save column widths
        header.sectionResized.connect(self._on_column_resized)

        # Configure column widths and resize modes based on visible columns
        self._apply_column_order_and_widths()
        
        # Enable word wrapping for the Comment column to show full text without truncation
        class CommentColumnDelegate(QStyledItemDelegate):
            """Delegate for Comment column that formats text for display."""
            def paint(self, painter, option, index):
                # Disable text elision (no "..." truncation)
                # This allows the full text to be displayed, wrapping naturally
                option.textElideMode = Qt.TextElideMode.ElideNone
                super().paint(painter, option, index)
            
            def displayText(self, value, locale):
                """Format comment text for display by replacing newlines with spaces.
                
                This is presentation logic (formatting for display) and belongs in the view layer.
                """
                if value is None:
                    return ""
                # Replace newlines with spaces for display purposes
                # This prevents newlines from breaking the text flow in the table cell
                text = str(value)
                return text.replace('\n', ' ').replace('\r', ' ')
        
        # Set delegate for Comment column to handle formatting (if visible)
        comment_column = model.COL_COMMENT
        column_mapping = model.get_column_index_mapping()
        if comment_column in column_mapping:
            comment_visible = column_mapping[comment_column]
            self.moves_table.setItemDelegateForColumn(comment_visible, CommentColumnDelegate())
        
        # Enable word wrapping in the table view so text wraps within column width
        self.moves_table.setWordWrap(True)
        
        # Connect click / double-click handlers
        self.moves_table.clicked.connect(self._on_table_clicked)
        try:
            self.moves_table.doubleClicked.disconnect(self._on_table_double_clicked)
        except (TypeError, RuntimeError):
            pass
        self.moves_table.doubleClicked.connect(self._on_table_double_clicked)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe for active move changes.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            try:
                self._game_model.metadata_updated.disconnect(self._on_metadata_updated_refresh_moves)
            except (TypeError, RuntimeError):
                pass
        
        self._game_model = model
        
        # Connect to model signals
        model.active_move_changed.connect(self._on_active_move_changed)
        model.metadata_updated.connect(self._on_metadata_updated_refresh_moves)
        
        # Set highlight color in moves list model if available
        if self._moveslist_model:
            highlight_color = self._get_active_move_highlight_color()
            self._moveslist_model.set_highlight_color(highlight_color)
        
        # Initialize with current active move if any
        self._on_active_move_changed(model.get_active_move_ply())
    
    def _on_metadata_updated_refresh_moves(self) -> None:
        """Rebuild moves list when PGN changed (e.g. comments, headers)."""
        if (
            not self._game_model
            or not self._game_model.active_game
            or not self._game_controller
            or not self._moveslist_model
        ):
            return
        game = self._game_model.active_game
        current_ply = self._game_model.get_active_move_ply()
        moves = self._game_controller.extract_moves_from_game(game)
        self._moveslist_model.clear()
        for move in moves:
            self._moveslist_model.add_move(move)
        self._moveslist_model.set_active_move_ply(current_ply)
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from model.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        self._active_move_ply = ply_index
        
        # Update model with active move ply for highlighting
        if self._moveslist_model:
            self._moveslist_model.set_active_move_ply(ply_index)
            
            # Calculate which row to highlight based on ply_index
            # ply_index = 0: no row (starting position)
            # ply_index = 1: row 0, white move (move 1)
            # ply_index = 2: row 0, black move (move 1)
            # ply_index = 3: row 1, white move (move 2)
            # ply_index = 4: row 1, black move (move 2)
            # etc.
            
            if ply_index > 0:
                # Convert ply_index to row index (0-based)
                # Row = (ply_index - 1) // 2
                row_index = (ply_index - 1) // 2
                
                if 0 <= row_index < self._moveslist_model.rowCount():
                    # Scroll to the active row (use first visible column)
                    visible_col = 0
                    if self._moveslist_model.columnCount() > 0:
                        self.moves_table.scrollTo(
                            self._moveslist_model.index(row_index, visible_col),
                            QTableView.ScrollHint.EnsureVisible
                        )
    
    def _get_active_move_highlight_color(self) -> QColor:
        """Get the highlight color for active move from config.
        
        Returns:
            QColor for active move highlight.
        """
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        moveslist_config = panel_config.get('moveslist', {})
        active_config = moveslist_config.get('table', {}).get('active_move', {})
        bg_color = active_config.get('background_color', [100, 120, 180])
        return QColor(bg_color[0], bg_color[1], bg_color[2])
    
    def set_game_controller(self, controller: GameController) -> None:
        """Set the game controller for navigating to specific plies.
        
        Args:
            controller: The GameController instance.
        """
        self._game_controller = controller
    
    def _on_table_clicked(self, index: QModelIndex) -> None:
        """Handle click on table cell.
        
        Args:
            index: Model index of the clicked cell.
        """
        if not index.isValid() or not self._game_model:
            return
        
        # Since all columns are always present in the model, index.column() is already the logical column index
        logical_col = index.column()
        
        # Only handle clicks on the move number column (#)
        if logical_col == MovesListModel.COL_NUM:
            row = index.row()
            
            # Get move number from the model
            if self._moveslist_model:
                move_data = self._moveslist_model.get_move(row)
                if move_data:
                    move_number = move_data.move_number
                    
                    # Calculate ply index for white to play after this move
                    # Move number N corresponds to ply index = (N-1)*2 + 1
                    # Example: Move 1 -> ply 1 (after white's move), Move 2 -> ply 3 (after white's move)
                    ply_index = (move_number - 1) * 2 + 1
                    
                    # Navigate to this ply using the game controller (updates board position)
                    if self._game_controller:
                        self._game_controller.navigate_to_ply(ply_index)
                    else:
                        # Fallback: just set active move in model (board won't update)
                        self._game_model.set_active_move_ply(ply_index)
    
    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        """Open comment editor when double-clicking the Comment column."""
        if not index.isValid() or not self._game_model or not self._game_model.active_game:
            return
        if not self._moveslist_model or not self._game_controller:
            return
        logical_col = index.column()
        if logical_col != MovesListModel.COL_COMMENT:
            return
        self._open_move_comment_editor(index.row())
    
    def open_move_comment_editor(self, row_index: int) -> None:
        """Open the move-comment dialog for ``row_index`` (moves list row)."""
        self._open_move_comment_editor(row_index)
    
    def _open_move_comment_editor(self, row_index: int) -> None:
        """Edit main-line comments for the given moves-list row."""
        if not self._game_model or not self._game_model.active_game or not self._game_controller:
            return
        game = self._game_model.active_game
        read_result = self._game_controller.read_mainline_move_comments(game, row_index)
        if read_result is None:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Comments",
                "Could not read comments for this row.",
                self,
            )
            return
        white_c, black_c, has_black = read_result
        move_data = self._moveslist_model.get_move(row_index)
        white_san = (move_data.white_move or "").strip() if move_data else ""
        black_san = (move_data.black_move or "").strip() if move_data else ""
        from app.views.dialogs.move_comment_dialog import MoveCommentDialog
        
        dlg = MoveCommentDialog(
            self.config,
            row_index + 1,
            white_san,
            black_san,
            white_c,
            black_c,
            has_black,
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_w, new_b = dlg.get_comments()
        ok, err = self._game_controller.apply_mainline_move_comments(
            game, row_index, new_w, new_b
        )
        if not ok:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Comments", err, self)
            return
        if self._database_controller:
            db_model = self._database_controller.find_database_model_for_game(game)
            if db_model:
                db_model.update_game(game)
                self._database_controller.mark_database_unsaved(db_model)
        self._game_model.metadata_updated.emit()

    def _on_moves_table_context_menu(self, pos: QPoint) -> None:
        """Show context menu for copy actions at the cell under the cursor."""
        from app.views.style import StyleManager

        index = self.moves_table.indexAt(pos)
        model = self._moveslist_model
        if not model:
            return

        menu = QMenu(self)
        StyleManager.style_context_menu(menu, self.config)

        if self._column_profile_controller:
            profile_menu = menu.addMenu("Column profile")
            StyleManager.style_context_menu(profile_menu, self.config)
            active_name = self._column_profile_controller.get_active_profile_name()
            for profile_idx, pname in enumerate(self._column_profile_controller.get_profile_names()):
                pa = QAction(pname, profile_menu)
                pa.setCheckable(True)
                pa.setChecked(pname == active_name)
                if profile_idx < 9:
                    pa.setShortcut(QKeySequence(str(profile_idx + 1)))
                pa.triggered.connect(lambda _checked=False, n=pname: self._on_context_profile_chosen(n))
                profile_menu.addAction(pa)
            menu.addSeparator()

        copy_value_action = menu.addAction("Copy value")
        copy_value_action.triggered.connect(lambda: self._copy_cell_value(index))
        copy_value_action.setEnabled(index.isValid())

        if index.isValid() and index.column() == MovesListModel.COL_COMMENT:
            edit_comments_action = menu.addAction("Edit Comments")
            can_edit_comments = (
                self._game_model is not None
                and self._game_model.active_game is not None
                and self._game_controller is not None
            )
            edit_comments_action.setEnabled(can_edit_comments)
            row = index.row()
            edit_comments_action.triggered.connect(
                lambda _checked=False, r=row: self._open_move_comment_editor(r)
            )

        menu.addSeparator()
        menu.addAction("Copy Table as CSV (Visual Columns)").triggered.connect(self._copy_table_csv_visual)
        menu.addAction("Copy Table as CSV (All Columns)").triggered.connect(self._copy_table_csv_all)
        menu.addAction("Copy Table as TSV (Visual Columns)").triggered.connect(self._copy_table_tsv_visual)
        menu.addAction("Copy Table as TSV (All Columns)").triggered.connect(self._copy_table_tsv_all)

        from app.views.style.context_menu import try_wire_context_menu_shared_action_icons

        try_wire_context_menu_shared_action_icons(menu)
        menu.exec(self.moves_table.viewport().mapToGlobal(pos))

    def _copy_cell_value(self, index: QModelIndex) -> None:
        """Copy the display value of the cell at index to the clipboard."""
        if not index.isValid() or not self._moveslist_model:
            return
        val = self._moveslist_model.data(index, Qt.ItemDataRole.DisplayRole)
        text = "" if val is None else str(val)
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        from app.services.progress_service import ProgressService
        ProgressService.get_instance().set_status("Copied value to clipboard")

    def _get_visual_column_indices(self) -> List[int]:
        """Return model column indices in current visual order (visible columns only)."""
        if not self._moveslist_model:
            return []
        return get_visual_column_indices(self.moves_table.horizontalHeader())

    def _get_copy_table_config(self) -> Dict[str, Any]:
        """Return copy_table config (csv/tsv delimiter, use_escaping, always_quote_values) from config with defaults."""
        return get_copy_table_config(self.config)

    def _copy_table_csv_visual(self) -> None:
        cfg = self._get_copy_table_config()["csv"]
        self._copy_table_delimited(
            visual_columns=True,
            delimiter=cfg["delimiter"],
            use_csv_escaping=cfg["use_escaping"],
            always_quote_values=cfg["always_quote_values"],
            status_message="Copied table as CSV (visual columns) to clipboard",
        )

    def _copy_table_csv_all(self) -> None:
        cfg = self._get_copy_table_config()["csv"]
        self._copy_table_delimited(
            visual_columns=False,
            delimiter=cfg["delimiter"],
            use_csv_escaping=cfg["use_escaping"],
            always_quote_values=cfg["always_quote_values"],
            status_message="Copied table as CSV (all columns) to clipboard",
        )

    def _copy_table_tsv_visual(self) -> None:
        cfg = self._get_copy_table_config()["tsv"]
        self._copy_table_delimited(
            visual_columns=True,
            delimiter=cfg["delimiter"],
            use_csv_escaping=cfg["use_escaping"],
            always_quote_values=cfg["always_quote_values"],
            status_message="Copied table as TSV (visual columns) to clipboard",
        )

    def _copy_table_tsv_all(self) -> None:
        cfg = self._get_copy_table_config()["tsv"]
        self._copy_table_delimited(
            visual_columns=False,
            delimiter=cfg["delimiter"],
            use_csv_escaping=cfg["use_escaping"],
            always_quote_values=cfg["always_quote_values"],
            status_message="Copied table as TSV (all columns) to clipboard",
        )

    def _copy_table_delimited(
        self,
        visual_columns: bool,
        delimiter: str,
        use_csv_escaping: bool,
        always_quote_values: bool = False,
        status_message: str = "Copied table to clipboard",
    ) -> None:
        """Copy table to clipboard as delimited text. View only orchestrates; formatting in util."""
        if not self._moveslist_model:
            return
        if visual_columns:
            column_indices = self._get_visual_column_indices()
        else:
            column_indices = list(range(self._moveslist_model.columnCount()))
        text = table_to_delimited(
            self._moveslist_model,
            column_indices,
            delimiter,
            use_csv_escaping,
            always_quote_values=always_quote_values,
        )
        QApplication.clipboard().setText(text)
        from app.services.progress_service import ProgressService
        ProgressService.get_instance().set_status(status_message)

    def set_column_profile_controller(self, controller: Optional[ColumnProfileController]) -> None:
        """Wire column profile updates through ``ColumnProfileController`` only (no direct model access)."""
        if self._column_profile_controller and self._column_profile_controller is not controller:
            self._column_profile_controller.detach_moves_list_view_profile_signals(
                self._on_column_visibility_changed,
                self._on_active_profile_changed,
            )

        self._column_profile_controller = controller

        if controller:
            controller.attach_moves_list_view_profile_signals(
                self._on_column_visibility_changed,
                self._on_active_profile_changed,
            )
            from PyQt6.QtCore import QTimer

            def apply_initial_settings() -> None:
                self._apply_column_visibility()
                self._apply_column_order_and_widths()

            QTimer.singleShot(0, apply_initial_settings)

    def _on_context_profile_chosen(self, profile_name: str) -> None:
        if not self._column_profile_controller:
            return
        ok = self._column_profile_controller.set_active_profile(profile_name)
        if ok:
            from app.services.progress_service import ProgressService

            ProgressService.get_instance().set_status(f"Profile '{profile_name}' activated")
    
    def _on_column_visibility_changed(self, column_name: str, visible: bool) -> None:
        """Handle column visibility change from profile model.
        
        Args:
            column_name: Name of the column.
            visible: True if column is visible, False otherwise.
        """
        # Update moves list model column visibility tracking
        if self._moveslist_model and self._column_profile_controller:
            column_visibility = self._column_profile_controller.get_column_visibility()
            self._moveslist_model.set_column_visibility(column_visibility)
        
        # Apply visibility changes to the view using hideSection/showSection
        self._apply_column_visibility()
        
        # Reapply column widths when visibility changes (preserve current order)
        # Use a small delay to ensure the model has updated
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(10, lambda: self._apply_column_widths_only())
    
    def _on_active_profile_changed(self, profile_name: str) -> None:
        """Handle active profile change from profile model.
        
        Args:
            profile_name: Name of the new active profile.
        """
        # When switching profiles, we don't save the current profile's state
        # The user must explicitly save using "Save Profile" if they want to persist changes
        
        # Update moves list model column visibility when profile changes
        # Use a small delay to ensure the profile model has fully updated
        if self._moveslist_model and self._column_profile_controller:
            from PyQt6.QtCore import QTimer
            def update_visibility():
                column_visibility = self._column_profile_controller.get_column_visibility()
                self._moveslist_model.set_column_visibility(column_visibility)
                self._apply_column_visibility()
                self._apply_column_order_and_widths()
            QTimer.singleShot(10, update_visibility)
        else:
            self._apply_column_visibility()
            self._apply_column_order_and_widths()
    
    def _apply_column_visibility(self) -> None:
        """Apply column visibility using hideSection/showSection."""
        if not self._moveslist_model or not self._column_profile_controller:
            return
        
        header = self.moves_table.horizontalHeader()
        column_visibility = self._column_profile_controller.get_column_visibility()
        
        # Map column names to logical indices
        from app.models.moveslist_model import MovesListModel
        logical_to_name = {
            MovesListModel.COL_NUM: COL_NUM,
            MovesListModel.COL_WHITE: COL_WHITE,
            MovesListModel.COL_BLACK: COL_BLACK,
            MovesListModel.COL_EVAL_WHITE: COL_EVAL_WHITE,
            MovesListModel.COL_EVAL_BLACK: COL_EVAL_BLACK,
            MovesListModel.COL_CPL_WHITE: COL_CPL_WHITE,
            MovesListModel.COL_CPL_BLACK: COL_CPL_BLACK,
            MovesListModel.COL_CPL_WHITE_2: COL_CPL_WHITE_2,
            MovesListModel.COL_CPL_WHITE_3: COL_CPL_WHITE_3,
            MovesListModel.COL_CPL_BLACK_2: COL_CPL_BLACK_2,
            MovesListModel.COL_CPL_BLACK_3: COL_CPL_BLACK_3,
            MovesListModel.COL_ASSESS_WHITE: COL_ASSESS_WHITE,
            MovesListModel.COL_ASSESS_BLACK: COL_ASSESS_BLACK,
            MovesListModel.COL_BEST_WHITE: COL_BEST_WHITE,
            MovesListModel.COL_BEST_BLACK: COL_BEST_BLACK,
            MovesListModel.COL_BEST_WHITE_2: COL_BEST_WHITE_2,
            MovesListModel.COL_BEST_WHITE_3: COL_BEST_WHITE_3,
            MovesListModel.COL_BEST_BLACK_2: COL_BEST_BLACK_2,
            MovesListModel.COL_BEST_BLACK_3: COL_BEST_BLACK_3,
            MovesListModel.COL_WHITE_IS_TOP3: COL_WHITE_IS_TOP3,
            MovesListModel.COL_BLACK_IS_TOP3: COL_BLACK_IS_TOP3,
            MovesListModel.COL_WHITE_DEPTH: COL_WHITE_DEPTH,
            MovesListModel.COL_BLACK_DEPTH: COL_BLACK_DEPTH,
            MovesListModel.COL_WHITE_SELDEPTH: COL_WHITE_SELDEPTH,
            MovesListModel.COL_BLACK_SELDEPTH: COL_BLACK_SELDEPTH,
            MovesListModel.COL_ECO: COL_ECO,
            MovesListModel.COL_OPENING: COL_OPENING,
            MovesListModel.COL_COMMENT: COL_COMMENT,
            MovesListModel.COL_WHITE_CAPTURE: COL_WHITE_CAPTURE,
            MovesListModel.COL_BLACK_CAPTURE: COL_BLACK_CAPTURE,
            MovesListModel.COL_WHITE_MATERIAL: COL_WHITE_MATERIAL,
            MovesListModel.COL_BLACK_MATERIAL: COL_BLACK_MATERIAL,
            MovesListModel.COL_FEN_WHITE: COL_FEN_WHITE,
            MovesListModel.COL_FEN_BLACK: COL_FEN_BLACK,
        }
        
        # Apply visibility for all columns
        for logical_idx in range(self._moveslist_model.columnCount()):
            col_name = logical_to_name.get(logical_idx)
            if col_name:
                visible = column_visibility.get(col_name, True)
                if visible:
                    header.showSection(logical_idx)
                else:
                    header.hideSection(logical_idx)
    
    def _apply_column_order_and_widths(self) -> None:
        """Apply column order and widths from profile, then set last column to stretch."""
        if not self._moveslist_model:
            return
        
        if not self._column_profile_controller:
            return
        
        # Apply column order first
        self._apply_column_order()
        
        # Then apply widths
        self._apply_column_widths_only()
    
    def _apply_column_widths_only(self) -> None:
        """Apply column widths from profile and set last column to stretch, preserving current order."""
        if not self._moveslist_model:
            return
        
        if not self._column_profile_controller:
            return
        
        header = self.moves_table.horizontalHeader()
        column_visibility = self._column_profile_controller.get_column_visibility()
        
        # Get widths from profile - must exist in user_settings.json
        column_widths = self._column_profile_controller.get_column_widths()
        
        # Map logical column indices to column names
        logical_to_name = {
            MovesListModel.COL_NUM: COL_NUM,
            MovesListModel.COL_WHITE: COL_WHITE,
            MovesListModel.COL_BLACK: COL_BLACK,
            MovesListModel.COL_EVAL_WHITE: COL_EVAL_WHITE,
            MovesListModel.COL_EVAL_BLACK: COL_EVAL_BLACK,
            MovesListModel.COL_CPL_WHITE: COL_CPL_WHITE,
            MovesListModel.COL_CPL_BLACK: COL_CPL_BLACK,
            MovesListModel.COL_CPL_WHITE_2: COL_CPL_WHITE_2,
            MovesListModel.COL_CPL_WHITE_3: COL_CPL_WHITE_3,
            MovesListModel.COL_CPL_BLACK_2: COL_CPL_BLACK_2,
            MovesListModel.COL_CPL_BLACK_3: COL_CPL_BLACK_3,
            MovesListModel.COL_ASSESS_WHITE: COL_ASSESS_WHITE,
            MovesListModel.COL_ASSESS_BLACK: COL_ASSESS_BLACK,
            MovesListModel.COL_BEST_WHITE: COL_BEST_WHITE,
            MovesListModel.COL_BEST_BLACK: COL_BEST_BLACK,
            MovesListModel.COL_BEST_WHITE_2: COL_BEST_WHITE_2,
            MovesListModel.COL_BEST_WHITE_3: COL_BEST_WHITE_3,
            MovesListModel.COL_BEST_BLACK_2: COL_BEST_BLACK_2,
            MovesListModel.COL_BEST_BLACK_3: COL_BEST_BLACK_3,
            MovesListModel.COL_WHITE_IS_TOP3: COL_WHITE_IS_TOP3,
            MovesListModel.COL_BLACK_IS_TOP3: COL_BLACK_IS_TOP3,
            MovesListModel.COL_WHITE_DEPTH: COL_WHITE_DEPTH,
            MovesListModel.COL_BLACK_DEPTH: COL_BLACK_DEPTH,
            MovesListModel.COL_WHITE_SELDEPTH: COL_WHITE_SELDEPTH,
            MovesListModel.COL_BLACK_SELDEPTH: COL_BLACK_SELDEPTH,
            MovesListModel.COL_ECO: COL_ECO,
            MovesListModel.COL_OPENING: COL_OPENING,
            MovesListModel.COL_COMMENT: COL_COMMENT,
            MovesListModel.COL_WHITE_CAPTURE: COL_WHITE_CAPTURE,
            MovesListModel.COL_BLACK_CAPTURE: COL_BLACK_CAPTURE,
            MovesListModel.COL_WHITE_MATERIAL: COL_WHITE_MATERIAL,
            MovesListModel.COL_BLACK_MATERIAL: COL_BLACK_MATERIAL,
            MovesListModel.COL_FEN_WHITE: COL_FEN_WHITE,
            MovesListModel.COL_FEN_BLACK: COL_FEN_BLACK,
        }
        
        # Set widths for all columns (including hidden ones)
        for logical_idx in range(self._moveslist_model.columnCount()):
            col_name = logical_to_name.get(logical_idx)
            if not col_name:
                continue
            
            # Get width from profile
            if col_name not in column_widths:
                raise RuntimeError(
                    f"Column width missing for '{col_name}' in user_settings.json. "
                    f"Please add 'width' to the column configuration in the active profile."
                )
            width = column_widths[col_name]
            
            # Set width for this column (logical index)
            header.setSectionResizeMode(logical_idx, header.ResizeMode.Interactive)
            header.resizeSection(logical_idx, width)
        
        # Find the last visible column by visual index (after reordering)
        # This ensures the correct column stretches regardless of column order
        last_visible_logical_idx = None
        column_count = header.count()
        for visual_idx in range(column_count - 1, -1, -1):  # Iterate backwards from last visual position
            logical_idx = header.logicalIndex(visual_idx)
            if logical_idx == -1:
                continue
            col_name = logical_to_name.get(logical_idx)
            if col_name and column_visibility.get(col_name, True):
                last_visible_logical_idx = logical_idx
                break
        
        # Last visible column always stretches to fill remaining space
        if last_visible_logical_idx is not None:
            header.setSectionResizeMode(last_visible_logical_idx, header.ResizeMode.Stretch)
    
    def _apply_column_order(self) -> None:
        """Apply column order from profile."""
        if not self._moveslist_model or not self._column_profile_controller:
            return
        
        header = self.moves_table.horizontalHeader()
        column_order = self._column_profile_controller.get_active_profile_column_order()
        
        # Map column names to logical indices
        name_to_logical = {
            COL_NUM: MovesListModel.COL_NUM,
            COL_WHITE: MovesListModel.COL_WHITE,
            COL_BLACK: MovesListModel.COL_BLACK,
            COL_EVAL_WHITE: MovesListModel.COL_EVAL_WHITE,
            COL_EVAL_BLACK: MovesListModel.COL_EVAL_BLACK,
            COL_CPL_WHITE: MovesListModel.COL_CPL_WHITE,
            COL_CPL_BLACK: MovesListModel.COL_CPL_BLACK,
            COL_CPL_WHITE_2: MovesListModel.COL_CPL_WHITE_2,
            COL_CPL_WHITE_3: MovesListModel.COL_CPL_WHITE_3,
            COL_CPL_BLACK_2: MovesListModel.COL_CPL_BLACK_2,
            COL_CPL_BLACK_3: MovesListModel.COL_CPL_BLACK_3,
            COL_ASSESS_WHITE: MovesListModel.COL_ASSESS_WHITE,
            COL_ASSESS_BLACK: MovesListModel.COL_ASSESS_BLACK,
            COL_BEST_WHITE: MovesListModel.COL_BEST_WHITE,
            COL_BEST_BLACK: MovesListModel.COL_BEST_BLACK,
            COL_BEST_WHITE_2: MovesListModel.COL_BEST_WHITE_2,
            COL_BEST_WHITE_3: MovesListModel.COL_BEST_WHITE_3,
            COL_BEST_BLACK_2: MovesListModel.COL_BEST_BLACK_2,
            COL_BEST_BLACK_3: MovesListModel.COL_BEST_BLACK_3,
            COL_WHITE_IS_TOP3: MovesListModel.COL_WHITE_IS_TOP3,
            COL_BLACK_IS_TOP3: MovesListModel.COL_BLACK_IS_TOP3,
            COL_WHITE_DEPTH: MovesListModel.COL_WHITE_DEPTH,
            COL_BLACK_DEPTH: MovesListModel.COL_BLACK_DEPTH,
            COL_WHITE_SELDEPTH: MovesListModel.COL_WHITE_SELDEPTH,
            COL_BLACK_SELDEPTH: MovesListModel.COL_BLACK_SELDEPTH,
            COL_ECO: MovesListModel.COL_ECO,
            COL_OPENING: MovesListModel.COL_OPENING,
            COL_COMMENT: MovesListModel.COL_COMMENT,
            COL_WHITE_CAPTURE: MovesListModel.COL_WHITE_CAPTURE,
            COL_BLACK_CAPTURE: MovesListModel.COL_BLACK_CAPTURE,
            COL_WHITE_MATERIAL: MovesListModel.COL_WHITE_MATERIAL,
            COL_BLACK_MATERIAL: MovesListModel.COL_BLACK_MATERIAL,
            COL_FEN_WHITE: MovesListModel.COL_FEN_WHITE,
            COL_FEN_BLACK: MovesListModel.COL_FEN_BLACK,
        }
        
        # Get column visibility to only apply order to visible columns
        column_visibility = self._column_profile_controller.get_column_visibility()
        
        # Filter column_order to only include visible columns
        visible_order = [col_name for col_name in column_order if column_visibility.get(col_name, True)]
        
        # Restore column order by moving sections
        # Temporarily disable move signals to avoid triggering save during restore
        header.blockSignals(True)
        try:
            for target_position, col_name in enumerate(visible_order):
                if col_name not in name_to_logical:
                    continue
                logical_idx = name_to_logical[col_name]
                
                # Get current visual position of this column
                current_visual = header.visualIndex(logical_idx)
                if current_visual == -1:
                    continue  # Column is hidden
                
                # Move to target position if not already there
                if current_visual != target_position:
                    header.moveSection(current_visual, target_position)
        finally:
            header.blockSignals(False)
    
    def _save_column_widths(self) -> None:
        """Save current column widths to the active profile (in memory only, not persisted)."""
        if not self._moveslist_model or not self._column_profile_controller:
            return
        
        header = self.moves_table.horizontalHeader()
        
        # Get current widths from table header for all columns (including hidden)
        widths = {}
        logical_to_name = {
            MovesListModel.COL_NUM: COL_NUM,
            MovesListModel.COL_WHITE: COL_WHITE,
            MovesListModel.COL_BLACK: COL_BLACK,
            MovesListModel.COL_EVAL_WHITE: COL_EVAL_WHITE,
            MovesListModel.COL_EVAL_BLACK: COL_EVAL_BLACK,
            MovesListModel.COL_CPL_WHITE: COL_CPL_WHITE,
            MovesListModel.COL_CPL_BLACK: COL_CPL_BLACK,
            MovesListModel.COL_CPL_WHITE_2: COL_CPL_WHITE_2,
            MovesListModel.COL_CPL_WHITE_3: COL_CPL_WHITE_3,
            MovesListModel.COL_CPL_BLACK_2: COL_CPL_BLACK_2,
            MovesListModel.COL_CPL_BLACK_3: COL_CPL_BLACK_3,
            MovesListModel.COL_ASSESS_WHITE: COL_ASSESS_WHITE,
            MovesListModel.COL_ASSESS_BLACK: COL_ASSESS_BLACK,
            MovesListModel.COL_BEST_WHITE: COL_BEST_WHITE,
            MovesListModel.COL_BEST_BLACK: COL_BEST_BLACK,
            MovesListModel.COL_BEST_WHITE_2: COL_BEST_WHITE_2,
            MovesListModel.COL_BEST_WHITE_3: COL_BEST_WHITE_3,
            MovesListModel.COL_BEST_BLACK_2: COL_BEST_BLACK_2,
            MovesListModel.COL_BEST_BLACK_3: COL_BEST_BLACK_3,
            MovesListModel.COL_WHITE_IS_TOP3: COL_WHITE_IS_TOP3,
            MovesListModel.COL_BLACK_IS_TOP3: COL_BLACK_IS_TOP3,
            MovesListModel.COL_WHITE_DEPTH: COL_WHITE_DEPTH,
            MovesListModel.COL_BLACK_DEPTH: COL_BLACK_DEPTH,
            MovesListModel.COL_WHITE_SELDEPTH: COL_WHITE_SELDEPTH,
            MovesListModel.COL_BLACK_SELDEPTH: COL_BLACK_SELDEPTH,
            MovesListModel.COL_ECO: COL_ECO,
            MovesListModel.COL_OPENING: COL_OPENING,
            MovesListModel.COL_COMMENT: COL_COMMENT,
            MovesListModel.COL_WHITE_CAPTURE: COL_WHITE_CAPTURE,
            MovesListModel.COL_BLACK_CAPTURE: COL_BLACK_CAPTURE,
            MovesListModel.COL_WHITE_MATERIAL: COL_WHITE_MATERIAL,
            MovesListModel.COL_BLACK_MATERIAL: COL_BLACK_MATERIAL,
            MovesListModel.COL_FEN_WHITE: COL_FEN_WHITE,
            MovesListModel.COL_FEN_BLACK: COL_FEN_BLACK,
        }
        
        # Get which column is the last visible one by visual index (it stretches)
        column_visibility = self._column_profile_controller.get_column_visibility()
        last_visible_logical_idx = None
        column_count = header.count()
        for visual_idx in range(column_count - 1, -1, -1):  # Iterate backwards from last visual position
            logical_idx = header.logicalIndex(visual_idx)
            if logical_idx == -1:
                continue
            col_name = logical_to_name.get(logical_idx)
            if col_name and column_visibility.get(col_name, True):
                last_visible_logical_idx = logical_idx
                break
        
        # Save widths for all columns (including hidden ones), excluding the last visible one which stretches
        for logical_idx in range(self._moveslist_model.columnCount()):
            col_name = logical_to_name.get(logical_idx)
            if col_name:
                # Skip the last visible column (it stretches)
                if logical_idx != last_visible_logical_idx:
                    # Get width from header using logical index
                    width = header.sectionSize(logical_idx)
                    widths[col_name] = width
        
        # Update profile with current widths (in memory only, not persisted)
        if widths:
            self._column_profile_controller.update_column_widths(widths)

    def sync_moves_list_column_layout_to_active_profile(self) -> None:
        """Push current header widths and column order into the active profile (in memory).

        Call before operations that snapshot the profile (e.g. Save Profile, Save Profile as).
        """
        self._save_column_widths()
        self._save_column_order_to_active_profile()

    def _save_column_order_to_active_profile(self) -> None:
        """Read left-to-right visible column order from the header into the active profile."""
        if not self._moveslist_model or not self._column_profile_controller:
            return

        header = self.moves_table.horizontalHeader()
        column_visibility = self._column_profile_controller.get_column_visibility()
        logical_to_name = {
            MovesListModel.COL_NUM: COL_NUM,
            MovesListModel.COL_WHITE: COL_WHITE,
            MovesListModel.COL_BLACK: COL_BLACK,
            MovesListModel.COL_EVAL_WHITE: COL_EVAL_WHITE,
            MovesListModel.COL_EVAL_BLACK: COL_EVAL_BLACK,
            MovesListModel.COL_CPL_WHITE: COL_CPL_WHITE,
            MovesListModel.COL_CPL_BLACK: COL_CPL_BLACK,
            MovesListModel.COL_CPL_WHITE_2: COL_CPL_WHITE_2,
            MovesListModel.COL_CPL_WHITE_3: COL_CPL_WHITE_3,
            MovesListModel.COL_CPL_BLACK_2: COL_CPL_BLACK_2,
            MovesListModel.COL_CPL_BLACK_3: COL_CPL_BLACK_3,
            MovesListModel.COL_ASSESS_WHITE: COL_ASSESS_WHITE,
            MovesListModel.COL_ASSESS_BLACK: COL_ASSESS_BLACK,
            MovesListModel.COL_BEST_WHITE: COL_BEST_WHITE,
            MovesListModel.COL_BEST_BLACK: COL_BEST_BLACK,
            MovesListModel.COL_BEST_WHITE_2: COL_BEST_WHITE_2,
            MovesListModel.COL_BEST_WHITE_3: COL_BEST_WHITE_3,
            MovesListModel.COL_BEST_BLACK_2: COL_BEST_BLACK_2,
            MovesListModel.COL_BEST_BLACK_3: COL_BEST_BLACK_3,
            MovesListModel.COL_WHITE_IS_TOP3: COL_WHITE_IS_TOP3,
            MovesListModel.COL_BLACK_IS_TOP3: COL_BLACK_IS_TOP3,
            MovesListModel.COL_WHITE_DEPTH: COL_WHITE_DEPTH,
            MovesListModel.COL_BLACK_DEPTH: COL_BLACK_DEPTH,
            MovesListModel.COL_WHITE_SELDEPTH: COL_WHITE_SELDEPTH,
            MovesListModel.COL_BLACK_SELDEPTH: COL_BLACK_SELDEPTH,
            MovesListModel.COL_ECO: COL_ECO,
            MovesListModel.COL_OPENING: COL_OPENING,
            MovesListModel.COL_COMMENT: COL_COMMENT,
            MovesListModel.COL_WHITE_CAPTURE: COL_WHITE_CAPTURE,
            MovesListModel.COL_BLACK_CAPTURE: COL_BLACK_CAPTURE,
            MovesListModel.COL_WHITE_MATERIAL: COL_WHITE_MATERIAL,
            MovesListModel.COL_BLACK_MATERIAL: COL_BLACK_MATERIAL,
            MovesListModel.COL_FEN_WHITE: COL_FEN_WHITE,
            MovesListModel.COL_FEN_BLACK: COL_FEN_BLACK,
        }

        visible_order: List[str] = []
        for visual_idx in range(header.count()):
            logical_idx = header.logicalIndex(visual_idx)
            if logical_idx == -1:
                continue
            col_name = logical_to_name.get(logical_idx)
            if col_name and column_visibility.get(col_name, True):
                visible_order.append(col_name)

        default_order = self._column_profile_controller.get_column_names()
        column_order = visible_order.copy()
        for name in default_order:
            if name not in column_order:
                column_order.append(name)

        self._column_profile_controller.set_active_profile_column_order(column_order)
    
    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        """Handle column resize event.
        
        Args:
            logical_index: Logical index of the resized column.
            old_size: Previous size.
            new_size: New size.
        """
        # Early return if widget is being destroyed or doesn't have required attributes
        if not hasattr(self, 'moves_table') or not self.moves_table:
            return
        
        # Save column widths to profile model (in memory only, not persisted)
        # Use a timer to debounce rapid resize events
        if not hasattr(self, '_resize_timer') or self._resize_timer is None:
            self._resize_timer = QTimer(self)  # Parent to widget for automatic cleanup
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._save_column_widths)
        
        # Check if timer is still valid before using it
        if self._resize_timer is not None:
            # Restart timer on each resize (debounce)
            # Note: This saves to the profile model in memory, but doesn't persist
            # User must explicitly save the profile to persist width changes
            try:
                self._resize_timer.start(500)  # Save to model after 500ms of no resizing
            except RuntimeError:
                # Timer was deleted, recreate it
                self._resize_timer = None
    
    def closeEvent(self, event) -> None:
        """Handle widget close event to cleanup resources.
        
        Args:
            event: Close event.
        """
        # Stop and cleanup timer
        if hasattr(self, '_resize_timer') and self._resize_timer is not None:
            try:
                self._resize_timer.stop()
                self._resize_timer.deleteLater()
            except RuntimeError:
                # Timer already deleted, ignore
                pass
            self._resize_timer = None
        
        # Disconnect header signals
        if hasattr(self, 'moves_table') and self.moves_table:
            try:
                header = self.moves_table.horizontalHeader()
                header.sectionResized.disconnect(self._on_column_resized)
            except (TypeError, RuntimeError):
                # Signals not connected or already disconnected, ignore
                pass
        
        if self._column_profile_controller:
            self._column_profile_controller.detach_moves_list_view_profile_signals(
                self._on_column_visibility_changed,
                self._on_active_profile_changed,
            )
        
        super().closeEvent(event)


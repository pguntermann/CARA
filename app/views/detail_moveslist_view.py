"""Moves List view for detail panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableView, QStyledItemDelegate
from PyQt6.QtCore import Qt, QModelIndex, QTimer
from PyQt6.QtGui import QPalette, QColor, QBrush
from typing import Dict, Any, Optional, List

from app.models.moveslist_model import MovesListModel
from app.models.game_model import GameModel
from app.controllers.game_controller import GameController
from app.models.column_profile_model import (ColumnProfileModel, COL_NUM, COL_WHITE, COL_BLACK, COL_EVAL_WHITE, COL_EVAL_BLACK, 
                                             COL_CPL_WHITE, COL_CPL_BLACK, COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3,
                                             COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_BEST_WHITE, 
                                             COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3, COL_BEST_BLACK_2, COL_BEST_BLACK_3,
                                             COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3, COL_WHITE_DEPTH, COL_BLACK_DEPTH,
                                             COL_ECO, COL_OPENING, COL_COMMENT, COL_WHITE_CAPTURE, COL_BLACK_CAPTURE,
                                             COL_WHITE_MATERIAL, COL_BLACK_MATERIAL, COL_FEN_WHITE, COL_FEN_BLACK)


class DetailMovesListView(QWidget):
    """Moves list view displaying chess moves in a table."""
    
    def __init__(self, config: Dict[str, Any], moveslist_model: Optional[MovesListModel] = None,
                 game_model: Optional[GameModel] = None, game_controller: Optional[GameController] = None,
                 column_profile_model: Optional[ColumnProfileModel] = None) -> None:
        """Initialize the moves list view.
        
        Args:
            config: Configuration dictionary.
            moveslist_model: Optional MovesListModel to observe.
                           If provided, view will automatically update when model changes.
            game_model: Optional GameModel to observe for active move changes.
            game_controller: Optional GameController for navigating to specific plies.
            column_profile_model: Optional ColumnProfileModel for column visibility and widths.
        """
        super().__init__()
        self.config = config
        self._moveslist_model: Optional[MovesListModel] = None
        self._game_model: Optional[GameModel] = None
        self._game_controller: Optional[GameController] = None
        self._column_profile_model: Optional[ColumnProfileModel] = None
        self._active_move_ply: int = 0
        self._setup_ui()
        
        # Connect to models if provided
        if moveslist_model:
            self.set_model(moveslist_model)
        
        if game_model:
            self.set_game_model(game_model)
        
        if game_controller:
            self.set_game_controller(game_controller)
        
        if column_profile_model:
            self.set_column_profile_model(column_profile_model)
    
    def _setup_ui(self) -> None:
        """Setup the moves list UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create table view
        self.moves_table = QTableView()
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
        header_bg = table_config.get('header_background_color', [45, 45, 50])
        header_text = table_config.get('header_text_color', [200, 200, 200])
        header_border = table_config.get('header_border_color', [60, 60, 65])
        gridline_color = table_config.get('gridline_color', [60, 60, 65])
        selection_bg = table_config.get('selection_background_color', [70, 90, 130])
        selection_text = table_config.get('selection_text_color', [240, 240, 240])
        
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
                background-color: rgb({header_bg[0]}, {header_bg[1]}, {header_bg[2]});
                border: 1px solid rgb({header_border[0]}, {header_border[1]}, {header_border[2]});
            }}
        """
        self.moves_table.setStyleSheet(stylesheet)
        
        # Also set palette on header views to prevent macOS override
        horizontal_header = self.moves_table.horizontalHeader()
        if horizontal_header:
            header_palette = horizontal_header.palette()
            header_palette.setColor(horizontal_header.backgroundRole(), header_bg_color)
            header_palette.setColor(horizontal_header.foregroundRole(), header_text_color)
            horizontal_header.setPalette(header_palette)
            horizontal_header.setAutoFillBackground(True)
        
        # Set palette on vertical header to prevent macOS override
        vertical_header = self.moves_table.verticalHeader()
        if vertical_header:
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
                header.sectionMoved.disconnect(self._on_column_moved)
            except (TypeError, RuntimeError):
                # Signals not connected or already disconnected, ignore
                pass
        
        self._moveslist_model = model
        
        # Set model on table view
        self.moves_table.setModel(model)
        
        # Get header and enable column reordering
        header = self.moves_table.horizontalHeader()
        header.setSectionsMovable(True)  # Enable drag and drop column reordering
        
        # Connect to header resize events to save column widths
        header.sectionResized.connect(self._on_column_resized)
        
        # Connect to column move events to save column order
        header.sectionMoved.connect(self._on_column_moved)
        
        
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
        
        # Connect click handler to table view
        self.moves_table.clicked.connect(self._on_table_clicked)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe for active move changes.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
        
        self._game_model = model
        
        # Connect to model signals
        model.active_move_changed.connect(self._on_active_move_changed)
        
        # Set highlight color in moves list model if available
        if self._moveslist_model:
            highlight_color = self._get_active_move_highlight_color()
            self._moveslist_model.set_highlight_color(highlight_color)
        
        # Initialize with current active move if any
        self._on_active_move_changed(model.get_active_move_ply())
    
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
    
    def set_column_profile_model(self, model: ColumnProfileModel) -> None:
        """Set the column profile model to observe for column visibility and widths.
        
        Args:
            model: The ColumnProfileModel instance to observe.
        """
        if self._column_profile_model and self._column_profile_model != model:
            # Disconnect from old model
            try:
                if hasattr(self._column_profile_model, 'column_visibility_changed'):
                    self._column_profile_model.column_visibility_changed.disconnect(self._on_column_visibility_changed)
                if hasattr(self._column_profile_model, 'active_profile_changed'):
                    self._column_profile_model.active_profile_changed.disconnect(self._on_active_profile_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._column_profile_model = model
        
        # Connect to model signals
        if model:
            model.column_visibility_changed.connect(self._on_column_visibility_changed)
            model.active_profile_changed.connect(self._on_active_profile_changed)
            
            # Apply initial column visibility, order and widths (use a small delay to ensure model is ready)
            from PyQt6.QtCore import QTimer
            def apply_initial_settings():
                self._apply_column_visibility()
                self._apply_column_order_and_widths()
            QTimer.singleShot(0, apply_initial_settings)
    
    def _on_column_visibility_changed(self, column_name: str, visible: bool) -> None:
        """Handle column visibility change from profile model.
        
        Args:
            column_name: Name of the column.
            visible: True if column is visible, False otherwise.
        """
        # Update moves list model column visibility tracking
        if self._moveslist_model and self._column_profile_model:
            column_visibility = self._column_profile_model.get_current_column_visibility()
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
        if self._moveslist_model and self._column_profile_model:
            from PyQt6.QtCore import QTimer
            def update_visibility():
                column_visibility = self._column_profile_model.get_current_column_visibility()
                self._moveslist_model.set_column_visibility(column_visibility)
                self._apply_column_visibility()
                self._apply_column_order_and_widths()
            QTimer.singleShot(10, update_visibility)
        else:
            # If no delay needed, apply immediately
            self._apply_column_visibility()
            self._apply_column_order_and_widths()
    
    def _apply_column_visibility(self) -> None:
        """Apply column visibility using hideSection/showSection."""
        if not self._moveslist_model or not self._column_profile_model:
            return
        
        header = self.moves_table.horizontalHeader()
        column_visibility = self._column_profile_model.get_current_column_visibility()
        
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
        for logical_idx in range(32):
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
        
        # Skip if profile model not set yet - will be called again when connected
        if not self._column_profile_model:
            return
        
        # Apply column order first
        self._apply_column_order()
        
        # Then apply widths
        self._apply_column_widths_only()
    
    def _apply_column_widths_only(self) -> None:
        """Apply column widths from profile and set last column to stretch, preserving current order."""
        if not self._moveslist_model:
            return
        
        # Skip if profile model not set yet - will be called again when connected
        if not self._column_profile_model:
            return
        
        header = self.moves_table.horizontalHeader()
        column_visibility = self._column_profile_model.get_current_column_visibility()
        
        # Get widths from profile - must exist in user_settings.json
        column_widths = self._column_profile_model.get_current_column_widths()
        
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
        for logical_idx in range(32):
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
        if not self._moveslist_model or not self._column_profile_model:
            return
        
        header = self.moves_table.horizontalHeader()
        active_profile = self._column_profile_model._profiles[self._column_profile_model._active_profile_name]
        
        # Get default column order (all columns)
        default_order = self._column_profile_model._column_names.copy()
        column_order = active_profile.get_column_order(default_order)
        
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
        column_visibility = self._column_profile_model.get_current_column_visibility()
        
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
    
    def _place_column_at_end(self, column_name: str) -> None:
        """Place a newly shown column at the end of visible columns.
        
        Args:
            column_name: Name of the column to place at the end.
        """
        if not self._moveslist_model or not self._column_profile_model:
            return
        
        header = self.moves_table.horizontalHeader()
        
        # Map column names to logical indices
        from app.models.moveslist_model import MovesListModel
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
        
        if column_name not in name_to_logical:
            return
        
        logical_idx = name_to_logical[column_name]
        current_visual = header.visualIndex(logical_idx)
        
        # If column is not visible, don't move it
        if current_visual == -1:
            return
        
        # Find the last visible column position
        column_visibility = self._column_profile_model.get_current_column_visibility()
        last_visible_position = -1
        column_count = header.count()
        
        for visual_idx in range(column_count):
            logical = header.logicalIndex(visual_idx)
            if logical == -1:
                continue
            col_name = None
            for name, log_idx in name_to_logical.items():
                if log_idx == logical:
                    col_name = name
                    break
            if col_name and column_visibility.get(col_name, True):
                last_visible_position = visual_idx
        
        # Move the column to the end if it's not already there
        if last_visible_position >= 0 and current_visual != last_visible_position:
            header.blockSignals(True)
            try:
                header.moveSection(current_visual, last_visible_position)
            finally:
                header.blockSignals(False)
    
    def _on_column_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int) -> None:
        """Handle column move event from user dragging.
        
        Args:
            logical_index: Logical index of the moved column.
            old_visual_index: Previous visual position.
            new_visual_index: New visual position.
        """
        # Save column order when user drags a column
        self._save_column_order()
    
    def _save_column_order(self) -> None:
        """Save current column order to the active profile."""
        if not self._moveslist_model or not self._column_profile_model:
            return
        
        header = self.moves_table.horizontalHeader()
        
        # Map logical indices to column names
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
        
        # Get column visibility to only save visible columns in order
        column_visibility = self._column_profile_model.get_current_column_visibility()
        
        # Capture visual order from left to right (only visible columns)
        column_order = []
        for visual_index in range(header.count()):
            logical_index = header.logicalIndex(visual_index)
            col_name = logical_to_name.get(logical_index)
            if col_name and column_visibility.get(col_name, True):
                column_order.append(col_name)
        
        # Append hidden columns at the end (in their default order)
        default_order = self._column_profile_model._column_names.copy()
        for col_name in default_order:
            if col_name not in column_order and not column_visibility.get(col_name, True):
                column_order.append(col_name)
        
        # Update profile with current column order
        active_profile = self._column_profile_model._profiles[self._column_profile_model._active_profile_name]
        active_profile.set_column_order(column_order)
    
    def _save_column_widths(self) -> None:
        """Save current column widths to the active profile (in memory only, not persisted)."""
        if not self._moveslist_model or not self._column_profile_model:
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
        column_visibility = self._column_profile_model.get_current_column_visibility()
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
        for logical_idx in range(32):
            col_name = logical_to_name.get(logical_idx)
            if col_name:
                # Skip the last visible column (it stretches)
                if logical_idx != last_visible_logical_idx:
                    # Get width from header using logical index
                    width = header.sectionSize(logical_idx)
                    widths[col_name] = width
        
        # Update profile with current widths (in memory only, not persisted)
        if widths:
            self._column_profile_model.update_current_profile_column_widths(widths)
    
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
                header.sectionMoved.disconnect(self._on_column_moved)
            except (TypeError, RuntimeError):
                # Signals not connected or already disconnected, ignore
                pass
        
        super().closeEvent(event)
    
    def _on_column_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int) -> None:
        """Handle column reordering event.
        
        Args:
            logical_index: Logical index of the moved column.
            old_visual_index: Previous visual index.
            new_visual_index: New visual index.
        """
        # Column order saving is disabled - will be reimplemented later
        pass


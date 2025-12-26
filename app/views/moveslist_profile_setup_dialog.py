"""Moves list profile setup dialog for configuring column visibility and order."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QGroupBox,
    QScrollArea,
    QWidget,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QHeaderView,
    QAbstractSpinBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPalette, QFocusEvent
from typing import Dict, Any, List, Optional, Set

from app.models.column_profile_model import (
    DEFAULT_PROFILE_NAME,
    COL_NUM, COL_WHITE, COL_BLACK, COL_COMMENT,
    COL_EVAL_WHITE, COL_EVAL_BLACK, COL_CPL_WHITE, COL_CPL_BLACK,
    COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3,
    COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3,
    COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3,
    COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_WHITE_DEPTH, COL_BLACK_DEPTH,
    COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL,
    COL_ECO, COL_OPENING, COL_FEN_WHITE, COL_FEN_BLACK
)
from app.controllers.column_profile_controller import ColumnProfileController

class MovesListProfileSetupDialog(QDialog):
    """Dialog for configuring moves list column visibility and order."""
    
    def __init__(self, config: Dict[str, Any], profile_controller: ColumnProfileController, parent=None) -> None:
        """Initialize the moves list profile setup dialog.
        
        Args:
            config: Configuration dictionary.
            profile_controller: ColumnProfileController instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.profile_controller = profile_controller
        # Get model from controller (for signals and display names only)
        self.profile_model = profile_controller.get_profile_model()
        
        # Store initial state for cancel (state when dialog opens)
        self._initial_visibility: Dict[str, bool] = {}
        self._initial_order: Optional[List[str]] = None
        self._initial_widths: Dict[str, int] = {}
        
        # Store persisted state for reset (state saved to disk)
        self._persisted_visibility: Dict[str, bool] = {}
        self._persisted_order: Optional[List[str]] = None
        self._persisted_widths: Dict[str, int] = {}
        
        # Store current dialog widths (user-entered values, not yet saved to model)
        # This is the source of truth for spinbox values in the dialog
        self._current_dialog_widths: Dict[str, int] = {}
        
        # Flag to prevent recursive calls to _update_ui_from_state
        self._updating_ui = False
        
        # Column categories (matching menu structure)
        self.column_categories = {
            "Basic Columns": [COL_NUM, COL_WHITE, COL_BLACK, COL_COMMENT],
            "Evaluation Columns": [COL_EVAL_WHITE, COL_EVAL_BLACK, COL_CPL_WHITE, COL_CPL_BLACK,
                                  COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3],
            "Best Moves Columns": [
                COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3,
                COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3
            ],
            "Analysis Columns": [COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_WHITE_DEPTH, COL_BLACK_DEPTH],
            "Material Columns": [COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL],
            "Position Columns": [COL_ECO, COL_OPENING, COL_FEN_WHITE, COL_FEN_BLACK]
        }
        
        # Get dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {})
        width = dialog_config.get('width', 900)
        height = dialog_config.get('height', 600)
        self.setMinimumSize(width, height)
        self.resize(width, height)
        
        self._setup_ui()
        self._apply_styling()
        self._load_current_state()
        self.setWindowTitle("Setup Profile")
        
        # Set splitter sizes after dialog is set up
        # Left panel: fixed width (narrower), Right panel: takes remaining space
        margins = self.layout_config.get('margins', [15, 15, 15, 15])
        available_width = self._dialog_width - margins[0] - margins[2]  # left + right margins
        left_panel_width = self.layout_config.get('left_panel_width', 250)
        right_size = available_width - left_panel_width  # Right panel takes remaining space
        self.splitter.setSizes([left_panel_width, right_size])
        
        # Connect to model signals for synchronization
        self.profile_model.column_visibility_changed.connect(self._on_model_visibility_changed)
        self.profile_model.active_profile_changed.connect(self._on_profile_changed)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {})
        self.layout_config = dialog_config.get('layout', {})
        layout_spacing = self.layout_config.get('spacing', 10)
        layout_margins = self.layout_config.get('margins', [15, 15, 15, 15])
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(layout_spacing)
        main_layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Create splitter for two-panel layout
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel: Available columns with checkboxes
        left_panel = self._create_left_panel()
        self.splitter.addWidget(left_panel)
        
        # Right panel: Visible columns in order
        right_panel = self._create_right_panel()
        self.splitter.addWidget(right_panel)
        
        # Set splitter behavior: left panel fixed width, right panel stretches
        self.splitter.setStretchFactor(0, 0)  # Left panel fixed (no stretch)
        self.splitter.setStretchFactor(1, 1)  # Right panel stretches
        self.splitter.setCollapsible(0, False)  # Left panel cannot be collapsed
        self.splitter.setCollapsible(1, False)  # Right panel cannot be collapsed
        
        # Fix cursor on splitter handle for macOS compatibility
        # Horizontal splitter needs vertical resize cursor
        for i in range(self.splitter.count() - 1):
            handle = self.splitter.handle(i)
            if handle:
                handle.setCursor(Qt.CursorShape.SizeHorCursor)
        
        # Apply splitter styling to prevent macOS theme override
        ui_config = self.config.get('ui', {})
        splitter_config = ui_config.get('splitter', {})
        handle_color = splitter_config.get('handle_color', [30, 30, 30])
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
            QSplitter::handle:horizontal {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
        """)
        
        main_layout.addWidget(self.splitter)
        
        # Store dialog width for splitter sizing
        self._dialog_width = dialog_config.get('width', 750)
        
        # Buttons
        button_layout = QHBoxLayout()
        buttons_config = dialog_config.get('buttons', {})
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        
        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.clicked.connect(self._on_clear_all)
        button_layout.addWidget(self.clear_all_button)
        
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._on_reset)
        button_layout.addWidget(self.reset_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_button)
        
        main_layout.addLayout(button_layout)
    
    def _create_left_panel(self) -> QWidget:
        """Create the left panel with available columns grouped by category."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        # Get left panel layout config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {})
        layout_config = dialog_config.get('layout', {})
        left_panel_config = layout_config.get('left_panel', {})
        left_panel_margins = left_panel_config.get('margins', [0, 0, 0, 0])
        left_panel_spacing = left_panel_config.get('spacing', 5)
        layout.setContentsMargins(left_panel_margins[0], left_panel_margins[1], left_panel_margins[2], left_panel_margins[3])
        layout.setSpacing(left_panel_spacing)
        
        label = QLabel("Available Columns")
        layout.addWidget(label)
        
        # Scroll area for categories
        from PyQt6.QtWidgets import QFrame
        self.available_columns_scroll = QScrollArea()
        self.available_columns_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.available_columns_scroll.setWidgetResizable(True)
        self.available_columns_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.available_columns_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        # Get scroll area margins and spacing from config
        scroll_area_margins = self.layout_config.get('scroll_area_margins', [10, 10, 10, 10])
        scroll_layout_spacing = self.layout_config.get('scroll_layout_spacing', 10)
        scroll_layout.setContentsMargins(scroll_area_margins[0], scroll_area_margins[1], scroll_area_margins[2], scroll_area_margins[3])
        scroll_layout.setSpacing(scroll_layout_spacing)
        
        # Store checkboxes for later access
        self.column_checkboxes: Dict[str, QCheckBox] = {}
        
        # Get groups config for layout spacing and content margins
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {})
        groups_config = dialog_config.get('groups', {})
        group_content_margins = groups_config.get('content_margins', [10, 15, 10, 10])
        group_layout_spacing = groups_config.get('layout_spacing', 8)
        
        # Create group boxes for each category
        all_column_names = self.profile_model.get_column_names()
        categorized_columns = set()
        
        for category_name, category_columns in self.column_categories.items():
            group = QGroupBox(category_name)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(group_content_margins[0], group_content_margins[1], group_content_margins[2], group_content_margins[3])
            group_layout.setSpacing(group_layout_spacing)
            
            for column_name in category_columns:
                if column_name in all_column_names:
                    categorized_columns.add(column_name)
                    display_name = self.profile_model.get_column_display_name(column_name)
                    checkbox = QCheckBox(display_name)
                    checkbox.setProperty("column_name", column_name)
                    checkbox.toggled.connect(lambda checked, name=column_name: self._on_checkbox_toggled(name, checked))
                    self.column_checkboxes[column_name] = checkbox
                    group_layout.addWidget(checkbox)
            
            scroll_layout.addWidget(group)
        
        # Handle uncategorized columns
        uncategorized = [col for col in all_column_names if col not in categorized_columns]
        if uncategorized:
            group = QGroupBox("Other")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(group_content_margins[0], group_content_margins[1], group_content_margins[2], group_content_margins[3])
            group_layout.setSpacing(group_layout_spacing)
            
            for column_name in uncategorized:
                display_name = self.profile_model.get_column_display_name(column_name)
                checkbox = QCheckBox(display_name)
                checkbox.setProperty("column_name", column_name)
                checkbox.toggled.connect(lambda checked, name=column_name: self._on_checkbox_toggled(name, checked))
                self.column_checkboxes[column_name] = checkbox
                group_layout.addWidget(checkbox)
            
            scroll_layout.addWidget(group)
        
        scroll_layout.addStretch()
        self.available_columns_scroll.setWidget(scroll_widget)
        layout.addWidget(self.available_columns_scroll)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """Create the right panel with visible columns in order and width editing."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        # Get right panel layout config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {})
        layout_config = dialog_config.get('layout', {})
        right_panel_config = layout_config.get('right_panel', {})
        right_panel_margins = right_panel_config.get('margins', [0, 0, 0, 0])
        right_panel_spacing = right_panel_config.get('spacing', 5)
        layout.setContentsMargins(right_panel_margins[0], right_panel_margins[1], right_panel_margins[2], right_panel_margins[3])
        layout.setSpacing(right_panel_spacing)
        
        # Get label left padding from config
        label_left_padding = layout_config.get('right_panel_label_left_padding', 10)
        
        label = QLabel("Visible Columns (drag to reorder)")
        label.setContentsMargins(label_left_padding, 0, 0, 0)
        layout.addWidget(label)
        
        # Table widget for visible columns with drag-and-drop and width editing
        # Use a custom class to preserve cell widgets during drag-and-drop
        class MovableTableWidget(QTableWidget):
            def __init__(self, parent_dialog):
                super().__init__()
                self.parent_dialog = parent_dialog
            
            def dropEvent(self, event):
                """Override dropEvent to preserve cell widgets when rows are moved."""
                # Get state BEFORE drag (column order and widgets)
                order_before = []
                items_data = {}  # Store item data and widget width values
                
                for row in range(self.rowCount()):
                    item = self.item(row, 0)
                    if item:
                        column_name = item.data(Qt.ItemDataRole.UserRole)
                        if column_name:
                            order_before.append(column_name)
                            widget = self.cellWidget(row, 1)
                            # Extract item data and widget width BEFORE clearing (items/widgets will be deleted)
                            width_value = None
                            if widget and hasattr(widget, 'value'):
                                width_value = widget.value()
                            
                            items_data[column_name] = {
                                'text': item.text(),
                                'flags': item.flags(),
                                'width': width_value  # Store width value, not widget reference
                            }
                
                # Get drop position from event
                drop_row = self.drop_on(event)
                if drop_row is None:
                    drop_row = self.rowCount()
                
                # Find which row was being dragged (from selected items)
                selected_items = self.selectedItems()
                dragged_column_name = None
                source_row = None
                
                if selected_items:
                    # Get the first selected item (should be the dragged row)
                    dragged_item = selected_items[0]
                    source_row = dragged_item.row()
                    dragged_column_name = dragged_item.data(Qt.ItemDataRole.UserRole)
                
                # If we couldn't find the dragged item from selection, try to detect from event
                if dragged_column_name is None:
                    # Accept the event but handle manually
                    event.accept()
                    # Try to get dragged item from mimeData or use a different approach
                    # For now, fall back to Qt's default behavior but preserve all items
                    super().dropEvent(event)
                else:
                    # Manual reordering to preserve all items
                    # Remove the dragged item from its current position
                    new_order = order_before.copy()
                    
                    # Remove dragged item from its current position
                    if dragged_column_name in new_order:
                        new_order.remove(dragged_column_name)
                    
                    # Insert at drop position
                    # Adjust drop_row if dragging from above (since we removed the item)
                    if source_row is not None and source_row < drop_row:
                        drop_row -= 1
                    
                    # Clamp drop_row to valid range
                    drop_row = max(0, min(drop_row, len(new_order)))
                    new_order.insert(drop_row, dragged_column_name)
                    
                    # Accept the event (prevent default behavior)
                    event.accept()
                    
                    # Clear the table (this deletes all items, but we've already extracted the data)
                    self.setRowCount(0)
                    
                    # Rebuild table with new order, preserving all items and widgets
                    for row, column_name in enumerate(new_order):
                        self.insertRow(row)
                        # Restore item from extracted data
                        item_data = items_data.get(column_name)
                        if item_data:
                            # Create new item from extracted data
                            new_item = QTableWidgetItem(item_data['text'])
                            new_item.setData(Qt.ItemDataRole.UserRole, column_name)
                            new_item.setFlags(item_data['flags'])
                            self.setItem(row, 0, new_item)
                            
                            # Recreate widget with stored width value
                            width_value = item_data.get('width')
                            if width_value is None:
                                # Fallback to current dialog widths or default
                                if hasattr(self.parent_dialog, '_current_dialog_widths'):
                                    width_value = self.parent_dialog._current_dialog_widths.get(column_name, 100)
                                else:
                                    width_value = 100
                            
                            # Create new spinbox widget (recreate instead of reusing)
                            if hasattr(self.parent_dialog, '_create_width_spinbox'):
                                widget = self.parent_dialog._create_width_spinbox(column_name, width_value)
                                self.setCellWidget(row, 1, widget)
                                # Update parent dialog's width_spinboxes dictionary
                                if hasattr(self.parent_dialog, 'width_spinboxes'):
                                    self.parent_dialog.width_spinboxes[column_name] = widget
                                # Apply styling
                                if hasattr(self.parent_dialog, '_apply_spinbox_styling'):
                                    self.parent_dialog._apply_spinbox_styling(widget)
                
                # Get state AFTER drag (column order)
                order_after = []
                for row in range(self.rowCount()):
                    item = self.item(row, 0)
                    if item:
                        column_name = item.data(Qt.ItemDataRole.UserRole)
                        if column_name:
                            order_after.append(column_name)
                
            
            def drop_on(self, event) -> Optional[int]:
                """Get the row index where the drop occurred."""
                index = self.indexAt(event.position().toPoint())
                if index.isValid():
                    # Check if dropping above or below the item
                    drop_point = event.position().toPoint()
                    item_rect = self.visualItemRect(self.item(index.row(), 0))
                    if drop_point.y() < item_rect.center().y():
                        # Dropping above the item
                        return index.row()
                    else:
                        # Dropping below the item
                        return index.row() + 1
                else:
                    # Dropping at the end
                    return self.rowCount()
        
        self.visible_table = MovableTableWidget(self)
        self.visible_table.setColumnCount(2)
        self.visible_table.setHorizontalHeaderLabels(["Column", "Width"])
        self.visible_table.horizontalHeader().setStretchLastSection(False)
        self.visible_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.visible_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        # Get width column width from config
        table_config = dialog_config.get('table', {})
        width_column_width = table_config.get('width_column_width', 80)
        self.visible_table.setColumnWidth(1, width_column_width)
        self.visible_table.verticalHeader().setVisible(False)
        self.visible_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.visible_table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.visible_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.visible_table.setShowGrid(False)
        layout.addWidget(self.visible_table)
        
        # Store width spinboxes for later access
        self.width_spinboxes: Dict[str, QSpinBox] = {}
        
        return panel
    
    def _load_current_state(self) -> None:
        """Load current profile state into dialog."""
        # Get persisted state (used for Reset button)
        persisted_state = self.profile_controller.get_persisted_profile_state()
        self._persisted_visibility = persisted_state['visibility'].copy()
        self._persisted_order = persisted_state['order'].copy() if persisted_state['order'] else None
        self._persisted_widths = persisted_state['widths'].copy()
        
        # Get current in-memory state (state when dialog opens, used for Cancel button)
        current_state = self.profile_controller.get_current_profile_state()
        self._initial_visibility = current_state['visibility'].copy()
        self._initial_order = current_state['order'].copy() if current_state['order'] else None
        self._initial_widths = current_state['widths'].copy()
        
        # Initialize current dialog widths with current in-memory values
        self._current_dialog_widths = current_state['widths'].copy()
        
        # Update UI with current state (so dialog shows current in-memory state)
        self._update_ui_from_state()
    
    def _update_ui_from_state(self) -> None:
        """Update UI elements from current profile state."""
        # Prevent recursive calls
        if self._updating_ui:
            return
        self._updating_ui = True
        try:
            column_visibility = self.profile_controller.get_column_visibility()
            column_widths = self.profile_controller.get_column_widths()
            active_profile = self.profile_model._profiles.get(self.profile_model._active_profile_name)
            
            # CRITICAL: First, save ALL current spinbox values to _current_dialog_widths
            # This must happen BEFORE any table rebuild to preserve user edits
            for i in range(self.visible_table.rowCount()):
                item = self.visible_table.item(i, 0)
                if item:
                    column_name = item.data(Qt.ItemDataRole.UserRole)
                    if column_name:
                        existing_spinbox = self.visible_table.cellWidget(i, 1)
                        if existing_spinbox and isinstance(existing_spinbox, QSpinBox):
                            # Force save current spinbox value - this is critical!
                            current_val = existing_spinbox.value()
                            old_val = self._current_dialog_widths.get(column_name)
                            self._current_dialog_widths[column_name] = current_val
            
            # Now use _current_dialog_widths as the preserved widths
            preserved_widths = self._current_dialog_widths.copy()
            
            # Update checkboxes
            for column_name, checkbox in self.column_checkboxes.items():
                visible = column_visibility.get(column_name, True)
                checkbox.blockSignals(True)
                checkbox.setChecked(visible)
                checkbox.blockSignals(False)
            
            # Update visible table
            self.visible_table.setRowCount(0)
            self.width_spinboxes.clear()
            
            if active_profile:
                default_order = self.profile_model._column_names.copy()
                column_order = active_profile.get_column_order(default_order)
                
                # Add only visible columns in order
                for column_name in column_order:
                    if column_visibility.get(column_name, True):
                        row = self.visible_table.rowCount()
                        self.visible_table.insertRow(row)
                        
                        # Column name
                        display_name = self.profile_model.get_column_display_name(column_name)
                        name_item = QTableWidgetItem(display_name)
                        name_item.setData(Qt.ItemDataRole.UserRole, column_name)
                        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.visible_table.setItem(row, 0, name_item)
                        
                        # Width spinbox - ALWAYS use _current_dialog_widths as source of truth
                        # This ensures user edits are never lost, even if table is rebuilt
                        if column_name in self._current_dialog_widths:
                            width = self._current_dialog_widths[column_name]
                        elif column_name in preserved_widths:
                            width = preserved_widths[column_name]
                            # Store in current dialog widths for consistency
                            self._current_dialog_widths[column_name] = width
                        else:
                            width = column_widths.get(column_name, 100)
                            # Store in current dialog widths
                            self._current_dialog_widths[column_name] = width
                        spinbox = self._create_width_spinbox(column_name, width)
                        self.width_spinboxes[column_name] = spinbox
                        self.visible_table.setCellWidget(row, 1, spinbox)
                        # Apply styling to spinbox
                        self._apply_spinbox_styling(spinbox)
        finally:
            self._updating_ui = False
    
    def _create_width_spinbox(self, column_name: str, width: int) -> QSpinBox:
        """Create a width spinbox with proper event handling."""
        class WidthSpinBox(QSpinBox):
            def __init__(self, parent_dialog, col_name, initial_value):
                super().__init__()
                self.parent_dialog = parent_dialog
                self.col_name = col_name
                self.is_col_num = (col_name == COL_NUM)
                # Get spinbox range and minimum height from config
                inputs_config = self.parent_dialog.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {}).get('inputs', {})
                spinbox_config = inputs_config.get('spinbox', {})
                min_value = spinbox_config.get('min_value', 10)
                max_value = spinbox_config.get('max_value', 1000)
                spinbox_min_height = spinbox_config.get('minimum_height', 30)
                self.setRange(min_value, max_value)
                self.setValue(initial_value)
                self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                self.setMinimumHeight(spinbox_min_height)
                self.setProperty("column_name", col_name)
                
                # Connect to valueChanged to track user edits in real-time
                # This fires on every change, including when user types
                # CRITICAL: Save immediately on any value change, even partial input
                def make_handler(name):
                    def handler(val):
                        # Save immediately on any value change - this is the source of truth
                        # Store directly to avoid any delays or race conditions
                        old_val = parent_dialog._current_dialog_widths.get(name)
                        parent_dialog._current_dialog_widths[name] = val
                    return handler
                self.valueChanged.connect(make_handler(col_name))
                # Also connect to editingFinished as backup (fires when user finishes editing)
                # BUT: editingFinished fires AFTER validation, so we need to check if value changed
                def on_editing_finished():
                    # Only save if the value in _current_dialog_widths is different from current value
                    # This prevents overwriting with a reverted value
                    saved_val = parent_dialog._current_dialog_widths.get(col_name)
                    current_val = self.value()
                    if saved_val != current_val:
                        # Saved value differs from current - validation may have reset it
                        # Don't overwrite the saved value (preserve user input)
                        pass
                    else:
                        # Values match, safe to save
                        self._save_current_value()
                self.editingFinished.connect(on_editing_finished)
                # Also connect to textChanged as additional backup for text input
                # This ensures we catch the value even if valueChanged doesn't fire
                # CRITICAL: Get lineEdit() inside the handler, not during __init__, to avoid
                # accessing an invalid widget reference
                def on_text_changed():
                    # Get fresh lineEdit reference each time - don't capture it in closure
                    line_edit = self.lineEdit()
                    if not line_edit:
                        return
                    text = line_edit.text()
                    if not text:
                        return
                    # Only process if text is purely numeric (no leading/trailing spaces)
                    text = text.strip()
                    if not text:
                        return
                    # Validate that text contains only digits (with optional minus sign)
                    if not text.lstrip('-').isdigit():
                        return
                    val = int(text)
                    # Validate range before saving
                    if 10 <= val <= 1000:
                        parent_dialog._current_dialog_widths[col_name] = val
                
                # Connect to textChanged - get lineEdit after widget is fully initialized
                # Use QTimer to ensure lineEdit is available
                from PyQt6.QtCore import QTimer
                def connect_text_changed():
                    line_edit = self.lineEdit()
                    if line_edit:
                        line_edit.textChanged.connect(on_text_changed)
                QTimer.singleShot(0, connect_text_changed)
            
            def _save_current_value(self) -> None:
                """Save current value to dialog widths."""
                # CRITICAL: Read from line edit text first, as it may have uncommitted user input
                # Only fall back to value() if text parsing fails
                # Get fresh lineEdit reference - don't rely on captured reference
                line_edit = self.lineEdit()
                if line_edit:
                    text = line_edit.text()
                    if text:
                        text = text.strip()
                        if text and text.lstrip('-').isdigit():
                            # Text is valid numeric string
                            current_val = int(text)
                            # Validate range
                            if 10 <= current_val <= 1000:
                                self.parent_dialog._current_dialog_widths[self.col_name] = current_val
                                return
                    # If text is invalid or out of range, use validated value
                    current_val = self.value()
                else:
                    # No lineEdit available, use validated value
                    current_val = self.value()
                
                self.parent_dialog._current_dialog_widths[self.col_name] = current_val
            
            def focusOutEvent(self, event: QFocusEvent) -> None:
                """Save value when focus is lost - ensure it's saved before any rebuild."""
                # CRITICAL: Read from line edit text FIRST and save it immediately
                # This must happen BEFORE any validation or setValue calls
                # Get fresh lineEdit reference - don't rely on captured reference
                line_edit = self.lineEdit()
                text_val = None
                if line_edit:
                    text = line_edit.text()
                    if text:
                        text = text.strip()
                        if text and text.lstrip('-').isdigit():
                            text_val = int(text)
                            # Validate range before saving
                            if 10 <= text_val <= 1000:
                                # CRITICAL: Save the text value immediately to _current_dialog_widths
                                # This preserves user input even if validation clamps it later
                                if text_val != self.value():
                                    # User typed a different value - save it immediately
                                    self.parent_dialog._current_dialog_widths[self.col_name] = text_val
                                    # Now try to set the value (may clamp to min/max)
                                    # Block signals temporarily to prevent recursive saves
                                    self.blockSignals(True)
                                    self.setValue(text_val)
                                    self.blockSignals(False)
                
                validated_val = self.value()
                
                # Only call _save_current_value if we haven't already saved the text value above
                # This prevents overwriting with a clamped value
                if text_val is None or text_val == validated_val:
                    # No text input or text matches validated value, safe to save
                    self._save_current_value()
                # else: We already saved the text value above, don't overwrite with clamped value
                super().focusOutEvent(event)
        
        return WidthSpinBox(self, column_name, width)
    
    def _on_width_changed(self, column_name: str, value: int) -> None:
        """Handle width change from spinbox - store in dialog widths dict."""
        # Store the value immediately when user changes it
        # This is the source of truth - always use this when creating spinboxes
        self._current_dialog_widths[column_name] = value
    
    def _on_width_editing_finished(self, column_name: str, value: int) -> None:
        """Handle editing finished - ensure value is saved."""
        # Backup handler for editingFinished signal
        self._current_dialog_widths[column_name] = value
    
    def _on_checkbox_toggled(self, column_name: str, checked: bool) -> None:
        """Handle checkbox toggle."""
        # CRITICAL: Save all current spinbox values BEFORE making any changes
        # This must happen first to preserve any user edits
        self._save_all_spinbox_values()
        
        # Update visible table
        if checked:
            # Use _current_dialog_widths as the source of truth (already saved above)
            current_widths = self._current_dialog_widths.copy()
            
            # Add to visible table at the end
            row = self.visible_table.rowCount()
            self.visible_table.insertRow(row)
            
            display_name = self.profile_model.get_column_display_name(column_name)
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, column_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.visible_table.setItem(row, 0, name_item)
            
            # Width spinbox - ALWAYS use _current_dialog_widths as source of truth
            if column_name in self._current_dialog_widths:
                width = self._current_dialog_widths[column_name]
            elif column_name in current_widths:
                width = current_widths[column_name]
                self._current_dialog_widths[column_name] = width
            elif column_name in self.width_spinboxes:
                # Column has a spinbox but not in table (shouldn't happen, but preserve if it does)
                width = self.width_spinboxes[column_name].value()
                self._current_dialog_widths[column_name] = width
            else:
                # Get width from controller
                column_widths = self.profile_controller.get_column_widths()
                width = column_widths.get(column_name, 100)
                self._current_dialog_widths[column_name] = width
            
            spinbox = self._create_width_spinbox(column_name, width)
            self.width_spinboxes[column_name] = spinbox
            self.visible_table.setCellWidget(row, 1, spinbox)
            # Apply styling to spinbox
            self._apply_spinbox_styling(spinbox)
            
            # Restore preserved widths for existing columns (in case they were reset)
            for i in range(self.visible_table.rowCount() - 1):  # Exclude the row we just added
                item = self.visible_table.item(i, 0)
                if item:
                    existing_column_name = item.data(Qt.ItemDataRole.UserRole)
                    if existing_column_name and existing_column_name in current_widths:
                        existing_spinbox = self.visible_table.cellWidget(i, 1)
                        if existing_spinbox and isinstance(existing_spinbox, QSpinBox):
                            existing_spinbox.setValue(current_widths[existing_column_name])
        else:
            # Remove from visible table
            for i in range(self.visible_table.rowCount()):
                item = self.visible_table.item(i, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == column_name:
                    # Remove spinbox reference
                    if column_name in self.width_spinboxes:
                        del self.width_spinboxes[column_name]
                    self.visible_table.removeRow(i)
                    break
    
    def _on_clear_all(self) -> None:
        """Clear all columns except #."""
        # CRITICAL: Save all current spinbox values BEFORE clearing
        # This must happen first to preserve any user edits, especially for COL_NUM
        self._save_all_spinbox_values()
        
        # Clear all columns via controller
        visibility = self.profile_controller.clear_all_columns()
        
        # Update checkboxes
        for column_name, checkbox in self.column_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(visibility.get(column_name, False))
            checkbox.blockSignals(False)
        
        # Clear visible table and add only COL_NUM
        self.visible_table.setRowCount(0)
        self.width_spinboxes.clear()
        
        row = self.visible_table.rowCount()
        self.visible_table.insertRow(row)
        display_name = self.profile_model.get_column_display_name(COL_NUM)
        name_item = QTableWidgetItem(display_name)
        name_item.setData(Qt.ItemDataRole.UserRole, COL_NUM)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.visible_table.setItem(row, 0, name_item)
        
        # Width spinbox for COL_NUM - ALWAYS use _current_dialog_widths as source of truth
        # This ensures user edits are preserved even after clear all
        if COL_NUM in self._current_dialog_widths:
            width = self._current_dialog_widths[COL_NUM]
        else:
            column_widths = self.profile_controller.get_column_widths()
            width = column_widths.get(COL_NUM, 50)
            # Store in current dialog widths
            self._current_dialog_widths[COL_NUM] = width
        spinbox = self._create_width_spinbox(COL_NUM, width)
        self.width_spinboxes[COL_NUM] = spinbox
        self.visible_table.setCellWidget(row, 1, spinbox)
        # Apply styling to spinbox
        self._apply_spinbox_styling(spinbox)
    
    def _on_reset(self) -> None:
        """Reset to persisted state of the active profile (state saved to disk)."""
        # Use persisted state (saved to disk)
        
        # Restore persisted visibility
        for column_name, checkbox in self.column_checkboxes.items():
            visible = self._persisted_visibility.get(column_name, True)
            checkbox.blockSignals(True)
            checkbox.setChecked(visible)
            checkbox.blockSignals(False)
        
        # Reset dialog widths to persisted values
        self._current_dialog_widths = self._persisted_widths.copy()
        
        # Restore persisted order
        column_order = self._persisted_order.copy() if self._persisted_order else self.profile_model._column_names.copy()
        
        # Update visible table based on initial visibility, order, and widths
        self.visible_table.setRowCount(0)
        self.width_spinboxes.clear()
        
        for column_name in column_order:
            if self._persisted_visibility.get(column_name, True):
                row = self.visible_table.rowCount()
                self.visible_table.insertRow(row)
                
                display_name = self.profile_model.get_column_display_name(column_name)
                name_item = QTableWidgetItem(display_name)
                name_item.setData(Qt.ItemDataRole.UserRole, column_name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.visible_table.setItem(row, 0, name_item)
                
                # Width spinbox with initial width
                width = self._current_dialog_widths.get(column_name, 100)
                spinbox = self._create_width_spinbox(column_name, width)
                self.width_spinboxes[column_name] = spinbox
                self.visible_table.setCellWidget(row, 1, spinbox)
                # Apply styling to spinbox
                self._apply_spinbox_styling(spinbox)
    
    def _on_apply(self) -> None:
        """Apply changes to model via controller."""
        # Collect visibility from checkboxes
        visibility = {}
        for column_name, checkbox in self.column_checkboxes.items():
            visibility[column_name] = checkbox.isChecked()
        
        # Validate that at least one column is selected
        visible_count = sum(1 for v in visibility.values() if v)
        if visible_count == 0:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "No Columns Selected",
                "Please select at least one column to display.",
                self
            )
            return
        
        # Collect order from visible table
        column_order = []
        for i in range(self.visible_table.rowCount()):
            item = self.visible_table.item(i, 0)
            if item:
                column_name = item.data(Qt.ItemDataRole.UserRole)
                if column_name:
                    column_order.append(column_name)
        
        # Add hidden columns at the end in default order
        column_visibility = self.profile_controller.get_column_visibility()
        default_order = self.profile_model._column_names.copy()
        for column_name in default_order:
            if column_name not in column_order and not column_visibility.get(column_name, True):
                column_order.append(column_name)
        
        # Collect widths from spinboxes
        widths = {}
        for column_name, spinbox in self.width_spinboxes.items():
            widths[column_name] = spinbox.value()
        
        # Apply changes via controller
        self.profile_controller.apply_dialog_changes(visibility, column_order, widths)
        
        # Update initial state for next cancel
        self._load_current_state()
        
        self.accept()
    
    def _on_model_visibility_changed(self, column_name: str, visible: bool) -> None:
        """Handle visibility change from model (menu toggle)."""
        # First, save all current spinbox values before making any changes
        self._save_all_spinbox_values()
        
        if column_name in self.column_checkboxes:
            checkbox = self.column_checkboxes[column_name]
            checkbox.blockSignals(True)
            checkbox.setChecked(visible)
            checkbox.blockSignals(False)
            
            # Update visible table
            if visible:
                # Check if already in table
                found = False
                for i in range(self.visible_table.rowCount()):
                    item = self.visible_table.item(i, 0)
                    if item and item.data(Qt.ItemDataRole.UserRole) == column_name:
                        found = True
                        break
                
                if not found:
                    # Add at end
                    row = self.visible_table.rowCount()
                    self.visible_table.insertRow(row)
                    display_name = self.profile_model.get_column_display_name(column_name)
                    name_item = QTableWidgetItem(display_name)
                    name_item.setData(Qt.ItemDataRole.UserRole, column_name)
                    name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.visible_table.setItem(row, 0, name_item)
                    
                    # Width spinbox - ALWAYS use _current_dialog_widths as source of truth
                    if column_name in self._current_dialog_widths:
                        width = self._current_dialog_widths[column_name]
                    else:
                        existing_width = None
                        for j in range(self.visible_table.rowCount()):
                            item = self.visible_table.item(j, 0)
                            if item and item.data(Qt.ItemDataRole.UserRole) == column_name:
                                existing_spinbox = self.visible_table.cellWidget(j, 1)
                                if existing_spinbox and isinstance(existing_spinbox, QSpinBox):
                                    existing_width = existing_spinbox.value()
                                break
                        
                        if existing_width is not None:
                            width = existing_width
                        else:
                            column_widths = self.profile_controller.get_column_widths()
                            width = column_widths.get(column_name, 100)
                        self._current_dialog_widths[column_name] = width
                    
                    spinbox = self._create_width_spinbox(column_name, width)
                    self.width_spinboxes[column_name] = spinbox
                    self.visible_table.setCellWidget(row, 1, spinbox)
                    # Apply styling to spinbox
                    self._apply_spinbox_styling(spinbox)
            else:
                # Remove from table
                for i in range(self.visible_table.rowCount()):
                    item = self.visible_table.item(i, 0)
                    if item and item.data(Qt.ItemDataRole.UserRole) == column_name:
                        # Remove spinbox reference
                        if column_name in self.width_spinboxes:
                            del self.width_spinboxes[column_name]
                        self.visible_table.removeRow(i)
                        break
    
    def _save_all_spinbox_values(self) -> None:
        """Save all current spinbox values to _current_dialog_widths."""
        # This is called before any operation that might rebuild the table
        for i in range(self.visible_table.rowCount()):
            item = self.visible_table.item(i, 0)
            if item:
                column_name = item.data(Qt.ItemDataRole.UserRole)
                if column_name:
                    existing_spinbox = self.visible_table.cellWidget(i, 1)
                    if existing_spinbox and isinstance(existing_spinbox, QSpinBox):
                        current_val = existing_spinbox.value()
                        self._current_dialog_widths[column_name] = current_val
    
    def _on_profile_changed(self, profile_name: str) -> None:
        """Handle profile change from model."""
        self._load_current_state()
    
    def reject(self) -> None:
        """Cancel dialog and restore initial state."""
        # Restore initial state via controller
        if self._initial_order:
            self.profile_controller.apply_dialog_changes(
                self._initial_visibility,
                self._initial_order,
                self._initial_widths
            )
        
        super().reject()
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('moveslist_profile_setup', {})
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        border_color = dialog_config.get('border_color', [60, 60, 65])
        text_color = dialog_config.get('text_color', [200, 200, 200])
        from app.utils.font_utils import scale_font_size
        font_size = scale_font_size(dialog_config.get('font_size', 11))
        
        # Set dialog background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(palette)
        
        # Button styling
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)
        
        # Label styling
        labels_config = dialog_config.get('labels', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        label_font_family = resolve_font_family(labels_config.get('font_family', 'Helvetica Neue'))
        label_font_size = scale_font_size(labels_config.get('font_size', 11))
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        
        label_style = (
            f"QLabel {{"
            f"font-family: {label_font_family};"
            f"font-size: {label_font_size}pt;"
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
            label_palette = label.palette()
            label_palette.setColor(label.foregroundRole(), QColor(*label_text_color))
            label.setPalette(label_palette)
            label.update()
        
        # Checkbox styling using StyleManager
        from app.views.style import StyleManager
        from pathlib import Path
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Use input border and background colors for checkbox indicator
        inputs_config = dialog_config.get('inputs', {})
        input_border_color = inputs_config.get('border_color', [60, 60, 65])
        input_bg_color = inputs_config.get('background_color', [30, 30, 35])
        
        # Get all checkboxes and apply styling
        checkboxes = self.findChildren(QCheckBox)
        StyleManager.style_checkboxes(
            checkboxes,
            self.config,
            label_text_color,
            label_font_family,
            label_font_size,
            input_bg_color,
            input_border_color,
            checkmark_path
        )
        
        # Set palette to prevent macOS override of background color
        for checkbox in checkboxes:
            checkbox_palette = checkbox.palette()
            checkbox_palette.setColor(checkbox.foregroundRole(), QColor(*label_text_color))
            checkbox_palette.setColor(checkbox_palette.ColorRole.Base, QColor(bg_color[0], bg_color[1], bg_color[2]))
            checkbox_palette.setColor(checkbox_palette.ColorRole.Window, QColor(bg_color[0], bg_color[1], bg_color[2]))
            checkbox.setPalette(checkbox_palette)
            checkbox.setAutoFillBackground(True)
            checkbox.update()
        
        # Scroll area styling
        if hasattr(self, 'available_columns_scroll'):
            inputs_config = dialog_config.get('inputs', {})
            input_bg = inputs_config.get('background_color', [30, 30, 35])
            input_border = inputs_config.get('border_color', [60, 60, 65])
            input_border_radius = inputs_config.get('border_radius', 3)
            
            # Apply scrollbar styling using StyleManager
            from app.views.style import StyleManager
            StyleManager.style_scroll_area(
                self.available_columns_scroll,
                self.config,
                input_bg,
                input_border,
                input_border_radius
            )
        
        # Table widget styling
        table_config = dialog_config.get('table', {})
        table_bg_color = table_config.get('background_color', [30, 30, 35])
        table_text_color = table_config.get('text_color', [240, 240, 240])
        table_border_color = table_config.get('border_color', [60, 60, 65])
        table_border_radius = table_config.get('border_radius', 3)
        table_header_bg = table_config.get('header_background_color', [45, 45, 50])
        table_header_text = table_config.get('header_text_color', [200, 200, 200])
        table_item_padding = table_config.get('item_padding', 5)
        table_header_padding = table_config.get('header_padding', 5)
        
        table_style = (
            f"QTableWidget {{"
            f"background-color: rgb({table_bg_color[0]}, {table_bg_color[1]}, {table_bg_color[2]});"
            f"color: rgb({table_text_color[0]}, {table_text_color[1]}, {table_text_color[2]});"
            f"border: 1px solid rgb({table_border_color[0]}, {table_border_color[1]}, {table_border_color[2]});"
            f"border-radius: {table_border_radius}px;"
            f"font-size: {font_size}pt;"
            f"gridline-color: rgb({table_border_color[0]}, {table_border_color[1]}, {table_border_color[2]});"
            f"}}"
            f"QTableWidget::item {{"
            f"padding: {table_item_padding}px;"
            f"}}"
            f"QTableWidget::item:selected {{"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"}}"
            f"QHeaderView::section {{"
            f"background-color: rgb({table_header_bg[0]}, {table_header_bg[1]}, {table_header_bg[2]});"
            f"color: rgb({table_header_text[0]}, {table_header_text[1]}, {table_header_text[2]});"
            f"border: 1px solid rgb({table_border_color[0]}, {table_border_color[1]}, {table_border_color[2]});"
            f"padding: {table_header_padding}px;"
            f"font-size: {font_size}pt;"
            f"}}"
        )
        
        self.visible_table.setStyleSheet(table_style)
        
        # Apply scrollbar styling to table widget to match the left scroll area exactly
        # Use same input colors as left scroll area for exact matching
        inputs_config = dialog_config.get('inputs', {})
        input_bg = inputs_config.get('background_color', [30, 30, 35])
        input_border = inputs_config.get('border_color', [60, 60, 65])
        
        # Apply table scrollbar styling using StyleManager
        from app.views.style import StyleManager
        StyleManager.style_table_scrollbar(
            self.visible_table,
            self.config,
            input_bg,
            input_border,
            table_style
        )
        
        # Set palette on table header to prevent macOS override
        header = self.visible_table.horizontalHeader()
        if header:
            header_palette = header.palette()
            header_palette.setColor(header.backgroundRole(), QColor(*table_header_bg))
            header_palette.setColor(header.foregroundRole(), QColor(*table_header_text))
            header.setPalette(header_palette)
            header.setAutoFillBackground(True)
        
        # Spinbox styling (use input styling from config)
        inputs_config = dialog_config.get('inputs', {})
        from app.utils.font_utils import resolve_font_family
        input_font_family_raw = inputs_config.get('font_family', 'Cascadia Mono')
        input_font_family = resolve_font_family(input_font_family_raw)
        input_font_size = scale_font_size(inputs_config.get('font_size', 11))
        input_text_color = inputs_config.get('text_color', [240, 240, 240])
        input_bg_color = inputs_config.get('background_color', [30, 30, 35])
        input_border_color = inputs_config.get('border_color', [60, 60, 65])
        input_border_radius = inputs_config.get('border_radius', 3)
        input_padding = inputs_config.get('padding', [8, 6])
        
        # Store spinbox style for later application
        self._spinbox_style = (
            f"QSpinBox {{"
            f"font-family: {input_font_family};"
            f"font-size: {input_font_size}pt;"
            f"color: rgb({input_text_color[0]}, {input_text_color[1]}, {input_text_color[2]});"
            f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
            f"border: 1px solid rgb({input_border_color[0]}, {input_border_color[1]}, {input_border_color[2]});"
            f"border-radius: {input_border_radius}px;"
            f"padding: {input_padding[1]}px {input_padding[0]}px;"
            f"}}"
        )
        
        # Apply to existing spinboxes
        for spinbox in self.findChildren(QSpinBox):
            spinbox.setStyleSheet(self._spinbox_style)
        
        # Group box styling
        groups_config = dialog_config.get('groups', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        group_title_font = resolve_font_family(groups_config.get('title_font_family', 'Helvetica Neue'))
        group_title_size = scale_font_size(groups_config.get('title_font_size', 11))
        group_title_color = groups_config.get('title_color', [240, 240, 240])
        content_margins = groups_config.get('content_margins', [10, 15, 10, 10])
        margin_top = groups_config.get('margin_top', 10)
        padding_top = groups_config.get('padding_top', 5)
        
        # Get group box border radius and title padding from config
        group_border_radius = groups_config.get('border_radius', 3)
        title_config = groups_config.get('title', {})
        title_padding_left = title_config.get('padding_left', 5)
        title_padding_right = title_config.get('padding_right', 5)
        
        group_style = (
            f"QGroupBox {{"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {group_border_radius}px;"
            f"margin-top: {margin_top}px;"
            f"padding-top: {padding_top}px;"
            f"}}"
            f"QGroupBox::title {{"
            f"subcontrol-origin: margin;"
            f"subcontrol-position: top left;"
            f"padding-left: {title_padding_left}px;"
            f"padding-right: {title_padding_right}px;"
            f"padding-top: {padding_top}px;"
            f"font-family: {group_title_font};"
            f"font-size: {group_title_size}pt;"
            f"color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
            layout = group.layout()
            if layout:
                layout.setContentsMargins(content_margins[0], content_margins[1], content_margins[2], content_margins[3])
    
    def _apply_spinbox_styling(self, spinbox: QSpinBox) -> None:
        """Apply styling to a spinbox widget."""
        if hasattr(self, '_spinbox_style'):
            spinbox.setStyleSheet(self._spinbox_style)


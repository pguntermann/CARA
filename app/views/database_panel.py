"""Database-Panel below Main-Panel and Detail-Panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableView
)
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtGui import QPalette, QColor, QPixmap, QPainter, QIcon, QBrush
from PyQt6.QtCore import Qt, QModelIndex, QTimer, QSize, QRect
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
import math

from app.models.database_model import DatabaseModel
from app.models.database_panel_model import DatabasePanelModel
from app.utils.font_utils import resolve_font_family, scale_font_size


class DatabasePanel(QWidget):
    """Database panel - can be collapsed if not needed."""
    
    def __init__(self, config: Dict[str, Any], panel_model: Optional[DatabasePanelModel] = None, 
                 on_row_double_click: Optional[Callable[[int], None]] = None,
                 on_add_tab_clicked: Optional[Callable[[], None]] = None) -> None:
        """Initialize the database panel.
        
        Args:
            config: Configuration dictionary.
            panel_model: Optional DatabasePanelModel to observe.
                       If provided, panel will automatically update when model changes.
            on_row_double_click: Optional callback function called when a row is double-clicked.
                               Receives the row index as argument.
            on_add_tab_clicked: Optional callback function called when the "+" tab is clicked.
                              Should trigger the open PGN database dialog.
        """
        super().__init__()
        self.config = config
        self._panel_model: Optional[DatabasePanelModel] = None
        self._on_row_double_click = on_row_double_click
        self._on_add_tab_clicked = on_add_tab_clicked
        # Map DatabaseModel instances to tab indices: {DatabaseModel: tab_index}
        self._model_to_tab: Dict[DatabaseModel, int] = {}
        # Track tabs and their models: {tab_index: {'model': DatabaseModel, 'file_path': str, 'table': QTableView, 'identifier': str}}
        self._tab_models: Dict[int, Dict[str, Any]] = {}
        
        # Animation state for pulsing unsaved indicator
        self._pulse_timer: Optional[QTimer] = None
        self._pulse_frame: int = 0  # Current animation frame (0-3)
        self._pulse_interval_ms: int = 120  # Update interval for smooth pulse (~8 FPS)
        self._unsaved_tabs: set = set()  # Set of tab indices with unsaved changes
        
        self._setup_ui()
        
        # Connect to panel model if provided
        if panel_model:
            self.set_panel_model(panel_model)
    
    def _setup_ui(self) -> None:
        """Setup the database panel UI."""
        # Main vertical layout
        main_layout = QVBoxLayout(self)
        ui_config = self.config.get('ui', {})
        
        # Get margins from config
        margins = ui_config.get('margins', {}).get('database_panel', [5, 5, 5, 5])
        main_layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        main_layout.setSpacing(0)
        
        # Get panel config
        panel_config = ui_config.get('panels', {}).get('database', {})
        
        # Tab widget for database tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(False)  # Disable document mode for better control
        main_layout.addWidget(self.tab_widget, 1)  # Takes remaining space
        
        # Apply tab styling from config
        self._apply_tab_styling()
        
        # Setup pulse animation timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse_animation)
        self._pulse_timer.setInterval(self._pulse_interval_ms)
        
        # Initialize tabs: "Clipboard" first, "+" last
        self._initialize_tabs()
        
        # Configure QTabBar after tabs are added
        self._configure_tab_bar()
        
        # Set minimum size so widget is visible
        # Store minimum height for expanding, but allow override when collapsed
        min_width = panel_config.get('minimum_width', 200)
        self._min_height_expanded = panel_config.get('minimum_height', 40)
        self.setMinimumSize(min_width, self._min_height_expanded)
        
        # Set background color from config using palette
        debug_config = self.config.get("debug", {})
        if debug_config.get("enable_debug_backgrounds", False):
            # Use debug background color
            color = debug_config.get("background_color_debug_databasepanel", [255, 255, 255])
        else:
            # Use normal background color
            color = panel_config.get("background_color", [35, 35, 40])
        
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(color[0], color[1], color[2]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
    
    def _apply_tab_styling(self) -> None:
        """Apply styling to the tab widget based on configuration."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('database', {})
        tabs_config = panel_config.get('tabs', {})
        
        # Get font settings
        font_family = resolve_font_family(tabs_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(tabs_config.get('font_size', 10))
        tab_height = tabs_config.get('tab_height', 24)
        pane_bg = tabs_config.get('pane_background', [35, 35, 40])
        
        # Get color settings
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        hover = colors_config.get('hover', {})
        active = colors_config.get('active', {})
        
        # Normal state colors
        norm_bg = normal.get('background', [45, 45, 50])
        norm_text = normal.get('text', [200, 200, 200])
        norm_border = normal.get('border', [60, 60, 65])
        
        # Hover state colors
        hover_bg = hover.get('background', [55, 55, 60])
        hover_text = hover.get('text', [230, 230, 230])
        hover_border = hover.get('border', [80, 80, 85])
        
        # Active state colors
        active_bg = active.get('background', [70, 90, 130])
        active_text = active.get('text', [240, 240, 240])
        active_border = active.get('border', [100, 120, 160])
        
        # Scroll button color
        scroll_button_color = tabs_config.get('scroll_button_color', [30, 30, 30])
        
        # Create stylesheet
        stylesheet = f"""
            QTabWidget::pane {{
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
            }}
            
            QTabBar {{
                alignment: left;
            }}
            
            QTabBar::tab {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                min-width: 80px;
                height: {tab_height}px;
                font-family: "{font_family}";
                font-size: {font_size}pt;
                margin-right: 2px;
            }}
            
            QTabBar::tab:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
                border-color: rgb({hover_border[0]}, {hover_border[1]}, {hover_border[2]});
            }}
            
            QTabBar::tab:selected {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
                border-color: rgb({active_border[0]}, {active_border[1]}, {active_border[2]});
                font-weight: 500;
            }}
            
            QTabBar::tab:!selected {{
                margin-top: 2px;
            }}
            
            QTabBar::tab:first:selected {{
                margin-left: 0px;
            }}
            
            QTabBar::tab:last:selected {{
                margin-right: 0px;
            }}
            
            QTabBar QToolButton {{
                background-color: rgb({scroll_button_color[0]}, {scroll_button_color[1]}, {scroll_button_color[2]});
                border: none;
            }}
            
            QTabBar QToolButton:hover {{
                background-color: rgb({scroll_button_color[0]}, {scroll_button_color[1]}, {scroll_button_color[2]});
            }}
            
            QTabBar QToolButton:pressed {{
                background-color: rgb({scroll_button_color[0]}, {scroll_button_color[1]}, {scroll_button_color[2]});
            }}
        """
        
        self.tab_widget.setStyleSheet(stylesheet)
    
    def _configure_tab_bar(self) -> None:
        """Configure QTabBar for macOS compatibility (left-aligned, content-sized tabs)."""
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setExpanding(False)  # Allow tabs to size to content instead of filling space
        tab_bar.setElideMode(Qt.TextElideMode.ElideNone)  # Prevent text truncation
        tab_bar.setUsesScrollButtons(True)  # Enable scroll buttons when tabs don't fit
        tab_bar.setDrawBase(False)  # Don't draw base line
    
    def _initialize_tabs(self) -> None:
        """Initialize the database panel tabs."""
        # Get column widths from config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('database', {})
        widths_config = panel_config.get('table', {}).get('column_widths', {})
        self._column_widths = [
            widths_config.get('col_num', 50),
            widths_config.get('col_unsaved', 25),  # Narrow column for unsaved indicator icon (second column)
            widths_config.get('col_white', 170),
            widths_config.get('col_black', 170),
            widths_config.get('col_white_elo', 80),
            widths_config.get('col_black_elo', 80),
            widths_config.get('col_result', 70),
            widths_config.get('col_date', 110),
            widths_config.get('col_event', 150),
            widths_config.get('col_site', 150),
            widths_config.get('col_moves', 65),
            widths_config.get('col_eco', 65),
            widths_config.get('col_analyzed', 70),
            widths_config.get('col_annotated', 70),
            widths_config.get('col_source_db', 120),
            # col_pgn stretches, no width needed
        ]
        
        # "+" tab (always last) for adding new tabs
        add_tab_widget = QWidget()
        self.tab_widget.addTab(add_tab_widget, "+")
        
        # Store reference to the add tab index
        self._add_tab_index = 0  # Index of the "+" tab (will be updated as databases are added)
        
        # Connect tab change signal to handle "+" tab clicks
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
    
    def set_panel_model(self, panel_model: DatabasePanelModel) -> None:
        """Set the database panel model to observe.
        
        Args:
            panel_model: The DatabasePanelModel instance to observe.
        """
        if self._panel_model:
            # Disconnect from old model
            self._panel_model.active_database_changed.disconnect(self._on_active_database_changed)
            self._panel_model.database_added.disconnect(self._on_database_added)
            self._panel_model.database_removed.disconnect(self._on_database_removed)
            self._panel_model.database_unsaved_changed.disconnect(self._on_database_unsaved_changed)
        
        self._panel_model = panel_model
        
        # Connect to panel model signals
        panel_model.active_database_changed.connect(self._on_active_database_changed)
        panel_model.database_added.connect(self._on_database_added)
        panel_model.database_removed.connect(self._on_database_removed)
        panel_model.database_unsaved_changed.connect(self._on_database_unsaved_changed)
        
        # Initialize UI with existing databases
        all_databases = panel_model.get_all_databases()
        for identifier, info in all_databases.items():
            self._add_database_tab(info.model, info.file_path, identifier)
        
        # Set active database tab
        active_database = panel_model.get_active_database()
        if active_database:
            self._set_active_tab_for_database(active_database)
    
    def _on_active_database_changed(self, database: Optional[DatabaseModel]) -> None:
        """Handle active database change from panel model.
        
        Args:
            database: The active DatabaseModel instance, or None.
        """
        if database:
            self._set_active_tab_for_database(database)
    
    def _on_database_added(self, identifier: str, info) -> None:
        """Handle database added signal from panel model.
        
        Args:
            identifier: Database identifier.
            info: DatabaseInfo instance.
        """
        self._add_database_tab(info.model, info.file_path, identifier)
    
    def _on_database_removed(self, identifier: str) -> None:
        """Handle database removed signal from panel model.
        
        Args:
            identifier: Database identifier.
        """
        # Find tab index for this identifier
        tab_index = None
        for idx, tab_info in self._tab_models.items():
            if tab_info.get('identifier') == identifier:
                tab_index = idx
                break
        
        if tab_index is not None:
            # Remove the tab (controller already handled setting the new active database)
            self._remove_database_tab(tab_index)
    
    def _on_database_unsaved_changed(self, identifier: str, has_unsaved: bool) -> None:
        """Handle database unsaved changes signal from panel model.
        
        Args:
            identifier: Database identifier.
            has_unsaved: True if database has unsaved changes, False otherwise.
        """
        # Find tab index for this identifier
        tab_index = None
        for idx, tab_info in self._tab_models.items():
            if tab_info.get('identifier') == identifier:
                tab_index = idx
                break
        
        if tab_index is not None:
            self._update_tab_unsaved_indicator(tab_index, has_unsaved)
    
    def _set_active_tab_for_database(self, database: DatabaseModel) -> None:
        """Set the active tab for a given database model.
        
        Args:
            database: DatabaseModel instance to activate.
        """
        tab_index = self._model_to_tab.get(database)
        if tab_index is not None:
            self.tab_widget.setCurrentIndex(tab_index)
    
    def _add_database_tab(self, model: DatabaseModel, file_path: Optional[str], identifier: str) -> int:
        """Add a database tab to the UI.
        
        Args:
            model: DatabaseModel instance.
            file_path: Optional file path (None for clipboard).
            identifier: Database identifier.
            
        Returns:
            Tab index of the newly created tab.
        """
        # Check if tab already exists for this model
        if model in self._model_to_tab:
            return self._model_to_tab[model]
        
        # Create widget and layout for the tab
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        
        # Create table view for this tab
        tab_table = QTableView()
        tab_layout.addWidget(tab_table)
        
        # Configure selection mode for multi-row selection (shift+click support)
        from PyQt6.QtWidgets import QAbstractItemView
        tab_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tab_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Set model on table view
        tab_table.setModel(model)
        
        # Enable sorting on the table view
        tab_table.setSortingEnabled(True)
        
        # Connect to model's dataChanged signal to refresh view immediately
        model.dataChanged.connect(self._on_model_data_changed)
        
        # Configure column widths and resize modes
        header = tab_table.horizontalHeader()
        column_count = model.columnCount()
        
        # Make unsaved column (index 1) non-sortable
        header.setSortIndicatorShown(True)
        # Note: We can't directly disable sorting for a specific column in Qt,
        # but the model's sort() method will ignore COL_UNSAVED
        
        # Set widths for columns that have width definitions
        for i in range(min(len(self._column_widths), column_count)):
            header.setSectionResizeMode(i, header.ResizeMode.Interactive)
            header.resizeSection(i, self._column_widths[i])
        
        # Unsaved column (second column, index 1) should be fixed width
        if column_count > 1:
            header.setSectionResizeMode(1, header.ResizeMode.Fixed)
        
        # Last column (PGN) stretches to fill remaining space
        if column_count > 0:
            header.setSectionResizeMode(column_count - 1, header.ResizeMode.Stretch)
        
        # Hide Source DB column for non-search-results tabs
        if identifier != 'search_results':
            source_db_col = model.COL_SOURCE_DB
            if source_db_col < column_count:
                tab_table.setColumnHidden(source_db_col, True)
        
        # Apply styling
        self._configure_table_styling_for_table(tab_table)
        
        # Set delegate for PGN column
        from PyQt6.QtWidgets import QStyledItemDelegate
        from PyQt6.QtCore import Qt
        
        class PgnColumnDelegate(QStyledItemDelegate):
            """Delegate for PGN column that formats text for display."""
            def paint(self, painter, option, index):
                option.textElideMode = Qt.TextElideMode.ElideNone
                super().paint(painter, option, index)
            
            def displayText(self, value, locale):
                if value is None:
                    return ""
                text = str(value)
                return text.replace('\n', ' ').replace('\r', ' ')
        
        pgn_column = model.COL_PGN
        tab_table.setItemDelegateForColumn(pgn_column, PgnColumnDelegate())
        tab_table.setWordWrap(True)
        
        # Connect double-click signal
        tab_table.doubleClicked.connect(self._on_table_double_click)
        
        # Force table to update and show all columns
        tab_table.update()
        tab_table.viewport().update()
        
        # Determine tab label
        if file_path:
            tab_label = Path(file_path).stem
        else:
            tab_label = "Clipboard"
        
        # Insert tab before the "+" tab
        tab_index = self._add_tab_index
        self.tab_widget.insertTab(tab_index, tab_widget, tab_label)
        
        # Check if database has unsaved changes and set icon
        if self._panel_model:
            db_info = self._panel_model.get_database(identifier)
            if db_info and db_info.has_unsaved_changes:
                self._set_tab_unsaved_indicator(tab_index, True)
        
        # Store mappings
        self._tab_models[tab_index] = {
            'model': model,
            'file_path': file_path,
            'table': tab_table,
            'identifier': identifier
        }
        self._model_to_tab[model] = tab_index
        
        # Update add tab index (it's now one position later)
        self._add_tab_index += 1
        
        # Reconfigure tab bar after adding new tab
        self._configure_tab_bar()
        
        return tab_index
    
    def add_search_results_tab(self, model: DatabaseModel) -> int:
        """Add a search results tab to the UI.
        
        Args:
            model: DatabaseModel instance containing search results.
            
        Returns:
            Tab index of the newly created tab.
        """
        # Check if "Search Results" tab already exists
        for tab_idx, tab_data in self._tab_models.items():
            if tab_data.get('identifier') == 'search_results':
                # Update existing tab
                tab_data['model'] = model
                tab_table = tab_data['table']
                tab_table.setModel(model)
                # Ensure Source DB column is visible for search results
                source_db_col = model.COL_SOURCE_DB
                tab_table.setColumnHidden(source_db_col, False)
                # Refresh the view
                tab_table.update()
                tab_table.viewport().update()
                # Switch to the tab
                self.tab_widget.setCurrentIndex(tab_idx)
                return tab_idx
        
        # Create new search results tab
        identifier = "search_results"
        tab_index = self._add_database_tab(model, None, identifier)
        
        # Update tab label to "Search Results"
        self.tab_widget.setTabText(tab_index, "Search Results")
        
        # Ensure Source DB column is visible for search results
        tab_data = self._tab_models.get(tab_index)
        if tab_data:
            tab_table = tab_data.get('table')
            if tab_table:
                source_db_col = model.COL_SOURCE_DB
                tab_table.setColumnHidden(source_db_col, False)
        
        return tab_index
    
    def _remove_database_tab(self, tab_index: int) -> None:
        """Remove a database tab from the UI.
        
        Args:
            tab_index: Index of the tab to remove.
        """
        if tab_index not in self._tab_models:
            return
        
        tab_info = self._tab_models[tab_index]
        model = tab_info['model']
        
        # Remove from unsaved tabs tracking if present
        self._unsaved_tabs.discard(tab_index)
        
        # Remove from mappings
        # Note: Search results tabs are not in _model_to_tab, so check first
        if model in self._model_to_tab:
            del self._model_to_tab[model]
        del self._tab_models[tab_index]
        
        # Remove the tab from the widget
        self.tab_widget.removeTab(tab_index)
        
        # Stop animation if no unsaved tabs remain
        if not self._unsaved_tabs and self._pulse_timer.isActive():
            self._pulse_timer.stop()
        
        # Update add tab index (it's now one position earlier)
        self._add_tab_index -= 1
        
        # Update indices for all tabs after the removed one
        new_tab_models = {}
        new_model_to_tab = {}
        new_unsaved_tabs = set()
        for old_idx, tab_info in self._tab_models.items():
            if old_idx < tab_index:
                # Before removed tab - keep same index
                new_tab_models[old_idx] = tab_info
                new_model_to_tab[tab_info['model']] = old_idx
                if old_idx in self._unsaved_tabs:
                    new_unsaved_tabs.add(old_idx)
            elif old_idx > tab_index:
                # After removed tab - decrement index
                new_idx = old_idx - 1
                new_tab_models[new_idx] = tab_info
                new_model_to_tab[tab_info['model']] = new_idx
                if old_idx in self._unsaved_tabs:
                    new_unsaved_tabs.add(new_idx)
        
        self._tab_models = new_tab_models
        self._model_to_tab = new_model_to_tab
        self._unsaved_tabs = new_unsaved_tabs
    
    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change event.
        
        Args:
            index: Index of the newly selected tab.
        """
        # If the "+" tab is clicked, trigger the open PGN database callback
        if index == self._add_tab_index and self._on_add_tab_clicked:
            # Switch back to the previous tab (or Clipboard if no previous tab)
            if self._add_tab_index > 1:
                # There's at least one other tab before the "+" tab
                self.tab_widget.setCurrentIndex(self._add_tab_index - 1)
            else:
                # Only Clipboard and "+" tabs exist, switch to Clipboard
                self.tab_widget.setCurrentIndex(0)
            
            # Trigger the open PGN database callback
            self._on_add_tab_clicked()
        else:
            # Update active database in panel model when user changes tabs
            # (but not for search results tabs, which aren't in the panel model)
            if self._panel_model and index in self._tab_models:
                tab_info = self._tab_models[index]
                identifier = tab_info.get('identifier')
                # Only update active database for real databases, not search results
                if identifier != 'search_results':
                    model = tab_info['model']
                    self._panel_model.set_active_database(model)
    
    def get_active_database_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently active database.
        
        Returns:
            Dictionary with 'model', 'file_path', 'table', 'identifier' keys, or None if no valid database.
        """
        # First, check the current tab index (works for search results too)
        current_index = self.tab_widget.currentIndex()
        if current_index in self._tab_models:
            return self._tab_models[current_index]
        
        # Fallback: use panel model (for regular databases)
        if not self._panel_model:
            return None
        
        active_database = self._panel_model.get_active_database()
        if not active_database:
            return None
        
        tab_index = self._model_to_tab.get(active_database)
        if tab_index is not None and tab_index in self._tab_models:
            return self._tab_models[tab_index]
        return None
    
    def mark_database_unsaved(self, model: DatabaseModel) -> None:
        """Mark a database as having unsaved changes.
        
        Args:
            model: DatabaseModel instance to mark as unsaved.
        """
        if self._panel_model:
            self._panel_model.mark_database_unsaved(model)
    
    def get_selected_game_indices(self) -> List[int]:
        """Get selected game row indices from the active database table.
        
        Returns:
            List of selected row indices (empty list if no selection).
        """
        active_info = self.get_active_database_info()
        if not active_info:
            return []
        
        table = active_info.get('table')
        if not table:
            return []
        
        # Get selected indexes from the table's selection model
        selection_model = table.selectionModel()
        if not selection_model:
            return []
        
        # Get all selected indexes (works with ExtendedSelection mode)
        selected_indexes = selection_model.selectedIndexes()
        # Extract unique row indices (since we're in row selection mode, all columns of a row are selected)
        row_indices = sorted(set(index.row() for index in selected_indexes))
        
        return row_indices
    
    def highlight_row(self, database: DatabaseModel, row_index: int) -> None:
        """Highlight a specific row in a specific database's table.
        
        Args:
            database: DatabaseModel instance.
            row_index: Index of the row to highlight.
        """
        self.highlight_rows(database, [row_index])
    
    def highlight_rows(self, database: DatabaseModel, row_indices: List[int]) -> None:
        """Highlight multiple rows in a specific database's table and sort them to the top.
        
        Args:
            database: DatabaseModel instance.
            row_indices: List of row indices to highlight.
        """
        tab_index = self._model_to_tab.get(database)
        if tab_index is None or tab_index not in self._tab_models:
            return
        
        tab_info = self._tab_models[tab_index]
        table = tab_info.get('table')
        model = tab_info.get('model')
        
        if not table or not model:
            return
        
        # Filter to valid row indices
        valid_indices = [idx for idx in row_indices if 0 <= idx < model.rowCount()]
        if not valid_indices:
            return
        
        # Switch to this database tab
        self.tab_widget.setCurrentIndex(tab_index)
        
        # Set active database in panel model
        if self._panel_model:
            self._panel_model.set_active_database(database)
        
        # Sort games to bring highlighted ones to the top
        # We'll use a custom sort that puts highlighted games first
        highlighted_games = [model.get_game(idx) for idx in valid_indices]
        if highlighted_games:
            model.sort_games_to_top(highlighted_games)
        
        # Update row indices after sorting (games may have moved)
        updated_indices = []
        for game in highlighted_games:
            new_idx = model.find_game(game)
            if new_idx is not None:
                updated_indices.append(new_idx)
        
        if not updated_indices:
            return
        
        # Clear existing selection
        table.clearSelection()
        
        # Select all highlighted rows
        selection_model = table.selectionModel()
        if selection_model:
            for row_idx in updated_indices:
                # Select entire row
                for col in range(model.columnCount()):
                    index = model.index(row_idx, col)
                    selection_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        
        # Scroll to the first highlighted row
        if updated_indices:
            first_col_index = model.index(updated_indices[0], 0)
            table.scrollTo(first_col_index, QTableView.ScrollHint.EnsureVisible)
    
    def update_tab_file_path(self, tab_index: int, file_path: str) -> None:
        """Update the file path for a specific tab.
        
        Args:
            tab_index: Index of the tab to update.
            file_path: New file path.
        """
        if tab_index in self._tab_models:
            self._tab_models[tab_index]['file_path'] = file_path
            # Update tab label with new file name
            file_name = Path(file_path).stem
            self.tab_widget.setTabText(tab_index, file_name)
            
            # Update unsaved indicator if needed
            if self._panel_model:
                identifier = self._tab_models[tab_index].get('identifier')
                if identifier:
                    db_info = self._panel_model.get_database(identifier)
                    if db_info:
                        self._set_tab_unsaved_indicator(tab_index, db_info.has_unsaved_changes)
    
    def _create_pulse_pixmap(self, opacity: float) -> QPixmap:
        """Create a pixmap with a circle at the specified opacity.
        
        Args:
            opacity: Opacity value from 0.0 to 1.0.
            
        Returns:
            QPixmap with the circle icon.
        """
        # Icon size - small circle that fits in tab
        size = 8
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get tab text color for the circle (use a visible color)
        # Use a light color that works on dark backgrounds
        circle_color = QColor(255, 200, 100)  # Orange/yellow for visibility
        circle_color.setAlphaF(opacity)
        
        # Draw circle centered in pixmap
        margin = 1
        circle_rect = QRect(margin, margin, size - 2 * margin, size - 2 * margin)
        painter.setBrush(QBrush(circle_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle_rect)
        
        painter.end()
        return pixmap
    
    def _get_pulse_opacity(self, frame: int) -> float:
        """Get opacity value for current pulse frame.
        
        Uses a sine wave for smooth pulsing animation.
        
        Args:
            frame: Current animation frame (0-3 for 4-frame cycle).
            
        Returns:
            Opacity value from 0.3 to 1.0.
        """
        # Use sine wave: sin goes from -1 to 1, we want 0.3 to 1.0
        # Map frame (0-3) to angle (0 to 2π)
        angle = (frame / 4.0) * 2 * math.pi
        sine_value = math.sin(angle)
        # Map sine (-1 to 1) to opacity (0.3 to 1.0)
        opacity = 0.65 + 0.35 * sine_value
        return opacity
    
    def _set_tab_unsaved_indicator(self, tab_index: int, has_unsaved: bool) -> None:
        """Set or remove the unsaved changes indicator icon on a tab.
        
        Args:
            tab_index: Index of the tab to update.
            has_unsaved: True to show pulsing indicator, False to remove it.
        """
        if tab_index not in self._tab_models:
            return
        
        if has_unsaved:
            # Add to unsaved tabs set and start animation if needed
            self._unsaved_tabs.add(tab_index)
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
            # Set initial icon
            self._update_tab_icon(tab_index)
        else:
            # Remove from unsaved tabs set
            self._unsaved_tabs.discard(tab_index)
            # Remove icon
            self.tab_widget.setTabIcon(tab_index, QIcon())
            # Stop animation if no unsaved tabs
            if not self._unsaved_tabs and self._pulse_timer.isActive():
                self._pulse_timer.stop()
    
    def _update_tab_icon(self, tab_index: int) -> None:
        """Update the icon for a tab based on current pulse frame.
        
        Args:
            tab_index: Index of the tab to update.
        """
        if tab_index not in self._unsaved_tabs:
            return
        
        opacity = self._get_pulse_opacity(self._pulse_frame)
        pixmap = self._create_pulse_pixmap(opacity)
        icon = QIcon(pixmap)
        self.tab_widget.setTabIcon(tab_index, icon)
    
    def _update_pulse_animation(self) -> None:
        """Update pulse animation frame and refresh icons."""
        # Cycle through 4 frames (0, 1, 2, 3) for smooth pulse
        self._pulse_frame = (self._pulse_frame + 1) % 4
        
        # Update icons for all unsaved tabs
        for tab_index in list(self._unsaved_tabs):
            self._update_tab_icon(tab_index)
    
    def _update_tab_unsaved_indicator(self, tab_index: int, has_unsaved: bool) -> None:
        """Update the unsaved changes indicator on a tab.
        
        Args:
            tab_index: Index of the tab to update.
            has_unsaved: True to show indicator, False to hide it.
        """
        self._set_tab_unsaved_indicator(tab_index, has_unsaved)
    
    def _on_table_double_click(self, index: QModelIndex) -> None:
        """Handle double-click on table row.
        
        Args:
            index: Model index of the clicked cell.
        """
        if not index.isValid() or not self._on_row_double_click:
            return
        
        row = index.row()
        # Get the current tab's model to determine which database to use
        current_tab_index = self.tab_widget.currentIndex()
        if current_tab_index in self._tab_models:
            model = self._tab_models[current_tab_index]['model']
            # Call the callback with row and model
            import inspect
            sig = inspect.signature(self._on_row_double_click)
            if len(sig.parameters) > 1:
                self._on_row_double_click(row, model)
            else:
                self._on_row_double_click(row)
        else:
            # Fallback: use default model if tab not found
            self._on_row_double_click(row)
    
    def _on_model_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles: list = None) -> None:
        """Handle dataChanged signal from model to refresh the view.
        
        Qt's QTableView automatically updates when dataChanged is emitted,
        so no manual repaint is necessary. This method is kept for potential
        future custom handling if needed.
        
        Args:
            top_left: Top-left index of changed data.
            bottom_right: Bottom-right index of changed data.
            roles: List of data roles that changed.
        """
        # Qt's model/view architecture automatically handles view updates
        # when dataChanged signal is emitted. No manual intervention needed.
        pass
    
    def refresh_table_for_model(self, model: DatabaseModel) -> None:
        """Refresh all table views that use the specified model.
        
        Qt's QTableView automatically updates when dataChanged is emitted,
        so this method just ensures updates are enabled. If a manual refresh
        is truly needed, use update() instead of repaint() for asynchronous updates.
        
        Args:
            model: DatabaseModel instance to refresh views for.
        """
        # Find all table views using this model
        for tab_info in self._tab_models.values():
            if tab_info['model'] is model:
                table = tab_info['table']
                if table and table.isVisible():
                    # Ensure updates are enabled (Qt will handle the actual repaint)
                    table.setUpdatesEnabled(True)
                    # Schedule an update (asynchronous, non-blocking)
                    table.update()
    
    def _configure_table_styling_for_table(self, table: QTableView) -> None:
        """Configure table view styling for dark theme.
        
        Args:
            table: QTableView instance to style.
        """
        ui_config = self.config.get('ui', {})
        tabs_config = ui_config.get('panels', {}).get('database', {}).get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [35, 35, 40])
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        norm_text = normal.get('text', [200, 200, 200])
        
        stylesheet = f"""
            QTableView {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                gridline-color: rgb(60, 60, 65);
                selection-background-color: rgb(70, 90, 130);
                selection-color: rgb(240, 240, 240);
            }}
            QHeaderView::section {{
                background-color: rgb(45, 45, 50);
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                padding: 4px;
                border: 1px solid rgb(60, 60, 65);
                font-weight: 500;
            }}
        """
        table.setStyleSheet(stylesheet)
    
    
    def set_collapsed_state(self, is_collapsed: bool) -> None:
        """Update the panel content visibility based on collapsed state.

        Args:
            is_collapsed: True if panel is collapsed, False if expanded.
        """
        # Adjust minimum height and content visibility based on collapsed state
        # When collapsed, allow smaller minimum height to honor collapsed_height config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('database', {})
        min_width = panel_config.get('minimum_width', 200)

        if is_collapsed:
            # Use collapsed height - hide tab widget, use fixed height to force collapse
            collapsed_height = panel_config.get('collapsed_height', 1)
            self.tab_widget.setVisible(False)
            # Use setFixedHeight to force exact collapsed height, bypassing layout constraints
            self.setFixedHeight(collapsed_height)
            self.setMinimumHeight(0)  # Allow even smaller
        else:
            # Restore normal state when expanded
            self.tab_widget.setVisible(True)
            self.setMinimumHeight(self._min_height_expanded)
            self.setMaximumHeight(16777215)  # Reset fixed height (Qt's default max)


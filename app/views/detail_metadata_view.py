"""Metadata view for detail panel."""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, 
                             QPushButton, QDialog, QLabel, QLineEdit, QDialogButtonBox,
                             QFormLayout, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPalette, QColor
from typing import Dict, Any, Optional, List, Tuple

from app.models.metadata_model import MetadataModel
from app.models.game_model import GameModel
from app.models.database_model import DatabaseModel
import chess.pgn
import io

# Standard PGN tags in order of importance
# These are the most commonly used and important tags in PGN format
STANDARD_TAGS_ORDER = [
    # Core game identification (most important)
    "Event",
    "Site",
    "Date",
    "Round",
    "White",
    "Black",
    "Result",
    # Game characteristics
    "ECO",
    "WhiteElo",
    "BlackElo",
    "TimeControl",
    # Player information
    "WhiteTitle",
    "BlackTitle",
    "WhiteFideId",
    "BlackFideId",
    "WhiteTeam",
    "BlackTeam",
    # Game metadata
    "PlyCount",
    "EventDate",
    "SetUp",
    "FEN",
    # Common additional tags
    "Termination",
    "Annotator",
    "UTCDate",
    "UTCTime",
]


class DetailMetadataView(QWidget):
    """Metadata view displaying game headers in a table."""
    
    def __init__(self, config: Dict[str, Any], metadata_model: Optional[MetadataModel] = None,
                 game_model: Optional[GameModel] = None,
                 database_model: Optional[DatabaseModel] = None,
                 database_panel = None) -> None:
        """Initialize the metadata view.
        
        Args:
            config: Configuration dictionary.
            metadata_model: Optional MetadataModel to observe.
                          If provided, view will automatically update when model changes.
            game_model: Optional GameModel to observe for active game changes.
            database_model: Optional DatabaseModel to update when metadata changes.
            database_panel: Optional DatabasePanel instance to refresh views after updates.
        """
        super().__init__()
        self.config = config
        self._metadata_model: Optional[MetadataModel] = None
        self._game_model: Optional[GameModel] = None
        self._database_model: Optional[DatabaseModel] = None
        self._database_panel = database_panel
        self._setup_ui()
        
        # Connect to models if provided
        if metadata_model:
            self.set_model(metadata_model)
        
        if game_model:
            self.set_game_model(game_model)
        
        if database_model:
            self.set_database_model(database_model)
    
    def _setup_ui(self) -> None:
        """Setup the metadata view UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Get button config to use bottom margin as spacing between button bar and table
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        metadata_config = panel_config.get('metadata', {})
        button_config = metadata_config.get('button', {})
        margins = button_config.get('margins', [8, 8, 8, 8])
        # Use bottom margin from button config as spacing between button bar and table
        layout.setSpacing(margins[2] if len(margins) > 2 else 8)
        
        # Create button bar
        button_bar = self._create_button_bar()
        layout.addWidget(button_bar)
        
        # Create table view
        self.metadata_table = QTableView()
        layout.addWidget(self.metadata_table)
        
        # Get column widths from config (will be set when model is connected)
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        metadata_config = panel_config.get('metadata', {})
        widths_config = metadata_config.get('table', {}).get('column_widths', {})
        self._column_widths = [
            widths_config.get('col_name', 150),
            widths_config.get('col_value', 200),
        ]
        
        # Model will be set via set_model() method
        # Column widths and resize modes will be configured when model is set
        
        # Configure table view appearance for dark theme
        self._configure_table_styling()
    
    def _create_button_bar(self) -> QWidget:
        """Create the button bar with Add Tag button.
        
        Returns:
            QWidget containing the button bar.
        """
        from PyQt6.QtWidgets import QFrame
        
        button_bar = QFrame()
        layout = QHBoxLayout(button_bar)
        
        # Get button config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        metadata_config = panel_config.get('metadata', {})
        button_config = metadata_config.get('button', {})
        
        margins = button_config.get('margins', [8, 8, 8, 8])
        spacing = button_config.get('spacing', 8)
        layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        layout.setSpacing(spacing)
        
        # Add button
        self.add_tag_button = QPushButton("Add")
        layout.addWidget(self.add_tag_button)
        
        # Remove button
        self.remove_tag_button = QPushButton("Remove")
        layout.addWidget(self.remove_tag_button)
        
        # Add stretch to push buttons to the left
        layout.addStretch()
        
        # Connect button signals
        self.add_tag_button.clicked.connect(self._on_add_tag_clicked)
        self.remove_tag_button.clicked.connect(self._on_remove_tag_clicked)
        
        # Apply consistent styling to match other detail views
        self._apply_button_styling()
        
        return button_bar

    def _apply_button_styling(self) -> None:
        """Apply shared detail-panel button styling to metadata buttons using StyleManager."""
        if not hasattr(self, "add_tag_button") or not hasattr(self, "remove_tag_button"):
            return
        
        ui_config = self.config.get('ui', {})
        detail_config = ui_config.get('panels', {}).get('detail', {})
        metadata_button_config = detail_config.get('metadata', {}).get('button', {})
        tabs_config = detail_config.get('tabs', {})
        
        # Get base background color from view (pane_background)
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        button_height = metadata_button_config.get('height', 28)
        border_color = metadata_button_config.get('border_color', [60, 60, 65])
        
        # Calculate background offset from button_config if available
        # If button_config has explicit background_color, calculate offset from pane_bg
        button_bg_color = metadata_button_config.get('background_color', [50, 50, 55])
        background_offset = button_bg_color[0] - pane_bg[0] if button_bg_color[0] > pane_bg[0] else 20
        
        bg_color_list = [pane_bg[0], pane_bg[1], pane_bg[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        # Apply button styling using StyleManager
        from app.views.style import StyleManager
        StyleManager.style_buttons(
            [self.add_tag_button, self.remove_tag_button],
            self.config,
            bg_color_list,
            border_color_list,
            background_offset=background_offset,
            min_height=button_height
        )
        # Set max height manually (StyleManager doesn't support max_height)
        for button in (self.add_tag_button, self.remove_tag_button):
            button.setMaximumHeight(button_height)
        
        # Ensure consistent width across metadata buttons
        width = max(
            self.add_tag_button.sizeHint().width(),
            self.remove_tag_button.sizeHint().width(),
        )
        self.add_tag_button.setFixedWidth(width)
        self.remove_tag_button.setFixedWidth(width)
    
    def _configure_table_styling(self) -> None:
        """Configure table view styling for dark theme."""
        ui_config = self.config.get('ui', {})
        tabs_config = ui_config.get('panels', {}).get('detail', {}).get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        norm_text = normal.get('text', [200, 200, 200])
        
        # Get table header colors from config (use same as moves list table)
        panel_config = ui_config.get('panels', {}).get('detail', {})
        moveslist_config = panel_config.get('moveslist', {})
        table_config = moveslist_config.get('table', {})
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
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                border: none;
            }}
        """
        self.metadata_table.setStyleSheet(stylesheet)
        
        # Apply scrollbar styling using StyleManager
        from app.views.style import StyleManager
        StyleManager.style_table_view_scrollbar(
            self.metadata_table,
            self.config,
            pane_bg,
            gridline_color,
            stylesheet
        )
        
        # Also set palette on header views to prevent macOS override
        horizontal_header = self.metadata_table.horizontalHeader()
        if horizontal_header:
            header_palette = horizontal_header.palette()
            header_palette.setColor(horizontal_header.backgroundRole(), header_bg_color)
            header_palette.setColor(horizontal_header.foregroundRole(), header_text_color)
            horizontal_header.setPalette(header_palette)
            horizontal_header.setAutoFillBackground(True)
        
        # Set palette on vertical header to prevent macOS override
        vertical_header = self.metadata_table.verticalHeader()
        if vertical_header:
            vertical_header_palette = vertical_header.palette()
            vertical_header_palette.setColor(vertical_header.backgroundRole(), header_bg_color)
            vertical_header_palette.setColor(vertical_header.foregroundRole(), header_text_color)
            vertical_header.setPalette(vertical_header_palette)
            vertical_header.setAutoFillBackground(True)
    
    def set_model(self, model: MetadataModel) -> None:
        """Set the metadata model to observe.
        
        Args:
            model: The MetadataModel instance to observe.
        """
        if self._metadata_model:
            # Disconnect from old model
            if hasattr(self._metadata_model, 'value_changed'):
                self._metadata_model.value_changed.disconnect(self._on_metadata_value_changed)
        
        self._metadata_model = model
        
        # Connect to model signals
        if hasattr(model, 'value_changed'):
            model.value_changed.connect(self._on_metadata_value_changed)
        if hasattr(model, 'tag_added'):
            model.tag_added.connect(self._on_tag_added)
        if hasattr(model, 'tag_removed'):
            model.tag_removed.connect(self._on_tag_removed)
        
        # Set config on model for styling
        if hasattr(model, '_config'):
            model._config = self.config
        
        # Set model on table view
        self.metadata_table.setModel(model)
        
        # Configure column widths and resize modes
        header = self.metadata_table.horizontalHeader()
        for i in range(len(self._column_widths)):
            header.setSectionResizeMode(i, header.ResizeMode.Interactive)
            header.resizeSection(i, self._column_widths[i])
        # Value column stretches to fill remaining space
        header.setSectionResizeMode(MetadataModel.COL_VALUE, header.ResizeMode.Stretch)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe for active game changes.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
            self._game_model.metadata_updated.disconnect(self._on_metadata_updated)
        
        self._game_model = model
        
        # Connect to model signals
        model.active_game_changed.connect(self._on_active_game_changed)
        model.metadata_updated.connect(self._on_metadata_updated)
        
        # Initialize with current active game if any
        if model.active_game:
            self._on_active_game_changed(model.active_game)
    
    def set_database_model(self, model: Optional[DatabaseModel]) -> None:
        """Set the database model to update when metadata changes.
        
        Args:
            model: The DatabaseModel instance to update.
        """
        self._database_model = model
    
    def _find_database_model_for_game(self, game) -> Optional[DatabaseModel]:
        """Find the database model that contains the given game.
        
        Args:
            game: GameData instance to find.
            
        Returns:
            DatabaseModel that contains the game, or None if not found.
        """
        # First try the stored database model
        if self._database_model and self._database_model.find_game(game) is not None:
            return self._database_model
        
        # If not found, search through all databases in the panel model
        if self._database_panel and hasattr(self._database_panel, '_panel_model'):
            panel_model = self._database_panel._panel_model
            if panel_model:
                all_databases = panel_model.get_all_databases()
                for identifier, info in all_databases.items():
                    if info.model.find_game(game) is not None:
                        return info.model
        
        return None
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change from model.
        
        Args:
            game: GameData instance or None.
        """
        if not self._metadata_model:
            return
        
        if game is None:
            # Clear metadata
            self._metadata_model.clear()
            return
        
        # Extract headers from game's PGN
        metadata = self._extract_metadata_from_game(game)
        
        # Update model with metadata
        self._metadata_model.set_metadata(metadata)
    
    def _on_metadata_updated(self) -> None:
        """Handle metadata update from model - refresh metadata display.
        
        This is called when metadata tags are added, edited, or removed.
        """
        if self._game_model and self._game_model.active_game:
            # Re-extract metadata from the updated game
            metadata = self._extract_metadata_from_game(self._game_model.active_game)
            # Update model with refreshed metadata
            if self._metadata_model:
                self._metadata_model.set_metadata(metadata)
    
    def _extract_metadata_from_game(self, game) -> list:
        """Extract metadata (headers) from a game.
        
        Args:
            game: GameData instance.
            
        Returns:
            List of (name, value) tuples sorted by importance:
            - Standard tags first (in predefined order)
            - Non-standard tags alphabetically after
        """
        metadata = []
        standard_tags = []
        non_standard_tags = []
        
        try:
            # Parse PGN to extract headers
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game:
                headers = chess_game.headers
                
                # Convert headers dict to list of (name, value) tuples
                # Separate standard and non-standard tags
                standard_tags_set = set(STANDARD_TAGS_ORDER)
                for name, value in headers.items():
                    if name in standard_tags_set:
                        standard_tags.append((name, value))
                    else:
                        non_standard_tags.append((name, value))
                
                # Sort standard tags by predefined order
                standard_tags.sort(key=lambda x: (
                    STANDARD_TAGS_ORDER.index(x[0]) if x[0] in STANDARD_TAGS_ORDER 
                    else len(STANDARD_TAGS_ORDER)
                ))
                
                # Sort non-standard tags alphabetically
                non_standard_tags.sort(key=lambda x: x[0])
                
                # Combine: standard tags first, then non-standard
                metadata = standard_tags + non_standard_tags
        except Exception:
            # On any error, return empty list
            pass
        
        return metadata
    
    def _on_metadata_value_changed(self, tag_name: str, new_value: str) -> None:
        """Handle metadata value change from model.
        
        Args:
            tag_name: Name of the tag that was edited.
            new_value: New value for the tag.
        """
        if not self._game_model or not self._game_model.active_game:
            return
        
        # Defer the PGN update until after editing is complete
        # This prevents "commitData called with an editor that does not belong to this view" warnings
        # Use a small delay (10ms) to ensure the editor is fully closed and the view is ready to receive updates
        QTimer.singleShot(10, lambda: self._update_game_pgn_after_edit(tag_name, new_value))
    
    def _update_game_pgn_after_edit(self, tag_name: str, new_value: str) -> None:
        """Update the game's PGN with the new metadata value.
        
        This is called after editing is complete to avoid conflicts with the active editor.
        
        Args:
            tag_name: Name of the tag that was edited.
            new_value: New value for the tag.
        """
        if not self._game_model or not self._game_model.active_game:
            return
        
        # Update the game's PGN with the new metadata value
        try:
            import chess.pgn
            from io import StringIO
            
            game = self._game_model.active_game
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game:
                # Update the header
                chess_game.headers[tag_name] = new_value
                
                # Regenerate the PGN text
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                new_pgn = chess_game.accept(exporter).strip()
                
                # Update the game's PGN
                game.pgn = new_pgn
                
                # Update corresponding GameData fields if this tag corresponds to a database column
                tag_to_field_mapping = {
                    "White": "white",
                    "Black": "black",
                    "Result": "result",
                    "Date": "date",
                    "ECO": "eco",
                    "Event": "event",
                    "Site": "site",
                    "WhiteElo": "white_elo",
                    "BlackElo": "black_elo",
                }
                
                # Special handling for CARAAnalysisData and CARAAnnotations tags (boolean fields)
                if tag_name == "CARAAnalysisData":
                    game.analyzed = bool(new_value) if new_value else False
                elif tag_name == "CARAAnnotations":
                    game.annotated = bool(new_value) if new_value else False
                elif tag_name in tag_to_field_mapping:
                    field_name = tag_to_field_mapping[tag_name]
                    setattr(game, field_name, new_value)
                
                # Find the database model that contains this game and update it
                # This ensures the PGN update is persisted when saving
                database_model = self._find_database_model_for_game(game)
                if database_model:
                    database_model.update_game(game)
                    # Mark database as having unsaved changes
                    if self._database_panel:
                        self._database_panel.mark_database_unsaved(database_model)
                
                # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
                self._game_model.metadata_updated.emit()
                
                # Refresh active game to update game info display (e.g., player names above chessboard)
                # This re-emits active_game_changed signal without resetting the move position
                self._game_model.refresh_active_game()
                
                # Note: We don't call set_metadata() again here because:
                # 1. The model already has the correct value (we just edited it)
                # 2. Calling set_metadata() would clear and re-insert all rows, which is unnecessary
                # 3. It could cause editor conflicts if called while editing
        except Exception:
            # On any error, silently ignore (don't break the UI)
            pass
    
    def _on_add_tag_clicked(self) -> None:
        """Handle Add Tag button click."""
        if not self._game_model or not self._game_model.active_game:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "No Game", "Please select a game first.", self)
            return
        
        # Show dialog to enter tag name and value
        dialog = AddTagDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            tag_name, tag_value = dialog.get_tag_info()
            if tag_name:
                # Add tag to model
                if self._metadata_model and self._metadata_model.add_tag(tag_name, tag_value):
                    # The tag_added signal will be emitted, which will update the PGN
                    pass
                else:
                    from app.views.message_dialog import MessageDialog
                    MessageDialog.show_warning(self.config, "Add Tag Failed", 
                                      f"Tag '{tag_name}' already exists or validation failed.", self)
    
    def _on_remove_tag_clicked(self) -> None:
        """Handle Remove button click."""
        if not self._game_model or not self._game_model.active_game:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "No Game", "Please select a game first.", self)
            return
        
        if not self._metadata_model:
            return
        
        # Get selected row in the metadata table
        selection_model = self.metadata_table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        
        if not selected_indexes:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "No Selection", "Please select a tag to remove.", self)
            return
        
        # Get the first selected row
        selected_row = selected_indexes[0].row()
        
        # Get the tag name from the model
        tag_name_index = self._metadata_model.index(selected_row, MetadataModel.COL_NAME)
        tag_name = self._metadata_model.data(tag_name_index, Qt.ItemDataRole.DisplayRole)
        
        if not tag_name:
            return
        
        # CARA analysis and annotation tags are read-only and cannot be removed
        read_only_tags = {
            "CARAAnalysisData", "CARAAnalysisInfo", "CARAAnalysisChecksum",
            "CARAAnnotations", "CARAAnnotationsInfo", "CARAAnnotationsChecksum"
        }
        if tag_name in read_only_tags:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Cannot Remove Tag", 
                              f"The tag '{tag_name}' is read-only and cannot be removed.", self)
            return
        
        # Ask for confirmation using custom styled dialog
        confirmed = self._show_confirmation_dialog(
            "Remove Tag",
            f"Are you sure you want to remove the tag '{tag_name}'?"
        )
        
        if confirmed:
            # Remove tag from model
            if self._metadata_model.remove_tag(tag_name):
                # The tag_removed signal will be emitted, which will update the PGN
                pass
            else:
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(self.config, "Remove Tag Failed", 
                                  f"Tag '{tag_name}' was not found.", self)
    
    def _show_confirmation_dialog(self, title: str, message: str) -> bool:
        """Show a styled confirmation dialog.
        
        Args:
            title: Dialog title.
            message: Confirmation message.
            
        Returns:
            True if user confirmed (Yes), False if cancelled (No).
        """
        from app.views.confirmation_dialog import ConfirmationDialog
        return ConfirmationDialog.show_confirmation(self.config, title, message, self)
    
    def _on_tag_added(self, tag_name: str, tag_value: str) -> None:
        """Handle tag addition from model.
        
        Args:
            tag_name: Name of the tag that was added.
            tag_value: Value of the tag that was added.
        """
        if not self._game_model or not self._game_model.active_game:
            return
        
        # Update the game's PGN with the new tag
        QTimer.singleShot(10, lambda: self._update_game_pgn_after_tag_added(tag_name, tag_value))
    
    def _update_game_pgn_after_tag_added(self, tag_name: str, tag_value: str) -> None:
        """Update the game's PGN with the newly added tag.
        
        Args:
            tag_name: Name of the tag that was added.
            tag_value: Value of the tag that was added.
        """
        if not self._game_model or not self._game_model.active_game:
            return
        
        # Update the game's PGN with the new tag
        try:
            import chess.pgn
            from io import StringIO
            
            game = self._game_model.active_game
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game:
                # Add the new header
                chess_game.headers[tag_name] = tag_value
                
                # Regenerate the PGN text
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                new_pgn = chess_game.accept(exporter).strip()
                
                # Update the game's PGN
                game.pgn = new_pgn
                
                # Update corresponding GameData fields if this tag corresponds to a database column
                tag_to_field_mapping = {
                    "White": "white",
                    "Black": "black",
                    "Result": "result",
                    "Date": "date",
                    "ECO": "eco",
                    "Event": "event",
                    "Site": "site",
                    "WhiteElo": "white_elo",
                    "BlackElo": "black_elo",
                }
                
                # Special handling for CARAAnalysisData tag (boolean field)
                if tag_name == "CARAAnalysisData":
                    game.analyzed = bool(tag_value) if tag_value else False
                elif tag_name in tag_to_field_mapping:
                    field_name = tag_to_field_mapping[tag_name]
                    setattr(game, field_name, tag_value)
                
                # Find the database model that contains this game and update it
                # This ensures the PGN update is persisted when saving
                database_model = self._find_database_model_for_game(game)
                if database_model:
                    database_model.update_game(game)
                    # Mark database as having unsaved changes
                    if self._database_panel:
                        self._database_panel.mark_database_unsaved(database_model)
                
                # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
                self._game_model.metadata_updated.emit()
        except Exception:
            # On any error, silently ignore (don't break the UI)
            pass
    
    def _on_tag_removed(self, tag_name: str) -> None:
        """Handle tag removal from model.
        
        Args:
            tag_name: Name of the tag that was removed.
        """
        if not self._game_model or not self._game_model.active_game:
            return
        
        # Update the game's PGN with the tag removed
        QTimer.singleShot(10, lambda: self._update_game_pgn_after_tag_removed(tag_name))
    
    def _update_game_pgn_after_tag_removed(self, tag_name: str) -> None:
        """Update the game's PGN after a tag is removed.
        
        Args:
            tag_name: Name of the tag that was removed.
        """
        if not self._game_model or not self._game_model.active_game:
            return
        
        # Update the game's PGN with the tag removed
        try:
            import chess.pgn
            from io import StringIO
            
            game = self._game_model.active_game
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game:
                # Remove the header if it exists
                if tag_name in chess_game.headers:
                    del chess_game.headers[tag_name]
                
                # Regenerate the PGN text
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                new_pgn = chess_game.accept(exporter).strip()
                
                # Update the game's PGN
                game.pgn = new_pgn
                
                # Update corresponding GameData fields if this tag corresponds to a database column
                tag_to_field_mapping = {
                    "White": "white",
                    "Black": "black",
                    "Result": "result",
                    "Date": "date",
                    "ECO": "eco",
                    "Event": "event",
                    "Site": "site",
                    "WhiteElo": "white_elo",
                    "BlackElo": "black_elo",
                }
                
                # Special handling for CARAAnalysisData and CARAAnnotations tags (boolean fields)
                if tag_name == "CARAAnalysisData":
                    game.analyzed = False
                elif tag_name == "CARAAnnotations":
                    game.annotated = False
                elif tag_name in tag_to_field_mapping:
                    field_name = tag_to_field_mapping[tag_name]
                    # Clear the field when tag is removed
                    setattr(game, field_name, "")
                
                # Find the database model that contains this game and update it
                # This ensures the PGN update is persisted when saving
                database_model = self._find_database_model_for_game(game)
                if database_model:
                    database_model.update_game(game)
                    # Mark database as having unsaved changes
                    if self._database_panel:
                        self._database_panel.mark_database_unsaved(database_model)
                
                # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
                self._game_model.metadata_updated.emit()
                
                # Refresh active game to update game info display (e.g., player names above chessboard)
                # This re-emits active_game_changed signal without resetting the move position
                self._game_model.refresh_active_game()
        except Exception:
            # On any error, silently ignore (don't break the UI)
            pass


class AddTagDialog(QDialog):
    """Dialog for adding a new metadata tag."""
    
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize the add tag dialog.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.tag_name = ""
        self.tag_value = ""
        
        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Add Tag")
    
    def _load_config(self) -> None:
        """Load configuration values from config dictionary."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('add_tag_dialog', {})
        self.dialog_width = dialog_config.get('width', 400)
        self.dialog_height = dialog_config.get('height', 180)
        self.dialog_min_width = dialog_config.get('minimum_width', 350)
        self.dialog_min_height = dialog_config.get('minimum_height', 150)
        self.dialog_bg_color = dialog_config.get('background_color', [40, 40, 45])
        
        layout_config = dialog_config.get('layout', {})
        self.layout_spacing = layout_config.get('spacing', 15)
        self.layout_margins = layout_config.get('margins', [15, 15, 15, 15])
        
        labels_config = dialog_config.get('labels', {})
        self.label_font_family = labels_config.get('font_family', 'Helvetica Neue')
        from app.utils.font_utils import scale_font_size
        self.label_font_size = scale_font_size(labels_config.get('font_size', 11))
        self.label_text_color = labels_config.get('text_color', [200, 200, 200])
        
        inputs_config = dialog_config.get('inputs', {})
        from app.utils.font_utils import resolve_font_family
        input_font_family_raw = inputs_config.get('font_family', 'Cascadia Mono')
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = inputs_config.get('font_size', 11)
        self.input_text_color = inputs_config.get('text_color', [240, 240, 240])
        self.input_bg_color = inputs_config.get('background_color', [30, 30, 35])
        self.input_border_color = inputs_config.get('border_color', [60, 60, 65])
        self.input_border_radius = inputs_config.get('border_radius', 3)
        self.input_padding = inputs_config.get('padding', [8, 6])
        self.input_min_width = inputs_config.get('minimum_width', 200)
        self.input_min_height = inputs_config.get('minimum_height', 30)
        
        buttons_config = dialog_config.get('buttons', {})
        self.button_width = buttons_config.get('width', 120)
        self.button_height = buttons_config.get('height', 30)
        self.button_border_radius = buttons_config.get('border_radius', 3)
        self.button_padding = buttons_config.get('padding', 5)
        self.button_bg_offset = buttons_config.get('background_offset', 20)
        self.button_hover_bg_offset = buttons_config.get('hover_background_offset', 30)
        self.button_pressed_bg_offset = buttons_config.get('pressed_background_offset', 10)
        from app.utils.font_utils import scale_font_size
        self.button_font_size = scale_font_size(buttons_config.get('font_size', 10))
        self.button_text_color = buttons_config.get('text_color', [200, 200, 200])
        self.button_border_color = buttons_config.get('border_color', [60, 60, 65])
        self.button_spacing = buttons_config.get('spacing', 10)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Set dialog size
        self.setFixedSize(self.dialog_width, self.dialog_height)
        self.setMinimumSize(self.dialog_min_width, self.dialog_min_height)
        
        # Set dialog background color
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(
            self.dialog_bg_color[0], self.dialog_bg_color[1], self.dialog_bg_color[2]
        ))
        self.setPalette(palette)
        
        # Create main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(self.layout_spacing)
        layout.setContentsMargins(
            self.layout_margins[0], self.layout_margins[1],
            self.layout_margins[2], self.layout_margins[3]
        )
        
        # Create form layout for inputs
        form_layout = QFormLayout()
        form_layout.setSpacing(self.layout_spacing)
        # Set field growth policy to make fields expand
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        # Tag name input
        tag_name_label = QLabel("Tag Name:")
        self.tag_name_input = QLineEdit()
        self.tag_name_input.setMinimumWidth(self.input_min_width)
        self.tag_name_input.setMinimumHeight(self.input_min_height)
        self.tag_name_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout.addRow(tag_name_label, self.tag_name_input)
        
        # Tag value input
        tag_value_label = QLabel("Tag Value:")
        self.tag_value_input = QLineEdit()
        self.tag_value_input.setMinimumWidth(self.input_min_width)
        self.tag_value_input.setMinimumHeight(self.input_min_height)
        self.tag_value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout.addRow(tag_value_label, self.tag_value_input)
        
        layout.addLayout(form_layout)
        
        # Create button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set focus on tag name input
        self.tag_name_input.setFocus()
    
    def _apply_styling(self) -> None:
        """Apply styling to dialog elements."""
        # Label styling
        label_style = f"""
            QLabel {{
                font-family: '{self.label_font_family}';
                font-size: {self.label_font_size}pt;
                color: rgb({self.label_text_color[0]}, {self.label_text_color[1]}, {self.label_text_color[2]});
            }}
        """
        
        # Input styling
        input_style = f"""
            QLineEdit {{
                font-family: '{self.input_font_family}';
                font-size: {self.input_font_size}pt;
                color: rgb({self.input_text_color[0]}, {self.input_text_color[1]}, {self.input_text_color[2]});
                background-color: rgb({self.input_bg_color[0]}, {self.input_bg_color[1]}, {self.input_bg_color[2]});
                border: 1px solid rgb({self.input_border_color[0]}, {self.input_border_color[1]}, {self.input_border_color[2]});
                border-radius: {self.input_border_radius}px;
                padding: {self.input_padding[0]}px {self.input_padding[1]}px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgb(100, 150, 200);
            }}
        """
        
        # Apply styles
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
        
        for line_edit in self.findChildren(QLineEdit):
            line_edit.setStyleSheet(input_style)
        
        # Apply button styling using StyleManager
        from app.views.style import StyleManager
        buttons = list(self.findChildren(QPushButton))
        if buttons:
            bg_color_list = [self.dialog_bg_color[0], self.dialog_bg_color[1], self.dialog_bg_color[2]]
            border_color_list = [self.button_border_color[0], self.button_border_color[1], self.button_border_color[2]]
            StyleManager.style_buttons(
                buttons,
                self.config,
                bg_color_list,
                border_color_list,
                background_offset=self.button_bg_offset,
                hover_background_offset=self.button_hover_bg_offset,
                pressed_background_offset=self.button_pressed_bg_offset,
                min_width=self.button_width,
                min_height=self.button_height
            )
    
    def _on_ok_clicked(self) -> None:
        """Handle OK button click."""
        tag_name = self.tag_name_input.text().strip()
        tag_value = self.tag_value_input.text().strip()
        
        if not tag_name:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Invalid Input", "Tag name cannot be empty.", self)
            return
        
        self.tag_name = tag_name
        self.tag_value = tag_value
        self.accept()
    
    def get_tag_info(self) -> Tuple[str, str]:
        """Get the tag name and value entered in the dialog.
        
        Returns:
            Tuple of (tag_name, tag_value).
        """
        return (self.tag_name, self.tag_value)


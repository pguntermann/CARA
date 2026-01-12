"""Metadata controller for managing game metadata operations."""

import chess.pgn
from io import StringIO
from typing import Dict, Any, Optional, List, Tuple
from PyQt6.QtCore import Qt

from app.models.game_model import GameModel
from app.models.database_model import DatabaseModel, GameData
from app.services.pgn_service import PgnService
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.controllers.database_controller import DatabaseController
    from app.models.metadata_model import MetadataModel

# Standard PGN tags in order of importance
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


class MetadataController:
    """Controller for managing game metadata operations.
    
    This controller handles metadata extraction, tag updates, and PGN regeneration
    for game metadata operations.
    """
    
    def __init__(self, game_model: GameModel, database_controller: Optional['DatabaseController'] = None) -> None:
        """Initialize the metadata controller.
        
        Args:
            game_model: GameModel instance for accessing active game.
            database_controller: Optional DatabaseController for database operations.
        """
        self._game_model = game_model
        self._database_controller = database_controller
        # Get database model from controller if available
        self._database_model = database_controller.get_database_model() if database_controller else None
        self._metadata_model: Optional['MetadataModel'] = None
        
        # Cache for database model lookup (performance optimization)
        self._cached_database_model: Optional[DatabaseModel] = None
        self._cached_game: Optional[GameData] = None
        
        # Connect to active game changes to update cache
        if self._game_model:
            self._game_model.active_game_changed.connect(self._on_active_game_changed)
    
    def extract_metadata_from_game(self, game: GameData) -> List[Tuple[str, str]]:
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
            pgn_io = StringIO(game.pgn)
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
    
    def _update_database_model_cache(self) -> None:
        """Update cached database model reference when active game changes.
        
        This avoids expensive searches when updating metadata for the same game.
        """
        if not self._game_model or not self._game_model.active_game:
            self._cached_database_model = None
            self._cached_game = None
            return
        
        game = self._game_model.active_game
        # Only search if game changed or cache is invalid
        if game != self._cached_game or self._cached_database_model is None:
            self._cached_database_model = self.find_database_model_for_game(game)
            self._cached_game = game
    
    def _on_active_game_changed(self, game: Optional[GameData]) -> None:
        """Handle active game change - update cache."""
        self._update_database_model_cache()
    
    def find_database_model_for_game(self, game: GameData) -> Optional[DatabaseModel]:
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
        if self._database_controller:
            panel_model = self._database_controller.get_panel_model()
            if panel_model:
                all_databases = panel_model.get_all_databases()
                for identifier, info in all_databases.items():
                    if info.model.find_game(game) is not None:
                        return info.model
        
        return None
    
    def update_metadata_tag(self, tag_name: str, new_value: str) -> bool:
        """Update a metadata tag in the active game (optimized version).
        
        This method:
        - Updates game.pgn (for saving/copying)
        - Updates database model (for database view)
        - Updates metadata model incrementally (no re-extraction)
        - Updates PGN view selectively (only metadata section)
        - Marks game as unsaved
        
        Args:
            tag_name: Name of the tag to update.
            new_value: New value for the tag.
            
        Returns:
            True if successful, False otherwise.
        """
        if not self._game_model or not self._game_model.active_game:
            return False
        
        try:
            game = self._game_model.active_game
            
            # Ensure database model cache is valid (O(1) after first call)
            self._update_database_model_cache()
            database_model = self._cached_database_model
            
            # STEP 1: Parse PGN once (only time we parse)
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # STEP 2: Update the header
            chess_game.headers[tag_name] = new_value
            
            # STEP 3: Regenerate PGN (required for saving/copying)
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            game.pgn = new_pgn  # Update game.pgn (critical for saving/copying)
            
            # STEP 4: Update corresponding GameData fields (for database columns)
            self._update_gamedata_fields(game, tag_name, new_value)
            
            # STEP 5: Update database model (for database view visibility)
            if database_model:
                # Determine which column changed (if any)
                column_index = self._get_column_index_for_tag(tag_name)
                
                if column_index is not None:
                    # Emit dataChanged only for the specific column (performance optimization)
                    row = database_model.find_game(game)
                    if row is not None:
                        index = database_model.index(row, column_index)
                        database_model.dataChanged.emit(index, index, 
                                                       [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
                        database_model._unsaved_games.add(game)
                else:
                    # Tag doesn't map to a column, use full row update
                    database_model.update_game(game)
                
                # Mark database as having unsaved changes
                if self._database_controller:
                    self._database_controller.mark_database_unsaved(database_model)
            
            # STEP 6: Update metadata model incrementally (NO re-extraction)
            if self._metadata_model:
                # Model already has correct value (user just edited it)
                # Just ensure it's in sync (in case of external changes)
                # This is a no-op if value is already correct
                self._metadata_model.update_tag_value(tag_name, new_value)
            
            # STEP 7: Emit metadata_updated signal (for PGN view)
            # This tells PGN view that metadata changed, but NOT game structure
            self._game_model.metadata_updated.emit()
            
            # STEP 8: Refresh active game ONLY if player names or result changed (for game info header)
            # This updates the game info header (player names and result above chessboard)
            # We only do this for these specific tags to avoid unnecessary re-extraction in metadata view
            if tag_name in ["White", "Black", "Result"]:
                self._game_model.refresh_active_game()
            
            return True
        except Exception:
            return False
    
    def _update_gamedata_fields(self, game: GameData, tag_name: str, new_value: str) -> None:
        """Update GameData fields that correspond to PGN tags.
        
        Args:
            game: GameData instance to update.
            tag_name: Name of the tag that was updated.
            new_value: New value for the tag.
        """
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
        
        if tag_name == "CARAAnalysisData":
            game.analyzed = bool(new_value) if new_value else False
        elif tag_name == "CARAAnnotations":
            game.annotated = bool(new_value) if new_value else False
        elif tag_name in tag_to_field_mapping:
            field_name = tag_to_field_mapping[tag_name]
            setattr(game, field_name, new_value)
    
    def _get_column_index_for_tag(self, tag_name: str) -> Optional[int]:
        """Get database model column index for a tag (if it maps to a column).
        
        Args:
            tag_name: Name of the PGN tag.
            
        Returns:
            Column index if tag maps to a database column, None otherwise.
        """
        from app.models.database_model import DatabaseModel
        
        # Map standard tags to database columns
        tag_to_column = {
            "White": DatabaseModel.COL_WHITE,
            "Black": DatabaseModel.COL_BLACK,
            "Result": DatabaseModel.COL_RESULT,
            "Date": DatabaseModel.COL_DATE,
            "ECO": DatabaseModel.COL_ECO,
            "Event": DatabaseModel.COL_EVENT,
            "Site": DatabaseModel.COL_SITE,
            "WhiteElo": DatabaseModel.COL_WHITE_ELO,
            "BlackElo": DatabaseModel.COL_BLACK_ELO,
            "CARAAnalysisData": DatabaseModel.COL_ANALYZED,
            "CARAAnnotations": DatabaseModel.COL_ANNOTATED,
        }
        return tag_to_column.get(tag_name)
    
    def add_metadata_tag(self, tag_name: str, tag_value: str) -> bool:
        """Add a new metadata tag to the active game.
        
        Args:
            tag_name: Name of the tag to add.
            tag_value: Value for the tag.
            
        Returns:
            True if successful, False otherwise.
        """
        if not self._game_model or not self._game_model.active_game:
            return False
        
        try:
            game = self._game_model.active_game
            
            # Ensure database model cache is valid
            self._update_database_model_cache()
            database_model = self._cached_database_model
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # Add the new header
            chess_game.headers[tag_name] = tag_value
            
            # Regenerate the PGN text
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
            # Update the game's PGN
            game.pgn = new_pgn
            
            # Update corresponding GameData fields if this tag corresponds to a database column
            self._update_gamedata_fields(game, tag_name, tag_value)
            
            # Update database model (for database view visibility)
            if database_model:
                # Determine which column changed (if any)
                column_index = self._get_column_index_for_tag(tag_name)
                
                if column_index is not None:
                    # Emit dataChanged only for the specific column
                    row = database_model.find_game(game)
                    if row is not None:
                        index = database_model.index(row, column_index)
                        database_model.dataChanged.emit(index, index, 
                                                       [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
                        database_model._unsaved_games.add(game)
                else:
                    # Tag doesn't map to a column, use full row update
                    database_model.update_game(game)
                
                # Mark database as having unsaved changes
                if self._database_controller:
                    self._database_controller.mark_database_unsaved(database_model)
            
            # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
            self._game_model.metadata_updated.emit()
            
            # Update metadata model (structural change requires re-extraction)
            if self._metadata_model:
                # Re-extract metadata to include the new tag
                metadata = self.extract_metadata_from_game(game)
                self._metadata_model.set_metadata(metadata)
            
            return True
        except Exception:
            return False
    
    def remove_metadata_tag(self, tag_name: str) -> bool:
        """Remove a metadata tag from the active game.
        
        Args:
            tag_name: Name of the tag to remove.
            
        Returns:
            True if successful, False otherwise.
        """
        if not self._game_model or not self._game_model.active_game:
            return False
        
        try:
            game = self._game_model.active_game
            
            # Ensure database model cache is valid
            self._update_database_model_cache()
            database_model = self._cached_database_model
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # Remove the header if it exists
            if tag_name in chess_game.headers:
                del chess_game.headers[tag_name]
            
            # Regenerate the PGN text
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
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
            
            # Update database model (for database view visibility)
            if database_model:
                # Determine which column changed (if any)
                column_index = self._get_column_index_for_tag(tag_name)
                
                if column_index is not None:
                    # Emit dataChanged only for the specific column
                    row = database_model.find_game(game)
                    if row is not None:
                        index = database_model.index(row, column_index)
                        database_model.dataChanged.emit(index, index, 
                                                       [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
                        database_model._unsaved_games.add(game)
                else:
                    # Tag doesn't map to a column, use full row update
                    database_model.update_game(game)
                
                # Mark database as having unsaved changes
                if self._database_controller:
                    self._database_controller.mark_database_unsaved(database_model)
            
            # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
            self._game_model.metadata_updated.emit()
            
            # Update metadata model (structural change requires re-extraction)
            if self._metadata_model:
                # Re-extract metadata to reflect removed tag
                metadata = self.extract_metadata_from_game(game)
                self._metadata_model.set_metadata(metadata)
            
            return True
        except Exception:
            return False
    
    def set_metadata_model(self, metadata_model: Optional['MetadataModel']) -> None:
        """Set the metadata model for updating metadata display.
        
        Args:
            metadata_model: The MetadataModel instance.
        """
        self._metadata_model = metadata_model
    
    def update_metadata_model(self, metadata: List[Tuple[str, str]]) -> None:
        """Update the metadata model with extracted metadata.
        
        Args:
            metadata: List of (name, value) tuples.
        """
        if self._metadata_model:
            self._metadata_model.set_metadata(metadata)
    
    def clear_metadata_model(self) -> None:
        """Clear the metadata model."""
        if self._metadata_model:
            self._metadata_model.clear()
    
    def set_database_controller(self, database_controller: Optional['DatabaseController']) -> None:
        """Set the database controller for database operations.
        
        Args:
            database_controller: The DatabaseController instance.
        """
        self._database_controller = database_controller
        # Update database model reference
        self._database_model = database_controller.get_database_model() if database_controller else None


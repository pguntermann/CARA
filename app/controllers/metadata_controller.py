"""Metadata controller for managing game metadata operations."""

import chess.pgn
from io import StringIO
from typing import Dict, Any, Optional, List, Tuple

from app.models.game_model import GameModel
from app.models.database_model import DatabaseModel, GameData
from app.services.pgn_service import PgnService
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.controllers.database_controller import DatabaseController

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
        """Update a metadata tag in the active game.
        
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
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # Update the header
            chess_game.headers[tag_name] = new_value
            
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
                game.analyzed = bool(new_value) if new_value else False
            elif tag_name == "CARAAnnotations":
                game.annotated = bool(new_value) if new_value else False
            elif tag_name in tag_to_field_mapping:
                field_name = tag_to_field_mapping[tag_name]
                setattr(game, field_name, new_value)
            
            # Find the database model that contains this game and update it
            database_model = self.find_database_model_for_game(game)
            if database_model:
                database_model.update_game(game)
                # Mark database as having unsaved changes
                if self._database_controller:
                    self._database_controller.mark_database_unsaved(database_model)
            
            # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
            self._game_model.metadata_updated.emit()
            
            # Refresh active game to update game info display (e.g., player names above chessboard)
            self._game_model.refresh_active_game()
            
            return True
        except Exception:
            return False
    
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
            database_model = self.find_database_model_for_game(game)
            if database_model:
                database_model.update_game(game)
                # Mark database as having unsaved changes
                if self._database_controller:
                    self._database_controller.mark_database_unsaved(database_model)
            
            # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
            self._game_model.metadata_updated.emit()
            
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
            
            # Find the database model that contains this game and update it
            database_model = self.find_database_model_for_game(game)
            if database_model:
                database_model.update_game(game)
                # Mark database as having unsaved changes
                if self._database_controller:
                    self._database_controller.mark_database_unsaved(database_model)
            
            # Emit metadata_updated signal to notify views (e.g., PGN view) that metadata changed
            self._game_model.metadata_updated.emit()
            
            # Refresh active game to update game info display (e.g., player names above chessboard)
            self._game_model.refresh_active_game()
            
            return True
        except Exception:
            return False
    
    def set_database_controller(self, database_controller: Optional['DatabaseController']) -> None:
        """Set the database controller for database operations.
        
        Args:
            database_controller: The DatabaseController instance.
        """
        self._database_controller = database_controller
        # Update database model reference
        self._database_model = database_controller.get_database_model() if database_controller else None


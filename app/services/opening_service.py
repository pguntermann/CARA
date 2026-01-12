"""Opening service for looking up ECO codes and opening names from FEN positions."""

import json
import chess
import chess.pgn
from io import StringIO
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config.config_loader import ConfigLoader


class OpeningService:
    """Service for looking up opening information from FEN positions.
    
    This service loads ECO files and provides lookup functionality to identify
    opening ECO codes and names from chess positions.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the opening service.
        
        Args:
            config: Configuration dictionary containing resources.ecolists_path.
        """
        self.config = config
        self._eco_base: Optional[Dict[str, Any]] = None
        self._eco_interpolated: Optional[Dict[str, Any]] = None
        self._loaded = False
    
    def load(self) -> None:
        """Load ECO files into memory.
        
        This method loads the eco_base.json and eco_interpolated.json files.
        It should be called once before using lookup methods.
        """
        if self._loaded:
            return
        
        # Get ecolists path from config
        ecolists_path_str = self.config.get('resources', {}).get('ecolists_path', 'app/resources/ecolists')
        
        # Resolve path relative to app root
        app_root = Path(__file__).parent.parent.parent
        ecolists_path = app_root / ecolists_path_str
        
        # Load eco_base.json
        eco_base_file = ecolists_path / "eco_base.json"
        if eco_base_file.exists():
            with open(eco_base_file, "r", encoding="utf-8") as f:
                self._eco_base = json.load(f)
        else:
            self._eco_base = {}
        
        # Load eco_interpolated.json
        eco_interpolated_file = ecolists_path / "eco_interpolated.json"
        if eco_interpolated_file.exists():
            with open(eco_interpolated_file, "r", encoding="utf-8") as f:
                self._eco_interpolated = json.load(f)
        else:
            self._eco_interpolated = {}
        
        self._loaded = True
        
        # Log opening book loaded
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        base_count = len(self._eco_base) if self._eco_base else 0
        interpolated_count = len(self._eco_interpolated) if self._eco_interpolated else 0
        logging_service.info(f"Opening book loaded: path={ecolists_path}, base_positions={base_count}, interpolated_positions={interpolated_count}")
    
    def lookup_opening(self, fen: str) -> Optional[Dict[str, Any]]:
        """Look up opening information for a FEN position.
        
        Args:
            fen: FEN position string.
            
        Returns:
            Dictionary with 'eco', 'name', 'moves', etc., or None if not found.
        """
        if not self._loaded:
            self.load()
        
        # First check interpolated (contains interpolated positions)
        if self._eco_interpolated and fen in self._eco_interpolated:
            return self._eco_interpolated[fen]
        
        # Then check base files
        if self._eco_base and fen in self._eco_base:
            return self._eco_base[fen]
        
        return None
    
    def get_opening_info(self, fen: str) -> Tuple[Optional[str], Optional[str]]:
        """Get ECO code and opening name for a FEN position.
        
        Args:
            fen: FEN position string.
            
        Returns:
            Tuple of (eco_code, opening_name). Both are None if not found.
        """
        opening = self.lookup_opening(fen)
        if opening:
            eco = opening.get('eco', None)
            name = opening.get('name', None)
            return (eco, name)
        return (None, None)
    
    def is_loaded(self) -> bool:
        """Check if ECO files are loaded.
        
        Returns:
            True if files are loaded, False otherwise.
        """
        return self._loaded
    
    def get_final_eco_for_game(self, pgn: str) -> Optional[str]:
        """Get the final ECO code for a game by traversing moves backwards.
        
        This method parses the PGN, traverses all moves backwards, and looks up ECO codes
        for each position. Returns the first ECO code found when traversing backwards
        (which is the last opening played in the game). This is more efficient than
        traversing forwards since we can stop once we find an opening.
        
        This follows the same pattern as GameController.extract_moves_from_game() but
        traverses backwards for efficiency.
        
        Args:
            pgn: PGN string of the game.
            
        Returns:
            ECO code string if found, None otherwise.
        """
        if not self._loaded:
            self.load()
        
        try:
            # Parse the PGN
            pgn_io = StringIO(pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return None
            
            # Navigate to end of game first
            node = chess_game
            move_nodes = []  # Store all move nodes for backwards traversal
            
            # Traverse forwards to collect all nodes
            while node.variations:
                next_node = node.variation(0)
                move_nodes.append(next_node)
                node = next_node
            
            # Traverse backwards to find the last opening
            # This is more efficient - we can stop once we find an ECO
            for move_idx in range(len(move_nodes) - 1, -1, -1):
                move_node = move_nodes[move_idx]
                
                # Get the board position after the move (for opening lookup)
                board_after = move_node.board()
                fen_after = board_after.fen()  # Use full FEN string (matches GameController pattern)
                
                # Look up opening for this position (after the move)
                eco, _ = self.get_opening_info(fen_after)
                
                if eco:
                    return eco  # Found opening - return immediately
            
            return None
            
        except Exception:
            # If parsing fails, return None
            return None


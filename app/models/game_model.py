"""Game model for tracking the active game."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional

from app.models.database_model import GameData


class GameModel(QObject):
    """Model representing the currently active game.
    
    This model holds the active game state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emitted when active game changes
    active_game_changed = pyqtSignal(object)  # Emitted when active game changes (GameData or None)
    active_move_changed = pyqtSignal(int)  # Emitted when active move changes (ply_index: 0 = start, 1 = after first move, etc.)
    is_game_analyzed_changed = pyqtSignal(bool)  # Emitted when game analysis completion status changes
    metadata_updated = pyqtSignal()  # Emitted when metadata tags are added/edited/removed
    
    def __init__(self) -> None:
        """Initialize the game model."""
        super().__init__()
        self._active_game: Optional[GameData] = None
        self._active_move_ply: int = 0  # Ply index (0 = starting position, 1 = after first move, etc.)
        self._is_game_analyzed: bool = False  # True if the active game has been completely analyzed
    
    @property
    def active_game(self) -> Optional[GameData]:
        """Get the currently active game.
        
        Returns:
            The active GameData instance, or None if no game is active.
        """
        return self._active_game
    
    def set_active_game(self, game: Optional[GameData]) -> None:
        """Set the active game.
        
        Args:
            game: GameData instance to set as active, or None to clear active game.
        """
        if self._active_game != game:
            # Debug log: active game change
            from app.services.logging_service import LoggingService
            logging_service = LoggingService.get_instance()
            old_identifier = self._get_game_identifier(self._active_game) if self._active_game else "None"
            new_identifier = self._get_game_identifier(game) if game else "None"
            logging_service.debug(f"Active game changed: {old_identifier} -> {new_identifier}")
            
            self._active_game = game
            # Reset analysis flag when active game changes
            self._set_is_game_analyzed(False)
            self.active_game_changed.emit(self._active_game)
    
    def clear_active_game(self) -> None:
        """Clear the active game (set to None)."""
        self.set_active_game(None)
        self._active_move_ply = 0
        # Analysis flag is already reset in set_active_game(None)
    
    def set_active_move_ply(self, ply_index: int) -> None:
        """Set the active move by ply index.
        
        Args:
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
        """
        if self._active_move_ply != ply_index:
            self._active_move_ply = ply_index
            self.active_move_changed.emit(ply_index)
    
    def get_active_move_ply(self) -> int:
        """Get the current active move ply index.
        
        Returns:
            Current ply index (0 = starting position, 1 = after first move, etc.).
        """
        return self._active_move_ply
    
    @property
    def is_game_analyzed(self) -> bool:
        """Get whether the active game has been completely analyzed.
        
        Returns:
            True if the active game has been completely analyzed, False otherwise.
        """
        return self._is_game_analyzed
    
    def _set_is_game_analyzed(self, value: bool) -> None:
        """Set the game analysis completion status.
        
        Args:
            value: True if game has been completely analyzed, False otherwise.
        """
        if self._is_game_analyzed != value:
            self._is_game_analyzed = value
            self.is_game_analyzed_changed.emit(value)
    
    def set_is_game_analyzed(self, value: bool) -> None:
        """Set the game analysis completion status (public method).
        
        Args:
            value: True if game has been completely analyzed, False otherwise.
        """
        self._set_is_game_analyzed(value)
    
    def refresh_active_game(self) -> None:
        """Refresh the active game by re-emitting the active_game_changed signal.
        
        This is useful when the active game's PGN has been updated and views
        need to refresh their display of the game data.
        """
        if self._active_game is not None:
            # Re-emit the signal to trigger view updates
            self.active_game_changed.emit(self._active_game)
    
    def _get_game_identifier(self, game: GameData) -> str:
        """Get a string identifier for a game.
        
        Args:
            game: GameData instance.
            
        Returns:
            String identifier (e.g., "#1 White vs Black" or "#1" if players unknown).
        """
        if game is None:
            return "None"
        identifier = f"#{game.game_number}"
        if game.white or game.black:
            white = game.white or "?"
            black = game.black or "?"
            identifier += f" {white} vs {black}"
        return identifier


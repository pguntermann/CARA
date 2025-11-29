"""Main application area / Main-Panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QPalette, QColor
from typing import Dict, Any, Optional

from app.views.main_gameinfo_view import MainGameInfoView
from app.views.main_chessboard_view import MainChessBoardView
from app.models.board_model import BoardModel
from app.models.game_model import GameModel
from app.controllers.game_controller import GameController
from app.models.evaluation_model import EvaluationModel


class MainPanel(QWidget):
    """Main application area panel."""
    
    def __init__(self, config: Dict[str, Any], board_model: Optional[BoardModel] = None, 
                 game_model: Optional[GameModel] = None,
                 game_controller: Optional[GameController] = None,
                 evaluation_model: Optional[EvaluationModel] = None) -> None:
        """Initialize the main panel.
        
        Args:
            config: Configuration dictionary.
            board_model: Optional BoardModel to observe.
            game_model: Optional GameModel to observe.
            game_controller: Optional GameController for extracting game info.
            evaluation_model: Optional EvaluationModel to observe.
        """
        super().__init__()
        self.config = config
        self._board_model = board_model
        self._game_model: Optional[GameModel] = None
        self._game_controller = game_controller
        self._evaluation_model = evaluation_model
        self._setup_ui()
        
        # Connect to board model for visibility state if provided
        if board_model:
            self.set_board_model(board_model)
        
        # Connect to game model if provided
        if game_model:
            self.set_game_model(game_model)
        
        # Connect to evaluation model if provided
        if evaluation_model and hasattr(self, 'chessboard_view'):
            self.chessboard_view.set_evaluation_model(evaluation_model)
    
    def _setup_ui(self) -> None:
        """Setup the main panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('main', {})
        
        # Top section: Game info header
        self.game_info_view = MainGameInfoView(self.config)
        layout.addWidget(self.game_info_view, 0)
        
        # Bottom section: Chess board
        self.chessboard_view = MainChessBoardView(self.config, self._board_model, self._evaluation_model)
        layout.addWidget(self.chessboard_view, 1)  # Takes remaining space
        
        # Set minimum size so widget is visible
        min_width = panel_config.get('minimum_width', 200)
        min_height = panel_config.get('minimum_height', 200)
        self.setMinimumSize(min_width, min_height)
        
        # Set background color from config using palette
        debug_config = self.config.get("debug", {})
        if debug_config.get("enable_debug_backgrounds", False):
            # Use debug background color
            color = debug_config.get("background_color_debug_mainpanel", [255, 255, 255])
        else:
            # Use normal background color
            color = panel_config.get("background_color", [40, 40, 45])
        
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(color[0], color[1], color[2]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
    
    def set_board_model(self, model: BoardModel) -> None:
        """Set the board model to observe for visibility state.
        
        Args:
            model: The BoardModel instance to observe.
        """
        if self._board_model and self._board_model != model:
            # Disconnect from old model (if it was different)
            try:
                if hasattr(self._board_model, 'game_info_visibility_changed'):
                    self._board_model.game_info_visibility_changed.disconnect(self._on_game_info_visibility_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._board_model = model
        
        # Connect to model signals
        if model:
            model.game_info_visibility_changed.connect(self._on_game_info_visibility_changed)
            
            # Initialize with current visibility state
            self._update_game_info_visibility(model.show_game_info)
    
    def _on_game_info_visibility_changed(self, show: bool) -> None:
        """Handle game info visibility change from model.
        
        Args:
            show: True if game info should be visible, False otherwise.
        """
        self._update_game_info_visibility(show)
    
    def _update_game_info_visibility(self, show: bool) -> None:
        """Update game info visibility state.
        
        Args:
            show: True if game info should be visible, False otherwise.
        """
        if hasattr(self, 'game_info_view'):
            self.game_info_view.setVisible(show)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
        
        self._game_model = model
        
        # Connect to model signals
        model.active_game_changed.connect(self._on_active_game_changed)
        
        # Initialize with current active game if any
        if model.active_game:
            self._on_active_game_changed(model.active_game)
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change from model.
        
        Args:
            game: GameData instance or None.
        """
        if game is None:
            # Clear game info display
            self._clear_game_info()
            return
        
        # Update game info view with game data
        self._update_game_info(game)
    
    def _update_game_info(self, game) -> None:
        """Update game info view with game data.
        
        Args:
            game: GameData instance.
        """
        # Get processed game info from controller (business logic)
        if self._game_controller:
            game_info = self._game_controller.get_game_info(game)
        else:
            # Fallback: create default game info if controller not available
            from app.controllers.game_controller import GameInfo
            game_info = GameInfo(
                white_name="White",
                black_name="Black",
                white_elo=1500,
                black_elo=1500,
                result="*",
                eco="A00",
                opening_name="Unknown Opening"
            )
        
        # Update game info view (presentation logic only)
        self.game_info_view.set_white_player(game_info.white_name, game_info.white_elo)
        self.game_info_view.set_black_player(game_info.black_name, game_info.black_elo)
        self.game_info_view.set_result(game_info.result)
        self.game_info_view.set_opening(game_info.eco, game_info.opening_name)
    
    def _clear_game_info(self) -> None:
        """Clear game info display to default values."""
        # Get default game info from controller (business logic)
        if self._game_controller:
            game_info = self._game_controller.get_game_info(None)
        else:
            # Fallback: create default game info if controller not available
            from app.controllers.game_controller import GameInfo
            game_info = GameInfo(
                white_name="White",
                black_name="Black",
                white_elo=1500,
                black_elo=1500,
                result="*",
                eco="A00",
                opening_name="Unknown Opening"
            )
        
        # Update game info view (presentation logic only)
        self.game_info_view.set_white_player(game_info.white_name, game_info.white_elo)
        self.game_info_view.set_black_player(game_info.black_name, game_info.black_elo)
        self.game_info_view.set_result(game_info.result)
        self.game_info_view.set_opening(game_info.eco, game_info.opening_name)


"""Main application area / Main-Panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import QObject, QEvent, QPoint
from typing import Dict, Any, Optional

from app.views.main_gameinfo_view import MainGameInfoView
from app.views.main_chessboard_view import MainChessBoardView
from app.models.board_model import BoardModel
from app.models.game_model import GameModel
from app.controllers.game_controller import GameController
from app.models.evaluation_model import EvaluationModel

GAME_INFO_CENTER_IN_VIEW = "center_in_view"
GAME_INFO_CENTER_OVER_BOARD = "center_over_board"


class _ChessboardResizeNotifier(QObject):
    """Updates game info horizontal margins when the chessboard geometry changes."""

    def __init__(self, main_panel: "MainPanel") -> None:
        super().__init__(main_panel)
        self._panel = main_panel

    def eventFilter(self, obj, event):  # type: ignore[no-untyped-def]
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._panel._update_game_info_center_margins()
        return False


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
        self._game_info_center_mode: str = GAME_INFO_CENTER_IN_VIEW
        self._board_resize_notifier: Optional[_ChessboardResizeNotifier] = None
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
        
        # Set minimum size so widget is visible (width default avoids board/UI glitches when narrow)
        min_width = int(panel_config.get('minimum_width', 250))
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

        self._board_resize_notifier = _ChessboardResizeNotifier(self)
        self.chessboard_view.chessboard.installEventFilter(self._board_resize_notifier)
    
    def set_game_info_center_mode(self, mode: str) -> None:
        """``center_in_view`` or ``center_over_board`` (see ``GAME_INFO_CENTER_*``)."""
        if mode == GAME_INFO_CENTER_OVER_BOARD:
            self._game_info_center_mode = GAME_INFO_CENTER_OVER_BOARD
        else:
            self._game_info_center_mode = GAME_INFO_CENTER_IN_VIEW
        self._update_game_info_center_margins()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_game_info_center_margins()

    def _update_game_info_center_margins(self) -> None:
        """Match game info content width to the board (borders + squares), excluding coord labels."""
        if self._game_info_center_mode != GAME_INFO_CENTER_OVER_BOARD:
            self.game_info_view.set_centering_margin_extras(0, 0)
            return
        w = self.width()
        if w <= 0:
            self.game_info_view.set_centering_margin_extras(0, 0)
            return
        cb = self.chessboard_view.chessboard
        if cb.width() <= 0 or cb.height() <= 0:
            self.game_info_view.set_centering_margin_extras(0, 0)
            return
        dims = cb._calculate_board_dimensions()
        # Align to the playing board (border + squares only), not the rank/file coordinate gutter.
        board_left_cb = int(dims["board_border_start"])
        coord_gutter_w = board_left_cb - int(dims["board_group_start_x"])
        board_w = int(dims["total_board_width"]) - coord_gutter_w
        board_left = int(cb.mapTo(self, QPoint(board_left_cb, 0)).x())
        l0, _, r0, _ = self.game_info_view._margin_base_ltrb
        el = max(0, int(round(board_left - l0)))
        er = max(0, int(round(w - l0 - el - board_w - r0)))
        self.game_info_view.set_centering_margin_extras(el, er)
    
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
            self._disconnect_board_layout_signals(self._board_model)
        
        self._board_model = model
        
        # Connect to model signals
        if model:
            model.game_info_visibility_changed.connect(self._on_game_info_visibility_changed)
            self._disconnect_board_layout_signals(model)
            self._connect_board_layout_signals(model)
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
        self._update_game_info_center_margins()

    def _connect_board_layout_signals(self, model: BoardModel) -> None:
        for sig in (
            model.evaluation_bar_visibility_changed,
            model.material_widget_visibility_changed,
            model.game_tags_widget_visibility_changed,
            model.coordinates_visibility_changed,
            model.flip_state_changed,
        ):
            try:
                sig.connect(self._update_game_info_center_margins)
            except Exception:
                pass

    def _disconnect_board_layout_signals(self, model: BoardModel) -> None:
        for sig in (
            model.evaluation_bar_visibility_changed,
            model.material_widget_visibility_changed,
            model.game_tags_widget_visibility_changed,
            model.coordinates_visibility_changed,
            model.flip_state_changed,
        ):
            try:
                sig.disconnect(self._update_game_info_center_margins)
            except (TypeError, RuntimeError):
                pass
    
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
        else:
            # Ensure header reflects controller defaults when there is no active game.
            # Otherwise, MainGameInfoView keeps its constructor placeholders until
            # the first time a game becomes None later.
            self._clear_game_info()
    
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


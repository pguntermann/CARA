"""Chess board state model."""

import chess
from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional, Tuple

# Import for type hints (avoid circular import)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.pv_plan_parser_service import PieceTrajectory


class BoardModel(QObject):
    """Model representing chess board state using python-chess.
    
    This model holds the board state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emitted when board state changes
    position_changed = pyqtSignal()  # Emitted when board position changes
    flip_state_changed = pyqtSignal(bool)  # Emitted when board flip state changes
    coordinates_visibility_changed = pyqtSignal(bool)  # Emitted when coordinates visibility changes
    turn_indicator_visibility_changed = pyqtSignal(bool)  # Emitted when turn indicator visibility changes
    game_info_visibility_changed = pyqtSignal(bool)  # Emitted when game info visibility changes
    playedmove_arrow_visibility_changed = pyqtSignal(bool)  # Emitted when played move arrow visibility changes
    bestnextmove_arrow_visibility_changed = pyqtSignal(bool)  # Emitted when best next move arrow visibility changes
    pv2_arrow_visibility_changed = pyqtSignal(bool)  # Emitted when PV2 arrow visibility changes
    pv3_arrow_visibility_changed = pyqtSignal(bool)  # Emitted when PV3 arrow visibility changes
    bestalternativemove_arrow_visibility_changed = pyqtSignal(bool)  # Emitted when best alternative move arrow visibility changes
    evaluation_bar_visibility_changed = pyqtSignal(bool)  # Emitted when evaluation bar visibility changes
    material_widget_visibility_changed = pyqtSignal(bool)  # Emitted when material widget visibility changes
    turn_changed = pyqtSignal(bool)  # Emitted when turn changes (True=White, False=Black)
    last_move_changed = pyqtSignal(object)  # Emitted when last move changes (chess.Move or None)
    best_next_move_changed = pyqtSignal(object)  # Emitted when best next move changes (chess.Move or None)
    pv2_move_changed = pyqtSignal(object)  # Emitted when PV2 move changes (chess.Move or None)
    pv3_move_changed = pyqtSignal(object)  # Emitted when PV3 move changes (chess.Move or None)
    best_alternative_move_changed = pyqtSignal(object)  # Emitted when best alternative move changes (chess.Move or None)
    positional_plan_changed = pyqtSignal(object)  # Emitted when positional plan changes (PieceTrajectory or None)
    active_pv_plan_changed = pyqtSignal(int)  # Emitted when active PV plan changes (1, 2, 3, or 0 for none)
    hide_other_arrows_during_plan_exploration_changed = pyqtSignal(bool)  # Emitted when hide other arrows setting changes
    
    def __init__(self, fen: Optional[str] = None) -> None:
        """Initialize the board model.
        
        Args:
            fen: Optional FEN string to initialize board position.
                 If None, starts with standard starting position.
        """
        super().__init__()
        if fen is None:
            self._board = chess.Board()
        else:
            self._board = chess.Board(fen)
        self._is_flipped = False  # Track if board is flipped 180 degrees
        self._show_coordinates = True  # Track if coordinates are visible
        self._show_turn_indicator = True  # Track if turn indicator is visible
        self._show_game_info = True  # Track if game info is visible
        self._show_playedmove_arrow = True  # Track if played move arrow is visible
        self._show_bestnextmove_arrow = True  # Track if best next move arrow is visible
        self._show_pv2_arrow = True  # Track if PV2 arrow is visible
        self._show_pv3_arrow = True  # Track if PV3 arrow is visible
        self._show_bestalternativemove_arrow = True  # Track if best alternative move arrow is visible
        self._show_evaluation_bar = False  # Track if evaluation bar is visible
        self._show_material_widget = False  # Track if material widget is visible
        self._last_move: Optional[chess.Move] = None  # Track the last move made
        self._best_next_move: Optional[chess.Move] = None  # Track the best next move from manual analysis
        self._pv2_move: Optional[chess.Move] = None  # Track the PV2 move from manual analysis
        self._pv3_move: Optional[chess.Move] = None  # Track the PV3 move from manual analysis
        self._best_alternative_move: Optional[chess.Move] = None  # Track the best alternative move from movelist
        self._positional_plans = []  # Track current positional plans (List[PieceTrajectory])
        self._active_pv_plan: int = 0  # Track which PV plan is active (0=none, 1=PV1, 2=PV2, 3=PV3)
        self._hide_other_arrows_during_plan_exploration: bool = False  # Track if other arrows should be hidden during plan exploration
    
    @property
    def board(self) -> chess.Board:
        """Get the python-chess board instance.
        
        Returns:
            The chess.Board instance.
        """
        return self._board
    
    def get_fen(self) -> str:
        """Get current position as FEN string.
        
        Returns:
            Current position as FEN string.
        """
        return self._board.fen()
    
    def set_fen(self, fen: str, last_move: Optional[chess.Move] = None) -> None:
        """Set board position from FEN string.
        
        Args:
            fen: FEN string representing the position.
            last_move: Optional last move that led to this position.
        """
        old_turn = self._board.turn if hasattr(self, '_board') else None
        
        # Capture old last move before updating
        old_last_move = getattr(self, '_last_move', None)
        
        self._board = chess.Board(fen)
        new_turn = self._board.turn
        
        # Update last move
        if last_move is not None:
            self._last_move = last_move
        elif self._board.move_stack:
            # If board has move history, get the last move
            self._last_move = self._board.move_stack[-1]
        else:
            # No move history, clear last move
            self._last_move = None
        
        self.position_changed.emit()
        
        # Always emit last_move_changed when position changes (even if move is the same)
        # This ensures the view updates when navigating through moves
        self.last_move_changed.emit(self._last_move)
        
        # Emit turn_changed if turn actually changed
        if old_turn is not None and old_turn != new_turn:
            self.turn_changed.emit(new_turn == chess.WHITE)
    
    def reset_to_starting_position(self) -> None:
        """Reset board to standard starting position."""
        old_turn = self._board.turn if hasattr(self, '_board') else None
        self._board.reset()
        new_turn = self._board.turn
        
        # Clear last move on reset
        self._last_move = None
        self.last_move_changed.emit(None)
        
        self.position_changed.emit()
        
        # Emit turn_changed if turn actually changed (usually White after reset)
        if old_turn is not None and old_turn != new_turn:
            self.turn_changed.emit(new_turn == chess.WHITE)
        elif old_turn is None:
            # First initialization - emit initial turn state
            self.turn_changed.emit(new_turn == chess.WHITE)
    
    def get_piece_at_square(self, file: int, rank: int) -> Optional[Tuple[str, str]]:
        """Get piece at a square.
        
        Args:
            file: File index (0-7, a-h).
            rank: Rank index (0-7, 1-8).
        
        Returns:
            Tuple (color, piece_type) if piece exists, None otherwise.
            color: 'w' or 'b'
            piece_type: 'p', 'r', 'n', 'b', 'q', 'k'
        """
        chess_square = chess.square(file, rank)
        piece = self._board.piece_at(chess_square)
        
        if piece is None:
            return None
        
        # Convert chess.Piece to our representation
        color = 'w' if piece.color == chess.WHITE else 'b'
        
        piece_type_map = {
            chess.PAWN: 'p',
            chess.ROOK: 'r',
            chess.KNIGHT: 'n',
            chess.BISHOP: 'b',
            chess.QUEEN: 'q',
            chess.KING: 'k',
        }
        
        piece_type = piece_type_map[piece.piece_type]
        return (color, piece_type)
    
    def get_all_pieces(self) -> dict[Tuple[int, int], Tuple[str, str]]:
        """Get all pieces on the board.
        
        Returns:
            Dictionary mapping (file, rank) -> (color, piece_type)
            where file and rank are 0-7.
        """
        pieces = {}
        for rank in range(8):
            for file in range(8):
                piece = self.get_piece_at_square(file, rank)
                if piece:
                    pieces[(file, rank)] = piece
        return pieces
    
    def rotate_180(self) -> None:
        """Rotate the board 180 degrees visually (flip board display).
        
        This method only changes the visual flip state, NOT the actual board position.
        FEN notation always represents the position from White's perspective,
        regardless of visual rotation.
        """
        # Only toggle the visual flip state - do NOT change the actual board position
        self._is_flipped = not self._is_flipped
        
        # Emit signal for visual update (no position_changed signal needed)
        self.flip_state_changed.emit(self._is_flipped)
    
    @property
    def is_flipped(self) -> bool:
        """Get whether the board is flipped 180 degrees.
        
        Returns:
            True if board is flipped, False otherwise.
        """
        return self._is_flipped
    
    def toggle_coordinates_visibility(self) -> None:
        """Toggle the visibility of board coordinates.
        
        This method changes the visibility state and emits a signal
        for views to update their display.
        """
        self._show_coordinates = not self._show_coordinates
        self.coordinates_visibility_changed.emit(self._show_coordinates)
    
    @property
    def show_coordinates(self) -> bool:
        """Get whether coordinates are visible.
        
        Returns:
            True if coordinates are visible, False otherwise.
        """
        return self._show_coordinates
    
    def set_show_coordinates(self, show: bool) -> None:
        """Set the visibility of board coordinates.
        
        Args:
            show: True to show coordinates, False to hide them.
        """
        if self._show_coordinates != show:
            self._show_coordinates = show
            self.coordinates_visibility_changed.emit(self._show_coordinates)
    
    def toggle_turn_indicator_visibility(self) -> None:
        """Toggle the visibility of turn indicator.
        
        This method changes the visibility state and emits a signal
        for views to update their display.
        """
        self._show_turn_indicator = not self._show_turn_indicator
        self.turn_indicator_visibility_changed.emit(self._show_turn_indicator)
    
    @property
    def show_turn_indicator(self) -> bool:
        """Get whether turn indicator is visible.
        
        Returns:
            True if turn indicator is visible, False otherwise.
        """
        return self._show_turn_indicator
    
    def set_show_turn_indicator(self, show: bool) -> None:
        """Set the visibility of turn indicator.
        
        Args:
            show: True to show turn indicator, False to hide it.
        """
        if self._show_turn_indicator != show:
            self._show_turn_indicator = show
            self.turn_indicator_visibility_changed.emit(self._show_turn_indicator)
    
    def toggle_game_info_visibility(self) -> None:
        """Toggle the visibility of game info.
        
        This method changes the visibility state and emits a signal
        for views to update their display.
        """
        self._show_game_info = not self._show_game_info
        self.game_info_visibility_changed.emit(self._show_game_info)
    
    @property
    def show_game_info(self) -> bool:
        """Get whether game info is visible.
        
        Returns:
            True if game info is visible, False otherwise.
        """
        return self._show_game_info
    
    def set_show_game_info(self, show: bool) -> None:
        """Set the visibility of game info.
        
        Args:
            show: True to show game info, False to hide it.
        """
        if self._show_game_info != show:
            self._show_game_info = show
            self.game_info_visibility_changed.emit(self._show_game_info)
    
    def is_white_turn(self) -> bool:
        """Get whether it is White's turn.
        
        Returns:
            True if White's turn, False if Black's turn.
        """
        return self._board.turn == chess.WHITE
    
    @property
    def show_playedmove_arrow(self) -> bool:
        """Get played move arrow visibility state.
        
        Returns:
            True if played move arrow is visible, False otherwise.
        """
        return self._show_playedmove_arrow
    
    def set_show_playedmove_arrow(self, show: bool) -> None:
        """Set played move arrow visibility.
        
        Args:
            show: True to show played move arrow, False to hide it.
        """
        if self._show_playedmove_arrow != show:
            self._show_playedmove_arrow = show
            self.playedmove_arrow_visibility_changed.emit(show)
    
    def toggle_playedmove_arrow_visibility(self) -> None:
        """Toggle played move arrow visibility."""
        self.set_show_playedmove_arrow(not self._show_playedmove_arrow)
    
    @property
    def show_bestnextmove_arrow(self) -> bool:
        """Get best next move arrow visibility state.
        
        Returns:
            True if best next move arrow is visible, False otherwise.
        """
        return self._show_bestnextmove_arrow
    
    def set_show_bestnextmove_arrow(self, show: bool) -> None:
        """Set best next move arrow visibility.
        
        Args:
            show: True to show best next move arrow, False to hide it.
        """
        if self._show_bestnextmove_arrow != show:
            self._show_bestnextmove_arrow = show
            self.bestnextmove_arrow_visibility_changed.emit(show)
    
    def toggle_bestnextmove_arrow_visibility(self) -> None:
        """Toggle best next move arrow visibility."""
        self.set_show_bestnextmove_arrow(not self._show_bestnextmove_arrow)
    
    @property
    def show_pv2_arrow(self) -> bool:
        """Get PV2 arrow visibility state.
        
        Returns:
            True if PV2 arrow is visible, False otherwise.
        """
        return self._show_pv2_arrow
    
    def set_show_pv2_arrow(self, show: bool) -> None:
        """Set PV2 arrow visibility.
        
        Args:
            show: True to show PV2 arrow, False to hide it.
        """
        if self._show_pv2_arrow != show:
            self._show_pv2_arrow = show
            self.pv2_arrow_visibility_changed.emit(show)
    
    def toggle_pv2_arrow_visibility(self) -> None:
        """Toggle PV2 arrow visibility."""
        self.set_show_pv2_arrow(not self._show_pv2_arrow)
    
    @property
    def show_pv3_arrow(self) -> bool:
        """Get PV3 arrow visibility state.
        
        Returns:
            True if PV3 arrow is visible, False otherwise.
        """
        return self._show_pv3_arrow
    
    def set_show_pv3_arrow(self, show: bool) -> None:
        """Set PV3 arrow visibility.
        
        Args:
            show: True to show PV3 arrow, False to hide it.
        """
        if self._show_pv3_arrow != show:
            self._show_pv3_arrow = show
            self.pv3_arrow_visibility_changed.emit(show)
    
    def toggle_pv3_arrow_visibility(self) -> None:
        """Toggle PV3 arrow visibility."""
        self.set_show_pv3_arrow(not self._show_pv3_arrow)
    
    @property
    def show_bestalternativemove_arrow(self) -> bool:
        """Get best alternative move arrow visibility state.
        
        Returns:
            True if best alternative move arrow is visible, False otherwise.
        """
        return self._show_bestalternativemove_arrow
    
    def set_show_bestalternativemove_arrow(self, show: bool) -> None:
        """Set best alternative move arrow visibility.
        
        Args:
            show: True to show best alternative move arrow, False to hide it.
        """
        if self._show_bestalternativemove_arrow != show:
            self._show_bestalternativemove_arrow = show
            self.bestalternativemove_arrow_visibility_changed.emit(show)
    
    def toggle_bestalternativemove_arrow_visibility(self) -> None:
        """Toggle best alternative move arrow visibility."""
        self.set_show_bestalternativemove_arrow(not self._show_bestalternativemove_arrow)
    
    @property
    def best_next_move(self) -> Optional[chess.Move]:
        """Get the best next move from manual analysis.
        
        Returns:
            The best next Move object, or None if no best next move available.
        """
        return self._best_next_move
    
    def set_best_next_move(self, move: Optional[chess.Move]) -> None:
        """Set the best next move from manual analysis.
        
        Args:
            move: The best next Move object, or None to clear.
        """
        if self._best_next_move != move:
            self._best_next_move = move
            self.best_next_move_changed.emit(move)
    
    @property
    def pv2_move(self) -> Optional[chess.Move]:
        """Get the PV2 move from manual analysis.
        
        Returns:
            The PV2 Move object, or None if no PV2 move available.
        """
        return self._pv2_move
    
    def set_pv2_move(self, move: Optional[chess.Move]) -> None:
        """Set the PV2 move from manual analysis.
        
        Args:
            move: The PV2 Move object, or None to clear.
        """
        if self._pv2_move != move:
            self._pv2_move = move
            self.pv2_move_changed.emit(move)
    
    @property
    def pv3_move(self) -> Optional[chess.Move]:
        """Get the PV3 move from manual analysis.
        
        Returns:
            The PV3 Move object, or None if no PV3 move available.
        """
        return self._pv3_move
    
    def set_pv3_move(self, move: Optional[chess.Move]) -> None:
        """Set the PV3 move from manual analysis.
        
        Args:
            move: The PV3 Move object, or None to clear.
        """
        if self._pv3_move != move:
            self._pv3_move = move
            self.pv3_move_changed.emit(move)
    
    @property
    def show_evaluation_bar(self) -> bool:
        """Get evaluation bar visibility state.
        
        Returns:
            True if evaluation bar is visible, False otherwise.
        """
        return self._show_evaluation_bar
    
    def set_show_evaluation_bar(self, show: bool) -> None:
        """Set evaluation bar visibility.
        
        Args:
            show: True to show evaluation bar, False to hide it.
        """
        if self._show_evaluation_bar != show:
            self._show_evaluation_bar = show
            self.evaluation_bar_visibility_changed.emit(show)
    
    def toggle_evaluation_bar_visibility(self) -> None:
        """Toggle evaluation bar visibility."""
        self.set_show_evaluation_bar(not self._show_evaluation_bar)
    
    @property
    def show_material_widget(self) -> bool:
        """Get whether material widget is visible.
        
        Returns:
            True if material widget is visible, False otherwise.
        """
        return self._show_material_widget
    
    def set_show_material_widget(self, show: bool) -> None:
        """Set the visibility of material widget.
        
        Args:
            show: True to show material widget, False to hide it.
        """
        if self._show_material_widget != show:
            self._show_material_widget = show
            self.material_widget_visibility_changed.emit(self._show_material_widget)
    
    def toggle_material_widget_visibility(self) -> None:
        """Toggle the visibility of material widget.
        
        This method changes the visibility state and emits a signal
        for views to update their display.
        """
        self.set_show_material_widget(not self._show_material_widget)
    
    @property
    def last_move(self) -> Optional[chess.Move]:
        """Get the last move made.
        
        Returns:
            The last Move object, or None if no move has been made.
        """
        return self._last_move
    
    @property
    def best_alternative_move(self) -> Optional[chess.Move]:
        """Get the best alternative move from movelist.
        
        Returns:
            The best alternative Move object, or None if no best alternative move available.
        """
        return self._best_alternative_move
    
    def set_best_alternative_move(self, move: Optional[chess.Move]) -> None:
        """Set the best alternative move from movelist.
        
        Args:
            move: The best alternative Move object, or None to clear.
        """
        if self._best_alternative_move != move:
            self._best_alternative_move = move
            self.best_alternative_move_changed.emit(move)
    
    @property
    def positional_plan(self):
        """Get the current positional plan trajectory (first one for backward compatibility).
        
        Returns:
            PieceTrajectory object, or None if no plan is active.
        """
        return self._positional_plans[0] if self._positional_plans else None
    
    @property
    def positional_plans(self):
        """Get all current positional plan trajectories.
        
        Returns:
            List of PieceTrajectory objects. Empty list if no plans are active.
        """
        return self._positional_plans.copy()
    
    def set_positional_plan(self, plan) -> None:
        """Set the current positional plan trajectory (backward compatibility).
        
        Args:
            plan: PieceTrajectory object, or None to clear.
        """
        if plan is None:
            self.set_positional_plans([])
        else:
            self.set_positional_plans([plan])
    
    def set_positional_plans(self, plans) -> None:
        """Set the current positional plan trajectories.
        
        Args:
            plans: List of PieceTrajectory objects, or empty list to clear.
        """
        if self._positional_plans != plans:
            self._positional_plans = plans.copy() if plans else []
            # Emit the first plan for backward compatibility
            self.positional_plan_changed.emit(self._positional_plans[0] if self._positional_plans else None)
    
    @property
    def active_pv_plan(self) -> int:
        """Get which PV plan is currently active.
        
        Returns:
            0 if no plan is active, 1-3 for PV1-PV3.
        """
        return self._active_pv_plan
    
    def set_active_pv_plan(self, pv_number: int) -> None:
        """Set which PV plan is currently active.
        
        Args:
            pv_number: 0 to disable, 1-3 for PV1-PV3.
        """
        if pv_number < 0 or pv_number > 3:
            pv_number = 0
        if self._active_pv_plan != pv_number:
            self._active_pv_plan = pv_number
            self.active_pv_plan_changed.emit(pv_number)
    
    @property
    def hide_other_arrows_during_plan_exploration(self) -> bool:
        """Get whether other arrows should be hidden during plan exploration.
        
        Returns:
            True if other arrows should be hidden, False otherwise.
        """
        return self._hide_other_arrows_during_plan_exploration
    
    def set_hide_other_arrows_during_plan_exploration(self, hide: bool) -> None:
        """Set whether other arrows should be hidden during plan exploration.
        
        Args:
            hide: True to hide other arrows, False to show them.
        """
        old_value = self._hide_other_arrows_during_plan_exploration
        self._hide_other_arrows_during_plan_exploration = hide
        # Always emit signal to ensure UI updates, even if value didn't change
        # (in case the active plan state changed)
        if old_value != hide:
            self.hide_other_arrows_during_plan_exploration_changed.emit(hide)


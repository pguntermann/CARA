"""Hoverable PV label that shows mini chessboard on move hover."""

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMouseEvent
import chess
from typing import Dict, Any, List, Optional

from app.views.mini_chessboard_widget import MiniChessBoardWidget
from app.controllers.board_controller import BoardController


class HoverablePvLabel(QLabel):
    """QLabel subclass that shows mini chessboard on move hover.
    
    This label represents a single move in a PV line. When hovered, it shows
    the position after that move.
    """
    
    def __init__(self, move_text: str, move_index: int, pv_moves: List[str],
                 current_fen: str, board_controller: BoardController,
                 config: Dict[str, Any], multipv: int = 0,
                 analysis_model = None) -> None:
        """Initialize the hoverable PV label for a single move.
        
        Args:
            move_text: The move text to display (e.g., "Nf3").
            move_index: Index of this move in the PV (0-based).
            pv_moves: Complete list of move strings in the PV.
            current_fen: FEN string of the current analysis position.
            board_controller: BoardController instance for getting board orientation.
            config: Configuration dictionary.
            multipv: MultiPV number for this line.
            analysis_model: Optional ManualAnalysisModel to check if miniature preview is enabled.
        """
        super().__init__(move_text)
        self._move_text = move_text
        self._move_index = move_index
        self._pv_moves = pv_moves
        self._current_fen = current_fen
        self._board_controller = board_controller
        self.config = config
        self._multipv = multipv
        self._analysis_model = analysis_model
        
        # Track hover state
        self._is_hovered = False
        
        # Debouncing
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._on_hover_timeout)
        
        # Mini-board popup
        self._mini_board: Optional[MiniChessBoardWidget] = None
        
        # Snapshot of PV moves and FEN when hover starts (to prevent updates during hover)
        self._frozen_pv_moves: Optional[List[str]] = None
        self._frozen_current_fen: Optional[str] = None
        
        # Stable Y position for mini-board (set when hover starts)
        self._stable_y_position: Optional[int] = None
        
        # Get hover delay from config
        manual_analysis_config = config.get('ui', {}).get('panels', {}).get('detail', {}).get('manual_analysis', {})
        pv_hover_config = manual_analysis_config.get('pv_hover', {})
        self._hover_delay = pv_hover_config.get('hover_delay_ms', 50)
        
        # Get mini-board position offset from config
        mini_board_config = pv_hover_config.get('mini_board', {})
        self._offset_x = mini_board_config.get('offset_x', 20)
        self._offset_y = mini_board_config.get('offset_y', 20)
        
        # Enable mouse tracking
        self.setMouseTracking(True)
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to detect hover."""
        super().mouseMoveEvent(event)
        
        # Check if miniature preview is enabled
        if self._analysis_model and not self._analysis_model.enable_miniature_preview:
            return
        
        # Mouse is over this label (which represents a single move)
        if not self._is_hovered:
            self._is_hovered = True
            
            # Freeze PV snapshot when hover starts (prevents updates during hover)
            self._frozen_pv_moves = list(self._pv_moves)  # Create a copy
            self._frozen_current_fen = self._current_fen
            
            # Add underline highlighting
            current_text = self.text()
            # Check if text already has underline
            if 'text-decoration: underline' not in current_text and 'text-decoration:underline' not in current_text:
                # If text already has a span, add underline to existing style
                if current_text.startswith('<span') and current_text.endswith('</span>'):
                    # Extract existing style and add underline
                    import re
                    # Match <span style="...">content</span>
                    match = re.match(r'<span style="([^"]*)">(.*?)</span>', current_text)
                    if match:
                        existing_style = match.group(1)
                        content = match.group(2)
                        # Add underline to existing style
                        if 'text-decoration' not in existing_style:
                            new_style = existing_style + '; text-decoration: underline'
                        else:
                            new_style = existing_style
                        underlined_text = f'<span style="{new_style}">{content}</span>'
                        self.setText(underlined_text)
                    else:
                        # Try without quotes
                        match = re.match(r'<span style=([^>]*)>(.*?)</span>', current_text)
                        if match:
                            existing_style = match.group(1)
                            content = match.group(2)
                            if 'text-decoration' not in existing_style:
                                new_style = existing_style + '; text-decoration: underline'
                            else:
                                new_style = existing_style
                            underlined_text = f'<span style="{new_style}">{content}</span>'
                            self.setText(underlined_text)
                        else:
                            # Fallback: wrap with underline span
                            underlined_text = f'<span style="text-decoration: underline;">{current_text}</span>'
                            self.setText(underlined_text)
                else:
                    # No existing span, wrap with underline span
                    underlined_text = f'<span style="text-decoration: underline;">{current_text}</span>'
                    self.setText(underlined_text)
            
            # Start debounce timer
            self._hover_timer.start(self._hover_delay)
    
    def enterEvent(self, event) -> None:
        """Handle mouse enter."""
        super().enterEvent(event)
        # No action needed - mouseMoveEvent will handle it
    
    def leaveEvent(self, event) -> None:
        """Handle mouse leave - hide mini-board."""
        super().leaveEvent(event)
        
        # Cancel any pending update
        self._hover_timer.stop()
        
        # Hide mini-board and clear frozen state
        self._is_hovered = False
        self._hide_mini_board()
        self._frozen_pv_moves = None
        self._frozen_current_fen = None
        self._stable_y_position = None
        
        # Remove underline highlighting
        current_text = self.text()
        # Remove underline from style if present
        if 'text-decoration: underline' in current_text or 'text-decoration:underline' in current_text:
            import re
            # If text has a span with underline, remove underline from style
            if current_text.startswith('<span') and current_text.endswith('</span>'):
                # Match <span style="...">content</span>
                match = re.match(r'<span style="([^"]*)">(.*?)</span>', current_text)
                if match:
                    existing_style = match.group(1)
                    content = match.group(2)
                    # Remove underline from style
                    new_style = re.sub(r';\s*text-decoration:\s*underline|text-decoration:\s*underline\s*;?', '', existing_style)
                    new_style = new_style.strip().rstrip(';').strip()
                    if new_style:
                        ununderlined_text = f'<span style="{new_style}">{content}</span>'
                    else:
                        # No style left, just use content
                        ununderlined_text = content
                    self.setText(ununderlined_text)
                else:
                    # Try without quotes
                    match = re.match(r'<span style=([^>]*)>(.*?)</span>', current_text)
                    if match:
                        existing_style = match.group(1)
                        content = match.group(2)
                        new_style = re.sub(r';\s*text-decoration:\s*underline|text-decoration:\s*underline\s*;?', '', existing_style)
                        new_style = new_style.strip().rstrip(';').strip()
                        if new_style:
                            ununderlined_text = f'<span style="{new_style}">{content}</span>'
                        else:
                            ununderlined_text = content
                        self.setText(ununderlined_text)
                    else:
                        # Fallback: try to extract content from simple underline span
                        match = re.search(r'<span style="text-decoration: underline;">(.*?)</span>', current_text)
                        if match:
                            self.setText(match.group(1))
    
    def _on_hover_timeout(self) -> None:
        """Handle hover timeout - show mini-board with position."""
        # Use frozen PV snapshot if available (prevents updates during hover)
        pv_moves_to_use = self._frozen_pv_moves if self._frozen_pv_moves is not None else self._pv_moves
        current_fen_to_use = self._frozen_current_fen if self._frozen_current_fen is not None else self._current_fen
        
        # Calculate position after applying moves up to and including this move
        try:
            # Start from frozen analysis position
            board = chess.Board(current_fen_to_use)
            
            # Apply moves up to and including this move (using frozen PV)
            moves_to_apply = pv_moves_to_use[:self._move_index + 1]
            
            for move_text in moves_to_apply:
                try:
                    move = board.parse_san(move_text)
                    board.push(move)
                except (chess.InvalidMoveError, ValueError):
                    # Invalid move - abort
                    return
            
            # Get FEN after applying moves
            new_fen = board.fen()
            
            # Get board orientation and arrow visibility from board controller
            is_flipped = False
            show_arrow = False
            move_to_show = None
            
            if self._board_controller:
                board_model = self._board_controller.get_board_model()
                if board_model:
                    is_flipped = board_model.is_flipped
                    # Check if "Show best move arrow" is enabled
                    show_arrow = board_model.show_bestnextmove_arrow
                    
                    # Get the move for this position (the move that leads to this position)
                    if self._move_index < len(pv_moves_to_use):
                        move_text = pv_moves_to_use[self._move_index]
                        try:
                            # Parse the move from the position before this move
                            temp_board = chess.Board(current_fen_to_use)
                            # Apply moves up to (but not including) this move
                            for i in range(self._move_index):
                                temp_move = temp_board.parse_san(pv_moves_to_use[i])
                                temp_board.push(temp_move)
                            # Now parse this move
                            move_to_show = temp_board.parse_san(move_text)
                        except (chess.InvalidMoveError, ValueError):
                            move_to_show = None
            
            # Show or update mini-board
            self._show_mini_board(new_fen, is_flipped, move_to_show, show_arrow)
            
        except Exception:
            # Any error - hide mini-board
            self._hide_mini_board()
    
    def _show_mini_board(self, fen: str, is_flipped: bool, move: Optional[chess.Move] = None, show_arrow: bool = False) -> None:
        """Show mini-board popup at cursor position.
        
        Args:
            fen: FEN string of position to display.
            is_flipped: Whether board should be flipped.
            move: Optional move to show with arrow.
            show_arrow: Whether to show the arrow (if "Show best move arrow" is enabled).
        """
        # Get scale factor from analysis model
        scale_factor = 1.0
        if self._analysis_model:
            scale_factor = self._analysis_model.miniature_preview_scale_factor
        
        if self._mini_board is None:
            # Create mini-board with scale factor
            self._mini_board = MiniChessBoardWidget(self.config, fen, is_flipped, scale_factor)
            self._mini_board.hide()
        else:
            # Update scale factor if it changed (recreate widget to apply new size)
            current_scale = getattr(self._mini_board, '_scale_factor', 1.0)
            if abs(current_scale - scale_factor) > 0.01:  # Use small epsilon for float comparison
                # Recreate widget with new scale factor
                self._mini_board.hide()
                self._mini_board = MiniChessBoardWidget(self.config, fen, is_flipped, scale_factor)
                self._mini_board.hide()
        
        # Update position and orientation
        self._mini_board.set_position(fen)
        self._mini_board.set_flipped(is_flipped)
        self._mini_board.set_move(move, show_arrow)
        
        # Get cursor position in global coordinates
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication
        cursor_pos = QCursor.pos()
        
        # Get screen geometry to check boundaries
        screen = QApplication.screenAt(cursor_pos)
        if screen is None:
            # Fallback to primary screen
            screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # Get mini-board size
        mini_board_size = self._mini_board.size()
        mini_board_width = mini_board_size.width()
        mini_board_height = mini_board_size.height()
        
        # Calculate initial popup position (offset from cursor)
        popup_x = cursor_pos.x() + self._offset_x
        
        # Use stable Y position if set, otherwise set it now
        if self._stable_y_position is not None:
            popup_y = self._stable_y_position
        else:
            popup_y = cursor_pos.y() + self._offset_y
            self._stable_y_position = int(popup_y)
        
        # Adjust position to keep mini-board within screen boundaries
        # Check right boundary
        if popup_x + mini_board_width > screen_geometry.right():
            # Move left to fit
            popup_x = screen_geometry.right() - mini_board_width
        
        # Check left boundary
        if popup_x < screen_geometry.left():
            popup_x = screen_geometry.left()
        
        # Check bottom boundary
        if popup_y + mini_board_height > screen_geometry.bottom():
            # Move up to fit
            popup_y = screen_geometry.bottom() - mini_board_height
        
        # Check top boundary
        if popup_y < screen_geometry.top():
            popup_y = screen_geometry.top()
        
        # Move mini-board to adjusted position
        self._mini_board.move(int(popup_x), int(popup_y))
        
        # Show mini-board
        if not self._mini_board.isVisible():
            self._mini_board.show()
    
    def _hide_mini_board(self) -> None:
        """Hide mini-board popup."""
        if self._mini_board:
            self._mini_board.hide()
    
    def update_pv(self, pv_moves: List[str], current_fen: str) -> None:
        """Update PV moves and FEN (only if not currently hovered).
        
        Args:
            pv_moves: New list of PV moves.
            current_fen: New current FEN.
        """
        if not self._is_hovered:
            self._pv_moves = pv_moves
            self._current_fen = current_fen
            # Note: We don't update the displayed text here because
            # the widget will be recreated on analysis updates anyway

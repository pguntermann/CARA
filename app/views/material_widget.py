"""Material widget for displaying captured pieces and material difference."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QFontDatabase
from PyQt6.QtCore import Qt, QRect
from typing import Dict, Any, Optional, List
from collections import Counter
import chess

from app.models.board_model import BoardModel
from app.utils.material_tracker import PIECE_VALUES, calculate_material_balance
from app.utils.font_utils import resolve_font_family


class MaterialWidget(QWidget):
    """Widget displaying captured pieces and material difference."""
    
    # Mapping from chess piece type to letter symbol
    PIECE_LETTERS = {
        chess.PAWN: 'P',
        chess.ROOK: 'R',
        chess.KNIGHT: 'N',
        chess.BISHOP: 'B',
        chess.QUEEN: 'Q',
        chess.KING: 'K',
    }
    
    def __init__(self, config: Dict[str, Any], board_model: Optional[BoardModel] = None) -> None:
        """Initialize the material widget.
        
        Args:
            config: Configuration dictionary.
            board_model: Optional BoardModel to observe.
        """
        super().__init__()
        self.config = config
        self._board_model: Optional[BoardModel] = None
        self._is_flipped = False
        
        # Track captured pieces (pieces that were on board initially but are now gone)
        self._initial_white_pieces: Dict[int, int] = {}  # {piece_type: count}
        self._initial_black_pieces: Dict[int, int] = {}  # {piece_type: count}
        self._captured_by_white: List[int] = []  # List of piece types captured by white
        self._captured_by_black: List[int] = []  # List of piece types captured by black
        
        self._load_config()
        self._setup_ui()
        
        # Connect to model if provided
        if board_model:
            self.set_board_model(board_model)
    
    def _load_config(self) -> None:
        """Load configuration from config dictionary."""
        board_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
        material_config = board_config.get("material_widget", {})
        pieces_config = board_config.get("pieces", {})
        
        self.widget_width = material_config.get("width", 120)
        self.widget_height = material_config.get("height", 60)
        self.padding = material_config.get("padding", [10, 10, 10, 10])  # [top, right, bottom, left]
        self.background_color = QColor(*material_config.get("background_color", [30, 30, 35]))
        self.border_color = QColor(*material_config.get("border_color", [60, 60, 65]))
        self.border_radius = material_config.get("border_radius", 5)
        font_family_raw = material_config.get("font_family", "Helvetica Neue")
        self.font_family = resolve_font_family(font_family_raw)
        self.font_size = material_config.get("font_size", 10)
        self.white_text_color = QColor(*material_config.get("white_text_color", [240, 240, 240]))
        self.black_text_color = QColor(*material_config.get("black_text_color", [200, 200, 200]))
        self.difference_text_color = QColor(*material_config.get("difference_text_color", [255, 255, 100]))
        self.separator_color = QColor(*material_config.get("separator_color", [100, 100, 105]))
        
        # Set fixed size
        self.setFixedSize(self.widget_width, self.widget_height)
    
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setMinimumSize(self.widget_width, self.widget_height)
        self.setMaximumSize(self.widget_width, self.widget_height)
    
    def set_board_model(self, model: BoardModel) -> None:
        """Set the board model to observe.
        
        Args:
            model: BoardModel instance.
        """
        if self._board_model:
            # Disconnect from old model
            try:
                self._board_model.position_changed.disconnect(self._on_position_changed)
                self._board_model.flip_state_changed.disconnect(self._on_flip_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._board_model = model
        
        if self._board_model:
            # Connect to new model
            self._board_model.position_changed.connect(self._on_position_changed)
            self._board_model.flip_state_changed.connect(self._on_flip_changed)
            # Initialize with current position
            self._on_position_changed()
            self._on_flip_changed(self._board_model.is_flipped)
    
    def set_flipped(self, is_flipped: bool) -> None:
        """Set board flip state.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if self._is_flipped != is_flipped:
            self._is_flipped = is_flipped
            self.update()
    
    def _on_flip_changed(self, is_flipped: bool) -> None:
        """Handle board flip state change from model.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        self.set_flipped(is_flipped)
    
    def _on_position_changed(self) -> None:
        """Handle position change from model."""
        if not self._board_model:
            return
        
        # Update captured pieces based on current board state
        self._update_captured_pieces()
        self.update()
    
    def force_update(self) -> None:
        """Force update of the material widget based on current board position.
        
        This method can be called to ensure the widget updates even if the
        position_changed signal wasn't emitted or the connection was broken.
        """
        if not self._board_model:
            return
        
        # Ensure initial pieces are set (fallback if not set yet)
        if not self._initial_white_pieces and not self._initial_black_pieces:
            # Try to get starting FEN from board model if available
            # This is a fallback - ideally initial pieces should be set when game is loaded
            board = self._board_model.board
            self._initial_white_pieces = {}
            self._initial_black_pieces = {}
            for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                self._initial_white_pieces[piece_type] = len(chess.Board().pieces(piece_type, chess.WHITE))
                self._initial_black_pieces[piece_type] = len(chess.Board().pieces(piece_type, chess.BLACK))
        
        # Update captured pieces based on current board state
        self._update_captured_pieces()
        self.update()
    
    def set_at_starting_position(self, is_at_start: bool) -> None:
        """Set whether we're at the starting position.
        
        Args:
            is_at_start: True if at starting position, False otherwise.
        """
        if is_at_start and self._board_model:
            # Only reset initial pieces if they haven't been set yet
            # This prevents overwriting correct initial pieces when navigating to ply 0
            # after the board has already been moved from the starting position
            if not self._initial_white_pieces and not self._initial_black_pieces:
                # Reset initial pieces when at starting position (only if not already set)
                board = self._board_model.board
                self._initial_white_pieces = {}
                self._initial_black_pieces = {}
                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                    self._initial_white_pieces[piece_type] = len(board.pieces(piece_type, chess.WHITE))
                    self._initial_black_pieces[piece_type] = len(board.pieces(piece_type, chess.BLACK))
                # Update captured pieces after resetting initial pieces
                self._update_captured_pieces()
                self.update()
            else:
                # Still update captured pieces based on current position
                self._update_captured_pieces()
                self.update()
    
    def set_initial_pieces_from_fen(self, fen: str) -> None:
        """Set initial pieces from a FEN string.
        
        This method allows setting the initial piece counts from a custom starting position,
        which is useful when a game has a custom FEN starting position.
        
        Args:
            fen: FEN string representing the starting position.
        """
        try:
            starting_board = chess.Board(fen)
            self._initial_white_pieces = {}
            self._initial_black_pieces = {}
            for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                self._initial_white_pieces[piece_type] = len(starting_board.pieces(piece_type, chess.WHITE))
                self._initial_black_pieces[piece_type] = len(starting_board.pieces(piece_type, chess.BLACK))
            # Update captured pieces after setting initial pieces
            if self._board_model:
                self._update_captured_pieces()
                self.update()
        except Exception:
            # If FEN parsing fails, fall back to standard starting position
            starting_board = chess.Board()
            self._initial_white_pieces = {}
            self._initial_black_pieces = {}
            for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                self._initial_white_pieces[piece_type] = len(starting_board.pieces(piece_type, chess.WHITE))
                self._initial_black_pieces[piece_type] = len(starting_board.pieces(piece_type, chess.BLACK))
    
    def _update_captured_pieces(self) -> None:
        """Update the list of captured pieces based on current board state."""
        if not self._board_model:
            return
        
        board = self._board_model.board
        
        # Note: We don't check move_stack here because set_fen() creates a new board
        # with empty move_stack. Instead, we rely on set_at_starting_position() being
        # called when we're at the starting position (ply_index == 0)
        
        # Initialize starting position pieces if not already done (fallback for edge cases)
        # Note: This fallback assumes standard starting position, which may be incorrect
        # if the game has a custom FEN. The proper fix is to call set_initial_pieces_from_fen()
        # when a game is loaded, which should happen in _on_active_game_changed().
        # IMPORTANT: Only initialize if BOTH dictionaries are empty (not just one)
        # This ensures we don't reset initial pieces when jumping directly to a move
        # if they were already set when the game was loaded
        if not self._initial_white_pieces and not self._initial_black_pieces:
            # Fallback: assume standard starting position
            # This is a last resort - ideally initial pieces should be set when game is loaded
            try:
                starting_board = chess.Board()
                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                    self._initial_white_pieces[piece_type] = len(starting_board.pieces(piece_type, chess.WHITE))
                    self._initial_black_pieces[piece_type] = len(starting_board.pieces(piece_type, chess.BLACK))
            except Exception:
                # Final fallback to standard starting position
                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                    self._initial_white_pieces[piece_type] = len(chess.Board().pieces(piece_type, chess.WHITE))
                    self._initial_black_pieces[piece_type] = len(chess.Board().pieces(piece_type, chess.BLACK))
        
        # Calculate current piece counts
        current_white_pieces: Dict[int, int] = {}
        current_black_pieces: Dict[int, int] = {}
        
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            current_white_pieces[piece_type] = len(board.pieces(piece_type, chess.WHITE))
            current_black_pieces[piece_type] = len(board.pieces(piece_type, chess.BLACK))
        
        # Calculate captured pieces
        self._captured_by_white = []
        self._captured_by_black = []
        
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            # Pieces captured by white (black pieces that are missing)
            initial_black = self._initial_black_pieces.get(piece_type, 0)
            current_black = current_black_pieces.get(piece_type, 0)
            captured_count = initial_black - current_black
            for _ in range(captured_count):
                self._captured_by_white.append(piece_type)
            
            # Pieces captured by black (white pieces that are missing)
            initial_white = self._initial_white_pieces.get(piece_type, 0)
            current_white = current_white_pieces.get(piece_type, 0)
            captured_count = initial_white - current_white
            for _ in range(captured_count):
                self._captured_by_black.append(piece_type)
    
    def _calculate_material_difference(self) -> float:
        """Calculate material difference in pawns (positive = white advantage).
        
        Returns:
            Material difference in pawns.
        """
        if not self._board_model:
            return 0.0
        
        # Calculate material balance (in centipawns)
        balance = calculate_material_balance(self._board_model.board)
        
        # Convert to pawns (divide by 100)
        return balance / 100.0
    
    def paintEvent(self, event) -> None:
        """Paint the material widget."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.widget_width
        height = self.widget_height
        
        # Draw background with border
        painter.setBrush(QColor(self.background_color))
        painter.setPen(QColor(self.border_color))
        painter.drawRoundedRect(0, 0, width, height, self.border_radius, self.border_radius)
        
        # Setup font for material difference text only
        font = QFont(self.font_family, self.font_size)
        painter.setFont(font)
        fm = QFontMetrics(font)
        line_height = fm.height()  # Define line_height here for use throughout
        
        # Calculate text area (inside padding)
        text_area_x = self.padding[3]  # left padding
        text_area_y = self.padding[0]  # top padding
        text_area_width = width - self.padding[3] - self.padding[1]  # left + right padding
        text_area_height = height - self.padding[0] - self.padding[2]  # top + bottom padding
        
        # Calculate spacing
        spacing = 10  # Spacing between white and black piece sections
        text_spacing = 6  # Spacing between piece labels
        
        # Fixed height for each side: 2 rows of text
        rows_per_side = 2
        fixed_side_height = rows_per_side * line_height + (rows_per_side - 1) * text_spacing
        
        # Consistent spacing unit for all gaps (between elements and separators)
        spacing_unit = spacing // 2  # 5 pixels
        separator_thickness = 1  # 1 pixel line thickness
        
        def draw_pieces_in_rows(pieces: List[int], y_start: int, color: str, fixed_height: int) -> int:
            """Draw pieces in rows with smart layout.
            
            Args:
                pieces: List of piece types to draw
                y_start: Starting Y position
                color: 'w' or 'b' for piece color
                fixed_height: Fixed height to reserve for this side (2 rows)
            
            Returns:
                Total height used (always fixed_height to maintain consistent layout)
            """
            # Count pieces by type
            piece_counts = Counter(pieces)
            
            # Fixed piece order: First row: P, B, N | Second row: R, Q (King excluded - game ends when king is taken)
            first_row_order = [chess.PAWN, chess.BISHOP, chess.KNIGHT]
            second_row_order = [chess.ROOK, chess.QUEEN]
            
            # Set font and color
            painter.setFont(font)
            if color == 'b':
                painter.setPen(self.white_text_color)  # White text for black pieces
            else:
                painter.setPen(self.black_text_color)  # Black text for white pieces
            
            current_y = y_start
            current_x = text_area_x
            
            # First row: P, B, N (always show, even if count is 0)
            for piece_type in first_row_order:
                count = piece_counts.get(piece_type, 0)
                piece_letter = self.PIECE_LETTERS.get(piece_type, '?')
                # Show only letter and colon if count is 0, otherwise show count
                piece_text = f"{piece_letter}:" if count == 0 else f"{piece_letter}:{count}"
                # Calculate width as if "0" was always there to keep letters aligned
                text_width_with_zero = fm.horizontalAdvance(f"{piece_letter}:0")
                
                text_rect = QRect(current_x, current_y, text_width_with_zero, line_height)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, piece_text)
                current_x += text_width_with_zero + text_spacing
            
            # Second row: R, Q (always show, even if count is 0)
            current_x = text_area_x
            current_y += line_height + text_spacing
            
            for piece_type in second_row_order:
                count = piece_counts.get(piece_type, 0)
                piece_letter = self.PIECE_LETTERS.get(piece_type, '?')
                # Show only letter and colon if count is 0, otherwise show count
                piece_text = f"{piece_letter}:" if count == 0 else f"{piece_letter}:{count}"
                # Calculate width as if "0" was always there to keep letters aligned
                text_width_with_zero = fm.horizontalAdvance(f"{piece_letter}:0")
                
                text_rect = QRect(current_x, current_y, text_width_with_zero, line_height)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, piece_text)
                current_x += text_width_with_zero + text_spacing
            
            # Always return fixed_height to reserve consistent space (2 rows)
            return fixed_height
        
        # Calculate positions sequentially with consistent spacing
        # White pieces
        white_y = text_area_y
        white_bottom = white_y + fixed_side_height
        
        # First separator (between white and black)
        separator1_y = white_bottom + spacing_unit
        
        # Black pieces
        black_y = separator1_y + separator_thickness + spacing_unit
        black_bottom = black_y + fixed_side_height
        
        # Second separator (between black and score)
        separator2_y = black_bottom + spacing_unit
        
        # Material score
        score_font = QFont(self.font_family, self.font_size)
        painter.setFont(score_font)
        score_fm = QFontMetrics(score_font)
        score_line_height = score_fm.height()
        diff_y = separator2_y + separator_thickness + spacing_unit
        
        # Draw White captured pieces (black pieces captured by white)
        white_pieces_height = draw_pieces_in_rows(self._captured_by_white, white_y, 'b', fixed_side_height)
        
        # Draw first separator line between white and black sections
        painter.setPen(self.separator_color)
        painter.drawLine(text_area_x, separator1_y, text_area_x + text_area_width, separator1_y)
        
        # Draw Black captured pieces (white pieces captured by black)
        black_pieces_height = draw_pieces_in_rows(self._captured_by_black, black_y, 'w', fixed_side_height)
        
        # Draw second separator line between black pieces and material score
        painter.setPen(self.separator_color)
        painter.drawLine(text_area_x, separator2_y, text_area_x + text_area_width, separator2_y)
        
        # Draw material difference score
        painter.setFont(score_font)
        material_diff = self._calculate_material_difference()
        
        if abs(material_diff) < 0.01:  # Essentially equal
            diff_text = "Δ: 0.0"
        elif material_diff > 0:
            diff_text = f"Δ: +{material_diff:.1f}"
        else:
            diff_text = f"Δ: {material_diff:.1f}"
        
        painter.setPen(self.difference_text_color)
        painter.drawText(QRect(text_area_x, diff_y, text_area_width, score_line_height), 
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, diff_text)


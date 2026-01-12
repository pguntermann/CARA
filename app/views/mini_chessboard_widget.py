"""Mini chessboard widget for displaying positions in popups."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPolygonF
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from pathlib import Path
import chess
import sys
from typing import Dict, Any, Optional, List
from app.services.logging_service import LoggingService


class MiniChessBoardWidget(QWidget):
    """Mini chessboard widget displaying only pieces (no arrows, coordinates, etc.)."""
    
    def __init__(self, config: Dict[str, Any], fen: str, is_flipped: bool = False, scale_factor: float = 1.0) -> None:
        """Initialize the mini chessboard widget.
        
        Args:
            config: Configuration dictionary.
            fen: FEN string representing the position to display.
            is_flipped: Whether the board should be displayed flipped (matching main board).
            scale_factor: Scale factor for board size (1.0 = default, 1.25 = 1.25x, etc.).
        """
        super().__init__()
        self.config = config
        self._fen = fen
        self._is_flipped = is_flipped
        self._move_to_show: Optional[chess.Move] = None
        self._show_arrow = False
        self._scale_factor = scale_factor
        self._load_config()
        self._setup_board()
        self._load_position_from_fen(fen)
        
        # Set widget flags for popup behavior
        # Use ToolTip instead of Popup to prevent it from being destroyed when parent is hidden
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # Don't auto-delete
    
    def _load_config(self) -> None:
        """Load configuration for the mini chessboard."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('main', {})
        board_config = panel_config.get('board', {})
        
        # Square colors
        squares_config = board_config.get('squares', {})
        self.light_square_color = squares_config.get('light_color', [240, 217, 181])
        self.dark_square_color = squares_config.get('dark_color', [181, 136, 99])
        
        # Pieces
        pieces_config = board_config.get('pieces', {})
        self.svg_path = pieces_config.get('svg_path', 'app/resources/chesspieces/default')
        
        # Border
        border_config = board_config.get('border', {})
        self.border_size = border_config.get('size', 2)
        self.border_color = border_config.get('color', [60, 60, 65])
        
        # Get mini-board specific config
        manual_analysis_config = ui_config.get('panels', {}).get('detail', {}).get('manual_analysis', {})
        pv_hover_config = manual_analysis_config.get('pv_hover', {})
        mini_board_config = pv_hover_config.get('mini_board', {})
        
        # Size (default 120x120) - apply scale factor
        base_size = mini_board_config.get('size', 120)
        self.board_size = base_size * self._scale_factor
        self.square_size = self.board_size / 8
        
        # Get best next move arrow color (same as main board)
        bestnextmove_arrow_config = board_config.get('bestnextmove_arrow', {})
        self.arrow_color = bestnextmove_arrow_config.get('color', [0, 0, 255])
        
        # Calculate widget size (board + border)
        widget_size = self.board_size + self.border_size * 2
        self.setFixedSize(int(widget_size), int(widget_size))
    
    def _setup_board(self) -> None:
        """Setup the board data structure."""
        self.square_count = 8
        self.board = [[None for _ in range(self.square_count)] for _ in range(self.square_count)]
        
        # Load piece renderers
        self._load_pieces()
    
    def _load_pieces(self) -> None:
        """Load chess piece SVG files from the configured path."""
        import sys
        
        # Resolve path relative to project root (same as main board)
        project_root = Path(__file__).parent.parent.parent
        pieces_dir = project_root / self.svg_path
        
        if not pieces_dir.exists():
            logging_service = LoggingService.get_instance()
            logging_service.warning(f"Chess pieces directory not found: {pieces_dir}")
            self.piece_renderers = {}
            return
        
        # Piece type mapping: (color, piece_type) -> filename
        piece_types = ['p', 'r', 'n', 'b', 'q', 'k']
        colors = ['w', 'b']
        
        self.piece_renderers = {}
        
        for color in colors:
            for piece_type in piece_types:
                filename = f"{color}{piece_type}.svg"
                file_path = pieces_dir / filename
                
                if file_path.exists():
                    renderer = QSvgRenderer(str(file_path))
                    if renderer.isValid():
                        self.piece_renderers[(color, piece_type)] = renderer
                    else:
                        logging_service = LoggingService.get_instance()
                        logging_service.warning(f"Invalid SVG file: {file_path}")
    
    def _load_position_from_fen(self, fen: str) -> None:
        """Load board position from FEN string.
        
        Args:
            fen: FEN string representing the position.
        """
        # Clear the board
        self.board = [[None for _ in range(self.square_count)] for _ in range(self.square_count)]
        
        try:
            board = chess.Board(fen)
            pieces = board.piece_map()
            
            for square, piece in pieces.items():
                file = chess.square_file(square)
                rank = chess.square_rank(square)
                
                # Convert to our row/col system
                # python-chess rank: 0=rank1, 7=rank8 (bottom to top)
                # Our system: row 0=rank8, row 7=rank1 (top to bottom)
                
                if self._is_flipped:
                    # When flipped, mirror both file and rank
                    mirrored_file = 7 - file
                    mirrored_rank = 7 - rank
                    row = 7 - mirrored_rank
                    col = mirrored_file
                else:
                    row = 7 - rank
                    col = file
                
                # Convert piece to our format
                color = 'w' if piece.color == chess.WHITE else 'b'
                piece_type_map = {
                    chess.PAWN: 'p',
                    chess.ROOK: 'r',
                    chess.KNIGHT: 'n',
                    chess.BISHOP: 'b',
                    chess.QUEEN: 'q',
                    chess.KING: 'k'
                }
                piece_type = piece_type_map.get(piece.piece_type, 'p')
                
                self.board[row][col] = (color, piece_type)
        except Exception:
            # If FEN parsing fails, leave board empty
            pass
    
    def set_position(self, fen: str) -> None:
        """Update the position displayed on the mini board.
        
        Args:
            fen: FEN string representing the new position.
        """
        self._fen = fen
        self._load_position_from_fen(fen)
        self.update()
    
    def set_flipped(self, is_flipped: bool) -> None:
        """Set whether the board should be displayed flipped.
        
        Args:
            is_flipped: True if board should be flipped, False otherwise.
        """
        if self._is_flipped != is_flipped:
            self._is_flipped = is_flipped
            self._load_position_from_fen(self._fen)
            self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the mini chessboard."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate board start position (accounting for border)
        board_start_x = self.border_size
        board_start_y = self.border_size
        
        # Draw border
        if self.border_size > 0:
            border_rect = QRect(
                0, 0,
                int(self.board_size + self.border_size * 2),
                int(self.board_size + self.border_size * 2)
            )
            border_color = QColor(self.border_color[0], self.border_color[1], self.border_color[2])
            painter.fillRect(border_rect, QBrush(border_color))
        
        # Draw squares
        light_color = QColor(self.light_square_color[0], self.light_square_color[1], self.light_square_color[2])
        dark_color = QColor(self.dark_square_color[0], self.dark_square_color[1], self.dark_square_color[2])
        
        for row in range(self.square_count):
            for col in range(self.square_count):
                is_light = (row + col) % 2 == 0
                square_color = light_color if is_light else dark_color
                
                square_x = board_start_x + col * self.square_size
                square_y = board_start_y + row * self.square_size
                
                square_rect = QRect(int(square_x), int(square_y), int(self.square_size), int(self.square_size))
                painter.fillRect(square_rect, QBrush(square_color))
        
        # Draw pieces
        self._draw_pieces(painter, board_start_x, board_start_y)
        
        # Draw arrow if enabled and move is set
        if self._show_arrow and self._move_to_show is not None:
            self._draw_arrow(painter, self._move_to_show, self.arrow_color, board_start_x, board_start_y)
    
    def _draw_pieces(self, painter: QPainter, board_start_x: float, board_start_y: float) -> None:
        """Draw chess pieces on the board.
        
        Args:
            painter: QPainter instance.
            board_start_x: X position where the board squares start.
            board_start_y: Y position where the board squares start.
        """
        piece_padding = 0.1  # 10% padding on each side
        
        for row in range(self.square_count):
            for col in range(self.square_count):
                piece = self.board[row][col]
                if piece is None:
                    continue
                
                color, piece_type = piece
                renderer = self.piece_renderers.get((color, piece_type))
                if renderer is None:
                    continue
                
                # Calculate square position
                square_x = board_start_x + col * self.square_size
                square_y = board_start_y + row * self.square_size
                
                # Calculate piece size with padding
                piece_size = self.square_size * (1 - piece_padding * 2)
                
                # Calculate piece position (centered in square)
                piece_x = square_x + self.square_size * piece_padding
                piece_y = square_y + self.square_size * piece_padding
                
                # Draw piece
                piece_rect = QRectF(piece_x, piece_y, piece_size, piece_size)
                renderer.render(painter, piece_rect)
    
    def _draw_arrow(self, painter: QPainter, move: chess.Move, color: List[int], board_start_x: float, board_start_y: float) -> None:
        """Draw an arrow for a chess move.
        
        Args:
            painter: QPainter instance for drawing.
            move: Chess move to draw arrow for.
            color: RGB color list [r, g, b] for the arrow.
            board_start_x: X coordinate of the board's top-left corner.
            board_start_y: Y coordinate of the board's top-left corner.
        """
        if move is None:
            return
        
        # Get move squares
        from_square = move.from_square
        to_square = move.to_square
        
        # Convert square indices to file and rank
        from_file = chess.square_file(from_square)
        from_rank = chess.square_rank(from_square)
        to_file = chess.square_file(to_square)
        to_rank = chess.square_rank(to_square)
        
        # Adjust for flipped board
        if self._is_flipped:
            from_file = 7 - from_file
            from_rank = 7 - from_rank
            to_file = 7 - to_file
            to_rank = 7 - to_rank
        
        # CRITICAL: In python-chess, ranks are 0-based from bottom (0=rank1, 7=rank8)
        # But in our drawing system, row 0 is at the top (rank 8), row 7 is at the bottom (rank 1)
        # So we need to convert: visual_row = 7 - rank
        from_visual_rank = 7 - from_rank
        to_visual_rank = 7 - to_rank
        
        # Calculate square centers
        from_x = board_start_x + from_file * self.square_size + self.square_size / 2
        from_y = board_start_y + from_visual_rank * self.square_size + self.square_size / 2
        to_x = board_start_x + to_file * self.square_size + self.square_size / 2
        to_y = board_start_y + to_visual_rank * self.square_size + self.square_size / 2
        
        # Set up pen for arrow
        arrow_color = QColor(color[0], color[1], color[2])
        pen = QPen(arrow_color)
        pen.setWidth(2)  # Slightly thinner for mini-board
        painter.setPen(pen)
        painter.setBrush(QBrush(arrow_color))
        
        # Draw arrow line from source to destination
        # Shorten the line to leave space for arrowhead
        arrowhead_size = self.square_size * 0.15
        dx = to_x - from_x
        dy = to_y - from_y
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            # Normalize direction
            unit_x = dx / length
            unit_y = dy / length
            
            # Shorten line to make room for arrowhead
            shortened_to_x = to_x - unit_x * arrowhead_size
            shortened_to_y = to_y - unit_y * arrowhead_size
            
            # Draw line
            painter.drawLine(int(from_x), int(from_y), int(shortened_to_x), int(shortened_to_y))
            
            # Draw arrowhead (triangle pointing to destination)
            arrowhead_points = QPolygonF([
                QPointF(to_x, to_y),
                QPointF(
                    shortened_to_x - unit_y * arrowhead_size * 0.5,
                    shortened_to_y + unit_x * arrowhead_size * 0.5
                ),
                QPointF(
                    shortened_to_x + unit_y * arrowhead_size * 0.5,
                    shortened_to_y - unit_x * arrowhead_size * 0.5
                )
            ])
            painter.drawPolygon(arrowhead_points)
    
    def set_move(self, move: Optional[chess.Move], show_arrow: bool) -> None:
        """Set the move to display with an arrow.
        
        Args:
            move: Chess move to show arrow for, or None to hide arrow.
            show_arrow: Whether to show the arrow (if "Show best move arrow" is enabled).
        """
        self._move_to_show = move
        self._show_arrow = show_arrow
        self.update()


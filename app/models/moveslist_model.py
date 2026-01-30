"""Moves list model for holding move data."""

from PyQt6.QtCore import QAbstractTableModel, Qt
from PyQt6.QtGui import QColor, QBrush
from typing import Optional, List, Dict

from app.models.column_profile_model import (COL_NUM, COL_WHITE, COL_BLACK, COL_EVAL_WHITE, COL_EVAL_BLACK, COL_CPL_WHITE, COL_CPL_BLACK,
                                             COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3,
                                             COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2,
                                             COL_BEST_WHITE_3, COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3,
                                             COL_WHITE_DEPTH, COL_BLACK_DEPTH, COL_WHITE_SELDEPTH, COL_BLACK_SELDEPTH,
                                             COL_COMMENT, COL_ECO, COL_OPENING,
                                             COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL,
                                             COL_FEN_WHITE, COL_FEN_BLACK)


class MoveData:
    """Represents a single move's data."""
    
    def __init__(self,
                 move_number: int,
                 white_move: str = "",
                 black_move: str = "",
                 eval_white: str = "",
                 eval_black: str = "",
                 cpl_white: str = "",
                 cpl_black: str = "",
                 cpl_white_2: str = "",
                 cpl_white_3: str = "",
                 cpl_black_2: str = "",
                 cpl_black_3: str = "",
                 assess_white: str = "",
                 assess_black: str = "",
                 best_white: str = "",
                 best_black: str = "",
                 best_white_2: str = "",
                 best_white_3: str = "",
                 best_black_2: str = "",
                 best_black_3: str = "",
                 white_is_top3: bool = False,
                 black_is_top3: bool = False,
                 white_depth: int = 0,
                 black_depth: int = 0,
                 white_seldepth: int = 0,
                 black_seldepth: int = 0,
                 eco: str = "",
                 opening_name: str = "",
                 comment: str = "",
                 white_capture: str = "",
                 black_capture: str = "",
                 white_material: int = 0,
                 black_material: int = 0,
                 white_queens: int = 0,
                 white_rooks: int = 0,
                 white_bishops: int = 0,
                 white_knights: int = 0,
                 white_pawns: int = 0,
                 black_queens: int = 0,
                 black_rooks: int = 0,
                 black_bishops: int = 0,
                 black_knights: int = 0,
                 black_pawns: int = 0,
                 fen_white: str = "",
                 fen_black: str = "") -> None:
        """Initialize move data.
        
        Args:
            move_number: Move number (row index).
            white_move: White's move (e.g., "e4").
            black_move: Black's move (e.g., "e5").
            eval_white: Evaluation after white's move.
            eval_black: Evaluation after black's move.
            cpl_white: Centipawn loss for white's move.
            cpl_black: Centipawn loss for black's move.
            cpl_white_2: Centipawn loss for white's move compared to PV2.
            cpl_white_3: Centipawn loss for white's move compared to PV3.
            cpl_black_2: Centipawn loss for black's move compared to PV2.
            cpl_black_3: Centipawn loss for black's move compared to PV3.
            assess_white: Assessment of white's move (e.g., "good", "blunder").
            assess_black: Assessment of black's move.
            best_white: Best alternative move for white (PV1).
            best_black: Best alternative move for black (PV1).
            best_white_2: Second best move for white (PV2).
            best_white_3: Third best move for white (PV3).
            best_black_2: Second best move for black (PV2).
            best_black_3: Third best move for black (PV3).
            white_is_top3: True if white's played move is in top 3.
            black_is_top3: True if black's played move is in top 3.
            white_depth: Engine depth for white's move analysis.
            black_depth: Engine depth for black's move analysis.
            white_seldepth: Engine selective depth for white's move (0 if engine does not report).
            black_seldepth: Engine selective depth for black's move (0 if engine does not report).
            eco: ECO code for this position.
            opening_name: Opening name for this position.
            comment: Move comment.
            white_capture: Captured piece letter for white's move (p, r, n, b, q, or "").
            black_capture: Captured piece letter for black's move (p, r, n, b, q, or "").
            white_material: Material count in centipawns after white's move.
            black_material: Material count in centipawns after black's move.
            white_queens: Number of white queens after white's move.
            white_rooks: Number of white rooks after white's move.
            white_bishops: Number of white bishops after white's move.
            white_knights: Number of white knights after white's move.
            white_pawns: Number of white pawns after white's move.
            black_queens: Number of black queens after white's move.
            black_rooks: Number of black rooks after white's move.
            black_bishops: Number of black bishops after white's move.
            black_knights: Number of black knights after white's move.
            black_pawns: Number of black pawns after white's move.
            fen_white: FEN string after white's move.
            fen_black: FEN string after black's move.
        """
        self.move_number = move_number
        self.white_move = white_move
        self.black_move = black_move
        self.eval_white = eval_white
        self.eval_black = eval_black
        self.cpl_white = cpl_white
        self.cpl_black = cpl_black
        self.cpl_white_2 = cpl_white_2
        self.cpl_white_3 = cpl_white_3
        self.cpl_black_2 = cpl_black_2
        self.cpl_black_3 = cpl_black_3
        self.assess_white = assess_white
        self.assess_black = assess_black
        self.best_white = best_white
        self.best_black = best_black
        self.best_white_2 = best_white_2
        self.best_white_3 = best_white_3
        self.best_black_2 = best_black_2
        self.best_black_3 = best_black_3
        self.white_is_top3 = white_is_top3
        self.black_is_top3 = black_is_top3
        self.white_depth = white_depth
        self.black_depth = black_depth
        self.white_seldepth = white_seldepth
        self.black_seldepth = black_seldepth
        self.eco = eco
        self.opening_name = opening_name
        self.comment = comment
        self.white_capture = white_capture
        self.black_capture = black_capture
        self.white_material = white_material
        self.black_material = black_material
        self.white_queens = white_queens
        self.white_rooks = white_rooks
        self.white_bishops = white_bishops
        self.white_knights = white_knights
        self.white_pawns = white_pawns
        self.black_queens = black_queens
        self.black_rooks = black_rooks
        self.black_bishops = black_bishops
        self.black_knights = black_knights
        self.black_pawns = black_pawns
        self.fen_white = fen_white
        self.fen_black = fen_black


class MovesListModel(QAbstractTableModel):
    """Model representing moves list table data.
    
    This model holds the moves list state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Column indices
    COL_NUM = 0
    COL_WHITE = 1
    COL_BLACK = 2
    COL_EVAL_WHITE = 3
    COL_EVAL_BLACK = 4
    COL_CPL_WHITE = 5
    COL_CPL_BLACK = 6
    COL_CPL_WHITE_2 = 7
    COL_CPL_WHITE_3 = 8
    COL_CPL_BLACK_2 = 9
    COL_CPL_BLACK_3 = 10
    COL_ASSESS_WHITE = 11
    COL_ASSESS_BLACK = 12
    COL_BEST_WHITE = 13
    COL_BEST_BLACK = 14
    COL_BEST_WHITE_2 = 15
    COL_BEST_WHITE_3 = 16
    COL_BEST_BLACK_2 = 17
    COL_BEST_BLACK_3 = 18
    COL_WHITE_IS_TOP3 = 19
    COL_BLACK_IS_TOP3 = 20
    COL_WHITE_DEPTH = 21
    COL_BLACK_DEPTH = 22
    COL_WHITE_SELDEPTH = 32
    COL_BLACK_SELDEPTH = 33
    COL_ECO = 23
    COL_OPENING = 24
    COL_COMMENT = 25
    COL_WHITE_CAPTURE = 26
    COL_BLACK_CAPTURE = 27
    COL_WHITE_MATERIAL = 28
    COL_BLACK_MATERIAL = 29
    COL_FEN_WHITE = 30
    COL_FEN_BLACK = 31
    
    def __init__(self) -> None:
        """Initialize the moves list model."""
        super().__init__()
        self._moves: List[MoveData] = []
        self._active_move_ply: int = 0  # Ply index of active move (0 = starting position)
        self._highlight_color: Optional[QColor] = None  # Highlight color for active move
        self._column_visibility: Dict[int, bool] = {}  # Map column index to visibility
        # Initialize all columns as visible by default
        for col in range(self.columnCount()):
            self._column_visibility[col] = True
    
    def rowCount(self, parent=None) -> int:
        """Get number of rows in the model.
        
        Args:
            parent: Parent index (unused for table models).
            
        Returns:
            Number of rows.
        """
        return len(self._moves)
    
    def columnCount(self, parent=None) -> int:
        """Get number of columns in the model.
        
        Args:
            parent: Parent index (unused for table models).
            
        Returns:
            Total number of columns (always 32).
        """
        # Always return total columns - visibility is handled by view using hideSection/showSection
        return 34
    
    def set_highlight_color(self, color: Optional[QColor]) -> None:
        """Set the highlight color for active move.
        
        Args:
            color: QColor for highlighting, or None to disable.
        """
        self._highlight_color = color
    
    def set_active_move_ply(self, ply_index: int) -> None:
        """Set the active move ply index for highlighting.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        if self._active_move_ply != ply_index:
            # Emit data changed for affected rows
            old_row = (self._active_move_ply - 1) // 2 if self._active_move_ply > 0 else -1
            new_row = (ply_index - 1) // 2 if ply_index > 0 else -1
            
            self._active_move_ply = ply_index
            
            # Notify views that data changed for affected rows
            if old_row >= 0 and old_row < len(self._moves):
                top_left = self.index(old_row, 0)
                bottom_right = self.index(old_row, self.columnCount() - 1)  # All columns (0-31)
                self.dataChanged.emit(top_left, bottom_right)
            
            if new_row >= 0 and new_row < len(self._moves):
                top_left = self.index(new_row, 0)
                bottom_right = self.index(new_row, self.columnCount() - 1)  # All columns (0-31)
                self.dataChanged.emit(top_left, bottom_right)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Get data for a given index and role.
        
        Args:
            index: Model index (row, column). Column is the visible column index.
            role: Data role (DisplayRole, BackgroundRole, etc.).
            
        Returns:
            Data value or None.
        """
        if not index.isValid():
            return None
        
        row = index.row()
        logical_col = index.column()  # Column index is now directly the logical index
        
        if row < 0 or row >= len(self._moves):
            return None
        
        if logical_col < 0 or logical_col >= self.columnCount():
            return None
        
        # Handle BackgroundRole for active move highlighting
        if role == Qt.ItemDataRole.BackgroundRole:
            # Check if this row corresponds to the active move
            # ply_index = 1 -> row 0 (white move), ply_index = 2 -> row 0 (black move)
            # ply_index = 3 -> row 1 (white move), ply_index = 4 -> row 1 (black move)
            if self._active_move_ply > 0 and self._highlight_color is not None:
                active_row = (self._active_move_ply - 1) // 2
                if row == active_row:
                    # This row contains the active move - return highlight color
                    return QBrush(self._highlight_color)
            return None
        
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        
        move = self._moves[row]
        
        if logical_col == self.COL_NUM:
            return move.move_number
        elif logical_col == self.COL_WHITE:
            return move.white_move
        elif logical_col == self.COL_BLACK:
            return move.black_move
        elif logical_col == self.COL_EVAL_WHITE:
            return move.eval_white
        elif logical_col == self.COL_EVAL_BLACK:
            return move.eval_black
        elif logical_col == self.COL_CPL_WHITE:
            return move.cpl_white
        elif logical_col == self.COL_CPL_BLACK:
            return move.cpl_black
        elif logical_col == self.COL_CPL_WHITE_2:
            return move.cpl_white_2
        elif logical_col == self.COL_CPL_WHITE_3:
            return move.cpl_white_3
        elif logical_col == self.COL_CPL_BLACK_2:
            return move.cpl_black_2
        elif logical_col == self.COL_CPL_BLACK_3:
            return move.cpl_black_3
        elif logical_col == self.COL_ASSESS_WHITE:
            return move.assess_white
        elif logical_col == self.COL_ASSESS_BLACK:
            return move.assess_black
        elif logical_col == self.COL_BEST_WHITE:
            return move.best_white
        elif logical_col == self.COL_BEST_BLACK:
            return move.best_black
        elif logical_col == self.COL_BEST_WHITE_2:
            return move.best_white_2
        elif logical_col == self.COL_BEST_WHITE_3:
            return move.best_white_3
        elif logical_col == self.COL_BEST_BLACK_2:
            return move.best_black_2
        elif logical_col == self.COL_BEST_BLACK_3:
            return move.best_black_3
        elif logical_col == self.COL_WHITE_IS_TOP3:
            return "✓" if move.white_is_top3 else ""
        elif logical_col == self.COL_BLACK_IS_TOP3:
            return "✓" if move.black_is_top3 else ""
        elif logical_col == self.COL_WHITE_DEPTH:
            return str(move.white_depth) if move.white_depth > 0 else ""
        elif logical_col == self.COL_BLACK_DEPTH:
            return str(move.black_depth) if move.black_depth > 0 else ""
        elif logical_col == self.COL_WHITE_SELDEPTH:
            # If seldepth is missing or less than depth, show depth (engine may not report seldepth on every info line)
            effective = max(move.white_seldepth, move.white_depth)
            return str(effective) if effective > 0 else ""
        elif logical_col == self.COL_BLACK_SELDEPTH:
            effective = max(move.black_seldepth, move.black_depth)
            return str(effective) if effective > 0 else ""
        elif logical_col == self.COL_ECO:
            return move.eco
        elif logical_col == self.COL_OPENING:
            return move.opening_name
        elif logical_col == self.COL_COMMENT:
            # Return raw comment text (presentation formatting handled by view/delegate)
            return move.comment
        elif logical_col == self.COL_WHITE_CAPTURE:
            return move.white_capture
        elif logical_col == self.COL_BLACK_CAPTURE:
            return move.black_capture
        elif logical_col == self.COL_WHITE_MATERIAL:
            # Always return material value (even if 0, which is valid if all pieces are captured)
            return str(move.white_material)
        elif logical_col == self.COL_BLACK_MATERIAL:
            # Always return material value (even if 0, which is valid if all pieces are captured)
            return str(move.black_material)
        elif logical_col == self.COL_FEN_WHITE:
            return move.fen_white
        elif logical_col == self.COL_FEN_BLACK:
            return move.fen_black
        
        return None
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Get header data for a column or row.
        
        Args:
            section: Section index (visible column index for horizontal).
            orientation: Qt.Orientation.Horizontal or Qt.Orientation.Vertical.
            role: Data role.
            
        Returns:
            Header text or None.
        """
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        
        if orientation == Qt.Orientation.Horizontal:
            # Section is now directly the logical column index
            logical_col = section
            if logical_col < 0 or logical_col >= self.columnCount():
                return None
            
            headers = ["#", "White", "Black", "Eval White", "Eval Black",
                      "CPL White", "CPL Black", "CPL White 2", "CPL White 3",
                      "CPL Black 2", "CPL Black 3", "Assess White", "Assess Black",
                      "Best White", "Best Black", "Best White 2", "Best White 3",
                      "Best Black 2", "Best Black 3", "White Is Top 3", "Black Is Top 3",
                      "White Depth", "Black Depth", "Eco", "Opening Name", "Comment",
                      "White Capture", "Black Capture", "White Material", "Black Material",
                      "FEN White", "FEN Black", "White SelDepth", "Black SelDepth"]
            if 0 <= logical_col < len(headers):
                return headers[logical_col]
        
        return None
    
    def add_move(self, move: MoveData) -> None:
        """Add a move to the model.
        
        Args:
            move: MoveData instance to add.
        """
        # Insert the new row
        self.beginInsertRows(self.index(len(self._moves), 0).parent(), len(self._moves), len(self._moves))
        self._moves.append(move)
        self.endInsertRows()
    
    def clear(self) -> None:
        """Clear all moves from the model."""
        if len(self._moves) > 0:
            self.beginRemoveRows(self.index(0, 0).parent(), 0, len(self._moves) - 1)
            self._moves.clear()
            self.endRemoveRows()
    
    def get_move(self, row: int) -> Optional[MoveData]:
        """Get move data at a specific row.
        
        Args:
            row: Row index.
            
        Returns:
            MoveData instance or None if row is invalid.
        """
        if 0 <= row < len(self._moves):
            return self._moves[row]
        return None
    
    def get_all_moves(self) -> List[MoveData]:
        """Get all moves in the model.
        
        Returns:
            List of MoveData instances.
        """
        return self._moves.copy()
    
    def set_column_visibility(self, column_visibility: Dict[str, bool]) -> None:
        """Set column visibility based on column names.
        
        Note: This method only tracks visibility state. Actual hiding/showing
        is handled by the view using header.hideSection()/showSection().
        
        Args:
            column_visibility: Dictionary mapping column names to visibility (True/False).
                              Column names: "col_num", "col_white", "col_black", etc.
        """
        # Map column names to indices
        name_to_index = {
            COL_NUM: self.COL_NUM,
            COL_WHITE: self.COL_WHITE,
            COL_BLACK: self.COL_BLACK,
            COL_EVAL_WHITE: self.COL_EVAL_WHITE,
            COL_EVAL_BLACK: self.COL_EVAL_BLACK,
            COL_CPL_WHITE: self.COL_CPL_WHITE,
            COL_CPL_BLACK: self.COL_CPL_BLACK,
            COL_CPL_WHITE_2: self.COL_CPL_WHITE_2,
            COL_CPL_WHITE_3: self.COL_CPL_WHITE_3,
            COL_CPL_BLACK_2: self.COL_CPL_BLACK_2,
            COL_CPL_BLACK_3: self.COL_CPL_BLACK_3,
            COL_ASSESS_WHITE: self.COL_ASSESS_WHITE,
            COL_ASSESS_BLACK: self.COL_ASSESS_BLACK,
            COL_BEST_WHITE: self.COL_BEST_WHITE,
            COL_BEST_BLACK: self.COL_BEST_BLACK,
            COL_BEST_WHITE_2: self.COL_BEST_WHITE_2,
            COL_BEST_WHITE_3: self.COL_BEST_WHITE_3,
            COL_BEST_BLACK_2: self.COL_BEST_BLACK_2,
            COL_BEST_BLACK_3: self.COL_BEST_BLACK_3,
            COL_WHITE_IS_TOP3: self.COL_WHITE_IS_TOP3,
            COL_BLACK_IS_TOP3: self.COL_BLACK_IS_TOP3,
            COL_WHITE_DEPTH: self.COL_WHITE_DEPTH,
            COL_BLACK_DEPTH: self.COL_BLACK_DEPTH,
            COL_WHITE_SELDEPTH: self.COL_WHITE_SELDEPTH,
            COL_BLACK_SELDEPTH: self.COL_BLACK_SELDEPTH,
            COL_ECO: self.COL_ECO,
            COL_OPENING: self.COL_OPENING,
            COL_COMMENT: self.COL_COMMENT,
            COL_WHITE_CAPTURE: self.COL_WHITE_CAPTURE,
            COL_BLACK_CAPTURE: self.COL_BLACK_CAPTURE,
            COL_WHITE_MATERIAL: self.COL_WHITE_MATERIAL,
            COL_BLACK_MATERIAL: self.COL_BLACK_MATERIAL,
            COL_FEN_WHITE: self.COL_FEN_WHITE,
            COL_FEN_BLACK: self.COL_FEN_BLACK,
        }
        
        # Update visibility tracking (for internal state only)
        for col_name, visible in column_visibility.items():
            if col_name in name_to_index:
                col_index = name_to_index[col_name]
                self._column_visibility[col_index] = visible
    
    def get_column_index_mapping(self) -> Dict[int, int]:
        """Get mapping from logical column index to logical column index.
        
        Returns:
            Dictionary mapping logical column index to itself (1:1 mapping since all columns exist).
            This is kept for backward compatibility but now all columns are always in the model.
        """
        # All columns are always in the model, so mapping is 1:1
        return {i: i for i in range(14)}
    
    def clear_analysis_data(self) -> None:
        """Clear all analysis data from moves (evaluations, CPL, assessments, best moves).
        
        This method clears the following fields for all moves:
        - eval_white, eval_black
        - cpl_white, cpl_black
        - assess_white, assess_black
        - best_white, best_black
        """
        changed = False
        for move in self._moves:
            if (move.eval_white or move.eval_black or move.cpl_white or move.cpl_black or
                move.assess_white or move.assess_black or move.best_white or move.best_black or
                move.white_depth or move.black_depth or move.white_seldepth or move.black_seldepth):
                move.eval_white = ""
                move.eval_black = ""
                move.cpl_white = ""
                move.cpl_black = ""
                move.assess_white = ""
                move.assess_black = ""
                move.best_white = ""
                move.best_black = ""
                move.white_depth = 0
                move.black_depth = 0
                move.white_seldepth = 0
                move.black_seldepth = 0
                changed = True
        
        if changed:
            # Emit dataChanged for all rows and all columns
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._moves) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)


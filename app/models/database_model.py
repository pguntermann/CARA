"""Database model for holding game data."""

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor
from typing import Optional, List, Dict, Any, Set, Tuple
from datetime import datetime
from collections import Counter


class GameData:
    """Represents a single game's data."""
    
    def __init__(self, 
                 game_number: int,
                 white: str = "",
                 black: str = "",
                 result: str = "",
                 date: str = "",
                 moves: int = 0,
                 eco: str = "",
                 pgn: str = "",
                 event: str = "",
                 site: str = "",
                 white_elo: str = "",
                 black_elo: str = "",
                 analyzed: bool = False,
                 annotated: bool = False,
                 source_database: str = "") -> None:
        """Initialize game data.
        
        Args:
            game_number: Game number/row index.
            white: White player name.
            black: Black player name.
            result: Game result (e.g., "1-0", "0-1", "1/2-1/2").
            date: Game date.
            moves: Number of moves.
            eco: ECO code (opening classification).
            pgn: Full PGN text.
            event: Event name (PGN tag [Event]).
            site: Site name (PGN tag [Site]).
            white_elo: White player Elo rating (PGN tag [WhiteElo]).
            black_elo: Black player Elo rating (PGN tag [BlackElo]).
                analyzed: Whether the game has been analyzed (has CARAAnalysisData tag).
                annotated: Whether the game has saved annotations (has CARAAnnotations tag).
            source_database: Name of the database this game came from (for search results).
        """
        self.game_number = game_number
        self.white = white
        self.black = black
        self.result = result
        self.date = date
        self.moves = moves
        self.eco = eco
        self.pgn = pgn
        self.event = event
        self.site = site
        self.white_elo = white_elo
        self.black_elo = black_elo
        self.analyzed = analyzed
        self.annotated = annotated
        self.source_database = source_database


class DatabaseModel(QAbstractTableModel):
    """Model representing database table data for games.
    
    This model holds the database state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Column indices
    COL_NUM = 0
    COL_UNSAVED = 1
    COL_WHITE = 2
    COL_BLACK = 3
    COL_WHITE_ELO = 4
    COL_BLACK_ELO = 5
    COL_RESULT = 6
    COL_DATE = 7
    COL_EVENT = 8
    COL_SITE = 9
    COL_MOVES = 10
    COL_ECO = 11
    COL_ANALYZED = 12
    COL_ANNOTATED = 13
    COL_SOURCE_DB = 14
    COL_PGN = 15
    
    def __init__(self) -> None:
        """Initialize the database model."""
        super().__init__()
        self._games: List[GameData] = []
        self._unsaved_games: Set[GameData] = set()  # Track games with unsaved changes
        self._unsaved_icon: Optional[QIcon] = None  # Cached icon for unsaved indicator
    
    def rowCount(self, parent=None) -> int:
        """Get number of rows in the model.
        
        Args:
            parent: Parent index (unused for table models).
            
        Returns:
            Number of rows.
        """
        return len(self._games)
    
    def columnCount(self, parent=None) -> int:
        """Get number of columns in the model.
        
        Args:
            parent: Parent index (unused for table models).
            
        Returns:
            Number of columns (16: #, ●, White, Black, WhiteElo, BlackElo, Result, Date, Event, Site, Moves, ECO, Analyzed, Annotated, Source DB, PGN).
        """
        return 16
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Get data for a given index and role.
        
        Args:
            index: Model index (row, column).
            role: Data role (DisplayRole, DecorationRole, etc.).
            
        Returns:
            Data value or None.
        """
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row < 0 or row >= len(self._games):
            return None
        
        game = self._games[row]
        
        # Handle unsaved column with DecorationRole for icon (second column)
        if col == self.COL_UNSAVED:
            if role == Qt.ItemDataRole.DecorationRole:
                # Return icon if game has unsaved changes, None otherwise
                if game in self._unsaved_games:
                    if self._unsaved_icon is None:
                        self._unsaved_icon = self._create_unsaved_icon()
                    return self._unsaved_icon
                return None
            elif role == Qt.ItemDataRole.DisplayRole:
                # Return empty string for text display
                return ""
            elif role == Qt.ItemDataRole.TextAlignmentRole:
                # Center align the icon
                return Qt.AlignmentFlag.AlignCenter
            return None
        
        # For other columns, only handle DisplayRole
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        
        if col == self.COL_NUM:
            return game.game_number
        elif col == self.COL_WHITE:
            return game.white
        elif col == self.COL_BLACK:
            return game.black
        elif col == self.COL_WHITE_ELO:
            return game.white_elo
        elif col == self.COL_BLACK_ELO:
            return game.black_elo
        elif col == self.COL_RESULT:
            return game.result
        elif col == self.COL_DATE:
            return game.date
        elif col == self.COL_EVENT:
            return game.event
        elif col == self.COL_SITE:
            return game.site
        elif col == self.COL_MOVES:
            return game.moves
        elif col == self.COL_ECO:
            return game.eco
        elif col == self.COL_ANALYZED:
            return "✓" if game.analyzed else ""
        elif col == self.COL_ANNOTATED:
            return "✓" if getattr(game, "annotated", False) else ""
        elif col == self.COL_SOURCE_DB:
            return game.source_database
        elif col == self.COL_PGN:
            # Return raw PGN text (presentation formatting handled by view/delegate)
            return game.pgn
        
        return None
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Get header data for a column or row.
        
        Args:
            section: Section index (column or row).
            orientation: Qt.Orientation.Horizontal or Qt.Orientation.Vertical.
            role: Data role.
            
        Returns:
            Header text or None.
        """
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        
        if orientation == Qt.Orientation.Horizontal:
            headers = ["#", "●", "White", "Black", "WhiteElo", "BlackElo", "Result", "Date", "Event", "Site", "Moves", "ECO", "Analyzed", "Annotated", "Source DB", "PGN"]
            if 0 <= section < len(headers):
                return headers[section]
        
        return None
    
    def add_game(self, game: GameData, mark_unsaved: bool = True) -> None:
        """Add a game to the model.
        
        Args:
            game: GameData instance to add.
            mark_unsaved: If True, mark the game as having unsaved changes.
                         Set to False when loading games from a file (they're already saved).
                         Default is True for newly added games (import, paste, etc.).
        """
        # Set game number based on current row count
        game.game_number = len(self._games) + 1
        
        # Insert the new row
        row = len(self._games)
        self.beginInsertRows(self.index(row, 0).parent(), row, row)
        self._games.append(game)
        # Mark game as having unsaved changes if requested (newly added games are unsaved by default)
        if mark_unsaved:
            self._unsaved_games.add(game)
        self.endInsertRows()
        
        # Emit dataChanged for the unsaved column to ensure the indicator is displayed
        # This is needed because endInsertRows() may not trigger a refresh of the DecorationRole
        # Only emit if we marked it as unsaved (otherwise no indicator needed)
        if mark_unsaved:
            parent = QModelIndex()
            unsaved_index = self.index(row, self.COL_UNSAVED, parent)
            self.dataChanged.emit(unsaved_index, unsaved_index,
                                 [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
    
    def clear(self) -> None:
        """Clear all games from the model."""
        if len(self._games) > 0:
            self.beginRemoveRows(self.index(0, 0).parent(), 0, len(self._games) - 1)
            self._games.clear()
            self._unsaved_games.clear()
            self.endRemoveRows()
    
    def remove_games(self, games_to_remove: List['GameData']) -> None:
        """Remove multiple games from the model.
        
        Args:
            games_to_remove: List of GameData instances to remove.
        """
        if not games_to_remove:
            return
        
        # Find row indices for games to remove
        rows_to_remove = []
        for game in games_to_remove:
            row = self.find_game(game)
            if row is not None:
                rows_to_remove.append(row)
        
        if not rows_to_remove:
            return
        
        # Remove duplicates and sort in descending order
        rows_to_remove = sorted(set(rows_to_remove), reverse=True)
        
        # Remove games from list and unsaved set (from highest to lowest index)
        # This avoids index shifting issues
        parent = self.index(0, 0).parent()
        for row in rows_to_remove:
            if 0 <= row < len(self._games):
                game = self._games[row]
                self._unsaved_games.discard(game)
                # Emit signal for this single row removal
                self.beginRemoveRows(parent, row, row)
                self._games.pop(row)
                self.endRemoveRows()
    
    def sort_games_to_top(self, games_to_top: List['GameData']) -> None:
        """Sort games to bring specified games to the top.
        
        Args:
            games_to_top: List of GameData instances to move to the top.
        """
        if not games_to_top:
            return
        
        # Create a set for fast lookup
        games_set = set(games_to_top)
        
        # Notify views that layout is about to change
        self.layoutAboutToBeChanged.emit()
        
        # Store persistent indexes
        old_persistent_indexes = self.persistentIndexList()
        persistent_games = []
        for old_index in old_persistent_indexes:
            if old_index.isValid() and old_index.row() < len(self._games):
                persistent_games.append((old_index, self._games[old_index.row()]))
            else:
                persistent_games.append((old_index, None))
        
        # Separate games into highlighted and others
        highlighted = []
        others = []
        for game in self._games:
            if game in games_set:
                highlighted.append(game)
            else:
                others.append(game)
        
        # Reorder: highlighted games first, then others
        self._games = highlighted + others
        
        # Update game numbers
        for i, game in enumerate(self._games):
            game.game_number = i + 1
        
        # Map old persistent indexes to new positions
        new_persistent_indexes = []
        for old_index, game in persistent_games:
            if game is not None:
                new_row = self.find_game(game)
                if new_row is not None:
                    new_index = self.index(new_row, old_index.column())
                    new_persistent_indexes.append(new_index)
                else:
                    new_persistent_indexes.append(QModelIndex())
            else:
                new_persistent_indexes.append(QModelIndex())
        
        # Update persistent indexes
        self.changePersistentIndexList(old_persistent_indexes, new_persistent_indexes)
        
        # Notify views that layout has changed
        self.layoutChanged.emit()
    
    def get_game(self, row: int) -> Optional[GameData]:
        """Get game data at a specific row.
        
        Args:
            row: Row index.
            
        Returns:
            GameData instance or None if row is invalid.
        """
        if 0 <= row < len(self._games):
            return self._games[row]
        return None
    
    def get_all_games(self) -> List[GameData]:
        """Get all games in the model.
        
        Returns:
            List of GameData instances.
        """
        return self._games.copy()
    
    def get_unique_players(self) -> List[Tuple[str, int]]:
        """Get unique player names with game counts.
        
        Returns:
            List of (player_name, game_count) tuples, sorted by game count (descending).
        """
        player_counts: Dict[str, int] = {}
        
        for game in self._games:
            # Count white player
            if game.white and game.white.strip():
                player_counts[game.white] = player_counts.get(game.white, 0) + 1
            
            # Count black player
            if game.black and game.black.strip():
                player_counts[game.black] = player_counts.get(game.black, 0) + 1
        
        # Sort by game count (descending), then by name (ascending) for ties
        sorted_players = sorted(player_counts.items(), key=lambda x: (-x[1], x[0]))
        
        return sorted_players
    
    def find_game(self, game: 'GameData') -> Optional[int]:
        """Find the row index of a game in the model.
        
        Args:
            game: GameData instance to find.
            
        Returns:
            Row index if found, None otherwise.
        """
        try:
            return self._games.index(game)
        except ValueError:
            return None
    
    def update_game(self, game: 'GameData') -> bool:
        """Update a game in the model and notify views.
        
        This method finds the game, updates it, and emits dataChanged
        signal for all columns to refresh the table view. Automatically
        marks the game as having unsaved changes.
        
        Args:
            game: GameData instance to update (must already be in the model).
            
        Returns:
            True if game was found and updated, False otherwise.
        """
        row = self.find_game(game)
        if row is None:
            return False
        
        # Auto-mark game as having unsaved changes
        self._unsaved_games.add(game)
        
        # Emit dataChanged for all columns of this row
        # For table models, parent should be QModelIndex() (invalid index)
        # Use same pattern as beginInsertRows/beginRemoveRows
        parent = QModelIndex()
        left_index = self.index(row, 0, parent)
        right_index = self.index(row, self.columnCount(parent) - 1, parent)
        # Emit with DisplayRole and DecorationRole to refresh the view
        # DecorationRole is needed for the unsaved column icon
        # Note: We need to emit with roles parameter to ensure Qt processes the signal correctly
        self.dataChanged.emit(left_index, right_index, 
                             [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
        
        return True
    
    def batch_update_games(self, games: List['GameData']) -> None:
        """Batch update multiple games and emit a single dataChanged signal.
        
        This is more efficient than calling update_game() multiple times,
        as it emits a single signal for all affected rows instead of one per game.
        
        Args:
            games: List of GameData instances to update (must already be in the model).
        """
        if not games:
            return
        
        # Mark all games as having unsaved changes
        for game in games:
            self._unsaved_games.add(game)
        
        # Find all row indices for the updated games
        rows = []
        for game in games:
            row = self.find_game(game)
            if row is not None:
                rows.append(row)
        
        if not rows:
            return
        
        # Sort rows to get the range
        rows.sort()
        min_row = rows[0]
        max_row = rows[-1]
        
        # Emit a single dataChanged signal for the entire range
        parent = QModelIndex()
        left_index = self.index(min_row, 0, parent)
        right_index = self.index(max_row, self.columnCount(parent) - 1, parent)
        self.dataChanged.emit(left_index, right_index,
                             [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
    
    def _create_unsaved_icon(self) -> QIcon:
        """Create icon for unsaved changes indicator.
        
        Returns:
            QIcon with a small circle centered in a wider transparent pixmap.
        """
        # Column width is 25px, create pixmap to match
        # This allows transparent space on left to push icon toward center
        column_width = 25
        circle_size = 8
        pixmap = QPixmap(column_width, circle_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Use orange/yellow color for visibility (same as tab indicator)
        circle_color = QColor(255, 200, 100)
        
        # Draw circle positioned more to the right in the pixmap
        # Add extra padding on left to push visible circle toward center of column
        # Position circle at ~60% of column width to visually center it
        x_offset = int(column_width * 0.6) - circle_size // 2
        margin = 1
        circle_rect = QRect(x_offset + margin, margin, circle_size - 2 * margin, circle_size - 2 * margin)
        painter.setBrush(QBrush(circle_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle_rect)
        
        painter.end()
        return QIcon(pixmap)
    
    def clear_all_unsaved(self) -> None:
        """Clear all unsaved change indicators.
        
        This should be called after saving or reloading the database.
        """
        if not self._unsaved_games:
            return
        
        # Get all affected rows before clearing
        affected_rows = []
        for game in self._unsaved_games:
            row = self.find_game(game)
            if row is not None:
                affected_rows.append(row)
        
        # Clear the set
        self._unsaved_games.clear()
        
        if not affected_rows:
            return
        
        # Emit a single batch dataChanged signal for all affected rows
        # This is more efficient than emitting individual signals for each row
        # Include both DisplayRole and DecorationRole since we return icon with DecorationRole
        parent = QModelIndex()
        if affected_rows:
            # Sort rows to get the range
            affected_rows.sort()
            min_row = affected_rows[0]
            max_row = affected_rows[-1]
            
            # Emit a single signal for the entire range
            left_index = self.index(min_row, self.COL_UNSAVED, parent)
            right_index = self.index(max_row, self.COL_UNSAVED, parent)
            self.dataChanged.emit(left_index, right_index, 
                                 [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
    
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sort the model by the specified column.
        
        Args:
            column: Column index to sort by.
            order: Sort order (AscendingOrder or DescendingOrder).
        """
        # Don't sort by unsaved column (icon column)
        if column == self.COL_UNSAVED:
            return
        
        # Define key extraction function for each column type
        def get_sort_key(game: GameData) -> Any:
            """Extract sort key value from a game for the current column.
            
            Returns:
                Sort key value appropriate for the column type.
            """
            if column == self.COL_NUM:
                return game.game_number
            elif column == self.COL_WHITE:
                return game.white or ""
            elif column == self.COL_BLACK:
                return game.black or ""
            elif column == self.COL_WHITE_ELO:
                # Parse as integer, treat empty as 0
                try:
                    return int(game.white_elo) if game.white_elo else 0
                except (ValueError, TypeError):
                    return 0
            elif column == self.COL_BLACK_ELO:
                # Parse as integer, treat empty as 0
                try:
                    return int(game.black_elo) if game.black_elo else 0
                except (ValueError, TypeError):
                    return 0
            elif column == self.COL_RESULT:
                return game.result or ""
            elif column == self.COL_DATE:
                # Parse dates for proper chronological sorting
                return self._parse_date_for_sort(game.date)
            elif column == self.COL_EVENT:
                return game.event or ""
            elif column == self.COL_SITE:
                return game.site or ""
            elif column == self.COL_MOVES:
                return game.moves
            elif column == self.COL_ECO:
                return game.eco or ""
            elif column == self.COL_ANALYZED:
                # Sort by boolean: False (not analyzed) comes before True (analyzed)
                return game.analyzed
            elif column == self.COL_ANALYZED:
                return game.analyzed
            elif column == self.COL_ANNOTATED:
                return getattr(game, "annotated", False)
            elif column == self.COL_SOURCE_DB:
                return game.source_database or ""
            elif column == self.COL_PGN:
                return game.pgn or ""
            else:
                return None
        
        # Notify views that layout is about to change
        self.layoutAboutToBeChanged.emit()
        
        # Store persistent indexes and their associated games for selection preservation
        old_persistent_indexes = self.persistentIndexList()
        persistent_games = []
        for old_index in old_persistent_indexes:
            if old_index.isValid() and old_index.row() < len(self._games):
                persistent_games.append((old_index, self._games[old_index.row()]))
            else:
                persistent_games.append((old_index, None))
        
        # Sort the games list using key function
        # Use reverse=True for descending order
        reverse = (order == Qt.SortOrder.DescendingOrder)
        self._games.sort(key=get_sort_key, reverse=reverse)
        
        # Map old persistent indexes to new positions based on game objects
        new_persistent_indexes = []
        for old_index, game in persistent_games:
            if old_index.isValid() and game is not None:
                # Find the new row position of this game after sorting
                try:
                    new_row = self._games.index(game)
                    new_index = self.index(new_row, old_index.column(), old_index.parent())
                    new_persistent_indexes.append(new_index)
                except ValueError:
                    # Game not found (shouldn't happen, but handle gracefully)
                    new_persistent_indexes.append(QModelIndex())
            else:
                new_persistent_indexes.append(QModelIndex())
        
        # Update persistent indexes
        self.changePersistentIndexList(old_persistent_indexes, new_persistent_indexes)
        
        # Notify views that layout has changed
        self.layoutChanged.emit()
    
    def _parse_date_for_sort(self, date_str: str) -> tuple:
        """Parse a date string for sorting purposes.
        
        PGN dates can be in various formats:
        - "YYYY.MM.DD" (year.month.day - most common)
        - "DD.MM.YYYY" (day.month.year - European format)
        - "YYYY.DD.MM" (year.day.month - alternative format)
        - "YYYY.MM" (year and month)
        - "YYYY" (year only)
        - Empty string
        
        The method attempts to auto-detect the format by analyzing the values.
        
        Returns:
            Tuple (year, month, day) for comparison, with missing parts as 0.
            Empty dates return (0, 0, 0) to sort to the beginning.
        """
        if not date_str or not date_str.strip():
            return (0, 0, 0)
        
        # Remove whitespace
        date_str = date_str.strip()
        
        # Split by dots
        parts = date_str.split('.')
        
        try:
            # Parse all three parts as integers
            part1 = int(parts[0]) if len(parts) > 0 and parts[0] else 0
            part2 = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            part3 = int(parts[2]) if len(parts) > 2 and parts[2] else 0
            
            # Auto-detect format based on values
            # Strategy: identify which part is the year (typically > 31 or > 1900)
            # Then determine if it's YYYY.MM.DD, DD.MM.YYYY, or YYYY.DD.MM
            
            if len(parts) == 3:
                # Three-part date - try to detect format
                if part1 > 31 or part1 > 1900:
                    # First part is likely year (YYYY.MM.DD or YYYY.DD.MM)
                    if part2 <= 12 and part3 <= 31:
                        # YYYY.MM.DD format (most common): year.month.day
                        return (part1, part2, part3)
                    elif part2 <= 31 and part3 <= 12:
                        # YYYY.DD.MM format: year.day.month
                        return (part1, part3, part2)
                    elif part2 > 12 and part3 <= 12:
                        # part2 > 12 can't be month, so likely YYYY.DD.MM
                        return (part1, part3, part2)
                    else:
                        # Ambiguous - assume YYYY.MM.DD and use as-is
                        return (part1, part2, part3)
                elif part3 > 31 or part3 > 1900:
                    # Third part is likely year (DD.MM.YYYY format)
                    return (part3, part2, part1)
                else:
                    # Can't clearly identify - assume YYYY.MM.DD
                    return (part1, part2, part3)
            elif len(parts) == 2:
                # Two-part date - assume YYYY.MM
                if part1 > 31 or part1 > 1900:
                    return (part1, part2, 0)
                else:
                    # Could be MM.YYYY or DD.MM - assume MM.YYYY
                    return (part2, part1, 0)
            elif len(parts) == 1:
                # Single part - assume year
                return (part1, 0, 0)
            else:
                return (0, 0, 0)
        except (ValueError, IndexError):
            # If parsing fails, try to extract just the year
            try:
                year = int(date_str.split('.')[0]) if '.' in date_str else int(date_str)
                return (year, 0, 0)
            except (ValueError, TypeError):
                return (0, 0, 0)


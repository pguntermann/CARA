"""Database model for holding game data."""

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRect, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor
from typing import Optional, List, Dict, Any, Set, Tuple
from datetime import datetime
from collections import Counter

from app.utils.time_control_utils import get_tc_type


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
                 time_control: str = "",
                 game_tags_raw: str = "",
                 game_tags: str = "",
                 analyzed: bool = False,
                 annotated: bool = False,
                 has_notes: bool = False,
                 notes: Optional[str] = None,
                 source_database: str = "",
                 file_position: int = 0,
                 ref_ply: int = 0) -> None:
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
            time_control: Time control (PGN tag [TimeControl]).
            analyzed: Whether the game has been analyzed (has CARAAnalysisData tag).
            annotated: Whether the game has saved annotations (has CARAAnnotations tag).
            has_notes: Whether the game has a CARANotes tag.
            notes: Optional cached notes text (from CARANotes tag); None until loaded.
            source_database: Name of the database this game came from (for search results).
            file_position: Original position of game in file (1-based, 0 if not from file).
            ref_ply: Optional reference ply index used by search results to open a game
                at a specific move (e.g. a brilliant move). 0 means "no specific ply".
        """
        self.game_number = game_number
        self.white = white
        self.black = black
        self.result = result
        self.date = date
        self.moves = moves
        self.eco = eco
        # Backing storage for pgn property (auto-invalidates display cache when modified)
        self._pgn: str = pgn
        self.event = event
        self.site = site
        self.white_elo = white_elo
        self.black_elo = black_elo
        self.time_control = time_control
        # CARA per-game tags (stored in PGN header [CARAGameTags "..."])
        self.game_tags_raw = game_tags_raw
        self.game_tags = game_tags
        self.analyzed = analyzed
        self.annotated = annotated
        self.has_notes = has_notes
        self.notes = notes  # Cached notes from CARANotes tag; None until loaded
        self.source_database = source_database
        self.file_position = file_position
        self.ref_ply = ref_ply

    @property
    def pgn(self) -> str:
        """Full PGN text (source of truth for exports and detail views)."""
        return self._pgn

    @pgn.setter
    def pgn(self, value: str) -> None:
        """Set full PGN text and invalidate the database panel preview cache."""
        self._pgn = value
        # Database panel caches a truncated display preview in `data()` for COL_PGN.
        # If PGN changes (e.g. tag edits, bulk tag operations), we must invalidate it.
        self._pgn_preview = None


class DatabaseModel(QAbstractTableModel):
    """Model representing database table data for games.
    
    This model holds the database state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    #: Emitted when game rows or stored game content relevant to aggregates
    #: (e.g. player statistics) changes. Not emitted for sort/reorder or
    #: unsaved-indicator-only updates.
    stats_relevant_data_change = pyqtSignal()
    
    # Column indices
    COL_NUM = 0
    COL_FILE_NUM = 1
    COL_UNSAVED = 2
    COL_WHITE = 3
    COL_BLACK = 4
    COL_WHITE_ELO = 5
    COL_BLACK_ELO = 6
    COL_RESULT = 7
    COL_DATE = 8
    COL_EVENT = 9
    COL_SITE = 10
    COL_MOVES = 11
    COL_ECO = 12
    COL_TIMECONTROL = 13
    COL_TC_TYPE = 14
    COL_ANALYZED = 15
    COL_ANNOTATED = 16
    COL_NOTES = 17
    COL_SOURCE_DB = 18
    COL_REF_PLY = 19
    COL_TAGS = 20
    COL_PGN = 21
    
    def __init__(self, file_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the database model.
        
        Args:
            file_path: Optional file path for file-based databases. None for clipboard database.
            config: Optional config dict for TC Type mapping thresholds (e.g. tc_type under ui.panels.database).
        """
        super().__init__()
        self._games: List[GameData] = []
        self._unsaved_games: Set[GameData] = set()  # Track games with unsaved changes
        self._unsaved_icon: Optional[QIcon] = None  # Cached icon for unsaved indicator
        self._unique_tags: Set[str] = set()  # Cache of unique tag names found in games
        self.file_path: Optional[str] = file_path  # File path for file-based databases, None for clipboard
        self._config: Dict[str, Any] = config or {}
        # Maximum number of characters to show in the PGN column (preview only).
        # Full PGN remains available via game.pgn for exports and detail views.
        ui_cfg = (self._config.get("ui") or {})
        db_panel_cfg = ui_cfg.get("panels", {}).get("database", {})
        self._pgn_preview_max_len: int = db_panel_cfg.get("pgn_col_max_chars", 250)

        # Position indices (zobrist hash -> occurrences) for Position Search.
        # hash -> list[(id(game), ply)]
        self._position_index: Dict[int, List[Tuple[int, int]]] = {}
        # id(game) -> list[(hash, ply)]
        self._position_reverse: Dict[int, List[Tuple[int, int]]] = {}
        # Fuzzy (ignore castling + en-passant)
        self._position_index_fuzzy: Dict[int, List[Tuple[int, int]]] = {}
        self._position_reverse_fuzzy: Dict[int, List[Tuple[int, int]]] = {}

    def set_config(self, config: Dict[str, Any]) -> None:
        """Update config and refresh cached theme-driven assets."""
        self._config = config or {}
        ui_cfg = (self._config.get("ui") or {})
        db_panel_cfg = ui_cfg.get("panels", {}).get("database", {})
        self._pgn_preview_max_len = db_panel_cfg.get("pgn_col_max_chars", 250)
        self._unsaved_icon = None
        self._emit_unsaved_icon_data_change()

    def _get_unsaved_indicator_color(self) -> QColor:
        """Return the configured unsaved table-indicator color."""
        db_panel_cfg = ((self._config.get("ui") or {}).get("panels", {}) or {}).get("database", {})
        color = db_panel_cfg.get("unsaved_table_indicator_color", [255, 200, 100])
        try:
            return QColor(int(color[0]), int(color[1]), int(color[2]))
        except Exception:
            return QColor(255, 200, 100)

    def _emit_unsaved_icon_data_change(self) -> None:
        """Refresh the unsaved-indicator column after a theme/config change."""
        if not self._games:
            return
        parent = QModelIndex()
        top_left = self.index(0, self.COL_UNSAVED, parent)
        bottom_right = self.index(len(self._games) - 1, self.COL_UNSAVED, parent)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole],
        )
    
    def _emit_stats_relevant_data_change(self) -> None:
        """Notify listeners that stats-relevant game data or membership changed."""
        self.stats_relevant_data_change.emit()
    
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
            Number of columns (22: includes per-game Tags before PGN).
        """
        return 22
    
    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Get item flags for the given index.
        
        Args:
            index: Model index (row, column).
            
        Returns:
            Item flags indicating the item's state (enabled, selectable, etc.).
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    
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
        
        # Handle unsaved column: icon in UI (DecorationRole), text for export/copy (DisplayRole)
        if col == self.COL_UNSAVED:
            if role == Qt.ItemDataRole.DecorationRole:
                # Return icon if game has unsaved changes, None otherwise
                if game in self._unsaved_games:
                    if self._unsaved_icon is None:
                        self._unsaved_icon = self._create_unsaved_icon()
                    return self._unsaved_icon
                return None
            elif role == Qt.ItemDataRole.DisplayRole:
                # Empty so the cell shows only the icon (DecorationRole); export uses is_row_unsaved() instead
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
        elif col == self.COL_FILE_NUM:
            # Return file position if available, empty string otherwise
            return game.file_position if game.file_position > 0 else ""
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
        elif col == self.COL_TIMECONTROL:
            return getattr(game, "time_control", "") or ""
        elif col == self.COL_TC_TYPE:
            tc = getattr(game, "time_control", "") or ""
            return get_tc_type(tc, (self._config.get("ui") or {}).get("panels", {}).get("database", {}).get("tc_type"))
        elif col == self.COL_ANALYZED:
            return "✓" if game.analyzed else ""
        elif col == self.COL_ANNOTATED:
            return "✓" if getattr(game, "annotated", False) else ""
        elif col == self.COL_NOTES:
            return "✓" if getattr(game, "has_notes", False) else ""
        elif col == self.COL_SOURCE_DB:
            return game.source_database
        elif col == self.COL_REF_PLY:
            # 0 means "no specific reference ply" so display empty string
            ref_ply = int(getattr(game, "ref_ply", 0) or 0)
            if ref_ply <= 0:
                return ""
            move_no = (ref_ply + 1) // 2
            suffix = "..." if (ref_ply % 2) == 0 else "."
            return f"{move_no}{suffix}"
        elif col == self.COL_TAGS:
            return getattr(game, "game_tags", "") or ""
        elif col == self.COL_PGN:
            # Return a cached, single-line preview of the PGN for display.
            # The full PGN is still available on game.pgn and is used for exports.
            preview = getattr(game, "_pgn_preview", None)
            if preview is None:
                text = (game.pgn or "").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                max_len = self._pgn_preview_max_len
                if len(text) > max_len:
                    preview = text[: max_len - 1] + "…"
                else:
                    preview = text
                setattr(game, "_pgn_preview", preview)
            return preview
        
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
            headers = [
                "#",
                "# in File",
                "●",
                "White",
                "Black",
                "WhiteElo",
                "BlackElo",
                "Result",
                "Date",
                "Event",
                "Site",
                "Moves",
                "ECO",
                "TimeControl",
                "TC Type",
                "Analyzed",
                "Annotated",
                "Notes",
                "Source DB",
                "Move",
                "Game tags",
                "PGN",
            ]
            if 0 <= section < len(headers):
                return headers[section]
        
        return None
    
    def add_game(
        self,
        game: GameData,
        mark_unsaved: bool = True,
        tags: List[str] = None,
        position_hashes: Optional[List[int]] = None,
        position_hashes_fuzzy: Optional[List[int]] = None,
    ) -> None:
        """Add a game to the model.
        
        Args:
            game: GameData instance to add.
            mark_unsaved: If True, mark the game as having unsaved changes.
                         Set to False when loading games from a file (they're already saved).
                         Default is True for newly added games (import, paste, etc.).
            tags: List of tag names already extracted from the game (required).
                 Tags must be provided from the parsed game data to avoid redundant parsing.
        """
        if tags is None:
            raise ValueError("tags parameter is required. Tags must be extracted during PGN parsing.")
        
        # Set game number: use file_position if available (loaded from file),
        # otherwise use incremental number (pasted/imported)
        if game.file_position > 0:
            game.game_number = game.file_position
        else:
            game.game_number = len(self._games) + 1
        
        # Insert the new row
        row = len(self._games)
        self.beginInsertRows(self.index(row, 0).parent(), row, row)
        self._games.append(game)
        # Mark game as having unsaved changes if requested (newly added games are unsaved by default)
        if mark_unsaved:
            self._unsaved_games.add(game)
        self.endInsertRows()

        self._position_index_add_game(game, position_hashes, position_hashes_fuzzy)
        
        # Cache tags from this game
        self._add_tags_to_cache(set(tags))
        
        # Emit dataChanged for the unsaved column to ensure the indicator is displayed
        # This is needed because endInsertRows() may not trigger a refresh of the DecorationRole
        # Only emit if we marked it as unsaved (otherwise no indicator needed)
        if mark_unsaved:
            parent = QModelIndex()
            unsaved_index = self.index(row, self.COL_UNSAVED, parent)
            self.dataChanged.emit(unsaved_index, unsaved_index,
                                 [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
        self._emit_stats_relevant_data_change()
    
    def add_games_batch(
        self,
        games: List[GameData],
        mark_unsaved: bool = True,
        tags_list: List[List[str]] = None,
        position_hashes_list: Optional[List[Optional[List[int]]]] = None,
        position_hashes_fuzzy_list: Optional[List[Optional[List[int]]]] = None,
    ) -> None:
        """Add multiple games to the model in a single batch operation.
        
        This is much more efficient than calling add_game() multiple times,
        especially when the model is already connected to views, as it only
        triggers one view update cycle instead of one per game.
        
        Args:
            games: List of GameData instances to add.
            mark_unsaved: If True, mark all games as having unsaved changes.
                         Set to False when loading games from a file (they're already saved).
                         Default is True for newly added games (import, paste, etc.).
            tags_list: List of tag lists, one per game (must match games length, required).
                      Tags must be provided from the parsed game data to avoid redundant parsing.
        """
        if not games:
            return
        
        if tags_list is None:
            raise ValueError("tags_list parameter is required. Tags must be extracted during PGN parsing.")
        
        if len(tags_list) != len(games):
            raise ValueError(f"tags_list length ({len(tags_list)}) must match games length ({len(games)})")
        if position_hashes_list is not None and len(position_hashes_list) != len(games):
            raise ValueError(f"position_hashes_list length ({len(position_hashes_list)}) must match games length ({len(games)})")
        if position_hashes_fuzzy_list is not None and len(position_hashes_fuzzy_list) != len(games):
            raise ValueError(f"position_hashes_fuzzy_list length ({len(position_hashes_fuzzy_list)}) must match games length ({len(games)})")
        
        # Set game numbers for all games
        start_count = len(self._games)
        for i, game in enumerate(games):
            if game.file_position > 0:
                game.game_number = game.file_position
            else:
                game.game_number = start_count + i + 1
        
        # Batch insert: notify view once for all rows
        first_row = start_count
        last_row = start_count + len(games) - 1
        self.beginInsertRows(self.index(first_row, 0).parent(), first_row, last_row)
        
        # Add all games to the list
        self._games.extend(games)
        
        # Mark games as unsaved if requested
        if mark_unsaved:
            self._unsaved_games.update(games)
        
        self.endInsertRows()

        if position_hashes_list is None:
            for g in games:
                self._position_index_add_game(g, None, None)
        else:
            if position_hashes_fuzzy_list is None:
                for g, h in zip(games, position_hashes_list):
                    self._position_index_add_game(g, h, None)
            else:
                for g, h, hf in zip(games, position_hashes_list, position_hashes_fuzzy_list):
                    self._position_index_add_game(g, h, hf)
        
        # Cache tags from all games in this batch (use provided tags)
        all_tags: Set[str] = set()
        for tags in tags_list:
            if tags:
                all_tags.update(tags)
        self._add_tags_to_cache(all_tags)
        
        # Emit dataChanged for unsaved column if needed (only if marking as unsaved)
        # We emit for all rows at once for efficiency
        if mark_unsaved:
            parent = QModelIndex()
            top_left = self.index(first_row, self.COL_UNSAVED, parent)
            bottom_right = self.index(last_row, self.COL_UNSAVED, parent)
            self.dataChanged.emit(top_left, bottom_right,
                                 [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole])
        self._emit_stats_relevant_data_change()
    
    def clear(self) -> None:
        """Clear all games from the model."""
        if len(self._games) > 0:
            self.beginRemoveRows(self.index(0, 0).parent(), 0, len(self._games) - 1)
            self._games.clear()
            self._unsaved_games.clear()
            self._unique_tags.clear()
            self._position_index.clear()
            self._position_reverse.clear()
            self._position_index_fuzzy.clear()
            self._position_reverse_fuzzy.clear()
            self.endRemoveRows()
            self._emit_stats_relevant_data_change()
    
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
                self._position_index_remove_game(game)
                self._position_index_remove_game_fuzzy(game)
                self._unsaved_games.discard(game)
                # Emit signal for this single row removal
                self.beginRemoveRows(parent, row, row)
                self._games.pop(row)
                self.endRemoveRows()
        self._emit_stats_relevant_data_change()

    def get_position_matches(self, position_hash: int) -> Dict[int, int]:
        """Return dict of id(game) -> first ply where this position occurs."""
        try:
            h = int(position_hash)
        except Exception:
            return {}
        if not h:
            return {}
        out: Dict[int, int] = {}
        for gid, ply in self._position_index.get(h, []):
            if gid not in out:
                out[gid] = int(ply)
        return out

    def get_position_matches_fuzzy(self, position_hash: int) -> Dict[int, int]:
        """Return dict of id(game) -> first ply where this fuzzy position occurs."""
        try:
            h = int(position_hash)
        except Exception:
            return {}
        if not h:
            return {}
        out: Dict[int, int] = {}
        for gid, ply in self._position_index_fuzzy.get(h, []):
            if gid not in out:
                out[gid] = int(ply)
        return out

    def _position_index_remove_game(self, game: GameData) -> None:
        gid = id(game)
        entries = self._position_reverse.pop(gid, [])
        if not entries:
            return
        for h, ply in entries:
            bucket = self._position_index.get(int(h))
            if not bucket:
                continue
            # Remove all entries for this gid.
            bucket = [(g, p) for (g, p) in bucket if g != gid]
            if bucket:
                self._position_index[int(h)] = bucket
            else:
                self._position_index.pop(int(h), None)

    def _position_index_remove_game_fuzzy(self, game: GameData) -> None:
        gid = id(game)
        entries = self._position_reverse_fuzzy.pop(gid, [])
        if not entries:
            return
        for h, ply in entries:
            bucket = self._position_index_fuzzy.get(int(h))
            if not bucket:
                continue
            bucket = [(g, p) for (g, p) in bucket if g != gid]
            if bucket:
                self._position_index_fuzzy[int(h)] = bucket
            else:
                self._position_index_fuzzy.pop(int(h), None)

    def _position_index_add_game(
        self,
        game: GameData,
        position_hashes: Optional[List[int]],
        position_hashes_fuzzy: Optional[List[int]],
    ) -> None:
        # Ensure idempotent (e.g. reindexing).
        self._position_index_remove_game(game)
        self._position_index_remove_game_fuzzy(game)
        hashes = position_hashes
        hashes_fuzzy = position_hashes_fuzzy
        computed_from_pgn = False
        if not hashes or not hashes_fuzzy:
            computed = self._compute_position_hashes_from_pgn(getattr(game, "pgn", "") or "")
            if computed:
                computed_from_pgn = True
                if not hashes:
                    hashes = computed[0]
                if not hashes_fuzzy:
                    hashes_fuzzy = computed[1]
        if not hashes:
            return

        try:
            from app.services.logging_service import LoggingService
            LoggingService.get_instance().debug(
                "Position search index: indexing game "
                f"game_number={getattr(game, 'game_number', None)} "
                f"plies={len(hashes)} "
                f"computed_from_pgn={computed_from_pgn}"
            )
        except Exception:
            pass

        gid = id(game)
        rev: List[Tuple[int, int]] = []
        for ply, h in enumerate(hashes):
            try:
                hh = int(h)
            except Exception:
                continue
            if not hh:
                continue
            self._position_index.setdefault(hh, []).append((gid, int(ply)))
            rev.append((hh, int(ply)))
        if rev:
            self._position_reverse[gid] = rev

        if hashes_fuzzy:
            revf: List[Tuple[int, int]] = []
            for ply, h in enumerate(hashes_fuzzy):
                try:
                    hh = int(h)
                except Exception:
                    continue
                if not hh:
                    continue
                self._position_index_fuzzy.setdefault(hh, []).append((gid, int(ply)))
                revf.append((hh, int(ply)))
            if revf:
                self._position_reverse_fuzzy[gid] = revf

    def _compute_position_hashes_from_pgn(self, pgn_text: str) -> Optional[Tuple[List[int], List[int]]]:
        """Compute per-ply Zobrist hashes from a PGN main line.

        Used as a fallback when hashes were not provided by the PGN loader.
        """
        try:
            import chess
            import chess.pgn
            from io import StringIO
            from chess.polyglot import zobrist_hash

            if not pgn_text or not str(pgn_text).strip():
                return None
            pgn_io = StringIO(pgn_text)
            g = chess.pgn.read_game(pgn_io)
            if g is None:
                return None
            board = g.board()
            hashes: List[int] = [int(zobrist_hash(board))]
            # fuzzy: ignore castling/ep
            cr0 = getattr(board, "castling_rights", 0)
            ep0 = getattr(board, "ep_square", None)
            try:
                board.castling_rights = 0
                board.ep_square = None
                hashes_fuzzy: List[int] = [int(zobrist_hash(board))]
            finally:
                board.castling_rights = cr0
                board.ep_square = ep0
            node = g
            while node.variations:
                node = node.variation(0)
                board.push(node.move)
                hashes.append(int(zobrist_hash(board)))
                cr0 = getattr(board, "castling_rights", 0)
                ep0 = getattr(board, "ep_square", None)
                try:
                    board.castling_rights = 0
                    board.ep_square = None
                    hashes_fuzzy.append(int(zobrist_hash(board)))
                finally:
                    board.castling_rights = cr0
                    board.ep_square = ep0
            return (hashes, hashes_fuzzy)
        except Exception:
            return None
    
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
        
        # Note: game_number is NOT updated - it always reflects the original assignment
        
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

    def is_row_unsaved(self, row: int) -> bool:
        """Return whether the game at the given row has unsaved changes.

        Used by export so the "●" column can be exported as "●" or "" without
        putting text in the cell (which would show next to the icon in the UI).

        Args:
            row: Row index.

        Returns:
            True if the game has unsaved changes, False otherwise.
        """
        if 0 <= row < len(self._games):
            return self._games[row] in self._unsaved_games
        return False

    def get_row_indices_matching_column_value(
        self,
        column_index: int,
        criterion: str,
        reference_value: Any = None,
    ) -> List[int]:
        """Get row indices where the column value matches the given criterion.

        Uses the same value and empty semantics as data(DisplayRole). No Qt or view dependency.

        Args:
            column_index: Model column index.
            criterion: One of "all", "none", "equals", "not_equals", "empty", "not_empty".
            reference_value: For "equals" and "not_equals", the value to compare against.
                Normalized for comparison (e.g. str for display consistency).

        Returns:
            List of row indices (model space) matching the criterion.
        """
        n = len(self._games)
        if n == 0:
            return []

        if criterion == "all":
            return list(range(n))
        if criterion == "none":
            return []

        def cell_value(r: int) -> Any:
            idx = self.index(r, column_index)
            return self.data(idx, Qt.ItemDataRole.DisplayRole)

        def is_empty(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str):
                return val.strip() == ""
            return False

        ref_normalized = reference_value
        if ref_normalized is not None and not isinstance(ref_normalized, str):
            ref_normalized = str(ref_normalized)

        result: List[int] = []
        for row in range(n):
            val = cell_value(row)
            if criterion == "equals":
                v_str = str(val).strip() if val is not None else ""
                if ref_normalized is not None and v_str == ref_normalized.strip():
                    result.append(row)
            elif criterion == "not_equals":
                v_str = str(val).strip() if val is not None else ""
                if ref_normalized is not None and v_str != ref_normalized.strip():
                    result.append(row)
            elif criterion == "empty":
                if is_empty(val):
                    result.append(row)
            elif criterion == "not_empty":
                if not is_empty(val):
                    result.append(row)
        return result
    
    def get_all_games(self) -> List[GameData]:
        """Get all games in the model.
        
        Returns:
            List of GameData instances.
        """
        return self._games.copy()
    
    def _extract_tags_from_game(self, game: GameData) -> Set[str]:
        """Extract tag names from a game's PGN.
        
        Args:
            game: GameData instance to extract tags from.
            
        Returns:
            Set of tag names found in the game.
        """
        if not game or not game.pgn:
            return set()
        
        try:
            import chess.pgn
            from io import StringIO
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game and chess_game.headers:
                return set(chess_game.headers.keys())
        except Exception:
            pass
        
        return set()
    
    def _add_tags_to_cache(self, tags: Set[str]) -> None:
        """Add tags to the unique tags cache.
        
        Args:
            tags: Set of tag names to add.
        """
        if tags:
            self._unique_tags.update(tags)
    
    def get_unique_tags(self) -> List[str]:
        """Get ordered list of unique tags.
        
        Returns:
            List of tag names ordered by importance (same ordering as bulk_replace_controller).
        """
        if not self._unique_tags:
            return []
        
        # Standard PGN tags
        STANDARD_TAGS = [
            "White", "Black", "Result", "Date", "Event", "Site", "Round",
            "ECO", "WhiteElo", "BlackElo", "TimeControl", "WhiteTitle",
            "BlackTitle", "WhiteFideId", "BlackFideId", "WhiteTeam", "BlackTeam",
            "PlyCount", "EventDate", "Termination", "Annotator", "UTCTime"
        ]
        
        # Important/common tags that should appear first
        IMPORTANT_TAGS = ["White", "Black", "Result", "Date", "Event", "Site", "Round", "ECO"]
        
        # Separate tags into categories
        important_tags: List[str] = []
        standard_tags: List[str] = []
        custom_tags: List[str] = []
        
        standard_tags_set = set(STANDARD_TAGS)
        important_tags_set = set(IMPORTANT_TAGS)
        
        for tag_name in self._unique_tags:
            if tag_name in important_tags_set:
                important_tags.append(tag_name)
            elif tag_name in standard_tags_set:
                standard_tags.append(tag_name)
            else:
                custom_tags.append(tag_name)
        
        # Sort each category alphabetically
        important_tags.sort()
        standard_tags.sort()
        custom_tags.sort()
        
        # Within important tags, maintain importance order first, then alphabetical
        important_ordered: List[str] = []
        for important_tag in IMPORTANT_TAGS:
            if important_tag in important_tags:
                important_ordered.append(important_tag)
        
        # Combine: important tags (in importance order), then other standard tags (alphabetically), then custom tags (alphabetically)
        result: List[str] = []
        result.extend(important_ordered)
        result.extend([tag for tag in standard_tags if tag not in important_tags_set])
        result.extend(custom_tags)
        
        return result
    
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
    
    def update_game(self, game: 'GameData', *, reindex_positions: bool = True) -> bool:
        """Update a game in the model and notify views.
        
        This method finds the game, updates it, and emits dataChanged
        signal for all columns to refresh the table view. Automatically
        marks the game as having unsaved changes.

        Note: Updating the position-search index can be expensive because it may
        require parsing the full PGN and hashing every ply. Callers that update
        many games in rapid succession (e.g. bulk analysis) can pass
        `reindex_positions=False` and perform a full reindex later if needed.
        
        Args:
            game: GameData instance to update (must already be in the model).
            reindex_positions: If True (default), update the position-search index
                for this game based on its current PGN.
            
        Returns:
            True if game was found and updated, False otherwise.
        """
        row = self.find_game(game)
        if row is None:
            return False

        # Keep position index consistent with the game content (optional).
        if reindex_positions:
            self._position_index_add_game(game, None, None)
        
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
        self._emit_stats_relevant_data_change()
        return True
    
    def batch_update_games(self, games: List['GameData'], *, reindex_positions: bool = True) -> None:
        """Batch update multiple games and emit a single dataChanged signal.
        
        This is more efficient than calling update_game() multiple times,
        as it emits a single signal for all affected rows instead of one per game.
        
        Args:
            games: List of GameData instances to update (must already be in the model).
            reindex_positions: If True (default), update the position-search index
                for each game based on its current PGN.
        """
        if not games:
            return
        
        if reindex_positions:
            for game in games:
                self._position_index_add_game(game, None, None)
        
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
        self._emit_stats_relevant_data_change()
    
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
        
        circle_color = self._get_unsaved_indicator_color()
        
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
        # Don't sort by unsaved column (icon column) or "# in File" column (hidden)
        if column == self.COL_UNSAVED or column == self.COL_FILE_NUM:
            return
        
        # Define key extraction function for each column type
        def get_sort_key(game: GameData) -> Any:
            """Extract sort key value from a game for the current column.
            
            Returns:
                Sort key value appropriate for the column type.
            """
            if column == self.COL_NUM:
                # Sort by game_number (the value displayed in "#" column)
                # This sorts by the actual game number, whether from file_position or incremental
                return game.game_number
            elif column == self.COL_FILE_NUM:
                # Sort by file position (use tuple to ensure None sorts last)
                # Return (0, position) for file games, (1, 0) for non-file games
                # This ensures file games sort first, then non-file games
                if game.file_position > 0:
                    return (0, game.file_position)
                else:
                    return (1, 0)
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
            elif column == self.COL_TIMECONTROL:
                return getattr(game, "time_control", "") or ""
            elif column == self.COL_TC_TYPE:
                tc = getattr(game, "time_control", "") or ""
                return get_tc_type(tc, (self._config.get("ui") or {}).get("panels", {}).get("database", {}).get("tc_type"))
            elif column == self.COL_ANALYZED:
                return game.analyzed
            elif column == self.COL_ANNOTATED:
                return getattr(game, "annotated", False)
            elif column == self.COL_NOTES:
                return getattr(game, "has_notes", False)
            elif column == self.COL_SOURCE_DB:
                return game.source_database or ""
            elif column == self.COL_REF_PLY:
                return getattr(game, "ref_ply", 0)
            elif column == self.COL_TAGS:
                return getattr(game, "game_tags", "") or ""
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
        
        # Note: game_number is NOT updated during sorting - it always reflects
        # the original assignment (file_position when loaded, or incremental when pasted/imported)
        
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
        
        # Explicitly emit dataChanged for all rows and columns to ensure view refreshes
        # This is necessary for large datasets where layoutChanged might not fully refresh all cells
        if len(self._games) > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._games) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])
    
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


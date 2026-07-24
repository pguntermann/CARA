"""Opening service for looking up ECO codes and opening names from FEN positions."""

import json
import chess
import chess.pgn
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config.config_loader import ConfigLoader


@dataclass(frozen=True)
class OpeningDisplay:
    """ECO label for a book position."""

    eco: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.eco} · {self.name}"


OPENING_STARTING = OpeningDisplay("A00", "Starting Position")
OPENING_UNKNOWN = OpeningDisplay("A00", "Unknown Opening")


@dataclass(frozen=True)
class OpeningOutOfBookGap:
    """Stretch where the played line left the book before rejoining."""

    ply_count: int
    start_full_move: int
    start_is_white: bool
    end_full_move: int
    end_is_white: bool
    first_san: Optional[str]
    last_san: Optional[str]

    @staticmethod
    def _move_label(full_move: int, is_white: bool) -> str:
        return f"{full_move}." if is_white else f"{full_move}..."

    @property
    def summary(self) -> str:
        start = OpeningOutOfBookGap._move_label(self.start_full_move, self.start_is_white)
        end = OpeningOutOfBookGap._move_label(self.end_full_move, self.end_is_white)
        if self.ply_count <= 1:
            if self.first_san:
                return f"Out of book · {start} {self.first_san}"
            return f"Out of book · {start}"
        if self.first_san and self.last_san:
            return f"Out of book · {start} {self.first_san} … {end} {self.last_san}"
        return f"Out of book · {start}–{end} ({self.ply_count} moves)"


@dataclass(frozen=True)
class OpeningPathStep:
    """One distinct opening label along the played line to the current ply."""

    fen: str
    display: OpeningDisplay
    ply_index: int  # 0 = start; n = after nth ply
    move_san: Optional[str] = None
    move_uci: Optional[str] = None
    full_move_number: Optional[int] = None
    is_white_move: Optional[bool] = None
    gap_before: Optional[OpeningOutOfBookGap] = None


@dataclass(frozen=True)
class OpeningContinuation:
    """A legal move from a position that lands on another known book position."""

    san: str
    fen_after: str
    display: OpeningDisplay
    move_uci: str


class OpeningService:
    """Service for looking up opening information from FEN positions.
    
    This service loads ECO files and provides lookup functionality to identify
    opening ECO codes and names from chess positions.
    """

    MAX_CONTINUATIONS_PER_NODE = 12
    MAX_CONTINUATION_DEPTH = 8

    _PREFERRED_MOVE_ORDER = {
        san: i
        for i, san in enumerate(
            [
                "e4", "d4", "Nf3", "c4", "g3", "b3", "f4", "Nc3", "e3", "d3", "c3",
                "e5", "c5", "e6", "c6", "d5", "d6", "Nf6", "g6", "Nc6", "a6", "b6", "f5",
            ]
        )
    }
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the opening service.
        
        Args:
            config: Configuration dictionary containing resources.ecolists_path.
        """
        self.config = config
        self._eco_base: Optional[Dict[str, Any]] = None
        self._eco_interpolated: Optional[Dict[str, Any]] = None
        # Placement + side-to-move index (ignores EP and clocks), matching Chess Recorder.
        self._openings_by_book_key: Dict[str, Dict[str, Any]] = {}
        # Lazy reverse indexes for diagram lookup (ECO → FEN, ECO+name → FEN).
        self._fen_by_eco: Optional[Dict[str, str]] = None
        self._fen_by_eco_name: Optional[Dict[Tuple[str, str], str]] = None
        self._loaded = False
    
    def load(self) -> None:
        """Load ECO files into memory.
        
        This method loads the eco_base.json and eco_interpolated.json files.
        It should be called once before using lookup methods.
        """
        if self._loaded:
            return
        
        # Get ecolists path from config
        ecolists_path_str = self.config.get('resources', {}).get('ecolists_path', 'app/resources/ecolists')
        
        # Resolve path relative to app root
        app_root = Path(__file__).parent.parent.parent
        ecolists_path = app_root / ecolists_path_str
        
        # Load eco_base.json
        eco_base_file = ecolists_path / "eco_base.json"
        if eco_base_file.exists():
            with open(eco_base_file, "r", encoding="utf-8") as f:
                self._eco_base = json.load(f)
        else:
            self._eco_base = {}
        
        # Load eco_interpolated.json
        eco_interpolated_file = ecolists_path / "eco_interpolated.json"
        if eco_interpolated_file.exists():
            with open(eco_interpolated_file, "r", encoding="utf-8") as f:
                self._eco_interpolated = json.load(f)
        else:
            self._eco_interpolated = {}

        self._openings_by_book_key = self._build_book_key_index(
            self._eco_base or {},
            self._eco_interpolated or {},
        )
        
        self._loaded = True
        
        # Log opening book loaded
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        base_count = len(self._eco_base) if self._eco_base else 0
        interpolated_count = len(self._eco_interpolated) if self._eco_interpolated else 0
        logging_service.info(
            f"Opening book loaded: path={ecolists_path}, base_positions={base_count}, "
            f"interpolated_positions={interpolated_count}, book_keys={len(self._openings_by_book_key)}"
        )

    @staticmethod
    def book_key(fen: str) -> str:
        """Normalize a FEN to placement + side-to-move (ignore EP and clocks).
        
        Args:
            fen: Full or partial FEN string.
            
        Returns:
            Book key used for clock-independent opening lookup.
        """
        fields = fen.split(" ")
        if len(fields) >= 2:
            return f"{fields[0]} {fields[1]}"
        return fen

    def _build_book_key_index(
        self,
        eco_base: Dict[str, Any],
        eco_interpolated: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Build placement+STM index; interpolated entries override base on collision."""
        indexed: Dict[str, Dict[str, Any]] = {}
        for fen, entry in eco_base.items():
            if isinstance(entry, dict):
                indexed[self.book_key(fen)] = entry
        for fen, entry in eco_interpolated.items():
            if isinstance(entry, dict):
                indexed[self.book_key(fen)] = entry
        return indexed

    def _display_from_entry(self, entry: Dict[str, Any]) -> Optional[OpeningDisplay]:
        eco = entry.get("eco") or ""
        name = entry.get("name") or ""
        if not eco or not name:
            return None
        return OpeningDisplay(eco=str(eco), name=str(name))

    def lookup_opening_display(self, fen: str) -> Optional[OpeningDisplay]:
        """Look up an OpeningDisplay for a FEN (exact then book-key fallback)."""
        entry = self.lookup_opening(fen)
        if not entry:
            return None
        return self._display_from_entry(entry)
    
    def lookup_opening(self, fen: str) -> Optional[Dict[str, Any]]:
        """Look up opening information for a FEN position.
        
        Tries an exact full-FEN match first (interpolated, then base), then falls
        back to a placement + side-to-move key so positions that re-enter book at
        a different move clock still resolve.
        
        Args:
            fen: FEN position string.
            
        Returns:
            Dictionary with 'eco', 'name', 'moves', etc., or None if not found.
        """
        if not self._loaded:
            self.load()
        
        # First check interpolated (contains interpolated positions)
        if self._eco_interpolated and fen in self._eco_interpolated:
            return self._eco_interpolated[fen]
        
        # Then check base files
        if self._eco_base and fen in self._eco_base:
            return self._eco_base[fen]

        # Clock/EP-independent fallback (Chess Recorder bookKey behavior)
        return self._openings_by_book_key.get(self.book_key(fen))
    
    def get_opening_info(self, fen: str) -> Tuple[Optional[str], Optional[str]]:
        """Get ECO code and opening name for a FEN position.
        
        Args:
            fen: FEN position string.
            
        Returns:
            Tuple of (eco_code, opening_name). Both are None if not found.
        """
        opening = self.lookup_opening(fen)
        if opening:
            eco = opening.get('eco', None)
            name = opening.get('name', None)
            return (eco, name)
        return (None, None)

    def _ensure_fen_reverse_indexes(self) -> None:
        """Build ECO / ECO+name → FEN maps (shortest move-list wins per key)."""
        if self._fen_by_eco is not None and self._fen_by_eco_name is not None:
            return
        if not self._loaded:
            self.load()

        by_eco: Dict[str, Tuple[int, str]] = {}
        by_eco_name: Dict[Tuple[str, str], Tuple[int, str]] = {}
        for book in (self._eco_base or {}, self._eco_interpolated or {}):
            for fen, entry in book.items():
                if not isinstance(entry, dict):
                    continue
                eco = str(entry.get("eco") or "").strip()
                if not eco:
                    continue
                name = str(entry.get("name") or "").strip()
                move_len = len(str(entry.get("moves") or ""))
                prev = by_eco.get(eco)
                if prev is None or move_len < prev[0]:
                    by_eco[eco] = (move_len, fen)
                if name:
                    key = (eco, name)
                    prev_n = by_eco_name.get(key)
                    if prev_n is None or move_len < prev_n[0]:
                        by_eco_name[key] = (move_len, fen)

        self._fen_by_eco = {eco: fen for eco, (_n, fen) in by_eco.items()}
        self._fen_by_eco_name = {key: fen for key, (_n, fen) in by_eco_name.items()}

    def find_representative_fen(
        self, eco: Optional[str], name: Optional[str] = None
    ) -> Optional[str]:
        """Return a book FEN that best matches ``eco`` / ``name`` for diagrams.

        Prefers an exact ECO+name match; otherwise the ECO entry with the
        shortest move list (root-ish position for that code). Returns ``None``
        when the book has no entry for the ECO.
        """
        eco_key = str(eco or "").strip()
        if not eco_key or eco_key.lower() == "unknown":
            return None
        self._ensure_fen_reverse_indexes()
        assert self._fen_by_eco is not None and self._fen_by_eco_name is not None
        name_key = str(name or "").strip()
        if name_key:
            fen = self._fen_by_eco_name.get((eco_key, name_key))
            if fen:
                return fen
        return self._fen_by_eco.get(eco_key)

    def is_book_position(self, fen: str) -> bool:
        """Return True if the FEN resolves to a known opening (exact or book-key)."""
        return self.lookup_opening(fen) is not None
    
    def is_loaded(self) -> bool:
        """Check if ECO files are loaded.
        
        Returns:
            True if files are loaded, False otherwise.
        """
        return self._loaded

    @staticmethod
    def lichess_name_slug(name: str) -> str:
        """Convert an opening name to a Lichess `/opening/` path slug."""
        cleaned = (
            str(name or "")
            .replace(":", " ")
            .replace(",", " ")
            .replace("'", "")
            .replace("’", "")
        )
        parts = [p for p in cleaned.split() if p]
        return "_".join(parts)

    @staticmethod
    def lichess_moves_path(moves: str) -> str:
        """Convert a book moves string like ``1. e4 e5 2. Nf3`` to ``e4_e5_Nf3``."""
        sans: List[str] = []
        for token in str(moves or "").replace("...", " ").split():
            raw = token.strip()
            if not raw:
                continue
            if raw.endswith("."):
                # Move number like "1."
                continue
            if raw[0].isdigit() and "." in raw:
                # Rare glued form "1.e4"
                raw = raw.split(".", 1)[1]
            san = raw.rstrip("+#!?")
            if san:
                sans.append(san)
        return "_".join(sans)

    @staticmethod
    def lichess_analysis_url(fen: str) -> str:
        """Build a Lichess analysis-board URL for ``fen``."""
        fen_path = str(fen or chess.Board().fen()).strip().replace(" ", "_")
        return f"https://lichess.org/analysis/{fen_path}"

    def lichess_url_for_fen(self, fen: str) -> str:
        """Build the best Lichess deep link for a position.

        Preference:
        1. ``/opening/{NameSlug}/{sans}`` when name + moves are known
        2. ``/opening/{ECO}`` when only ECO is known
        3. ``/analysis/{fen}`` otherwise
        """
        if not self._loaded:
            self.load()

        entry = self.lookup_opening(fen)
        if entry:
            name = str(entry.get("name") or "").strip()
            moves = str(entry.get("moves") or "").strip()
            eco = str(entry.get("eco") or "").strip()
            slug = self.lichess_name_slug(name) if name else ""
            moves_path = self.lichess_moves_path(moves) if moves else ""
            if slug and moves_path:
                return f"https://lichess.org/opening/{slug}/{moves_path}"
            if slug:
                return f"https://lichess.org/opening/{slug}"
            if eco:
                return f"https://lichess.org/opening/{eco}"

        return self.lichess_analysis_url(fen)

    @staticmethod
    def is_standard_start_fen(fen: str) -> bool:
        """True for the standard starting position (ECO tables omit it)."""
        try:
            return OpeningService.book_key(fen) == OpeningService.book_key(chess.Board().fen())
        except Exception:
            return False

    def replay_mainline_to_ply(
        self, pgn: str, ply_index: int
    ) -> Tuple[List[str], List[str], List[str]]:
        """Replay the PGN mainline up to ``ply_index``.

        Returns:
            ``(fens, sans, ucis)`` where ``fens[0]`` is the start position and
            ``fens[k]`` is the position after ``k`` plies (``k <= ply_index``).
        """
        fens: List[str] = []
        sans: List[str] = []
        ucis: List[str] = []
        try:
            game = chess.pgn.read_game(StringIO(pgn or ""))
            if game is None:
                return [chess.Board().fen()], [], []
            board = game.board()
            fens.append(board.fen())
            node = game
            while node.variations and len(sans) < max(0, ply_index):
                node = node.variation(0)
                move = node.move
                sans.append(board.san(move))
                ucis.append(move.uci())
                board.push(move)
                fens.append(board.fen())
        except Exception:
            return [chess.Board().fen()], [], []
        return fens, sans, ucis

    def fen_at_ply(self, pgn: str, ply_index: int) -> str:
        """Return the mainline FEN at ``ply_index`` (0 = start)."""
        fens, _, _ = self.replay_mainline_to_ply(pgn, ply_index)
        return fens[-1] if fens else chess.Board().fen()

    def build_path_from_pgn(self, pgn: str, ply_index: int) -> List[OpeningPathStep]:
        """Build distinct opening steps along the main line up to ``ply_index``.
        
        Args:
            pgn: Game PGN.
            ply_index: Active ply (0 = start position).
            
        Returns:
            Path steps with optional out-of-book gaps on rejoin.
        """
        if not self._loaded:
            self.load()

        fens, sans, ucis = self.replay_mainline_to_ply(pgn, ply_index)
        return self.build_path_from_replay(fens, sans, ucis)

    def build_path_from_replay(
        self,
        fens: List[str],
        sans: List[str],
        ucis: List[str],
    ) -> List[OpeningPathStep]:
        """Build path steps from an already-replayed mainline."""
        if not self._loaded:
            self.load()
        return self._build_path(fens, sans, ucis)

    def last_in_book_index(self, fens: List[str]) -> int:
        """Return the highest FEN index that is in the opening book (or standard start).

        Scans the full line (including after out-of-book gaps) so a later rejoin
        updates the index. Used to cap the SAN summary while the current ply is
        out of book.
        """
        if not fens:
            return 0
        if not self._loaded:
            self.load()
        last = 0
        for index, fen in enumerate(fens):
            match = self.lookup_opening_display(fen)
            if match is None and index == 0 and self.is_standard_start_fen(fen):
                match = OPENING_STARTING
            if match is not None:
                last = index
        return last

    def _build_path(
        self,
        fens: List[str],
        sans: List[str],
        ucis: List[str],
    ) -> List[OpeningPathStep]:
        steps: List[OpeningPathStep] = []
        last_display: Optional[OpeningDisplay] = None
        out_of_book_start: Optional[int] = None

        for index, fen in enumerate(fens):
            match = self.lookup_opening_display(fen)
            # ECO omits the real start; only force that label for the standard start FEN.
            if match is None and index == 0 and self.is_standard_start_fen(fen):
                match = OPENING_STARTING

            if match is None:
                if out_of_book_start is None and index > 0:
                    out_of_book_start = index
                continue

            gap_before: Optional[OpeningOutOfBookGap] = None
            if out_of_book_start is not None and out_of_book_start <= index - 1:
                gap_before = self._out_of_book_gap(out_of_book_start, index - 1, sans)
            out_of_book_start = None

            if match == last_display and gap_before is None:
                continue

            move_san = sans[index - 1] if index > 0 and index - 1 < len(sans) else None
            move_uci = ucis[index - 1] if index > 0 and index - 1 < len(ucis) else None
            full_move = (index + 1) // 2 if index > 0 else None
            is_white = (index % 2 == 1) if index > 0 else None

            steps.append(
                OpeningPathStep(
                    fen=fen,
                    display=match,
                    ply_index=index,
                    move_san=move_san,
                    move_uci=move_uci,
                    full_move_number=full_move,
                    is_white_move=is_white,
                    gap_before=gap_before,
                )
            )
            last_display = match

        if not steps and fens:
            fen0 = fens[0]
            display = self.lookup_opening_display(fen0)
            if display is None and self.is_standard_start_fen(fen0):
                display = OPENING_STARTING
            if display is None:
                display = OPENING_UNKNOWN
            steps = [
                OpeningPathStep(
                    fen=fen0,
                    display=display,
                    ply_index=0,
                )
            ]
        return steps

    def _out_of_book_gap(
        self,
        from_ply_index: int,
        to_ply_index: int,
        sans: List[str],
    ) -> OpeningOutOfBookGap:
        start = max(from_ply_index, 1)
        end = max(to_ply_index, start)
        first_i = start - 1
        last_i = end - 1
        return OpeningOutOfBookGap(
            ply_count=end - start + 1,
            start_full_move=(start + 1) // 2,
            start_is_white=start % 2 == 1,
            end_full_move=(end + 1) // 2,
            end_is_white=end % 2 == 1,
            first_san=sans[first_i] if 0 <= first_i < len(sans) else None,
            last_san=sans[last_i] if 0 <= last_i < len(sans) else None,
        )

    def continuations(
        self,
        fen: str,
        limit: Optional[int] = None,
    ) -> List[OpeningContinuation]:
        """Legal moves from ``fen`` that land on another known book position."""
        if not self._loaded:
            self.load()
        if limit is None:
            limit = self.MAX_CONTINUATIONS_PER_NODE
        try:
            board = chess.Board(fen)
        except Exception:
            return []

        results: List[OpeningContinuation] = []
        for move in board.legal_moves:
            san = board.san(move)
            board.push(move)
            fen_after = board.fen()
            display = self.lookup_opening_display(fen_after)
            board.pop()
            if display is None:
                continue
            results.append(
                OpeningContinuation(
                    san=san,
                    fen_after=fen_after,
                    display=display,
                    move_uci=move.uci(),
                )
            )
            # Early exit for existence probes (limit=1) and capped listings.
            if len(results) >= max(int(limit), 0) and max(int(limit), 0) > 0:
                # Still need full sort for normal listings; only short-circuit probes.
                if max(int(limit), 0) == 1:
                    return results

        def sort_key(c: OpeningContinuation) -> Tuple[int, str, str]:
            normalized = c.san.rstrip("+#")
            rank = self._PREFERRED_MOVE_ORDER.get(normalized, 10_000)
            return (rank, c.display.eco, c.san)

        results.sort(key=sort_key)
        return results[: max(int(limit), 0)]
    
    def get_final_eco_for_game(self, pgn: str) -> Optional[str]:
        """Get the final ECO code for a game by traversing moves backwards.
        
        This method parses the PGN, traverses all moves backwards, and looks up ECO codes
        for each position. Returns the first ECO code found when traversing backwards
        (which is the last opening played in the game). This is more efficient than
        traversing forwards since we can stop once we find an opening.
        
        This follows the same pattern as GameController.extract_moves_from_game() but
        traverses backwards for efficiency.
        
        Args:
            pgn: PGN string of the game.
            
        Returns:
            ECO code string if found, None otherwise.
        """
        if not self._loaded:
            self.load()
        
        try:
            # Parse the PGN
            pgn_io = StringIO(pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return None
            
            # Navigate to end of game first
            node = chess_game
            move_nodes = []  # Store all move nodes for backwards traversal
            
            # Traverse forwards to collect all nodes
            while node.variations:
                next_node = node.variation(0)
                move_nodes.append(next_node)
                node = next_node
            
            # Traverse backwards to find the last opening
            # This is more efficient - we can stop once we find an ECO
            for move_idx in range(len(move_nodes) - 1, -1, -1):
                move_node = move_nodes[move_idx]
                
                # Get the board position after the move (for opening lookup)
                board_after = move_node.board()
                fen_after = board_after.fen()  # Use full FEN string (matches GameController pattern)
                
                # Look up opening for this position (after the move)
                eco, _ = self.get_opening_info(fen_after)
                
                if eco:
                    return eco  # Found opening - return immediately
            
            return None
            
        except Exception:
            # If parsing fails, return None
            return None

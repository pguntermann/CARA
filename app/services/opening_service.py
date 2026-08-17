"""Opening service for looking up ECO codes and opening names.

Position lookups use FEN. Game-level ECO (header, bulk analysis, bulk ECO
update) uses :meth:`OpeningService.last_opening_for_pgn` — the last named
book ply on the main line.
"""

import json
import threading
import chess
import chess.pgn
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Dict, Any, Optional, Sequence, Tuple, List, Set
from typing import TYPE_CHECKING

from app.utils.path_resolver import get_app_resource_path

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
    """One in-book position along the played line to the current ply."""

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


@dataclass(frozen=True)
class EcoBookRow:
    """One ECO book position (base or interpolated)."""

    fen: str
    name: str
    eco: str
    moves: str


def parse_move_sans(moves: str) -> List[str]:
    """Parse a book ``moves`` string like ``1. e4 e5 2. Nf3`` into SAN tokens."""
    sans: List[str] = []
    for token in str(moves or "").replace("...", " ").split():
        raw = token.strip()
        if not raw:
            continue
        if raw.endswith("."):
            continue
        if raw.isdigit():
            continue
        if raw[0].isdigit() and "." in raw:
            raw = raw.split(".", 1)[1]
        san = raw.rstrip("+#!?")
        if san:
            sans.append(san)
    return sans


def fen_after_sans(sans: Sequence[str]) -> Optional[str]:
    """Replay ``sans`` from the standard start. ``None`` if a token is illegal."""
    board = chess.Board()
    try:
        for san in sans:
            board.push_san(san)
    except ValueError:
        return None
    return board.fen()


def _lcp_len(sequences: Sequence[Sequence[str]]) -> int:
    if not sequences:
        return 0
    shortest = min(len(seq) for seq in sequences)
    first = sequences[0]
    n = 0
    while n < shortest and all(seq[n] == first[n] for seq in sequences):
        n += 1
    return n


def _fen_from_lcp(
    items: Sequence[Tuple[int, EcoBookRow, List[str]]],
    lcp_len: int,
) -> Optional[str]:
    """Book row on the prefix if present; otherwise replay. Empty prefix → shallowest."""
    if not items:
        return None
    if lcp_len <= 0:
        return items[0][1].fen
    lcp = items[0][2][:lcp_len]
    for _depth, row, sans in items:
        if sans == lcp:
            return row.fen
    parent = fen_after_sans(lcp)
    return parent if parent else items[0][1].fen


def compute_tabiya_fen(
    rows: Sequence[EcoBookRow],
    *,
    family: bool = False,
) -> Optional[str]:
    """Choose one diagram FEN from book rows.

    Dedup transpositions (placement + side to move).

    Named entries (``family=False``): use the shallowest unique position. If
    several min-depth positions are siblings, pop to their common parent.

    Family roots (``family=True``): use the longest common SAN prefix of all
    unique lines so a shallow sideline does not steal the diagram.
    Unrelated move orders (empty prefix) keep the shallowest FEN, not startpos.
    """
    if not rows:
        return None

    by_key: Dict[str, Tuple[int, EcoBookRow, List[str]]] = {}
    for row in rows:
        sans = parse_move_sans(row.moves)
        depth = len(sans)
        key = OpeningService.book_key(row.fen)
        prev = by_key.get(key)
        if prev is None or depth < prev[0]:
            by_key[key] = (depth, row, sans)

    items = list(by_key.values())
    if not items:
        return None
    items.sort(key=lambda item: (item[0], item[1].fen))

    if family:
        return _fen_from_lcp(items, _lcp_len([sans for _d, _r, sans in items]))

    min_depth = items[0][0]
    shallow = [item for item in items if item[0] == min_depth]
    if len(shallow) == 1:
        return shallow[0][1].fen
    return _fen_from_lcp(shallow, _lcp_len([sans for _d, _r, sans in shallow]))


class OpeningService:
    """Service for looking up opening information from FEN positions.

    Production code should use :meth:`get_instance` so the ECO book is loaded
    once per process. Tests may still construct ``OpeningService(config)`` for
    isolation. After :meth:`load`, lookups are read-only and safe to share
    across threads.
    """

    MAX_CONTINUATIONS_PER_NODE = 12
    MAX_CONTINUATION_DEPTH = 8

    _instance: Optional["OpeningService"] = None
    _instance_lock = threading.Lock()

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
        # Curated (base) placement+STM index for classification names.
        self._classified_by_book_key: Dict[str, Dict[str, Any]] = {}
        # Placement+STM keys from base and interpolated (theory graph, not names).
        self._theory_book_keys: Set[str] = set()
        # Lazy reverse indexes for diagram lookup (ECO → FEN, ECO+name → FEN).
        self._fen_by_eco: Optional[Dict[str, str]] = None
        self._fen_by_eco_name: Optional[Dict[Tuple[str, str], str]] = None
        self._book_rows: Optional[List[EcoBookRow]] = None
        self._loaded = False
        self._load_lock = threading.Lock()

    @classmethod
    def get_instance(cls, config: Dict[str, Any]) -> "OpeningService":
        """Return the process-wide shared opening book (lazy; call ``load()`` as needed)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    def load(self) -> None:
        """Load ECO files and derived indexes into memory.

        Thread-safe. After return, lookup maps are immutable and shared reads
        do not need a lock.
        """
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return

            ecolists_path_str = self.config.get('resources', {}).get(
                'ecolists_path', 'app/resources/ecolists'
            )
            ecolists_path = Path(str(ecolists_path_str))
            if not ecolists_path.is_absolute():
                ecolists_path = get_app_resource_path(str(ecolists_path))

            eco_base_file = ecolists_path / "eco_base.json"
            if eco_base_file.exists():
                with open(eco_base_file, "r", encoding="utf-8") as f:
                    self._eco_base = json.load(f)
            else:
                self._eco_base = {}

            eco_interpolated_file = ecolists_path / "eco_interpolated.json"
            if eco_interpolated_file.exists():
                with open(eco_interpolated_file, "r", encoding="utf-8") as f:
                    self._eco_interpolated = json.load(f)
            else:
                self._eco_interpolated = {}

            self._classified_by_book_key = self._build_classified_index(self._eco_base or {})
            self._theory_book_keys = self._build_theory_keys(
                self._eco_base or {},
                self._eco_interpolated or {},
            )
            self._book_rows = self._build_book_rows()
            self._fen_by_eco, self._fen_by_eco_name = self._build_fen_reverse_indexes()
            self._loaded = True

            from app.services.logging_service import LoggingService
            logging_service = LoggingService.get_instance()
            base_count = len(self._eco_base) if self._eco_base else 0
            interpolated_count = len(self._eco_interpolated) if self._eco_interpolated else 0
            classified_count = len(self._classified_by_book_key)
            theory_count = len(self._theory_book_keys)
            book_row_count = len(self._book_rows or [])
            fen_eco_count = len(self._fen_by_eco or {})
            fen_eco_name_count = len(self._fen_by_eco_name or {})
            logging_service.debug(
                f"Opening lookup index built: classified_keys={classified_count}, "
                f"theory_keys={theory_count}, book_rows={book_row_count}, "
                f"fen_by_eco={fen_eco_count}, fen_by_eco_name={fen_eco_name_count}"
            )
            logging_service.info(
                f"Opening book loaded: path={ecolists_path}, base_positions={base_count}, "
                f"interpolated_positions={interpolated_count}, "
                f"classified_keys={classified_count}, "
                f"theory_keys={theory_count}"
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

    def _build_classified_index(
        self, eco_base: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Placement+STM index of curated (base) names only.

        Interpolated rows are omitted: they copy a shallow root name onto later
        plies and would mislabel transpositions (e.g. Van't Kruijs on a Modern).
        On a key collision, keep the longer canonical line (more specific tabiya).
        """
        indexed: Dict[str, Tuple[Dict[str, Any], int]] = {}
        for fen, entry in eco_base.items():
            if not isinstance(entry, dict):
                continue
            key = self.book_key(fen)
            depth = len(parse_move_sans(str(entry.get("moves") or "")))
            prev = indexed.get(key)
            if prev is None or depth > prev[1]:
                indexed[key] = (entry, depth)
        return {key: entry for key, (entry, _depth) in indexed.items()}

    def _build_theory_keys(
        self,
        eco_base: Dict[str, Any],
        eco_interpolated: Dict[str, Any],
    ) -> Set[str]:
        """Placement+STM keys that still count as opening-book positions."""
        keys: Set[str] = set()
        for book in (eco_base, eco_interpolated):
            for fen, entry in book.items():
                if isinstance(entry, dict):
                    keys.add(self.book_key(str(fen)))
        return keys

    def _build_book_rows(self) -> List[EcoBookRow]:
        """Unique ECO book positions (interpolated overrides base on the same FEN)."""
        by_fen: Dict[str, EcoBookRow] = {}
        for book in (self._eco_base or {}, self._eco_interpolated or {}):
            for fen, entry in book.items():
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "").strip()
                if not name:
                    continue
                by_fen[str(fen)] = EcoBookRow(
                    fen=str(fen),
                    name=name,
                    eco=str(entry.get("eco") or "").strip(),
                    moves=str(entry.get("moves") or "").strip(),
                )
        return list(by_fen.values())

    def _build_fen_reverse_indexes(
        self,
    ) -> Tuple[Dict[str, str], Dict[Tuple[str, str], str]]:
        """ECO / ECO+name → FEN maps (shortest move-list wins per key)."""
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
        return (
            {eco: fen for eco, (_n, fen) in by_eco.items()},
            {key: fen for key, (_n, fen) in by_eco_name.items()},
        )

    def _display_from_entry(self, entry: Dict[str, Any]) -> Optional[OpeningDisplay]:
        eco = entry.get("eco") or ""
        name = entry.get("name") or ""
        if not eco or not name:
            return None
        return OpeningDisplay(eco=str(eco), name=str(name))

    def lookup_opening_display(self, fen: str) -> Optional[OpeningDisplay]:
        """Look up a curated OpeningDisplay for a FEN (exact then book-key)."""
        entry = self.lookup_opening(fen)
        if not entry:
            return None
        return self._display_from_entry(entry)
    
    def lookup_opening(self, fen: str) -> Optional[Dict[str, Any]]:
        """Look up a curated opening name for a FEN position.

        Matches Lichess chess-openings: only named (base ECO) positions, keyed
        by exact FEN then placement + side-to-move so transpositions resolve.
        Interpolated gap-fills are not used for names.

        Args:
            fen: FEN position string.
            
        Returns:
            Dictionary with 'eco', 'name', 'moves', etc., or None if not found.
        """
        if not self._loaded:
            self.load()

        entry: Optional[Dict[str, Any]] = None
        if self._eco_base and fen in self._eco_base:
            found = self._eco_base[fen]
            if isinstance(found, dict):
                entry = found
        if entry is None:
            found = self._classified_by_book_key.get(self.book_key(fen))
            entry = found if isinstance(found, dict) else None
        return entry

    def get_opening_info(self, fen: str) -> Tuple[Optional[str], Optional[str]]:
        """Get ECO code and opening name for a FEN position.

        Position lookup only. Game-level ECO (header, bulk analysis, bulk
        ECO update) must use :meth:`last_opening_for_pgn` /
        :meth:`get_final_eco_for_game`.

        Args:
            fen: FEN position string.

        Returns:
            Tuple of (eco_code, opening_name). Both are None if not found.
        """
        display = self.lookup_opening_display(fen)
        if display:
            return (display.eco, display.name)
        return (None, None)

    def last_opening_from_fens(
        self, fens: Sequence[str]
    ) -> Optional[OpeningDisplay]:
        """Last curated opening among ``fens``, scanning from the end.

        This is the single game-level rule: the last mainline ply that is a
        named book position. Callers must not reimplement last-row / ``*``
        scans on move tables.
        """
        if not self._loaded:
            self.load()
        for fen in reversed(list(fens)):
            display = self.lookup_opening_display(fen)
            if display:
                return display
        return None

    def last_opening_for_pgn(self, pgn: str) -> Optional[OpeningDisplay]:
        """Last curated opening on the PGN main line."""
        return self.last_opening_from_fens(self._mainline_fens_after_each_move(pgn))

    def _mainline_fens_after_each_move(self, pgn: str) -> List[str]:
        """FENs after each mainline ply. Empty if the PGN cannot be parsed."""
        try:
            pgn_io = StringIO(pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game is None:
                return []
            fens: List[str] = []
            node = chess_game
            while node.variations:
                node = node.variation(0)
                fens.append(node.board().fen())
            return fens
        except Exception:
            return []

    def _ensure_fen_reverse_indexes(self) -> None:
        if not self._loaded:
            self.load()

    def iter_book_rows(self) -> List[EcoBookRow]:
        """All unique ECO book positions (interpolated overrides base on the same FEN)."""
        if not self._loaded:
            self.load()
        return self._book_rows or []

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
        """True if the position appears in the ECO theory graph (base or interpolated)."""
        if not self._loaded:
            self.load()
        if self._eco_base and fen in self._eco_base:
            return True
        if self._eco_interpolated and fen in self._eco_interpolated:
            return True
        return self.book_key(fen) in self._theory_book_keys
    
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
        return "_".join(parse_move_sans(moves))

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
        """Return the highest FEN index that is in the opening theory graph.

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
            if index == 0 and self.is_standard_start_fen(fen):
                last = index
                continue
            if self.is_book_position(fen):
                last = index
        return last

    def _build_path(
        self,
        fens: List[str],
        sans: List[str],
        ucis: List[str],
    ) -> List[OpeningPathStep]:
        steps: List[OpeningPathStep] = []
        out_of_book_start: Optional[int] = None
        last_named: Optional[OpeningDisplay] = None

        for index, fen in enumerate(fens):
            named = self.lookup_opening_display(fen)
            # ECO omits the real start; only force that label for the standard start FEN.
            if named is None and index == 0 and self.is_standard_start_fen(fen):
                named = OPENING_STARTING
            if named is not None:
                last_named = named
                match = named
            elif last_named is not None and self.is_book_position(fen):
                # Unnamed theory ply: keep the last curated name (Lichess carry-forward).
                match = last_named
            else:
                match = None

            if match is None:
                if out_of_book_start is None and index > 0:
                    out_of_book_start = index
                continue

            gap_before: Optional[OpeningOutOfBookGap] = None
            if out_of_book_start is not None and out_of_book_start <= index - 1:
                gap_before = self._out_of_book_gap(out_of_book_start, index - 1, sans)
            out_of_book_start = None

            # Every in-book ply is its own step (including same ECO/name continuations),
            # so "Lines until here" shows each played position up to the current line.
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
        fallback_display: Optional[OpeningDisplay] = None,
    ) -> List[OpeningContinuation]:
        """Legal moves from ``fen`` that land on another theory-graph position.

        Destination names are curated lookups. Interpolated-only landings keep
        ``fallback_display`` (typically the current named opening) instead of
        adopting a shallow interpolated root name.
        """
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
            if display is None and self.is_book_position(fen_after):
                display = fallback_display
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
        """ECO of the last named book opening on the main line.

        Thin wrapper over :meth:`last_opening_for_pgn`. Used by bulk ECO
        update, bulk analysis, and the game header.
        """
        opening = self.last_opening_for_pgn(pgn)
        return opening.eco if opening else None

"""One shared text renderer for a logged moment (#93).

Both the Chess Log tab's "Copy log to clipboard" and Show Shallow/Vague Logs'
"Copy to clipboard" build their moment text here, in both clipboard flavors
(plain text and HTML), from the same data.

A moment is rendered whole (every answer, flagged or not) and each flagged
answer is marked after its text: ``Why1: I wanted to open the h-file [Shallow]``.

Single source of truth (#85/#88): the renderer is handed moment *references*
(game, path_key, preset) and reads the entries and flags through the Chess Log
controller at render time.  It keeps no copy of either and saves nothing.  Only
saved flags count; an Ignored answer (Ignore honoured for its current text) is
treated as not flagged.  The move is shown as the Chess Log dialogs show it
(``32. g5`` / ``32… g5``) via ``node_info``; a path key is never printed.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from io import StringIO
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Tuple

import chess.pgn

from app.services.chess_log_html_service import ChessLogHTMLService, _encode_text
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.chess_log_preset_order import order_categories
from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
from app.utils.pgn_variation_path import decode_path
from app.views.dialogs._tag_row_helpers import game_header_text, node_info, ply_for_path

_WHY_KEYS = ("Why1", "Why2", "Why3", "Why4")
_WHOLE_GAME_LABEL = "Whole game"
_UNKNOWN_MOVE_LABEL = "Unknown move"


def display_move_label(pgn_game: Optional[chess.pgn.Game], path_key: str) -> str:
    """The label for a moment's move: ``32. g5`` / ``32… g5``, never the path key.

    Falls back to "Whole game" (empty path) or "Unknown move" (move not found).
    """
    if not (path_key or "").strip():
        return _WHOLE_GAME_LABEL
    _fen, _move, label, _black = node_info(pgn_game, path_key)
    # node_info returns the path key itself when the node cannot be located.
    return _UNKNOWN_MOVE_LABEL if label == path_key else label


@dataclass(frozen=True)
class MomentRef:
    """Names one moment; carries no entries and no flags."""

    game: Any
    path_key: str
    preset: str


@dataclass(frozen=True)
class RenderedMoments:
    """The two clipboard flavors of the same moments."""

    plain: str
    html: str


def _answer_flags(entry: Dict[str, Any]) -> Tuple[bool, bool]:
    """(shallow, vague) for one saved entry; Ignored answers are unflagged."""
    if ChessLogStorageService.is_entry_ignore_honoured(entry):
        return (False, False)
    return (bool(entry.get("is_shallow")), bool(entry.get("is_vague")))


def moment_flags(
    preset: str, entries: List[Dict[str, Any]]
) -> Tuple[bool, bool, FrozenSet[str], FrozenSet[str]]:
    """(is_shallow, is_vague, shallow_cats, vague_cats) for a moment's entries.

    CLAMP/CCT flag the moment; 3x3 flags per answer (Why1-3 Shallow, Why4 Vague).
    Uses ``_answer_flags``, so every output agrees on what still applies to the text.
    """
    if preset == "3x3":
        shallow_cats = set()
        vague_cats = set()
        for e in entries:
            if not (e.get("why") or "").strip():
                continue
            shallow, vague = _answer_flags(e)
            if shallow and e.get("cat") in _WHY_KEYS[:3]:
                shallow_cats.add(e["cat"])
            if vague and e.get("cat") == _WHY_KEYS[3]:
                vague_cats.add(e["cat"])
        return (False, False, frozenset(shallow_cats), frozenset(vague_cats))
    flags = [_answer_flags(e) for e in entries]
    return (any(f[0] for f in flags), any(f[1] for f in flags), frozenset(), frozenset())


class ChessLogMomentRenderer:
    """Renders moments through *controller* (needs ``get_tags_for_game(game)``)."""

    def __init__(self, controller, config: Dict[str, Any]) -> None:
        self._controller = controller
        self._svc = ChessLogHTMLService(config)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(
        self,
        refs: Iterable[MomentRef],
        entries_for: Optional[Callable[[MomentRef], List[Dict[str, Any]]]] = None,
    ) -> RenderedMoments:
        """Render *refs* grouped under a header per game (first-appearance order),
        moments within a game in ply order.

        *entries_for* supplies a moment's entries instead of the controller; a
        dialog that shows pending (unsaved) state passes its own.  Default: the
        controller's saved entries.
        """
        plain: List[str] = []
        html_parts: List[str] = []
        pgn_cache: Dict[int, Optional[chess.pgn.Game]] = {}
        refs = self._in_ply_order(list(refs), pgn_cache)
        current_game = None
        opened = False
        for ref in refs:
            moment = self._moment_lines(ref, pgn_cache, entries_for)
            if moment is None:
                continue
            if not opened or ref.game is not current_game:
                if opened:
                    plain.append("")
                    html_parts.append("<hr>")
                header = game_header_text(ref.game)
                plain.append(header)
                html_parts.append(f"<h3>{html.escape(header, quote=False)}</h3>")
                current_game = ref.game
                opened = True
            m_plain, m_html = moment
            plain.extend(m_plain)
            html_parts.extend(m_html)
        return RenderedMoments(plain="\n".join(plain), html="".join(html_parts))

    def _in_ply_order(
        self, refs: List[MomentRef], pgn_cache: Dict[int, Optional[chess.pgn.Game]]
    ) -> List[MomentRef]:
        """Games in first-appearance order; within a game, moments by ply (stable)."""
        game_order: Dict[int, int] = {}
        for ref in refs:
            game_order.setdefault(id(ref.game), len(game_order))

        def key(ref: MomentRef) -> Tuple[int, int]:
            path = decode_path(ref.path_key) or ()
            return (game_order[id(ref.game)], ply_for_path(self._pgn_of(ref.game, pgn_cache), path))

        return sorted(refs, key=key)

    # ------------------------------------------------------------------
    # Per moment
    # ------------------------------------------------------------------

    def _moment_lines(
        self,
        ref: MomentRef,
        pgn_cache: Dict[int, Optional[chess.pgn.Game]],
        entries_for: Optional[Callable[[MomentRef], List[Dict[str, Any]]]] = None,
    ) -> Optional[Tuple[List[str], List[str]]]:
        if entries_for is not None:
            source = entries_for(ref)
        else:
            source = self._controller.get_tags_for_game(ref.game).get(ref.path_key, [])
        entries = [e for e in source if e.get("preset", "") == ref.preset]
        if not entries:
            return None
        move_label = display_move_label(self._pgn_of(ref.game, pgn_cache), ref.path_key)
        if ref.preset == "3x3":
            return self._lines_3x3(move_label, entries)
        return self._lines_clamp_cct(move_label, ref.preset, entries)

    @staticmethod
    def _pgn_of(game, pgn_cache: Dict[int, Optional[chess.pgn.Game]]) -> Optional[chess.pgn.Game]:
        key = id(game)
        if key not in pgn_cache:
            pgn_game = None
            try:
                pgn = getattr(game, "pgn", None)
                if pgn:
                    pgn_game = chess.pgn.read_game(StringIO(pgn))
            except Exception:
                pgn_game = None
            pgn_cache[key] = pgn_game
        return pgn_cache[key]

    # ------------------------------------------------------------------
    # Per preset
    # ------------------------------------------------------------------

    def _markers(self, shallow: bool, vague: bool) -> List[str]:
        out: List[str] = []
        if shallow:
            out.append(self._svc.shallow_label)
        if vague:
            out.append(self._svc.vague_label)
        return out

    def _chips_html(self, shallow: bool, vague: bool) -> str:
        chips = []
        if shallow:
            chips.append(self._svc.shallow_chip_html())
        if vague:
            chips.append(self._svc.vague_chip_html())
        return "".join(f"&nbsp;{c}" for c in chips)

    def _lines_clamp_cct(
        self, move_label: str, preset: str, entries: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[str]]:
        cats = order_categories(preset, [e.get("cat", "") for e in entries if e.get("cat")])
        head = f"{move_label} — {' '.join(cats)}" if cats else move_label
        note = next(
            ((e.get("why") or "").strip() for e in entries if (e.get("why") or "").strip()),
            "",
        )
        shallow, vague, _, _ = moment_flags(preset, entries)
        plain = [head]
        html_parts = [f"<p><strong>{html.escape(head, quote=False)}</strong></p>"]
        if note:
            marks = "".join(f" [{m}]" for m in self._markers(shallow, vague))
            plain.append("  " + note.replace("\n", "\n  ") + marks)
            html_parts.append(f"<p>{_encode_text(note)}{self._chips_html(shallow, vague)}</p>")
        return plain, html_parts

    def _lines_3x3(
        self, move_label: str, entries: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[str]]:
        by_cat = {e.get("cat", ""): e for e in entries}
        plain = [move_label]
        html_parts = [f"<p><strong>{html.escape(move_label, quote=False)}</strong></p>"]
        for key in _WHY_KEYS:
            question = THREE_BY_THREE_PROMPTS.get(key, key)
            entry = by_cat.get(key, {})
            answer = (entry.get("why") or "").strip()
            shallow, vague = _answer_flags(entry) if answer else (False, False)
            marks = "".join(f" [{m}]" for m in self._markers(shallow, vague))
            body = answer.replace("\n", "\n    ")
            plain.append(f"  {question} {body}{marks}" if answer else f"  {question}")
            answer_html = f" {_encode_text(answer)}" if answer else ""
            html_parts.append(
                f"<p><strong>{html.escape(question, quote=False)}</strong>{answer_html}"
                f"{self._chips_html(shallow, vague)}</p>"
            )
        return plain, html_parts

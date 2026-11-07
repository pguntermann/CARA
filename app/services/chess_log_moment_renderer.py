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
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chess.pgn

from app.services.chess_log_html_service import ChessLogHTMLService, _encode_text
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.chess_log_preset_order import order_categories
from app.views.dialogs._tag_row_helpers import game_header_text, node_info

_WHY_KEYS = ("Why1", "Why2", "Why3", "Why4")
_WHOLE_GAME_LABEL = "Whole game"
_UNKNOWN_MOVE_LABEL = "Unknown move"


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


class ChessLogMomentRenderer:
    """Renders moments through *controller* (needs ``get_tags_for_game(game)``)."""

    def __init__(self, controller, config: Dict[str, Any]) -> None:
        self._controller = controller
        self._svc = ChessLogHTMLService(config)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self, refs: Iterable[MomentRef]) -> RenderedMoments:
        """Render *refs* in the given order, grouped under a header per game."""
        plain: List[str] = []
        html_parts: List[str] = []
        pgn_cache: Dict[int, Optional[chess.pgn.Game]] = {}
        current_game = None
        opened = False
        for ref in refs:
            moment = self._moment_lines(ref, pgn_cache)
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

    # ------------------------------------------------------------------
    # Per moment
    # ------------------------------------------------------------------

    def _moment_lines(
        self, ref: MomentRef, pgn_cache: Dict[int, Optional[chess.pgn.Game]]
    ) -> Optional[Tuple[List[str], List[str]]]:
        entries = [
            e for e in self._controller.get_tags_for_game(ref.game).get(ref.path_key, [])
            if e.get("preset", "") == ref.preset
        ]
        if not entries:
            return None
        move_label = self._move_label(ref, pgn_cache)
        if ref.preset == "3x3":
            return self._lines_3x3(move_label, entries)
        return self._lines_clamp_cct(move_label, ref.preset, entries)

    @staticmethod
    def _move_label(ref: MomentRef, pgn_cache: Dict[int, Optional[chess.pgn.Game]]) -> str:
        if not (ref.path_key or "").strip():
            return _WHOLE_GAME_LABEL
        key = id(ref.game)
        if key not in pgn_cache:
            pgn_game = None
            try:
                pgn = getattr(ref.game, "pgn", None)
                if pgn:
                    pgn_game = chess.pgn.read_game(StringIO(pgn))
            except Exception:
                pgn_game = None
            pgn_cache[key] = pgn_game
        _fen, _move, label, _black = node_info(pgn_cache[key], ref.path_key)
        # node_info returns the path key itself when the node cannot be located.
        return _UNKNOWN_MOVE_LABEL if label == ref.path_key else label

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
        shallow = vague = False
        for e in entries:
            s, v = _answer_flags(e)
            shallow, vague = shallow or s, vague or v
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
            entry = by_cat.get(key, {})
            answer = (entry.get("why") or "").strip()
            shallow, vague = _answer_flags(entry) if answer else (False, False)
            marks = "".join(f" [{m}]" for m in self._markers(shallow, vague))
            body = answer.replace("\n", "\n    ")
            plain.append(f"  {key}: {body}{marks}".rstrip() if answer else f"  {key}:")
            answer_html = f" {_encode_text(answer)}" if answer else ""
            html_parts.append(
                f"<p><strong>{key}:</strong>{answer_html}{self._chips_html(shallow, vague)}</p>"
            )
        return plain, html_parts

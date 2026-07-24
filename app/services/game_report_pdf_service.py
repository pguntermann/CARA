"""Compose printable game PDF reports (summary + annotated PGN with mini boards)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import chess
import chess.pgn
import io
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPdfWriter,
    QPen,
    QPixmap,
)

from app.models.database_model import GameData
from app.models.moveslist_model import MoveData
from app.services.game_summary_service import GameSummary
from app.services.pdf_report_base import BasePDFReportService
from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget

_ASSESSMENT_SYMBOLS: Dict[str, str] = {
    "Brilliant": "!!",
    "Best Move": "!",
    "Good Move": "",
    "Book Move": "",
    "Inaccuracy": "?!",
    "Mistake": "?",
    "Miss": "⁇",
    "Blunder": "??",
}

_CLASSIFICATION_ORDER = (
    "Book Move",
    "Brilliant",
    "Best Move",
    "Good Move",
    "Inaccuracy",
    "Mistake",
    "Miss",
    "Blunder",
)

# Miniatures for notable mistakes / brilliancies only — not Best/Good.
_DIAGRAM_MOVE_ASSESSMENTS = frozenset(
    {
        "Brilliant",
        "Inaccuracy",
        "Mistake",
        "Miss",
        "Blunder",
    }
)


@dataclass(frozen=True)
class _Ply:
    """One half-move in mainline order."""

    ply: int  # 1-based
    move_number: int
    is_white: bool
    san: str
    assessment: str
    evaluation: str
    best_move: str
    fen: str
    fen_before: str
    eco: str
    opening_name: str
    comment: str = ""


@dataclass(frozen=True)
class _Diagram:
    after_ply: int
    title: str  # headline: "Blunder", "Opening", "Final Position", "Comment", …
    move_label: str  # e.g. "36... Qxf3+"
    fen: str
    fen_before: str
    san: str
    evaluation: str = ""
    best_move: str = ""
    cpl: Optional[float] = None
    detail: str = ""  # optional second line (opening ECO · name, etc.)
    comment: str = ""  # PGN comment shown with text wrap


class GameReportPDFService(BasePDFReportService):
    """Build a multi-page PDF game report using Qt's QPdfWriter."""

    def __init__(self, config: Dict[str, Any]) -> None:
        report_cfg = (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("summary", {})
            .get("pdf_report", {})
        )
        if not isinstance(report_cfg, dict):
            report_cfg = {}
        super().__init__(config, report_cfg)

        colors = self._cfg.get("colors", {})
        if not isinstance(colors, dict):
            colors = {}
        assess = colors.get("assessments", {})
        if not isinstance(assess, dict):
            assess = {}
        self._assess_colors = {
            "Book Move": self._rgb(assess.get("book_move"), (128, 120, 110)),
            "Brilliant": self._rgb(assess.get("brilliant"), (208, 148, 38)),
            "Best Move": self._rgb(assess.get("best_move"), (32, 118, 88)),
            "Good Move": self._rgb(assess.get("good_move"), (70, 150, 185)),
            "Inaccuracy": self._rgb(assess.get("inaccuracy"), (200, 155, 25)),
            "Mistake": self._rgb(assess.get("mistake"), (210, 115, 45)),
            "Miss": self._rgb(assess.get("miss"), (150, 70, 160)),
            "Blunder": self._rgb(assess.get("blunder"), (185, 45, 50)),
        }
        self._pie_slice_border = self._rgb(
            colors.get("pie_slice_border"), (255, 255, 255)
        )
        self._pie_slice_border_width = float(
            self._cfg.get("pie_slice_border_width", 1.75)
        )

        self._font_move = QFont(self._font_body)
        self._board_size = int(self._cfg.get("board_size", 112))
        self._highlight_board_size = int(self._cfg.get("highlight_board_size", 72))
        self._board_render_scale = max(1, int(self._cfg.get("board_render_scale", 4)))
        self._max_comment_diagrams = max(0, int(self._cfg.get("max_comment_diagrams", 3)))
        self._include_symbols = bool(self._cfg.get("include_symbols", True))
        self._eval_chart_height = float(self._cfg.get("eval_chart_height", 110))
        self._pie_size = float(self._cfg.get("pie_size", 108))
        self._opening_repeat = str(
            config.get("resources", {}).get("opening_repeat_indicator", "*")
        )

        graph_colors = colors.get("eval_graph", {})
        if not isinstance(graph_colors, dict):
            graph_colors = {}
        self._graph_bg = self._rgb(graph_colors.get("background"), (255, 255, 255))
        self._graph_grid = self._rgb(graph_colors.get("grid"), (220, 224, 230))
        self._graph_axis = self._rgb(graph_colors.get("axis"), (120, 125, 135))
        self._graph_line = self._rgb(graph_colors.get("line"), (35, 80, 120))
        self._graph_zero = self._rgb(graph_colors.get("zero_line"), (160, 165, 175))
        self._graph_phase = self._rgb(graph_colors.get("phase_line"), (100, 140, 190))
        self._graph_border = self._rgb(graph_colors.get("border"), (200, 205, 210))

    def export(
        self,
        path: str | Path,
        *,
        summary: GameSummary,
        moves: Sequence[MoveData],
        game: Optional[GameData] = None,
        chart_image: Optional[QPixmap] = None,  # ignored; PDF draws its own light chart
    ) -> Path:
        """Write the PDF report to ``path`` and return the resolved path."""
        out = Path(path)
        if out.suffix.lower() != ".pdf":
            out = out.with_suffix(".pdf")

        writer = self._create_pdf_writer(out)
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("Could not start PDF painter")

        try:
            content = self._content_rect(writer)
            plies = self._plies_with_pgn_comments(self._build_plies(moves), game)
            diagrams = self._select_diagrams(summary, plies, game=game)
            white_name = (game.white.strip() if game and game.white else "") or "White"
            black_name = (game.black.strip() if game and game.black else "") or "Black"

            self._page_number = 1
            self._draw_page_chrome(painter, content)
            y = self._draw_summary_pages(
                painter,
                writer,
                content,
                summary=summary,
                moves=moves,
                game=game,
                white_name=white_name,
                black_name=black_name,
            )
            writer.newPage()
            self._page_number += 1
            self._draw_page_chrome(painter, content)
            self._draw_annotated_game(
                painter,
                writer,
                content,
                plies=plies,
                diagrams=diagrams,
                game=game,
            )
            _ = y
        finally:
            painter.end()

        return out

    # ------------------------------------------------------------------ plies / diagrams

    def _build_plies(self, moves: Sequence[MoveData]) -> List[_Ply]:
        plies: List[_Ply] = []
        prev_fen = chess.STARTING_FEN
        ply = 0
        for move in moves:
            white_comment, black_comment = self._split_row_comments(move)
            if move.white_move:
                ply += 1
                fen = (move.fen_white or "").strip() or prev_fen
                plies.append(
                    _Ply(
                        ply=ply,
                        move_number=int(move.move_number),
                        is_white=True,
                        san=str(move.white_move).strip(),
                        assessment=str(move.assess_white or "").strip(),
                        evaluation=str(move.eval_white or "").strip(),
                        best_move=str(move.best_white or "").strip(),
                        fen=fen,
                        fen_before=prev_fen,
                        eco=str(move.eco or "").strip(),
                        opening_name=str(move.opening_name or "").strip(),
                        comment=white_comment,
                    )
                )
                prev_fen = fen
            if move.black_move:
                ply += 1
                fen = (move.fen_black or "").strip() or prev_fen
                plies.append(
                    _Ply(
                        ply=ply,
                        move_number=int(move.move_number),
                        is_white=False,
                        san=str(move.black_move).strip(),
                        assessment=str(move.assess_black or "").strip(),
                        evaluation=str(move.eval_black or "").strip(),
                        best_move=str(move.best_black or "").strip(),
                        fen=fen,
                        fen_before=prev_fen,
                        eco=str(move.eco or "").strip(),
                        opening_name=str(move.opening_name or "").strip(),
                        comment=black_comment,
                    )
                )
                prev_fen = fen
        return plies

    @staticmethod
    def _split_row_comments(move: MoveData) -> Tuple[str, str]:
        """Map MoveData.comment onto white/black plies for this row."""
        raw = str(getattr(move, "comment", "") or "").strip()
        if not raw:
            return "", ""
        has_white = bool(str(getattr(move, "white_move", "") or "").strip())
        has_black = bool(str(getattr(move, "black_move", "") or "").strip())
        if has_white and has_black and "; " in raw:
            left, right = raw.split("; ", 1)
            return left.strip(), right.strip()
        if has_white and not has_black:
            return raw, ""
        if has_black and not has_white:
            return "", raw
        # Both sides present, single blob: usually White's comment (Black had none).
        # Prefer PGN overlay via ``_plies_with_pgn_comments`` when ``game`` is available.
        return raw, ""

    def _plies_with_pgn_comments(
        self, plies: Sequence[_Ply], game: Optional[GameData]
    ) -> List[_Ply]:
        """Re-attach comments per half-move from the PGN tree (source of truth).

        MoveData stores one row-level comment string, which cannot reliably tell
        White-only vs Black-only comments. PGN nodes keep them on the correct move
        (e.g. ``6. a4 {…} 6... b6`` → comment on a4).
        """
        if not plies or game is None or not (game.pgn or "").strip():
            return list(plies)
        try:
            chess_game = chess.pgn.read_game(io.StringIO(game.pgn))
        except Exception:
            return list(plies)
        if chess_game is None:
            return list(plies)

        from app.controllers.game_controller import (
            _comment_text_for_moves_list_display,
            _pgn_child_node_raw_comment,
        )

        pgn_comments: List[str] = []
        node: chess.pgn.GameNode = chess_game
        while node.variations:
            next_node = node.variation(0)
            raw = _pgn_child_node_raw_comment(next_node)
            pgn_comments.append(_comment_text_for_moves_list_display(raw))
            node = next_node

        if len(pgn_comments) != len(plies):
            return list(plies)

        return [
            replace(ply, comment=comment) if comment != ply.comment else ply
            for ply, comment in zip(plies, pgn_comments)
        ]

    def _select_diagrams(
        self,
        summary: GameSummary,
        plies: Sequence[_Ply],
        *,
        game: Optional[GameData] = None,
    ) -> List[_Diagram]:
        """Pick a small, high-signal set of miniatures for the annotated PGN.

        Always include opening and final position. Critical miniatures only for
        Brilliant / Inaccuracy / Mistake / Miss / Blunder (never Best or Good).
        Up to three spaced PGN comments get boards and replace any other miniature
        already chosen on the same ply.
        """
        if not plies:
            return []
        used: set[int] = set()
        diagrams: List[_Diagram] = []

        def add(diagram: _Diagram) -> None:
            if diagram.after_ply in used:
                return
            used.add(diagram.after_ply)
            diagrams.append(diagram)

        def add_or_replace(diagram: _Diagram) -> None:
            if diagram.after_ply in used:
                diagrams[:] = [d for d in diagrams if d.after_ply != diagram.after_ply]
                used.discard(diagram.after_ply)
            used.add(diagram.after_ply)
            diagrams.append(diagram)

        def from_ply(
            ply: _Ply,
            title: str,
            *,
            best_move: str = "",
            evaluation: Optional[str] = None,
            cpl: Optional[float] = None,
            detail: str = "",
            comment: str = "",
        ) -> _Diagram:
            return _Diagram(
                after_ply=ply.ply,
                title=title,
                move_label=self._move_label(ply),
                fen=ply.fen,
                fen_before=ply.fen_before,
                san=ply.san,
                evaluation=ply.evaluation if evaluation is None else evaluation,
                best_move=best_move,
                cpl=cpl,
                detail=detail,
                comment=comment or ply.comment,
            )

        # 1) Opening — where the final opening line was reached, with ECO/name.
        opening_ply = self._opening_diagram_ply(summary, plies)
        if opening_ply is not None:
            eco, name = self._opening_label_for_ply(plies, opening_ply, game=game)
            detail = self._format_opening_title(eco, name)
            if detail == "Opening":
                detail = ""
            add(
                from_ply(
                    opening_ply,
                    "Opening",
                    best_move="",
                    detail=detail,
                )
            )

        # 2) First blunder in the game.
        first_blunder = next((p for p in plies if p.assessment == "Blunder"), None)
        if first_blunder is not None:
            add(
                from_ply(
                    first_blunder,
                    "Blunder",
                    best_move=first_blunder.best_move,
                )
            )

        # 3) Overall top-3 worst among notable error assessments.
        for cm, is_white in self._top_critical(
            summary.white_top_worst, summary.black_top_worst, worst=True
        ):
            ply = self._find_ply_for_critical(plies, cm, is_white)
            if ply is None:
                continue
            assess = (cm.assessment or ply.assessment or "").strip()
            if assess not in _DIAGRAM_MOVE_ASSESSMENTS or assess == "Brilliant":
                continue
            add(
                from_ply(
                    ply,
                    f"Worst · {assess}",
                    best_move=cm.best_move or ply.best_move,
                    evaluation=cm.evaluation or ply.evaluation,
                    cpl=float(cm.cpl) if cm.cpl is not None else None,
                )
            )

        # 4) Brilliancies (never Best/Good miniatures).
        for ply in plies:
            if ply.assessment != "Brilliant":
                continue
            add(
                from_ply(
                    ply,
                    "Brilliant",
                    best_move=ply.best_move,
                )
            )

        # 5) Final position — always present (replaces a critical diagram on the last ply).
        last = plies[-1]
        prior = next((d for d in diagrams if d.after_ply == last.ply), None)
        if prior is not None:
            diagrams = [d for d in diagrams if d.after_ply != last.ply]
            used.discard(last.ply)
            add(
                _Diagram(
                    after_ply=last.ply,
                    title="Final Position",
                    move_label=self._move_label(last),
                    fen=last.fen,
                    fen_before=last.fen_before,
                    san=last.san,
                    evaluation=prior.evaluation or last.evaluation,
                    best_move=prior.best_move,
                    cpl=prior.cpl,
                    detail=(
                        prior.title
                        if prior.title not in ("Final Position", "Opening", "Comment")
                        else prior.detail
                    ),
                    comment=prior.comment or last.comment,
                )
            )
        else:
            add(from_ply(last, "Final Position", best_move=""))

        # 6) Spaced comment miniatures — replace any existing board on the same ply.
        for ply in self._select_spaced_comment_plies(plies, self._max_comment_diagrams):
            prior = next((d for d in diagrams if d.after_ply == ply.ply), None)
            title = "Final Position" if ply.ply == last.ply else "Comment"
            detail = ""
            if prior is not None:
                if prior.title not in ("Comment", "Final Position", "Opening"):
                    detail = prior.title
                elif prior.detail:
                    detail = prior.detail
            add_or_replace(
                from_ply(
                    ply,
                    title,
                    best_move=(prior.best_move if prior else ply.best_move) or ply.best_move,
                    evaluation=(
                        prior.evaluation
                        if prior and prior.evaluation
                        else ply.evaluation
                    ),
                    cpl=prior.cpl if prior else None,
                    detail=detail,
                    comment=ply.comment,
                )
            )

        diagrams.sort(key=lambda d: d.after_ply)
        return diagrams

    @staticmethod
    def _select_spaced_comment_plies(
        plies: Sequence[_Ply], count: int
    ) -> List[_Ply]:
        """Choose up to ``count`` commented plies spaced across the game."""
        if count <= 0:
            return []
        candidates = [p for p in plies if (p.comment or "").strip()]
        if not candidates:
            return []
        if len(candidates) <= count:
            return list(candidates)

        lo = float(candidates[0].ply)
        hi = float(candidates[-1].ply)
        span = max(1.0, hi - lo)
        chosen: List[_Ply] = []
        used_plies: set[int] = set()
        for i in range(count):
            target = lo + (i + 0.5) / float(count) * span
            best: Optional[_Ply] = None
            best_dist: Optional[float] = None
            for p in candidates:
                if p.ply in used_plies:
                    continue
                dist = abs(float(p.ply) - target)
                if best_dist is None or dist < best_dist:
                    best = p
                    best_dist = dist
            if best is None:
                break
            used_plies.add(best.ply)
            chosen.append(best)
        chosen.sort(key=lambda p: p.ply)
        return chosen

    @staticmethod
    def _top_critical(
        white: Sequence[Any],
        black: Sequence[Any],
        *,
        worst: bool,
        count: int = 3,
    ) -> List[Tuple[Any, bool]]:
        """Merge per-side critical lists into an overall top-N."""
        merged: List[Tuple[Any, bool]] = [(cm, True) for cm in (white or [])]
        merged.extend((cm, False) for cm in (black or []))
        merged.sort(key=lambda item: float(getattr(item[0], "cpl", 0.0)), reverse=worst)
        return merged[:count]

    @staticmethod
    def _find_ply_for_critical(
        plies: Sequence[_Ply], critical: Any, is_white: bool
    ) -> Optional[_Ply]:
        move_number = int(getattr(critical, "move_number", 0) or 0)
        notation = str(getattr(critical, "move_notation", "") or "")
        san = notation.split(" ", 1)[-1].strip() if notation else ""
        candidates = [
            p for p in plies if p.move_number == move_number and p.is_white == is_white
        ]
        if not candidates:
            return None
        if san:
            for p in candidates:
                if p.san == san:
                    return p
        return candidates[0]

    def _opening_diagram_ply(
        self, summary: GameSummary, plies: Sequence[_Ply]
    ) -> Optional[_Ply]:
        """Ply where the final opening line was reached.

        Prefer the last move that still carries a real ECO/name (not the ``*``
        repeat placeholder). That is when the opening identity last changed —
        not the last book move, which can be many plies later.
        """
        last_named: Optional[_Ply] = None
        last_book: Optional[_Ply] = None
        for p in plies:
            if p.assessment == "Book Move":
                last_book = p
            if self._is_real_opening_value(p.eco) or self._is_real_opening_value(
                p.opening_name
            ):
                last_named = p
        if last_named is not None:
            return last_named
        if last_book is not None:
            return last_book
        if summary.opening_end <= 0:
            return None
        target = summary.opening_end * 2
        found = next((p for p in plies if p.ply == target), None)
        if found is not None:
            return found
        return next(
            (p for p in plies if p.move_number == summary.opening_end and p.is_white),
            None,
        )

    def _is_real_opening_value(self, value: str) -> bool:
        """True if ``value`` is a real ECO/name (not empty or the repeat placeholder)."""
        text = (value or "").strip()
        if not text:
            return False
        if text == self._opening_repeat:
            return False
        return True

    @staticmethod
    def _format_opening_title(eco: str, name: str) -> str:
        if eco and name:
            return f"{eco} · {name}"
        if name:
            return name
        if eco:
            return eco
        return "Opening"

    def _opening_label_for_ply(
        self,
        plies: Sequence[_Ply],
        opening_ply: _Ply,
        *,
        game: Optional[GameData] = None,
    ) -> Tuple[str, str]:
        """Best ECO / opening name at or before the opening diagram ply.

        Move rows often store ``*`` (opening_repeat_indicator) when the opening
        is unchanged from the previous row — those placeholders are skipped.
        """
        eco = ""
        name = ""
        for p in plies:
            if p.ply > opening_ply.ply:
                break
            if self._is_real_opening_value(p.eco):
                eco = p.eco.strip()
            if self._is_real_opening_value(p.opening_name):
                name = p.opening_name.strip()
        if not eco and game is not None:
            header_eco = str(getattr(game, "eco", "") or "").strip()
            if self._is_real_opening_value(header_eco):
                eco = header_eco
        return eco, name

    @staticmethod
    def _move_label(ply: _Ply) -> str:
        if ply.is_white:
            return f"{ply.move_number}. {ply.san}"
        return f"{ply.move_number}... {ply.san}"

    # ------------------------------------------------------------------ drawing helpers

    def _phase_subheader_height(self) -> float:
        return float(QFontMetrics(self._font_body_bold).height()) + 6.0

    def _draw_phase_subheader(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        title: str,
        *,
        keep_with: float,
        top_gap: float = 0.0,
    ) -> float:
        """Draw a phase/group subheader kept on the same page as following content."""
        y, _ = self._ensure_space(
            painter,
            writer,
            content,
            y,
            top_gap + self._phase_subheader_height() + max(0.0, keep_with),
        )
        y += top_gap
        painter.setFont(self._font_body_bold)
        painter.setPen(self._muted)
        fm = QFontMetrics(self._font_body_bold)
        painter.drawText(int(content.left()), int(y + fm.ascent()), title)
        return y + fm.height() + 6.0

    def _elide(self, text: str, font: QFont, max_width: float) -> str:
        fm = QFontMetrics(font)
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, max(20, int(max_width)))

    def _fmt_pct(self, value: Optional[float]) -> str:
        return f"{value:.1f}%" if value is not None else "—"

    def _fmt_num(self, value: Optional[float], digits: int = 1) -> str:
        return f"{value:.{digits}f}" if value is not None else "—"

    def _draw_comparison_table(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        white_name: str,
        black_name: str,
        rows: Sequence[Tuple[str, str, str]],
        *,
        row_height: float = 14.0,
        x: Optional[float] = None,
        width: Optional[float] = None,
        zebra: Optional[QColor] = None,
        header_fill: Optional[QColor] = None,
    ) -> float:
        """Draw label | white | black comparison rows."""
        table_x = content.left() if x is None else float(x)
        table_w = content.width() if width is None else float(width)
        label_w = table_w * 0.36
        col_w = (table_w - label_w) / 2.0
        zebra_color = zebra if zebra is not None else QColor(250, 250, 252)
        head_fill = header_fill if header_fill is not None else self._card

        # Header
        painter.fillRect(QRectF(table_x, y, table_w, row_height), head_fill)
        painter.setFont(self._font_body)
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(table_x + label_w, y, col_w, row_height),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(white_name, self._font_body, col_w - 6),
        )
        painter.drawText(
            QRectF(table_x + label_w + col_w, y, col_w, row_height),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(black_name, self._font_body, col_w - 6),
        )
        y += row_height + 1

        for index, (label, white_val, black_val) in enumerate(rows):
            if index % 2 == 0:
                painter.fillRect(QRectF(table_x, y, table_w, row_height), zebra_color)
            painter.setFont(self._font_body)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(table_x + 4, y, label_w - 8, row_height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            painter.setPen(self._text)
            painter.drawText(
                QRectF(table_x + label_w, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                white_val,
            )
            painter.drawText(
                QRectF(table_x + label_w + col_w, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                black_val,
            )
            y += row_height
        return y + 6

    # ------------------------------------------------------------------ summary pages

    def _draw_summary_pages(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        *,
        summary: GameSummary,
        moves: Sequence[MoveData],
        game: Optional[GameData],
        white_name: str,
        black_name: str,
    ) -> float:
        y = content.top()
        y = self._draw_report_header(painter, content, y, game, white_name, black_name)

        y = self._draw_overview_card(painter, writer, content, y, summary, white_name, black_name, game)
        y = self._draw_evaluation_chart(painter, writer, content, y, summary)
        y = self._draw_classification_table(painter, writer, content, y, summary, white_name, black_name)
        y = self._draw_phase_table(painter, writer, content, y, summary, white_name, black_name)
        y = self._draw_highlights_block(painter, writer, content, y, summary, moves)
        y = self._draw_critical_block(painter, writer, content, y, summary, white_name, black_name)
        return y

    def _draw_report_header(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        game: Optional[GameData],
        white_name: str,
        black_name: str,
    ) -> float:
        """Title / meta / players on the left, CARA logo top-right."""
        has_logo = self._resolve_logo_file() is not None
        logo_size = self._logo_size if has_logo else 0.0
        gap = 12.0 if has_logo else 0.0
        text_width = max(120.0, content.width() - logo_size - gap)
        header_top = y

        y = self._draw_text_line(
            painter, self._title, content.left(), y, text_width, self._font_title, self._accent
        )
        y += 4

        meta_bits: List[str] = []
        if game:
            if game.event:
                meta_bits.append(str(game.event))
            if game.site:
                meta_bits.append(str(game.site))
            if game.date:
                meta_bits.append(str(game.date))
            if game.eco:
                meta_bits.append(f"ECO {game.eco}")
        if meta_bits:
            y = self._draw_text_line(
                painter,
                " · ".join(meta_bits),
                content.left(),
                y,
                text_width,
                self._font_caption,
                self._muted,
            )
            y += 2

        players = f"{white_name}"
        if game and game.white_elo:
            players += f" ({game.white_elo})"
        players += f"  —  {black_name}"
        if game and game.black_elo:
            players += f" ({game.black_elo})"
        if game and game.result:
            players += f"   [{game.result}]"
        # Same muted body style as the meta line (line 2).
        y = self._draw_text_line(
            painter, players, content.left(), y, text_width, self._font_caption, self._muted
        )

        if has_logo and logo_size > 0:
            logo_rect = QRectF(content.right() - logo_size, header_top, logo_size, logo_size)
            if self._draw_logo(painter, logo_rect):
                y = max(y, header_top + logo_size)

        return y + 10

    def _draw_overview_card(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        summary: GameSummary,
        white_name: str,
        black_name: str,
        game: Optional[GameData],
    ) -> float:
        """Overview card: accuracy hero row + merged KPI comparison table."""
        ws, bs = summary.white_stats, summary.black_stats
        kpi_rows = [
            ("Avg CPL", self._fmt_num(ws.average_cpl), self._fmt_num(bs.average_cpl)),
            ("Est. Elo", str(ws.estimated_elo if ws.estimated_elo is not None else "—"),
             str(bs.estimated_elo if bs.estimated_elo is not None else "—")),
            ("Total Moves", str(ws.total_moves or 0), str(bs.total_moves or 0)),
            ("Best Move %", self._fmt_pct(ws.best_move_percentage), self._fmt_pct(bs.best_move_percentage)),
            ("Top3-Move Accuracy", self._fmt_pct(ws.top3_move_percentage), self._fmt_pct(bs.top3_move_percentage)),
            ("Blunder Rate", self._fmt_pct(ws.blunder_rate), self._fmt_pct(bs.blunder_rate)),
        ]
        pad = 12.0
        accuracy_h = 58.0
        row_h = 14.0
        table_h = row_h * (len(kpi_rows) + 1) + 2
        card_h = pad + accuracy_h + 10 + table_h + pad

        y = self._section_heading(
            painter, writer, content, y, "Overview", keep_with=card_h
        )

        card = QRectF(content.left(), y, content.width(), card_h)
        painter.setPen(QPen(self._rule, 0.8))
        painter.setBrush(self._card)
        painter.drawRoundedRect(card, 6, 6)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        inner = card.adjusted(pad, pad, -pad, -pad)
        cursor = self._draw_accuracy_comparison(
            painter,
            QRectF(inner.left(), inner.top(), inner.width(), accuracy_h),
            white_name,
            black_name,
            summary,
            game,
        )
        cursor += 8
        # Slightly lighter zebra so the table reads inside the card fill.
        self._draw_comparison_table(
            painter,
            content,
            cursor,
            white_name,
            black_name,
            kpi_rows,
            row_height=row_h,
            x=inner.left(),
            width=inner.width(),
            zebra=QColor(255, 255, 255),
            header_fill=QColor(235, 238, 243),
        )
        return y + card_h + 12

    def _draw_accuracy_comparison(
        self,
        painter: QPainter,
        rect: QRectF,
        white_name: str,
        black_name: str,
        summary: GameSummary,
        game: Optional[GameData],
    ) -> float:
        """Centered White | result | Black accuracy hero row."""
        result = (game.result or "").strip() if game else ""
        show_result = result in {"1-0", "0-1", "1/2-1/2", "½-½"}
        result_w = 22.0 if show_result else 0.0
        divider_w = 12.0
        side_w = (rect.width() - divider_w - result_w * (2 if show_result else 0)) / 2.0

        x = rect.left()
        self._draw_accuracy_score(
            painter,
            QRectF(x, rect.top(), side_w, rect.height()),
            white_name,
            summary.white_stats,
            align=Qt.AlignmentFlag.AlignHCenter,
        )
        x += side_w

        if show_result:
            wp = "1" if result == "1-0" else ("0" if result == "0-1" else "½")
            bp = "0" if result == "1-0" else ("1" if result == "0-1" else "½")
            painter.setFont(self._font_heading)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(x, rect.top(), result_w, rect.height()),
                Qt.AlignmentFlag.AlignCenter,
                wp,
            )
            x += result_w

        # Vertical divider
        painter.setPen(QPen(self._rule, 1.0))
        painter.drawLine(
            int(x + divider_w / 2),
            int(rect.top() + 8),
            int(x + divider_w / 2),
            int(rect.bottom() - 8),
        )
        x += divider_w

        if show_result:
            painter.setFont(self._font_heading)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(x, rect.top(), result_w, rect.height()),
                Qt.AlignmentFlag.AlignCenter,
                bp,
            )
            x += result_w

        self._draw_accuracy_score(
            painter,
            QRectF(x, rect.top(), side_w, rect.height()),
            black_name,
            summary.black_stats,
            align=Qt.AlignmentFlag.AlignHCenter,
        )
        return rect.bottom()

    def _draw_accuracy_score(
        self,
        painter: QPainter,
        rect: QRectF,
        name: str,
        stats: Any,
        *,
        align: Qt.AlignmentFlag,
    ) -> None:
        accuracy = getattr(stats, "accuracy", None)
        book = getattr(stats, "book_moves", 0) or 0
        h_align = int(align) | Qt.AlignmentFlag.AlignTop

        painter.setFont(self._font_body)
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(rect.left(), rect.top(), rect.width(), 14),
            h_align,
            self._elide(name, self._font_body, rect.width() - 4),
        )

        painter.setFont(self._font_accuracy)
        painter.setPen(self._text)
        painter.drawText(
            QRectF(rect.left(), rect.top() + 16, rect.width(), 28),
            int(align) | Qt.AlignmentFlag.AlignVCenter,
            self._fmt_pct(accuracy),
        )

        painter.setFont(self._font_body)
        painter.setPen(self._muted)
        book_text = f"{book} book" if book else ""
        painter.drawText(
            QRectF(rect.left(), rect.top() + 44, rect.width(), 14),
            int(align) | Qt.AlignmentFlag.AlignTop,
            book_text,
        )

    @staticmethod
    def _classification_pie_data(stats: Any) -> Dict[str, int]:
        if stats is None:
            return {cat: 0 for cat in _CLASSIFICATION_ORDER}
        return {
            "Book Move": int(getattr(stats, "book_moves", 0) or 0),
            "Brilliant": int(getattr(stats, "brilliant_moves", 0) or 0),
            "Best Move": int(getattr(stats, "best_moves", 0) or 0),
            "Good Move": int(getattr(stats, "good_moves", 0) or 0),
            "Inaccuracy": int(getattr(stats, "inaccuracies", 0) or 0),
            "Mistake": int(getattr(stats, "mistakes", 0) or 0),
            "Miss": int(getattr(stats, "misses", 0) or 0),
            "Blunder": int(getattr(stats, "blunders", 0) or 0),
        }

    def _draw_pie_chart(self, painter: QPainter, rect: QRectF, data: Dict[str, int]) -> None:
        """Draw a move-classification pie into ``rect`` (PDF-native, not a widget grab)."""
        total = sum(int(v) for v in data.values())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if total <= 0:
            painter.setPen(QPen(self._rule, 1.0))
            painter.setBrush(self._card)
            painter.drawEllipse(rect)
            painter.setPen(self._muted)
            painter.setFont(self._font_caption)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "No data")
            painter.restore()
            return

        border_w = max(0.0, self._pie_slice_border_width)
        start_angle = 0  # Qt: 16ths of a degree; 0 = 3 o'clock, CCW
        for category in _CLASSIFICATION_ORDER:
            count = int(data.get(category, 0) or 0)
            if count <= 0:
                continue
            span = int(round((count / total) * 360 * 16))
            if span <= 0:
                continue
            color = self._assess_colors.get(category, self._muted)
            painter.setBrush(color)
            if border_w > 0:
                painter.setPen(QPen(self._pie_slice_border, border_w))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(rect, start_angle, span)
            start_angle += span
        painter.restore()

    def _draw_classification_legend(
        self, painter: QPainter, content: QRectF, y: float
    ) -> float:
        """Color key under the pies (shared by White/Black)."""
        swatch = 8.0
        gap_x = 12.0
        gap_y = 4.0
        row_h = 12.0
        text_gap = 4.0
        painter.setFont(self._font_caption)
        fm = QFontMetrics(self._font_caption)

        items: List[Tuple[str, QColor, float]] = []
        for cat in _CLASSIFICATION_ORDER:
            label_w = float(fm.horizontalAdvance(cat))
            items.append(
                (cat, self._assess_colors.get(cat, self._muted), swatch + text_gap + label_w)
            )

        x = content.left()
        row_y = y
        max_right = content.right()
        for cat, color, item_w in items:
            if x > content.left() and x + item_w > max_right:
                x = content.left()
                row_y += row_h + gap_y
            swatch_rect = QRectF(x, row_y + (row_h - swatch) / 2.0, swatch, swatch)
            painter.setPen(QPen(self._rule, 0.6))
            painter.setBrush(color)
            painter.drawRect(swatch_rect)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(x + swatch + text_gap, row_y, item_w - swatch - text_gap, row_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                cat,
            )
            x += item_w + gap_x
        return row_y + row_h + 8.0

    def _draw_classification_pies(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        white_name: str,
        black_name: str,
        white_data: Dict[str, int],
        black_data: Dict[str, int],
    ) -> float:
        """Draw White / Black pies side by side; returns y below the charts."""
        pie = max(64.0, min(self._pie_size, content.width() * 0.38))
        gap = 18.0
        col_w = (content.width() - gap) / 2.0
        name_h = 14.0
        for index, (name, data) in enumerate(
            ((white_name, white_data), (black_name, black_data))
        ):
            col_x = content.left() + index * (col_w + gap)
            painter.setFont(self._font_body)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(col_x, y, col_w, name_h),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                self._elide(name, self._font_body, col_w - 4),
            )
            pie_x = col_x + (col_w - pie) / 2.0
            pie_y = y + name_h + 4.0
            self._draw_pie_chart(painter, QRectF(pie_x, pie_y, pie, pie), data)
        return y + name_h + 4.0 + pie + 8.0

    def _draw_classification_table(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        summary: GameSummary,
        white_name: str,
        black_name: str,
    ) -> float:
        ws, bs = summary.white_stats, summary.black_stats
        white_data = self._classification_pie_data(ws)
        black_data = self._classification_pie_data(bs)
        rows = [
            (cat, str(white_data[cat]), str(black_data[cat]))
            for cat in _CLASSIFICATION_ORDER
        ]
        pie = max(64.0, min(self._pie_size, content.width() * 0.38))
        # names + pies + ~2 legend rows + table (kept with the section heading)
        body = 18 + pie + 8 + 36 + 17 * (len(rows) + 1)
        y = self._section_heading(
            painter, writer, content, y, "Move Classification", keep_with=body
        )
        y = self._draw_classification_pies(
            painter, content, y, white_name, black_name, white_data, black_data
        )
        y = self._draw_classification_legend(painter, content, y)
        return self._draw_comparison_table(painter, content, y, white_name, black_name, rows)

    def _draw_phase_table(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        summary: GameSummary,
        white_name: str,
        black_name: str,
    ) -> float:
        def phase_vals(phase_w: Any, phase_b: Any) -> Tuple[str, str]:
            def one(p: Any) -> str:
                if p is None or getattr(p, "moves", 0) == 0:
                    return "—"
                acc = self._fmt_pct(getattr(p, "accuracy", None))
                cpl = self._fmt_num(getattr(p, "average_cpl", None))
                return f"{acc} / {cpl}"
            return one(phase_w), one(phase_b)

        open_w, open_b = phase_vals(summary.white_opening, summary.black_opening)
        mid_w, mid_b = phase_vals(summary.white_middlegame, summary.black_middlegame)
        end_w, end_b = phase_vals(summary.white_endgame, summary.black_endgame)
        open_label = f"Opening (..{summary.opening_end})" if summary.opening_end else "Opening"
        mid_label = f"Middlegame (..{summary.middlegame_end})" if summary.middlegame_end else "Middlegame"
        end_label = f"Endgame ({summary.endgame_type})" if summary.endgame_type else "Endgame"
        rows = [
            (open_label, open_w, open_b),
            (mid_label, mid_w, mid_b),
            (end_label, end_w, end_b),
        ]
        body = 14 + 17 * (len(rows) + 1)
        y = self._section_heading(
            painter, writer, content, y, "Phase Analysis", keep_with=body
        )
        painter.setFont(self._font_caption)
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(content.left(), y, content.width(), 12),
            Qt.AlignmentFlag.AlignLeft,
            "Values: Accuracy / ACPL",
        )
        y += 14
        return self._draw_comparison_table(painter, content, y, white_name, black_name, rows)

    def _draw_highlights_block(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        summary: GameSummary,
        moves: Sequence[MoveData],
    ) -> float:
        """Game Highlights as compact board cards (PDF analogue of summary Cards view)."""
        highlights = summary.highlights or []
        if not highlights:
            return y

        seen = set()
        unique = []
        for h in highlights:
            key = (h.move_notation, h.description)
            if key in seen:
                continue
            seen.add(key)
            unique.append(h)

        opening_end = int(summary.opening_end or 0)
        middlegame_end = int(summary.middlegame_end or 0)
        opening = [h for h in unique if h.move_number <= opening_end]
        middlegame = [
            h for h in unique if opening_end < h.move_number < middlegame_end
        ]
        endgame = [h for h in unique if h.move_number >= middlegame_end]
        phases = (
            ("Opening", opening),
            ("Middlegame", middlegame),
            ("Endgame", endgame),
        )
        if not any(items for _, items in phases):
            return y

        moves_by_number = {
            int(m.move_number): m for m in moves if getattr(m, "move_number", None) is not None
        }
        board_display = float(self._highlight_board_size)
        card_gap = 8.0
        first_phase = next((items for _, items in phases if items), None)
        first_keep = (
            self._phase_subheader_height()
            + self._highlight_card_height(
                first_phase[0], content.width(), board_display=board_display
            )
            if first_phase
            else board_display + 24.0
        )
        y = self._section_heading(
            painter, writer, content, y, "Game Highlights", keep_with=first_keep
        )

        for phase_idx, (phase_name, phase_items) in enumerate(phases):
            if not phase_items:
                continue
            first_card_h = self._highlight_card_height(
                phase_items[0], content.width(), board_display=board_display
            )
            y = self._draw_phase_subheader(
                painter,
                writer,
                content,
                y,
                phase_name,
                keep_with=first_card_h,
                top_gap=6.0 if phase_idx > 0 else 0.0,
            )

            for highlight in phase_items:
                y = self._draw_highlight_card(
                    painter,
                    writer,
                    content,
                    y,
                    highlight,
                    moves_by_number,
                    board_display=board_display,
                )
                y += card_gap

        return y + 4

    def _highlight_card_height(
        self,
        highlight: Any,
        content_width: float,
        *,
        board_display: float,
    ) -> float:
        """Estimate height of a highlight card (for keep-with-next paging)."""
        gap = 10.0
        pad = 6.0
        text_x_pad = board_display + gap + pad
        caption_w = max(80.0, content_width - text_x_pad - pad)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | Qt.TextFlag.TextWordWrap
        move_text = str(getattr(highlight, "move_notation", "") or "").strip() or "—"
        description = str(getattr(highlight, "description", "") or "").strip()
        move_bound = QFontMetrics(self._font_body_bold).boundingRect(
            QRectF(0, 0, caption_w, 80).toRect(), flags, move_text
        )
        text_h = float(move_bound.height())
        if description:
            desc_bound = QFontMetrics(self._font_body).boundingRect(
                QRectF(0, 0, caption_w, 400).toRect(), flags, description
            )
            text_h += 4.0 + float(desc_bound.height())
        return max(board_display, text_h) + pad * 2

    def _fen_before_after_for_highlight(
        self,
        highlight: Any,
        moves_by_number: Dict[int, MoveData],
    ) -> Tuple[str, str, str]:
        """Return (fen_after, fen_before, san) for a highlight's primary half-move."""
        md = moves_by_number.get(int(highlight.move_number))
        if md is None:
            return "", "", ""
        if highlight.is_white:
            fen_after = (md.fen_white or "").strip()
            san = (md.white_move or "").strip()
            if int(highlight.move_number) <= 1:
                fen_before = chess.STARTING_FEN
            else:
                prev = moves_by_number.get(int(highlight.move_number) - 1)
                fen_before = (
                    (prev.fen_black if prev and prev.fen_black else "") or chess.STARTING_FEN
                )
        else:
            fen_after = (md.fen_black or "").strip()
            san = (md.black_move or "").strip()
            fen_before = (md.fen_white or "").strip() or chess.STARTING_FEN
        return fen_after, fen_before, san

    def _draw_highlight_card(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        highlight: Any,
        moves_by_number: Dict[int, MoveData],
        *,
        board_display: float,
    ) -> float:
        """One compact highlight card: mini board left, move + description right."""
        fen_after, fen_before, san = self._fen_before_after_for_highlight(
            highlight, moves_by_number
        )
        gap = 10.0
        pad = 6.0
        text_x_pad = board_display + gap + pad
        caption_w = max(80.0, content.width() - text_x_pad - pad)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | Qt.TextFlag.TextWordWrap

        move_text = str(getattr(highlight, "move_notation", "") or "").strip() or "—"
        description = str(getattr(highlight, "description", "") or "").strip()

        painter.setFont(self._font_body_bold)
        move_bound = painter.boundingRect(QRectF(0, 0, caption_w, 80), flags, move_text)
        painter.setFont(self._font_body)
        desc_bound = (
            painter.boundingRect(QRectF(0, 0, caption_w, 400), flags, description)
            if description
            else QRectF()
        )
        text_h = float(move_bound.height()) + (4.0 + float(desc_bound.height()) if description else 0.0)
        card_h = max(board_display, text_h) + pad * 2
        y, _ = self._ensure_space(painter, writer, content, y, card_h + 4)

        card = QRectF(content.left(), y, content.width(), card_h)
        painter.setPen(QPen(self._rule, 0.7))
        painter.setBrush(self._card)
        painter.drawRoundedRect(card, 4, 4)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        board_y = y + pad
        if fen_after:
            board = self._render_board(
                fen_after,
                fen_before,
                san,
                size=int(board_display),
            )
            scale = float(self._board_render_scale)
            bw = float(board.width()) / scale
            bh = float(board.height()) / scale
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(
                QRectF(content.left() + pad, board_y, bw, bh),
                board,
                QRectF(0, 0, board.width(), board.height()),
            )
            painter.restore()
        else:
            painter.setPen(self._muted)
            painter.setFont(self._font_caption)
            painter.drawText(
                QRectF(content.left() + pad, board_y, board_display, board_display),
                int(Qt.AlignmentFlag.AlignCenter),
                "No board",
            )

        text_x = content.left() + pad + board_display + gap
        ty = y + pad
        painter.setFont(self._font_body_bold)
        painter.setPen(self._text)
        painter.drawText(
            QRectF(text_x, ty, caption_w, move_bound.height() + 4),
            flags,
            move_text,
        )
        ty += float(move_bound.height()) + 4
        if description:
            painter.setFont(self._font_body)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(text_x, ty, caption_w, desc_bound.height() + 4),
                flags,
                description,
            )
        return y + card_h

    def _draw_critical_block(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        summary: GameSummary,
        white_name: str,
        black_name: str,
    ) -> float:
        """Critical Moments as two player columns (lists), not a cramped 2×2 table."""
        white_worst = list(summary.white_top_worst or [])[:3]
        white_best = list(summary.white_top_best or [])[:3]
        black_worst = list(summary.black_top_worst or [])[:3]
        black_best = list(summary.black_top_best or [])[:3]
        if not (white_worst or white_best or black_worst or black_best):
            return y

        gap = 14.0
        col_w = (content.width() - gap) / 2.0
        # Estimate height from line counts so we page-break before drawing.
        line_h = float(QFontMetrics(self._font_body).height()) + 2.0
        sub_h = float(QFontMetrics(self._font_caption).height()) + 1.0
        header_h = float(QFontMetrics(self._font_body_bold).height()) + 8.0

        def column_height(worst: List[Any], best: List[Any]) -> float:
            h = header_h + 4.0
            for group in (worst, best):
                h += line_h + 4.0  # group title
                for m in group:
                    h += line_h
                    if getattr(m, "best_move", None):
                        h += sub_h
                    h += 3.0
                h += 8.0
            return h

        need = max(
            column_height(white_worst, white_best),
            column_height(black_worst, black_best),
        )
        y = self._section_heading(
            painter, writer, content, y, "Critical Moments", keep_with=need
        )

        y_white = self._draw_critical_player_column(
            painter,
            content.left(),
            y,
            col_w,
            white_name,
            white_worst,
            white_best,
            is_white=True,
        )
        y_black = self._draw_critical_player_column(
            painter,
            content.left() + col_w + gap,
            y,
            col_w,
            black_name,
            black_worst,
            black_best,
            is_white=False,
        )
        return max(y_white, y_black) + 4

    def _critical_move_label(self, move: Any, *, is_white: bool) -> str:
        notation = str(getattr(move, "move_notation", "") or "").strip()
        move_number = int(getattr(move, "move_number", 0) or 0)
        san = notation.split(" ", 1)[-1].strip() if notation else ""
        if move_number and san:
            return f"{move_number}. {san}" if is_white else f"{move_number}... {san}"
        return notation or "—"

    def _draw_critical_player_column(
        self,
        painter: QPainter,
        x: float,
        y: float,
        width: float,
        player_name: str,
        top_worst: Sequence[Any],
        top_best: Sequence[Any],
        *,
        is_white: bool,
    ) -> float:
        """One player's worst/best lists stacked vertically."""
        pad = 6.0
        inner_w = max(40.0, width - pad * 2)

        # Player header bar
        header_h = float(QFontMetrics(self._font_body_bold).height()) + 8.0
        painter.fillRect(QRectF(x, y, width, header_h), self._card)
        painter.setFont(self._font_body_bold)
        painter.setPen(self._text)
        painter.drawText(
            QRectF(x + pad, y, inner_w, header_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(player_name, self._font_body_bold, inner_w),
        )
        y += header_h + 6.0

        groups = (
            ("Worst moves", top_worst, True),
            ("Best moves", top_best, False),
        )
        for group_idx, (title, moves, show_best_alt) in enumerate(groups):
            if group_idx > 0:
                y += 6.0
            painter.setFont(self._font_body_bold)
            painter.setPen(self._muted)
            fm = QFontMetrics(self._font_body_bold)
            painter.drawText(int(x + pad), int(y + fm.ascent()), title)
            y += fm.height() + 4.0

            if not moves:
                painter.setFont(self._font_caption)
                painter.setPen(self._muted)
                cfm = QFontMetrics(self._font_caption)
                painter.drawText(int(x + pad), int(y + cfm.ascent()), "—")
                y += cfm.height() + 2.0
                continue

            for i, move in enumerate(moves, 1):
                if not move:
                    continue
                notation = self._critical_move_label(move, is_white=is_white)
                assessment = str(getattr(move, "assessment", "") or "").strip() or "—"
                cpl = getattr(move, "cpl", None)
                cpl_s = f"{cpl:.0f}" if cpl is not None else "—"
                best_alt = str(getattr(move, "best_move", "") or "").strip()

                # Rank + move
                painter.setFont(self._font_body)
                painter.setPen(self._text)
                fm = QFontMetrics(self._font_body)
                painter.drawText(
                    int(x + pad),
                    int(y + fm.ascent()),
                    f"{i}. {notation}",
                )
                y += fm.height() + 1.0

                # Assessment · CPL (colored by assessment when known)
                meta = f"{assessment} · CPL {cpl_s}"
                painter.setFont(self._font_caption)
                color = self._assess_colors.get(assessment, self._muted)
                painter.setPen(color)
                cfm = QFontMetrics(self._font_caption)
                painter.drawText(int(x + pad + 10), int(y + cfm.ascent()), meta)
                y += cfm.height() + 1.0

                if show_best_alt and best_alt:
                    painter.setPen(self._muted)
                    painter.drawText(
                        int(x + pad + 10),
                        int(y + cfm.ascent()),
                        f"Best: {best_alt}",
                    )
                    y += cfm.height() + 1.0
                y += 3.0

        return y

    def _draw_evaluation_chart(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        summary: GameSummary,
    ) -> float:
        """Draw a print-friendly evaluation chart (light theme, near Overview)."""
        data = list(summary.evaluation_data or [])
        if not data:
            return y

        chart_h = self._eval_chart_height
        y = self._section_heading(
            painter, writer, content, y, "Evaluation", keep_with=chart_h
        )

        rect = QRectF(content.left(), y, content.width(), chart_h)
        painter.setPen(QPen(self._graph_border, 0.8))
        painter.setBrush(self._graph_bg)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        pad_l, pad_t, pad_r, pad_b = 28.0, 8.0, 10.0, 18.0
        left = rect.left() + pad_l
        top = rect.top() + pad_t
        right = rect.right() - pad_r
        bottom = rect.bottom() - pad_b
        gw = max(1.0, right - left)
        gh = max(1.0, bottom - top)

        # Scale: symmetric around 0, capped at ±10 pawns.
        vals = [float(v) for _, v in data]
        max_abs = max(abs(min(vals)), abs(max(vals)), 100.0)
        max_abs = min(max_abs, 1000.0)
        if max_abs < 150.0:
            max_abs = 150.0

        def y_for(cp: float) -> float:
            cp = max(-max_abs, min(max_abs, cp))
            return top + gh / 2.0 - (cp / max_abs) * (gh / 2.0)

        max_ply = max(int(p) for p, _ in data)
        max_ply = max(1, max_ply)

        def x_for(ply: int) -> float:
            return left + (float(ply) / float(max_ply)) * gw

        # Grid + zero line
        painter.setPen(QPen(self._graph_grid, 0.7))
        for pawns in (-5, -2, 2, 5):
            cp = pawns * 100.0
            if abs(cp) <= max_abs:
                yy = y_for(cp)
                painter.drawLine(int(left), int(yy), int(right), int(yy))
        painter.setPen(QPen(self._graph_zero, 1.0))
        zero_y = y_for(0.0)
        painter.drawLine(int(left), int(zero_y), int(right), int(zero_y))

        # Phase boundaries (move number → approximate ply)
        painter.setPen(QPen(self._graph_phase, 1.0, Qt.PenStyle.DashLine))
        for move_end in (summary.opening_end, summary.middlegame_end):
            if move_end and move_end > 0:
                ply = min(max_ply, int(move_end) * 2)
                xx = x_for(ply)
                painter.drawLine(int(xx), int(top), int(xx), int(bottom))

        # Eval polyline
        points = sorted(data, key=lambda t: t[0])
        painter.setPen(QPen(self._graph_line, 1.6))
        prev = None
        for ply, cp in points:
            pt = (x_for(int(ply)), y_for(float(cp)))
            if prev is not None:
                painter.drawLine(int(prev[0]), int(prev[1]), int(pt[0]), int(pt[1]))
            prev = pt

        # Axis labels (same body font as the rest of the report)
        painter.setFont(self._font_body)
        painter.setPen(self._graph_axis)
        fm = QFontMetrics(self._font_body)
        for pawns, label in ((int(max_abs / 100), f"+{max_abs/100:.0f}"), (0, "0"), (-int(max_abs / 100), f"-{max_abs/100:.0f}")):
            cp = pawns * 100.0
            yy = y_for(cp)
            tw = fm.horizontalAdvance(label)
            painter.drawText(int(left - tw - 4), int(yy + fm.ascent() / 2), label)

        # X labels: start / mid / end as full-move numbers (data is ply-indexed)
        def move_label_for_ply(ply: int) -> str:
            return str((int(ply) + 1) // 2)

        for ply in (0, max_ply // 2, max_ply):
            xx = x_for(ply)
            label = move_label_for_ply(ply)
            tw = fm.horizontalAdvance(label)
            painter.drawText(int(xx - tw / 2), int(bottom + fm.ascent() + 2), label)

        return y + chart_h + 10

    # ------------------------------------------------------------------ annotated game

    def _draw_annotated_game(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        *,
        plies: Sequence[_Ply],
        diagrams: Sequence[_Diagram],
        game: Optional[GameData],
    ) -> None:
        y = content.top()
        y = self._section_heading(
            painter, writer, content, y, "Annotated Game", keep_with=48.0
        )

        if game:
            headers = []
            for label, value in (
                ("Event", game.event),
                ("Site", game.site),
                ("Date", game.date),
                ("White", game.white),
                ("Black", game.black),
                ("Result", game.result),
                ("ECO", game.eco),
            ):
                if value:
                    headers.append(f'[{label} "{value}"]')
            if headers:
                line_h = float(QFontMetrics(self._font_caption).height()) + 1.0
                y, _ = self._ensure_space(
                    painter, writer, content, y, line_h * len(headers) + 8
                )
                for tag in headers:
                    y, _ = self._ensure_space(painter, writer, content, y, line_h)
                    y = self._draw_text_line(
                        painter,
                        tag,
                        content.left(),
                        y,
                        content.width(),
                        self._font_caption,
                        self._muted,
                    )
                y += 8

        by_ply = {d.after_ply: d for d in diagrams}
        x = content.left()
        line_height = QFontMetrics(self._font_move).height() + 3
        max_x = content.right()

        for ply in plies:
            tw = self._ply_token_width(ply)
            if x > content.left() and x + tw > max_x:
                x = content.left()
                y += line_height
            y, new_page = self._ensure_space(painter, writer, content, y, line_height + 4)
            if new_page:
                x = content.left()
            x = self._draw_ply_token(painter, x, y, ply)

            diagram = by_ply.get(ply.ply)
            if diagram is not None:
                x = content.left()
                y += line_height + 8
                y = self._draw_diagram(painter, writer, content, y, diagram)

        if game and game.result:
            y += line_height + 6
            y, _ = self._ensure_space(painter, writer, content, y, line_height)
            painter.setFont(self._font_body_bold)
            painter.setPen(self._text)
            painter.drawText(
                int(content.left()),
                int(y + QFontMetrics(self._font_body_bold).ascent()),
                str(game.result),
            )

    def _ply_move_text(self, ply: _Ply) -> str:
        symbol = _ASSESSMENT_SYMBOLS.get(ply.assessment, "") if self._include_symbols else ""
        return f"{ply.san}{symbol}"

    def _ply_token_width(self, ply: _Ply) -> float:
        move_fm = QFontMetrics(self._font_move)
        move_w = float(move_fm.horizontalAdvance(self._ply_move_text(ply) + "  "))
        if not ply.is_white:
            return move_w
        num_fm = QFontMetrics(self._font_body_bold)
        return float(num_fm.horizontalAdvance(f"{ply.move_number}. ")) + move_w

    def _draw_ply_token(self, painter: QPainter, x: float, y: float, ply: _Ply) -> float:
        """Draw one ply; move numbers stay bold + neutral, SAN uses assessment color."""
        move_text = self._ply_move_text(ply)
        color = self._assess_colors.get(ply.assessment, self._text)
        baseline = y + QFontMetrics(self._font_move).ascent()
        if ply.is_white:
            num = f"{ply.move_number}. "
            painter.setFont(self._font_body_bold)
            painter.setPen(self._text)
            painter.drawText(int(x), int(baseline), num)
            x += QFontMetrics(self._font_body_bold).horizontalAdvance(num)
        painter.setFont(self._font_move)
        painter.setPen(color if ply.assessment in self._assess_colors else self._text)
        painter.drawText(int(x), int(baseline), move_text)
        x += QFontMetrics(self._font_move).horizontalAdvance(move_text + "  ")
        return x

    def _draw_diagram(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        diagram: _Diagram,
    ) -> float:
        board = self._render_board(diagram.fen, diagram.fen_before, diagram.san)
        scale = float(self._board_render_scale)
        board_w = float(board.width()) / scale
        board_h = float(board.height()) / scale

        gap = 12.0
        caption_w = max(120.0, content.width() - board_w - gap)
        caption_x = content.left() + board_w + gap
        lines = self._diagram_caption_lines(diagram)
        line_gap = 3.0
        caption_h = 0.0
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | Qt.TextFlag.TextWordWrap
        wrap_h = 1200.0
        for font, _color, text in lines:
            painter.setFont(font)
            fm = QFontMetrics(font)
            bound = painter.boundingRect(QRectF(0, 0, caption_w, wrap_h), flags, text)
            caption_h += max(float(fm.height()), float(bound.height())) + line_gap
        if caption_h > 0:
            caption_h -= line_gap

        block_h = max(board_h, caption_h) + 10
        y, _ = self._ensure_space(painter, writer, content, y, block_h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(
            QRectF(content.left(), y, board_w, board_h),
            board,
            QRectF(0, 0, board.width(), board.height()),
        )
        painter.restore()

        cy = y + 2.0
        for font, color, text in lines:
            painter.setFont(font)
            painter.setPen(color)
            fm = QFontMetrics(font)
            bound = painter.boundingRect(QRectF(0, 0, caption_w, wrap_h), flags, text)
            line_h = max(float(fm.height()), float(bound.height()))
            painter.drawText(QRectF(caption_x, cy, caption_w, line_h + 4), flags, text)
            cy += line_h + line_gap
        return y + block_h + 8

    def _diagram_caption_lines(
        self, diagram: _Diagram
    ) -> List[Tuple[QFont, QColor, str]]:
        """Structured caption: headline → detail → move → comment → metrics → best."""
        lines: List[Tuple[QFont, QColor, str]] = []
        if diagram.title:
            lines.append((self._font_body_bold, self._text, diagram.title))
        if diagram.detail:
            lines.append((self._font_body, self._text, diagram.detail))
        if diagram.move_label:
            lines.append((self._font_body, self._text, diagram.move_label))

        comment = (diagram.comment or "").strip()
        if comment:
            # Normalize whitespace but keep paragraph breaks for readability.
            comment = "\n".join(
                " ".join(part.split()) for part in comment.replace("\r\n", "\n").split("\n")
            ).strip()
            if comment:
                lines.append((self._font_body, self._text, comment))

        metrics: List[str] = []
        eval_text = (diagram.evaluation or "").strip()
        if eval_text:
            metrics.append(f"Eval {eval_text}")
        if diagram.cpl is not None:
            metrics.append(f"CPL {diagram.cpl:.0f}")
        if metrics:
            lines.append((self._font_caption, self._muted, " · ".join(metrics)))

        best = (diagram.best_move or "").strip()
        if best:
            lines.append((self._font_caption, self._muted, f"Best: {best}"))
        return lines

    def _render_board(
        self,
        fen: str,
        fen_before: str,
        san: str,
        *,
        size: Optional[int] = None,
    ) -> QPixmap:
        """Rasterize a mini board at supersampled size for sharp PDF embedding."""
        scale = self._board_render_scale
        board_size = int(size if size is not None else self._board_size)
        widget = MiniChessBoardWidget(
            self.config,
            fen or chess.STARTING_FEN,
            embedded=True,
            size_override=int(board_size * scale),
        )
        if fen_before and san:
            try:
                board = chess.Board(fen_before)
                move = board.parse_san(san)
                widget.set_move(move, True)
            except Exception:
                pass
        widget_size = widget.size()
        image = QImage(widget_size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.white)
        widget.render(image)
        return QPixmap.fromImage(image)


def default_pdf_filename(game: Optional[GameData] = None) -> str:
    """Suggest a download filename for the report."""
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    white = (game.white or "White").strip().replace(" ", "_") if game else "White"
    black = (game.black or "Black").strip().replace(" ", "_") if game else "Black"
    # Keep filesystem-friendly.
    for ch in '/\\:*?"<>|':
        white = white.replace(ch, "")
        black = black.replace(ch, "")
    return f"CARA-Report-{white}-vs-{black}-{stamp}.pdf"

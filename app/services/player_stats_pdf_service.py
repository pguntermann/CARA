"""Compose printable player-statistics PDF reports (profile-aware sections)."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap

from app.services.opening_service import OpeningService
from app.services.pdf_report_base import BasePDFReportService
from app.utils.player_stats_text_formatter import PlayerStatsTextFormatter
from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget

try:
    import chess
except ImportError:  # pragma: no cover
    chess = None  # type: ignore

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


class PlayerStatsPDFService(BasePDFReportService):
    """Build a multi-page PDF player-stats report using Qt's QPdfWriter."""

    def __init__(self, config: Dict[str, Any]) -> None:
        report_cfg = (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
            .get("pdf_report", {})
        )
        if not isinstance(report_cfg, dict):
            report_cfg = {}
        super().__init__(config, report_cfg)
        self._chart_height = float(self._cfg.get("chart_height", 96))
        self._move_quality_chart_height = float(
            self._cfg.get("move_quality_chart_height", self._chart_height)
        )
        self._acpl_phase_chart_height = float(
            self._cfg.get("acpl_phase_chart_height", self._move_quality_chart_height)
        )
        self._heatmap_cell = float(self._cfg.get("heatmap_cell_size", 10))
        self._max_opening_rows = max(1, int(self._cfg.get("max_opening_rows", 12)))
        self._max_tree_rows = max(1, int(self._cfg.get("max_tree_rows", 40)))
        self._max_error_patterns = max(1, int(self._cfg.get("max_error_patterns", 12)))
        self._max_significant_moves = max(
            1, int(self._cfg.get("max_significant_moves_per_category", 5))
        )
        self._pie_size = float(self._cfg.get("pie_size", 108))
        self._pie_slice_border_width = float(self._cfg.get("pie_slice_border_width", 1.75))
        self._opening_board_size = float(self._cfg.get("opening_board_size", 72))
        self._significant_move_board_size = float(
            self._cfg.get(
                "significant_move_board_size",
                min(64.0, self._opening_board_size),
            )
        )
        self._board_render_scale = max(1, int(self._cfg.get("board_render_scale", 4)))
        self._opening_service: Optional[OpeningService] = None

        # Assessment colors: prefer summary pdf_report (shared with game report look)
        summary_pdf = (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("summary", {})
            .get("pdf_report", {})
        )
        colors = {}
        if isinstance(summary_pdf, dict):
            colors = summary_pdf.get("colors", {}) or {}
        assess = colors.get("assessments", {}) if isinstance(colors, dict) else {}
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
            colors.get("pie_slice_border") if isinstance(colors, dict) else None,
            (255, 255, 255),
        )

        # Severity colors: same source as Player Stats error-pattern indicators
        ep_cfg = (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
            .get("error_patterns", {})
        )
        sev = {}
        if isinstance(ep_cfg, dict):
            sev = (
                (ep_cfg.get("severity_indicator") or {}).get("colors") or {}
            )
        if not isinstance(sev, dict):
            sev = {}
        self._severity_colors = {
            "critical": self._rgb(sev.get("critical"), (255, 100, 100)),
            "high": self._rgb(sev.get("high"), (255, 150, 100)),
            "moderate": self._rgb(sev.get("moderate"), (255, 200, 100)),
            "low": self._rgb(sev.get("low"), (200, 200, 100)),
            "default": self._rgb(sev.get("default"), (150, 150, 150)),
        }

    def export(
        self,
        path: str | Path,
        *,
        stats: Any,
        patterns: Sequence[Any],
        player_name: str,
        section_visibility: Optional[Dict[str, bool]] = None,
        profile_name: Optional[str] = None,
        top_games_summary: Optional[
            Tuple[int, Optional[float], Optional[float], int, Optional[float], Optional[float]]
        ] = None,
        games_by_performance: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        significant_moves: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        opening_tree_summary_lines: Optional[List[str]] = None,
        opening_tree_data: Optional[Dict[str, Any]] = None,
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
            self._page_number = 1
            self._draw_page_chrome(painter, content)
            y = self._draw_header(
                painter,
                content,
                player_name=player_name or "Player",
                profile_name=profile_name,
                stats=stats,
            )
            y = self._draw_sections(
                painter,
                writer,
                content,
                y,
                stats=stats,
                patterns=list(patterns or []),
                section_visibility=section_visibility,
                top_games_summary=top_games_summary,
                games_by_performance=games_by_performance,
                significant_moves=significant_moves,
                opening_tree_summary_lines=opening_tree_summary_lines,
                opening_tree_data=opening_tree_data,
                player_name=player_name or "Player",
            )
            _ = y
        finally:
            painter.end()

        return out

    def _is_visible(
        self, section_id: str, section_visibility: Optional[Dict[str, bool]]
    ) -> bool:
        return PlayerStatsTextFormatter._is_section_visible_for_export(
            section_id, section_visibility
        )

    def _draw_header(
        self,
        painter: QPainter,
        content: QRectF,
        *,
        player_name: str,
        profile_name: Optional[str],
        stats: Any,
    ) -> float:
        y = content.top()
        logo = self._logo_size
        logo_rect = QRectF(content.right() - logo, y, logo, logo)
        self._draw_logo(painter, logo_rect)

        title_w = content.width() - logo - 12.0
        y = self._draw_text_line(
            painter,
            self._title,
            content.left(),
            y,
            title_w,
            self._font_title,
            self._accent,
        )
        # Blank line between report title and player name
        y += float(QFontMetrics(self._font_heading).height())
        y = self._draw_text_line(
            painter,
            player_name,
            content.left(),
            y,
            title_w,
            self._font_heading,
            self._text,
        )
        meta_bits = []
        if profile_name:
            meta_bits.append(f"View profile: {profile_name}")
        try:
            meta_bits.append(f"{int(stats.total_games)} games")
            meta_bits.append(f"{int(stats.analyzed_games)} analyzed")
        except Exception:
            pass
        meta_bits.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
        y = self._draw_text_line(
            painter,
            " · ".join(meta_bits),
            content.left(),
            y + 2,
            title_w,
            self._font_caption,
            self._muted,
        )
        painter.setPen(QPen(self._rule, 1.0))
        y = max(y, content.top() + logo) + 8.0
        painter.drawLine(
            int(content.left()), int(y), int(content.right()), int(y)
        )
        return y + 6.0

    def _draw_sections(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        *,
        stats: Any,
        patterns: List[Any],
        section_visibility: Optional[Dict[str, bool]],
        top_games_summary,
        games_by_performance: Optional[Dict[str, List[Dict[str, Any]]]],
        significant_moves: Optional[Dict[str, List[Dict[str, Any]]]],
        opening_tree_summary_lines: Optional[List[str]],
        opening_tree_data: Optional[Dict[str, Any]],
        player_name: str,
    ) -> float:
        show = self._is_visible

        if show("overview", section_visibility):
            y = self._draw_kv_section(
                painter,
                writer,
                content,
                y,
                "Overview",
                self._overview_rows(stats),
            )

        if show("activity_heatmap", section_visibility):
            y = self._draw_activity_heatmap(painter, writer, content, y, stats)

        if show("accuracy_distribution", section_visibility):
            y = self._draw_accuracy_distribution(painter, writer, content, y, stats)

        if show("move_accuracy", section_visibility):
            y = self._draw_move_accuracy(
                painter, writer, content, y, stats, player_name=player_name
            )

        if show("performance_by_phase", section_visibility):
            y = self._draw_phase_performance(
                painter, writer, content, y, stats, player_name=player_name
            )

        if show("accuracy_vs_progress", section_visibility):
            y = self._draw_progress_chart(
                painter,
                writer,
                content,
                y,
                "Avg. Accuracy over Game Duration",
                getattr(stats, "accuracy_by_progress", None) or [],
                getattr(stats, "opponent_accuracy_by_progress", None) or [],
            )

        if show("accuracy_progression", section_visibility):
            y = self._draw_time_series_section(
                painter,
                writer,
                content,
                y,
                "Accuracy Progression",
                getattr(stats, "accuracy_over_time", None) or [],
                getattr(stats, "trends_subcaption", None),
            )

        if show("move_quality_progression", section_visibility):
            y = self._draw_move_quality_progression(painter, writer, content, y, stats)

        if show("acpl_phase_progression", section_visibility):
            y = self._draw_acpl_phase_progression(painter, writer, content, y, stats)

        if show("openings", section_visibility) and (
            stats.top_openings
            or stats.worst_accuracy_openings
            or stats.best_accuracy_openings
        ):
            y = self._draw_openings(painter, writer, content, y, stats)

        if show("opening_tree", section_visibility):
            y = self._draw_opening_tree(
                painter,
                writer,
                content,
                y,
                opening_tree_data=opening_tree_data,
                opening_tree_summary_lines=opening_tree_summary_lines,
            )

        if show("endgame_tree", section_visibility):
            y = self._draw_endgame_tree(painter, writer, content, y, stats)

        if show("games_by_performance", section_visibility):
            y = self._draw_games_by_performance(
                painter,
                writer,
                content,
                y,
                games_by_performance=games_by_performance,
                top_games_summary=top_games_summary,
            )

        if show("significant_moves", section_visibility):
            y = self._draw_significant_moves(
                painter,
                writer,
                content,
                y,
                significant_moves=significant_moves,
                stats=stats,
            )

        if show("error_patterns", section_visibility) and patterns:
            y = self._draw_error_patterns(painter, writer, content, y, patterns)

        return y

    def _overview_rows(self, stats: Any) -> List[Tuple[str, str]]:
        rows: List[Tuple[str, str]] = [
            ("Total games", str(stats.total_games)),
            ("Record (W-D-L)", f"{stats.wins}-{stats.draws}-{stats.losses}"),
            ("Win rate", f"{stats.win_rate:.1f}%"),
        ]
        ps = stats.player_stats
        acc = ps.accuracy if ps.accuracy is not None else 0.0
        rows.append(("Average accuracy", f"{acc:.1f}%"))
        elo = ps.estimated_elo if ps.estimated_elo is not None else 0
        rows.append(("Estimated Elo", str(elo)))
        cpl = ps.average_cpl if ps.average_cpl is not None else 0.0
        rows.append(("Average CPL", f"{cpl:.1f}"))
        best = ps.best_move_percentage if ps.best_move_percentage is not None else 0.0
        rows.append(("Best move %", f"{best:.1f}%"))
        top3 = ps.top3_move_percentage if ps.top3_move_percentage is not None else 0.0
        rows.append(("Top 3 move %", f"{top3:.1f}%"))
        blunder = ps.blunder_rate if ps.blunder_rate is not None else 0.0
        rows.append(("Blunder rate", f"{blunder:.1f}%"))
        return rows

    @staticmethod
    def _elide(text: str, font: QFont, max_width: float) -> str:
        fm = QFontMetrics(font)
        t = str(text or "")
        if fm.horizontalAdvance(t) <= max_width:
            return t
        return fm.elidedText(t, Qt.TextElideMode.ElideRight, int(max_width))

    @staticmethod
    def _classification_counts_from_player(ps: Any) -> Dict[str, int]:
        if ps is None:
            return {cat: 0 for cat in _CLASSIFICATION_ORDER}
        return {
            "Book Move": int(getattr(ps, "book_moves", 0) or 0),
            "Brilliant": int(getattr(ps, "brilliant_moves", 0) or 0),
            "Best Move": int(getattr(ps, "best_moves", 0) or 0),
            "Good Move": int(getattr(ps, "good_moves", 0) or 0),
            "Inaccuracy": int(getattr(ps, "inaccuracies", 0) or 0),
            "Mistake": int(getattr(ps, "mistakes", 0) or 0),
            "Miss": int(getattr(ps, "misses", 0) or 0),
            "Blunder": int(getattr(ps, "blunders", 0) or 0),
        }

    @staticmethod
    def _classification_counts_from_dict(data: Any) -> Dict[str, int]:
        src = data if isinstance(data, dict) else {}
        return {cat: int(src.get(cat, 0) or 0) for cat in _CLASSIFICATION_ORDER}

    @staticmethod
    def _classification_pcts(counts: Dict[str, int]) -> Dict[str, float]:
        total = sum(int(v) for v in counts.values())
        if total <= 0:
            return {cat: 0.0 for cat in _CLASSIFICATION_ORDER}
        return {
            cat: (int(counts.get(cat, 0) or 0) / total) * 100.0
            for cat in _CLASSIFICATION_ORDER
        }

    def _draw_pie_chart(self, painter: QPainter, rect: QRectF, data: Dict[str, int]) -> None:
        """Draw a move-classification pie into ``rect`` (PDF-native)."""
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
        start_angle = 0
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
        left_name: str,
        right_name: str,
        left_data: Dict[str, int],
        right_data: Dict[str, int],
    ) -> float:
        pie = max(64.0, min(self._pie_size, content.width() * 0.38))
        gap = 18.0
        col_w = (content.width() - gap) / 2.0
        name_h = 14.0
        for index, (name, data) in enumerate(
            ((left_name, left_data), (right_name, right_data))
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

    def _draw_pct_comparison_table(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        left_name: str,
        right_name: str,
        left_pcts: Dict[str, float],
        right_pcts: Dict[str, float],
        *,
        row_height: float = 14.0,
    ) -> float:
        """Category | player % | opponents % | Δ (player − opponents, pp)."""
        table_x = content.left()
        table_w = content.width()
        label_w = table_w * 0.32
        col_w = (table_w - label_w) / 3.0
        zebra = QColor(250, 250, 252)

        painter.fillRect(QRectF(table_x, y, table_w, row_height), self._card)
        painter.setFont(self._font_body)
        painter.setPen(self._muted)
        headers = (
            (table_x + label_w, left_name),
            (table_x + label_w + col_w, right_name),
            (table_x + label_w + 2 * col_w, "Diff (pp)"),
        )
        for hx, label in headers:
            painter.drawText(
                QRectF(hx, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                self._elide(label, self._font_body, col_w - 6),
            )
        y += row_height + 1

        for index, cat in enumerate(_CLASSIFICATION_ORDER):
            lp = float(left_pcts.get(cat, 0.0))
            rp = float(right_pcts.get(cat, 0.0))
            diff = lp - rp
            if index % 2 == 0:
                painter.fillRect(QRectF(table_x, y, table_w, row_height), zebra)
            painter.setFont(self._font_body)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(table_x + 4, y, label_w - 8, row_height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                cat,
            )
            painter.setPen(self._text)
            painter.drawText(
                QRectF(table_x + label_w, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                f"{lp:.1f}%",
            )
            painter.drawText(
                QRectF(table_x + label_w + col_w, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                f"{rp:.1f}%",
            )
            if abs(diff) < 0.05:
                diff_text = "0.0"
            else:
                diff_text = f"{diff:+.1f}"
            painter.drawText(
                QRectF(table_x + label_w + 2 * col_w, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                diff_text,
            )
            y += row_height
        return y + 6.0

    def _draw_move_accuracy(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        stats: Any,
        *,
        player_name: str,
    ) -> float:
        player_data = self._classification_counts_from_player(
            getattr(stats, "player_stats", None)
        )
        opp_data = self._classification_counts_from_dict(
            getattr(stats, "opponent_move_classification", None)
        )
        if sum(player_data.values()) <= 0 and sum(opp_data.values()) <= 0:
            return y

        player_pcts = self._classification_pcts(player_data)
        opp_pcts = self._classification_pcts(opp_data)
        left_label = (player_name or "Player").strip() or "Player"
        right_label = "Opponents"

        pie = max(64.0, min(self._pie_size, content.width() * 0.38))
        # names + pies + ~2 legend rows + table header/rows
        body = 18 + pie + 8 + 36 + 15 * (len(_CLASSIFICATION_ORDER) + 1)
        y = self._section_heading(
            painter, writer, content, y, "Move Accuracy", keep_with=body
        )
        y = self._draw_classification_pies(
            painter,
            content,
            y,
            left_label,
            right_label,
            player_data,
            opp_data,
        )
        y = self._draw_classification_legend(painter, content, y)
        caption = (
            "Share of each side's moves. Diff is player minus opponents (pp)."
        )
        y = self._draw_text_line(
            painter,
            caption,
            content.left(),
            y,
            content.width(),
            self._font_caption,
            self._muted,
        )
        y += 4.0
        return self._draw_pct_comparison_table(
            painter,
            content,
            y,
            left_label,
            right_label,
            player_pcts,
            opp_pcts,
        )

    @staticmethod
    def _fmt_pct(value: Optional[float]) -> str:
        return f"{value:.1f}%" if value is not None else "—"

    @staticmethod
    def _fmt_num(value: Optional[float], digits: int = 1) -> str:
        return f"{value:.{digits}f}" if value is not None else "—"

    def _draw_comparison_table(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        left_name: str,
        right_name: str,
        rows: Sequence[Tuple[str, str, str]],
        *,
        row_height: float = 14.0,
    ) -> float:
        """Draw label | left | right comparison rows (game-report style)."""
        table_x = content.left()
        table_w = content.width()
        label_w = table_w * 0.36
        col_w = (table_w - label_w) / 2.0
        zebra = QColor(250, 250, 252)

        painter.fillRect(QRectF(table_x, y, table_w, row_height), self._card)
        painter.setFont(self._font_body)
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(table_x + label_w, y, col_w, row_height),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(left_name, self._font_body, col_w - 6),
        )
        painter.drawText(
            QRectF(table_x + label_w + col_w, y, col_w, row_height),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(right_name, self._font_body, col_w - 6),
        )
        y += row_height + 1

        for index, (label, left_val, right_val) in enumerate(rows):
            if index % 2 == 0:
                painter.fillRect(QRectF(table_x, y, table_w, row_height), zebra)
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
                left_val,
            )
            painter.drawText(
                QRectF(table_x + label_w + col_w, y, col_w, row_height),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                right_val,
            )
            y += row_height
        return y + 6.0

    def _opponent_bar_color(self, base: QColor) -> QColor:
        """Readable mid-tone companion color for opponent bars on a light page."""
        c = QColor(base)
        h, s, v, _a = c.getHsv()
        # Keep hue; clamp to a mid value so bars never wash out to white.
        c.setHsv(
            max(0, h),
            max(50, min(140, int(s * 0.55) if s > 0 else 70)),
            155,
        )
        return c

    def _draw_phase_accuracy_bars(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        player_acc: Dict[str, float],
        opp_acc: Dict[str, float],
        *,
        player_name: str,
    ) -> float:
        """Paired horizontal bars so both player and opponent lengths stay visible."""
        phases = ("Opening", "Middlegame", "Endgame")
        ui = self.config.get("ui", {})
        colors_cfg = (
            ui.get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
            .get("colors", {})
        )
        if not isinstance(colors_cfg, dict):
            colors_cfg = {}
        phase_colors = {
            "Opening": self._rgb(colors_cfg.get("phase_opening_color"), (100, 150, 255)),
            "Middlegame": self._rgb(colors_cfg.get("phase_middlegame_color"), (100, 170, 90)),
            "Endgame": self._rgb(colors_cfg.get("phase_endgame_color"), (210, 150, 60)),
        }

        label_w = 78.0
        value_w = 72.0
        bar_h = 7.0
        bar_gap = 2.0
        row_gap = 8.0
        pair_h = bar_h * 2 + bar_gap
        avail = max(40.0, content.width() - label_w - value_w - 8.0)

        # Legend (use Opening hue as the sample pair)
        sample = phase_colors["Opening"]
        painter.setFont(self._font_caption)
        sw = 10.0
        lx = content.left()
        painter.setBrush(sample)
        painter.setPen(QPen(self._rule, 0.6))
        painter.drawRect(QRectF(lx, y + 2, sw, sw))
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(lx + sw + 4, y, 120, 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(player_name, self._font_caption, 110),
        )
        ox = content.left() + 130
        painter.setBrush(self._opponent_bar_color(sample))
        painter.setPen(QPen(self._rule, 0.6))
        painter.drawRect(QRectF(ox, y + 2, sw, sw))
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(ox + sw + 4, y, 100, 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Opponents",
        )
        y += 18.0

        for phase in phases:
            pa = float(player_acc.get(phase, 0.0) or 0.0)
            oa = float(opp_acc.get(phase, 0.0) or 0.0)
            color = phase_colors.get(phase, self._chart_bar)
            opp_color = self._opponent_bar_color(color)

            painter.setFont(self._font_body)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(content.left(), y, label_w - 4, pair_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                phase,
            )

            track_x = content.left() + label_w
            # Shared track background behind both bars
            painter.setPen(QPen(self._rule, 0.6))
            painter.setBrush(self._card)
            painter.drawRect(QRectF(track_x, y, avail, pair_h))

            pw = avail * max(0.0, min(1.0, pa / 100.0))
            ow = avail * max(0.0, min(1.0, oa / 100.0))

            painter.setPen(Qt.PenStyle.NoPen)
            if pw > 0.5:
                painter.setBrush(color)
                painter.drawRect(QRectF(track_x, y, pw, bar_h))
            if ow > 0.5:
                painter.setBrush(opp_color)
                painter.drawRect(QRectF(track_x, y + bar_h + bar_gap, ow, bar_h))

            # Outline tracks so empty ends stay readable
            painter.setPen(QPen(self._rule, 0.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(track_x, y, avail, bar_h))
            painter.drawRect(QRectF(track_x, y + bar_h + bar_gap, avail, bar_h))

            painter.setPen(self._text)
            painter.setFont(self._font_caption)
            painter.drawText(
                QRectF(track_x + avail + 4, y, value_w, pair_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{pa:.0f}% / {oa:.0f}%",
            )
            y += pair_h + row_gap

        return y + 2.0

    def _draw_phase_performance(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        stats: Any,
        *,
        player_name: str,
    ) -> float:
        """Phase accuracy bars + Acc/ACPL comparison table (game-report style)."""
        opening = getattr(stats, "opening_stats", None)
        middle = getattr(stats, "middlegame_stats", None)
        endgame = getattr(stats, "endgame_stats", None)
        opp_raw = getattr(stats, "opponent_phase_accuracy", None) or {}
        if not isinstance(opp_raw, dict):
            opp_raw = {}

        def player_cell(phase: Any) -> str:
            if phase is None:
                return "—"
            moves = int(getattr(phase, "moves", 0) or 0)
            acc = getattr(phase, "accuracy", None)
            cpl = getattr(phase, "average_cpl", None)
            if moves <= 0 and acc is None and cpl is None:
                return "—"
            return f"{self._fmt_pct(acc)} / {self._fmt_num(cpl)}"

        def opp_cell(phase_name: str) -> str:
            if phase_name not in opp_raw:
                return "—"
            try:
                val = float(opp_raw.get(phase_name))
            except (TypeError, ValueError):
                return "—"
            # Opponents only expose accuracy in aggregated stats (no ACPL).
            return f"{self._fmt_pct(val)} / —"

        player_acc = {
            "Opening": float(getattr(opening, "accuracy", 0.0) or 0.0),
            "Middlegame": float(getattr(middle, "accuracy", 0.0) or 0.0),
            "Endgame": float(getattr(endgame, "accuracy", 0.0) or 0.0),
        }
        opp_acc = {
            "Opening": float(opp_raw.get("Opening", 0.0) or 0.0),
            "Middlegame": float(opp_raw.get("Middlegame", 0.0) or 0.0),
            "Endgame": float(opp_raw.get("Endgame", 0.0) or 0.0),
        }

        left_label = (player_name or "Player").strip() or "Player"
        right_label = "Opponents"
        rows = [
            ("Opening", player_cell(opening), opp_cell("Opening")),
            ("Middlegame", player_cell(middle), opp_cell("Middlegame")),
            ("Endgame", player_cell(endgame), opp_cell("Endgame")),
        ]

        # legend + paired bars (~3 rows) + caption + table
        body = 18 + 90 + 14 + 17 * (len(rows) + 1)
        y = self._section_heading(
            painter, writer, content, y, "Performance by Phase", keep_with=body
        )
        y = self._draw_phase_accuracy_bars(
            painter, content, y, player_acc, opp_acc, player_name=left_label
        )
        painter.setFont(self._font_caption)
        painter.setPen(self._muted)
        painter.drawText(
            QRectF(content.left(), y, content.width(), 12),
            Qt.AlignmentFlag.AlignLeft,
            "Values: Accuracy / ACPL  (opponents: accuracy only)",
        )
        y += 14
        return self._draw_comparison_table(
            painter, content, y, left_label, right_label, rows
        )

    def _draw_kv_section(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        title: str,
        rows: List[Tuple[str, str]],
    ) -> float:
        line_h = float(QFontMetrics(self._font_body).height()) + 2.0
        y = self._section_heading(
            painter, writer, content, y, title, keep_with=line_h * 3
        )
        col_w = content.width() / 2.0 - 6.0
        label_w = col_w * 0.55
        for i, (label, value) in enumerate(rows):
            y, _ = self._ensure_space(painter, writer, content, y, line_h)
            col = i % 2
            if col == 0 and i + 1 == len(rows):
                # last odd item spans conceptually left column only
                pass
            x = content.left() + col * (col_w + 12.0)
            row_y = y
            self._draw_text_line(
                painter, label, x, row_y, label_w, self._font_body, self._muted
            )
            self._draw_text_line(
                painter,
                value,
                x + label_w,
                row_y,
                col_w - label_w,
                self._font_body_bold,
                self._text,
            )
            if col == 1 or i + 1 == len(rows):
                y += line_h
        return y + 4.0

    def _draw_text_section(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        title: str,
        lines: Sequence[str],
    ) -> float:
        body = [ln for ln in lines if ln is not None]
        if not body:
            return y
        line_h = float(QFontMetrics(self._font_body).height()) + 1.0
        y = self._section_heading(
            painter, writer, content, y, title, keep_with=line_h * 2
        )
        for ln in body:
            text = str(ln).strip()
            if not text:
                y += 4.0
                continue
            # Skip duplicate section headers from text formatter
            if text.startswith("---") or text == title:
                continue
            y, _ = self._ensure_space(painter, writer, content, y, line_h * 2)
            y = self._draw_text_line(
                painter,
                text,
                content.left(),
                y,
                content.width(),
                self._font_body,
                self._text,
            )
        return y + 4.0

    def _draw_accuracy_distribution(
        self, painter: QPainter, writer, content: QRectF, y: float, stats: Any
    ) -> float:
        values_raw = getattr(stats, "accuracy_values", None) or []
        if len(values_raw) < 2:
            return y

        values = [max(0.0, min(100.0, float(v))) for v in values_raw]
        try:
            from app.services.player_stats_accuracy_distribution_user import (
                normalize_player_stats_accuracy_distribution_settings,
            )
            from app.services.user_settings_service import UserSettingsService
            from app.views.widgets.accuracy_distribution_chart_widget import (
                _bar_pixel_spans,
            )

            usr = normalize_player_stats_accuracy_distribution_settings(
                UserSettingsService.get_instance()
                .get_model()
                .get_player_stats_accuracy_distribution()
            )
        except Exception:
            usr = {
                "skew_mode": "high_accuracy_skew",
                "y_axis_mode": "count",
                "x_axis_span": "full",
                "bin_density": "auto",
            }
            from app.views.widgets.accuracy_distribution_chart_widget import (
                _bar_pixel_spans,
            )

        dist_cfg = (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
            .get("accuracy_distribution", {})
        )
        if not isinstance(dist_cfg, dict):
            dist_cfg = {}

        # Skew exponent (match in-app chart)
        mode = str(usr.get("skew_mode", "high_accuracy_skew"))
        ex = dist_cfg.get("skew_exponents")
        k = 4.0
        if isinstance(ex, dict) and mode in ex:
            try:
                k = max(1.0, float(ex[mode]))
            except (TypeError, ValueError):
                pass
        elif mode == "very_high_accuracy_skew":
            k = 6.5
        elif mode == "linear":
            k = 1.0

        data_min = min(values)
        data_max = max(values)
        margin = 2.5
        low = max(0.0, data_min - margin)
        high = min(100.0, data_max + margin)
        if high <= low:
            high = min(100.0, low + 5.0)
        range_size = high - low

        profiles = dist_cfg.get("bin_density_profiles")
        density_key = str(usr.get("bin_density", "auto"))
        profile = (
            profiles.get(density_key)
            if isinstance(profiles, dict)
            else None
        )
        if not isinstance(profile, dict):
            profile = {"min_bins": 5, "max_bins": 25, "range_divisor": 5.0}
        try:
            mn = max(3, int(profile.get("min_bins", 5)))
            mx = max(mn, int(profile.get("max_bins", 25)))
            div = float(profile.get("range_divisor", 5.0)) or 5.0
        except (TypeError, ValueError):
            mn, mx, div = 5, 25, 5.0
        bin_count = max(mn, min(mx, int(round(range_size / div))))

        if k <= 1.0001:
            t_low, t_high = low / 100.0, high / 100.0
        else:
            t_low = (low / 100.0) ** k
            t_high = (high / 100.0) ** k
        t_range = max(1e-9, t_high - t_low)
        t_edges = [t_low + (i / float(bin_count)) * t_range for i in range(bin_count + 1)]
        if k <= 1.0001:
            acc_edges = [100.0 * t for t in t_edges]
        else:
            acc_edges = [100.0 * (t ** (1.0 / k)) for t in t_edges]

        bins = [0] * bin_count
        for v in values:
            t = v / 100.0 if k <= 1.0001 else (v / 100.0) ** k
            if t <= t_low:
                idx = 0
            elif t >= t_high:
                idx = bin_count - 1
            else:
                idx = int((t - t_low) / t_range * bin_count)
                idx = min(bin_count - 1, max(0, idx))
            bins[idx] += 1

        y_mode = str(usr.get("y_axis_mode", "count"))
        total = len(values)
        if y_mode == "percent_of_games" and total > 0:
            heights = [100.0 * c / float(total) for c in bins]
            y_suffix = "%"
            y_title = "Share of games"
        else:
            heights = [float(c) for c in bins]
            y_suffix = ""
            y_title = "Games"
        max_h = max(heights) if heights else 1.0
        if max_h <= 0:
            max_h = 1.0

        x_span_mode = str(usr.get("x_axis_span", "full"))
        if x_span_mode == "data_bounds":
            x_min, x_max = float(acc_edges[0]), float(acc_edges[-1])
            if x_max <= x_min:
                x_max = min(100.0, x_min + 1.0)
        else:
            x_min, x_max = 0.0, 100.0

        # Print-safe bar colors from the active color preset (same as the in-app chart)
        color_ranges: List[Tuple[float, QColor]] = []
        presets = dist_cfg.get("color_presets")
        preset_id = str(usr.get("color_preset", "github_green"))
        raw_ranges = None
        if isinstance(presets, dict):
            raw_ranges = presets.get(preset_id) or presets.get("github_green")
        if isinstance(raw_ranges, list):
            for entry in raw_ranges:
                if not isinstance(entry, dict):
                    continue
                try:
                    max_acc = float(entry.get("max_acc"))
                    c = self._rgb(entry.get("color"), (35, 80, 120))
                    if c.lightness() > 175:
                        c = c.darker(125)
                    color_ranges.append((max_acc, c))
                except (TypeError, ValueError):
                    continue
            color_ranges.sort(key=lambda t: t[0])
        fallback_bar = self._rgb(dist_cfg.get("bar_color"), (35, 80, 120))
        if fallback_bar.lightness() > 175:
            fallback_bar = fallback_bar.darker(125)

        def bar_color(center_acc: float) -> QColor:
            if not color_ranges:
                return fallback_bar
            acc = max(0.0, min(100.0, center_acc))
            first_max, first_color = color_ranges[0]
            if acc <= first_max:
                return first_color
            prev_max, prev_color = first_max, first_color
            for max_acc, color in color_ranges[1:]:
                if acc <= max_acc:
                    t = (
                        (acc - prev_max) / (max_acc - prev_max)
                        if max_acc > prev_max
                        else 1.0
                    )
                    return QColor(
                        int(prev_color.red() + t * (color.red() - prev_color.red())),
                        int(prev_color.green() + t * (color.green() - prev_color.green())),
                        int(prev_color.blue() + t * (color.blue() - prev_color.blue())),
                    )
                prev_max, prev_color = max_acc, color
            return color_ranges[-1][1]

        chart_h = float(self._cfg.get("accuracy_distribution_chart_height", self._chart_height))
        area_h = chart_h + 28.0
        block_h = area_h + 16.0
        y = self._section_heading(
            painter, writer, content, y, "Accuracy Distribution", keep_with=block_h
        )
        y, _ = self._ensure_space(painter, writer, content, y, block_h)
        outer = QRectF(content.left(), y, content.width(), area_h)

        painter.setFont(self._font_caption)
        fm = QFontMetrics(self._font_caption)
        line_h = float(fm.height())
        # Y tick labels
        y_ticks = 4
        y_labels = []
        for i in range(y_ticks):
            frac = i / (y_ticks - 1)
            val = max_h * frac
            if y_suffix:
                lab = f"{val:.0f}%" if abs(val - round(val)) < 0.05 else f"{val:.1f}%"
            else:
                lab = f"{val:.0f}"
            y_labels.append((val, lab))
        y_label_w = max(float(fm.horizontalAdvance(lab)) for _, lab in y_labels)
        pad_l = y_label_w + 8.0
        pad_r = 10.0
        pad_t = line_h + 4.0
        pad_b = line_h + 4.0 + line_h + 2.0  # x ticks + title
        plot = QRectF(
            outer.left() + pad_l,
            outer.top() + pad_t,
            max(20.0, outer.width() - pad_l - pad_r),
            max(20.0, outer.height() - pad_t - pad_b),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._card)
        painter.drawRect(outer)

        painter.setPen(self._muted)
        painter.setFont(self._font_caption)
        painter.drawText(
            QRectF(plot.left(), outer.top() + 1.0, plot.width(), line_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            y_title,
        )

        # Horizontal grid + Y labels
        painter.setPen(QPen(self._chart_grid, 0.7))
        for val, lab in y_labels:
            yy = plot.bottom() - (val / max_h) * plot.height()
            painter.drawLine(int(plot.left()), int(yy), int(plot.right()), int(yy))
        painter.setPen(self._muted)
        for val, lab in y_labels:
            yy = plot.bottom() - (val / max_h) * plot.height()
            tw = float(fm.horizontalAdvance(lab))
            painter.drawText(
                QRectF(plot.left() - tw - 6.0, yy - line_h / 2.0, tw + 2.0, line_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                lab,
            )

        # Vertical minor grid at 25% accuracy marks (when full span)
        painter.setPen(QPen(self._chart_grid, 0.7))
        x_tick_vals = [0.0, 25.0, 50.0, 75.0, 100.0]
        for xv in x_tick_vals:
            if xv < x_min - 1e-6 or xv > x_max + 1e-6:
                continue
            xx = plot.left() + (xv - x_min) / (x_max - x_min) * plot.width()
            painter.drawLine(int(xx), int(plot.top()), int(xx), int(plot.bottom()))

        # Bars (pixel spans match in-app histogram geometry)
        bar_gap = max(0, int(dist_cfg.get("bar_gap_px", 1)))
        spans = _bar_pixel_spans(
            int(plot.left()),
            int(plot.width()),
            acc_edges,
            bar_gap,
            x_min,
            x_max,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(bin_count):
            if bins[i] <= 0:
                continue
            if i >= len(spans):
                continue
            x0, w0 = spans[i]
            h_val = heights[i]
            bar_h = max(2.0, (h_val / max_h) * plot.height())
            rect = QRectF(float(x0), plot.bottom() - bar_h, float(max(1, w0)), bar_h)
            center = (acc_edges[i] + acc_edges[i + 1]) / 2.0
            painter.setBrush(bar_color(center))
            painter.drawRect(rect)

        # X tick labels
        painter.setPen(self._muted)
        painter.setFont(self._font_caption)
        for i, xv in enumerate(x_tick_vals):
            if xv < x_min - 1e-6 or xv > x_max + 1e-6:
                continue
            xx = plot.left() + (xv - x_min) / (x_max - x_min) * plot.width()
            lab = f"{xv:.0f}%"
            tw = float(fm.horizontalAdvance(lab))
            if i == 0:
                left = max(outer.left() + 2.0, xx)
            elif i == len(x_tick_vals) - 1:
                left = min(xx - tw, outer.right() - tw - 2.0)
            else:
                left = xx - tw / 2.0
            painter.drawText(
                QRectF(left, plot.bottom() + 3.0, tw + 1.0, line_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                lab,
            )
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + line_h + 4.0, plot.width(), line_h),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Accuracy",
        )

        painter.setPen(QPen(self._rule, 0.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot)

        return outer.bottom() + 8.0

    def _draw_progress_chart(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        title: str,
        player_series: Sequence,
        opponent_series: Sequence,
    ) -> float:
        pts = self._series_xy(player_series)
        if len(pts) < 2:
            return y
        chart_h = self._chart_height
        # Extra room for axis titles / tick labels outside the plot.
        area_h = chart_h + 22.0
        block_h = area_h + 20.0
        y = self._section_heading(
            painter, writer, content, y, title, keep_with=block_h
        )
        y, _ = self._ensure_space(painter, writer, content, y, block_h)
        area = QRectF(content.left(), y, content.width(), area_h)
        series = [(pts, self._chart_bar, 2.0)]
        opp = self._series_xy(opponent_series)
        if len(opp) >= 2:
            series.append((opp, self._muted, 1.5))
        self._draw_accuracy_line_chart(
            painter,
            area,
            series,
            x_domain=(0.0, 100.0),
            x_ticks=[
                (0.0, "0%"),
                (25.0, "25%"),
                (50.0, "50%"),
                (75.0, "75%"),
                (100.0, "100%"),
            ],
            x_axis_title="Game duration",
            y_axis_title="Accuracy",
        )
        y = area.bottom() + 4.0
        y = self._draw_text_line(
            painter,
            "Solid: player · Faint: opponents",
            content.left(),
            y,
            content.width(),
            self._font_caption,
            self._muted,
        )
        return y + 6.0

    def _draw_time_series_section(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        title: str,
        series: Sequence,
        subcaption: Optional[str],
    ) -> float:
        pts, x_ticks = self._accuracy_over_time_points(series)
        if len(pts) < 2:
            class _Tmp:
                pass

            tmp = _Tmp()
            tmp.accuracy_over_time = series
            tmp.trends_subcaption = subcaption
            lines = PlayerStatsTextFormatter._format_accuracy_over_time(tmp)
            if not lines:
                return y
            return self._draw_text_section(
                painter,
                writer,
                content,
                y,
                title,
                lines[2:] if len(lines) > 2 else lines,
            )

        chart_h = self._chart_height
        area_h = chart_h + 22.0
        block_h = area_h + 20.0
        y = self._section_heading(
            painter, writer, content, y, title, keep_with=block_h
        )
        if subcaption:
            y = self._draw_text_line(
                painter,
                str(subcaption),
                content.left(),
                y,
                content.width(),
                self._font_caption,
                self._muted,
            )
        y, _ = self._ensure_space(painter, writer, content, y, block_h)
        area = QRectF(content.left(), y, content.width(), area_h)
        self._draw_accuracy_line_chart(
            painter,
            area,
            [(pts, self._chart_bar, 2.0)],
            x_ticks=x_ticks,
            x_axis_title="Date",
            y_axis_title="Accuracy",
        )
        return area.bottom() + 8.0

    @staticmethod
    def _accuracy_over_time_points(
        series: Sequence,
    ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, str]]]:
        """Parse accuracy_over_time bins → (x,y) points and a few x-axis tick labels."""
        pts: List[Tuple[float, float]] = []
        label_candidates: List[Tuple[float, str]] = []
        for i, item in enumerate(series):
            try:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                # (time_pct, median_all, median_white, median_black, count, lab0, lab1)
                x = float(item[0])
                yv = float(item[1])
                if yv != yv:  # NaN
                    continue
                pts.append((x, yv))
                lab = ""
                if len(item) >= 7:
                    lab = str(item[5] or item[6] or "").strip()
                elif len(item) >= 6:
                    lab = str(item[5] or "").strip()
                if lab:
                    label_candidates.append((x, lab))
            except Exception:
                # Fallback: index-based if row shape is unexpected
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        pts.append((float(i), float(item[1])))
                except Exception:
                    continue

        if not pts:
            return [], []

        xs = [p[0] for p in pts]
        min_x, max_x = min(xs), max(xs)
        ticks: List[Tuple[float, str]] = []
        if label_candidates:
            # First / middle / last labeled bins
            label_candidates.sort(key=lambda t: t[0])
            picks = {0, len(label_candidates) // 2, len(label_candidates) - 1}
            for idx in sorted(picks):
                ticks.append(label_candidates[idx])
        else:
            ticks = [
                (min_x, f"{min_x:.0f}"),
                ((min_x + max_x) / 2.0, f"{(min_x + max_x) / 2.0:.0f}"),
                (max_x, f"{max_x:.0f}"),
            ]
        return pts, ticks

    def _move_quality_series_styles(self) -> Dict[str, Tuple[QColor, float]]:
        """Map series id → (color, line_width) from player_stats chart config."""
        defaults = {
            "best_move": ((40, 140, 95), 2.0),
            "top3_move": ((50, 120, 190), 2.0),
            "blunder_rate": ((190, 55, 55), 2.0),
        }
        out: Dict[str, Tuple[QColor, float]] = {
            k: (QColor(*rgb), w) for k, (rgb, w) in defaults.items()
        }
        mq = (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
            .get("move_quality_over_time_chart", {})
        )
        if not isinstance(mq, dict):
            return out
        for item in mq.get("series") or []:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id", "")).strip()
            if not sid:
                continue
            rgb = item.get("line_color")
            color = self._rgb(rgb, defaults.get(sid, ((100, 100, 110), 2.0))[0])
            # Bright UI colors (dark theme) → slightly darker for print on light paper.
            if color.lightness() > 175:
                color = color.darker(125)
            lw = float(item.get("line_width", 2) or 2)
            out[sid] = (color, max(1.0, lw))
        return out

    def _draw_move_quality_progression(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        stats: Any,
    ) -> float:
        bins = list(getattr(stats, "move_quality_over_time", None) or [])
        labels = list(getattr(stats, "move_quality_series_labels", None) or [])
        ids = list(getattr(stats, "move_quality_series_ids", None) or [])
        if not bins or not labels:
            return y

        styles = self._move_quality_series_styles()
        fallback_colors = [
            QColor(40, 140, 95),
            QColor(50, 120, 190),
            QColor(190, 55, 55),
            QColor(150, 100, 60),
        ]

        while len(ids) < len(labels):
            ids.append(f"series_{len(ids)}")

        series_list: List[Tuple[List[Tuple[float, float]], QColor, float]] = []
        legend: List[Tuple[str, QColor]] = []
        sorted_bins = sorted(bins, key=lambda row: float(row[0]))
        for j, lab in enumerate(labels):
            sid = ids[j] if j < len(ids) else f"series_{j}"
            color, width = styles.get(
                sid, (fallback_colors[j % len(fallback_colors)], 2.0)
            )
            pts: List[Tuple[float, float]] = []
            for row in sorted_bins:
                try:
                    t_pct = float(row[0])
                    meds = row[4] if len(row) >= 5 else ()
                    if j >= len(meds):
                        continue
                    val = float(meds[j])
                    if val != val:  # NaN
                        continue
                    pts.append((t_pct, val))
                except Exception:
                    continue
            if len(pts) >= 2:
                series_list.append((pts, color, width))
                legend.append((str(lab), color))

        if not series_list:
            lines = PlayerStatsTextFormatter._format_move_quality_over_time(stats)
            if not lines:
                return y
            return self._draw_text_section(
                painter,
                writer,
                content,
                y,
                "Move Quality Progression",
                lines[2:] if len(lines) > 2 else lines,
            )

        label_candidates: List[Tuple[float, str]] = []
        for row in sorted_bins:
            try:
                t_pct = float(row[0])
                lab0 = str(row[2] if len(row) > 2 else "").strip()
                lab1 = str(row[3] if len(row) > 3 else "").strip()
                lab = lab0 or lab1
                if lab:
                    label_candidates.append((t_pct, lab))
            except Exception:
                continue
        x_ticks: List[Tuple[float, str]] = []
        if label_candidates:
            picks = {0, len(label_candidates) // 2, len(label_candidates) - 1}
            x_ticks = [label_candidates[i] for i in sorted(picks)]
        else:
            xs = [p[0] for pts, _, _ in series_list for p in pts]
            min_x, max_x = min(xs), max(xs)
            x_ticks = [
                (min_x, f"{min_x:.0f}"),
                ((min_x + max_x) / 2.0, f"{(min_x + max_x) / 2.0:.0f}"),
                (max_x, f"{max_x:.0f}"),
            ]

        chart_h = self._move_quality_chart_height
        area_h = chart_h + 36.0
        block_h = area_h + 24.0
        y = self._section_heading(
            painter, writer, content, y, "Move Quality Progression", keep_with=block_h
        )
        sub = getattr(stats, "move_quality_subcaption", None)
        if sub:
            y = self._draw_text_line(
                painter,
                str(sub),
                content.left(),
                y,
                content.width(),
                self._font_caption,
                self._muted,
            )
        y, _ = self._ensure_space(painter, writer, content, y, block_h)
        area = QRectF(content.left(), y, content.width(), area_h)
        self._draw_accuracy_line_chart(
            painter,
            area,
            series_list,
            x_ticks=x_ticks,
            x_axis_title="Date",
            y_axis_title="Move quality",
            legend=legend,
        )
        return area.bottom() + 8.0

    def _acpl_phase_series_styles(self) -> Tuple[Dict[str, Tuple[QColor, float]], float]:
        """Map series id → (color, width) and Y max cap from ACPL phase chart config."""
        ps = (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
        )
        colors_cfg = ps.get("colors", {}) if isinstance(ps, dict) else {}
        if not isinstance(colors_cfg, dict):
            colors_cfg = {}
        defaults = {
            "opening": (
                self._rgb(colors_cfg.get("phase_opening_color"), (100, 150, 255)),
                2.0,
            ),
            "middlegame": (
                self._rgb(colors_cfg.get("phase_middlegame_color"), (100, 170, 90)),
                2.0,
            ),
            "endgame": (
                self._rgb(colors_cfg.get("phase_endgame_color"), (210, 150, 60)),
                2.0,
            ),
        }
        out: Dict[str, Tuple[QColor, float]] = dict(defaults)
        ap = ps.get("acpl_phase_over_time_chart", {}) if isinstance(ps, dict) else {}
        if not isinstance(ap, dict):
            ap = {}
        y_cap = float(ap.get("y_axis_max_cap", 500) or 500)
        for item in ap.get("series") or []:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id", "")).strip().lower()
            if not sid:
                continue
            fallback_rgb = (100, 100, 110)
            if sid in defaults:
                c0 = defaults[sid][0]
                fallback_rgb = (c0.red(), c0.green(), c0.blue())
            color = self._rgb(item.get("line_color"), fallback_rgb)
            if color.lightness() > 175:
                color = color.darker(125)
            lw = float(item.get("line_width", 2) or 2)
            out[sid] = (color, max(1.0, lw))
        return out, y_cap

    def _draw_acpl_phase_progression(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        stats: Any,
    ) -> float:
        bins = list(getattr(stats, "acpl_phase_over_time", None) or [])
        labels = list(getattr(stats, "acpl_phase_series_labels", None) or [])
        ids = list(getattr(stats, "acpl_phase_series_ids", None) or [])
        if not bins or not labels:
            return y

        styles, y_cap = self._acpl_phase_series_styles()
        fallback_colors = [
            QColor(100, 150, 255),
            QColor(100, 170, 90),
            QColor(210, 150, 60),
        ]
        while len(ids) < len(labels):
            ids.append(f"series_{len(ids)}")

        series_list: List[Tuple[List[Tuple[float, float]], QColor, float]] = []
        legend: List[Tuple[str, QColor]] = []
        sorted_bins = sorted(bins, key=lambda row: float(row[0]))
        for j, lab in enumerate(labels):
            sid = str(ids[j] if j < len(ids) else f"series_{j}").strip().lower()
            color, width = styles.get(
                sid, (fallback_colors[j % len(fallback_colors)], 2.0)
            )
            pts: List[Tuple[float, float]] = []
            for row in sorted_bins:
                try:
                    t_pct = float(row[0])
                    meds = row[4] if len(row) >= 5 else ()
                    if j >= len(meds):
                        continue
                    val = float(meds[j])
                    if val != val:  # NaN
                        continue
                    pts.append((t_pct, val))
                except Exception:
                    continue
            if len(pts) >= 2:
                series_list.append((pts, color, width))
                legend.append((str(lab), color))

        if not series_list:
            lines = PlayerStatsTextFormatter._format_acpl_phase_over_time(stats)
            if not lines:
                return y
            return self._draw_text_section(
                painter,
                writer,
                content,
                y,
                "ACPL Progression by Phase",
                lines[2:] if len(lines) > 2 else lines,
            )

        label_candidates: List[Tuple[float, str]] = []
        for row in sorted_bins:
            try:
                t_pct = float(row[0])
                lab0 = str(row[2] if len(row) > 2 else "").strip()
                lab1 = str(row[3] if len(row) > 3 else "").strip()
                lab = lab0 or lab1
                if lab:
                    label_candidates.append((t_pct, lab))
            except Exception:
                continue
        x_ticks: List[Tuple[float, str]] = []
        if label_candidates:
            picks = {0, len(label_candidates) // 2, len(label_candidates) - 1}
            x_ticks = [label_candidates[i] for i in sorted(picks)]
        else:
            xs = [p[0] for pts, _, _ in series_list for p in pts]
            min_x, max_x = min(xs), max(xs)
            x_ticks = [
                (min_x, f"{min_x:.0f}"),
                ((min_x + max_x) / 2.0, f"{(min_x + max_x) / 2.0:.0f}"),
                (max_x, f"{max_x:.0f}"),
            ]

        chart_h = self._acpl_phase_chart_height
        area_h = chart_h + 36.0
        block_h = area_h + 24.0
        y = self._section_heading(
            painter, writer, content, y, "ACPL Progression by Phase", keep_with=block_h
        )
        sub = getattr(stats, "acpl_phase_subcaption", None)
        if sub:
            y = self._draw_text_line(
                painter,
                str(sub),
                content.left(),
                y,
                content.width(),
                self._font_caption,
                self._muted,
            )
        y, _ = self._ensure_space(painter, writer, content, y, block_h)
        area = QRectF(content.left(), y, content.width(), area_h)
        self._draw_accuracy_line_chart(
            painter,
            area,
            series_list,
            x_ticks=x_ticks,
            x_axis_title="Date",
            y_axis_title="Median ACPL",
            legend=legend,
            y_suffix="",
            y_max_cap=y_cap,
        )
        return area.bottom() + 8.0

    def _draw_accuracy_line_chart(
        self,
        painter: QPainter,
        outer: QRectF,
        series_list: Sequence[Tuple[List[Tuple[float, float]], QColor, float]],
        *,
        x_ticks: Sequence[Tuple[float, str]],
        x_domain: Optional[Tuple[float, float]] = None,
        y_domain: Optional[Tuple[float, float]] = None,
        y_tick_count: int = 4,
        x_axis_title: str = "",
        y_axis_title: str = "",
        legend: Optional[Sequence[Tuple[str, QColor]]] = None,
        y_suffix: str = "%",
        y_max_cap: Optional[float] = 100.0,
    ) -> None:
        """Draw a framed line chart with gridlines and axis labels.

        ``y_suffix`` is appended to tick labels (``%`` for accuracy charts, empty for ACPL).
        ``y_max_cap`` clamps the upper Y bound (``100`` for percentages, ``500`` typical for ACPL).
        """
        all_pts: List[Tuple[float, float]] = []
        for pts, _c, _w in series_list:
            all_pts.extend(pts)
        if len(all_pts) < 2:
            return

        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        if x_domain is None:
            min_x, max_x = min(xs), max(xs)
            if max_x <= min_x:
                max_x = min_x + 1.0
        else:
            min_x, max_x = float(x_domain[0]), float(x_domain[1])
            if max_x <= min_x:
                max_x = min_x + 1.0

        if y_domain is None:
            raw_lo, raw_hi = min(ys), max(ys)
            pad = max(1.0, (raw_hi - raw_lo) * 0.08)
            raw_lo = max(0.0, raw_lo - pad)
            raw_hi = raw_hi + pad
            if y_max_cap is not None:
                raw_hi = min(float(y_max_cap), raw_hi)
            if raw_hi <= raw_lo:
                bump = 5.0 if y_max_cap is None else min(5.0, float(y_max_cap) - raw_lo)
                raw_hi = raw_lo + max(1.0, bump)
        else:
            raw_lo, raw_hi = float(y_domain[0]), float(y_domain[1])
            if raw_hi <= raw_lo:
                raw_hi = raw_lo + 1.0

        min_y, max_y, y_tick_vals = self._nice_axis_ticks(
            raw_lo, raw_hi, max(2, int(y_tick_count))
        )
        min_y = max(0.0, min_y)
        if y_max_cap is not None:
            max_y = min(float(y_max_cap), max(max_y, min_y + 1.0))
        else:
            max_y = max(max_y, min_y + 1.0)
        y_tick_vals = [v for v in y_tick_vals if min_y - 1e-6 <= v <= max_y + 1e-6]
        if len(y_tick_vals) < 2:
            y_tick_vals = [min_y, max_y]

        painter.setFont(self._font_caption)
        fm = QFontMetrics(self._font_caption)
        line_h = float(fm.height())

        def _y_label(v: float) -> str:
            if abs(v - round(v)) < 0.05:
                body = f"{v:.0f}"
            else:
                body = f"{v:.1f}"
            return f"{body}{y_suffix}"

        y_labels = [_y_label(v) for v in y_tick_vals]
        y_label_w = max((float(fm.horizontalAdvance(t)) for t in y_labels), default=24.0)

        visible_x = [
            (xv, lab)
            for xv, lab in x_ticks
            if min_x - 1e-6 <= xv <= max_x + 1e-6
        ]
        # Reserve side room so edge tick labels are not clipped by the frame.
        edge_x_pad = 4.0
        if visible_x:
            first_w = float(fm.horizontalAdvance(visible_x[0][1]))
            last_w = float(fm.horizontalAdvance(visible_x[-1][1]))
            edge_x_pad = max(edge_x_pad, first_w * 0.35, last_w * 0.35)

        title_band = (line_h + 4.0) if y_axis_title else 4.0
        tick_band = line_h + 4.0
        title_x_band = (line_h + 2.0) if x_axis_title else 0.0
        legend_items = list(legend or [])
        legend_band = (line_h + 6.0) if legend_items else 0.0
        pad_l = y_label_w + 8.0
        pad_r = max(8.0, edge_x_pad)
        pad_t = title_band
        pad_b = tick_band + title_x_band + legend_band + 2.0

        plot = QRectF(
            outer.left() + pad_l,
            outer.top() + pad_t,
            max(20.0, outer.width() - pad_l - pad_r),
            max(20.0, outer.height() - pad_t - pad_b),
        )

        # Card background (no outer border — plot has its own frame)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._card)
        painter.drawRect(outer)

        def map_x(xv: float) -> float:
            return plot.left() + (xv - min_x) / (max_x - min_x) * plot.width()

        def map_y(yv: float) -> float:
            return plot.bottom() - (yv - min_y) / (max_y - min_y) * plot.height()

        # Y-axis title in its own band above the plot (aligned to plot, not y-ticks)
        if y_axis_title:
            painter.setPen(self._muted)
            painter.setFont(self._font_caption)
            painter.drawText(
                QRectF(plot.left(), outer.top() + 1.0, plot.width(), line_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                y_axis_title,
            )

        # Horizontal grid + Y tick labels
        painter.setPen(QPen(self._chart_grid, 0.7))
        for yv in y_tick_vals:
            yy = map_y(yv)
            painter.drawLine(int(plot.left()), int(yy), int(plot.right()), int(yy))
        painter.setPen(self._muted)
        painter.setFont(self._font_caption)
        for yv, label in zip(y_tick_vals, y_labels):
            yy = map_y(yv)
            # Keep label vertically inside the outer card
            top = max(outer.top() + title_band, yy - line_h / 2.0)
            top = min(top, outer.bottom() - pad_b - line_h)
            painter.drawText(
                QRectF(outer.left() + 2.0, top, pad_l - 6.0, line_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        # Vertical grid
        painter.setPen(QPen(self._chart_grid, 0.7))
        for xv, _lab in visible_x:
            xx = map_x(xv)
            painter.drawLine(int(xx), int(plot.top()), int(xx), int(plot.bottom()))

        # X tick labels — edge-aware alignment so dates / 0% stay inside the card
        painter.setPen(self._muted)
        painter.setFont(self._font_caption)
        n_x = len(visible_x)
        for i, (xv, lab) in enumerate(visible_x):
            xx = map_x(xv)
            tw = float(fm.horizontalAdvance(lab))
            if i == 0:
                left = max(outer.left() + 2.0, xx)
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            elif i == n_x - 1:
                left = min(xx - tw, outer.right() - tw - 2.0)
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            else:
                left = xx - tw / 2.0
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            painter.drawText(
                QRectF(left, plot.bottom() + 3.0, tw + 1.0, line_h),
                align,
                lab,
            )

        if x_axis_title:
            painter.setPen(self._muted)
            painter.setFont(self._font_caption)
            title_y = plot.bottom() + tick_band
            painter.drawText(
                QRectF(plot.left(), title_y, plot.width(), line_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                x_axis_title,
            )

        # Series legend (color key)
        if legend_items:
            sw = 10.0
            gap = 14.0
            text_gap = 4.0
            lx = plot.left()
            legend_y = plot.bottom() + tick_band + title_x_band
            painter.setFont(self._font_caption)
            for lab, color in legend_items:
                tw = float(fm.horizontalAdvance(lab))
                item_w = sw + text_gap + tw
                if lx > plot.left() and lx + item_w > plot.right():
                    lx = plot.left()
                    legend_y += line_h + 2.0
                painter.setPen(QPen(self._rule, 0.6))
                painter.setBrush(color)
                painter.drawRect(QRectF(lx, legend_y + (line_h - sw) / 2.0, sw, sw))
                painter.setPen(self._text)
                painter.drawText(
                    QRectF(lx + sw + text_gap, legend_y, tw + 2.0, line_h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    lab,
                )
                lx += item_w + gap

        # Plot border
        painter.setPen(QPen(self._rule, 0.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot)

        # Series (clipped to plot)
        painter.save()
        painter.setClipRect(plot)
        for pts, color, width in series_list:
            if len(pts) < 2:
                continue
            painter.setPen(QPen(color, width))
            prev = None
            for xv, yv in sorted(pts, key=lambda p: p[0]):
                px = map_x(xv)
                py = map_y(yv)
                if prev is not None:
                    painter.drawLine(int(prev[0]), int(prev[1]), int(px), int(py))
                prev = (px, py)
        painter.restore()

    @staticmethod
    def _nice_axis_ticks(
        lo: float, hi: float, count: int
    ) -> Tuple[float, float, List[float]]:
        """Expand [lo, hi] to nice round ticks (1 / 2 / 5 × 10^n steps)."""
        count = max(2, count)
        span = max(1e-6, hi - lo)
        raw_step = span / (count - 1)
        exp = math.floor(math.log10(raw_step)) if raw_step > 0 else 0
        base = 10.0**exp

        def _ticks_for_step(step: float) -> Tuple[float, float, List[float]]:
            nice_lo = math.floor(lo / step) * step
            nice_hi = math.ceil(hi / step) * step
            if nice_hi <= nice_lo:
                nice_hi = nice_lo + step
            ticks: List[float] = []
            v = nice_lo
            while v <= nice_hi + step * 0.01:
                ticks.append(round(v, 10))
                v += step
            return nice_lo, nice_hi, ticks

        # Prefer coarser steps so labels stay sparse (avoid 2.5%-style density).
        step = base * 10.0
        for mult in (1.0, 2.0, 5.0, 10.0):
            cand = mult * base
            if cand >= raw_step * 0.9:
                step = cand
                break

        nice_lo, nice_hi, ticks = _ticks_for_step(step)
        # If still too many labels, bump to the next nice step.
        bump = 0
        while len(ticks) > count and bump < 4:
            bump += 1
            exp2 = math.floor(math.log10(step)) if step > 0 else 0
            b2 = 10.0**exp2
            next_step = step * 2.0
            for mult in (1.0, 2.0, 5.0, 10.0):
                cand = mult * b2
                if cand > step + 1e-12:
                    next_step = cand
                    break
            step = next_step
            nice_lo, nice_hi, ticks = _ticks_for_step(step)

        return nice_lo, nice_hi, ticks

    @staticmethod
    def _series_xy(
        series: Sequence, *, x_from_index: bool = False
    ) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        for i, item in enumerate(series):
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    if item[1] is None:
                        continue
                    x = float(i if x_from_index else item[0])
                    y = float(item[1])
                    if y != y:  # NaN
                        continue
                elif hasattr(item, "accuracy"):
                    x = float(i)
                    y = float(item.accuracy)
                elif hasattr(item, "value"):
                    x = float(i)
                    y = float(item.value)
                else:
                    continue
                pts.append((x, y))
            except Exception:
                continue
        return pts

    def _draw_activity_heatmap(
        self, painter: QPainter, writer, content: QRectF, y: float, stats: Any
    ) -> float:
        pairs = list(getattr(stats, "activity_heatmap_per_game_ordinals", None) or [])
        if not pairs:
            return y

        from datetime import date

        from app.services.player_stats_activity_heatmap_layout import (
            build_activity_heatmap_paint_model,
        )
        from app.services.user_settings_service import UserSettingsService
        from app.views.widgets.player_activity_heatmap_widget import _color_for_count

        try:
            usr = (
                UserSettingsService.get_instance()
                .get_model()
                .get_player_stats_activity_heatmap()
            )
        except Exception:
            usr = {}

        model = build_activity_heatmap_paint_model(
            pairs, usr, date.today().toordinal()
        )
        if model is None or not model.bands:
            return y

        heatmap_cfg = (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("player_stats", {})
            .get("activity_heatmap", {})
        )
        if not isinstance(heatmap_cfg, dict):
            heatmap_cfg = {}
        preset = str(usr.get("color_preset", "ocean_blue") or "ocean_blue")
        # Print page is light — dark UI empty cells would look like filled activity.
        empty_rgb = (232, 234, 238)
        gap = 1.5
        label_w = 28.0
        month_h = 12.0
        band_gap = 10.0

        max_cols = max(b.n_cols for b in model.bands)
        avail = max(40.0, content.width() - label_w)
        cell = min(
            float(self._heatmap_cell),
            avail / max(1, max_cols) - gap,
        )
        cell = max(4.0, cell)

        grid_h = 0.0
        for i, band in enumerate(model.bands):
            if i:
                grid_h += band_gap
            grid_h += month_h + band.n_rows * (cell + gap)

        y = self._section_heading(
            painter, writer, content, y, "Activity Heatmap", keep_with=grid_h + 24
        )
        if model.subcaption:
            y = self._draw_text_line(
                painter,
                model.subcaption,
                content.left(),
                y,
                content.width(),
                self._font_caption,
                self._muted,
            )
            y += 2.0

        y, _ = self._ensure_space(painter, writer, content, y, grid_h + 8)
        grid_ox = content.left() + label_w
        band_y = y

        for bi, band in enumerate(model.bands):
            if bi:
                band_y += band_gap
            # Month labels
            painter.setPen(self._muted)
            painter.setFont(self._font_caption)
            for i, (col, lab) in enumerate(band.month_label_bands[0] if band.month_label_bands else ()):
                x0 = grid_ox + col * (cell + gap)
                if i + 1 < len(band.month_label_bands[0]):
                    c_next = band.month_label_bands[0][i + 1][0]
                    w = max(1.0, (c_next - col) * (cell + gap) - gap)
                else:
                    w = max(1.0, band.n_cols * (cell + gap) - gap - col * (cell + gap))
                painter.drawText(
                    QRectF(x0, band_y, w, month_h),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    lab,
                )
            cells_top = band_y + month_h

            # Weekday labels (first band only typically has them)
            if band.row_labels:
                for r, lab in enumerate(band.row_labels):
                    cy = cells_top + r * (cell + gap)
                    painter.setPen(self._muted)
                    painter.setFont(self._font_caption)
                    painter.drawText(
                        QRectF(content.left(), cy, label_w - 4.0, cell),
                        int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                        lab,
                    )

            # Cells
            for r in range(band.n_rows):
                for c in range(band.n_cols):
                    cnt = band.counts[r][c] if r < len(band.counts) and c < len(band.counts[r]) else 0
                    # Skip out-of-range padding cells (ordinal < 0)
                    ord_v = -1
                    if r < len(band.cell_ordinals) and c < len(band.cell_ordinals[r]):
                        ord_v = int(band.cell_ordinals[r][c])
                    if ord_v < 0:
                        continue
                    fill = _color_for_count(
                        int(cnt), model.scale_max, heatmap_cfg, preset, empty_rgb
                    )
                    rect = QRectF(
                        grid_ox + c * (cell + gap),
                        cells_top + r * (cell + gap),
                        cell,
                        cell,
                    )
                    painter.fillRect(rect, fill)

            # Month start dividers (week-aligned)
            painter.setPen(QPen(self._rule, 1.0))
            cells_bottom = cells_top + band.n_rows * (cell + gap) - gap
            for c in band.month_start_columns:
                if c <= 0:
                    continue
                x = grid_ox + c * (cell + gap) - gap / 2.0
                painter.drawLine(
                    int(x), int(cells_top), int(x), int(cells_bottom)
                )

            band_y = cells_bottom + 2.0

        return band_y + 8.0

    def _draw_multicolumn_table(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        headers: Sequence[str],
        rows: Sequence[Tuple[int, bool, Sequence[str]]],
        *,
        col_weights: Optional[Sequence[float]] = None,
        row_height: float = 14.0,
        numeric_cols: Optional[Sequence[int]] = None,
    ) -> float:
        """Draw a zebra table. Each row is (indent_level, bold, cell_texts)."""
        if not headers or not rows:
            return y
        n = len(headers)
        weights = list(col_weights) if col_weights and len(col_weights) == n else None
        if weights is None:
            weights = [0.40] + [0.60 / (n - 1)] * (n - 1) if n > 1 else [1.0]
        total_w = float(sum(weights)) or 1.0
        weights = [w / total_w for w in weights]
        col_ws = [content.width() * w for w in weights]
        num_set = set(numeric_cols or range(1, n))
        zebra = QColor(250, 250, 252)
        indent_px = 12.0

        body = row_height * (len(rows) + 1) + 4
        y, _ = self._ensure_space(painter, writer, content, y, body)

        painter.fillRect(QRectF(content.left(), y, content.width(), row_height), self._card)
        painter.setFont(self._font_body)
        painter.setPen(self._muted)
        x = content.left()
        for i, header in enumerate(headers):
            align = (
                Qt.AlignmentFlag.AlignCenter
                if i in num_set
                else Qt.AlignmentFlag.AlignLeft
            )
            pad = 4.0 if i == 0 else 2.0
            painter.drawText(
                QRectF(x + pad, y, col_ws[i] - pad * 2, row_height),
                align | Qt.AlignmentFlag.AlignVCenter,
                self._elide(header, self._font_body, col_ws[i] - pad * 2),
            )
            x += col_ws[i]
        y += row_height + 1.0

        for index, (indent, bold, cells) in enumerate(rows):
            y, _ = self._ensure_space(painter, writer, content, y, row_height)
            if index % 2 == 0:
                painter.fillRect(
                    QRectF(content.left(), y, content.width(), row_height), zebra
                )
            font = self._font_body_bold if bold else self._font_body
            painter.setFont(font)
            x = content.left()
            for i in range(n):
                text = cells[i] if i < len(cells) else ""
                if i == 0:
                    left_pad = 4.0 + indent_px * max(0, int(indent))
                    align = Qt.AlignmentFlag.AlignLeft
                    painter.setPen(self._text if bold else self._muted)
                else:
                    left_pad = 2.0
                    align = (
                        Qt.AlignmentFlag.AlignCenter
                        if i in num_set
                        else Qt.AlignmentFlag.AlignLeft
                    )
                    painter.setPen(self._text)
                avail = col_ws[i] - left_pad - 2.0
                painter.drawText(
                    QRectF(x + left_pad, y, max(8.0, avail), row_height),
                    align | Qt.AlignmentFlag.AlignVCenter,
                    self._elide(str(text), font, avail),
                )
                x += col_ws[i]
            y += row_height
        return y + 6.0

    @staticmethod
    def _fmt_tree_acc(sum_v: float, count: int) -> str:
        if count <= 0:
            return "—"
        return f"{sum_v / float(count):.1f}%"

    @staticmethod
    def _opening_node_label(san: str, node: Dict[str, Any]) -> str:
        eco = node.get("eco")
        name = node.get("opening_name")
        if name and eco:
            return f"{san} – {eco} ({name})"
        if name:
            return f"{san} – {name}"
        if eco:
            return f"{san} – {eco}"
        return str(san)

    def _opening_tree_table_rows(
        self, tree_data: Optional[Dict[str, Any]]
    ) -> List[Tuple[int, bool, Tuple[str, str, str, str, str, str]]]:
        """Flatten first two plies of the opening tree into table rows."""
        rows: List[Tuple[int, bool, Tuple[str, str, str, str, str, str]]] = []
        if not isinstance(tree_data, dict):
            return rows
        children = tree_data.get("children") or {}
        if not isinstance(children, dict) or not children:
            return rows

        sorted_roots = sorted(
            children.items(),
            key=lambda kv: int(kv[1].get("games", 0) or 0) if isinstance(kv[1], dict) else 0,
            reverse=True,
        )
        max_roots = max(1, self._max_tree_rows // 4)
        max_replies = 3
        for root_i, (san_root, root_node) in enumerate(sorted_roots):
            if root_i >= max_roots or len(rows) >= self._max_tree_rows:
                break
            if not isinstance(root_node, dict):
                continue
            total = int(root_node.get("games", 0) or 0)
            if total <= 0:
                continue
            white = int(root_node.get("white_games", 0) or 0)
            black = int(root_node.get("black_games", 0) or 0)
            g_sum = float(root_node.get("game_accuracy_sum", 0.0) or 0.0)
            g_cnt = int(root_node.get("game_accuracy_count", 0) or 0)
            p_sum = float(root_node.get("opening_accuracy_sum", 0.0) or 0.0)
            p_cnt = int(root_node.get("opening_accuracy_count", 0) or 0)
            rows.append(
                (
                    0,
                    True,
                    (
                        self._opening_node_label(str(san_root), root_node),
                        str(total),
                        str(white),
                        str(black),
                        self._fmt_tree_acc(g_sum, g_cnt),
                        self._fmt_tree_acc(p_sum, p_cnt),
                    ),
                )
            )
            replies = root_node.get("children") or {}
            if not isinstance(replies, dict):
                continue
            sorted_replies = sorted(
                replies.items(),
                key=lambda kv: int(kv[1].get("games", 0) or 0)
                if isinstance(kv[1], dict)
                else 0,
                reverse=True,
            )
            for reply_i, (san_reply, reply_node) in enumerate(sorted_replies):
                if reply_i >= max_replies or len(rows) >= self._max_tree_rows:
                    break
                if not isinstance(reply_node, dict):
                    continue
                r_total = int(reply_node.get("games", 0) or 0)
                if r_total <= 0:
                    continue
                r_white = int(reply_node.get("white_games", 0) or 0)
                r_black = int(reply_node.get("black_games", 0) or 0)
                rg_sum = float(reply_node.get("game_accuracy_sum", 0.0) or 0.0)
                rg_cnt = int(reply_node.get("game_accuracy_count", 0) or 0)
                rp_sum = float(reply_node.get("opening_accuracy_sum", 0.0) or 0.0)
                rp_cnt = int(reply_node.get("opening_accuracy_count", 0) or 0)
                rows.append(
                    (
                        1,
                        False,
                        (
                            self._opening_node_label(str(san_reply), reply_node),
                            str(r_total),
                            str(r_white),
                            str(r_black),
                            self._fmt_tree_acc(rg_sum, rg_cnt),
                            self._fmt_tree_acc(rp_sum, rp_cnt),
                        ),
                    )
                )
        return rows

    def _endgame_tree_table_rows(
        self, stats: Any
    ) -> List[Tuple[int, bool, Tuple[str, str, str, str, str, str]]]:
        rows: List[Tuple[int, bool, Tuple[str, str, str, str, str, str]]] = []
        grouped = getattr(stats, "accuracy_by_endgame_type_grouped", None) or []
        max_groups = 6
        max_types = 4
        for gi, group in enumerate(grouped):
            if gi >= max_groups or len(rows) >= self._max_tree_rows:
                break
            try:
                (
                    _gkey,
                    group_label,
                    group_endgame_accuracy,
                    group_game_accuracy,
                    group_count,
                    group_white,
                    group_black,
                    types_list,
                ) = group
            except Exception:
                continue
            if int(group_count) <= 0:
                continue
            rows.append(
                (
                    0,
                    True,
                    (
                        str(group_label),
                        str(int(group_count)),
                        str(int(group_white)),
                        str(int(group_black)),
                        f"{float(group_game_accuracy):.1f}%",
                        f"{float(group_endgame_accuracy):.1f}%",
                    ),
                )
            )
            for ti, t in enumerate(types_list or []):
                if ti >= max_types or len(rows) >= self._max_tree_rows:
                    break
                try:
                    (
                        _raw,
                        type_label,
                        type_endgame_accuracy,
                        type_game_accuracy,
                        type_count,
                        type_white,
                        type_black,
                    ) = t
                except Exception:
                    continue
                if int(type_count) <= 0:
                    continue
                rows.append(
                    (
                        1,
                        False,
                        (
                            str(type_label),
                            str(int(type_count)),
                            str(int(type_white)),
                            str(int(type_black)),
                            f"{float(type_game_accuracy):.1f}%",
                            f"{float(type_endgame_accuracy):.1f}%",
                        ),
                    )
                )
        return rows

    def _draw_opening_tree(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        *,
        opening_tree_data: Optional[Dict[str, Any]],
        opening_tree_summary_lines: Optional[List[str]],
    ) -> float:
        rows = self._opening_tree_table_rows(opening_tree_data)
        if not rows and opening_tree_summary_lines:
            return self._draw_text_section(
                painter,
                writer,
                content,
                y,
                "Opening Tree (first 2 moves)",
                list(opening_tree_summary_lines)[: self._max_tree_rows],
            )
        if not rows:
            return y
        headers = ("Move / Opening", "Total", "White", "Black", "Game Acc", "Phase Acc")
        body = 16 + 15 * (len(rows) + 1)
        y = self._section_heading(
            painter, writer, content, y, "Opening Tree (first 2 moves)", keep_with=body
        )
        return self._draw_multicolumn_table(
            painter,
            writer,
            content,
            y,
            headers,
            rows,
            col_weights=(0.42, 0.10, 0.10, 0.10, 0.14, 0.14),
            numeric_cols=(1, 2, 3, 4, 5),
        )

    def _draw_endgame_tree(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        stats: Any,
    ) -> float:
        rows = self._endgame_tree_table_rows(stats)
        if not rows:
            return y
        headers = ("Endgame type", "Total", "White", "Black", "Game Acc", "Phase Acc")
        body = 16 + 15 * (len(rows) + 1)
        y = self._section_heading(
            painter, writer, content, y, "Endgame Tree", keep_with=body
        )
        return self._draw_multicolumn_table(
            painter,
            writer,
            content,
            y,
            headers,
            rows,
            col_weights=(0.42, 0.10, 0.10, 0.10, 0.14, 0.14),
            numeric_cols=(1, 2, 3, 4, 5),
        )

    @staticmethod
    def _acc_range_caption(rows: Sequence[Dict[str, Any]]) -> str:
        vals = [
            float(r["accuracy"])
            for r in rows
            if isinstance(r, dict) and r.get("accuracy") is not None
        ]
        if not vals:
            return ""
        lo, hi = min(vals), max(vals)
        if abs(lo - hi) < 0.05:
            return f"Accuracy {lo:.1f}%"
        return f"Accuracy {lo:.1f}–{hi:.1f}%"

    def _performance_table_rows(
        self, games: Sequence[Dict[str, Any]]
    ) -> List[Tuple[int, bool, Tuple[str, str, str, str, str, str, str]]]:
        out: List[Tuple[int, bool, Tuple[str, str, str, str, str, str, str]]] = []
        for g in games:
            if not isinstance(g, dict):
                continue
            acc = g.get("accuracy")
            acpl = g.get("acpl")
            out.append(
                (
                    0,
                    False,
                    (
                        str(g.get("date") or "—"),
                        str(g.get("opponent") or "—"),
                        str(g.get("color") or "—"),
                        str(g.get("result") or "—"),
                        str(g.get("eco") or "—"),
                        f"{float(acc):.1f}%" if acc is not None else "—",
                        f"{float(acpl):.1f}" if acpl is not None else "—",
                    ),
                )
            )
        return out

    def _draw_games_block(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        *,
        title: str,
        subtitle: str,
        games: Sequence[Dict[str, Any]],
    ) -> float:
        rows = self._performance_table_rows(games)
        if not rows:
            return y
        headers = ("Date", "Opponent", "Color", "Result", "ECO", "Acc", "ACPL")
        keep = 14 + 15 * (len(rows) + 1) + (12 if subtitle else 0)
        y, _ = self._ensure_space(painter, writer, content, y, keep)

        painter.setFont(self._font_body_bold)
        painter.setPen(self._text)
        painter.drawText(
            QRectF(content.left(), y, content.width(), 14.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        y += 14.0
        if subtitle:
            painter.setFont(self._font_caption)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(content.left(), y, content.width(), 12.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                subtitle,
            )
            y += 12.0

        return self._draw_multicolumn_table(
            painter,
            writer,
            content,
            y,
            headers,
            rows,
            col_weights=(0.14, 0.30, 0.09, 0.09, 0.08, 0.12, 0.10),
            numeric_cols=(2, 3, 4, 5, 6),
        )

    def _draw_games_by_performance(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        *,
        games_by_performance: Optional[Dict[str, List[Dict[str, Any]]]],
        top_games_summary: Optional[
            Tuple[int, Optional[float], Optional[float], int, Optional[float], Optional[float]]
        ],
    ) -> float:
        payload = games_by_performance if isinstance(games_by_performance, dict) else {}
        best = list(payload.get("best") or [])
        worst = list(payload.get("worst") or [])

        if not best and not worst:
            if top_games_summary is None:
                return y
            lines = PlayerStatsTextFormatter._format_top_games(*top_games_summary)
            return self._draw_text_section(
                painter,
                writer,
                content,
                y,
                "Games by Performance",
                lines[2:] if len(lines) > 2 else lines,
            )

        body_rows = len(best) + len(worst) + (2 if best else 0) + (2 if worst else 0)
        y = self._section_heading(
            painter,
            writer,
            content,
            y,
            "Games by Performance",
            keep_with=16 + 15 * max(1, body_rows),
        )

        if best:
            cap = self._acc_range_caption(best)
            subtitle = "Lowest CPL"
            if cap:
                subtitle = f"{subtitle} · {cap}"
            y = self._draw_games_block(
                painter,
                writer,
                content,
                y,
                title="Best Games",
                subtitle=subtitle,
                games=best,
            )

        if worst:
            cap = self._acc_range_caption(worst)
            subtitle = "Highest CPL"
            if cap:
                subtitle = f"{subtitle} · {cap}"
            y = self._draw_games_block(
                painter,
                writer,
                content,
                y,
                title="Worst Games",
                subtitle=subtitle,
                games=worst,
            )
        return y

    def _draw_openings(
        self, painter: QPainter, writer, content: QRectF, y: float, stats: Any
    ) -> float:
        """Openings as miniature-board cards (game-report highlight style)."""
        groups: List[Tuple[str, List[Tuple[str, Optional[str], Optional[float], int]]]] = []
        if stats.top_openings:
            groups.append(
                (
                    "Most Played",
                    [
                        (eco, name, None, int(count))
                        for eco, name, count in stats.top_openings[
                            : self._max_opening_rows
                        ]
                    ],
                )
            )
        if stats.worst_accuracy_openings:
            groups.append(
                (
                    "Worst Accuracy",
                    [
                        (eco, name, float(cpl), int(count))
                        for eco, name, cpl, count in stats.worst_accuracy_openings[
                            : self._max_opening_rows
                        ]
                    ],
                )
            )
        if stats.best_accuracy_openings:
            groups.append(
                (
                    "Best Accuracy",
                    [
                        (eco, name, float(cpl), int(count))
                        for eco, name, cpl, count in stats.best_accuracy_openings[
                            : self._max_opening_rows
                        ]
                    ],
                )
            )
        if not groups:
            return y

        board = max(48.0, min(self._opening_board_size, content.width() * 0.22))
        # Estimate first group keep-with
        first_n = len(groups[0][1])
        cols = min(3, max(1, first_n))
        card_h = board + 48.0
        y = self._section_heading(
            painter,
            writer,
            content,
            y,
            "Openings",
            keep_with=18 + card_h + 8,
        )

        for gi, (group_title, rows) in enumerate(groups):
            if not rows:
                continue
            y, _ = self._ensure_space(
                painter, writer, content, y, 16 + card_h + 8
            )
            if gi:
                y += 6.0
            painter.setFont(self._font_body_bold)
            painter.setPen(self._muted)
            fm = QFontMetrics(self._font_body_bold)
            painter.drawText(
                int(content.left()), int(y + fm.ascent()), group_title
            )
            y += float(fm.height()) + 6.0
            y = self._draw_opening_card_row(
                painter, writer, content, y, rows, board_display=board
            )
        return y + 4.0

    def _opening_svc(self) -> OpeningService:
        if self._opening_service is None:
            self._opening_service = OpeningService(self.config)
            self._opening_service.load()
        return self._opening_service

    def _render_opening_board(self, fen: str, size: int) -> Optional[QPixmap]:
        return self._render_move_board(fen, "", "", size=size)

    def _render_move_board(
        self,
        fen: str,
        fen_before: str,
        san: str,
        *,
        size: int,
    ) -> Optional[QPixmap]:
        """Rasterize a mini board; optionally highlight the last move from fen_before+san."""
        if chess is None:
            return None
        scale = self._board_render_scale
        try:
            widget = MiniChessBoardWidget(
                self.config,
                fen or chess.STARTING_FEN,
                embedded=True,
                size_override=int(size * scale),
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
        except Exception:
            return None

    def _draw_opening_card_row(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        rows: Sequence[Tuple[str, Optional[str], Optional[float], int]],
        *,
        board_display: float,
    ) -> float:
        """Draw up to 3 opening cards per row (board + ECO / name / meta)."""
        gap = 8.0
        pad = 6.0
        n = len(rows)
        cols = min(3, max(1, n))
        card_w = (content.width() - gap * (cols - 1)) / cols
        caption_h = 42.0
        card_h = pad * 2 + board_display + 4.0 + caption_h

        row_y = y
        for idx, (eco, name, cpl, count) in enumerate(rows):
            col = idx % cols
            if col == 0 and idx > 0:
                row_y += card_h + gap
            if col == 0:
                row_y, _ = self._ensure_space(
                    painter, writer, content, row_y, card_h + 4
                )

            x = content.left() + col * (card_w + gap)
            card = QRectF(x, row_y, card_w, card_h)
            painter.setPen(QPen(self._rule, 0.7))
            painter.setBrush(self._card)
            painter.drawRoundedRect(card, 4, 4)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            eco_key = str(eco or "").strip().upper()
            bs = int(round(board_display))
            board_x = int(round(x + (card_w - bs) / 2.0))
            board_y = int(round(row_y + pad))
            board_rect = QRectF(board_x, board_y, bs, bs)

            if eco_key == "A00":
                # Irregular / unspecified — starting board with a clear "?" marker.
                pix = (
                    self._render_opening_board(chess.STARTING_FEN, bs)
                    if chess is not None
                    else None
                )
                painter.save()
                painter.setClipRect(board_rect)
                if pix is not None and not pix.isNull():
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    # Stretch to the exact target so wash/"?" share the same edges
                    # (avoids left/bottom gaps from supersample size mismatch).
                    painter.drawPixmap(
                        board_rect,
                        pix,
                        QRectF(0, 0, pix.width(), pix.height()),
                    )
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawRect(board_rect)
                wash = QColor(255, 255, 255, 160)
                painter.fillRect(board_rect, wash)
                q_font = QFont(self._font_title)
                q_font.setPointSize(max(18, int(bs * 0.42)))
                q_font.setBold(True)
                painter.setFont(q_font)
                painter.setPen(self._muted)
                painter.drawText(board_rect, int(Qt.AlignmentFlag.AlignCenter), "?")
                painter.restore()
            else:
                fen = self._opening_svc().find_representative_fen(eco, name)
                pix = self._render_opening_board(fen, bs) if fen else None
                if pix is not None and not pix.isNull():
                    painter.save()
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.setClipRect(board_rect)
                    painter.drawPixmap(
                        board_rect,
                        pix,
                        QRectF(0, 0, pix.width(), pix.height()),
                    )
                    painter.restore()
                else:
                    painter.setPen(QPen(self._rule, 0.8))
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawRect(board_rect)
                    painter.setPen(self._muted)
                    painter.setFont(self._font_caption)
                    painter.drawText(
                        board_rect,
                        int(Qt.AlignmentFlag.AlignCenter),
                        eco or "—",
                    )

            text_top = board_y + bs + 4.0
            text_w = card_w - pad * 2
            eco_s = str(eco or "—")
            name_s = str(name or "").strip() or "—"
            if cpl is None:
                meta = f"{count} game{'s' if count != 1 else ''}"
            else:
                meta = f"Avg CPL {cpl:.1f} · {count} game{'s' if count != 1 else ''}"

            painter.setFont(self._font_body_bold)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(x + pad, text_top, text_w, 12),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._elide(eco_s, self._font_body_bold, text_w),
            )
            painter.setFont(self._font_caption)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(x + pad, text_top + 12, text_w, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._elide(name_s, self._font_caption, text_w),
            )
            painter.drawText(
                QRectF(x + pad, text_top + 26, text_w, 12),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._elide(meta, self._font_caption, text_w),
            )

        return row_y + card_h + 4.0

    def _draw_significant_moves(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        *,
        significant_moves: Optional[Dict[str, List[Dict[str, Any]]]],
        stats: Any,
    ) -> float:
        payload = significant_moves if isinstance(significant_moves, dict) else {}
        categories: List[Tuple[str, str, List[Dict[str, Any]]]] = [
            ("Brilliant", "Brilliant", list(payload.get("brilliant") or [])),
            ("Misses", "Miss", list(payload.get("misses") or [])),
            ("Blunders", "Blunder", list(payload.get("blunders") or [])),
        ]
        categories = [(title, key, rows) for title, key, rows in categories if rows]
        if not categories:
            ps = getattr(stats, "player_stats", None)
            if ps is None:
                return y
            kv = [
                ("Brilliant moves", str(getattr(ps, "brilliant_moves", 0) or 0)),
                ("Misses", str(getattr(ps, "misses", 0) or 0)),
                ("Blunders", str(getattr(ps, "blunders", 0) or 0)),
            ]
            if not any(int(v) > 0 for _, v in kv if str(v).isdigit()):
                return y
            return self._draw_kv_section(
                painter, writer, content, y, "Significant Moves", kv
            )

        board = max(
            48.0,
            min(self._significant_move_board_size, content.width() * 0.28),
        )
        card_h = board + 12.0
        y = self._section_heading(
            painter,
            writer,
            content,
            y,
            "Significant Moves",
            keep_with=18 + card_h,
        )

        for title, assess_key, games in categories:
            y, _ = self._ensure_space(painter, writer, content, y, 16 + card_h)
            swatch = 8.0
            color = self._assess_colors.get(assess_key, self._text)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(content.left(), y + 3.0, swatch, swatch))
            painter.setFont(self._font_body_bold)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(
                    content.left() + swatch + 6.0,
                    y,
                    content.width() - swatch - 6.0,
                    14.0,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title,
            )
            y += 16.0

            for g in games:
                if not isinstance(g, dict):
                    continue
                y = self._draw_significant_move_card(
                    painter,
                    writer,
                    content,
                    y,
                    g,
                    assess_key=assess_key,
                    board_display=board,
                )
            y += 4.0
        return y

    def _draw_significant_move_card(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        move: Dict[str, Any],
        *,
        assess_key: str,
        board_display: float,
    ) -> float:
        """Highlight-style card: mini board left, move + game meta right."""
        pad = 6.0
        gap = 10.0
        card_h = board_display + pad * 2
        y, _ = self._ensure_space(painter, writer, content, y, card_h + 4)

        card = QRectF(content.left(), y, content.width(), card_h)
        painter.setPen(QPen(self._rule, 0.7))
        painter.setBrush(self._card)
        painter.drawRoundedRect(card, 4, 4)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        fen = str(move.get("fen") or "").strip()
        fen_before = str(move.get("fen_before") or "").strip()
        san = str(move.get("san") or "").strip()
        bs = int(round(board_display))
        board_x = content.left() + pad
        board_y = y + pad

        pix = (
            self._render_move_board(fen, fen_before, san, size=bs)
            if fen
            else None
        )
        if pix is not None and not pix.isNull():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(
                QRectF(board_x, board_y, bs, bs),
                pix,
                QRectF(0, 0, pix.width(), pix.height()),
            )
            painter.restore()
        else:
            painter.setPen(self._muted)
            painter.setFont(self._font_caption)
            painter.drawText(
                QRectF(board_x, board_y, bs, bs),
                int(Qt.AlignmentFlag.AlignCenter),
                "No board",
            )

        text_x = board_x + board_display + gap
        text_w = max(60.0, content.right() - pad - text_x)
        ty = y + pad

        move_text = str(move.get("move") or "—")
        painter.setFont(self._font_body_bold)
        painter.setPen(self._text)
        painter.drawText(
            QRectF(text_x, ty, text_w, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(move_text, self._font_body_bold, text_w),
        )
        ty += 16.0

        cpl = move.get("cpl")
        assess_color = self._assess_colors.get(assess_key, self._muted)
        meta_bits = [assess_key]
        if cpl is not None:
            meta_bits.append(f"CPL {float(cpl):.0f}")
        painter.setFont(self._font_caption)
        painter.setPen(assess_color)
        painter.drawText(
            QRectF(text_x, ty, text_w, 13),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(" · ".join(meta_bits), self._font_caption, text_w),
        )
        ty += 14.0

        painter.setPen(self._muted)
        opponent = str(move.get("opponent") or "—")
        color = str(move.get("color") or "—")
        date_s = str(move.get("date") or "—")
        for line in (
            f"vs {opponent}",
            f"{color} · {date_s}",
        ):
            painter.drawText(
                QRectF(text_x, ty, text_w, 12),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._elide(line, self._font_caption, text_w),
            )
            ty += 12.0

        return y + card_h + 4.0

    _SEVERITY_RANK = {
        "critical": 0,
        "high": 1,
        "moderate": 2,
        "low": 3,
    }

    _PATTERN_TYPE_LABELS = {
        "phase_blunders": "Phase",
        "tactical_misses": "Tactics",
        "opening_errors": "Opening",
        "high_cpl": "High CPL",
        "missed_top3": "Missed top 3",
        "conversion_issues": "Conversion",
        "defensive_weaknesses": "Defense",
        "consistent_inaccuracies": "Inaccuracies",
        "repeated_blunders_same_position": "Repeated position",
        "repeated_mistakes_same_position": "Repeated position",
        "repeated_misses_same_position": "Repeated position",
        "repeated_inaccuracies_same_position": "Repeated position",
    }

    def _error_pattern_freq_text(self, pattern: Any) -> str:
        ref_plies = getattr(pattern, "related_ref_plies", None)
        pct = float(getattr(pattern, "percentage", 0.0) or 0.0)
        if ref_plies:
            n_occ = len(ref_plies)
            n_games = len(getattr(pattern, "related_games", None) or [])
            return (
                f"{n_occ} occurrence{'s' if n_occ != 1 else ''} in "
                f"{n_games} game{'s' if n_games != 1 else ''} · {pct:.1f}%"
            )
        freq = int(getattr(pattern, "frequency", 0) or 0)
        return f"{freq} occurrence{'s' if freq != 1 else ''} · {pct:.1f}%"

    def _draw_error_patterns(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        patterns: Sequence[Any],
    ) -> float:
        items = [p for p in patterns if p is not None]
        if not items:
            return y

        items.sort(
            key=lambda p: (
                self._SEVERITY_RANK.get(
                    str(getattr(p, "severity", "") or "").lower(), 9
                ),
                -float(getattr(p, "percentage", 0.0) or 0.0),
            )
        )
        items = items[: self._max_error_patterns]

        y = self._section_heading(
            painter,
            writer,
            content,
            y,
            "Error Patterns",
            keep_with=40,
        )

        pad = 6.0
        swatch = 8.0
        gap = 8.0
        wrap_flags = int(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        ) | int(Qt.TextFlag.TextWordWrap)

        for pattern in items:
            severity = str(getattr(pattern, "severity", "") or "").lower()
            color = self._severity_colors.get(
                severity, self._severity_colors["default"]
            )
            description = str(getattr(pattern, "description", "") or "").strip() or "—"
            type_key = str(getattr(pattern, "pattern_type", "") or "")
            type_label = self._PATTERN_TYPE_LABELS.get(
                type_key,
                type_key.replace("_", " ").strip().title() if type_key else "",
            )
            freq_text = self._error_pattern_freq_text(pattern)
            meta_bits = [b for b in (type_label, freq_text) if b]
            meta = " · ".join(meta_bits)

            text_x = content.left() + pad + swatch + gap
            text_w = max(60.0, content.right() - pad - text_x)

            painter.setFont(self._font_body)
            desc_bound = painter.boundingRect(
                QRectF(0, 0, text_w, 200), wrap_flags, description
            )
            painter.setFont(self._font_caption)
            meta_h = float(QFontMetrics(self._font_caption).height()) + 2.0
            row_h = max(swatch + 4.0, float(desc_bound.height()) + 4.0 + meta_h) + pad * 2

            y, _ = self._ensure_space(painter, writer, content, y, row_h + 3)

            card = QRectF(content.left(), y, content.width(), row_h)
            painter.setPen(QPen(self._rule, 0.7))
            painter.setBrush(self._card)
            painter.drawRoundedRect(card, 4, 4)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                QRectF(
                    content.left() + pad,
                    y + pad + 2.0,
                    swatch,
                    swatch,
                )
            )

            ty = y + pad
            painter.setFont(self._font_body)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(text_x, ty, text_w, float(desc_bound.height()) + 4),
                wrap_flags,
                description,
            )
            ty += float(desc_bound.height()) + 4.0

            painter.setFont(self._font_caption)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(text_x, ty, text_w, meta_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._elide(meta, self._font_caption, text_w),
            )

            y += row_h + 4.0

        return y


def default_player_stats_pdf_filename(player_name: Optional[str] = None) -> str:
    """Suggest a download filename for the player-stats report."""
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    name = (player_name or "Player").strip().replace(" ", "_")
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, "")
    return f"CARA-PlayerStats-{name}-{stamp}.pdf"

"""PDF export service for Chess Log — tags dialogs and the Charts page."""

from __future__ import annotations


from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chess

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from app.models.chess_log_snapshot import TagRowSnapshot
from app.services.chess_log_narrative_service import sanitize_narrative_markdown
from app.services.chess_log_stats_service import shallow_flag_label
from app.services.chess_log_storage_service import ChessLogStorageService
from app.services.pdf_report_base import BasePDFReportService
from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS as _3X3_PROMPTS


def default_chess_log_tags_pdf_filename(*, is_shallow_only: bool = False) -> str:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    kind = "CheckLogs" if is_shallow_only else "AllGames"
    return f"CARA-ChessLog-{kind}-{ts}.pdf"


def default_chess_log_charts_pdf_filename(player_name: str = "") -> str:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in player_name)[:40]
    return f"CARA-ChessLogCharts-{safe}-{ts}.pdf" if safe else f"CARA-ChessLogCharts-{ts}.pdf"


def default_chess_log_narrative_pdf_filename(player_name: str = "") -> str:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in player_name)[:40]
    return (
        f"CARA-ChessLogNarrativeSummary-{safe}-{ts}.pdf" if safe
        else f"CARA-ChessLogNarrativeSummary-{ts}.pdf"
    )


class ChessLogPDFService(BasePDFReportService):
    """PDF report for Chess Log tags (dialogs) and the Charts page."""

    _BOARD_RENDER_SCALE = 4
    _BOARD_DISPLAY_PT = 100.0
    _ROW_PAD = 8.0
    _ROW_GAP = 6.0

    def __init__(self, config: Dict[str, Any]) -> None:
        report_cfg = (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("chess_log_charts", {})
            .get("pdf_report", {})
        )
        if not isinstance(report_cfg, dict):
            report_cfg = {}
        super().__init__(config, report_cfg)
        _cl_card_raw = config.get("ui", {}).get("pdf", {}).get("chess_log", {}).get("card_fill")
        if _cl_card_raw is not None:
            self._card = self._rgb(_cl_card_raw, (255, 255, 255))
        _warn_colors = (self._cfg.get("colors") or {})
        self._warn_fill = self._rgb(_warn_colors.get("warning_fill"), (241, 196, 15))
        self._warn_outline = self._rgb(_warn_colors.get("warning_outline"), (30, 30, 30))
        raw_pct = self._cfg.get("table_col_widths_pct")
        if isinstance(raw_pct, (list, tuple)) and len(raw_pct) == 3:
            self._table_col_pct = [float(v) / 100.0 for v in raw_pct]
        else:
            self._table_col_pct = [0.20, 0.40, 0.40]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _draw_source_generated_lines(
        self,
        painter: QPainter,
        content: QRectF,
        y: float,
        source_label: str,
        generated_str: str,
    ) -> float:
        """Draw the Source and Generated metadata lines (shared by all report types)."""
        if source_label:
            y = self._draw_text_line(
                painter, f"Source: {source_label}",
                content.left(), y, content.width(),
                self._font_body, self._muted,
            )
        y = self._draw_text_line(
            painter, generated_str,
            content.left(), y, content.width(),
            self._font_body, self._muted,
        )
        return y

    def export_tags(
        self,
        path: Path,
        tag_groups: List[Dict[str, Any]],
        *,
        is_shallow_only: bool = False,
        source_label: str = "",
        model_label: str = "",
        generated_at: str = "",
    ) -> bool:
        """Write tag rows from a Show-Tags dialog to a PDF."""
        painter = None
        try:
            writer = self._create_pdf_writer(path)
            painter = QPainter(writer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            content = self._content_rect(writer)
            self._page_number = 1
            self._draw_page_chrome(painter, content)
            title = "Chess Log — Check Logs" if is_shallow_only else "Chess Log — Logged Moments"
            y = self._draw_report_header(painter, content, title)
            if is_shallow_only:
                generated_str = (
                    f"Generated: {generated_at}"
                    if generated_at
                    else datetime.now().strftime("Generated: %Y-%m-%d %H:%M")
                )
                y = self._draw_source_generated_lines(painter, content, y, source_label, generated_str)
                ai_label = model_label if model_label else "not run (chips from earlier checks)"
                y = self._draw_text_line(
                    painter, f"AI model: {ai_label}",
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
                y += 6.0

            for group in tag_groups:
                header_text = group.get("header")
                rows: List[TagRowSnapshot] = group.get("rows", [])
                if not rows:
                    continue
                if header_text:
                    first_row_h = self._measure_tag_row_height(painter, content, rows[0])
                    y = self._section_heading(
                        painter, writer, content, y, header_text,
                        keep_with=first_row_h + self._ROW_GAP,
                    )
                for row in rows:
                    y = self._draw_tag_row(painter, writer, content, y, row)

            painter.end()
            return True
        except Exception as exc:
            try:
                from app.services.logging_service import LoggingService
                LoggingService.get_instance().error(
                    f"ChessLogPDFService.export_tags error: {exc}", exc_info=exc
                )
            except Exception:
                pass
            if painter is not None:
                try:
                    painter.end()
                except Exception:
                    pass
            return False

    def export_charts_report(
        self,
        path: Path,
        player_name: str,
        source_label: str,
        chart_pixmaps: List[Tuple[str, QPixmap]],
        narrative_text: str,
        shallow_rows: List[TagRowSnapshot],
        *,
        model_label: str = "",
        generated_at: str = "",
        n_games: int = 0,
        g_games: int = 0,
        m_moments: int = 0,
        s_flagged: int = 0,
        has_3x3: bool = False,
    ) -> bool:
        """Write Chess Log Charts page (charts + narrative + optional shallow rows) to a PDF."""
        painter = None
        try:
            writer = self._create_pdf_writer(path)
            painter = QPainter(writer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            content = self._content_rect(writer)
            self._page_number = 1
            self._draw_page_chrome(painter, content)

            display_name = player_name or "Chess Log"
            title = f"Chess Log Charts — {display_name}"
            y = self._draw_report_header(painter, content, title)
            if player_name:
                y = self._draw_text_line(
                    painter, f"Player: {player_name}",
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
            if source_label:
                y = self._draw_text_line(
                    painter, f"Source: {source_label}",
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
            narrative = (narrative_text or "").strip()
            if narrative:
                counts_line = (
                    f"{n_games} games · {g_games} with logged moments "
                    f"· {m_moments} moments · {s_flagged} {shallow_flag_label(has_3x3)}"
                )
                y = self._draw_text_line(
                    painter, counts_line,
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
                gen_str = (
                    f"Generated: {generated_at}" if generated_at
                    else datetime.now().strftime("Generated: %Y-%m-%d %H:%M")
                )
                y = self._draw_text_line(
                    painter, gen_str,
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
                if model_label:
                    y = self._draw_text_line(
                        painter, f"AI model: {model_label}",
                        content.left(), y, content.width(),
                        self._font_body, self._muted,
                    )
            else:
                gen_str = datetime.now().strftime("Generated: %Y-%m-%d %H:%M")
                y = self._draw_text_line(
                    painter, gen_str,
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
            y += 6.0

            for preset, pixmap in chart_pixmaps:
                if pixmap is None or pixmap.isNull():
                    continue
                aspect = pixmap.height() / max(pixmap.width(), 1)
                chart_h = content.width() * aspect
                y, _ = self._ensure_space(painter, writer, content, y, chart_h + 32)
                y = self._section_heading(
                    painter, writer, content, y, f"Chart: {preset}", keep_with=chart_h
                )
                target = QRectF(content.left(), y, content.width(), chart_h)
                painter.drawPixmap(
                    target, pixmap, QRectF(0, 0, pixmap.width(), pixmap.height())
                )
                y += chart_h + self._ROW_GAP

            if narrative:
                y = self._draw_narrative_paginated(painter, writer, content, y, narrative)
                y += self._ROW_GAP

            if shallow_rows:
                first_row_h = self._measure_tag_row_height(painter, content, shallow_rows[0])
                y = self._section_heading(
                    painter, writer, content, y, "Check Logs",
                    keep_with=first_row_h + self._ROW_GAP,
                )
                for row in shallow_rows:
                    y = self._draw_tag_row(painter, writer, content, y, row)

            painter.end()
            return True
        except Exception as exc:
            try:
                from app.services.logging_service import LoggingService
                LoggingService.get_instance().error(
                    f"ChessLogPDFService.export_charts_report error: {exc}", exc_info=exc
                )
            except Exception:
                pass
            if painter is not None:
                try:
                    painter.end()
                except Exception:
                    pass
            return False

    def export_narrative_report(
        self,
        path: Path,
        player_name: str,
        source_label: str,
        narrative_text: str,
        *,
        model_label: str = "",
        generated_at: str = "",
        n_games: int = 0,
        g_games: int = 0,
        m_moments: int = 0,
        s_flagged: int = 0,
        has_3x3: bool = False,
    ) -> bool:
        """Write a narrative-only Narrative Summary PDF."""
        painter = None
        try:
            writer = self._create_pdf_writer(path)
            painter = QPainter(writer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            content = self._content_rect(writer)
            self._page_number = 1
            self._draw_page_chrome(painter, content)

            y = self._draw_report_header(painter, content, "Chess Log — Narrative Summary")
            if player_name:
                y = self._draw_text_line(
                    painter, f"Player: {player_name}",
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
            if source_label:
                y = self._draw_text_line(
                    painter, f"Source: {source_label}",
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
            counts_line = (
                f"{n_games} games · {g_games} with logged moments "
                f"· {m_moments} moments · {s_flagged} {shallow_flag_label(has_3x3)}"
            )
            y = self._draw_text_line(
                painter, counts_line,
                content.left(), y, content.width(),
                self._font_body, self._muted,
            )
            gen_str = f"Generated: {generated_at}" if generated_at else datetime.now().strftime("Generated: %Y-%m-%d %H:%M")
            y = self._draw_text_line(
                painter, gen_str,
                content.left(), y, content.width(),
                self._font_body, self._muted,
            )
            if model_label:
                y = self._draw_text_line(
                    painter, f"AI model: {model_label}",
                    content.left(), y, content.width(),
                    self._font_body, self._muted,
                )
            y += 6.0

            narrative = (narrative_text or "").strip()
            if narrative:
                y = self._draw_narrative_paginated(painter, writer, content, y, narrative)

            painter.end()
            return True
        except Exception as exc:
            try:
                from app.services.logging_service import LoggingService
                LoggingService.get_instance().error(
                    f"ChessLogPDFService.export_narrative_report error: {exc}", exc_info=exc
                )
            except Exception:
                pass
            if painter is not None:
                try:
                    painter.end()
                except Exception:
                    pass
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _draw_report_header(self, painter: QPainter, content: QRectF, title: str) -> float:
        logo_sz = min(self._logo_size, 36.0)
        logo_rect = QRectF(
            content.right() - logo_sz, content.top(), logo_sz, logo_sz
        )
        self._draw_logo(painter, logo_rect)

        title_w = content.width() - logo_sz - 10.0
        y = content.top()
        y = self._draw_text_line(
            painter, "CARA — Chess Log",
            content.left(), y, title_w,
            self._font_body, self._muted,
        )
        y = self._draw_text_line(
            painter, title,
            content.left(), y + 2.0, title_w,
            self._font_title, self._accent,
        )
        rule_y = max(y + 6.0, content.top() + logo_sz + 4.0)
        painter.setPen(QPen(self._rule, 1.5))
        painter.drawLine(int(content.left()), int(rule_y), int(content.right()), int(rule_y))
        return rule_y + 12.0

    def _measure_tag_row_height(
        self,
        painter: QPainter,
        content: QRectF,
        row: TagRowSnapshot,
    ) -> float:
        """Compute the total card height (including padding) needed for this row."""
        pad = self._ROW_PAD
        board_sz = self._BOARD_DISPLAY_PT
        gap = 8.0
        w_inner = content.width() - pad * 2
        remaining = w_inner - board_sz - gap
        col2_w = remaining * 0.38
        col3_w = remaining - col2_w - gap
        flags = int(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
        )

        painter.setFont(self._font_body_bold)
        fm_bold = QFontMetrics(self._font_body_bold)
        fm_body = QFontMetrics(self._font_body)
        bold_line_h = float(fm_bold.height())
        body_line_h = float(fm_body.height())

        # Header height — move label (bold), plus room for triangle if shown.
        # 3x3 rows never show a header triangle (Ignore moves to per-chip text).
        header_br = painter.boundingRect(QRectF(0, 0, w_inner, 1000), flags, row.move_label)
        header_h = float(header_br.height())
        if row.show_ignore and row.preset != "3x3":
            header_h = max(header_h, bold_line_h + 4.0)

        # Body content height
        if row.preset == "3x3":
            why_map = {e.get("cat", ""): e.get("why", "") for e in row.entries}
            full_w = col2_w + gap + col3_w
            body_h = 0.0
            chip_pad = 3.0
            _labels_cfg_m = (self.config.get("ui", {}).get("dialogs", {})
                             .get("shallow", {}).get("labels", {}))
            _chip_w_est = max(
                float(fm_bold.horizontalAdvance(_labels_cfg_m.get("shallow", {}).get("text", "Shallow"))),
                float(fm_bold.horizontalAdvance(_labels_cfg_m.get("vague_lesson", {}).get("text", "Vague"))),
            ) + chip_pad * 2 + 4.0
            _ignore_w_est = max(
                float(fm_body.horizontalAdvance("Ignore: Yes")),
                float(fm_body.horizontalAdvance("Ignore: No")),
            )
            chip_col_w = max(_chip_w_est, _ignore_w_est) + 8.0
            chip_h = bold_line_h + 4.0
            for key in ("Why1", "Why2", "Why3", "Why4"):
                has_chip = key in row.shallow_cats or key in row.vague_cats
                prompt = _3X3_PROMPTS.get(key, key)
                q_w = (full_w - chip_col_w - 4.0) if has_chip else full_w
                painter.setFont(self._font_body_bold)
                br = painter.boundingRect(QRectF(0, 0, q_w, 1000), flags, prompt)
                q_h = float(br.height())
                answer = why_map.get(key, "").strip()
                if answer:
                    painter.setFont(self._font_body)
                    br2 = painter.boundingRect(QRectF(0, 0, q_w, 1000), flags, answer)
                    ans_h = float(br2.height())
                else:
                    ans_h = 0.0
                if has_chip:
                    col_h = chip_h + (4.0 + body_line_h if row.show_ignore else 0.0)
                    block_h = max(q_h + ans_h, col_h)
                else:
                    block_h = q_h + ans_h
                body_h += block_h
                if key != "Why4":
                    body_h += body_line_h
        else:
            from app.utils.chess_log_preset_order import CLAMP_ORDER, CCT_ORDER
            if row.preset == "CLAMP":
                cats = list(CLAMP_ORDER)
            elif row.preset == "CCT":
                cats = list(CCT_ORDER)
            else:
                cats = sorted({e.get("cat", "") for e in row.entries if e.get("cat")})
            check_h = len(cats) * body_line_h if cats else 0.0
            why = next((e.get("why", "").strip() for e in row.entries if e.get("why")), "")
            why_h = 0.0
            if why:
                painter.setFont(self._font_body)
                br = painter.boundingRect(QRectF(0, 0, col3_w, 1000), flags, why)
                why_h = float(br.height())
            body_h = max(check_h, why_h)

        body_h = max(body_h, board_sz)
        return pad * 2 + header_h + 4.0 + body_h

    def _draw_tag_row(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        row: TagRowSnapshot,
    ) -> float:
        """Draw one tag row atomically. Returns y after the row."""
        pad = self._ROW_PAD
        board_sz = self._BOARD_DISPLAY_PT
        gap = 8.0
        x = content.left()
        w = content.width()
        x_inner = x + pad
        w_inner = w - pad * 2
        remaining = w_inner - board_sz - gap
        col2_w = remaining * 0.38
        col3_w = remaining - col2_w - gap
        col2_x = x_inner + board_sz + gap
        col3_x = col2_x + col2_w + gap
        flags = int(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
        )

        # ---- Phase 1: Measure (before page-break check) ----
        painter.setFont(self._font_body_bold)
        fm_bold = QFontMetrics(self._font_body_bold)
        fm_body = QFontMetrics(self._font_body)
        bold_line_h = float(fm_bold.height())
        body_line_h = float(fm_body.height())

        header_br = painter.boundingRect(QRectF(0, 0, w_inner, 1000), flags, row.move_label)
        header_h = float(header_br.height())
        if row.show_ignore and row.preset != "3x3":
            header_h = max(header_h, bold_line_h + 4.0)

        if row.preset == "3x3":
            cats: List[str] = []
            why = ""
            why_h = 0.0
            why_map_3x3 = {e.get("cat", ""): e.get("why", "") for e in row.entries}
            full_w = col2_w + gap + col3_w
            body_h = 0.0
            chip_pad = 3.0
            labels_cfg_3x3 = (self.config.get("ui", {}).get("dialogs", {})
                               .get("shallow", {}).get("labels", {}))
            _chip_w_est = max(
                float(fm_bold.horizontalAdvance(labels_cfg_3x3.get("shallow", {}).get("text", "Shallow"))),
                float(fm_bold.horizontalAdvance(labels_cfg_3x3.get("vague_lesson", {}).get("text", "Vague"))),
            ) + chip_pad * 2 + 4.0
            _ignore_w_est = max(
                float(fm_body.horizontalAdvance("Ignore: Yes")),
                float(fm_body.horizontalAdvance("Ignore: No")),
            )
            chip_col_w = max(_chip_w_est, _ignore_w_est) + 8.0
            chip_h = bold_line_h + 4.0
            for key in ("Why1", "Why2", "Why3", "Why4"):
                has_chip = key in row.shallow_cats or key in row.vague_cats
                prompt = _3X3_PROMPTS.get(key, key)
                q_w = (full_w - chip_col_w - 4.0) if has_chip else full_w
                painter.setFont(self._font_body_bold)
                br = painter.boundingRect(QRectF(0, 0, q_w, 1000), flags, prompt)
                q_h = float(br.height())
                answer = why_map_3x3.get(key, "").strip()
                if answer:
                    painter.setFont(self._font_body)
                    br2 = painter.boundingRect(QRectF(0, 0, q_w, 1000), flags, answer)
                    ans_h = float(br2.height())
                else:
                    ans_h = 0.0
                if has_chip:
                    col_h = chip_h + (4.0 + body_line_h if row.show_ignore else 0.0)
                    block_h = max(q_h + ans_h, col_h)
                else:
                    block_h = q_h + ans_h
                body_h += block_h
                if key != "Why4":
                    body_h += body_line_h
        else:
            why_map_3x3 = {}
            full_w = 0.0
            from app.utils.chess_log_preset_order import CLAMP_ORDER, CCT_ORDER
            if row.preset == "CLAMP":
                cats = list(CLAMP_ORDER)
            elif row.preset == "CCT":
                cats = list(CCT_ORDER)
            else:
                cats = sorted({e.get("cat", "") for e in row.entries if e.get("cat")})
            check_h = len(cats) * body_line_h if cats else 0.0
            why = next((e.get("why", "").strip() for e in row.entries if e.get("why")), "")
            why_h = 0.0
            if why:
                painter.setFont(self._font_body)
                br = painter.boundingRect(QRectF(0, 0, col3_w, 1000), flags, why)
                why_h = float(br.height())
            body_h = max(check_h, why_h)

        body_h = max(body_h, board_sz)
        card_h = pad * 2 + header_h + 4.0 + body_h

        # ---- Page-break check ----
        y, _ = self._ensure_space(painter, writer, content, y, card_h + self._ROW_GAP)

        # ---- Phase 2: Draw ----
        painter.save()
        painter.setBrush(self._card)
        painter.setPen(QPen(self._rule, 0.5))
        painter.drawRoundedRect(QRectF(x, y, w, card_h), 4, 4)
        painter.restore()

        y_inner = y + pad

        # Header: move label
        painter.setFont(self._font_body_bold)
        painter.setPen(self._text)
        painter.drawText(QRectF(x_inner, y_inner, w_inner, header_h + 2), flags, row.move_label)

        # Header: Ignore text (right-aligned). No triangle for any preset.
        # 3x3 rows show Ignore per-chip in the body instead.
        if row.show_ignore and row.preset != "3x3":
            is_ignored = any(e.get("ignore_shallow") for e in row.entries)
            ignore_text = f"Ignore: {'Yes' if is_ignored else 'No'}"
            text_w = float(fm_bold.horizontalAdvance(ignore_text))
            text_x = x_inner + w_inner - text_w - 4.0
            painter.setFont(self._font_body_bold)
            painter.setPen(self._text)
            painter.drawText(
                QRectF(text_x, y_inner, text_w + 4.0, bold_line_h + 2),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                ignore_text,
            )

        # Header: chips (Shallow / Vague) — right-aligned, left of Ignore section.
        # 3x3 rows draw per-answer chips in the body instead of a header chip.
        if (row.is_shallow or row.is_vague) and row.preset != "3x3":
            labels_cfg = (
                self.config.get("ui", {}).get("dialogs", {})
                .get("shallow", {}).get("labels", {})
            )
            chip_pad = 3.0
            chip_total_w = 0.0
            chip_specs = []
            for kind, flag in (("shallow", row.is_shallow), ("vague_lesson", row.is_vague)):
                if not flag:
                    continue
                defaults = {"shallow": ([185, 70, 70], [255, 255, 255], "Shallow"),
                            "vague_lesson": ([195, 145, 55], [255, 255, 255], "Vague")}
                def_bg, def_tc, def_txt = defaults[kind]
                cfg = labels_cfg.get(kind, {})
                bg = cfg.get("background_color", def_bg)
                tc = cfg.get("text_color", def_tc)
                txt = cfg.get("text", def_txt)
                cw = float(fm_bold.horizontalAdvance(txt)) + chip_pad * 2
                chip_specs.append((txt, bg, tc, cw))
                chip_total_w += cw + 4.0
            if chip_specs:
                chip_total_w -= 4.0
                ignore_section_w = 0.0
                if row.show_ignore:
                    is_ignored = any(e.get("ignore_shallow") for e in row.entries)
                    ignore_text = f"Ignore: {'Yes' if is_ignored else 'No'}"
                    ignore_section_w = float(fm_bold.horizontalAdvance(ignore_text)) + 4.0 + 12.0
                chip_x = x_inner + w_inner - ignore_section_w - chip_total_w
                chip_h_hdr = bold_line_h + 4.0
                chip_y = y_inner + (header_h - chip_h_hdr) / 2
                for chip_text, bg_rgb, tc_rgb, chip_w in chip_specs:
                    painter.save()
                    painter.setBrush(QColor(bg_rgb[0], bg_rgb[1], bg_rgb[2]))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(QRectF(chip_x, chip_y, chip_w, chip_h_hdr), 2, 2)
                    painter.setFont(self._font_body_bold)
                    painter.setPen(QColor(tc_rgb[0], tc_rgb[1], tc_rgb[2]))
                    painter.drawText(
                        QRectF(chip_x, chip_y, chip_w, chip_h_hdr),
                        int(Qt.AlignmentFlag.AlignCenter),
                        chip_text,
                    )
                    painter.restore()
                    chip_x += chip_w + 4.0

        y_inner += header_h + 4.0

        # Board miniature
        board_px = self._render_board(row.fen, row.played_move, row.best_move, row.is_flipped)
        if board_px and not board_px.isNull():
            target = QRectF(x_inner, y_inner, board_sz, board_sz)
            painter.drawPixmap(
                target, board_px, QRectF(0, 0, board_px.width(), board_px.height())
            )

        # Body content: 3x3 prompts/answers OR checkboxes + why-text
        if row.preset == "3x3":
            # labels_cfg_3x3, chip_pad, chip_col_w, chip_h, full_w set in Phase 1 above
            entry_map_3x3 = {e.get("cat", ""): e for e in row.entries}
            y_col = y_inner
            for key in ("Why1", "Why2", "Why3", "Why4"):
                is_ans_shallow = key in row.shallow_cats
                is_ans_vague = key in row.vague_cats
                has_chip = is_ans_shallow or is_ans_vague
                entry = entry_map_3x3.get(key, {})
                is_ignored = ChessLogStorageService.is_entry_ignore_honoured(entry) if has_chip else False
                prompt = _3X3_PROMPTS.get(key, key)

                # Question + answer use same (possibly narrowed) width.
                q_w = (full_w - chip_col_w - 4.0) if has_chip else full_w
                y_col_block_start = y_col

                # Question line.
                painter.setFont(self._font_body_bold)
                painter.setPen(self._muted)
                br = painter.boundingRect(QRectF(col2_x, 0, q_w, 1000), flags, prompt)
                prompt_h = float(br.height())
                painter.drawText(
                    QRectF(col2_x, y_col, q_w, prompt_h + 2), flags, prompt
                )
                y_col += prompt_h

                # Answer row.
                answer = why_map_3x3.get(key, "").strip()
                ans_h = 0.0
                if answer:
                    painter.setFont(self._font_body)
                    painter.setPen(self._text)
                    br2 = painter.boundingRect(QRectF(col2_x, 0, q_w, 1000), flags, answer)
                    ans_h = float(br2.height())
                    painter.drawText(
                        QRectF(col2_x, y_col, q_w, ans_h + 2), flags, answer
                    )

                if has_chip:
                    if is_ans_shallow:
                        kind_key, def_bg, def_tc, def_txt = "shallow", [185, 70, 70], [255, 255, 255], "Shallow"
                    else:
                        kind_key, def_bg, def_tc, def_txt = "vague_lesson", [195, 145, 55], [255, 255, 255], "Vague"
                    cfg = labels_cfg_3x3.get(kind_key, {})
                    bg = cfg.get("background_color", def_bg)
                    tc = cfg.get("text_color", def_tc)
                    txt = cfg.get("text", def_txt)
                    cw = float(fm_bold.horizontalAdvance(txt)) + chip_pad * 2 + 4.0
                    chip_x = col2_x + full_w - chip_col_w
                    chip_y = y_col_block_start  # top-aligned with question
                    painter.save()
                    if is_ignored:
                        painter.setOpacity(0.4)
                    painter.setBrush(QColor(bg[0], bg[1], bg[2]))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(QRectF(chip_x, chip_y, cw, chip_h), 2, 2)
                    painter.setFont(self._font_body_bold)
                    painter.setPen(QColor(tc[0], tc[1], tc[2]))
                    painter.drawText(
                        QRectF(chip_x, chip_y, cw, chip_h),
                        int(Qt.AlignmentFlag.AlignCenter),
                        txt,
                    )
                    painter.restore()
                    if row.show_ignore:
                        ignore_str = f"Ignore: {'Yes' if is_ignored else 'No'}"
                        painter.setFont(self._font_body)
                        painter.setPen(self._muted)
                        painter.drawText(
                            QRectF(chip_x, chip_y + chip_h + 4.0, chip_col_w, body_line_h + 2),
                            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                            ignore_str,
                        )
                    chip_col_h = chip_h + (4.0 + body_line_h if row.show_ignore else 0.0)
                    y_col = y_col_block_start + max(prompt_h + ans_h, chip_col_h)
                else:
                    y_col += ans_h

                # Blank line after Why1-Why3; none after Why4.
                if key != "Why4":
                    y_col += body_line_h
        else:
            selected = {e.get("cat", "") for e in row.entries}
            y_col = y_inner
            painter.setFont(self._font_body)
            fm_cb = QFontMetrics(self._font_body)
            box_size = round(fm_cb.ascent() * 0.72)
            box_gap = 3.0
            for cat in cats:
                checked = cat in selected
                box_y = y_col + (body_line_h - box_size) / 2.0
                painter.save()
                painter.setPen(QPen(self._text, 0.9))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(col2_x, box_y, box_size, box_size))
                if checked:
                    path = QPainterPath()
                    path.moveTo(col2_x + box_size * 0.18, box_y + box_size * 0.52)
                    path.lineTo(col2_x + box_size * 0.42, box_y + box_size * 0.76)
                    path.lineTo(col2_x + box_size * 0.82, box_y + box_size * 0.24)
                    painter.setPen(QPen(self._text, 1.2))
                    painter.drawPath(path)
                painter.restore()
                painter.setPen(self._text)
                painter.drawText(
                    QRectF(col2_x + box_size + box_gap, y_col, col2_w - box_size - box_gap, body_line_h + 2),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                    cat,
                )
                y_col += body_line_h
            if why:
                painter.setFont(self._font_body)
                painter.setPen(self._muted)
                painter.drawText(
                    QRectF(col3_x, y_inner, col3_w, why_h + 4), flags, why
                )

        return y + card_h + self._ROW_GAP

    def _draw_warning_triangle(
        self, painter: QPainter, x: float, y: float, size: float
    ) -> None:
        """Draw a filled yellow warning triangle with a black exclamation mark."""
        painter.save()
        poly = QPolygonF([
            QPointF(x + size / 2, y),
            QPointF(x, y + size),
            QPointF(x + size, y + size),
        ])
        painter.setBrush(self._warn_fill)
        painter.setPen(QPen(self._warn_outline, 1.0))
        painter.drawPolygon(poly)
        # Exclamation mark: vertical bar + dot
        painter.setPen(QPen(self._warn_outline, 1.5))
        cx = x + size / 2
        painter.drawLine(
            QPointF(cx, y + size * 0.30),
            QPointF(cx, y + size * 0.62),
        )
        painter.setBrush(self._warn_outline)
        painter.setPen(QPen(self._warn_outline, 0.5))
        painter.drawEllipse(QPointF(cx, y + size * 0.78), size * 0.055, size * 0.055)
        painter.restore()

    @staticmethod
    def _is_table_separator(line: str) -> bool:
        """Return True iff *line* is a GFM pipe-table alignment separator row.

        Accepts any mix of dashes, colons, spaces between pipes — the only hard
        requirement is that there are at least two pipe-delimited cells and every
        cell contains only ``-``, ``:``, and whitespace.
        """
        stripped = line.strip().strip("|")
        if not stripped:
            return False
        cells = [c.strip() for c in stripped.split("|")]
        if len(cells) < 2:
            return False
        return all(c and all(ch in "-: " for ch in c) for c in cells)

    @staticmethod
    def _is_bullet_line(line: str) -> bool:
        """Return True iff *line* is a GFM bullet list item (``- ``, ``* ``, or ``+ ``)."""
        stripped = line.lstrip()
        if not stripped.startswith(("- ", "* ", "+ ")):
            return False
        return bool(stripped[2:].strip())

    @staticmethod
    def _parse_bullet_line(line: str) -> str:
        """Strip the bullet marker and return the remaining content verbatim."""
        stripped = line.lstrip()
        return stripped[2:].strip() if stripped[:2] in ("- ", "* ", "+ ") else stripped

    def _measure_bullet_line(
        self,
        content: QRectF,
        text: str,
        bullet_indent: float,
        bullet_gap: float,
        pad: float,
    ) -> float:
        """Return the pixel height needed to render one bullet item.

        Uses _count_cell_lines (same span-aware algorithm as _draw_wrapped_spans)
        so bold lead-in words — which are wider than their plain equivalents —
        are measured at bold width, matching what will actually be drawn.
        """
        fm_body = QFontMetrics(self._font_body)
        line_h = float(fm_body.height())
        body_w = content.width() - bullet_indent - bullet_gap
        spans = self._parse_bold_spans(text)
        n_lines = self._count_cell_lines(spans, body_w)
        return max(n_lines, 1) * line_h + 2 * pad

    def _draw_bullet_line_paginated(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        text: str,
    ) -> float:
        """Render one bullet item atomically (measure, ensure space, draw)."""
        bullet_indent = 12.0
        bullet_gap = 6.0
        pad = 2.0
        fm_body = QFontMetrics(self._font_body)
        line_h = float(fm_body.height())
        baseline = float(fm_body.ascent())

        h = self._measure_bullet_line(content, text, bullet_indent, bullet_gap, pad)
        y, _ = self._ensure_space(painter, writer, content, y, h)

        # Bullet glyph drawn at a fixed left offset, outside the body rect.
        painter.setFont(self._font_body)
        painter.setPen(self._text)
        painter.drawText(QPointF(content.left() + bullet_indent, y + pad + baseline), "•")

        body_rect = QRectF(
            content.left() + bullet_indent + bullet_gap,
            y + pad,
            content.width() - bullet_indent - bullet_gap,
            h - 2 * pad,
        )
        self._draw_wrapped_spans(painter, body_rect, self._parse_bold_spans(text), pad=0.0)
        return y + h + line_h * 0.15

    @staticmethod
    def _parse_pipe_table(
        lines: List[str],
    ) -> Tuple[List[str], List[List[str]]]:
        """Parse a GFM pipe-table block into (header_cells, [body_row_cells, ...]).

        *lines* must be: header row, separator row, then zero or more body rows.
        Cell strings are stripped of surrounding whitespace.  Rows with too many
        or too few cells are normalized to the header's column count (padded with
        empty strings or truncated) so the caller never index-errors.
        """
        if len(lines) < 2:
            return [], []

        def _split_row(raw: str) -> List[str]:
            return [c.strip() for c in raw.strip().strip("|").split("|")]

        header = _split_row(lines[0])
        n_cols = len(header)
        body: List[List[str]] = []
        for raw in lines[2:]:  # skip separator
            row = _split_row(raw)
            if len(row) < n_cols:
                row += [""] * (n_cols - len(row))
            elif len(row) > n_cols:
                row = row[:n_cols]
            body.append(row)
        return header, body

    def _count_cell_lines(
        self,
        spans: List[Tuple[str, bool]],
        available_width: float,
    ) -> int:
        """Count wrapped lines using the identical algorithm as _draw_wrapped_spans.

        Using the same manual horizontalAdvance-based word-wrap guarantees that
        the measured line count matches the actual lines drawn, preventing cells
        from overrunning their allocated height.
        """
        fm_body = QFontMetrics(self._font_body)
        fm_bold = QFontMetrics(self._font_body_bold)
        space_w = float(fm_body.horizontalAdvance(" "))

        word_runs = [(w, bold) for seg, bold in spans for w in seg.split() if w]
        if not word_runs:
            return 0

        n_lines = 0
        cur_line: List[Tuple[str, bool]] = []
        cur_width = 0.0
        for word, is_bold in word_runs:
            word_w = float((fm_bold if is_bold else fm_body).horizontalAdvance(word))
            needed = word_w if not cur_line else space_w + word_w
            if cur_line and cur_width + needed > available_width:
                n_lines += 1
                cur_line = [(word, is_bold)]
                cur_width = word_w
            else:
                cur_line.append((word, is_bold))
                cur_width += needed
        if cur_line:
            n_lines += 1
        return n_lines

    def _measure_pipe_table_row(
        self,
        painter: QPainter,
        col_widths: List[float],
        cells: List[str],
        font,
        pad: float,
    ) -> float:
        """Return the rendered height for one pipe-table row given column widths.

        Uses _count_cell_lines (same algorithm as _draw_wrapped_spans) so the
        measured height always equals the actually drawn height.
        """
        fm_body = QFontMetrics(self._font_body)
        line_h = float(fm_body.height())
        max_lines = 0
        for i, text in enumerate(cells):
            if i >= len(col_widths):
                break
            available_w = max(1.0, col_widths[i] - 2 * pad)
            spans = self._parse_bold_spans(text)
            n = self._count_cell_lines(spans, available_w)
            max_lines = max(max_lines, n)
        return max(1, max_lines) * line_h + 2 * pad

    def _draw_wrapped_spans(
        self,
        painter: QPainter,
        rect: QRectF,
        spans: List[Tuple[str, bool]],
        pad: float,
    ) -> None:
        """Draw (word, is_bold) spans word-wrapped into *rect* with *pad* padding."""
        fm_body = QFontMetrics(self._font_body)
        fm_bold = QFontMetrics(self._font_body_bold)
        line_h = float(fm_body.height())
        space_w = float(fm_body.horizontalAdvance(" "))
        baseline = float(fm_body.ascent())

        word_runs: List[Tuple[str, bool]] = [
            (w, bold) for seg, bold in spans for w in seg.split() if w
        ]
        if not word_runs:
            return

        cw = rect.width() - 2 * pad
        wrapped: List[List[Tuple[str, bool]]] = []
        cur_line: List[Tuple[str, bool]] = []
        cur_width = 0.0
        for word, is_bold in word_runs:
            word_w = float((fm_bold if is_bold else fm_body).horizontalAdvance(word))
            needed = word_w if not cur_line else space_w + word_w
            if cur_line and cur_width + needed > cw:
                wrapped.append(cur_line)
                cur_line = [(word, is_bold)]
                cur_width = word_w
            else:
                cur_line.append((word, is_bold))
                cur_width += needed
        if cur_line:
            wrapped.append(cur_line)

        y = rect.top() + pad
        x0 = rect.left() + pad
        for line_words in wrapped:
            x = x0
            for idx, (word, is_bold) in enumerate(line_words):
                fm = fm_bold if is_bold else fm_body
                painter.setFont(self._font_body_bold if is_bold else self._font_body)
                painter.setPen(self._text)
                painter.drawText(QPointF(x, y + baseline), word)
                x += fm.horizontalAdvance(word)
                if idx < len(line_words) - 1:
                    x += space_w
            y += line_h

    def _table_col_widths(self, n_cols: int, content_width: float) -> List[float]:
        """Return column widths for a pipe table given column count and available width."""
        if n_cols == 3:
            return [content_width * p for p in self._table_col_pct]
        return [content_width / max(1, n_cols)] * n_cols

    def _measure_table_start_height(
        self,
        painter: QPainter,
        header: List[str],
        body: List[List[str]],
        content_width: float,
    ) -> float:
        """Return header_h + first_body_h for a table — used by the heading lookahead."""
        col_widths = self._table_col_widths(len(header), content_width)
        pad = 4.0
        hdr_h = self._measure_pipe_table_row(
            painter, col_widths, header, self._font_body_bold, pad
        )
        first_body_h = (
            self._measure_pipe_table_row(
                painter, col_widths, body[0], self._font_body, pad
            )
            if body
            else 0.0
        )
        return hdr_h + first_body_h

    def _draw_pipe_table_paginated(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        header: List[str],
        body: List[List[str]],
    ) -> float:
        """Draw a bordered pipe table and return the y after the last row.

        Column widths: driven by ``chess_log_charts.pdf_report.table_col_widths_pct``
        in config (default [20, 40, 40] for the canonical 3-column schema:
        Skill, Observed Issue, Strategic Impact). Falls back to equal split for
        other column counts.

        TODO: measure max cell width per column and derive proportional widths.
        """
        n_cols = len(header)
        col_widths = self._table_col_widths(n_cols, content.width())

        pad = 4.0
        border_pen = QPen(self._rule, 0.5)

        first_body_h = (
            self._measure_pipe_table_row(
                painter, col_widths, body[0], self._font_body, pad
            )
            if body
            else 0.0
        )
        header_h = self._measure_pipe_table_row(
            painter, col_widths, header, self._font_body_bold, pad
        )

        # Ensure header stays with first body row (or just itself if no body).
        y, _ = self._ensure_space(
            painter, writer, content, y, header_h + first_body_h
        )

        # Draw header row — cells always rendered bold.
        x = content.left()
        painter.fillRect(QRectF(x, y, content.width(), header_h), self._card)
        for i, cell in enumerate(header):
            if i >= n_cols:
                break
            cell_rect = QRectF(x, y, col_widths[i], header_h)
            painter.setPen(border_pen)
            painter.drawRect(cell_rect)
            self._draw_wrapped_spans(
                painter, cell_rect, [(cell.strip(), True)], pad
            )
            x += col_widths[i]
        y += header_h

        # Draw body rows atomically (measure then ensure_space then draw).
        # First column (Skill) is always rendered bold.
        for row in body:
            row_h = self._measure_pipe_table_row(
                painter, col_widths, row, self._font_body, pad
            )
            y, _ = self._ensure_space(painter, writer, content, y, row_h)
            x = content.left()
            for i, cell in enumerate(row):
                if i >= n_cols:
                    break
                cell_rect = QRectF(x, y, col_widths[i], row_h)
                painter.setPen(border_pen)
                painter.drawRect(cell_rect)
                spans = [(cell.strip(), True)] if i == 0 else self._parse_bold_spans(cell)
                self._draw_wrapped_spans(painter, cell_rect, spans, pad)
                x += col_widths[i]
            y += row_h

        return y + self._ROW_GAP

    @staticmethod
    def _parse_bold_spans(text: str) -> List[Tuple[str, bool]]:
        """Split *text* into (segment, is_bold) runs on ``**...** `` markers.

        An unmatched trailing ``**`` (odd number of markers) is treated as a
        literal string so it reaches the caller instead of opening a span."""
        spans: List[Tuple[str, bool]] = []
        i, n = 0, len(text)
        bold = False
        buf: List[str] = []
        while i < n:
            if i + 1 < n and text[i] == "*" and text[i + 1] == "*":
                # Only open a new bold span if a closing ** exists ahead.
                if not bold and text.find("**", i + 2) == -1:
                    buf.append(text[i:])
                    i = n
                    continue
                if buf:
                    spans.append(("".join(buf), bold))
                    buf = []
                bold = not bold
                i += 2
            else:
                buf.append(text[i])
                i += 1
        if buf:
            spans.append(("".join(buf), bold))
        return spans

    def _draw_narrative_paginated(
        self,
        painter: QPainter,
        writer,
        content: QRectF,
        y: float,
        text: str,
    ) -> float:
        """Draw narrative text with automatic page breaks before the footer.

        Supports ``**bold**`` markdown (bold spans render with _font_body_bold,
        literal ``**`` markers never reach drawText) and GFM pipe tables (rendered
        as bordered cells via _draw_pipe_table_paginated).
        """
        text = sanitize_narrative_markdown(text)
        painter.setFont(self._font_body)
        painter.setPen(self._text)
        fm_body = QFontMetrics(self._font_body)
        fm_bold = QFontMetrics(self._font_body_bold)
        line_h = float(fm_body.height())
        cx = content.left()
        cw = content.width()
        space_w = float(fm_body.horizontalAdvance(" "))
        baseline = float(fm_body.ascent())

        all_lines = text.split("\n")
        i = 0
        while i < len(all_lines):
            para = all_lines[i]
            stripped = para.strip()

            if not stripped:
                y += line_h * 0.5
                i += 1
                continue

            # Markdown heading: render as a styled section heading.
            if stripped.startswith("#"):
                heading_text = stripped.lstrip("#").strip()
                if heading_text:
                    # Look ahead past blank lines: if the next content is a pipe
                    # table, use the table's header+first-body height as keep_with
                    # so this section heading never orphans when the table jumps
                    # to a new page.
                    keep_with = line_h * 2
                    j = i + 1
                    while j < len(all_lines) and not all_lines[j].strip():
                        j += 1
                    if j < len(all_lines) and all_lines[j].strip().startswith("|"):
                        sep_idx = j + 1
                        while sep_idx < len(all_lines) and not all_lines[sep_idx].strip():
                            sep_idx += 1
                        if sep_idx < len(all_lines) and self._is_table_separator(all_lines[sep_idx]):
                            tbl_block = [all_lines[j], all_lines[sep_idx]]
                            k = sep_idx + 1
                            while k < len(all_lines) and all_lines[k].strip().startswith("|"):
                                tbl_block.append(all_lines[k])
                                k += 1
                            hdr, bdy = self._parse_pipe_table(tbl_block)
                            if hdr:
                                keep_with = self._measure_table_start_height(
                                    painter, hdr, bdy, content.width()
                                )
                    y = self._section_heading(
                        painter, writer, content, y, heading_text, keep_with=keep_with
                    )
                    painter.setFont(self._font_body)
                    painter.setPen(self._text)
                i += 1
                continue

            # GFM pipe table: detected when the current line starts with "|" and
            # the next non-empty line is an alignment separator row (| --- | --- |).
            # Consume the entire block and delegate to _draw_pipe_table_paginated.
            if stripped.startswith("|"):
                next_idx = i + 1
                while next_idx < len(all_lines) and not all_lines[next_idx].strip():
                    next_idx += 1
                if next_idx < len(all_lines) and self._is_table_separator(all_lines[next_idx]):
                    block = [all_lines[i], all_lines[next_idx]]
                    j = next_idx + 1
                    while j < len(all_lines) and all_lines[j].strip().startswith("|"):
                        block.append(all_lines[j])
                        j += 1
                    header, body = self._parse_pipe_table(block)
                    if header:
                        y = self._draw_pipe_table_paginated(
                            painter, writer, content, y, header, body
                        )
                        y += line_h * 0.3
                    i = j
                    continue

            # GFM bullet list: consume the whole contiguous run atomically so each
            # bullet item is measured and placed as one unit.
            if self._is_bullet_line(para):
                j = i
                while j < len(all_lines):
                    if self._is_bullet_line(all_lines[j]):
                        y = self._draw_bullet_line_paginated(
                            painter, writer, content, y,
                            self._parse_bullet_line(all_lines[j]),
                        )
                        j += 1
                    elif not all_lines[j].strip():
                        j += 1
                    else:
                        break
                y += line_h * 0.25
                i = j
                continue

            # Body text: tokenize with bold-span awareness, wrap, draw word-by-word.
            word_runs: List[Tuple[str, bool]] = [
                (w, bold)
                for seg, bold in self._parse_bold_spans(stripped)
                for w in seg.split()
                if w
            ]
            if not word_runs:
                i += 1
                continue

            # Group words into wrapped lines.
            lines: List[List[Tuple[str, bool]]] = []
            cur_line: List[Tuple[str, bool]] = []
            cur_width = 0.0
            for word, is_bold in word_runs:
                word_w = float((fm_bold if is_bold else fm_body).horizontalAdvance(word))
                needed = word_w if not cur_line else space_w + word_w
                if cur_line and cur_width + needed > cw:
                    lines.append(cur_line)
                    cur_line = [(word, is_bold)]
                    cur_width = word_w
                else:
                    cur_line.append((word, is_bold))
                    cur_width += needed
            if cur_line:
                lines.append(cur_line)

            # Draw each line with per-word font switching.
            for line_words in lines:
                y, _ = self._ensure_space(painter, writer, content, y, line_h)
                painter.setPen(self._text)
                x = cx
                for idx, (word, is_bold) in enumerate(line_words):
                    fm = fm_bold if is_bold else fm_body
                    painter.setFont(self._font_body_bold if is_bold else self._font_body)
                    painter.drawText(QPointF(x, y + baseline), word)
                    x += fm.horizontalAdvance(word)
                    if idx < len(line_words) - 1:
                        x += space_w
                y += line_h
            y += line_h * 0.3  # paragraph gap
            i += 1

        return y

    def _render_board(
        self,
        fen: Optional[str],
        played_move: Optional[chess.Move],
        best_move: Optional[chess.Move] = None,
        is_flipped: bool = False,
    ) -> Optional[QPixmap]:
        """Rasterize a MiniChessBoardWidget for PDF embedding."""
        # Board size and arrows are fixed for print quality; View → Miniature Boards →
        # Chess Log settings are intentionally ignored here, matching Game Report PDF
        # behavior. See GitHub issue #50.
        try:
            import chess as chess_lib
            from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget
            size_px = int(self._BOARD_DISPLAY_PT * self._BOARD_RENDER_SCALE)
            widget = MiniChessBoardWidget(
                self.config,
                fen or chess_lib.STARTING_FEN,
                embedded=True,
                size_override=size_px,
                is_flipped=is_flipped,
            )
            widget.set_played_and_best(played_move, best_move)
            widget_size = widget.size()
            image = QImage(widget_size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.white)
            widget.render(image)
            return QPixmap.fromImage(image)
        except Exception as e:
            try:
                from app.services.logging_service import LoggingService
                LoggingService.get_instance().warning(f"Chess Log board render failed: {e}")
            except Exception:
                pass
            return None

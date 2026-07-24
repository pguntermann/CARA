"""Shared PDF report chrome: page setup, fonts, footer, section helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QMarginsF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
    QPixmap,
)

from app.utils.pdf_report_config import resolve_pdf_report_config


class BasePDFReportService:
    """Common look-and-feel for CARA printable PDF reports."""

    def __init__(
        self,
        config: Dict[str, Any],
        report_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config = config
        self._cfg = resolve_pdf_report_config(config, report_cfg)

        colors = self._cfg.get("colors", {})
        if not isinstance(colors, dict):
            colors = {}
        self._text = self._rgb(colors.get("text"), (30, 30, 35))
        self._muted = self._rgb(colors.get("muted"), (100, 100, 110))
        self._accent = self._rgb(colors.get("accent"), (35, 80, 120))
        self._rule = self._rgb(colors.get("rule"), (180, 185, 190))
        self._card = self._rgb(colors.get("card_fill"), (245, 247, 250))
        self._chart_bar = self._rgb(colors.get("chart_bar"), (35, 80, 120))
        self._chart_grid = self._rgb(colors.get("chart_grid"), (220, 224, 230))

        fonts = self._cfg.get("fonts", {})
        if not isinstance(fonts, dict):
            fonts = {}
        family = str(fonts.get("family", "Helvetica"))
        title_size = int(fonts.get("title_size", 14))
        heading_size = int(fonts.get("heading_size", 10))
        body_size = int(fonts.get("body_size", 9))
        self._font_title = QFont(family, title_size, QFont.Weight.Bold)
        self._font_heading = QFont(family, heading_size, QFont.Weight.Bold)
        self._font_body = QFont(family, body_size)
        self._font_body_bold = QFont(family, body_size, QFont.Weight.Bold)
        self._font_caption = QFont(family, body_size)
        self._font_accuracy = QFont(
            family, int(fonts.get("accuracy_size", 16)), QFont.Weight.Bold
        )

        self._margin = float(self._cfg.get("margin", 48))
        self._section_spacing = float(self._cfg.get("section_spacing", 18))
        self._logo_size = float(self._cfg.get("logo_size", 52))
        self._logo_path = str(self._cfg.get("logo_path", "appicon.svg"))
        self._logo_render_scale = max(1, int(self._cfg.get("logo_render_scale", 8)))
        self._title = str(self._cfg.get("title", "CARA REPORT"))

        version = str(config.get("version", "") or "").strip() or "?"
        footer_template = str(
            self._cfg.get(
                "footer_text",
                "Generated with CARA ({version})\n"
                "the free Open Source Chess Analysis "
                "and Review Application for Windows, macOS and Linux\n"
                "https://pguntermann.github.io/CARA/",
            )
        )
        self._footer_lines = [
            line.strip()
            for line in footer_template.replace("{version}", version).splitlines()
            if line.strip()
        ] or [f"Generated with CARA ({version})"]

        self._logo_file: Optional[Path] = None
        self._logo_pixmap: Optional[QPixmap] = None
        self._logo_resolved = False
        page = str(self._cfg.get("page_size", "letter")).lower()
        self._page_size_id = (
            QPageSize.PageSizeId.A4 if page == "a4" else QPageSize.PageSizeId.Letter
        )
        self._page_number = 1

    @staticmethod
    def _rgb(value: Any, default: Tuple[int, int, int]) -> QColor:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return QColor(int(value[0]), int(value[1]), int(value[2]))
        return QColor(default[0], default[1], default[2])

    def _create_pdf_writer(self, out: Path) -> QPdfWriter:
        writer = QPdfWriter(str(out))
        writer.setTitle(self._title)
        writer.setCreator("CARA")
        writer.setResolution(72)
        layout = QPageLayout(
            QPageSize(self._page_size_id),
            QPageLayout.Orientation.Portrait,
            QMarginsF(self._margin, self._margin, self._margin, self._margin),
            QPageLayout.Unit.Point,
        )
        writer.setPageLayout(layout)
        return writer

    def _content_rect(self, writer: QPdfWriter) -> QRectF:
        paint = writer.pageLayout().paintRectPixels(writer.resolution())
        return QRectF(0.0, 0.0, float(paint.width()), float(paint.height()))

    def _resolve_logo_file(self) -> Optional[Path]:
        if self._logo_resolved:
            return self._logo_file
        self._logo_resolved = True
        raw = Path(self._logo_path)
        candidates: List[Path] = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            candidates.append(repo_root / raw)
            candidates.append(repo_root / "appicon.svg")
            candidates.append(repo_root / "app" / "resources" / "icons" / "cara120.png")
        for path in candidates:
            if path.exists():
                self._logo_file = path
                break
        return self._logo_file

    def _logo_raster_pixmap(self) -> Optional[QPixmap]:
        if self._logo_pixmap is not None:
            return self._logo_pixmap
        path = self._resolve_logo_file()
        if path is None:
            return None
        px = max(64, int(round(self._logo_size * self._logo_render_scale)))
        if path.suffix.lower() == ".svg":
            from PyQt6.QtSvg import QSvgRenderer

            renderer = QSvgRenderer(str(path))
            if not renderer.isValid():
                return None
            image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            p = QPainter(image)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(p)
            p.end()
            self._logo_pixmap = QPixmap.fromImage(image)
            return self._logo_pixmap
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        self._logo_pixmap = pix.scaled(
            px,
            px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return self._logo_pixmap

    def _draw_logo(self, painter: QPainter, rect: QRectF) -> bool:
        pix = self._logo_raster_pixmap()
        if pix is None or pix.isNull():
            return False
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(rect, pix, QRectF(0, 0, pix.width(), pix.height()))
        painter.restore()
        return True

    def _footer_reserve(self, content_width: float) -> float:
        return 10.0 + self._footer_block_height(max(80.0, content_width - 36.0)) + 6.0

    def _footer_block_height(self, text_width: float) -> float:
        fm = QFontMetrics(self._font_caption)
        flags = int(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap
        )
        total = 0.0
        for line in self._footer_lines:
            bound = fm.boundingRect(
                QRectF(0, 0, max(80.0, text_width), 200).toRect(),
                flags,
                line,
            )
            total += max(float(fm.height()), float(bound.height()))
        return total

    def _draw_page_chrome(self, painter: QPainter, content: QRectF) -> None:
        painter.save()
        text_w = max(80.0, content.width() - 36.0)
        footer_h = self._footer_block_height(text_w)
        line_h = float(QFontMetrics(self._font_caption).height())
        y_line = content.bottom() - footer_h - 8.0
        painter.setPen(QPen(self._accent, 2.0))
        painter.drawLine(
            int(content.left()), int(y_line), int(content.right()), int(y_line)
        )
        painter.setPen(self._muted)
        painter.setFont(self._font_caption)
        flags = (
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap
        )
        y = y_line + 4.0
        for line in self._footer_lines:
            bound = painter.boundingRect(
                QRectF(content.left(), y, text_w, 200), flags, line
            )
            painter.drawText(
                QRectF(content.left(), y, text_w, bound.height() + 2), flags, line
            )
            y += max(line_h, float(bound.height()))
        painter.drawText(
            QRectF(
                content.right() - 36.0,
                content.bottom() - line_h - 2.0,
                36.0,
                line_h + 2,
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._page_number}",
        )
        painter.restore()

    def _content_bottom(self, content: QRectF) -> float:
        return content.bottom() - self._footer_reserve(content.width())

    def _ensure_space(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        needed: float,
    ) -> Tuple[float, bool]:
        if y + needed <= self._content_bottom(content):
            return y, False
        writer.newPage()
        self._page_number += 1
        self._draw_page_chrome(painter, content)
        return content.top(), True

    def _draw_text_line(
        self,
        painter: QPainter,
        text: str,
        x: float,
        y: float,
        width: float,
        font: QFont,
        color: QColor,
        *,
        flags: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
    ) -> float:
        painter.setFont(font)
        painter.setPen(color)
        fm = QFontMetrics(font)
        rect = QRectF(x, y, width, 1000)
        bounding = painter.boundingRect(
            rect, int(flags) | Qt.TextFlag.TextWordWrap, text
        )
        painter.drawText(bounding, int(flags) | Qt.TextFlag.TextWordWrap, text)
        return y + max(bounding.height(), fm.height())

    def _section_heading_height(self) -> float:
        return (
            self._section_spacing
            + float(QFontMetrics(self._font_heading).height())
            + 8.0
        )

    def _section_heading(
        self,
        painter: QPainter,
        writer: QPdfWriter,
        content: QRectF,
        y: float,
        title: str,
        *,
        keep_with: float = 36.0,
    ) -> float:
        y, _ = self._ensure_space(
            painter,
            writer,
            content,
            y,
            self._section_heading_height() + max(0.0, keep_with),
        )
        y += self._section_spacing
        y = self._draw_text_line(
            painter,
            title,
            content.left(),
            y,
            content.width(),
            self._font_heading,
            self._accent,
        )
        painter.setPen(QPen(self._rule, 1.0))
        painter.drawLine(
            int(content.left()), int(y + 2), int(content.right()), int(y + 2)
        )
        return y + 8

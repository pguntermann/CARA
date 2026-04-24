"""Tree view styling helpers for consistent cross-platform appearance."""

from typing import Dict, Any, List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QPixmap
from PyQt6.QtWidgets import QTreeWidget, QHeaderView, QProxyStyle, QStyle

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.themed_icon import themed_icon_from_svg
from app.views.delegates.no_focus_rect_delegate import NoFocusRectItemDelegate


_CARA_BRANCH_STYLES: list[QProxyStyle] = []


class _TreeBranchIndicatorIconStyle(QProxyStyle):
    """Draw branch indicators from themed SVG icons (no base style ownership)."""

    def __init__(
        self,
        *,
        tint_rgb: List[int],
        size_px: int,
        closed_svg: str,
        open_svg: str,
    ) -> None:
        # Important: do NOT set a base style here. Theme switching replaces the global style;
        # owning/wrapping any style object has been a source of segfaults.
        super().__init__()
        self._size_px = max(8, min(24, int(size_px)))
        self._closed_icon = themed_icon_from_svg(closed_svg, tint_rgb)
        self._open_icon = themed_icon_from_svg(open_svg, tint_rgb)
        self._closed_px_by_size: dict[int, QPixmap] = {}
        self._open_px_by_size: dict[int, QPixmap] = {}

    def _pixmap_for(self, is_open: bool, size_px: int) -> QPixmap:
        size_px = max(8, min(24, int(size_px)))
        if is_open:
            px = self._open_px_by_size.get(size_px)
            if px is None:
                px = self._open_icon.pixmap(size_px, size_px)
                self._open_px_by_size[size_px] = px
            return px
        px = self._closed_px_by_size.get(size_px)
        if px is None:
            px = self._closed_icon.pixmap(size_px, size_px)
            self._closed_px_by_size[size_px] = px
        return px

    def drawPrimitive(self, element, option, painter, widget=None):  # type: ignore[override]
        if element == QStyle.PrimitiveElement.PE_IndicatorBranch and option is not None:
            if not (option.state & QStyle.StateFlag.State_Children):
                return

            is_open = bool(option.state & QStyle.StateFlag.State_Open)
            r = option.rect
            if r is None:
                return

            target_size = min(self._size_px, max(8, r.width() - 2), max(8, r.height() - 2))
            px = self._pixmap_for(is_open, target_size)
            if px.isNull():
                return

            w = min(px.width(), r.width())
            h = min(px.height(), r.height())
            x = r.x() + (r.width() - w) // 2
            y = r.y() + (r.height() - h) // 2
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(x, y, w, h, px)
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)


def apply_tree_view_styling(
    tree_views: List[QTreeWidget],
    config: Dict[str, Any],
    tree_style_key: str = "tree_view",
) -> None:
    """Apply unified styling to one or more QTreeWidget instances.

    The styling parameters are read from config['ui']['styles'][tree_style_key].
    """
    styles_config = config.get("ui", {}).get("styles", {})
    tree_config = styles_config.get(tree_style_key, {})

    # Colors
    text_color = tree_config.get("text_color", [220, 220, 220])
    header_text_color = tree_config.get("header_text_color", text_color)
    header_sort_indicator_color = tree_config.get("header_sort_indicator_color", header_text_color)
    branch_cfg = tree_config.get("branch_indicator", {}) if isinstance(tree_config.get("branch_indicator", {}), dict) else {}
    branch_tint = branch_cfg.get("icon_tint_rgb", header_text_color)
    branch_size_px = int(branch_cfg.get("size_px", 12) or 12)
    branch_icons = branch_cfg.get("icons", {}) if isinstance(branch_cfg.get("icons", {}), dict) else {}
    branch_closed_svg = str(branch_icons.get("closed_svg", "app/resources/icons/tree_chevron_right.svg"))
    branch_open_svg = str(branch_icons.get("open_svg", "app/resources/icons/tree_chevron_down.svg"))
    background_color = tree_config.get("background_color", [35, 35, 40])
    alt_background_color = tree_config.get("alternate_background_color", [40, 40, 45])
    grid_color = tree_config.get("grid_color", [60, 60, 65])
    selection_bg = tree_config.get("selection_background_color", [70, 90, 130])
    selection_text = tree_config.get("selection_text_color", [240, 240, 240])
    hover_bg = tree_config.get("hover_background_color", selection_bg)
    hover_text = tree_config.get("hover_text_color", selection_text)

    # Fonts
    font_family_raw = tree_config.get("font_family", "Helvetica Neue")
    header_font_family_raw = tree_config.get("header_font_family", font_family_raw)
    font_size_raw = tree_config.get("font_size", 11)
    header_font_size_raw = tree_config.get("header_font_size", font_size_raw)

    font_family = resolve_font_family(font_family_raw)
    header_font_family = resolve_font_family(header_font_family_raw)
    font_size = scale_font_size(font_size_raw)
    header_font_size = scale_font_size(header_font_size_raw)

    row_height = tree_config.get("row_height")
    header_min_height = tree_config.get("header_min_height")
    show_grid = bool(tree_config.get("show_grid", False))
    show_focus_rect = bool(tree_config.get("show_focus_rect", True))
    header_borders = tree_config.get("header_borders", {}) if isinstance(tree_config.get("header_borders", {}), dict) else {}
    show_header_top = bool(header_borders.get("show_top", True))
    show_header_left_first = bool(header_borders.get("show_left_first", True))
    show_header_right_last = bool(header_borders.get("show_right_last", True))
    scrollbar_gutter_px = int(tree_config.get("scrollbar_gutter_px", 0) or 0)

    base_font = QFont(font_family, int(font_size))
    header_font = QFont(header_font_family, int(header_font_size))

    for tree in tree_views:
        if tree is None:
            continue

        # Suppress the per-cell "current index" focus rectangle (robust vs. QSS alone).
        # This keeps selection highlighting intact while removing the clicked-cell border.
        try:
            tree.setItemDelegate(NoFocusRectItemDelegate(tree))
        except Exception:
            pass

        tree.setFont(base_font)
        header = tree.header()
        if header is not None:
            header.setFont(header_font)
            if header_min_height is not None:
                header.setMinimumHeight(int(header_min_height))
            header.setHighlightSections(False)
            # Sort indicator chevrons are drawn by the platform style; palette roles usually control glyph color.
            try:
                p = header.palette()
                c = QColor(*header_sort_indicator_color)
                p.setColor(QPalette.ColorRole.ButtonText, c)
                p.setColor(QPalette.ColorRole.WindowText, c)
                p.setColor(QPalette.ColorRole.Text, c)
                header.setPalette(p)
            except Exception:
                pass

        text_qcolor = QColor(*text_color)
        palette = tree.palette()
        # Ensure generic and platform text roles use our light text color
        palette.setColor(tree.foregroundRole(), text_qcolor)
        palette.setColor(QPalette.ColorRole.Text, text_qcolor)
        palette.setColor(QPalette.ColorRole.WindowText, text_qcolor)
        palette.setColor(QPalette.ColorRole.ButtonText, text_qcolor)
        palette.setColor(QPalette.ColorRole.BrightText, text_qcolor)
        palette.setColor(tree.backgroundRole(), QColor(*background_color))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(*alt_background_color))
        tree.setPalette(palette)

        # Expand/collapse (branch) chevrons: programmatic rendering via QProxyStyle.
        # Keep references alive to avoid GC while Qt still paints with them.
        try:
            branch_style = _TreeBranchIndicatorIconStyle(
                tint_rgb=branch_tint,
                size_px=branch_size_px,
                closed_svg=branch_closed_svg,
                open_svg=branch_open_svg,
            )
            tree.setStyle(branch_style)
            setattr(tree, "_cara_branch_indicator_style", branch_style)
            _CARA_BRANCH_STYLES.append(branch_style)
        except Exception:
            pass

        # Provide a reliable right-side gutter between the last "real" column and the scrollbar.
        #
        # QSS padding and viewport margins don't consistently create visible spacing across platforms
        # for QTreeWidget/QAbstractScrollArea. A dedicated empty gutter column is robust.
        gutter = max(0, int(scrollbar_gutter_px))
        if gutter > 0:
            try:
                already_added = bool(tree.property("_cara_scrollbar_gutter_col_added"))
            except Exception:
                already_added = False
            if not already_added:
                try:
                    # Add one empty column at the end.
                    cols = int(tree.columnCount())
                    tree.setColumnCount(cols + 1)
                    header = tree.header()
                    if header is not None:
                        labels = [tree.headerItem().text(i) for i in range(cols)]
                        labels.append("")
                        tree.setHeaderLabels(labels)
                        header.setStretchLastSection(False)
                        header.setSectionResizeMode(cols, QHeaderView.ResizeMode.Fixed)
                        tree.setColumnWidth(cols, gutter)
                    tree.setProperty("_cara_scrollbar_gutter_col_added", True)
                except Exception:
                    # Best-effort; if anything fails, fall back to no gutter.
                    pass
        else:
            # If configured off, don't try to remove columns dynamically (could disrupt user resizing).
            pass

        # Build stylesheet primarily for header, grid lines and selection.
        grid_rgb = f"rgb({grid_color[0]}, {grid_color[1]}, {grid_color[2]})"
        header_text_rgb = (
            f"rgb({header_text_color[0]}, {header_text_color[1]}, {header_text_color[2]})"
        )
        bg_rgb = f"rgb({background_color[0]}, {background_color[1]}, {background_color[2]})"
        alt_bg_rgb = f"rgb({alt_background_color[0]}, {alt_background_color[1]}, {alt_background_color[2]})"
        sel_bg_rgb = f"rgb({selection_bg[0]}, {selection_bg[1]}, {selection_bg[2]})"
        sel_text_rgb = f"rgb({selection_text[0]}, {selection_text[1]}, {selection_text[2]})"
        hover_bg_rgb = f"rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]})"
        hover_text_rgb = f"rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]})"

        parts = [
            "QHeaderView {",
            "  border: none;",
            "}",
            "QTreeWidget::header {",
            "  border: none;",
            "}",
            "QTreeWidget {",
            f"  background-color: {bg_rgb};",
            f"  alternate-background-color: {alt_bg_rgb};",
            "  border: none;",
            "}",
            "QTreeWidget::item {",
            f"  color: {sel_text_rgb};",
            "  padding: 2px 4px;",
            "}",
            "QTreeWidget::item:selected {",
            f"  background-color: {sel_bg_rgb};",
            f"  color: {sel_text_rgb};",
            "}",
            "QTreeWidget::item:hover {",
            f"  background-color: {hover_bg_rgb};",
            f"  color: {hover_text_rgb};",
            "}",
            "QTreeWidget::item:selected:hover {",
            f"  background-color: {sel_bg_rgb};",
            f"  color: {sel_text_rgb};",
            "}",
            "QHeaderView::section {",
            f"  color: {header_text_rgb};",
            f"  background-color: {bg_rgb};",
            f"  border-top: {('1px solid ' + grid_rgb) if show_header_top else ('0px solid ' + grid_rgb)};",
            f"  border-bottom: 1px solid {grid_rgb};",
            f"  border-right: 1px solid {grid_rgb};",
            "  padding: 2px 4px;",
            "}",
        ]

        if not show_header_left_first:
            parts.extend(
                [
                    "QHeaderView::section:first {",
                    f"  border-left: 0px solid {grid_rgb};",
                    "}",
                ]
            )
        if not show_header_right_last:
            parts.extend(
                [
                    "QHeaderView::section:last {",
                    f"  border-right: 0px solid {grid_rgb};",
                    "}",
                ]
            )

        if not show_focus_rect:
            parts.extend(
                [
                    "QTreeWidget::item:focus {",
                    "  outline: none;",
                    "}",
                ]
            )

        if show_grid:
            parts.extend(
                [
                    "QTreeView {",
                    f"  gridline-color: {grid_rgb};",
                    "}",
                ]
            )

        stylesheet = "\n".join(parts)
        existing = tree.styleSheet()
        if existing:
            stylesheet = existing + "\n" + stylesheet
        tree.setStyleSheet(stylesheet)

        if row_height is not None:
            tree.setUniformRowHeights(True)
            tree.setStyleSheet(
                stylesheet
                + f"\nQTreeWidget::item {{ height: {int(row_height)}px; }}"
            )


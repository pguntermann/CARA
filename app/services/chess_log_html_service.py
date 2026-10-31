"""HTML and plain-text generators for Chess Log clipboard copy actions (#73).

Produces the HTML and plain-text clipboard flavors for:
  - Narrative Summary (Charts tab "Copy section" on the narrative frame)
  - Charts log (Charts tab "Copy log to clipboard")
  - Show Logged Moments (ShowTagsDialog "Copy to clipboard")
  - Show Shallow/Vague Logs (ShowShallowTagsDialog "Copy to clipboard")

Pipe tables in the narrative are handled here without modifying
markdown_to_html (Philipp's utility — authorship confirmed, untouched).
All other narrative markdown goes through markdown_to_html unchanged.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Tuple

from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
from app.utils.chess_log_preset_order import order_categories
from app.utils.markdown_to_html import markdown_to_html


# ---------------------------------------------------------------------------
# Chip inline styles — WCAG AA: white text on background ≥ 4.5:1 contrast.
# Shallow: dark amber  #9a4400  contrast with white ≈ 6.6:1
# Vague:   deep blue   #1d4ed8  contrast with white ≈ 6.7:1
# ---------------------------------------------------------------------------
_CHIP_BASE_STYLE = (
    "border-radius:3px;padding:1px 5px;"
    "font-size:0.85em;font-weight:bold;color:#fff;"
)
_SHALLOW_BG = "#9a4400"
_VAGUE_BG = "#1d4ed8"

# ---------------------------------------------------------------------------
# Table styles — match PDF proportions ([20,40,40] for 3-col Tactical Breakdown)
# ---------------------------------------------------------------------------
_TABLE_STYLE = "table-layout:fixed;width:100%;border-collapse:collapse"
_CELL_STYLE = (
    "white-space:normal;overflow-wrap:break-word;word-wrap:break-word;"
    "border:1px solid #888;padding:4px 8px"
)
_TABLE_3COL_PCT = [20, 40, 40]


class ChessLogHTMLService:
    """Produces HTML and plain-text strings for Chess Log clipboard copy actions."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        labels_cfg = (
            config.get("ui", {})
            .get("dialogs", {})
            .get("shallow", {})
            .get("labels", {})
        )
        self._shallow_label: str = labels_cfg.get("shallow", {}).get("text", "Shallow")
        self._vague_label: str = labels_cfg.get("vague_lesson", {}).get("text", "Vague")

    # ------------------------------------------------------------------
    # Public: Narrative Summary
    # ------------------------------------------------------------------

    def narrative_html(
        self,
        player_name: str,
        source_label: str,
        narrative_text: str,
        *,
        n_games: int = 0,
        g_games: int = 0,
        m_moments: int = 0,
        k_unflagged: int = 0,
        generated_at: str = "",
        model_label: str = "",
    ) -> str:
        parts = [
            self._narrative_header_html(
                player_name, source_label, n_games, g_games, m_moments, k_unflagged,
                generated_at, model_label,
            )
        ]
        if narrative_text:
            parts.append(_narrative_body_html(narrative_text))
        return _wrap_html_document("".join(parts))

    # ------------------------------------------------------------------
    # Public: Charts log
    # ------------------------------------------------------------------

    def charts_log_html(
        self,
        player_name: str,
        source_label: str,
        chart_preset_names: List[str],
        narrative_text: str,
        check_log_groups: List[Dict],
        *,
        n_games: int = 0,
        g_games: int = 0,
        m_moments: int = 0,
        k_unflagged: int = 0,
        generated_at: str = "",
        model_label: str = "",
    ) -> str:
        parts = [
            self._charts_header_html(
                player_name, source_label, n_games, g_games, m_moments, k_unflagged,
                generated_at, model_label, bool(narrative_text),
            )
        ]
        for preset in chart_preset_names:
            parts.append(
                f"<p>Category chart — {html.escape(preset, quote=False)}: "
                f"see Chess Log Charts tab in CARA.</p>"
            )
        if narrative_text:
            parts.append(_narrative_body_html(narrative_text))
        if check_log_groups:
            parts.append("<h2>Check Logs</h2>")
            parts.append(self._tag_groups_html(check_log_groups))
        return _wrap_html_document("".join(parts))

    # ------------------------------------------------------------------
    # Public: Show Logged Moments (ShowTagsDialog)
    # ------------------------------------------------------------------

    def logged_moments_html(self, tag_groups: List[Dict]) -> str:
        return _wrap_html_document("".join([
            "<h2>Chess Log — Logged Moments</h2><hr>",
            self._tag_groups_html(tag_groups),
        ]))

    def logged_moments_plain(self, tag_groups: List[Dict]) -> str:
        lines = ["Chess Log — Logged Moments", ""]
        body = self._tag_groups_plain(tag_groups)
        if body:
            lines.append(body)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public: Show Shallow/Vague Logs (ShowShallowTagsDialog)
    # ------------------------------------------------------------------

    def check_logs_html(
        self,
        tag_groups: List[Dict],
        *,
        source_label: str = "",
        model_label: str = "",
        generated_at: str = "",
    ) -> str:
        parts = [self._check_logs_header_html(source_label, model_label, generated_at)]
        parts.append(self._tag_groups_html(tag_groups))
        return _wrap_html_document("".join(parts))

    def check_logs_plain(
        self,
        tag_groups: List[Dict],
        *,
        source_label: str = "",
        model_label: str = "",
        generated_at: str = "",
    ) -> str:
        lines = ["Chess Log — Check Logs"]
        if source_label:
            lines.append(f"Source: {source_label}")
        if generated_at:
            lines.append(f"Generated: {generated_at}")
        if model_label:
            lines.append(f"AI model: {model_label}")
        lines.append("")
        body = self._tag_groups_plain(tag_groups)
        if body:
            lines.append(body)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def _narrative_header_html(
        self,
        player_name: str,
        source_label: str,
        n_games: int,
        g_games: int,
        m_moments: int,
        k_unflagged: int,
        generated_at: str,
        model_label: str,
    ) -> str:
        parts = ["<h2>Chess Log — Narrative Summary</h2>"]
        if player_name:
            parts.append(f"<p>Player: {html.escape(player_name, quote=False)}</p>")
        if source_label:
            parts.append(f"<p>Source: {html.escape(source_label, quote=False)}</p>")
        counts = (
            f"{n_games} games · {g_games} with logged moments "
            f"· {m_moments} moments · {k_unflagged} not flagged"
        )
        parts.append(f"<p>{html.escape(counts, quote=False)}</p>")
        if generated_at:
            parts.append(f"<p>Generated: {html.escape(generated_at, quote=False)}</p>")
        if model_label:
            parts.append(f"<p>AI model: {html.escape(model_label, quote=False)}</p>")
        parts.append("<hr>")
        return "".join(parts)

    def _charts_header_html(
        self,
        player_name: str,
        source_label: str,
        n_games: int,
        g_games: int,
        m_moments: int,
        k_unflagged: int,
        generated_at: str,
        model_label: str,
        has_narrative: bool,
    ) -> str:
        display_name = player_name or "Chess Log"
        parts = [f"<h2>Chess Log Charts — {html.escape(display_name, quote=False)}</h2>"]
        if player_name:
            parts.append(f"<p>Player: {html.escape(player_name, quote=False)}</p>")
        if source_label:
            parts.append(f"<p>Source: {html.escape(source_label, quote=False)}</p>")
        if has_narrative:
            counts = (
                f"{n_games} games · {g_games} with logged moments "
                f"· {m_moments} moments · {k_unflagged} not flagged"
            )
            parts.append(f"<p>{html.escape(counts, quote=False)}</p>")
        if generated_at:
            parts.append(f"<p>Generated: {html.escape(generated_at, quote=False)}</p>")
        if has_narrative and model_label:
            parts.append(f"<p>AI model: {html.escape(model_label, quote=False)}</p>")
        parts.append("<hr>")
        return "".join(parts)

    def _check_logs_header_html(
        self,
        source_label: str,
        model_label: str,
        generated_at: str,
    ) -> str:
        parts = ["<h2>Chess Log — Check Logs</h2>"]
        if source_label:
            parts.append(f"<p>Source: {html.escape(source_label, quote=False)}</p>")
        if generated_at:
            parts.append(f"<p>Generated: {html.escape(generated_at, quote=False)}</p>")
        if model_label:
            parts.append(f"<p>AI model: {html.escape(model_label, quote=False)}</p>")
        parts.append("<hr>")
        return "".join(parts)

    # ------------------------------------------------------------------
    # Tag groups
    # ------------------------------------------------------------------

    def _tag_groups_html(self, tag_groups: List[Dict]) -> str:
        non_empty = [g for g in tag_groups if g.get("rows")]
        parts: List[str] = []
        for i, group in enumerate(non_empty):
            header = group.get("header", "")
            rows = group.get("rows", [])
            if header:
                parts.append(f"<h3>{html.escape(header, quote=False)}</h3>")
            for row in rows:
                parts.append(self._row_html(row))
            if i < len(non_empty) - 1:
                parts.append("<hr>")
        return "".join(parts)

    def _tag_groups_plain(self, tag_groups: List[Dict]) -> str:
        non_empty = [g for g in tag_groups if g.get("rows")]
        parts: List[str] = []
        for i, group in enumerate(non_empty):
            header = group.get("header", "")
            rows = group.get("rows", [])
            if header:
                parts.append(header)
            for row in rows:
                parts.append(self._row_plain(row))
            if i < len(non_empty) - 1:
                parts.append("")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Per-row
    # ------------------------------------------------------------------

    def _row_html(self, row: Any) -> str:
        move_label = row.move_label or ""
        preset = row.preset or ""
        entries = row.entries or []
        if preset == "3x3":
            return self._row_3x3_html(
                move_label, entries, row.shallow_cats, row.vague_cats
            )
        return self._row_clamp_cct_html(
            move_label, preset, entries, row.is_shallow, row.is_vague
        )

    def _row_plain(self, row: Any) -> str:
        move_label = row.move_label or ""
        preset = row.preset or ""
        entries = row.entries or []
        if preset == "3x3":
            return self._row_3x3_plain(move_label, entries)
        return self._row_clamp_cct_plain(move_label, entries)

    def _row_3x3_html(
        self,
        move_label: str,
        entries: List[Dict],
        shallow_cats: Any,
        vague_cats: Any,
    ) -> str:
        why_map = {e.get("cat", ""): e.get("why", "") for e in entries}
        parts = [f"<p><strong>{html.escape(move_label, quote=False)}</strong></p>"]
        for key in ("Why1", "Why2", "Why3", "Why4"):
            question = THREE_BY_THREE_PROMPTS.get(key, key)
            chip_html = ""
            if key in shallow_cats:
                chip_html = f"&nbsp;{self._chip_span(self._shallow_label, _SHALLOW_BG)}"
            elif key in vague_cats:
                chip_html = f"&nbsp;{self._chip_span(self._vague_label, _VAGUE_BG)}"
            parts.append(
                f"<p><strong>{html.escape(question, quote=False)}</strong>{chip_html}</p>"
            )
            answer = why_map.get(key, "").strip()
            if answer:
                parts.append(f"<p>{_encode_text(answer)}</p>")
        return "".join(parts)

    def _row_clamp_cct_html(
        self,
        move_label: str,
        preset: str,
        entries: List[Dict],
        is_shallow: bool,
        is_vague: bool,
    ) -> str:
        present_cats = [e.get("cat", "") for e in entries if e.get("cat")]
        ordered = order_categories(preset, present_cats)
        cats_str = " ".join(ordered) if ordered else ""
        chip_html = ""
        if is_shallow:
            chip_html = f"&nbsp;{self._chip_span(self._shallow_label, _SHALLOW_BG)}"
        elif is_vague:
            chip_html = f"&nbsp;{self._chip_span(self._vague_label, _VAGUE_BG)}"
        move_part = f"<strong>{html.escape(move_label, quote=False)}</strong>"
        cats_part = f"&nbsp;<strong>{html.escape(cats_str, quote=False)}</strong>" if cats_str else ""
        parts = [f"<p>{move_part}{cats_part}{chip_html}</p>"]
        note = next(
            (e.get("why", "").strip() for e in entries if e.get("why", "").strip()),
            "",
        )
        if note:
            parts.append(f"<p>{_encode_text(note)}</p>")
        return "".join(parts)

    def _row_3x3_plain(self, move_label: str, entries: List[Dict]) -> str:
        why_map = {e.get("cat", ""): e.get("why", "") for e in entries}
        lines = [move_label]
        for key in ("Why1", "Why2", "Why3", "Why4"):
            question = THREE_BY_THREE_PROMPTS.get(key, key)
            answer = why_map.get(key, "").strip()
            lines.append(f"  {question} {answer}".rstrip())
        return "\n".join(lines)

    def _row_clamp_cct_plain(self, move_label: str, entries: List[Dict]) -> str:
        present_cats = [e.get("cat", "") for e in entries if e.get("cat")]
        note = next(
            (e.get("why", "").strip() for e in entries if e.get("why", "").strip()),
            "",
        )
        cats_str = " ".join(present_cats) if present_cats else ""
        note_part = f": {note}" if note else ""
        return f"{move_label} — {cats_str}{note_part}"

    # ------------------------------------------------------------------
    # Chip helper
    # ------------------------------------------------------------------

    def _chip_span(self, label: str, bg_color: str) -> str:
        style = f"background-color:{bg_color};{_CHIP_BASE_STYLE}"
        return f'<span style="{style}">{html.escape(label, quote=False)}</span>'


# ---------------------------------------------------------------------------
# Module-level helpers (no Qt, no config)
# ---------------------------------------------------------------------------

def _encode_text(text: str) -> str:
    """Escape HTML (text-content only, not attributes) and convert newlines to <br>."""
    return "<br>".join(html.escape(line, quote=False) for line in text.split("\n"))


def _split_narrative_blocks(md: str) -> List[Tuple[bool, str]]:
    """Split markdown into (is_table, text) pairs.

    Consecutive lines that start with '|' form a table block; everything else
    is a non-table block.  The split preserves order.
    """
    lines = md.split("\n")
    blocks: List[Tuple[bool, str]] = []
    current_is_table: Optional[bool] = None
    current_lines: List[str] = []

    for line in lines:
        is_table_line = line.strip().startswith("|")
        if current_is_table is None:
            current_is_table = is_table_line
            current_lines = [line]
        elif is_table_line == current_is_table:
            current_lines.append(line)
        else:
            blocks.append((current_is_table, "\n".join(current_lines)))
            current_is_table = is_table_line
            current_lines = [line]

    if current_lines:
        blocks.append((bool(current_is_table), "\n".join(current_lines)))
    return blocks


def _gfm_table_to_html(table_text: str) -> str:
    """Convert a GFM pipe table block to an HTML <table> element.

    Column widths match PDF defaults: 20/40/40 % for 3-column tables
    (Skill / Observed Issue / Strategic Impact), equal split otherwise.
    """
    lines = [ln for ln in table_text.strip().split("\n") if ln.strip()]
    if not lines:
        return ""

    def _parse_cells(line: str) -> List[str]:
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [cell.strip() for cell in line.split("|")]

    def _is_separator(line: str) -> bool:
        stripped = line.replace(" ", "").replace("|", "")
        return bool(stripped) and all(c in "-:" for c in stripped)

    has_header = len(lines) >= 2 and _is_separator(lines[1])
    header_cells = _parse_cells(lines[0]) if has_header else []
    n_cols = len(header_cells) if has_header else max(
        (len(_parse_cells(ln)) for ln in lines if not _is_separator(ln.replace("|", ""))),
        default=1,
    )

    if n_cols == 3:
        col_pcts: List[int] = _TABLE_3COL_PCT
    else:
        each = round(100 / max(1, n_cols), 2)
        col_pcts = [each] * n_cols

    out: List[str] = [f'<table style="{_TABLE_STYLE}">']
    out.append("<colgroup>")
    for pct in col_pcts:
        out.append(f'<col style="width:{pct}%">')
    out.append("</colgroup>")

    if has_header:
        out.append("<thead><tr>")
        for i, cell in enumerate(header_cells):
            w = col_pcts[i] if i < len(col_pcts) else col_pcts[-1]
            th_style = f"text-align:left;width:{w}%;{_CELL_STYLE}"
            out.append(f'<th style="{th_style}">{_table_cell_html(cell)}</th>')
        out.append("</tr></thead>")
        data_lines = lines[2:]
    else:
        data_lines = lines

    out.append("<tbody>")
    for line in data_lines:
        if _is_separator(line.replace("|", "")):
            continue
        out.append("<tr>")
        for cell in _parse_cells(line):
            out.append(f'<td style="{_CELL_STYLE}">{_table_cell_html(cell)}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _table_cell_html(cell: str) -> str:
    """Escape HTML and handle **bold** inline in a table cell.

    Non-breaking spaces (U+00A0) are replaced with regular spaces so the
    browser can wrap long cell text.
    """
    cell = cell.replace("\xa0", " ")
    escaped = html.escape(cell, quote=False)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)


def _wrap_html_document(body: str) -> str:
    """Wrap body HTML in a complete UTF-8 document, adding heading margins.

    1. Adds margin-top:1.2em to bare <h2> and <h3> tags.
    2. Encodes every non-ASCII character as a decimal numeric character
       reference so the HTML is pure ASCII and safe regardless of the
       receiver's assumed encoding.
    3. Wraps in <!DOCTYPE html> with <meta charset="utf-8">.
    """
    body = re.sub(r"<(h[23])(>|\s)", r'<\1 style="margin-top:1.2em"\2', body)
    body = body.encode("ascii", "xmlcharrefreplace").decode("ascii")
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        f"<body>{body}</body></html>"
    )


def _narrative_body_html(narrative_text: str) -> str:
    """Convert narrative markdown to HTML, handling pipe tables in-line."""
    blocks = _split_narrative_blocks(narrative_text)
    parts: List[str] = []
    for is_table, block_text in blocks:
        if is_table:
            parts.append(_gfm_table_to_html(block_text))
        elif block_text.strip():
            parts.append(markdown_to_html(block_text, heading_level_offset=1))
    return "".join(parts)

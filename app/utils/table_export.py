"""Export table data to delimited text (CSV/TSV). Used by moves list and database table."""

from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QAbstractTableModel
from PyQt6.QtWidgets import QHeaderView


def _normalize_line_breaks(value: str) -> str:
    """Replace line breaks with spaces so one table row maps to one delimited line (CSV/TSV convention)."""
    return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _quote_field(value: str, delimiter: str, always_quote: bool) -> str:
    """Apply encapsulation and escaping: wrap in quotes (always or when needed), double internal quotes.

    Args:
        value: Cell or header text.
        delimiter: Column delimiter; used to detect when quoting is needed.
        always_quote: If True, quote every field; if False, quote only if value
            contains delimiter, newline, carriage return, or double quote.

    Returns:
        Quoted and escaped string, or raw value if no quoting applied.
    """
    needs_quote = (
        always_quote
        or delimiter in value
        or "\n" in value
        or "\r" in value
        or '"' in value
    )
    if needs_quote:
        return '"' + value.replace('"', '""') + '"'
    return value


def table_to_delimited(
    model: QAbstractTableModel,
    column_indices: List[int],
    delimiter: str,
    use_csv_escaping: bool,
    always_quote_values: bool = False,
    cell_value_override: Optional[Callable[[int, int, QAbstractTableModel], Optional[str]]] = None,
    row_indices: Optional[List[int]] = None,
) -> str:
    """Build a delimited string (CSV or TSV) from the table model.

    Args:
        model: Table model with headerData() and data().
        column_indices: Logical column indices to include, in desired order.
        delimiter: Column delimiter (e.g. ',' or '\\t'); used for output and for when-needed quoting.
        use_csv_escaping: If True, apply quoting and escaping (per always_quote_values).
        always_quote_values: If True, quote every field; if False, quote only when value
            contains delimiter, newline, \\r, or double quote.
        cell_value_override: Optional (row, col, model) -> str or None. If given and returns
            a string, that value is used for the cell; if None, model.data(DisplayRole) is used.
            Used e.g. to export icon columns as text without changing the model's DisplayRole.
        row_indices: Optional list of row indices to include. If None, all rows are included.

    Returns:
        Header row + data rows as a single string.
    """
    if not column_indices:
        return ""

    def format_cell(raw: str) -> str:
        if use_csv_escaping:
            return _quote_field(raw, delimiter, always_quote_values)
        return raw

    headers: List[str] = []
    for col in column_indices:
        h = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        raw = _normalize_line_breaks(str(h) if h is not None else "")
        headers.append(format_cell(raw))

    lines: List[str] = [delimiter.join(headers)]
    row_count = model.rowCount()
    rows_to_use: List[int] = sorted(row_indices) if row_indices is not None else list(range(row_count))
    # Filter to valid row indices
    rows_to_use = [r for r in rows_to_use if 0 <= r < row_count]

    for row in rows_to_use:
        cells: List[str] = []
        for col in column_indices:
            if cell_value_override is not None:
                over = cell_value_override(row, col, model)
                if over is not None:
                    cell = _normalize_line_breaks(over)
                    cells.append(format_cell(cell))
                    continue
            index = model.index(row, col)
            val = model.data(index, Qt.ItemDataRole.DisplayRole)
            cell = _normalize_line_breaks("" if val is None else str(val))
            cells.append(format_cell(cell))
        lines.append(delimiter.join(cells))

    return "\n".join(lines)


def get_visual_column_indices(header: QHeaderView) -> List[int]:
    """Return model column indices in current visual order (visible columns only).

    Args:
        header: The table's horizontal header (e.g. table.horizontalHeader()).

    Returns:
        List of logical column indices in visual order, excluding hidden columns.
    """
    indices: List[int] = []
    for visual in range(header.count()):
        logical = header.logicalIndex(visual)
        if logical >= 0 and not header.isSectionHidden(logical):
            indices.append(logical)
    return indices


def get_copy_table_config(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return copy_table config (csv/tsv delimiter, use_escaping, always_quote_values) with defaults.

    Uses ui.panels.detail.moveslist.copy_table so moves list and database table share the same settings.

    Args:
        config: Full application config dict.

    Returns:
        Dict with "csv" and "tsv" entries, each with "delimiter", "use_escaping", "always_quote_values".
    """
    ui = config.get("ui", {})
    moveslist = ui.get("panels", {}).get("detail", {}).get("moveslist", {})
    copy_table = moveslist.get("copy_table", {})
    csv_cfg = copy_table.get("csv", {})
    tsv_cfg = copy_table.get("tsv", {})
    return {
        "csv": {
            "delimiter": csv_cfg.get("delimiter", ","),
            "use_escaping": csv_cfg.get("use_escaping", True),
            "always_quote_values": csv_cfg.get("always_quote_values", False),
        },
        "tsv": {
            "delimiter": tsv_cfg.get("delimiter", "\t"),
            "use_escaping": tsv_cfg.get("use_escaping", False),
            "always_quote_values": tsv_cfg.get("always_quote_values", False),
        },
    }

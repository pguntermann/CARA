"""Export moves list table data to delimited text (CSV/TSV)."""

from typing import List, Any

from PyQt6.QtCore import Qt, QAbstractTableModel


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
) -> str:
    """Build a delimited string (CSV or TSV) from the table model.

    Args:
        model: Table model with headerData() and data().
        column_indices: Logical column indices to include, in desired order.
        delimiter: Column delimiter (e.g. ',' or '\\t'); used for output and for when-needed quoting.
        use_csv_escaping: If True, apply quoting and escaping (per always_quote_values).
        always_quote_values: If True, quote every field; if False, quote only when value
            contains delimiter, newline, \\r, or double quote.

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
        raw = str(h) if h is not None else ""
        headers.append(format_cell(raw))

    lines: List[str] = [delimiter.join(headers)]
    row_count = model.rowCount()

    for row in range(row_count):
        cells: List[str] = []
        for col in column_indices:
            index = model.index(row, col)
            val = model.data(index, Qt.ItemDataRole.DisplayRole)
            cell = "" if val is None else str(val)
            cells.append(format_cell(cell))
        lines.append(delimiter.join(cells))

    return "\n".join(lines)

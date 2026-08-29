"""Database-panel table column ids, defaults, and layout normalization.

Canonical ids match ``ui.panels.database.table.column_widths`` in style configs.
Persisted shape (global and per-path)::

    {
      "columns": { "col_white": {"visible": true, "width": 170}, ... },
      "column_order": ["col_num", "col_unsaved", ...]
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.models.database_model import DatabaseModel


DYNAMIC_HEADER_COLUMN_PREFIX = "hdr_"

# PGN headers already represented by fixed database-table columns (do not offer as dynamic).
FIXED_PGN_HEADER_TAGS: frozenset = frozenset(
    {
        "White",
        "Black",
        "Result",
        "Date",
        "Event",
        "Site",
        "ECO",
        "WhiteElo",
        "BlackElo",
        "TimeControl",
        "CARAGameTags",
        "CARANotes",
        "CARAAnnotations",
        "CARAAnalysisData",
    }
)


def dynamic_header_column_id(tag_name: str) -> str:
    """Stable settings/layout id for a dynamic PGN-header column."""
    return f"{DYNAMIC_HEADER_COLUMN_PREFIX}{tag_name}"


def parse_dynamic_header_tag(column_id: str) -> Optional[str]:
    """Return the PGN tag for a ``hdr_*`` column id, or None."""
    sid = str(column_id or "")
    if not sid.startswith(DYNAMIC_HEADER_COLUMN_PREFIX):
        return None
    tag = sid[len(DYNAMIC_HEADER_COLUMN_PREFIX) :]
    return tag or None


def is_valid_dynamic_header_tag(tag_name: str) -> bool:
    """True if ``tag_name`` is a plausible PGN header name for a dynamic column."""
    tag = str(tag_name or "").strip()
    if not tag or tag in FIXED_PGN_HEADER_TAGS:
        return False
    # Reject characters that would break PGN tag syntax or our id scheme.
    if any(ch in tag for ch in '[]"\\\n\r\t'):
        return False
    return True


def eligible_dynamic_header_tags(unique_tags: Sequence[str]) -> List[str]:
    """Tags from a database's scanned set that may appear as extra columns."""
    out: List[str] = []
    seen: Set[str] = set()
    for tag in unique_tags:
        name = str(tag or "").strip()
        if not is_valid_dynamic_header_tag(name) or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


@dataclass(frozen=True)
class DatabaseTableColumn:
    """One database-table column definition."""

    id: str
    label: str
    logical_index: int
    # Never offered in Show/Hide; always forced hidden in the UI.
    system_hidden: bool = False
    # Only meaningful on search_results tabs; forced visible there, forced hidden elsewhere
    # unless the user layout already shows them (search path always forces visible).
    search_results_only: bool = False


DATABASE_TABLE_COLUMNS: Tuple[DatabaseTableColumn, ...] = (
    DatabaseTableColumn("col_num", "#", DatabaseModel.COL_NUM),
    DatabaseTableColumn(
        "col_file_num", "# in File", DatabaseModel.COL_FILE_NUM, system_hidden=True
    ),
    DatabaseTableColumn("col_unsaved", "●", DatabaseModel.COL_UNSAVED),
    DatabaseTableColumn("col_white", "White", DatabaseModel.COL_WHITE),
    DatabaseTableColumn("col_black", "Black", DatabaseModel.COL_BLACK),
    DatabaseTableColumn("col_white_elo", "WhiteElo", DatabaseModel.COL_WHITE_ELO),
    DatabaseTableColumn("col_black_elo", "BlackElo", DatabaseModel.COL_BLACK_ELO),
    DatabaseTableColumn("col_result", "Result", DatabaseModel.COL_RESULT),
    DatabaseTableColumn("col_date", "Date", DatabaseModel.COL_DATE),
    DatabaseTableColumn("col_event", "Event", DatabaseModel.COL_EVENT),
    DatabaseTableColumn("col_site", "Site", DatabaseModel.COL_SITE),
    DatabaseTableColumn("col_moves", "Moves", DatabaseModel.COL_MOVES),
    DatabaseTableColumn("col_eco", "ECO", DatabaseModel.COL_ECO),
    DatabaseTableColumn("col_time_control", "TimeControl", DatabaseModel.COL_TIMECONTROL),
    DatabaseTableColumn("col_tc_type", "TC Type", DatabaseModel.COL_TC_TYPE),
    DatabaseTableColumn("col_analyzed", "Analyzed", DatabaseModel.COL_ANALYZED),
    DatabaseTableColumn("col_annotated", "Annotated", DatabaseModel.COL_ANNOTATED),
    DatabaseTableColumn("col_notes", "Notes", DatabaseModel.COL_NOTES),
    DatabaseTableColumn(
        "col_source_db",
        "Source DB",
        DatabaseModel.COL_SOURCE_DB,
        search_results_only=True,
    ),
    DatabaseTableColumn(
        "col_ref_ply", "Move", DatabaseModel.COL_REF_PLY, search_results_only=True
    ),
    DatabaseTableColumn("col_tags", "Game tags", DatabaseModel.COL_TAGS),
    DatabaseTableColumn("col_pgn", "PGN", DatabaseModel.COL_PGN),
)

DATABASE_TABLE_COLUMN_IDS: Tuple[str, ...] = tuple(c.id for c in DATABASE_TABLE_COLUMNS)

_DEFAULT_WIDTHS: Dict[str, int] = {
    "col_num": 50,
    "col_file_num": 70,
    "col_unsaved": 25,
    "col_white": 170,
    "col_black": 170,
    "col_white_elo": 80,
    "col_black_elo": 80,
    "col_result": 70,
    "col_date": 110,
    "col_event": 150,
    "col_site": 150,
    "col_moves": 65,
    "col_eco": 65,
    "col_time_control": 85,
    "col_tc_type": 80,
    "col_analyzed": 80,
    "col_annotated": 80,
    "col_notes": 80,
    "col_source_db": 120,
    "col_ref_ply": 70,
    "col_tags": 260,
    "col_pgn": 200,
}


def column_by_id(column_id: str) -> Optional[DatabaseTableColumn]:
    for col in DATABASE_TABLE_COLUMNS:
        if col.id == column_id:
            return col
    return None


def column_by_logical_index(logical_index: int) -> Optional[DatabaseTableColumn]:
    for col in DATABASE_TABLE_COLUMNS:
        if col.logical_index == logical_index:
            return col
    return None


def dynamic_columns_for_model(
    model: Optional[DatabaseModel],
) -> Tuple[DatabaseTableColumn, ...]:
    """Build ephemeral column defs for a model's current dynamic PGN headers."""
    if model is None:
        return ()
    tags = model.get_dynamic_header_tags()
    if not tags:
        return ()
    out: List[DatabaseTableColumn] = []
    for i, tag in enumerate(tags):
        out.append(
            DatabaseTableColumn(
                dynamic_header_column_id(tag),
                tag,
                DatabaseModel.FIXED_COLUMN_COUNT + i,
            )
        )
    return tuple(out)


def resolve_column(
    column_id: str,
    model: Optional[DatabaseModel] = None,
) -> Optional[DatabaseTableColumn]:
    """Resolve a fixed or dynamic column id for the given model."""
    fixed = column_by_id(column_id)
    if fixed is not None:
        return fixed
    tag = parse_dynamic_header_tag(column_id)
    if tag is None or model is None:
        return None
    tags = model.get_dynamic_header_tags()
    try:
        idx = tags.index(tag)
    except ValueError:
        return None
    return DatabaseTableColumn(
        dynamic_header_column_id(tag),
        tag,
        DatabaseModel.FIXED_COLUMN_COUNT + idx,
    )


def resolve_column_by_logical(
    logical_index: int,
    model: Optional[DatabaseModel] = None,
) -> Optional[DatabaseTableColumn]:
    """Resolve a fixed or dynamic column by logical index."""
    fixed = column_by_logical_index(logical_index)
    if fixed is not None:
        return fixed
    if model is None:
        return None
    dyn = int(logical_index) - DatabaseModel.FIXED_COLUMN_COUNT
    tags = model.get_dynamic_header_tags()
    if 0 <= dyn < len(tags):
        tag = tags[dyn]
        return DatabaseTableColumn(
            dynamic_header_column_id(tag),
            tag,
            DatabaseModel.FIXED_COLUMN_COUNT + dyn,
        )
    return None


def default_database_table_columns(
    widths_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the factory-default layout (theme widths when provided)."""
    widths = dict(_DEFAULT_WIDTHS)
    if isinstance(widths_config, dict):
        for key, value in widths_config.items():
            sid = str(key)
            if sid in widths and isinstance(value, (int, float)):
                widths[sid] = int(value)

    columns: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for col in DATABASE_TABLE_COLUMNS:
        visible = not col.system_hidden and not col.search_results_only
        columns[col.id] = {
            "visible": visible,
            "width": int(widths.get(col.id, 100)),
        }
        order.append(col.id)
    return {"columns": columns, "column_order": order}


def normalize_database_table_columns(
    raw: Optional[Dict[str, Any]],
    *,
    widths_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize a layout dict; unknown fixed ids ignored, missing fixed ids filled.

    Dynamic ``hdr_<Tag>`` entries from ``raw`` are preserved (default hidden).
    """
    defaults = default_database_table_columns(widths_config)
    if not isinstance(raw, dict):
        return defaults

    out_columns: Dict[str, Dict[str, Any]] = {}
    raw_columns = raw.get("columns") if isinstance(raw.get("columns"), dict) else {}
    for col in DATABASE_TABLE_COLUMNS:
        default_entry = defaults["columns"][col.id]
        entry = raw_columns.get(col.id)
        visible = default_entry["visible"]
        width = default_entry["width"]
        if isinstance(entry, dict):
            if isinstance(entry.get("visible"), bool) and not col.system_hidden:
                visible = bool(entry["visible"])
            if isinstance(entry.get("width"), (int, float)) and int(entry["width"]) > 0:
                width = int(entry["width"])
        if col.system_hidden:
            visible = False
        out_columns[col.id] = {"visible": visible, "width": width}

    # Preserve dynamic PGN-header column prefs (missing from factory defaults).
    for key, entry in raw_columns.items():
        sid = str(key)
        tag = parse_dynamic_header_tag(sid)
        if tag is None or not is_valid_dynamic_header_tag(tag):
            continue
        visible = False
        width = 100
        if isinstance(entry, dict):
            if isinstance(entry.get("visible"), bool):
                visible = bool(entry["visible"])
            if isinstance(entry.get("width"), (int, float)) and int(entry["width"]) > 0:
                width = int(entry["width"])
        out_columns[dynamic_header_column_id(tag)] = {
            "visible": visible,
            "width": width,
        }

    # At least one non-system fixed column must stay visible.
    if not any(
        out_columns[c.id]["visible"]
        for c in DATABASE_TABLE_COLUMNS
        if not c.system_hidden
    ):
        out_columns["col_num"]["visible"] = True

    raw_order = raw.get("column_order")
    order: List[str] = []
    if isinstance(raw_order, list):
        for item in raw_order:
            sid = str(item)
            if sid in out_columns and sid not in order:
                order.append(sid)
    for col_id in DATABASE_TABLE_COLUMN_IDS:
        if col_id not in order:
            order.append(col_id)
    for col_id in out_columns:
        if col_id not in order:
            order.append(col_id)

    return {"columns": out_columns, "column_order": order}


def canonical_database_table_path(file_path: str) -> str:
    """Normalize a filesystem path used as a by-path settings key."""
    raw = str(file_path or "").strip()
    if not raw or raw in ("clipboard", "search_results"):
        return raw
    try:
        return str(Path(raw).expanduser().resolve())
    except Exception:
        return str(Path(raw).expanduser())


def normalize_database_table_columns_by_path(
    raw: Optional[Dict[str, Any]],
    *,
    widths_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Normalize the per-path override map (keys are canonical absolute paths)."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for path, layout in raw.items():
        key = canonical_database_table_path(str(path))
        if not key or key in ("clipboard", "search_results"):
            # Special tabs use the global default only.
            continue
        if isinstance(layout, dict):
            # Later duplicate keys (same resolved path) win.
            out[key] = normalize_database_table_columns(
                layout, widths_config=widths_config
            )
    return out


def lookup_database_table_columns_for_path(
    by_path: Dict[str, Dict[str, Any]],
    file_path: str,
) -> Optional[Dict[str, Any]]:
    """Return the override for ``file_path``, matching canonical path forms."""
    if not isinstance(by_path, dict):
        return None
    raw = str(file_path or "").strip()
    if not raw or raw in ("clipboard", "search_results"):
        return None
    if raw in by_path:
        return by_path[raw]
    canon = canonical_database_table_path(raw)
    if canon in by_path:
        return by_path[canon]
    for key, layout in by_path.items():
        if canonical_database_table_path(key) == canon:
            return layout
    return None


def user_controllable_columns(
    *,
    is_search_results: bool,
    model: Optional[DatabaseModel] = None,
) -> Sequence[DatabaseTableColumn]:
    """Columns the user may hide/show via the header menu."""
    result: List[DatabaseTableColumn] = []
    for col in DATABASE_TABLE_COLUMNS:
        if col.system_hidden:
            continue
        if col.search_results_only and not is_search_results:
            continue
        if col.search_results_only and is_search_results:
            # Keep Source DB / Move always visible on search results.
            continue
        result.append(col)
    result.extend(dynamic_columns_for_model(model))
    return tuple(result)


def effective_visibility_for_tab(
    layout: Dict[str, Any],
    *,
    is_search_results: bool,
    model: Optional[DatabaseModel] = None,
) -> Dict[str, bool]:
    """Resolve per-column visibility for a tab type.

    Dynamic ``hdr_*`` columns are only present when the tag exists on ``model``;
    they default to hidden unless the layout marks them visible.
    """
    columns = layout.get("columns") if isinstance(layout.get("columns"), dict) else {}
    out: Dict[str, bool] = {}
    for col in DATABASE_TABLE_COLUMNS:
        if col.system_hidden:
            out[col.id] = False
            continue
        if col.search_results_only:
            out[col.id] = bool(is_search_results)
            continue
        entry = columns.get(col.id)
        if isinstance(entry, dict) and isinstance(entry.get("visible"), bool):
            out[col.id] = bool(entry["visible"])
        else:
            out[col.id] = True
    for col in dynamic_columns_for_model(model):
        entry = columns.get(col.id)
        if isinstance(entry, dict) and isinstance(entry.get("visible"), bool):
            out[col.id] = bool(entry["visible"])
        else:
            out[col.id] = False
    if not any(out[c.id] for c in DATABASE_TABLE_COLUMNS if not c.system_hidden):
        out["col_num"] = True
    return out

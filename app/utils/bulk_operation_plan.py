"""Serialize and deserialize named bulk-operation plans (operations only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.controllers.bulk_operations_controller import (
    BulkOperation,
    validate_bulk_operation,
)

_BOOL_FIELDS = (
    "case_sensitive",
    "use_regex",
    "copy_value_from_source",
    "remove_comments",
    "remove_variations",
    "remove_non_standard_tags",
    "remove_annotations",
)

_STR_FIELDS = (
    "find_text",
    "replace_text",
    "source_tag",
)


def bulk_operation_to_dict(operation: BulkOperation) -> Dict[str, Any]:
    """Convert a BulkOperation to a JSON-friendly dict."""
    return {
        "mode": operation.mode,
        "tags": list(operation.tags),
        "find_text": operation.find_text,
        "replace_text": operation.replace_text,
        "case_sensitive": bool(operation.case_sensitive),
        "use_regex": bool(operation.use_regex),
        "source_tag": operation.source_tag,
        "copy_value_from_source": bool(operation.copy_value_from_source),
        "remove_comments": bool(operation.remove_comments),
        "remove_variations": bool(operation.remove_variations),
        "remove_non_standard_tags": bool(operation.remove_non_standard_tags),
        "remove_annotations": bool(operation.remove_annotations),
    }


def bulk_operation_from_dict(data: Any) -> Optional[BulkOperation]:
    """Build a BulkOperation from a dict, or None if invalid."""
    if not isinstance(data, dict):
        return None
    mode = str(data.get("mode", "") or "").strip()
    if not mode:
        return None

    tags_raw = data.get("tags", [])
    if not isinstance(tags_raw, list):
        return None
    tags = tuple(str(t) for t in tags_raw if isinstance(t, (str, int, float)))

    kwargs: Dict[str, Any] = {"mode": mode, "tags": tags}
    for key in _STR_FIELDS:
        raw = data.get(key, "")
        kwargs[key] = str(raw) if raw is not None else ""
    for key in _BOOL_FIELDS:
        kwargs[key] = bool(data.get(key, False))

    try:
        operation = BulkOperation(**kwargs)
    except TypeError:
        return None
    if validate_bulk_operation(operation) is not None:
        return None
    return operation


def plan_operations_to_dicts(operations: Sequence[BulkOperation]) -> List[Dict[str, Any]]:
    """Serialize an ordered plan (operations only)."""
    return [bulk_operation_to_dict(op) for op in operations]


def plan_operations_from_dicts(
    raw: Any,
) -> Tuple[List[BulkOperation], Optional[str]]:
    """Deserialize a plan list.

    Returns:
        (operations, error). On success error is None. Rejects the whole plan
        if ``raw`` is not a list or any step is invalid/empty.
    """
    if not isinstance(raw, list):
        return [], "Saved plan is corrupt (expected a list of operations)"
    if not raw:
        return [], "Saved plan is empty"
    operations: List[BulkOperation] = []
    for index, item in enumerate(raw):
        op = bulk_operation_from_dict(item)
        if op is None:
            return [], f"Saved plan has an invalid operation at step {index + 1}"
        operations.append(op)
    return operations, None


def normalize_plan_name(name: str) -> str:
    """Trim a plan name; empty after trim is invalid."""
    return (name or "").strip()

import argparse
import json
from pathlib import Path
from typing import Any, Dict


REF_MARKER_KEY = "$ref"


def _is_ref_marker(value: Any) -> bool:
    return isinstance(value, dict) and set(value.keys()) == {REF_MARKER_KEY} and isinstance(value.get(REF_MARKER_KEY), str)


def replace_font_family_refs(node: Any, *, from_value: str, ref_name: str) -> Any:
    """Replace font family string occurrences under *font_family* keys with a structured ref marker."""
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for k, v in node.items():
            if "font_family" in k and v == from_value:
                out[k] = {REF_MARKER_KEY: ref_name}
            else:
                out[k] = replace_font_family_refs(v, from_value=from_value, ref_name=ref_name)
        return out
    if isinstance(node, list):
        return [replace_font_family_refs(v, from_value=from_value, ref_name=ref_name) for v in node]
    return node


def replace_int_refs(node: Any, *, key_exact: str, from_value: int, ref_name: str) -> Any:
    """Replace integer occurrences for an exact key with a structured ref marker.

    Example:
      key_exact="font_size", from_value=11 -> { "$ref": "$_FONT_SIZE_BASE" }
    """
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for k, v in node.items():
            if k == key_exact and isinstance(v, int) and v == from_value:
                out[k] = {REF_MARKER_KEY: ref_name}
            else:
                out[k] = replace_int_refs(v, key_exact=key_exact, from_value=from_value, ref_name=ref_name)
        return out
    if isinstance(node, list):
        return [replace_int_refs(v, key_exact=key_exact, from_value=from_value, ref_name=ref_name) for v in node]
    return node


def replace_ref_name(node: Any, *, from_ref: str, to_ref: str) -> Any:
    """Replace structured ref marker names globally."""
    if isinstance(node, dict):
        if set(node.keys()) == {REF_MARKER_KEY} and node.get(REF_MARKER_KEY) == from_ref:
            return {REF_MARKER_KEY: to_ref}
        return {k: replace_ref_name(v, from_ref=from_ref, to_ref=to_ref) for k, v in node.items()}
    if isinstance(node, list):
        return [replace_ref_name(v, from_ref=from_ref, to_ref=to_ref) for v in node]
    return node


def replace_rgb_refs(
    node: Any,
    *,
    key_predicate,
    from_rgb: tuple[int, int, int],
    ref_name: str,
) -> Any:
    """Replace RGB triplet lists with a structured ref marker for matching keys only."""
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for k, v in node.items():
            if key_predicate(k) and isinstance(v, list) and len(v) == 3 and tuple(v) == from_rgb:
                out[k] = {REF_MARKER_KEY: ref_name}
            else:
                out[k] = replace_rgb_refs(v, key_predicate=key_predicate, from_rgb=from_rgb, ref_name=ref_name)
        return out
    if isinstance(node, list):
        return [replace_rgb_refs(v, key_predicate=key_predicate, from_rgb=from_rgb, ref_name=ref_name) for v in node]
    return node


def replace_rgb_refs_with_path(
    node: Any,
    *,
    path: tuple[str, ...],
    key_path_predicate,
    from_rgb: tuple[int, int, int],
    ref_name: str,
) -> Any:
    """Replace RGB triplet lists with a structured ref marker for matching (key, path) only."""
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for k, v in node.items():
            next_path = path + (k,)
            if (
                key_path_predicate(k, next_path)
                and isinstance(v, list)
                and len(v) == 3
                and tuple(v) == from_rgb
            ):
                out[k] = {REF_MARKER_KEY: ref_name}
            else:
                out[k] = replace_rgb_refs_with_path(
                    v,
                    path=next_path,
                    key_path_predicate=key_path_predicate,
                    from_rgb=from_rgb,
                    ref_name=ref_name,
                )
        return out
    if isinstance(node, list):
        return [
            replace_rgb_refs_with_path(
                v,
                path=path,
                key_path_predicate=key_path_predicate,
                from_rgb=from_rgb,
                ref_name=ref_name,
            )
            for v in node
        ]
    return node


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("app/config/config.json"),
        help="Path to config.json",
    )
    parser.add_argument(
        "--from-font",
        default="Helvetica Neue",
        help="Font family string to replace",
    )
    parser.add_argument(
        "--ref",
        default="$_FONT_FAMILY_PRIMARY",
        help="Constant key to reference via {\"$ref\": ...}",
    )
    parser.add_argument(
        "--replace-int-key",
        default=None,
        help="Replace exact integer key occurrences (e.g. font_size)",
    )
    parser.add_argument(
        "--from-int",
        type=int,
        default=None,
        help="Integer value to replace (used with --replace-int-key)",
    )
    parser.add_argument(
        "--replace-ref-from",
        default=None,
        help="Replace ref marker name (e.g. $_OLD)",
    )
    parser.add_argument(
        "--replace-ref-to",
        default=None,
        help="New ref marker name (e.g. $_NEW)",
    )
    parser.add_argument(
        "--replace-rgb-key-mode",
        default=None,
        choices=["text", "tabs_text", "background"],
        help="Replace RGB values for selected key families (currently: text-related keys only)",
    )
    parser.add_argument(
        "--from-rgb",
        default=None,
        help="RGB triplet to replace, formatted as r,g,b (e.g. 240,240,240)",
    )
    args = parser.parse_args()

    # PowerShell users may pass an escaped value like "\$_FOO".
    # Normalize so we always write "$_FOO" into JSON.
    args.ref = args.ref.lstrip("\\")

    config_path: Path = args.config
    raw = config_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    # Ensure constants exists (do not overwrite if already present)
    if isinstance(data, dict):
        constants = data.get("constants")
        if constants is None:
            data["constants"] = {args.ref: args.from_font}
        elif isinstance(constants, dict) and args.ref not in constants:
            constants[args.ref] = args.from_font

    # If a previous run accidentally wrote {"$ref": "\\"}, fix those to the intended ref.
    def _repair_broken_refs(node: Any) -> Any:
        if isinstance(node, dict):
            if set(node.keys()) == {REF_MARKER_KEY} and node.get(REF_MARKER_KEY) == "\\":
                return {REF_MARKER_KEY: args.ref}
            return {k: _repair_broken_refs(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_repair_broken_refs(v) for v in node]
        return node

    data = _repair_broken_refs(data)

    updated = replace_font_family_refs(data, from_value=args.from_font, ref_name=args.ref)
    if args.replace_int_key is not None and args.from_int is not None:
        updated = replace_int_refs(
            updated,
            key_exact=args.replace_int_key,
            from_value=args.from_int,
            ref_name=args.ref,
        )
    if args.replace_ref_from is not None and args.replace_ref_to is not None:
        updated = replace_ref_name(
            updated,
            from_ref=args.replace_ref_from,
            to_ref=args.replace_ref_to,
        )
    if args.replace_rgb_key_mode is not None and args.from_rgb is not None:
        parts = [p.strip() for p in args.from_rgb.split(",")]
        if len(parts) != 3:
            raise SystemExit("--from-rgb must be formatted as r,g,b")
        rgb = (int(parts[0]), int(parts[1]), int(parts[2]))

        if args.replace_rgb_key_mode == "text":
            def key_pred(k: str) -> bool:
                lk = k.lower()
                return (
                    lk == "text_color"
                    or lk.endswith("_text_color")
                    or lk == "label_color"
                    or lk.endswith("_label_color")
                    or lk == "placeholder_text_color"
                    or lk.endswith("placeholder_text_color")
                )

            updated = replace_rgb_refs(
                updated,
                key_predicate=key_pred,
                from_rgb=rgb,
                ref_name=args.ref,
            )

        elif args.replace_rgb_key_mode == "tabs_text":
            def key_path_pred(k: str, path: tuple[str, ...]) -> bool:
                # Only replace "text": [r,g,b] under:
                #   ... .tabs.colors.(normal|hover|active).text
                if k != "text":
                    return False
                if len(path) < 5:
                    return False
                # path ends with (..., "tabs", "colors", state, "text")
                state = path[-2]
                return path[-4] == "tabs" and path[-3] == "colors" and state in {"normal", "hover", "active"}

            updated = replace_rgb_refs_with_path(
                updated,
                path=(),
                key_path_predicate=key_path_pred,
                from_rgb=rgb,
                ref_name=args.ref,
            )

        elif args.replace_rgb_key_mode == "background":
            def key_pred(k: str) -> bool:
                lk = k.lower()
                return (
                    lk == "background_color"
                    or lk.endswith("_background_color")
                    or lk == "pane_background"
                    or lk == "alternate_background_color"
                    or lk == "section_background"
                )

            updated = replace_rgb_refs(
                updated,
                key_predicate=key_pred,
                from_rgb=rgb,
                ref_name=args.ref,
            )

    config_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


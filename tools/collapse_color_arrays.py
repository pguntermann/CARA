import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def _is_color_array(value: Any) -> bool:
    """Return True for RGB/RGBA arrays like [r,g,b] or [r,g,b,a]."""
    if not isinstance(value, list):
        return False
    if len(value) not in (3, 4):
        return False
    if not all(isinstance(x, int) for x in value):
        return False
    return all(0 <= x <= 255 for x in value)


def _json_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dump(node: Any, indent: int, level: int) -> str:
    pad = " " * (indent * level)
    pad_in = " " * (indent * (level + 1))

    if isinstance(node, dict):
        if not node:
            return "{}"
        items = []
        for k, v in node.items():
            items.append(f"{pad_in}{_json_scalar(k)}: {_dump(v, indent, level + 1)}")
        return "{\n" + ",\n".join(items) + f"\n{pad}" + "}"

    if isinstance(node, list):
        if _is_color_array(node):
            # Single-line: [45, 45, 50]
            inner = ", ".join(str(x) for x in node)
            return f"[{inner}]"
        if not node:
            return "[]"
        # Multi-line list, one element per line (keeps config style consistent)
        parts = [f"{pad_in}{_dump(v, indent, level + 1)}" for v in node]
        return "[\n" + ",\n".join(parts) + f"\n{pad}" + "]"

    return _json_scalar(node)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collapse RGB/RGBA arrays to single-line formatting in JSON.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("app/config/config.json"),
        help="Input JSON file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file (defaults to in-place rewrite of --input)",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indent size",
    )
    args = parser.parse_args()

    src: Path = args.input
    dst: Path = args.output or src

    data = json.loads(src.read_text(encoding="utf-8"))
    out = _dump(data, indent=args.indent, level=0) + "\n"
    dst.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""Generate synthetic Chess Log test data for full-year binning validation.

Takes a real tagged PGN file (e.g. TaggingTestGames.pgn), clones games across
a full calendar year with deliberate density variation, and writes a new PGN.

CARAChessLog / CARAChessLogInfo / CARAChessLogChecksum triples are copied
verbatim — checksums only cover the JSON payload (keyed by variation path),
not by Date/Round/UTCDate, so they remain valid after header rewriting.

Also produces a *mixed* output (TaggingTestGames_synthetic_2026_mixed.pgn) where
each game is randomly assigned CLAMP, CCT, or 3x3 preset tagging so the Chess
Log Charts tab can be tested with a genuine three-way mix.

Usage:
    python scripts/generate_synthetic_chess_log_data.py
    python scripts/generate_synthetic_chess_log_data.py --input TaggingTestGames.pgn
    python scripts/generate_synthetic_chess_log_data.py --output out.pgn --seed 42
"""

from __future__ import annotations

import argparse
import base64
import calendar
import gzip
import hashlib
import json
import random
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Month distribution for the target year ────────────────────────────────────
# Two empty months (Jan, Jun), two sparse (Feb, Nov), two dense (May, Oct).
MONTH_COUNTS = {
    1: 0,   # empty
    2: 2,   # sparse
    3: 6,
    4: 4,
    5: 12,  # dense
    6: 0,   # empty
    7: 3,
    8: 8,
    9: 5,
    10: 10, # dense
    11: 1,  # sparse
    12: 4,
}

_DATE_RE = re.compile(r'^(\[Date\s+")\d{4}\.\d{2}\.\d{2}("\])$')
_UTCDATE_RE = re.compile(r'^(\[UTCDate\s+")\d{4}\.\d{2}\.\d{2}("\])$')
_ROUND_RE = re.compile(r'^\[Round\s+"[^"]*"\]$')

# ── Mixed-preset generation helpers ──────────────────────────────────────────
# CCT category set (all three; a single moment may select 1-3 of them).
_CCT_CATS = ("Checks", "Captures", "Threats")

# Placeholder why-note texts for 3x3 moments (one per Why answer).
_3X3_WHYS = (
    "[synthetic] I made this move because it looked active",
    "[synthetic] It was suboptimal because I missed a tactic",
    "[synthetic] The engine's suggestion is stronger because it centralises a piece",
)

# CARAChessLog header regexes used by _inject_cl().
_CL_HDR_RE = re.compile(r'^\[CARAChessLog[A-Za-z]* "')


def _cl_entry(preset: str, cat: str, why: str = "") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "preset": preset,
        "cat": cat,
        "why": why,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _encode_cl(paths: dict) -> tuple[str, str, str]:
    """Encode a paths dict → (encoded_tag_value, info_str, checksum)."""
    payload = {"_v": 1, "paths": paths}
    json_text = json.dumps(payload, ensure_ascii=False)
    data_bytes = json_text.encode("utf-8")
    checksum = hashlib.sha256(data_bytes).hexdigest()
    encoded = base64.b64encode(gzip.compress(data_bytes, compresslevel=9)).decode("ascii")
    info_str = f"App Version: synthetic, Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return encoded, info_str, checksum


def _cct_paths(rng: random.Random) -> dict:
    """Generate 1-3 CCT moments (each moment selects 1-3 categories)."""
    n_moments = rng.randint(1, 3)
    move_nums = sorted(rng.sample(range(5, 31), n_moments))
    paths: dict = {}
    for mn in move_nums:
        n_cats = rng.randint(1, 3)
        cats = rng.sample(list(_CCT_CATS), n_cats)
        paths[f"syn_{mn}"] = [_cl_entry("CCT", c) for c in cats]
    return paths


def _3x3_paths(rng: random.Random) -> dict:
    """Generate 1-2 3x3 moments (each with Why1/Why2/Why3 entries)."""
    n_moments = rng.randint(1, 2)
    move_nums = sorted(rng.sample(range(5, 31), n_moments))
    paths: dict = {}
    for mn in move_nums:
        paths[f"syn_{mn}"] = [
            _cl_entry("3x3", f"Why{i + 1}", _3X3_WHYS[i]) for i in range(3)
        ]
    return paths


def _inject_cl(block: str, paths: dict) -> str:
    """Replace existing CARAChessLog* tags with new ones; CARAGameTags is left unchanged.

    Splits the game block into header lines and move text, rebuilds the header
    section with old CARAChessLog* tags stripped and new ones appended.
    """
    encoded, info_str, checksum = _encode_cl(paths)

    lines = block.splitlines()

    # Separate header lines from move text (first non-header non-blank line).
    hdr_raw: list[str] = []
    body: list[str] = []
    found_body = False
    for line in lines:
        s = line.strip()
        if found_body:
            body.append(line)
        elif s and not s.startswith("["):
            found_body = True
            body.append(line)
        else:
            hdr_raw.append(line)

    # Rebuild header lines: strip old CL tags.
    new_hdr: list[str] = []
    for line in hdr_raw:
        s = line.strip()
        if not s:
            continue  # drop blank lines within header section
        if _CL_HDR_RE.match(s):
            continue  # strip old CARAChessLog* tags
        new_hdr.append(line)

    new_hdr.append(f'[CARAChessLog "{encoded}"]')
    new_hdr.append(f'[CARAChessLogInfo "{info_str}"]')
    new_hdr.append(f'[CARAChessLogChecksum "{checksum}"]')

    return "\n".join(new_hdr) + "\n\n" + "\n".join(body)


def _split_games(text: str) -> list[str]:
    """Split a PGN file text into individual raw game blocks."""
    blocks: list[str] = []
    current: list[str] = []
    in_movetext = False

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[Event "):
            if current:
                blocks.append("".join(current).rstrip() + "\n")
            current = [line]
            in_movetext = False
        elif current:
            current.append(line)
            if not stripped.startswith("[") and stripped:
                in_movetext = True

    if current:
        blocks.append("".join(current).rstrip() + "\n")

    return [b for b in blocks if b.strip()]


def _rewrite_game(block: str, year: int, month: int, day: int, slot: int) -> str:
    """Return block with Date/UTCDate/Round rewritten; all other headers untouched."""
    date_str = f"{year:04d}.{month:02d}.{day:02d}"
    lines = block.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if _DATE_RE.match(stripped):
            m = _DATE_RE.match(stripped)
            out.append(f'{m.group(1)}{date_str}{m.group(2)}\n')
        elif _UTCDATE_RE.match(stripped):
            m = _UTCDATE_RE.match(stripped)
            out.append(f'{m.group(1)}{date_str}{m.group(2)}\n')
        elif _ROUND_RE.match(stripped):
            out.append(f'[Round "syn-{slot:03d}"]\n')
        else:
            out.append(line if line.endswith("\n") else line + "\n")
    return "".join(out)


def generate(
    input_path: Path,
    output_path: Path,
    year: int,
    seed: int,
    month_counts: dict[int, int] | None = None,
) -> None:
    if month_counts is None:
        month_counts = MONTH_COUNTS

    text = input_path.read_text(encoding="utf-8")
    source_games = _split_games(text)
    if not source_games:
        print(f"ERROR: no games found in {input_path}", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(seed)

    # Build the target slot list: (month, day) pairs in chronological order.
    slots: list[tuple[int, int]] = []
    for month in range(1, 13):
        count = month_counts.get(month, 0)
        _, days_in_month = calendar.monthrange(year, month)
        days = sorted(rng.sample(range(1, days_in_month + 1), min(count, days_in_month)))
        for day in days:
            slots.append((month, day))

    total = len(slots)
    out_blocks: list[str] = []
    for slot_idx, (month, day) in enumerate(slots):
        src = source_games[slot_idx % len(source_games)]
        out_blocks.append(_rewrite_game(src, year, month, day, slot_idx + 1))

    output_path.write_text("\n".join(out_blocks) + "\n", encoding="utf-8")

    # ── Report ────────────────────────────────────────────────────────────────
    month_names = [calendar.month_abbr[m] for m in range(1, 13)]
    print(f"Written {total} games to {output_path}")
    print(f"Source: {len(source_games)} games from {input_path}")
    print()
    print(f"{'Month':<6}  {'Count':>5}  {'Bar'}")
    for month in range(1, 13):
        count = sum(1 for m, _ in slots if m == month)
        bar = "█" * count
        print(f"{month_names[month-1]:<6}  {count:>5}  {bar}")

    # Verify CARAChessLog triples survived bit-identical.
    original_cl_lines = [l for l in text.splitlines() if l.startswith("[CARAChessLog ")]
    output_text = output_path.read_text(encoding="utf-8")
    output_cl_lines = [l for l in output_text.splitlines() if l.startswith("[CARAChessLog ")]
    original_values = {l for l in original_cl_lines}
    missing = original_values - set(output_cl_lines)
    if missing:
        print(f"\nWARNING: {len(missing)} CARAChessLog value(s) not found in output — header rewrite may have corrupted them.")
    else:
        tagged_src = len(original_cl_lines)
        tagged_out = len(output_cl_lines)
        print(f"\nCARAChessLog: {tagged_src} unique value(s) in source, {tagged_out} instances in output — all values preserved bit-identical.")


def generate_mixed(
    input_path: Path,
    output_path: Path,
    year: int,
    seed: int,
    month_counts: dict[int, int] | None = None,
) -> None:
    """Like generate(), but randomly assigns CLAMP / CCT / 3x3 per game slot.

    CLAMP games keep the source game's existing CARAChessLog tags verbatim.
    CCT and 3x3 games get freshly synthesised tags injected (replacing any
    existing source tags).  Same slot dates as generate() (same seed).
    """
    if month_counts is None:
        month_counts = MONTH_COUNTS

    text = input_path.read_text(encoding="utf-8")
    source_games = _split_games(text)
    if not source_games:
        print(f"ERROR: no games found in {input_path}", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(seed)
    rng_tags = random.Random(seed + 1)  # separate RNG for preset assignment / tag content

    # Same slot-generation logic as generate() so dates match.
    slots: list[tuple[int, int]] = []
    for month in range(1, 13):
        count = month_counts.get(month, 0)
        _, days_in_month = calendar.monthrange(year, month)
        days = sorted(rng.sample(range(1, days_in_month + 1), min(count, days_in_month)))
        for day in days:
            slots.append((month, day))

    preset_choices = ["CLAMP", "CCT", "3x3"]
    preset_weights = [0.40, 0.35, 0.25]
    presets = rng_tags.choices(preset_choices, weights=preset_weights, k=len(slots))

    out_blocks: list[str] = []
    preset_counts: dict[str, int] = {"CLAMP": 0, "CCT": 0, "3x3": 0}

    for slot_idx, ((month, day), preset) in enumerate(zip(slots, presets)):
        src = source_games[slot_idx % len(source_games)]
        block = _rewrite_game(src, year, month, day, slot_idx + 1)

        if preset == "CCT":
            block = _inject_cl(block, _cct_paths(rng_tags))
        elif preset == "3x3":
            block = _inject_cl(block, _3x3_paths(rng_tags))
        # CLAMP: keep block (and its existing CARAChessLog tags) unchanged.

        out_blocks.append(block)
        preset_counts[preset] += 1

    output_path.write_text("\n".join(out_blocks) + "\n", encoding="utf-8")

    total = len(slots)
    print(f"\nMixed output: {total} games → {output_path}")
    print(
        f"Preset mix:  CLAMP={preset_counts['CLAMP']}  "
        f"CCT={preset_counts['CCT']}  3x3={preset_counts['3x3']}"
    )

    # Verify CARAChessLog tags were written for all CCT+3x3 slots.
    output_text = output_path.read_text(encoding="utf-8")
    cl_count = sum(1 for ln in output_text.splitlines() if ln.startswith('[CARAChessLog "'))
    expected_min = preset_counts["CCT"] + preset_counts["3x3"]
    if cl_count >= expected_min:
        print(
            f"CARAChessLog: {cl_count} tag(s) in output "
            f"(≥{expected_min} expected for CCT+3x3) ✓"
        )
    else:
        print(
            f"WARNING: only {cl_count} CARAChessLog tag(s) found; "
            f"expected ≥{expected_min}"
        )


def main() -> None:
    repo_root = Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Generate synthetic Chess Log test PGN")
    parser.add_argument("--input", default=str(repo_root / "TaggingTestGames.pgn"),
                        help="Input PGN file (default: TaggingTestGames.pgn at repo root)")
    parser.add_argument("--output", default=str(repo_root / "TaggingTestGames_synthetic_2026.pgn"),
                        help="Output PGN file (default: TaggingTestGames_synthetic_2026.pgn at repo root)")
    parser.add_argument("--mixed-output",
                        default=str(repo_root / "TaggingTestGames_synthetic_2026_mixed.pgn"),
                        help="Mixed-preset output PGN (default: TaggingTestGames_synthetic_2026_mixed.pgn)")
    parser.add_argument("--year", type=int, default=2026,
                        help="Target year for synthesized dates (default: 2026)")
    parser.add_argument("--seed", type=int, default=20260830,
                        help="RNG seed for reproducibility (default: 20260830)")
    args = parser.parse_args()

    generate(
        input_path=Path(args.input),
        output_path=Path(args.output),
        year=args.year,
        seed=args.seed,
    )

    generate_mixed(
        input_path=Path(args.input),
        output_path=Path(args.mixed_output),
        year=args.year,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()

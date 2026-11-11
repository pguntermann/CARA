"""Shallow-note classifier service for Chess Log Charts.

Wraps the AIService call and reply-parse logic that was previously inlined in
ChessLogShallowThread.run().  Pure function — no Qt dependencies.

Behavior change vs. the old inline code
----------------------------------------
Previously, any line the parser couldn't understand was silently dropped —
the corresponding note stayed DEEP but there was no record that the model
failed to classify it.  Now every input index is accounted for:

- An index is "parsed" when the reply contains a verdict line for it.
- Unparsed indices are returned in ``ShallowResult.unparsed_indices``.
- An unparsed index is NEVER marked SHALLOW — it stays DEEP unchanged.
- The caller (ChessLogShallowThread) surfaces a notice to the user when
  ``unparsed_indices`` is non-empty.

Key tuples
----------
All key sets use a uniform 4-tuple ``(game, path_key, preset, cat)``
where ``game`` is the ``GameData`` object (identity-keyed, no custom
``__hash__``/``__eq__``):

- CLAMP/CCT: ``cat=""`` (empty string) — one entry per distinct note per moment.
- 3x3: ``cat`` is one of ``"Why1"``, ``"Why2"``, ``"Why3"``, ``"Why4"`` —
  each answer is judged independently.

3x3 classifier
--------------
``classify_notes_3x3`` classifies all four Why answers independently.

  WHY1/WHY2/WHY3 → SPECIFIC, GENERIC, or BLANK
      GENERIC → ``(game, pk, "3x3", cat)`` in ``shallow_keys``
  WHY4 (Lesson) → REAL, FILLER, or BLANK
      FILLER → ``(game, pk, "3x3", "Why4")`` in ``vague_keys``

The old "a real lesson rescues a generic Why1" combining rule is removed.
Each answer stands alone.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from app.services.ai_service import AIService, TokenUsage
from app.services.logging_service import LoggingService
from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShallowResult:
    """Result of classify_notes() or classify_notes_3x3()."""

    success: bool
    # (game, path_key, preset, cat) 4-tuples judged SHALLOW.
    # game is a GameData object (identity-keyed).
    # CLAMP/CCT: cat="" (empty).  3x3: cat in {"Why1","Why2","Why3"}.
    shallow_keys: FrozenSet[Tuple[Any, str, str, str]]
    error: Optional[str]
    usage: Optional[TokenUsage]
    model: str
    # Input indices for which the model returned no parsable verdict.
    # These notes are left unchanged (not marked shallow).
    unparsed_indices: Tuple[int, ...]
    # (game, path_key, "3x3", "Why4") 4-tuples with a vague lesson.
    # Always empty for CLAMP/CCT notes.
    vague_keys: FrozenSet[Tuple[Any, str, str, str]] = field(default_factory=frozenset)


# ---------------------------------------------------------------------------
# CLAMP/CCT verdict parsing
# ---------------------------------------------------------------------------

# Matches a verdict line anchored to the start of the line (MULTILINE).
# Leading decoration: whitespace, markdown bullets/pipes/angles/brackets.
# Separators: the classic set plus `|` for markdown-table replies.
# Trailing content must be whitespace/decoration/end-of-line — anything else
# (e.g. "0: DEEP because of …") rejects the line so the parser never guesses.
_LINE_RE = re.compile(
    r'^[\s|*>_\-\[]*'      # leading markdown/bullet/bracket decoration
    r'(\d+)\s*'             # the index
    r'[-\]:.)|]\s*'         # separator — adds `|` for markdown-table shape
    r'[*_`]*\s*'            # optional bold/italic/code decoration
    r'(SHALLOW|DEEP)'       # the verdict — gated so prose can't sneak in
    r'\s*[*_`|.,!;]*\s*$',  # trailing decoration (incl. punct) + end-of-line
    re.IGNORECASE | re.MULTILINE,
)


def _parse_verdicts(reply_text: str, note_count: int) -> dict:
    """Return {idx: verdict_upper} from the model reply.

    Preprocessing step: insert a newline between SHALLOW/DEEP and a following
    digit so that adjacent text blocks joined without a separator
    (e.g. "0: SHALLOW1: DEEP") are split before the line regex runs.

    Last occurrence wins for any duplicate index (model may reconsider).
    """
    text = re.sub(r'\b(SHALLOW|DEEP)(\d)', r'\1\n\2', reply_text, flags=re.IGNORECASE)
    parsed: dict = {}
    for m in _LINE_RE.finditer(text):
        try:
            idx = int(m.group(1))
        except ValueError:
            continue
        verdict = m.group(2).upper()
        if verdict not in ("SHALLOW", "DEEP"):
            continue
        if 0 <= idx < note_count:
            parsed[idx] = verdict
    return parsed


# ---------------------------------------------------------------------------
# 3x3 verdict parsing
# ---------------------------------------------------------------------------

# Line-start anchor for 3x3: optional leading decoration, index, separator.
# Same structural rule as the CLAMP _LINE_RE prefix — a verdict line must
# open with a digit (index) followed by a separator character.  This blocks
# prose lines whose only "index" is a move number mid-sentence.
_LINE_PREFIX_3X3 = re.compile(
    r'^[\s|*>_\-\[]*'   # leading decoration
    r'(\d+)\s*'           # the index
    r'[-\]:.)|]',         # separator character
    re.MULTILINE,
)

# Matches one FIELD=VALUE assignment anywhere on a line.  Tolerates:
#   - markdown bold/backtick/underscore wrapping on either side of the value
#   - optional whitespace between the = and the value
# The field name is captured in group 1; the value word in group 2.
_FIELD_RE_3X3 = re.compile(
    r'[*_`]*(WHY1|WHY2|WHY3|LESSON)\s*=\s*[*_`\s]*(SPECIFIC|GENERIC|BLANK|REAL|FILLER)[*_`]*',
    re.IGNORECASE,
)

_WHY_VALUES = frozenset(("SPECIFIC", "GENERIC", "BLANK"))
_LESSON_VALUES = frozenset(("REAL", "FILLER", "BLANK"))


def _parse_3x3_verdicts(reply_text: str, note_count: int) -> dict:
    """Return {idx: (why1_upper, why2_upper, why3_upper, lesson_upper)}.

    Tolerant of field order, comma/semicolon/pipe separators, and markdown
    decoration around values.  All four fields must be present and valid on
    the same line; a missing field, duplicate field, or invalid value leaves
    the index unparsed.

    Preprocessing: insert a newline when any enum value is immediately followed
    by a digit (glued reply blocks).  Last occurrence wins for duplicates.
    """
    text = re.sub(r'\b(SPECIFIC|GENERIC|BLANK|REAL|FILLER)(\d)', r'\1\n\2', reply_text, flags=re.IGNORECASE)
    parsed: dict = {}
    for line in text.splitlines():
        m = _LINE_PREFIX_3X3.match(line)
        if not m:
            continue
        try:
            idx = int(m.group(1))
        except ValueError:
            continue
        if not (0 <= idx < note_count):
            continue
        rest = line[m.end():]
        fields: dict = {}
        duplicate = False
        for fm in _FIELD_RE_3X3.finditer(rest):
            fname = fm.group(1).upper()
            fval = fm.group(2).upper()
            if fname in fields:
                duplicate = True
                break
            fields[fname] = fval
        if duplicate:
            continue
        if len(fields) != 4:
            continue
        if fields["WHY1"] not in _WHY_VALUES:
            continue
        if fields["WHY2"] not in _WHY_VALUES:
            continue
        if fields["WHY3"] not in _WHY_VALUES:
            continue
        if fields["LESSON"] not in _LESSON_VALUES:
            continue
        parsed[idx] = (fields["WHY1"], fields["WHY2"], fields["WHY3"], fields["LESSON"])
    return parsed


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

def _classifier_token_limit(note_count: int, per_note: int = 60) -> int:
    """Conservative output-token budget for the classifier.

    CLAMP/CCT (two-verdict format): ~31 tokens/note observed; 60/note (~2×)
    used here.  3x3 (four-verdict format): extrapolated conservatively to
    ~55 tokens/note worst-case; 90/note (~1.6×) gives adequate headroom.

    Pass ``per_note=90`` for the 3x3 classifier.  Floor of 2000 matches the
    former default so no small-library regression.
    """
    return max(2000, note_count * per_note + 500)


# ---------------------------------------------------------------------------
# Ignore-honour check (mirrors ChessLogStorageService.is_entry_ignore_honoured
# without pulling in Qt-dependent imports)
# ---------------------------------------------------------------------------

def _is_ignore_honoured(entry: Dict[str, Any]) -> bool:
    """Return True when this entry's ignore_shallow flag is in effect."""
    if not entry.get("ignore_shallow", False):
        return False
    h = entry.get("ignore_text_hash")
    if not h:
        return True  # legacy: no hash → honour unconditionally
    why = (entry.get("why") or "").strip()
    if not why:
        return False
    return hashlib.sha256(why.encode("utf-8")).hexdigest() == h


# ---------------------------------------------------------------------------
# Note builder (shared with Qt controller and acceptance harness)
# ---------------------------------------------------------------------------

def build_notes(
    games: Iterable[Any],
    tags_resolver: Callable[[Any], Dict[str, List[Dict[str, Any]]]],
) -> Tuple[
    List[Tuple[int, Any, str, str, str]],
    List[Tuple[int, Any, str, str, str, str, str, str]],
    List[FrozenSet[str]],
]:
    """Build classifier-ready note tuples by replicating Check Logs' filter rules.

    Splits entries by preset: CLAMP/CCT emit one legacy_notes entry per
    distinct non-blank note text per moment (first-seen order); 3x3 emits one
    three_notes entry per moment bundling Why1..Why4.  Blank-only 3x3 moments
    are skipped; moments whose non-blank answers are all ignored are skipped.
    Ignore is honoured only when the entry's ignore_text_hash matches the
    current ``why`` text — an edit that cleared the hash restores the entry to
    the queue.

    For CLAMP/CCT, a text is skipped only when *every* copy of it across the
    moment's category entries has an honoured ignore.  If any copy is
    un-ignored the text is sent exactly once.

    Args:
        games: Iterable of game objects (GameData or compatible).
        tags_resolver: Callable that returns ``{path_key: [entry, ...]}`` for
            a game. The resolver is expected to apply any orphan-filtering
            the caller requires (controller: ``get_tags_for_game``; service
            harness: ``ChessLogStorageService.load_resolved_paths``).

    Returns:
        ``(legacy_notes, three_notes, three_ignored_sets)``.

        ``legacy_notes``: 5-tuples ``(idx, game, path_key, preset, why)``
        for CLAMP/CCT, one per emitted entry.  ``game`` is the GameData object
        (identity-keyed; it is NOT a game_number integer).

        ``three_notes``: 8-tuples
        ``(idx, game, path_key, "3x3", why1, why2, why3, why4)``.
        ``game`` is likewise the GameData object.

        ``three_ignored_sets``: parallel to ``three_notes``; each element is
        the set of ``cat`` strings whose Ignore was honoured for that moment.
    """
    legacy_notes: List[Tuple[int, Any, str, str, str]] = []
    three_notes: List[Tuple[int, Any, str, str, str, str, str, str]] = []
    three_ignored_sets: List[FrozenSet[str]] = []

    for game in games:
        tags = tags_resolver(game)
        for path_key, entries in tags.items():
            if not entries:
                continue
            by_preset: Dict[str, list] = {}
            for entry in entries:
                p = entry.get("preset", "")
                by_preset.setdefault(p, []).append(entry)
            for preset, preset_entries in by_preset.items():
                if preset == "3x3":
                    why_map = {e.get("cat", ""): (e.get("why") or "").strip() for e in preset_entries}
                    # Per-entry hash check: honour ignore only when hash matches current text.
                    ignored_cats: Set[str] = set()
                    for e in preset_entries:
                        cat = e.get("cat", "")
                        why = (e.get("why") or "").strip()
                        ign = bool(e.get("ignore_shallow", False))
                        h = e.get("ignore_text_hash")
                        if ign:
                            if h:
                                if why and hashlib.sha256(why.encode("utf-8")).hexdigest() == h:
                                    ignored_cats.add(cat)
                                # hash mismatch → don't ignore (edit cleared it)
                            else:
                                ignored_cats.add(cat)  # legacy: no hash → honour
                    why1 = why_map.get("Why1", "")
                    why2 = why_map.get("Why2", "")
                    why3 = why_map.get("Why3", "")
                    why4 = why_map.get("Why4", "")
                    # Skip moment if all four whys are empty.
                    if not any([why1, why2, why3, why4]):
                        continue
                    # Skip moment if every non-blank answer is ignored.
                    non_blank = {c for c, w in (("Why1", why1), ("Why2", why2), ("Why3", why3), ("Why4", why4)) if w}
                    if non_blank and non_blank.issubset(ignored_cats):
                        continue
                    idx = len(three_notes)
                    three_notes.append((idx, game, path_key, preset, why1, why2, why3, why4))
                    three_ignored_sets.append(frozenset(ignored_cats))
                else:
                    # One entry per distinct non-blank note text, first-seen order.
                    # A text is skipped only when every copy of it has an honoured ignore.
                    why_all_ignored: Dict[str, bool] = {}
                    for entry in preset_entries:
                        why = (entry.get("why") or "").strip()
                        if not why:
                            continue
                        ign = _is_ignore_honoured(entry)
                        if why not in why_all_ignored:
                            why_all_ignored[why] = ign
                        elif not ign:
                            why_all_ignored[why] = False
                    for why, all_ignored in why_all_ignored.items():
                        if not all_ignored:
                            idx = len(legacy_notes)
                            legacy_notes.append((idx, game, path_key, preset, why))

    return legacy_notes, three_notes, three_ignored_sets


# ---------------------------------------------------------------------------
# Public API — CLAMP/CCT
# ---------------------------------------------------------------------------

def classify_notes(
    notes: List[Tuple[int, int, str, str, str]],
    provider: str,
    model: str,
    api_key: str,
    base_url_override: Optional[str],
    config: Optional[dict],
    timeout_seconds: int,
    *,
    _is_retry: bool = False,
) -> ShallowResult:
    """Classify *notes* as SHALLOW or DEEP via the configured AI provider.

    Args:
        notes: List of ``(idx, game, path_key, preset, why)`` tuples where
               ``game`` is the GameData object.  The ``idx`` values must be
               0-based sequential integers matching list positions
               (i.e. ``notes[i][0] == i``).
        provider: ``"anthropic"``, ``"openai"``, or ``"custom"``.
        model: Model ID string.
        api_key: Provider API key.
        base_url_override: Custom endpoint base URL; ``None`` for cloud providers.
        config: Optional config dict forwarded to AIService.
        timeout_seconds: Request timeout.

    Returns:
        A :class:`ShallowResult`.  On API failure ``success`` is ``False`` and
        ``shallow_keys`` is empty.  On a successful call with partial parse
        failures ``success`` is ``True``, ``shallow_keys`` holds the confirmed
        SHALLOW entries, and ``unparsed_indices`` lists the uncovered indices.
        ``vague_keys`` is always empty for CLAMP/CCT.
    """
    thinking = AIService.disable_thinking_for(model)
    notes_text = "\n".join(f"{i}: {why}" for (i, _gn, _pk, _pr, why) in notes)
    classifier_body = (config or {}).get("prompts", {}).get("chess_log", {}).get("classifier")
    if not classifier_body:
        return ShallowResult(
            success=False,
            shallow_keys=frozenset(),
            error="Chess Log prompts are missing from config.json — reinstall or restore the file.",
            usage=None,
            model=model,
            unparsed_indices=tuple(i for i, *_ in notes),
        )
    prompt = classifier_body + notes_text

    token_limit = _classifier_token_limit(len(notes))
    service = AIService(config=config)
    LoggingService.get_instance().info(
        "chess_log classifier: feature=check-logs-clamp, model=%s, thinking=%r, "
        "notes=%d, max_tokens=%d, body_bytes=%d, timeout=%ds%s"
        % (model, thinking, len(notes), token_limit,
           len(prompt.encode("utf-8")), timeout_seconds,
           ", IS_RETRY=True" if _is_retry else "")
    )
    _t0 = time.monotonic()
    result = service.send_message(
        provider=provider,
        model=model,
        api_key=api_key,
        messages=[{"role": "user", "content": prompt}],
        base_url_override=base_url_override,
        timeout_seconds=timeout_seconds,
        thinking=thinking,
        token_limit=token_limit,
    )
    _elapsed = time.monotonic() - _t0
    if result.success:
        _outcome = "ok"
    elif result.error and "timed out" in result.error.lower():
        _outcome = "timeout"
    else:
        _outcome = "error"
    _in_tok = result.usage.input_tokens if result.usage else None
    _out_tok = result.usage.output_tokens if result.usage else None
    _model_note = (f", replied_model={result.model!r}" if result.model != model else "")
    LoggingService.get_instance().info(
        "chess_log classifier done: feature=check-logs-clamp, model=%s, "
        "elapsed=%.1fs, outcome=%s, input_tokens=%s, output_tokens=%s%s"
        % (model, _elapsed, _outcome, _in_tok, _out_tok, _model_note)
    )

    if not result.success:
        return ShallowResult(
            success=False,
            shallow_keys=frozenset(),
            error=result.error or "Classification failed.",
            usage=result.usage,
            model=result.model,
            unparsed_indices=tuple(range(len(notes))),
        )

    parsed = _parse_verdicts(result.text, len(notes))

    shallow_keys: FrozenSet[Tuple[Any, str, str, str]] = frozenset(
        (notes[i][1], notes[i][2], notes[i][3], "")
        for i, verdict in parsed.items()
        if verdict == "SHALLOW"
    )
    unparsed = tuple(i for i in range(len(notes)) if i not in parsed)

    if unparsed:
        all_failed = len(parsed) == 0 and len(notes) > 0
        logger = LoggingService.get_instance()
        log = logger.error if all_failed else logger.debug
        log(
            "chess_log classifier parsed %d of %d notes "
            "(model=%s, stop_reason=%r, max_tokens=%s, "
            "input_tokens=%s, output_tokens=%s, "
            "block_count=%s, block_types=%s, reply_text=%r)"
            % (
                len(parsed), len(notes), result.model,
                result.stop_reason, token_limit,
                result.usage.input_tokens if result.usage else None,
                result.usage.output_tokens if result.usage else None,
                result.content_block_count,
                result.content_block_types,
                result.text[:4000],
            )
        )

    # Retry once for unparsed notes (never on a retry call itself).
    if unparsed and not _is_retry:
        retry_notes = [
            (j,) + notes[orig_i][1:]
            for j, orig_i in enumerate(unparsed)
        ]
        LoggingService.get_instance().info(
            "chess_log classifier retry: model=%s, %d of %d notes unparsed — retrying %d"
            % (model, len(unparsed), len(notes), len(retry_notes))
        )
        retry_result = classify_notes(
            retry_notes, provider, model, api_key, base_url_override,
            config, timeout_seconds, _is_retry=True,
        )
        if retry_result.success:
            shallow_keys = shallow_keys | retry_result.shallow_keys
            still_unparsed = frozenset(retry_result.unparsed_indices)
            unparsed = tuple(unparsed[j] for j in sorted(still_unparsed))

    return ShallowResult(
        success=True,
        shallow_keys=shallow_keys,
        error=None,
        usage=result.usage,
        model=result.model,
        unparsed_indices=unparsed,
    )


# ---------------------------------------------------------------------------
# Public API — 3x3
# ---------------------------------------------------------------------------

def classify_notes_3x3(
    notes: List[Tuple[int, int, str, str, str, str, str, str]],
    provider: str,
    model: str,
    api_key: str,
    base_url_override: Optional[str],
    config: Optional[dict],
    timeout_seconds: int,
    *,
    _is_retry: bool = False,
) -> ShallowResult:
    """Classify 3x3 notes with independent INTENT / LESSON verdicts.

    Args:
        notes: List of ``(idx, game, path_key, preset, why1, why2, why3, why4)``
               tuples where ``game`` is the GameData object.
               Indices must be 0-based sequential.
        ...

    Returns:
        A :class:`ShallowResult` with both ``shallow_keys`` and ``vague_keys``
        populated from the combining rules:

            shallow = (intent != SPECIFIC) and (lesson != REAL)
            vague   = (lesson == FILLER)
    """
    raw_body = (config or {}).get("prompts", {}).get("chess_log", {}).get("classifier_3x3")
    if not raw_body:
        return ShallowResult(
            success=False,
            shallow_keys=frozenset(),
            error="Chess Log 3x3 classifier prompt is missing from config.json — reinstall or restore the file.",
            usage=None,
            model=model,
            unparsed_indices=tuple(i for i, *_ in notes),
        )

    classifier_body = raw_body.format(
        why1_q=THREE_BY_THREE_PROMPTS["Why1"],
        why2_q=THREE_BY_THREE_PROMPTS["Why2"],
        why3_q=THREE_BY_THREE_PROMPTS["Why3"],
        why4_q=THREE_BY_THREE_PROMPTS["Why4"],
    )

    def _fmt_why(text: str) -> str:
        return text.strip() if text and text.strip() else "(blank)"

    note_blocks = []
    for (i, _gn, _pk, _pr, why1, why2, why3, why4) in notes:
        block = (
            f"{i}:\n"
            f"  Why1: {_fmt_why(why1)}\n"
            f"  Why2: {_fmt_why(why2)}\n"
            f"  Why3: {_fmt_why(why3)}\n"
            f"  Why4: {_fmt_why(why4)}"
        )
        note_blocks.append(block)

    prompt = classifier_body + "\n".join(note_blocks)

    thinking = AIService.disable_thinking_for(model)
    token_limit = _classifier_token_limit(len(notes), per_note=90)
    service = AIService(config=config)
    LoggingService.get_instance().info(
        "chess_log 3x3 classifier: feature=check-logs-3x3, model=%s, thinking=%r, "
        "notes=%d, max_tokens=%d, body_bytes=%d, timeout=%ds%s"
        % (model, thinking, len(notes), token_limit,
           len(prompt.encode("utf-8")), timeout_seconds,
           ", IS_RETRY=True" if _is_retry else "")
    )
    _t0_3x3 = time.monotonic()
    result = service.send_message(
        provider=provider,
        model=model,
        api_key=api_key,
        messages=[{"role": "user", "content": prompt}],
        base_url_override=base_url_override,
        timeout_seconds=timeout_seconds,
        thinking=thinking,
        token_limit=token_limit,
    )
    _elapsed_3x3 = time.monotonic() - _t0_3x3
    if result.success:
        _outcome_3x3 = "ok"
    elif result.error and "timed out" in result.error.lower():
        _outcome_3x3 = "timeout"
    else:
        _outcome_3x3 = "error"
    _in_tok_3x3 = result.usage.input_tokens if result.usage else None
    _out_tok_3x3 = result.usage.output_tokens if result.usage else None
    _model_note_3x3 = (f", replied_model={result.model!r}" if result.model != model else "")
    LoggingService.get_instance().info(
        "chess_log 3x3 classifier done: feature=check-logs-3x3, model=%s, "
        "elapsed=%.1fs, outcome=%s, input_tokens=%s, output_tokens=%s%s"
        % (model, _elapsed_3x3, _outcome_3x3, _in_tok_3x3, _out_tok_3x3, _model_note_3x3)
    )

    if not result.success:
        return ShallowResult(
            success=False,
            shallow_keys=frozenset(),
            error=result.error or "3x3 classification failed.",
            usage=result.usage,
            model=result.model,
            unparsed_indices=tuple(range(len(notes))),
        )

    parsed = _parse_3x3_verdicts(result.text, len(notes))

    s_keys = []
    v_keys = []
    for i, (why1, why2, why3, lesson) in parsed.items():
        game, pk = notes[i][1], notes[i][2]
        # Each Why1/Why2/Why3 answer is judged independently: GENERIC → shallow.
        for cat, verdict in (("Why1", why1), ("Why2", why2), ("Why3", why3)):
            if verdict == "GENERIC":
                s_keys.append((game, pk, "3x3", cat))
        # Why4 (Lesson): FILLER → vague lesson.
        if lesson == "FILLER":
            v_keys.append((game, pk, "3x3", "Why4"))
    shallow_keys: FrozenSet[Tuple[Any, str, str, str]] = frozenset(s_keys)
    vague_keys: FrozenSet[Tuple[Any, str, str, str]] = frozenset(v_keys)

    unparsed = tuple(i for i in range(len(notes)) if i not in parsed)

    if unparsed:
        all_failed = len(parsed) == 0 and len(notes) > 0
        logger = LoggingService.get_instance()
        log = logger.error if all_failed else logger.debug
        log(
            "chess_log 3x3 classifier parsed %d of %d notes "
            "(model=%s, stop_reason=%r, max_tokens=%s, "
            "input_tokens=%s, output_tokens=%s, "
            "block_count=%s, block_types=%s, reply_text=%r)"
            % (
                len(parsed), len(notes), result.model,
                result.stop_reason, token_limit,
                result.usage.input_tokens if result.usage else None,
                result.usage.output_tokens if result.usage else None,
                result.content_block_count,
                result.content_block_types,
                result.text[:4000],
            )
        )

    # Retry once for unparsed notes (never on a retry call itself).
    if unparsed and not _is_retry:
        retry_notes = [
            (j,) + notes[orig_i][1:]
            for j, orig_i in enumerate(unparsed)
        ]
        LoggingService.get_instance().info(
            "chess_log 3x3 classifier retry: model=%s, %d of %d notes unparsed — retrying %d"
            % (model, len(unparsed), len(notes), len(retry_notes))
        )
        retry_result = classify_notes_3x3(
            retry_notes, provider, model, api_key, base_url_override,
            config, timeout_seconds, _is_retry=True,
        )
        if retry_result.success:
            shallow_keys = shallow_keys | retry_result.shallow_keys
            vague_keys = vague_keys | retry_result.vague_keys
            still_unparsed = frozenset(retry_result.unparsed_indices)
            unparsed = tuple(unparsed[j] for j in sorted(still_unparsed))

    return ShallowResult(
        success=True,
        shallow_keys=shallow_keys,
        error=None,
        usage=result.usage,
        model=result.model,
        unparsed_indices=unparsed,
        vague_keys=vague_keys,
    )

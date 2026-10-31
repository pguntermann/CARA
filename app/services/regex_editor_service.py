"""Compile, color, and test regular expressions for the shared editor.

Case sensitivity is an input. This service does not decide it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

TOKEN_LITERAL = "literal"
TOKEN_ESCAPE = "escape"
TOKEN_QUANTIFIER = "quantifier"
TOKEN_GROUP = "group"
TOKEN_SET = "set"
TOKEN_RANGE = "range"
TOKEN_ANCHOR = "anchor"
TOKEN_ALTERNATION = "alternation"
TOKEN_ANY = "any"
TOKEN_ERROR = "error"

_QUANT_BODY = re.compile(r"\d+(?:,\d*)?|,\d+")

Span = Tuple[int, int, str]


@dataclass(frozen=True)
class RegexBlock:
    """One insertable building block."""

    id: str
    label: str
    insert: str
    tooltip: str
    select_text: str


@dataclass(frozen=True)
class RegexBlockGroup:
    """A menu category. Categories may contain blocks, nested categories, or both."""

    id: str
    label: str
    blocks: Tuple[RegexBlock, ...] = ()
    groups: Tuple["RegexBlockGroup", ...] = ()


@dataclass(frozen=True)
class RegexExample:
    """One ready-made pattern the editor can load, with text that shows what it matches."""

    id: str
    label: str
    pattern: str
    sample: str = ""
    tooltip: str = ""
    select_text: str = ""


@dataclass(frozen=True)
class RegexEditorValues:
    """Pattern and replacement returned when the editor is accepted."""

    pattern: str
    replacement: str


@dataclass(frozen=True)
class RegexExplainNode:
    """One step of a pattern explanation. ``fields`` fill the configured sentence."""

    kind: str
    token: str
    message_id: str
    fields: Tuple[Tuple[str, str], ...] = ()
    children: Tuple["RegexExplainNode", ...] = ()
    closing_token: str = ""


@dataclass(frozen=True)
class RegexPreview:
    """Live test of a pattern against sample text."""

    valid: bool
    empty: bool
    error: str
    spans: Tuple[Tuple[int, int], ...]
    matches: Tuple[str, ...]
    result: str
    truncated: bool
    match_count: int
    matches_capped: bool


class RegexEditorService:
    """Stateless regular-expression operations used by RegexEditorController."""

    def block_groups(self, config: Dict[str, Any]) -> List[RegexBlockGroup]:
        """Building-block categories from config, in menu order."""
        raw = _section(config).get("block_groups", [])
        if not isinstance(raw, list):
            return []
        return [group for item in raw if (group := self._load_group(item)) is not None]

    def normalize_name(self, name: str) -> str:
        """Trim a saved-regex name. Empty after trimming is not a usable name."""
        return (name or "").strip()

    def blocks(self, config: Dict[str, Any]) -> List[RegexBlock]:
        """Every insertable block, in menu order."""
        found: List[RegexBlock] = []

        def walk(groups: List[RegexBlockGroup]) -> None:
            for group in groups:
                found.extend(group.blocks)
                walk(list(group.groups))

        walk(self.block_groups(config))
        return found

    def examples(self, config: Dict[str, Any]) -> List[RegexExample]:
        """Example patterns from ``ui.dialogs.regex_editor.examples``, in menu order.

        Raises:
            ValueError: If the list is missing or any example is not a usable pattern.
        """
        raw = _section(config).get("examples")
        if not isinstance(raw, list) or not raw:
            raise ValueError(
                "ui.dialogs.regex_editor.examples must be a non-empty list in config.json"
            )
        examples: List[RegexExample] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ValueError(f"ui.dialogs.regex_editor.examples[{index}] must be an object")
            example_id = str(item.get("id", "")).strip()
            label = str(item.get("label", "")).strip()
            pattern = item.get("pattern")
            sample = str(item.get("sample", "") or "")
            tooltip = str(item.get("tooltip", "") or "")
            select_text = str(item.get("select_text", "") or "")
            if not example_id or not label or not isinstance(pattern, str) or pattern == "":
                raise ValueError(
                    f"ui.dialogs.regex_editor.examples[{index}] needs id, label, and pattern"
                )
            if example_id in seen_ids:
                raise ValueError(f"Duplicate regex example id {example_id!r} at index {index}")
            seen_ids.add(example_id)
            if select_text and select_text not in pattern:
                raise ValueError(
                    f"select_text {select_text!r} for example {example_id!r} "
                    "must be a substring of pattern"
                )
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid pattern for example {example_id!r}: {exc}") from exc
            examples.append(
                RegexExample(
                    id=example_id,
                    label=label,
                    pattern=pattern,
                    sample=sample,
                    tooltip=tooltip,
                    select_text=select_text,
                )
            )
        return examples

    def _load_group(self, item: Any) -> Optional[RegexBlockGroup]:
        if not isinstance(item, dict):
            return None
        label = str(item.get("label", "")).strip()
        raw_blocks = item.get("blocks", [])
        raw_groups = item.get("groups", [])
        blocks = tuple(
            block
            for entry in (raw_blocks if isinstance(raw_blocks, list) else [])
            if (block := self._load_block(entry)) is not None
        )
        groups = tuple(
            group
            for entry in (raw_groups if isinstance(raw_groups, list) else [])
            if (group := self._load_group(entry)) is not None
        )
        if not label or (not blocks and not groups):
            return None
        return RegexBlockGroup(id=str(item.get("id", "")), label=label, blocks=blocks, groups=groups)

    def _load_block(self, item: Any) -> Optional[RegexBlock]:
        if not isinstance(item, dict):
            return None
        label = str(item.get("label", "")).strip()
        insert = item.get("insert")
        if not label or not isinstance(insert, str) or insert == "":
            return None
        return RegexBlock(
            id=str(item.get("id", "")),
            label=label,
            insert=insert,
            tooltip=str(item.get("tooltip", "")),
            select_text=str(item.get("select_text", "")),
        )

    def classify(self, pattern: str) -> List[Span]:
        """Token spans for syntax coloring. Adjacent tokens of the same kind are merged.

        Kinds match the explanation cards: anchors, alternation, and ``.`` are
        separate, and a character class splits into the set, its ranges, and
        the characters inside it.
        """
        spans: List[Span] = []
        i = 0
        n = len(pattern)
        in_class = False
        class_first = False
        while i < n:
            ch = pattern[i]
            if in_class:
                if ch == "\\" and i + 1 < n:
                    _add(spans, i, i + 2, TOKEN_ESCAPE)
                    i += 2
                    class_first = False
                    continue
                if ch == "]" and not class_first:
                    _add(spans, i, i + 1, TOKEN_SET)
                    i += 1
                    in_class = False
                    continue
                if ch == "^" and class_first:
                    _add(spans, i, i + 1, TOKEN_SET)
                    class_first = False
                    i += 1
                    continue
                if (
                    i + 2 < n
                    and pattern[i + 1] == "-"
                    and pattern[i + 2] not in "]\\"
                ):
                    _add(spans, i, i + 3, TOKEN_RANGE)
                    i += 3
                    class_first = False
                    continue
                _add(spans, i, i + 1, TOKEN_LITERAL)
                class_first = False
                i += 1
                continue
            if ch == "\\":
                if i + 1 < n:
                    _add(spans, i, i + 2, TOKEN_ESCAPE)
                    i += 2
                else:
                    _add(spans, i, i + 1, TOKEN_ERROR)
                    i += 1
                continue
            if ch == "[":
                _add(spans, i, i + 1, TOKEN_SET)
                i += 1
                in_class = True
                class_first = True
                continue
            if ch == "{":
                end = pattern.find("}", i + 1)
                if end < 0:
                    _add(spans, i, n, TOKEN_ERROR)
                    break
                body = pattern[i + 1 : end]
                kind = TOKEN_QUANTIFIER if _QUANT_BODY.fullmatch(body) else TOKEN_ERROR
                _add(spans, i, end + 1, kind)
                i = end + 1
                continue
            if ch in "()":
                _add(spans, i, i + 1, TOKEN_GROUP)
                i += 1
                continue
            if ch == "?" and i > 0 and pattern[i - 1] == "(":
                _add(spans, i, i + 1, TOKEN_GROUP)
                i += 1
                continue
            if ch in "*+?":
                _add(spans, i, i + 1, TOKEN_QUANTIFIER)
                i += 1
                continue
            if ch in "^$":
                _add(spans, i, i + 1, TOKEN_ANCHOR)
                i += 1
                continue
            if ch == "|":
                _add(spans, i, i + 1, TOKEN_ALTERNATION)
                i += 1
                continue
            if ch == ".":
                _add(spans, i, i + 1, TOKEN_ANY)
                i += 1
                continue
            start = i
            i += 1
            while i < n and pattern[i] not in "\\[]()*+?{.^$|":
                i += 1
            _add(spans, start, i, TOKEN_LITERAL)
        return spans

    def insert_block(
        self,
        pattern: str,
        start: int,
        end: int,
        insert: str,
        select_text: str,
    ) -> Tuple[str, int, int]:
        """Insert a building block, optionally wrapping the current selection.

        Returns the new pattern and the selection range that should follow
        (the placeholder, or the wrapped text).
        """
        n = len(pattern)
        start = max(0, min(start, n))
        end = max(start, min(end, n))
        selected = pattern[start:end]
        placeholder_at = insert.find(select_text) if select_text else -1
        if placeholder_at >= 0 and selected:
            piece = insert[:placeholder_at] + selected + insert[placeholder_at + len(select_text) :]
            sel_start = start + placeholder_at
            sel_end = sel_start + len(selected)
        else:
            piece = insert
            if placeholder_at >= 0:
                sel_start = start + placeholder_at
                sel_end = sel_start + len(select_text)
            else:
                sel_start = start + len(piece)
                sel_end = sel_start
        updated = pattern[:start] + piece + pattern[end:]
        return updated, sel_start, sel_end

    def preview(
        self,
        pattern: str,
        replacement: str,
        sample: str,
        *,
        case_sensitive: bool,
        max_sample_chars: int,
        max_matches: int,
    ) -> RegexPreview:
        """Compile ``pattern`` and test it against the start of ``sample``.

        An empty pattern is not an error from ``re``, but it is not a usable
        expression, so it is reported as empty.
        """
        limit = max(0, int(max_sample_chars))
        truncated = len(sample) > limit
        text = sample[:limit]
        if pattern == "":
            return RegexPreview(
                valid=False,
                empty=True,
                error="",
                spans=(),
                matches=(),
                result="",
                truncated=truncated,
                match_count=0,
                matches_capped=False,
            )
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            return RegexPreview(
                valid=False,
                empty=False,
                error=str(exc),
                spans=(),
                matches=(),
                result="",
                truncated=truncated,
                match_count=0,
                matches_capped=False,
            )
        spans: List[Tuple[int, int]] = []
        matched_texts: List[str] = []
        capped = False
        cap = max(0, int(max_matches))
        for match in compiled.finditer(text):
            if match.start() == match.end():
                continue
            if len(matched_texts) >= cap:
                capped = True
                break
            matched_texts.append(match.group(0))
            spans.extend(_highlight_spans(match))
        matched = tuple(matched_texts)
        try:
            result = compiled.sub(replacement, text)
        except re.error as exc:
            return RegexPreview(
                valid=False,
                empty=False,
                error=str(exc),
                spans=tuple(spans),
                matches=matched,
                result="",
                truncated=truncated,
                match_count=len(matched),
                matches_capped=capped,
            )
        return RegexPreview(
            valid=True,
            empty=False,
            error="",
            spans=tuple(spans),
            matches=matched,
            result=result,
            truncated=truncated,
            match_count=len(matched),
            matches_capped=capped,
        )

    def explain(self, pattern: str) -> List[RegexExplainNode]:
        """Break ``pattern`` into a nested explanation. Empty input explains nothing."""
        if pattern == "":
            return []
        return _ExplainParser(pattern).parse()


def _highlight_spans(match: re.Match) -> List[Tuple[int, int]]:
    """Ranges worth painting. A group that is the whole match adds nothing."""
    full = (match.start(), match.end())
    inner: List[Tuple[int, int]] = []
    seen = set()
    for index in range(1, (match.lastindex or 0) + 1):
        start, end = match.span(index)
        span = (start, end)
        if start < 0 or start == end or span == full or span in seen:
            continue
        seen.add(span)
        inner.append(span)
    return inner or [full]


def _section(config: Dict[str, Any]) -> Dict[str, Any]:
    dialogs = config.get("ui", {}).get("dialogs", {})
    section = dialogs.get("regex_editor", {})
    return section if isinstance(section, dict) else {}


_ESCAPE_MESSAGES = {
    "d": "digit",
    "D": "not_digit",
    "w": "word",
    "W": "not_word",
    "s": "whitespace",
    "S": "not_whitespace",
    "A": "start_string",
    "Z": "end_string",
    "n": "newline",
    "r": "carriage_return",
    "t": "tab",
    "f": "form_feed",
    "v": "vertical_tab",
    "a": "bell",
}
_CLASS_BAD_ESCAPES = set("ABZ")
_QUANT_RE = re.compile(r"\{(\d+(?:,\d*)?|,\d+)\}")
_ATOM_BREAK = set("\\[]()|.^$*+?{")


class _ExplainParser:
    """Recursive reading of a Python ``re`` pattern into explanation nodes."""

    def __init__(self, pattern: str) -> None:
        self.s = pattern
        self.n = len(pattern)
        self.i = 0
        self.groups = 0

    def parse(self) -> List[RegexExplainNode]:
        return self._sequence(stop_on_paren=False)

    def _sequence(self, *, stop_on_paren: bool) -> List[RegexExplainNode]:
        nodes: List[RegexExplainNode] = []
        while self.i < self.n:
            ch = self.s[self.i]
            if stop_on_paren and ch == ")":
                break
            if ch == "|":
                self.i += 1
                nodes.append(RegexExplainNode("alternation", "|", "alternation"))
                continue
            if ch == ")":
                self.i += 1
                nodes.append(RegexExplainNode("error", ")", "unmatched"))
                continue
            atom = self._atom()
            if atom is not None:
                nodes.append(atom)
            quantifier = self._quantifier()
            if quantifier is not None:
                nodes.append(quantifier)
            elif atom is None:
                self.i += 1
                nodes.append(RegexExplainNode("error", ch, "unmatched", (("text", ch),)))
        return nodes

    def _atom(self) -> Optional[RegexExplainNode]:
        if self.i >= self.n:
            return None
        ch = self.s[self.i]
        if ch == "\\":
            return self._escape(in_class=False)
        if ch == "[":
            return self._char_class()
        if ch == "(":
            return self._group()
        if ch == ".":
            self.i += 1
            return RegexExplainNode("any", ".", "any")
        if ch == "^":
            self.i += 1
            return RegexExplainNode("anchor", "^", "start_anchor")
        if ch == "$":
            self.i += 1
            return RegexExplainNode("anchor", "$", "end_anchor")
        if ch in "*+?{)|":
            return None
        start = self.i
        self.i += 1
        while self.i < self.n and self.s[self.i] not in _ATOM_BREAK:
            self.i += 1
        text = self.s[start:self.i]
        return RegexExplainNode(
            "literal",
            text,
            "literal",
            (("text", text), ("case_matters", _case_flag(text))),
        )

    def _quantifier(self) -> Optional[RegexExplainNode]:
        if self.i >= self.n:
            return None
        ch = self.s[self.i]
        fields: List[Tuple[str, str]]
        if ch in "*+?":
            token = ch
            self.i += 1
            message = {
                "*": "quantifier_zero_or_more",
                "+": "quantifier_one_or_more",
                "?": "quantifier_zero_or_one",
            }[ch]
            fields = []
        elif ch == "{":
            match = _QUANT_RE.match(self.s, self.i)
            if match is None:
                return None
            body = match.group(1)
            token = match.group(0)
            self.i = match.end()
            if "," not in body:
                message = "quantifier_exact"
                fields = [("n", body)]
            elif body.startswith(","):
                message = "quantifier_at_most"
                fields = [("m", body[1:])]
            elif body.endswith(","):
                message = "quantifier_at_least"
                fields = [("n", body[:-1])]
            else:
                low, high = body.split(",", 1)
                message = "quantifier_between"
                fields = [("n", low), ("m", high)]
        else:
            return None
        lazy = "0"
        if self.i < self.n and self.s[self.i] == "?":
            token += "?"
            self.i += 1
            lazy = "1"
        fields.append(("lazy", lazy))
        return RegexExplainNode("quantifier", token, message, tuple(fields))

    def _group(self) -> RegexExplainNode:
        self.i += 1  # (
        if self.i < self.n and self.s[self.i] == "?":
            return self._extended_group()
        self.groups += 1
        number = str(self.groups)
        return self._wrap_group("(", "capturing_group", (("number", number),))

    def _extended_group(self) -> RegexExplainNode:
        rest = self.s[self.i:]
        if rest.startswith("?:"):
            self.i += 2
            return self._wrap_group("(?:", "noncapturing_group", ())
        if rest.startswith("?="):
            self.i += 2
            return self._wrap_group("(?=", "positive_lookahead", ())
        if rest.startswith("?!"):
            self.i += 2
            return self._wrap_group("(?!", "negative_lookahead", ())
        if rest.startswith("?<="):
            self.i += 3
            return self._wrap_group("(?<=", "positive_lookbehind", ())
        if rest.startswith("?<!"):
            self.i += 3
            return self._wrap_group("(?<!", "negative_lookbehind", ())
        if rest.startswith("?P<"):
            return self._named_group()
        if rest.startswith("?P="):
            return self._named_backreference()
        if rest.startswith("?#"):
            return self._comment()
        return self._flags_group()

    def _named_group(self) -> RegexExplainNode:
        self.i += 3  # ?P<
        start = self.i
        while self.i < self.n and self.s[self.i] != ">":
            self.i += 1
        name = self.s[start:self.i]
        if self.i < self.n and self.s[self.i] == ">":
            self.i += 1
        self.groups += 1
        return self._wrap_group(
            f"(?P<{name}>",
            "named_group",
            (("name", name), ("number", str(self.groups))),
        )

    def _named_backreference(self) -> RegexExplainNode:
        self.i += 3  # ?P=
        start = self.i
        while self.i < self.n and self.s[self.i] != ")":
            self.i += 1
        name = self.s[start:self.i]
        if self.i < self.n and self.s[self.i] == ")":
            self.i += 1
        return RegexExplainNode(
            "escape",
            f"(?P={name})",
            "named_backreference",
            (("name", name),),
        )

    def _comment(self) -> RegexExplainNode:
        self.i += 2  # ?#
        start = self.i
        while self.i < self.n and self.s[self.i] != ")":
            self.i += 1
        text = self.s[start:self.i]
        if self.i < self.n and self.s[self.i] == ")":
            self.i += 1
        return RegexExplainNode("literal", f"(?#{text})", "comment", (("text", text),))

    def _flags_group(self) -> RegexExplainNode:
        start = self.i + 1  # after ?
        j = start
        while j < self.n and self.s[j] in "aiLmsux-":
            j += 1
        flags = self.s[start:j]
        if j < self.n and self.s[j] == ":":
            self.i = j + 1
            return self._wrap_group(f"(?{flags}:", "flags_group", (("flags", flags),))
        if j < self.n and self.s[j] == ")":
            self.i = j + 1
            return RegexExplainNode("literal", f"(?{flags})", "flags", (("flags", flags),))
        self.i += 1
        return RegexExplainNode("error", "?", "unmatched", (("text", "?"),))

    def _wrap_group(
        self,
        token: str,
        message_id: str,
        fields: Tuple[Tuple[str, str], ...],
    ) -> RegexExplainNode:
        children = self._sequence(stop_on_paren=True)
        closing = ""
        if self.i < self.n and self.s[self.i] == ")":
            self.i += 1
            closing = ")"
        return RegexExplainNode("group", token, message_id, fields, tuple(children), closing)

    def _char_class(self) -> RegexExplainNode:
        self.i += 1  # [
        negated = self.i < self.n and self.s[self.i] == "^"
        if negated:
            self.i += 1
        children: List[RegexExplainNode] = []
        first = True
        closed = False
        while self.i < self.n:
            if self.s[self.i] == "]" and not first:
                self.i += 1
                closed = True
                break
            first = False
            children.append(self._class_item())
        return RegexExplainNode(
            "set",
            "[^" if negated else "[",
            "negated_set" if negated else "character_set",
            (),
            tuple(children),
            "]" if closed else "",
        )

    def _class_item(self) -> RegexExplainNode:
        if self.s[self.i] == "\\":
            return self._escape(in_class=True)
        ch = self.s[self.i]
        self.i += 1
        if (
            self.i + 1 < self.n
            and self.s[self.i] == "-"
            and self.s[self.i + 1] not in "]\\"
        ):
            self.i += 1
            end = self.s[self.i]
            self.i += 1
            return RegexExplainNode(
                "range",
                f"{ch}-{end}",
                "range",
                (
                    ("start", ch),
                    ("end", end),
                    ("start_code", str(ord(ch))),
                    ("end_code", str(ord(end))),
                    ("case_matters", _case_flag(ch + end)),
                ),
            )
        return RegexExplainNode(
            "literal",
            ch,
            "literal",
            (("text", ch), ("case_matters", _case_flag(ch))),
        )

    def _escape(self, *, in_class: bool) -> RegexExplainNode:
        self.i += 1
        if self.i >= self.n:
            return RegexExplainNode("error", "\\", "unclosed")
        ch = self.s[self.i]
        self.i += 1
        token = "\\" + ch
        if ch == "b":
            message = "backspace" if in_class else "word_boundary"
            return RegexExplainNode("escape", token, message)
        if ch == "B" and not in_class:
            return RegexExplainNode("escape", token, "not_word_boundary")
        if in_class and ch in _CLASS_BAD_ESCAPES:
            return RegexExplainNode("error", token, "bad_escape", (("text", token),))
        if ch.isdigit() and not in_class:
            while self.i < self.n and self.s[self.i].isdigit():
                token += self.s[self.i]
                self.i += 1
            return RegexExplainNode("escape", token, "backreference", (("number", token[1:]),))
        message = _ESCAPE_MESSAGES.get(ch)
        if message is not None:
            return RegexExplainNode("escape", token, message)
        return RegexExplainNode(
            "escape",
            token,
            "escaped_literal",
            (("text", ch), ("case_matters", _case_flag(ch))),
        )


def _case_flag(text: str) -> str:
    return "1" if any(ch.isalpha() for ch in text) else "0"


def _add(spans: List[Span], start: int, end: int, kind: str) -> None:
    if spans and spans[-1][2] == kind and spans[-1][1] == start:
        prev_start, _, prev_kind = spans[-1]
        spans[-1] = (prev_start, end, prev_kind)
        return
    spans.append((start, end, kind))

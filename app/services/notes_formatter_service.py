"""Service for formatting notes content for display.

This service is UI-independent and can be tested in isolation.

Currently it focuses on move-aware formatting:
- detects SAN-like move notation in free-form notes
- renders notes as HTML where recognized move tokens are either:
  - clickable links (if the move exists in the current game's notation map), or
  - bold text (if the token looks like a move but isn't part of the current game)

This module is intentionally named as a general formatter because the Notes view
will be extended with additional formatting capabilities beyond move linking.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from app.utils.markdown_to_html import markdown_notes_to_html


class NotesFormatterService:
    """Stateless service for converting notes plain text to formatted HTML."""

    @staticmethod
    def plain_to_html_with_move_links(
        plain: str,
        notation_to_ply: Dict[str, int],
        link_style: str,
        bold_style: str,
    ) -> str:
        if not plain:
            return ""

        # SAN-aware matcher (intentionally not a full PGN parser):
        # - prevents false positives like "h1. The" → "1. The"
        # - prevents "5.7" being treated as "5. 7"
        # - supports paired notation "1. e4 e5"
        file_ = r"[a-h]"
        rank_ = r"[1-8]"
        square = rf"{file_}{rank_}"
        check = r"[+#]?"
        promo = r"(?:=[QRBN])?"
        castling = rf"O-O(?:-O)?{check}"
        pawn_san = rf"(?:{file_}x)?{square}{promo}{check}"
        piece_san = rf"[KQRBN](?:{square}|{file_}|{rank_})?x?{square}{promo}{check}"
        san = rf"(?:{castling}|{piece_san}|{pawn_san})"

        boundary = r"(?<![A-Za-z0-9])"
        # Ensure we don't consume trailing punctuation into the move token.
        # Include "!" and "?" as valid delimiters so patterns like "1. e3!" still match,
        # while the "!" remains unformatted.
        token_end = r"(?=[\s,\.;:)\!\?]|$)"

        paired_pattern = re.compile(
            rf"{boundary}(?P<num>\d+)\.\s*(?P<w>{san}){token_end}"
            rf"(?:\s+(?P<b>{san}){token_end})?"
        )
        black_pattern = re.compile(
            rf"{boundary}(?P<num>\d+)\.\.\.\s*(?P<b>{san}){token_end}"
        )

        # tokens are (start, end, display_text, lookup_text)
        tokens: List[Tuple[int, int, str, str]] = []

        def _trim_trailing_punct(s: str) -> str:
            # Remove common trailing punctuation that may cling to tokens in natural language.
            # We intentionally do NOT keep SAN suffixes like "!" / "?" for highlighting.
            return s.rstrip(",.;:)!?")

        # 1) Paired or single white move: "1. e4" or "1. e4 e5"
        for m in paired_pattern.finditer(plain):
            num = m.group("num")

            w_start = m.start("num")
            w_end = m.end("w")
            w_text_raw = plain[w_start:w_end]
            w_text = _trim_trailing_punct(w_text_raw)
            w_end = w_start + len(w_text)
            tokens.append((w_start, w_end, w_text, w_text))

            b_san = m.group("b")
            if b_san:
                b_start = m.start("b")
                b_end = m.end("b")
                b_display_raw = plain[b_start:b_end]
                b_display = _trim_trailing_punct(b_display_raw)
                b_end = b_start + len(b_display)
                # Normalize paired black SAN into the app's notation form for lookup/linking: "1... e5"
                b_lookup = f"{num}... {b_display.strip()}"
                tokens.append((b_start, b_end, b_display, b_lookup))

        # 2) Explicit black move notation: "13... Rb7"
        for m in black_pattern.finditer(plain):
            b_start = m.start("num")
            b_end = m.end("b")
            b_text_raw = plain[b_start:b_end]
            b_text = _trim_trailing_punct(b_text_raw)
            b_end = b_start + len(b_text)
            tokens.append((b_start, b_end, b_text, b_text))

        # Sort tokens so we can stream-build HTML. Drop overlaps (prefer earlier/longer tokens).
        if tokens:
            tokens.sort(key=lambda t: (t[0], -(t[1] - t[0])))
            non_overlapping: List[Tuple[int, int, str, str]] = []
            last_end = -1
            for start, end, display_text, lookup_text in tokens:
                if start < last_end:
                    continue
                non_overlapping.append((start, end, display_text, lookup_text))
                last_end = end
            tokens = non_overlapping

        # Protect move tokens from markdown parsing by replacing them in the plain text
        # with unique placeholders, formatting the remaining text with inline markdown,
        # and finally substituting the protected placeholders with the move HTML.
        #
        # This keeps move-linking as priority while still letting the rest use markdown.
        # Placeholder must not contain markdown delimiter characters like '_' or '*' to
        # avoid being transformed by inline markdown parsing.
        placeholder_prefix = "@@CARA-MOVE-"
        placeholder_suffix = "@@"

        placeholder_to_html: dict[str, str] = {}
        protected_parts: List[str] = []
        i = 0
        for token_idx, (start, end, display_text, lookup_text) in enumerate(tokens):
            if start > i:
                protected_parts.append(plain[i:start])

            placeholder = f"{placeholder_prefix}{token_idx}{placeholder_suffix}"

            safe_display = html.escape(display_text)
            lookup_clean = lookup_text.rstrip(".,;:!?)")
            in_game = (
                lookup_clean in notation_to_ply
                or (" " in lookup_clean and lookup_clean.replace(" ", "", 1) in notation_to_ply)
            )

            if in_game:
                safe_href = html.escape(lookup_text)
                token_html = (
                    f'<a href="move:{safe_href}" style="{link_style}">{safe_display}</a>'
                )
            else:
                token_html = f'<span style="{bold_style}">{safe_display}</span>'

            placeholder_to_html[placeholder] = token_html
            protected_parts.append(placeholder)
            i = end

        if i < len(plain):
            protected_parts.append(plain[i:])

        protected_plain = "".join(protected_parts)

        # Render remaining text with a Notes-optimized markdown renderer.
        # This preserves user typing/whitespace better than the full markdown renderer,
        # avoiding cursor/space glitches while still supporting headings + inline markdown.
        rendered_html = markdown_notes_to_html(protected_plain)

        # Substitute placeholders with protected move HTML.
        for placeholder, token_html in placeholder_to_html.items():
            rendered_html = rendered_html.replace(placeholder, token_html)

        return rendered_html

    @dataclass(frozen=True)
    class FormatSpan:
        """A formatting instruction for a Notes QTextEdit document.

        Ranges are in plain-text character indices (start inclusive, end exclusive).
        """

        start: int
        end: int
        kind: str
        anchor_href: Optional[str] = None
        font_point_size: Optional[int] = None

    @staticmethod
    def get_notes_format_spans(
        plain: str,
        notation_to_ply: Dict[str, int],
        *,
        hide_markdown_markers: bool = True,
    ) -> List["NotesFormatterService.FormatSpan"]:
        """Detect spans for in-place formatting (no HTML rendering).

        Currently supports:
        - headings: `# Heading` at start of line (marker is hidden, content bold + slightly larger)
        - bold: `**text**` and `__text__`
        - inline code: `` `code` ``
        - strikethrough: `~~text~~`
        - blockquote: `> text` at start of line
        - move tokens: formats/anchors like the Notes HTML renderer
        """
        if not plain:
            return []

        spans: List[NotesFormatterService.FormatSpan] = []

        def _add_hidden(start: int, end: int) -> None:
            if hide_markdown_markers and start < end:
                spans.append(NotesFormatterService.FormatSpan(start=start, end=end, kind="hidden"))

        def _add_bold(start: int, end: int, point_size: Optional[int] = None) -> None:
            if start < end:
                spans.append(
                    NotesFormatterService.FormatSpan(
                        start=start, end=end, kind="bold", font_point_size=point_size
                    )
                )

        def _add_italic(start: int, end: int) -> None:
            if start < end:
                spans.append(NotesFormatterService.FormatSpan(start=start, end=end, kind="italic"))

        def _add_blockquote(start: int, end: int) -> None:
            if start < end:
                spans.append(NotesFormatterService.FormatSpan(start=start, end=end, kind="blockquote"))

        def _add_bold_italic(start: int, end: int) -> None:
            if start < end:
                spans.append(
                    NotesFormatterService.FormatSpan(start=start, end=end, kind="bold_italic")
                )

        def _add_inline_code(start: int, end: int) -> None:
            if start < end:
                spans.append(NotesFormatterService.FormatSpan(start=start, end=end, kind="inline_code"))

        def _add_strike(start: int, end: int) -> None:
            if start < end:
                spans.append(NotesFormatterService.FormatSpan(start=start, end=end, kind="strike"))

        # 1) Markdown: headings + bold markers (line-based, non-crossing newline)
        pos = 0
        for raw_line in plain.splitlines(keepends=True):
            # Work with content without line ending for regex purposes
            line_no_ending = raw_line.rstrip("\r\n")

            # Blockquote: '> text' at line start.
            # We keep it line-based so it behaves predictably with cursor/selection.
            blockq_match = re.match(r"^(?P<prefix>>[ \t]+)(?P<text>.*)$", line_no_ending)
            if blockq_match:
                prefix_start = pos + blockq_match.start("prefix")
                prefix_end = pos + blockq_match.end("prefix")
                text_start = pos + blockq_match.start("text")
                text_end = pos + len(line_no_ending)
                _add_hidden(prefix_start, prefix_end)
                _add_blockquote(text_start, text_end)

            line_match = re.match(r"^(?P<hashes>#{1,6})(?P<ws>\s+)(?P<text>.*)$", line_no_ending)
            if line_match:
                hashes_start = pos + line_match.start("hashes")
                ws_end = pos + line_match.end("hashes") + len(line_match.group("ws"))
                text_start = pos + line_match.start("text")
                text_end = pos + len(line_no_ending)

                _add_hidden(hashes_start, ws_end)
                # Make headings visually stronger but keep size reasonable.
                heading_level = len(line_match.group("hashes"))
                _add_bold(text_start, text_end, point_size=12 + heading_level)

            # Inline code: `code` (single-line).
            for m in re.finditer(r"(?<!`)`(?P<content>[^\n`]+?)`(?!`)", line_no_ending):
                marker_start = pos + m.start(0)
                marker_end = pos + m.end(0)
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                _add_hidden(marker_start, marker_start + 1)
                _add_hidden(marker_end - 1, marker_end)
                _add_inline_code(content_start, content_end)

            # Strikethrough: ~~text~~ (single-line).
            for m in re.finditer(r"(?<!~)~~(?P<content>[^\n~]+?)~~(?!~)", line_no_ending):
                marker_start = pos + m.start(0)
                marker_end = pos + m.end(0)
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                _add_hidden(marker_start, marker_start + 2)
                _add_hidden(marker_end - 2, marker_end)
                _add_strike(content_start, content_end)

            # Bold: **text**
            # Keep it within the line (no newline in match).
            # Avoid matching inside ***bold+italic*** by ensuring markers aren't adjacent to '*'.
            for m in re.finditer(
                r"(?<!\*)\*\*(?!\*)(?P<content>[^\n]+?)\*\*(?!\*)",
                line_no_ending,
            ):
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                # Hide the opening/closing markers
                _add_hidden(pos + m.start(0), pos + m.start(0) + 2)
                _add_hidden(pos + m.end(0) - 2, pos + m.end(0))
                _add_bold(content_start, content_end)

            # Bold: __text__
            # Avoid matching inside ___bold+italic___ by ensuring markers aren't adjacent to '_'.
            for m in re.finditer(
                r"(?<!_)__(?!_)(?P<content>[^\n]+?)__(?!_)",
                line_no_ending,
            ):
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                _add_hidden(pos + m.start(0), pos + m.start(0) + 2)
                _add_hidden(pos + m.end(0) - 2, pos + m.end(0))
                _add_bold(content_start, content_end)

            # Bold + italic: ***text*** (hide markers, apply both)
            for m in re.finditer(
                r"(?<!\*)\*\*\*(?!\*)(?P<content>[^\n*]+?)\*\*\*(?!\*)",
                line_no_ending,
            ):
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                _add_hidden(pos + m.start(0), pos + m.start(0) + 3)
                _add_hidden(pos + m.end(0) - 3, pos + m.end(0))
                _add_bold_italic(content_start, content_end)

            # Bold + italic: ___text___ (hide markers, apply both)
            for m in re.finditer(
                r"(?<!_)___(?!_)(?P<content>[^\n_]+?)___(?!_)",
                line_no_ending,
            ):
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                _add_hidden(pos + m.start(0), pos + m.start(0) + 3)
                _add_hidden(pos + m.end(0) - 3, pos + m.end(0))
                _add_bold_italic(content_start, content_end)

            # Italic: *text* (but not **bold**)
            # Opening/closing single '*' markers must not be adjacent to another '*'.
            for m in re.finditer(r"(?<!\*)\*(?!\*)(?P<content>[^\n*]+?)\*(?!\*)", line_no_ending):
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                marker_start = pos + m.start(0)
                marker_end = pos + m.end(0)
                # opening '*' and closing '*'
                _add_hidden(marker_start, marker_start + 1)
                _add_hidden(marker_end - 1, marker_end)
                _add_italic(content_start, content_end)

            # Italic: _text_ (but not __bold__)
            for m in re.finditer(r"(?<!_)_(?!_)(?P<content>[^\n_]+?)_(?!_)", line_no_ending):
                content_start = pos + m.start("content")
                content_end = pos + m.end("content")
                marker_start = pos + m.start(0)
                marker_end = pos + m.end(0)
                _add_hidden(marker_start, marker_start + 1)
                _add_hidden(marker_end - 1, marker_end)
                _add_italic(content_start, content_end)

            pos += len(raw_line)

        # 2) Move tokens (highest priority): preserve prior detection behavior
        # The regex below is derived from the HTML renderer logic to avoid regressions.
        file_ = r"[a-h]"
        rank_ = r"[1-8]"
        square = rf"{file_}{rank_}"
        check = r"[+#]?"
        promo = r"(?:=[QRBN])?"
        castling = rf"O-O(?:-O)?{check}"
        pawn_san = rf"(?:{file_}x)?{square}{promo}{check}"
        piece_san = rf"[KQRBN](?:{square}|{file_}|{rank_})?x?{square}{promo}{check}"
        san = rf"(?:{castling}|{piece_san}|{pawn_san})"

        boundary = r"(?<![A-Za-z0-9])"
        token_end = r"(?=[\s,\.;:)\!\?]|$)"

        paired_pattern = re.compile(
            rf"{boundary}(?P<num>\d+)\.\s*(?P<w>{san}){token_end}(?:\s+(?P<b>{san}){token_end})?"
        )
        black_pattern = re.compile(rf"{boundary}(?P<num>\d+)\.\.\.\s*(?P<b>{san}){token_end}")

        def _trim_trailing_punct(s: str) -> str:
            return s.rstrip(",.;:)!?")

        tokens: List[Tuple[int, int, str, str]] = []
        for m in paired_pattern.finditer(plain):
            num = m.group("num")
            w_start = m.start("num")
            w_end = m.end("w")
            w_text_raw = plain[w_start:w_end]
            w_text = _trim_trailing_punct(w_text_raw)
            w_end = w_start + len(w_text)
            tokens.append((w_start, w_end, w_text, w_text))

            b_san = m.group("b")
            if b_san:
                b_start = m.start("b")
                b_end = m.end("b")
                b_display_raw = plain[b_start:b_end]
                b_display = _trim_trailing_punct(b_display_raw)
                b_end = b_start + len(b_display)
                b_lookup = f"{num}... {b_display.strip()}"
                tokens.append((b_start, b_end, b_display, b_lookup))

        for m in black_pattern.finditer(plain):
            b_start = m.start("num")
            b_end = m.end("b")
            b_text_raw = plain[b_start:b_end]
            b_text = _trim_trailing_punct(b_text_raw)
            b_end = b_start + len(b_text)
            tokens.append((b_start, b_end, b_text, b_text))

        if tokens:
            tokens.sort(key=lambda t: (t[0], -(t[1] - t[0])))
            non_overlapping: List[Tuple[int, int, str, str]] = []
            last_end = -1
            for start, end, display_text, lookup_text in tokens:
                if start < last_end:
                    continue
                non_overlapping.append((start, end, display_text, lookup_text))
                last_end = end
            tokens = non_overlapping

        for start, end, display_text, lookup_text in tokens:
            lookup_clean = lookup_text.rstrip(".,;:!?)")
            in_game = (
                lookup_clean in notation_to_ply
                or (" " in lookup_clean and lookup_clean.replace(" ", "", 1) in notation_to_ply)
            )
            if in_game:
                spans.append(
                    NotesFormatterService.FormatSpan(
                        start=start,
                        end=end,
                        kind="move_link",
                        anchor_href=f"move:{lookup_text}",
                        font_point_size=None,
                    )
                )
            else:
                spans.append(
                    NotesFormatterService.FormatSpan(
                        start=start,
                        end=end,
                        kind="move_bold",
                        font_point_size=None,
                    )
                )

        return spans


    @staticmethod
    def selection_intersects_heading_line(plain: str, start: int, end: int) -> bool:
        """Return True if the selection intersects any markdown heading line.

        A heading line is defined as: `#{1,6}<whitespace>...` at an exact line start.
        """
        if not plain or end <= start:
            return False
        i = plain.rfind("\n", 0, start) + 1
        while i < len(plain) and i < end:
            line_start = i
            line_end = plain.find("\n", line_start)
            if line_end == -1:
                line_end = len(plain)
            if line_start < end and line_end > start:
                if NotesFormatterService._get_heading_prefix_len_at_line_start(plain, line_start) > 0:
                    return True
            i = line_end + 1
            if line_end >= len(plain):
                break
        return False

    @staticmethod
    def _get_heading_prefix_len_at_line_start(plain: str, line_start: int) -> int:
        """Return prefix length for `#{1,6} <text>` at an exact line start."""
        if line_start < 0 or line_start >= len(plain):
            return 0
        m = re.match(r"^(?P<hashes>#{1,6})(?P<ws>\s+)", plain[line_start:])
        if not m:
            return 0
        return m.end()

    @staticmethod
    def _get_blockquote_prefix_len_at_line_start(plain: str, line_start: int) -> int:
        """Return prefix length for `> ...` at an exact line start."""
        if line_start < 0 or line_start >= len(plain):
            return 0
        # Accept:
        # - `> ` (with whitespace)
        # - `>` (no whitespace)
        if plain.startswith(">", line_start):
            j = line_start + 1
            while j < len(plain) and plain[j] in (" ", "\t"):
                j += 1
            return j - line_start
        return 0

    @staticmethod
    def apply_toolbar_action(
        kind: str,
        plain: str,
        start: int,
        end: int,
    ) -> Tuple[str, int, int]:
        """Apply the toolbar action to the plain text selection.

        Returns: (new_plain, new_selection_start, new_selection_end)
        """
        if start < 0 or end < 0 or start == end:
            return plain, start, end
        if end < start:
            start, end = end, start

        # Prevent bold/italic inside headings (avoid conflicting markdown syntax).
        if kind in ("bold", "italic") and NotesFormatterService.selection_intersects_heading_line(plain, start, end):
            return plain, start, end

        if kind == "bold":
            return NotesFormatterService._toggle_or_wrap_inline_marker(plain, start, end, "**", "**")
        if kind == "italic":
            return NotesFormatterService._toggle_or_wrap_inline_marker(plain, start, end, "*", "*")
        if kind == "inline_code":
            return NotesFormatterService._toggle_or_wrap_inline_marker(plain, start, end, "`", "`")
        if kind == "strike":
            return NotesFormatterService._toggle_or_wrap_inline_marker(plain, start, end, "~~", "~~")
        if kind in ("h1", "h2", "h3"):
            level = {"h1": 1, "h2": 2, "h3": 3}[kind]
            return NotesFormatterService._apply_heading_prefix_to_selection(plain, start, end, level)
        if kind == "blockquote":
            return NotesFormatterService._apply_blockquote_prefix_to_selection(plain, start, end)

        return plain, start, end

    @staticmethod
    def _toggle_or_wrap_inline_marker(
        plain: str,
        start: int,
        end: int,
        prefix: str,
        suffix: str,
    ) -> Tuple[str, int, int]:
        selected = plain[start:end]
        if not selected:
            return plain, start, end

        p_len = len(prefix)
        s_len = len(suffix)

        def set_around(new_plain: str, new_start: int, new_end: int) -> Tuple[str, int, int]:
            return new_plain, new_start, new_end

        # 1) Toggle off when markers surround the selection.
        if start >= p_len and end + s_len <= len(plain) and plain[start - p_len : start] == prefix and plain[end : end + s_len] == suffix:
            # Special constraint for italic toggling inside bold (**...**).
            # When prefix/suffix is '*', ensure we are not inside '**...**'.
            if prefix == "*" and suffix == "*":
                # If we are inside bold+italic (`***text***`), toggling italic off should
                # convert to bold-only: `***bad***` -> `**bad**`.
                if (
                    start >= 3
                    and end + 3 <= len(plain)
                    and plain[start - 3 : start] == "***"
                    and plain[end : end + 3] == "***"
                ):
                    opening_two = plain[start - 2 : start]  # '**'
                    closing_two = plain[end : end + 2]  # '**'
                    new_plain = plain[: start - 3] + opening_two + selected + closing_two + plain[end + 3 :]
                    new_start = start - 1
                    new_end = new_start + len(selected)
                    return set_around(new_plain, new_start, new_end)

                # Otherwise, before the opening '*' must not be another '*'
                # (avoid toggling off inside `**...**`).
                before_ok = start - 2 < 0 or plain[start - 2] != "*"
                # After the closing '*' must not be another '*'.
                after_ok = end + 1 >= len(plain) or plain[end + 1] != "*"
                if before_ok and after_ok:
                    new_plain = plain[: start - 1] + selected + plain[end + 1 :]
                    new_start = start - 1
                    new_end = new_start + len(selected)
                    return set_around(new_plain, new_start, new_end)
                # Treat as normal wrap rather than toggle-off.
            else:
                new_plain = plain[: start - p_len] + selected + plain[end + s_len :]
                new_start = start - p_len
                new_end = new_start + len(selected)
                return set_around(new_plain, new_start, new_end)

        # 2) Toggle off when selection itself includes the markers.
        if selected.startswith(prefix) and selected.endswith(suffix) and len(selected) >= p_len + s_len:
            inner = selected[p_len : len(selected) - s_len]
            new_plain = plain[:start] + inner + plain[end:]
            new_start = start
            new_end = start + len(inner)
            return set_around(new_plain, new_start, new_end)

        # 3) Default wrap: insert markers around selection.
        new_plain = plain[:start] + prefix + selected + suffix + plain[end:]
        new_start = start + p_len
        new_end = new_start + len(selected)
        return set_around(new_plain, new_start, new_end)

    @staticmethod
    def _apply_heading_prefix_to_selection(plain: str, start: int, end: int, level: int) -> Tuple[str, int, int]:
        desired_prefix = ("#" * level) + " "
        desired_prefix_len = len(desired_prefix)

        affected_lines: List[Tuple[int, int, int]] = []  # (line_start, line_end, old_prefix_len)
        i = plain.rfind("\n", 0, start) + 1
        while i < len(plain) and i < end:
            line_start = i
            line_end = plain.find("\n", line_start)
            if line_end == -1:
                line_end = len(plain)
            if line_start < end and line_end > start:
                old_prefix_len = NotesFormatterService._get_heading_prefix_len_at_line_start(plain, line_start)
                affected_lines.append((line_start, line_end, old_prefix_len))
            i = line_end + 1
            if line_end >= len(plain):
                break

        if not affected_lines:
            return plain, start, end

        new_parts: List[str] = []
        last = 0
        for line_start, line_end, old_prefix_len in affected_lines:
            new_parts.append(plain[last:line_start])
            new_parts.append(desired_prefix)
            new_parts.append(plain[line_start + old_prefix_len : line_end])
            last = line_end
        new_plain = "".join(new_parts) + plain[last:]

        def map_index(idx: int) -> int:
            cumulative_delta = 0
            for ls, _le, old_len in affected_lines:
                delta = desired_prefix_len - old_len
                if idx < ls:
                    break
                if idx >= ls + old_len:
                    cumulative_delta += delta
                    continue
                # idx is inside the old prefix region
                offset = idx - ls
                new_offset = min(max(offset, 0), desired_prefix_len)
                return ls + new_offset + cumulative_delta
            return idx + cumulative_delta

        return new_plain, map_index(start), map_index(end)

    @staticmethod
    def _apply_blockquote_prefix_to_selection(plain: str, start: int, end: int) -> Tuple[str, int, int]:
        affected_lines: List[Tuple[int, int, int]] = []  # (line_start, line_end, old_prefix_len)
        i = plain.rfind("\n", 0, start) + 1
        while i < len(plain) and i < end:
            line_start = i
            line_end = plain.find("\n", line_start)
            if line_end == -1:
                line_end = len(plain)
            if line_start < end and line_end > start:
                old_prefix_len = NotesFormatterService._get_blockquote_prefix_len_at_line_start(plain, line_start)
                affected_lines.append((line_start, line_end, old_prefix_len))
            i = line_end + 1
            if line_end >= len(plain):
                break

        if not affected_lines:
            return plain, start, end

        # Toggle behavior:
        # - If *all* intersecting lines already have a blockquote prefix, remove it.
        # - Otherwise, ensure all intersecting lines have "> " as prefix.
        all_quoted = all(old_prefix_len > 0 for _ls, _le, old_prefix_len in affected_lines)
        desired_prefix = "" if all_quoted else "> "
        desired_prefix_len = len(desired_prefix)

        new_parts: List[str] = []
        last = 0
        for line_start, line_end, old_prefix_len in affected_lines:
            new_parts.append(plain[last:line_start])
            new_parts.append(desired_prefix)
            new_parts.append(plain[line_start + old_prefix_len : line_end])
            last = line_end
        new_plain = "".join(new_parts) + plain[last:]

        def map_index(idx: int) -> int:
            cumulative_delta = 0
            for ls, _le, old_len in affected_lines:
                delta = desired_prefix_len - old_len
                if idx < ls:
                    break
                if idx >= ls + old_len:
                    cumulative_delta += delta
                    continue
                offset = idx - ls
                new_offset = min(max(offset, 0), desired_prefix_len)
                return ls + new_offset + cumulative_delta
            return idx + cumulative_delta

        return new_plain, map_index(start), map_index(end)


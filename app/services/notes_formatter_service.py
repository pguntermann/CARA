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
from typing import Dict, List, Tuple


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

        parts: List[str] = []
        i = 0
        for start, end, display_text, lookup_text in tokens:
            if start > i:
                parts.append(html.escape(plain[i:start]).replace("\n", "<br>"))

            safe_display = html.escape(display_text)
            lookup_clean = lookup_text.rstrip(".,;:!?)")
            in_game = (
                lookup_clean in notation_to_ply
                or (" " in lookup_clean and lookup_clean.replace(" ", "", 1) in notation_to_ply)
            )

            if in_game:
                # Use lookup_text for href (may be normalized), but keep displayed text identical to user input.
                safe_href = html.escape(lookup_text)
                parts.append(f'<a href="move:{safe_href}" style="{link_style}">{safe_display}</a>')
            else:
                parts.append(f'<span style="{bold_style}">{safe_display}</span>')
            i = end

        if i < len(plain):
            parts.append(html.escape(plain[i:]).replace("\n", "<br>"))
        return "".join(parts)


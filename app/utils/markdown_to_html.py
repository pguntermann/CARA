"""Minimal markdown-to-HTML converter for inline + block content.

Supports: headings, paragraphs, lists, links, bold, italic, inline code, fenced code blocks.
Image syntax ![alt](url) and [![alt](img)](link) is stripped (no output).
No external dependencies; avoids Qt setMarkdown() and block iteration to prevent crashes.
"""

import re
import html


def _escape(s: str) -> str:
    """Escape for HTML text content."""
    return html.escape(s, quote=True)


def _escape_attr(s: str) -> str:
    """Escape for HTML attribute values."""
    return html.escape(s, quote=True)


def _heading_id(text: str) -> str:
    """Generate a slug for use as heading id (anchor target)."""
    slug = "".join(c if c.isalnum() or c == " " else "" for c in text.lower())
    slug = "-".join(slug.split())
    return slug or "section"


def _process_inline(line: str) -> str:
    """Process inline markdown for a single line of text.

    Supports:
    - links: [text](url)
    - bold: **text** / __text__
    - italic: *text* / _text_
    - inline code: `code`
    - images are stripped (no output)
    """
    out: list[str] = []
    i = 0
    while i < len(line):
        # Link-wrapped image: [![alt](image_url)](link_url) — strip (no output)
        wrap_match = re.match(r"\[!\[([^\]]*)\]\(\s*([^\s)]*)\s*\)\]\(\s*([^\s)]*)\s*\)", line[i:])
        if wrap_match:
            i += wrap_match.end()
            continue
        # Image: ![alt](url) or ![alt](url "title") — strip (no output)
        image_match = re.match(r"!\[([^\]]*)\]\(\s*([^\s)]*)(?:\s+[\"']([^\"']*)[\"'])?\s*\)", line[i:])
        if image_match:
            i += image_match.end()
            continue
        # Link: [text](url)
        link_match = re.match(r"\[([^\]]*)\]\(\s*([^\s)]+)(?:\s+[\"']([^\"']*)[\"'])?\s*\)", line[i:])
        if link_match:
            text, url, title = link_match.group(1), link_match.group(2), link_match.group(3)
            href = _escape_attr(url)
            title_attr = f' title="{_escape_attr(title)}"' if title else ""
            out.append(f'<a href="{href}"{title_attr}>{_escape(text)}</a>')
            i += link_match.end()
            continue

        # Inline code: `code`
        code_match = re.match(r"`([^`]*)`", line[i:])
        if code_match:
            content = code_match.group(1)
            out.append(f"<code>{_escape(content)}</code>")
            i += code_match.end()
            continue

        # Bold: **text** or __text__
        bold_match = re.match(r"\*\*([^*]+)\*\*|__([^_]+)__", line[i:])
        if bold_match:
            content = bold_match.group(1) or bold_match.group(2)
            out.append(f"<strong>{_escape(content)}</strong>")
            i += bold_match.end()
            continue

        # Italic: *text* or _text_
        italic_match = re.match(r"\*([^*]+)\*|_([^_]+)_", line[i:])
        if italic_match:
            content = italic_match.group(1) or italic_match.group(2)
            out.append(f"<em>{_escape(content)}</em>")
            i += italic_match.end()
            continue

        out.append(_escape(line[i]))
        i += 1
    return "".join(out)


def markdown_inline_to_html(md: str) -> str:
    """Convert a single markdown line to inline HTML (no <p>/<ul> wrappers)."""
    return _process_inline(md)


def markdown_notes_to_html(
    md: str,
    heading_font_point_sizes: dict[str, float | int] | None = None,
    heading_level_offset: int = 0,
) -> str:
    """Markdown-to-HTML renderer optimized for Notes.

    Goals:
    - Preserve user typing/whitespace as much as possible.
    - Support headings and inline markdown per line.
    - Keep behavior predictable for cursor restoration in QTextEdit.
    - Still strips images (handled in _process_inline).

    Supported:
    - Headings: `#`..`######` at the start of a line (optional leading whitespace)
    - Inline: links, bold, italic, inline code
    - Fenced code blocks: ```...``` (rendered as <pre>, no inline parsing inside)
    """
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []

    in_code = False
    code_lines: list[str] = []

    # The Notes view re-renders HTML from `QTextEdit.toPlainText()` while you type.
    # If we remove markdown syntax characters (e.g. '#', '**'), the next re-render
    # can't recognize them anymore.
    #
    # To avoid that, we preserve markdown syntax characters by rendering them
    # in invisible spans. They remain in the underlying plain text, but do not
    # affect layout.
    # Keep markdown syntax characters in the underlying document, but ensure they
    # do not contribute any visible spacing in QTextEdit rendering.
    # Using absolute positioning off-screen prevents them from affecting layout.
    md_marker_style = (
        "color: transparent; "
        "position: absolute; left: -10000px; top: -10000px; "
        "padding: 0; margin: 0; border: 0; "
        "pointer-events: none;"
    )

    def _process_inline_notes_preserve_markers(inline: str) -> str:
        """Inline markdown renderer that preserves syntax chars in plain text."""
        out_inline: list[str] = []
        i2 = 0
        while i2 < len(inline):
            # Link-wrapped image: strip (no output)
            wrap_match = re.match(r"\[!\[([^\]]*)\]\(\s*([^\s)]*)\s*\)\]\(\s*([^\s)]*)\s*\)", inline[i2:])
            if wrap_match:
                i2 += wrap_match.end()
                continue

            # Image: strip (no output)
            image_match = re.match(
                r"!\[([^\]]*)\]\(\s*([^\s)]*)(?:\s+[\"']([^\"']*)[\"'])?\s*\)",
                inline[i2:],
            )
            if image_match:
                i2 += image_match.end()
                continue

            # Link: [text](url) with optional title
            link_match = re.match(
                r"\[([^\]]*)\]\(\s*([^\s)]+)(?:\s+[\"']([^\"']*)[\"'])?\s*\)",
                inline[i2:],
            )
            if link_match:
                text, url, title = link_match.group(1), link_match.group(2), link_match.group(3)

                out_inline.append(f'<span style="{md_marker_style}">[</span>')
                out_inline.append(
                    f'<a href="{_escape_attr(url)}">{_escape(text)}</a>'
                )
                # Preserve the markdown delimiter "](" as invisible text.
                out_inline.append(f'<span style="{md_marker_style}">](</span>')
                # Keep url in plain text too (invisible).
                out_inline.append(f'<span style="{md_marker_style}">{_escape(url)}</span>')
                if title:
                    out_inline.append(
                        f'<span style="{md_marker_style}"> "{_escape(title)}"</span>'
                    )
                out_inline.append(f'<span style="{md_marker_style}">)</span>')

                i2 += link_match.end()
                continue

            # Inline code: `code`
            code_match = re.match(r"`([^`]*)`", inline[i2:])
            if code_match:
                content = code_match.group(1)
                # Render backticks invisibly and code visibly
                out_inline.append(f'<span style="{md_marker_style}">`</span>')
                out_inline.append(f"<code>{_escape(content)}</code>")
                out_inline.append(f'<span style="{md_marker_style}">`</span>')
                i2 += code_match.end()
                continue

            # Bold: **text** or __text__
            bold_match = re.match(r"\*\*([^*]+)\*\*|__([^_]+)__", inline[i2:])
            if bold_match:
                content = bold_match.group(1) or bold_match.group(2)
                matched = bold_match.group(0)
                marker = "**" if matched.startswith("**") else "__"
                out_inline.append(f'<span style="{md_marker_style}">{marker}</span>')
                out_inline.append(f'<span style="font-weight:bold">{_escape(content)}</span>')
                out_inline.append(f'<span style="{md_marker_style}">{marker}</span>')
                i2 += bold_match.end()
                continue

            # Italic: *text* or _text_
            italic_match = re.match(r"\*([^*]+)\*|_([^_]+)_", inline[i2:])
            if italic_match:
                content = italic_match.group(1) or italic_match.group(2)
                matched = italic_match.group(0)
                marker = "*" if matched.startswith("*") else "_"
                out_inline.append(f'<span style="{md_marker_style}">{marker}</span>')
                out_inline.append(f'<span style="font-style:italic">{_escape(content)}</span>')
                out_inline.append(f'<span style="{md_marker_style}">{marker}</span>')
                i2 += italic_match.end()
                continue

            # Default: escape a single character
            out_inline.append(_escape(inline[i2]))
            i2 += 1

        return "".join(out_inline)

    for raw in lines:
        stripped = raw.strip()

        # Fenced code block
        if stripped.startswith("```"):
            if in_code:
                out.append("<pre>" + _escape("\n".join(code_lines)) + "</pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(raw)
            continue

        # Headings: allow optional leading whitespace
        heading_match = re.match(r"^\s*(#{1,6})\s+(.+)$", raw)
        if heading_match:
            level = len(heading_match.group(1))
            effective_level = min(6, level + heading_level_offset)
            content = heading_match.group(2).strip()
            hid = _escape_attr(_heading_id(content))
            base_pt = (
                float(heading_font_point_sizes.get(f"h{effective_level}", 12 + effective_level))
                if heading_font_point_sizes
                else float(12 + effective_level)
            )
            font_pt = int(round(base_pt))
            # Preserve heading marker in underlying plain text but hide it visually.
            marker_prefix = heading_match.group(1) + " "
            out.append(
                f'<span style="{md_marker_style}">{_escape(marker_prefix)}</span>'
                f'<span id="{hid}" style="font-weight:bold; font-size:{font_pt}pt;">'
                f"{_process_inline_notes_preserve_markers(content)}"
                "</span>"
            )
            continue

        # Normal line: inline markdown, preserve line breaks via <br>
        out.append(_process_inline_notes_preserve_markers(raw))

    return "<br>".join(out)


def markdown_to_html(
    md: str,
    heading_styles: dict[str, str] | None = None,
    heading_level_offset: int = 0,
) -> str:
    """Convert markdown string to HTML. Uses body, p, h1-h6, ul, ol, li, pre, a, strong.

    heading_styles: optional map "h1".."h6" to inline style strings (emitted on heading tags).
    heading_level_offset: if set (e.g. 1), shift heading levels so # → h2, ## → h3, etc.,
        so the top-level heading is smaller when the renderer uses large default h1 size.
    """
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    code_lines: list[str] = []
    in_list = False
    list_tag: str | None = None  # "ul" or "ol"
    in_paragraph = False
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal in_paragraph, paragraph_lines
        if not in_paragraph or not paragraph_lines:
            return
        text = " ".join(p.strip() for p in paragraph_lines)
        if text:
            out.append("<p>")
            out.append(_process_inline(text))
            out.append("</p>")
        paragraph_lines = []
        in_paragraph = False

    def flush_list() -> None:
        nonlocal in_list, list_tag
        if not in_list or not list_tag:
            return
        out.append(f"</{list_tag}>")
        in_list = False
        list_tag = None

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Fenced code block
        if stripped.startswith("```"):
            if in_code:
                # End code block: emit <pre> with escaped content
                out.append("<pre>")
                out.append(_escape("\n".join(code_lines)))
                out.append("</pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                flush_list()
                in_code = True
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(raw)
            i += 1
            continue

        # Headings: # to ###### (with id for anchor links; optional inline style; optional level offset)
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match and not in_list:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            effective_level = min(6, level + heading_level_offset)
            content = heading_match.group(2).strip()
            hid = _escape_attr(_heading_id(content))
            key = f"h{effective_level}"
            if heading_styles and key in heading_styles:
                style_attr = _escape_attr(heading_styles[key])
                out.append(f'<h{effective_level} id="{hid}" style="{style_attr}">{_process_inline(content)}</h{effective_level}>')
            else:
                out.append(f'<h{effective_level} id="{hid}">{_process_inline(content)}</h{effective_level}>')
            i += 1
            continue

        # Unordered list: - or * or +
        ul_match = re.match(r"^(\s*)[-*+]\s+(.*)$", raw)
        if ul_match:
            flush_paragraph()
            if not in_list or list_tag != "ul":
                flush_list()
                out.append("<ul>")
                in_list = True
                list_tag = "ul"
            content = ul_match.group(2)
            out.append(f"<li>{_process_inline(content)}</li>")
            i += 1
            continue

        # Ordered list: 1. 2. etc.
        ol_match = re.match(r"^(\s*)\d+\.\s+(.*)$", raw)
        if ol_match:
            flush_paragraph()
            if not in_list or list_tag != "ol":
                flush_list()
                out.append("<ol>")
                in_list = True
                list_tag = "ol"
            content = ol_match.group(2)
            out.append(f"<li>{_process_inline(content)}</li>")
            i += 1
            continue

        # Empty line
        if not stripped:
            flush_paragraph()
            flush_list()
            i += 1
            continue

        # Paragraph
        flush_list()
        if not in_paragraph:
            in_paragraph = True
            paragraph_lines = [stripped]
        else:
            paragraph_lines.append(stripped)
        i += 1

    flush_paragraph()
    flush_list()
    if in_code and code_lines:
        out.append("<pre>")
        out.append(_escape("\n".join(code_lines)))
        out.append("</pre>")

    return "".join(out)

"""Minimal markdown-to-HTML converter for inline content (release notes, licenses).

Supports: headings, paragraphs, lists, links, bold, fenced code blocks.
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
    """Process inline markdown: strip images, handle links [text](url), bold **text**."""
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
        # Bold: **text** or __text__
        bold_match = re.match(r"\*\*([^*]+)\*\*|__([^_]+)__", line[i:])
        if bold_match:
            content = bold_match.group(1) or bold_match.group(2)
            out.append(f"<strong>{_escape(content)}</strong>")
            i += bold_match.end()
            continue
        out.append(_escape(line[i]))
        i += 1
    return "".join(out)


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

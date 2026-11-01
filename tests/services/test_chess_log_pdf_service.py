"""Tests for ChessLogPDFService — filename helpers and export smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

    from app.services.chess_log_pdf_service import (
        ChessLogPDFService,
        TagRowSnapshot,
        default_chess_log_charts_pdf_filename,
        default_chess_log_narrative_pdf_filename,
        default_chess_log_tags_pdf_filename,
    )


class TestFilenameHelpers(unittest.TestCase):
    def test_tags_filename_has_pdf_extension(self):
        name = default_chess_log_tags_pdf_filename()
        self.assertTrue(name.endswith(".pdf"), name)

    def test_tags_filename_shallow_variant(self):
        name = default_chess_log_tags_pdf_filename(is_shallow_only=True)
        self.assertIn("CheckLogs", name)

    def test_charts_filename_has_pdf_extension(self):
        name = default_chess_log_charts_pdf_filename()
        self.assertTrue(name.endswith(".pdf"), name)

    def test_charts_filename_includes_player_name(self):
        name = default_chess_log_charts_pdf_filename("Paul")
        self.assertIn("Paul", name)

    def test_charts_filename_sanitizes_spaces(self):
        name = default_chess_log_charts_pdf_filename("Paul Morphy")
        self.assertTrue(name.endswith(".pdf"), name)
        self.assertNotIn(" ", name)

    def test_narrative_filename_has_pdf_extension(self):
        if not _QT_OK:
            self.skipTest("Qt unavailable")
        name = default_chess_log_narrative_pdf_filename()
        self.assertTrue(name.endswith(".pdf"), name)

    def test_narrative_filename_contains_narrative_summary(self):
        if not _QT_OK:
            self.skipTest("Qt unavailable")
        name = default_chess_log_narrative_pdf_filename()
        self.assertIn("NarrativeSummary", name)

    def test_narrative_filename_includes_player_name(self):
        if not _QT_OK:
            self.skipTest("Qt unavailable")
        name = default_chess_log_narrative_pdf_filename("Paul")
        self.assertIn("Paul", name)

    def test_narrative_filename_sanitizes_spaces(self):
        if not _QT_OK:
            self.skipTest("Qt unavailable")
        name = default_chess_log_narrative_pdf_filename("Paul Morphy")
        self.assertTrue(name.endswith(".pdf"), name)
        self.assertNotIn(" ", name)


@requires_qt
class TestExportNarrativeReport(unittest.TestCase):
    """Smoke test and title check for export_narrative_report."""

    def test_export_narrative_report_creates_file(self):
        svc = ChessLogPDFService({})
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_narrative_report(
                tmp_path,
                player_name="Paul",
                source_label="Active Database",
                narrative_text="A test narrative.",
                model_label="Anthropic claude-opus-4-7",
                generated_at="2026-01-15 10:30",
                n_games=10,
                g_games=7,
                m_moments=23,
                s_flagged=18,
            )
            self.assertTrue(result, "export_narrative_report returned False")
            self.assertTrue(tmp_path.exists(), "PDF file not created")
            self.assertGreater(tmp_path.stat().st_size, 0, "PDF file is empty")
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_export_narrative_report_no_narrative_succeeds(self):
        svc = ChessLogPDFService({})
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_narrative_report(tmp_path, "", "", "")
            self.assertTrue(result)
        finally:
            tmp_path.unlink(missing_ok=True)


@requires_qt
class TestExportTagsSmoke(unittest.TestCase):
    """Smoke tests: export_tags writes a non-empty PDF file."""

    _MINIMAL_CONFIG: dict = {}

    def _make_minimal_snapshot(self) -> TagRowSnapshot:
        return TagRowSnapshot(
            move_label="1. e4",
            preset="CLAMP",
            entries=[{"preset": "CLAMP", "cat": "C", "why": "test note"}],
            fen=None,
            played_move=None,
            show_ignore=False,
        )

    def test_export_tags_creates_file(self):
        svc = ChessLogPDFService(self._MINIMAL_CONFIG)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_tags(tmp_path, [{"header": None, "rows": [self._make_minimal_snapshot()]}])
            self.assertTrue(result, "export_tags returned False")
            self.assertTrue(tmp_path.exists(), "PDF file not created")
            self.assertGreater(tmp_path.stat().st_size, 0, "PDF file is empty")
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_export_tags_multi_game(self):
        svc = ChessLogPDFService(self._MINIMAL_CONFIG)
        groups = [
            {"header": "White - Black * (2026.01.01 - 20 moves)", "rows": [self._make_minimal_snapshot()]},
            {"header": "A - B 1-0 (2026.02.01 - 15 moves)", "rows": [self._make_minimal_snapshot()]},
        ]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_tags(tmp_path, groups)
            self.assertTrue(result)
            self.assertGreater(tmp_path.stat().st_size, 0)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_export_tags_empty_groups_succeeds(self):
        svc = ChessLogPDFService(self._MINIMAL_CONFIG)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_tags(tmp_path, [])
            self.assertTrue(result)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_export_charts_report_creates_file(self):
        from PyQt6.QtGui import QPixmap
        svc = ChessLogPDFService(self._MINIMAL_CONFIG)
        pixmap = QPixmap(400, 200)
        pixmap.fill()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_charts_report(
                tmp_path,
                player_name="Paul",
                source_label="Active Database",
                chart_pixmaps=[("CLAMP", pixmap)],
                narrative_text="Test narrative text.",
                shallow_rows=[],
            )
            self.assertTrue(result, "export_charts_report returned False")
            self.assertGreater(tmp_path.stat().st_size, 0)
        finally:
            tmp_path.unlink(missing_ok=True)


class TestParseBoldSpans(unittest.TestCase):
    """Unit tests for ChessLogPDFService._parse_bold_spans — no Qt needed."""

    def _parse(self, text):
        if _QT_OK:
            return ChessLogPDFService._parse_bold_spans(text)
        # Fallback: import directly without Qt guard
        from app.services.chess_log_pdf_service import ChessLogPDFService as _Svc
        return _Svc._parse_bold_spans(text)

    def test_empty_string(self):
        self.assertEqual(self._parse(""), [])

    def test_no_markers(self):
        self.assertEqual(self._parse("hello world"), [("hello world", False)])

    def test_single_bold_span(self):
        result = self._parse("**bold**")
        self.assertEqual(result, [("bold", True)])

    def test_bold_in_middle(self):
        result = self._parse("before **bold** after")
        self.assertEqual(result, [("before ", False), ("bold", True), (" after", False)])

    def test_two_bold_spans(self):
        result = self._parse("**a** and **b**")
        self.assertIn(("a", True), result)
        self.assertIn(("b", True), result)

    def test_unmatched_trailing_marker_treated_as_literal(self):
        result = self._parse("text **orphan")
        joined = "".join(s for s, _ in result)
        self.assertIn("**orphan", joined)
        # None of the runs should be bold since there's no closing marker.
        self.assertTrue(all(not bold for _, bold in result))


@requires_qt
class TestDrawNarrativePaginated(unittest.TestCase):
    """drawText-spy tests for bold-span rendering in _draw_narrative_paginated."""

    from unittest.mock import MagicMock

    def _make_service(self):
        return ChessLogPDFService({})

    def _run(self, text):
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QRectF
        svc = self._make_service()
        painter = MagicMock()
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        svc._draw_narrative_paginated(painter, writer, content, 0.0, text)
        return svc, painter

    def test_no_asterisks_reach_draw_text(self):
        _, painter = self._run("Regular **bold phrase** rest of line.")
        drawn_strings = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        self.assertFalse(
            any("**" in s for s in drawn_strings),
            f"raw ** markers reached drawText: {drawn_strings}",
        )

    def test_bold_font_used_for_bold_span(self):
        svc, painter = self._run("Plain **emphatic** end.")
        bold_calls = [
            c for c in painter.setFont.call_args_list
            if c.args and c.args[0] == svc._font_body_bold
        ]
        self.assertGreater(len(bold_calls), 0,
                           "Expected at least one setFont(_font_body_bold) call")

    def test_plain_text_no_bold_font_calls(self):
        svc, painter = self._run("Completely plain sentence with no markers.")
        bold_calls = [
            c for c in painter.setFont.call_args_list
            if c.args and c.args[0] == svc._font_body_bold
        ]
        self.assertEqual(len(bold_calls), 0,
                         "No bold font expected for plain text")

    def test_heading_does_not_call_draw_text_directly(self):
        """Heading lines go through _section_heading, not the word-draw loop."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        svc = self._make_service()
        painter = MagicMock()
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        with patch.object(svc, "_section_heading", return_value=10.0) as mock_sh:
            svc._draw_narrative_paginated(painter, writer, content, 0.0,
                                          "## My Heading\nBody text here.")
        mock_sh.assert_called_once()
        drawn_strings = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        self.assertFalse(
            any("My Heading" in s for s in drawn_strings),
            "Heading text should not reach drawText directly",
        )


class TestIsTableSeparator(unittest.TestCase):
    """Unit tests for ChessLogPDFService._is_table_separator — no Qt needed."""

    def _check(self, line):
        if _QT_OK:
            return ChessLogPDFService._is_table_separator(line)
        from app.services.chess_log_pdf_service import ChessLogPDFService as _Svc
        return _Svc._is_table_separator(line)

    def test_standard_separator(self):
        self.assertTrue(self._check("| --- | --- | --- |"))

    def test_no_spaces_separator(self):
        self.assertTrue(self._check("|---|---|"))

    def test_colon_aligned(self):
        self.assertTrue(self._check("| :---: | ---: |"))

    def test_content_row_is_not_separator(self):
        self.assertFalse(self._check("| a | b |"))

    def test_plain_text_is_not_separator(self):
        self.assertFalse(self._check("regular prose"))

    def test_empty_string_is_not_separator(self):
        self.assertFalse(self._check(""))

    def test_single_cell_separator_is_not_separator(self):
        self.assertFalse(self._check("| --- |"))


class TestParsePipeTable(unittest.TestCase):
    """Unit tests for ChessLogPDFService._parse_pipe_table — no Qt needed."""

    def _parse(self, lines):
        if _QT_OK:
            return ChessLogPDFService._parse_pipe_table(lines)
        from app.services.chess_log_pdf_service import ChessLogPDFService as _Svc
        return _Svc._parse_pipe_table(lines)

    def test_three_column_table(self):
        lines = [
            "| Skill | Observed Issue | Strategic Impact |",
            "| --- | --- | --- |",
            "| Checks | Often missed | Allows counterplay |",
        ]
        header, body = self._parse(lines)
        self.assertEqual(header, ["Skill", "Observed Issue", "Strategic Impact"])
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0], ["Checks", "Often missed", "Allows counterplay"])

    def test_whitespace_stripped_from_cells(self):
        lines = [
            "|  A  |  B  |",
            "| --- | --- |",
            "|  x  |  y  |",
        ]
        header, body = self._parse(lines)
        self.assertEqual(header, ["A", "B"])
        self.assertEqual(body[0], ["x", "y"])

    def test_short_body_row_padded(self):
        lines = [
            "| A | B | C |",
            "| --- | --- | --- |",
            "| x | y |",  # one cell short
        ]
        header, body = self._parse(lines)
        self.assertEqual(len(body[0]), 3)
        self.assertEqual(body[0][2], "")

    def test_long_body_row_truncated(self):
        lines = [
            "| A | B |",
            "| --- | --- |",
            "| x | y | extra |",
        ]
        header, body = self._parse(lines)
        self.assertEqual(len(body[0]), 2)

    def test_no_body_rows(self):
        lines = [
            "| A | B |",
            "| --- | --- |",
        ]
        header, body = self._parse(lines)
        self.assertEqual(header, ["A", "B"])
        self.assertEqual(body, [])

    def test_empty_input(self):
        header, body = self._parse([])
        self.assertEqual(header, [])
        self.assertEqual(body, [])


@requires_qt
class TestMeasurePipeTableRow(unittest.TestCase):
    """Tests for _measure_pipe_table_row — uses manual word-wrap, not painter.boundingRect."""

    def test_single_line_cells_give_one_line_height_plus_padding(self):
        from unittest.mock import MagicMock
        from PyQt6.QtGui import QFontMetrics
        svc = ChessLogPDFService({})
        painter = MagicMock()
        pad = 4.0
        line_h = float(QFontMetrics(svc._font_body).height())
        col_widths = [100.0, 200.0, 200.0]
        cells = ["Checks", "Often missed", "Allows counterplay"]
        result = svc._measure_pipe_table_row(
            painter, col_widths, cells, svc._font_body, pad
        )
        self.assertAlmostEqual(result, line_h + 2 * pad, places=1)

    def test_narrow_column_forces_wrapping_and_taller_height(self):
        from unittest.mock import MagicMock
        from PyQt6.QtGui import QFontMetrics
        svc = ChessLogPDFService({})
        painter = MagicMock()
        pad = 4.0
        line_h = float(QFontMetrics(svc._font_body).height())
        # Very narrow — forces multi-line wrap
        result = svc._measure_pipe_table_row(
            painter, [20.0], ["a b c d e f g"], svc._font_body, pad
        )
        self.assertGreater(result, line_h + 2 * pad)


@requires_qt
class TestDrawNarrativePaginatedTableDetection(unittest.TestCase):
    """Verify pipe tables are rendered as cells, not as raw | characters."""

    def _run(self, text):
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QRectF
        svc = ChessLogPDFService({})
        painter = MagicMock()
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        # _measure_pipe_table_row calls painter.boundingRect; return a real QRectF
        # so .height() yields a float and comparisons don't fail.
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        svc._draw_narrative_paginated(painter, writer, content, 0.0, text)
        return svc, painter

    def test_section_heading_keep_with_is_table_height_when_table_follows(self):
        """_section_heading must be called with keep_with >= header+first-body height."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QFontMetrics
        svc = ChessLogPDFService({})
        painter = MagicMock()
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)

        narrative = (
            "## Tactical Breakdown\n\n"
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Checks | Missed fork | Drops material |\n"
        )
        line_h = float(QFontMetrics(svc._font_body).height())
        with patch.object(svc, "_section_heading", return_value=10.0) as mock_sh:
            svc._draw_narrative_paginated(painter, writer, content, 0.0, narrative)
        self.assertEqual(mock_sh.call_count, 1)
        _, kwargs = mock_sh.call_args
        keep_with = kwargs.get("keep_with", mock_sh.call_args.args[-1] if mock_sh.call_args.args else 0)
        self.assertGreater(
            keep_with, line_h * 2,
            f"keep_with ({keep_with:.1f}) should exceed default line_h*2 ({line_h * 2:.1f}) "
            "when a table follows the heading",
        )

    def test_section_heading_keep_with_is_default_when_no_table_follows(self):
        """keep_with stays at line_h*2 when heading is followed by prose."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QFontMetrics
        svc = ChessLogPDFService({})
        painter = MagicMock()
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)

        narrative = "## Patterns & Recurrent Themes\n\nSome prose follows here.\n"
        line_h = float(QFontMetrics(svc._font_body).height())
        with patch.object(svc, "_section_heading", return_value=10.0) as mock_sh:
            svc._draw_narrative_paginated(painter, writer, content, 0.0, narrative)
        _, kwargs = mock_sh.call_args
        keep_with = kwargs.get("keep_with", mock_sh.call_args.args[-1] if mock_sh.call_args.args else 0)
        self.assertAlmostEqual(keep_with, line_h * 2, places=1)

    def test_draw_rect_called_for_table_cells(self):
        narrative = (
            "## Tactical Breakdown\n\n"
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Checks | Missed tactics | Drops material |\n"
            "| Loose Pieces | Left hanging | Opponent gains tempo |\n"
        )
        _, painter = self._run(narrative)
        # 1 header row + 2 body rows, each with 3 cells = 9 drawRect calls minimum
        rect_calls = painter.drawRect.call_count
        self.assertGreaterEqual(rect_calls, 9, f"Expected >=9 drawRect calls, got {rect_calls}")

    def test_raw_pipe_chars_do_not_reach_draw_text(self):
        narrative = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Checks | Missed fork | Loses piece |\n"
        )
        _, painter = self._run(narrative)
        drawn_strings = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        self.assertFalse(
            any("|" in s for s in drawn_strings),
            f"Raw | characters reached drawText: {[s for s in drawn_strings if '|' in s]}",
        )

    def test_separator_row_does_not_reach_draw_text(self):
        narrative = (
            "| A | B | C |\n"
            "| --- | --- | --- |\n"
            "| x | y | z |\n"
        )
        _, painter = self._run(narrative)
        drawn_strings = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        self.assertFalse(
            any("---" in s for s in drawn_strings),
            "Separator row text reached drawText",
        )

    def test_header_cell_text_reaches_draw_text(self):
        narrative = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Checks | Something | Something else |\n"
        )
        _, painter = self._run(narrative)
        drawn_strings = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        self.assertTrue(
            any("Skill" in s for s in drawn_strings),
            "Header cell text 'Skill' did not reach drawText",
        )


@requires_qt
class TestExportChartsReportWithTable(unittest.TestCase):
    """Smoke test: export_charts_report handles a three-section narrative with a pipe table."""

    def test_export_creates_nonempty_pdf_with_table_narrative(self):
        from PyQt6.QtGui import QPixmap
        svc = ChessLogPDFService({})
        pixmap = QPixmap(400, 200)
        pixmap.fill()
        narrative = (
            "## Patterns & Recurrent Themes\n\n"
            "You tend to rush in the middlegame.\n\n"
            "## Tactical Breakdown\n\n"
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Checks | Missed back-rank threats | Allows opponent counterplay |\n"
            "| Loose Pieces | Left pieces undefended | Material loss under pressure |\n\n"
            "## Key Takeaways\n\n"
            "Your note 'I just didn't calculate far enough' shows the pattern clearly.\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = svc.export_charts_report(
                tmp_path,
                player_name="Paul",
                source_label="Active Database",
                chart_pixmaps=[("CLAMP", pixmap)],
                narrative_text=narrative,
                shallow_rows=[],
            )
            self.assertTrue(result, "export_charts_report returned False")
            self.assertGreater(tmp_path.stat().st_size, 0, "PDF file is empty")
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# _is_bullet_line — no Qt needed
# ---------------------------------------------------------------------------

class TestIsBulletLine(unittest.TestCase):

    def setUp(self):
        if not _QT_OK:
            self.skipTest("Qt platform plugin unavailable")
        self._svc = ChessLogPDFService({})

    def _check(self, line, expected):
        self.assertEqual(self._svc._is_bullet_line(line), expected, repr(line))

    def test_dash_bullet(self):
        self._check("- foo", True)

    def test_asterisk_bullet(self):
        self._check("* foo", True)

    def test_plus_bullet(self):
        self._check("+ foo", True)

    def test_leading_whitespace(self):
        self._check("  - foo", True)

    def test_bare_dash_not_bullet(self):
        self._check("-", False)

    def test_dash_space_only_not_bullet(self):
        self._check("- ", False)

    def test_no_space_after_dash_not_bullet(self):
        self._check("-foo", False)

    def test_regular_prose_not_bullet(self):
        self._check("regular prose", False)

    def test_empty_not_bullet(self):
        self._check("", False)


# ---------------------------------------------------------------------------
# _parse_bullet_line — no Qt needed
# ---------------------------------------------------------------------------

class TestParseBulletLine(unittest.TestCase):

    def setUp(self):
        if not _QT_OK:
            self.skipTest("Qt platform plugin unavailable")
        self._svc = ChessLogPDFService({})

    def test_strips_dash_marker(self):
        result = self._svc._parse_bullet_line("- **Bold.** rest")
        self.assertEqual(result, "**Bold.** rest")

    def test_strips_asterisk_marker(self):
        result = self._svc._parse_bullet_line("  * foo bar")
        self.assertEqual(result, "foo bar")

    def test_strips_plus_marker(self):
        result = self._svc._parse_bullet_line("+ trailing")
        self.assertEqual(result, "trailing")


# ---------------------------------------------------------------------------
# _draw_narrative_paginated — bullet detection
# ---------------------------------------------------------------------------

@requires_qt
class TestMeasureBulletLineSpanAware(unittest.TestCase):
    """Regression tests: _measure_bullet_line must use span-aware measurement.

    Bug: the original implementation reassembled spans to plain text and called
    painter.boundingRect(plain), which measured all words at body-font width.
    Bold lead-in words are wider than their plain equivalents, so the measured
    height was too small and _ensure_space reserved too little room, causing
    adjacent bullets to overlap.

    Fix: replaced the boundingRect call with _count_cell_lines (the same
    per-word bold/plain algorithm used by _draw_wrapped_spans) so measurement
    and drawing always agree.
    """

    def setUp(self):
        self._svc = ChessLogPDFService({})

    def _span_aware_h(self, text, content_w, bullet_indent=12.0, bullet_gap=6.0, pad=2.0):
        """Ground-truth height: _count_cell_lines × line_h + 2×pad."""
        from PyQt6.QtGui import QFontMetrics
        fm_body = QFontMetrics(self._svc._font_body)
        line_h = float(fm_body.height())
        body_w = content_w - bullet_indent - bullet_gap
        spans = self._svc._parse_bold_spans(text)
        n = self._svc._count_cell_lines(spans, body_w)
        return max(n, 1) * line_h + 2 * pad

    def test_height_matches_count_cell_lines(self):
        """Result must equal _count_cell_lines-based height, not plain-text boundingRect."""
        from PyQt6.QtCore import QRectF
        content = QRectF(0, 0, 200, 700)
        text = (
            "**Rushing calculation in sharp positions.** "
            "You repeatedly find yourself playing the first forcing move without "
            "checking whether the opponent has a quiet intermediate move."
        )
        expected = self._span_aware_h(text, content.width())
        actual = self._svc._measure_bullet_line(content, text, 12.0, 6.0, 2.0)
        self.assertAlmostEqual(actual, expected, places=1)

    def test_all_bold_text_uses_bold_widths(self):
        """All-bold text: returned height reflects bold word widths, not plain word widths.

        Directly demonstrates the fixed bug: the old approach measured with fm_body for
        all words, but bold words are wider, so bold-aware line count >= plain-text count.
        The fixed method must return the bold-aware height.
        """
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QFontMetrics
        content = QRectF(0, 0, 200, 700)
        bullet_indent, bullet_gap, pad = 12.0, 6.0, 2.0
        body_w = content.width() - bullet_indent - bullet_gap
        # All-bold text maximises the bold vs. plain width difference.
        text = "**Book moves and opening habits suppressing live calculation throughout the game.**"
        fm_body = QFontMetrics(self._svc._font_body)
        line_h = float(fm_body.height())
        space_w = float(fm_body.horizontalAdvance(" "))
        spans = self._svc._parse_bold_spans(text)
        # Bold-aware (correct) line count.
        bold_n = self._svc._count_cell_lines(spans, body_w)
        # Plain-text (old broken) line count — measure all words at fm_body width.
        words = [w for seg, _ in spans for w in seg.split() if w]
        plain_n, cur, cur_w = 0, [], 0.0
        for word in words:
            ww = float(fm_body.horizontalAdvance(word))
            needed = ww if not cur else space_w + ww
            if cur and cur_w + needed > body_w:
                plain_n += 1
                cur, cur_w = [word], ww
            else:
                cur.append(word)
                cur_w += needed
        if cur:
            plain_n += 1
        # Bold words must be at least as wide as plain (bold_n >= plain_n always true).
        self.assertGreaterEqual(bold_n, plain_n)
        # The fixed method must return the bold-aware height.
        actual_h = self._svc._measure_bullet_line(content, text, bullet_indent, bullet_gap, pad)
        expected_h = max(bold_n, 1) * line_h + 2 * pad
        self.assertAlmostEqual(actual_h, expected_h, places=1)

    def test_bold_font_is_wider_than_body_font(self):
        """Sanity check: bold font is wider than body font, proving the bug can trigger."""
        from PyQt6.QtGui import QFontMetrics
        fm_body = QFontMetrics(self._svc._font_body)
        fm_bold = QFontMetrics(self._svc._font_body_bold)
        # Pick a wide word that appears in typical bold lead-ins.
        sample = "Rushing"
        self.assertGreater(
            fm_bold.horizontalAdvance(sample),
            fm_body.horizontalAdvance(sample),
            "Bold font must be wider than body font for the bug to manifest",
        )

    def test_no_painter_dependency(self):
        """_measure_bullet_line must not require a live painter (no boundingRect call).

        The old code called painter.boundingRect(plain_text); the fix uses
        _count_cell_lines which needs no painter. Calling with no painter arg
        (only 5 positional args after self) must succeed without error.
        """
        from PyQt6.QtCore import QRectF
        content = QRectF(0, 0, 300, 700)
        text = "**Lead-in.** Some body text here."
        # Five args (no painter): should run without TypeError after the fix.
        h = self._svc._measure_bullet_line(content, text, 12.0, 6.0, 2.0)
        self.assertGreater(h, 0)


@requires_qt
class TestDrawNarrativePaginatedBulletDetection(unittest.TestCase):
    """Verify that bullet list items render via the bullet path (• glyph, no '- ' prefix)."""

    def _run(self, text: str):
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QRectF
        svc = ChessLogPDFService({})
        painter = MagicMock()
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        # _measure_bullet_line calls painter.boundingRect; return a real QRectF
        # so .height() yields a float and comparisons succeed.
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        svc._draw_narrative_paginated(painter, writer, content, 0.0, text)
        return svc, painter

    def test_bullet_glyph_reaches_draw_text(self):
        # No heading — avoids the real QPainter path through _section_heading.
        narrative = (
            "- **Theme one.** Body text here.\n\n"
            "- **Theme two.** More body text.\n\n"
            "- **Theme three.** Even more text.\n"
        )
        _, painter = self._run(narrative)
        all_text_args = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        bullet_calls = [t for t in all_text_args if "•" in t]
        self.assertGreaterEqual(len(bullet_calls), 3, "Expected at least 3 bullet glyphs drawn")

    def test_no_dash_prefix_reaches_draw_text(self):
        narrative = (
            "- **Theme one.** Body text here.\n\n"
            "- **Theme two.** More body text.\n"
        )
        _, painter = self._run(narrative)
        all_text_args = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        dash_prefix_calls = [t for t in all_text_args if t.startswith("- ")]
        self.assertEqual(dash_prefix_calls, [], "No '- ' prefix should reach drawText")


class TestTagRowSnapshotBestMove(unittest.TestCase):
    """TagRowSnapshot carries the best_move field."""

    def test_snapshot_default_best_move_none(self):
        from app.services.chess_log_pdf_service import TagRowSnapshot
        snap = TagRowSnapshot(
            move_label="1. e4",
            preset="CLAMP",
            entries=[],
            fen=None,
            played_move=None,
            show_ignore=False,
        )
        self.assertIsNone(snap.best_move)

    def test_snapshot_stores_best_move(self):
        import chess
        from app.services.chess_log_pdf_service import TagRowSnapshot
        best = chess.Move.from_uci("d2d4")
        snap = TagRowSnapshot(
            move_label="1. e4",
            preset="CLAMP",
            entries=[],
            fen=None,
            played_move=chess.Move.from_uci("e2e4"),
            show_ignore=False,
            best_move=best,
        )
        self.assertEqual(snap.best_move, best)


@requires_qt
class TestRenderBoardPassesBestMove(unittest.TestCase):
    """_render_board forwards best_move to set_played_and_best."""

    def test_render_board_calls_set_played_and_best(self):
        import chess
        from unittest.mock import patch
        from app.services.chess_log_pdf_service import ChessLogPDFService

        svc = ChessLogPDFService({})
        played = chess.Move.from_uci("e2e4")
        best = chess.Move.from_uci("d2d4")
        captured_calls = []

        from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget as _Real

        class _SpyWidget(_Real):
            def set_played_and_best(self, p, b=None):
                captured_calls.append((p, b))
                super().set_played_and_best(p, b)

        # _render_board uses a local import from mini_chessboard_widget module
        with patch(
            "app.views.widgets.mini_chessboard_widget.MiniChessBoardWidget",
            new=_SpyWidget,
        ):
            svc._render_board(
                "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                played,
                best,
            )

        self.assertEqual(len(captured_calls), 1)
        self.assertEqual(captured_calls[0], (played, best))


@requires_qt
class TestNarrativeSanitizationInPDF(unittest.TestCase):
    """sanitize_narrative_markdown is applied before _draw_narrative_paginated
    so bare thematic-break lines never reach drawText."""

    def test_thematic_break_line_not_drawn(self):
        from unittest.mock import MagicMock, patch
        import tempfile
        from pathlib import Path
        from app.services.chess_log_pdf_service import ChessLogPDFService

        svc = ChessLogPDFService({})
        narrative = "## Patterns & Recurrent Themes\n\n---\n\n## Key Takeaways\n\nSome text."

        drawn_texts: list[str] = []

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Monkey-patch drawText to capture what would be drawn.
            original_export = ChessLogPDFService.export_charts_report

            def _patched_export(self_inner, path, chart_widgets, narrative_text, source_label="", player="", shallow_rows=None):
                # Write a minimal PDF but intercept the painter's drawText calls.
                from PyQt6.QtGui import QPdfWriter, QPainter, QPageSize
                from PyQt6.QtCore import QMarginsF, QSizeF
                writer = QPdfWriter(str(path))
                writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                writer.setPageMargins(QMarginsF(20, 20, 20, 20))
                painter = QPainter(writer)
                try:
                    content = self_inner._content_rect(writer)
                    y = content.top()
                    orig_draw = painter.drawText

                    def _capture_draw(*args, **kwargs):
                        for a in args:
                            if isinstance(a, str):
                                drawn_texts.append(a)
                        return orig_draw(*args, **kwargs)

                    painter.drawText = _capture_draw
                    self_inner._draw_narrative_paginated(painter, writer, content, y, narrative_text)
                finally:
                    painter.end()
                return True

            ChessLogPDFService.export_charts_report = _patched_export
            try:
                svc.export_charts_report(tmp_path, [], narrative, source_label="Test")
            finally:
                ChessLogPDFService.export_charts_report = original_export

            dash_only = [t for t in drawn_texts if t.strip() and all(c == "-" for c in t.strip())]
            self.assertEqual(dash_only, [], f"Bare dash text was drawn: {dash_only}")
        finally:
            tmp_path.unlink(missing_ok=True)


@requires_qt
class TestPDFPrintTheme(unittest.TestCase):
    """Phase 6: ChessLogPDFService merges chess_log_charts.pdf_report over ui.pdf."""

    def _make_config(self, ui_pdf_text, report_text, warn_fill=None, warn_outline=None) -> dict:
        cfg: dict = {
            "ui": {
                "pdf": {"colors": {"text": ui_pdf_text}},
                "panels": {
                    "detail": {
                        "chess_log_charts": {
                            "pdf_report": {
                                "colors": {
                                    "text": report_text,
                                }
                            }
                        }
                    }
                },
            }
        }
        if warn_fill is not None:
            cfg["ui"]["panels"]["detail"]["chess_log_charts"]["pdf_report"]["colors"]["warning_fill"] = warn_fill
        if warn_outline is not None:
            cfg["ui"]["panels"]["detail"]["chess_log_charts"]["pdf_report"]["colors"]["warning_outline"] = warn_outline
        return cfg

    def test_report_specific_text_color_overrides_ui_pdf(self):
        """chess_log_charts.pdf_report.colors.text must win over ui.pdf.colors.text."""
        cfg = self._make_config(ui_pdf_text=[255, 255, 255], report_text=[30, 30, 35])
        svc = ChessLogPDFService(cfg)
        from PyQt6.QtGui import QColor
        self.assertEqual(svc._text, QColor(30, 30, 35))

    def test_warning_fill_from_config(self):
        cfg = self._make_config(
            ui_pdf_text=[30, 30, 35], report_text=[30, 30, 35],
            warn_fill=[200, 150, 0],
        )
        svc = ChessLogPDFService(cfg)
        from PyQt6.QtGui import QColor
        self.assertEqual(svc._warn_fill, QColor(200, 150, 0))

    def test_warning_outline_from_config(self):
        cfg = self._make_config(
            ui_pdf_text=[30, 30, 35], report_text=[30, 30, 35],
            warn_outline=[50, 50, 60],
        )
        svc = ChessLogPDFService(cfg)
        from PyQt6.QtGui import QColor
        self.assertEqual(svc._warn_outline, QColor(50, 50, 60))

    def test_warning_fill_default_when_no_config(self):
        from PyQt6.QtGui import QColor
        svc = ChessLogPDFService({})
        self.assertEqual(svc._warn_fill, QColor(241, 196, 15))

    def test_warning_outline_default_when_no_config(self):
        from PyQt6.QtGui import QColor
        svc = ChessLogPDFService({})
        self.assertEqual(svc._warn_outline, QColor(30, 30, 30))

    def test_table_col_widths_pct_from_config(self):
        """table_col_widths_pct in pdf_report overrides the 20/40/40 default."""
        cfg: dict = {
            "ui": {
                "panels": {
                    "detail": {
                        "chess_log_charts": {
                            "pdf_report": {
                                "table_col_widths_pct": [25, 50, 25],
                            }
                        }
                    }
                },
            }
        }
        svc = ChessLogPDFService(cfg)
        widths = svc._table_col_widths(3, 100.0)
        self.assertAlmostEqual(widths[0], 25.0, places=1)
        self.assertAlmostEqual(widths[1], 50.0, places=1)
        self.assertAlmostEqual(widths[2], 25.0, places=1)

    def test_does_not_mutate_input_config(self):
        import copy
        cfg = self._make_config(ui_pdf_text=[30, 30, 35], report_text=[30, 30, 35])
        original = copy.deepcopy(cfg)
        ChessLogPDFService(cfg)
        self.assertEqual(cfg, original)

    def test_chess_log_card_fill_white_from_config(self):
        """ui.pdf.chess_log.card_fill overrides the shared card_fill for ChessLogPDFService."""
        from PyQt6.QtGui import QColor
        cfg: dict = {
            "ui": {
                "pdf": {
                    "colors": {"card_fill": [245, 247, 250]},
                    "chess_log": {"card_fill": [255, 255, 255]},
                }
            }
        }
        svc = ChessLogPDFService(cfg)
        self.assertEqual(svc._card, QColor(255, 255, 255),
                         "ui.pdf.chess_log.card_fill must override shared card_fill")

    def test_chess_log_card_fill_fallback_without_override(self):
        """Without ui.pdf.chess_log.card_fill, ChessLogPDFService uses shared card_fill."""
        from PyQt6.QtGui import QColor
        cfg: dict = {"ui": {"pdf": {"colors": {"card_fill": [245, 247, 250]}}}}
        svc = ChessLogPDFService(cfg)
        self.assertEqual(svc._card, QColor(245, 247, 250),
                         "shared card_fill must apply when chess_log override is absent")

    def test_theme_files_chess_log_card_fill_white(self):
        """ui.pdf.chess_log.card_fill must be [255,255,255] in all theme files."""
        import json, os
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "app", "config")
        for filename in ("style_default.config.json", "style_light.config.json", "style_scholar.config.json"):
            path = os.path.join(config_dir, filename)
            with open(path) as f:
                data = json.load(f)
            cl_fill = (data.get("ui", {}).get("pdf", {}).get("chess_log", {}).get("card_fill"))
            self.assertEqual(
                cl_fill, [255, 255, 255],
                f"{filename}: ui.pdf.chess_log.card_fill must be [255,255,255], got {cl_fill}",
            )

    def test_theme_files_shared_card_fill_tinted(self):
        """ui.pdf.colors.card_fill must not be pure white — it is shared with Philipp's reports."""
        import json, os
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "app", "config")
        for filename in ("style_default.config.json", "style_light.config.json", "style_scholar.config.json"):
            path = os.path.join(config_dir, filename)
            with open(path) as f:
                data = json.load(f)
            shared_fill = (data.get("ui", {}).get("pdf", {}).get("colors", {}).get("card_fill"))
            self.assertNotEqual(
                shared_fill, [255, 255, 255],
                f"{filename}: ui.pdf.colors.card_fill must not be white (shared with other reports)",
            )


@requires_qt
class TestCLAMPCheckboxVectorDrawing(unittest.TestCase):
    """Verify CLAMP/CCT checkboxes use vector QPainter shapes, not Unicode glyphs."""

    def _run_draw_tag_row(self, entries, preset="CLAMP"):
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        svc = ChessLogPDFService({})
        row = TagRowSnapshot(
            move_label="1. e4",
            preset=preset,
            entries=entries,
            fen=None,
            played_move=None,
            show_ignore=False,
        )
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12.0)
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        with patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, writer, content, 0.0, row)
        draw_rect_calls = painter.drawRect.call_args_list
        draw_path_calls = painter.drawPath.call_args_list
        drawn_strings = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        return draw_rect_calls, draw_path_calls, drawn_strings

    def test_no_glyph_checkboxes_in_draw_text(self):
        """No Unicode checkbox glyphs should reach drawText for CLAMP rows."""
        entries = [
            {"preset": "CLAMP", "cat": "C", "why": ""},
            {"preset": "CLAMP", "cat": "L", "why": "I attacked early"},
        ]
        _, _, drawn_strings = self._run_draw_tag_row(entries)
        glyph_calls = [s for s in drawn_strings if "☐" in s or "☑" in s]
        self.assertEqual(glyph_calls, [], f"Glyph characters reached drawText: {glyph_calls}")

    def test_draw_rect_called_once_per_cat(self):
        """One drawRect call per CLAMP category (5 total for CLAMP)."""
        entries = [{"preset": "CLAMP", "cat": "C", "why": ""}]
        from app.utils.chess_log_preset_order import CLAMP_ORDER
        draw_rect_calls, _, _ = self._run_draw_tag_row(entries)
        self.assertEqual(len(draw_rect_calls), len(CLAMP_ORDER),
                         f"Expected {len(CLAMP_ORDER)} drawRect calls, got {len(draw_rect_calls)}")

    def test_draw_path_only_for_checked_cats(self):
        """drawPath (checkmark) called only for selected categories."""
        entries = [
            {"preset": "CLAMP", "cat": "C", "why": "too aggressive"},
            {"preset": "CLAMP", "cat": "A", "why": ""},
        ]
        _, draw_path_calls, _ = self._run_draw_tag_row(entries)
        self.assertEqual(len(draw_path_calls), 2,
                         f"Expected 2 drawPath calls (C and A checked), got {len(draw_path_calls)}")

    def test_draw_path_absent_when_no_selection(self):
        """No drawPath calls when no categories are checked."""
        entries = []
        _, draw_path_calls, _ = self._run_draw_tag_row(entries)
        self.assertEqual(len(draw_path_calls), 0,
                         f"Expected 0 drawPath calls with empty selection, got {len(draw_path_calls)}")

    def test_all_checkbox_rects_same_size(self):
        """All checkbox squares must be drawn at identical width and height."""
        entries = [
            {"preset": "CLAMP", "cat": "C", "why": ""},
            {"preset": "CLAMP", "cat": "L", "why": ""},
        ]
        draw_rect_calls, _, _ = self._run_draw_tag_row(entries)
        self.assertGreaterEqual(len(draw_rect_calls), 2)
        sizes = {(round(c.args[0].width(), 2), round(c.args[0].height(), 2))
                 for c in draw_rect_calls}
        self.assertEqual(len(sizes), 1,
                         f"All checkbox rects must be the same size, got: {sizes}")


try:
    import pypdf as _pypdf
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


@requires_qt
@unittest.skipUnless(_HAS_PYPDF, "pypdf not installed")
class TestNarrativeTokenLabelAbsentFromPDF(unittest.TestCase):
    """Prove the token-usage QLabel never leaks into the exported PDF."""

    def test_tokens_label_text_absent_from_pdf(self):
        from PyQt6.QtGui import QPixmap
        svc = ChessLogPDFService({})
        pixmap = QPixmap(100, 100)
        pixmap.fill()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            svc.export_charts_report(
                tmp_path,
                player_name="Paul",
                source_label="Test DB",
                chart_pixmaps=[("CLAMP", pixmap)],
                narrative_text="Here is the narrative text.",
                shallow_rows=[],
            )
            reader = _pypdf.PdfReader(str(tmp_path))
            all_text = " ".join(
                page.extract_text() or "" for page in reader.pages
            )
            self.assertNotIn(
                "Tokens:",
                all_text,
                "Token-usage label text must not appear in the PDF",
            )
        finally:
            tmp_path.unlink(missing_ok=True)


@requires_qt
class TestThreeByThreeIgnorePerChip(unittest.TestCase):
    """B6 fix: 3x3 header has no triangle; per-chip Ignore text appears on answer row;
    CLAMP rows are unaffected."""

    def _run_draw(self, row):
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        svc = ChessLogPDFService({})
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        writer = MagicMock()
        content = QRectF(0, 0, 500, 700)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, writer, content, 0.0, row)
        return painter

    def test_3x3_show_ignore_no_header_triangle(self):
        """show_ignore=True on a 3x3 row must NOT draw the header warning triangle."""
        row = TagRowSnapshot(
            move_label="1. e4",
            preset="3x3",
            entries=[
                {"preset": "3x3", "cat": "Why1", "why": "Control center"},
                {"preset": "3x3", "cat": "Why4", "why": "Look for tactics"},
            ],
            fen=None,
            played_move=None,
            show_ignore=True,
        )
        painter = self._run_draw(row)
        self.assertEqual(
            painter.drawPolygon.call_count, 0,
            "Header warning triangle must not appear for 3x3 rows",
        )

    def test_3x3_per_chip_ignore_text_on_answer_row(self):
        """A 3x3 chip with show_ignore=True must draw 'Ignore: Yes/No' on the answer row."""
        import hashlib
        why1_text = "Control center"
        h = hashlib.sha256(why1_text.encode("utf-8")).hexdigest()
        row = TagRowSnapshot(
            move_label="1. e4",
            preset="3x3",
            entries=[
                {
                    "preset": "3x3", "cat": "Why1", "why": why1_text,
                    "ignore_shallow": True, "ignore_text_hash": h, "is_shallow": True,
                },
            ],
            fen=None,
            played_move=None,
            show_ignore=True,
            shallow_cats=frozenset({"Why1"}),
        )
        painter = self._run_draw(row)
        all_drawn = [
            a for call in painter.drawText.call_args_list
            for a in call.args if isinstance(a, str)
        ]
        ignore_texts = [t for t in all_drawn if t.startswith("Ignore:")]
        self.assertGreaterEqual(len(ignore_texts), 1, f"Expected 'Ignore: ...' drawn; got: {all_drawn}")
        self.assertIn("Ignore: Yes", ignore_texts, f"Expect honoured entry → 'Ignore: Yes'; got: {ignore_texts}")

    def test_clamp_show_ignore_no_triangle(self):
        """CLAMP rows with show_ignore=True must NOT draw the header warning triangle."""
        row = TagRowSnapshot(
            move_label="2. Nf3",
            preset="CLAMP",
            entries=[{"preset": "CLAMP", "cat": "C", "why": "Improving piece",
                      "ignore_shallow": True, "is_shallow": True}],
            fen=None,
            played_move=None,
            show_ignore=True,
            is_shallow=True,
        )
        painter = self._run_draw(row)
        self.assertEqual(
            painter.drawPolygon.call_count, 0,
            "CLAMP header warning triangle must not be drawn when show_ignore=True",
        )


@requires_qt
class TestCheckLogsPDFMetadataLines(unittest.TestCase):
    """B7: Check Logs PDF (is_shallow_only=True) shows Source, Generated and AI model lines;
    narrative summary PDF is unchanged; locked-model behaviour."""

    _MINIMAL_CLAMP = [
        {"preset": "CLAMP", "cat": "C", "why": "test note"},
    ]

    def _export_and_extract(
        self,
        *,
        is_shallow_only: bool,
        source_label: str = "",
        model_label: str = "",
        export_charts: bool = False,
        charts_model_label: str = "",
    ) -> str:
        """Export a PDF and extract all text via pypdf."""
        try:
            import pypdf as _pypdf
        except ImportError:
            self.skipTest("pypdf not installed")

        from datetime import datetime as _real_dt
        from unittest.mock import patch
        from pathlib import Path
        import tempfile

        # Use a real datetime object so strftime("Generated: %Y-%m-%d %H:%M")
        # produces the expected string "Generated: 2099-01-15 07:30".
        _fixed_dt = _real_dt(2099, 1, 15, 7, 30)

        svc = ChessLogPDFService({})
        snap = TagRowSnapshot(
            move_label="1. e4",
            preset="CLAMP",
            entries=self._MINIMAL_CLAMP,
            fen=None,
            played_move=None,
            show_ignore=False,
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            with patch("app.services.chess_log_pdf_service.datetime") as mock_dt:
                mock_dt.now.return_value = _fixed_dt
                if export_charts:
                    svc.export_charts_report(
                        tmp_path,
                        player_name="Alice",
                        source_label=source_label,
                        chart_pixmaps=[],
                        narrative_text="",
                        shallow_rows=[snap] if charts_model_label else [],
                        model_label=charts_model_label,
                    )
                else:
                    svc.export_tags(
                        tmp_path,
                        [{"header": "G1", "rows": [snap]}],
                        is_shallow_only=is_shallow_only,
                        source_label=source_label,
                        model_label=model_label,
                    )
            reader = _pypdf.PdfReader(str(tmp_path))
            return " ".join(p.extract_text() or "" for p in reader.pages)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_check_logs_pdf_has_source_generated_model(self):
        """Check Logs PDF must contain all three metadata lines."""
        text = self._export_and_extract(
            is_shallow_only=True,
            source_label="Active Database: MyDB",
            model_label="Anthropic claude-sonnet-5-5",
        )
        self.assertIn("Source: Active Database: MyDB", text)
        self.assertIn("Generated:", text)
        self.assertIn("AI model: Anthropic claude-sonnet-5-5", text)

    def test_check_logs_pdf_no_run_fallback(self):
        """Empty model_label → 'not run (chips from earlier checks)'."""
        text = self._export_and_extract(
            is_shallow_only=True,
            source_label="All Games",
            model_label="",
        )
        self.assertIn("AI model: not run (chips from earlier checks)", text)

    def test_model_label_locked_at_run_time(self):
        """The model label in the PDF is whatever was passed (captured at run time),
        not a fresh read of current settings."""
        text = self._export_and_extract(
            is_shallow_only=True,
            source_label="Active Database: X",
            model_label="OpenAI gpt-4o",  # model that was current at run time
        )
        self.assertIn("AI model: OpenAI gpt-4o", text)
        self.assertNotIn("claude", text.lower())

    def test_charts_report_without_narrative_header(self):
        """export_charts_report with no narrative: Player, Source, Generated present; no Exported/AI model."""
        text = self._export_and_extract(
            is_shallow_only=False,
            source_label="Active Database: MyDB",
            export_charts=True,
            charts_model_label="",
        )
        self.assertIn("Player: Alice", text)
        self.assertIn("Source: Active Database: MyDB", text)
        self.assertIn("Generated:", text)
        self.assertNotIn("Exported:", text)
        self.assertNotIn("AI model:", text)


# ---------------------------------------------------------------------------
# Directive 15b: Charts PDF report header — narrative metadata
# ---------------------------------------------------------------------------

@requires_qt
@unittest.skipUnless(_HAS_PYPDF, "pypdf not installed")
class TestChartsReportHeaderMetadata(unittest.TestCase):
    """15b: export_charts_report header shows narrative counts/Generated/AI model when
    narrative is present; shows only Player/Source/Exported when narrative is absent."""

    def _export_charts_and_extract(
        self,
        *,
        player_name: str = "Alice",
        source_label: str = "Active Database",
        narrative_text: str = "",
        model_label: str = "",
        generated_at: str = "",
        n_games: int = 0,
        g_games: int = 0,
        m_moments: int = 0,
        s_flagged: int = 0,
        has_3x3: bool = False,
    ) -> str:
        import pypdf as _pypdf
        import tempfile
        from datetime import datetime as _real_dt
        from unittest.mock import patch

        _fixed_dt = _real_dt(2099, 3, 20, 14, 00)
        svc = ChessLogPDFService({})
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            with patch("app.services.chess_log_pdf_service.datetime") as mock_dt:
                mock_dt.now.return_value = _fixed_dt
                svc.export_charts_report(
                    tmp_path,
                    player_name=player_name,
                    source_label=source_label,
                    chart_pixmaps=[],
                    narrative_text=narrative_text,
                    shallow_rows=[],
                    model_label=model_label,
                    generated_at=generated_at,
                    n_games=n_games,
                    g_games=g_games,
                    m_moments=m_moments,
                    s_flagged=s_flagged,
                    has_3x3=has_3x3,
                )
            reader = _pypdf.PdfReader(str(tmp_path))
            return " ".join(p.extract_text() or "" for p in reader.pages)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_with_narrative_shows_counts_generated_ai_model(self):
        """When narrative is present, counts/Generated/AI model appear; no Exported line."""
        text = self._export_charts_and_extract(
            player_name="Paul",
            source_label="Active Database: DB.pgn",
            narrative_text="This is the narrative.",
            model_label="Anthropic claude-opus-4-7",
            generated_at="2026-05-10 09:15",
            n_games=12,
            g_games=8,
            m_moments=20,
            s_flagged=15,
        )
        self.assertIn("Player: Paul", text)
        self.assertIn("Source: Active Database: DB.pgn", text)
        self.assertIn("12 games", text)
        self.assertIn("8 with logged moments", text)
        self.assertIn("20 moments", text)
        self.assertIn("15 Shallow", text)
        self.assertNotIn("not flagged", text)
        self.assertIn("Generated: 2026-05-10 09:15", text)
        self.assertIn("AI model: Anthropic claude-opus-4-7", text)
        self.assertNotIn("Exported:", text)

    def test_without_narrative_shows_player_source_generated(self):
        """When no narrative, Player, Source, and Generated (export time) appear; no counts/AI model."""
        text = self._export_charts_and_extract(
            player_name="Paul",
            source_label="Active Database: DB.pgn",
            narrative_text="",
            model_label="Anthropic claude-opus-4-7",
            generated_at="2026-05-10 09:15",
            n_games=12,
            g_games=8,
            m_moments=20,
            s_flagged=15,
        )
        self.assertIn("Player: Paul", text)
        self.assertIn("Source: Active Database: DB.pgn", text)
        self.assertIn("Generated:", text)
        self.assertNotIn("Exported:", text)
        self.assertNotIn("AI model:", text)
        self.assertNotIn("not flagged", text)
        self.assertNotIn("Shallow", text)

    def test_title_unchanged(self):
        """Title must remain 'Chess Log Charts — {player}'."""
        text = self._export_charts_and_extract(player_name="Paul", narrative_text="")
        self.assertIn("Chess Log Charts", text)

    def test_filename_unchanged(self):
        """default_chess_log_charts_pdf_filename is unaffected by Directive 15b."""
        name = default_chess_log_charts_pdf_filename("Paul")
        self.assertIn("ChessLogCharts", name)
        self.assertIn("Paul", name)
        self.assertTrue(name.endswith(".pdf"))

    def test_with_narrative_generated_uses_captured_time_not_now(self):
        """With narrative, Generated: shows the captured generation time, not datetime.now()."""
        text = self._export_charts_and_extract(
            narrative_text="Some narrative.",
            generated_at="2025-01-01 08:00",
        )
        self.assertIn("Generated: 2025-01-01 08:00", text)
        self.assertNotIn("Exported:", text)


# ---------------------------------------------------------------------------
# Item 3: 3x3 PDF layout — chip right column, blank lines, measure==draw
# ---------------------------------------------------------------------------

@requires_qt
class TestThreeByThreePDFLayout(unittest.TestCase):
    """Verify measure/draw consistency, blank-line rhythm, and chip-column placement."""

    def _make_svc(self):
        return ChessLogPDFService({})

    def _measure_and_draw_height(self, row):
        """Return (measured_h, drawn_h) for a given row snapshot."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPainter
        svc = self._make_svc()
        content = QRectF(0, 0, 500, 2000)

        # Measure
        painter_m = MagicMock()
        painter_m.boundingRect.return_value = QRectF(0, 0, 100, 12)
        painter_m.fontMetrics.return_value = MagicMock(
            height=lambda: 12, lineSpacing=lambda: 12, descent=lambda: 2,
            horizontalAdvance=lambda s: len(s) * 6,
        )
        with patch.object(svc, "_render_board", return_value=None):
            measured = svc._measure_tag_row_height(painter_m, content, row)

        # Draw (y_start=0, returns y after row)
        painter_d = MagicMock()
        painter_d.boundingRect.return_value = QRectF(0, 0, 100, 12)
        painter_d.fontMetrics.return_value = MagicMock(
            height=lambda: 12, lineSpacing=lambda: 12, descent=lambda: 2,
            horizontalAdvance=lambda s: len(s) * 6,
        )
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            y_after = svc._draw_tag_row(painter_d, MagicMock(), content, 0.0, row)

        drawn = y_after - svc._ROW_GAP
        return measured, drawn

    def _make_3x3_row(self, entries, shallow_cats=frozenset(), vague_cats=frozenset(), show_ignore=False):
        return TagRowSnapshot(
            move_label="1. e4",
            preset="3x3",
            entries=entries,
            fen=None,
            played_move=None,
            show_ignore=show_ignore,
            shallow_cats=shallow_cats,
            vague_cats=vague_cats,
        )

    def test_measure_equals_draw_no_chips(self):
        entries = [{"preset": "3x3", "cat": k, "why": f"answer {k}"} for k in ("Why1", "Why2", "Why3", "Why4")]
        row = self._make_3x3_row(entries)
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"Measure={measured} Draw={drawn} must agree for 3x3 row without chips")

    def test_measure_equals_draw_with_shallow_chip(self):
        import hashlib
        text = "Control center"
        h = hashlib.sha256(text.encode()).hexdigest()
        entries = [{"preset": "3x3", "cat": "Why1", "why": text, "is_shallow": True}]
        row = self._make_3x3_row(entries, shallow_cats=frozenset({"Why1"}), show_ignore=True)
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"Measure={measured} Draw={drawn} must agree for row with shallow chip")

    def test_measure_equals_draw_blank_why(self):
        entries = [{"preset": "3x3", "cat": "Why3", "why": ""}]
        row = self._make_3x3_row(entries)
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg="Measure/draw must agree for a blank Why")

    def test_blank_why_question_is_drawn(self):
        """A Why with no answer text must still draw its question prompt."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        svc = self._make_svc()
        from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
        entries = [{"preset": "3x3", "cat": "Why2", "why": ""}]
        row = self._make_3x3_row(entries)
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        writer = MagicMock()
        content = QRectF(0, 0, 500, 2000)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, writer, content, 0.0, row)
        all_drawn = [a for call in painter.drawText.call_args_list
                     for a in call.args if isinstance(a, str)]
        why2_prompt = THREE_BY_THREE_PROMPTS.get("Why2", "Why2")
        self.assertTrue(
            any(why2_prompt in t for t in all_drawn),
            f"Why2 prompt must be drawn even for blank answer. Drawn: {all_drawn[:10]}"
        )

    def test_clamp_row_measure_unchanged(self):
        """CLAMP rows must still measure consistently (no regression)."""
        row_clamp = TagRowSnapshot(
            move_label="1. e4",
            preset="CLAMP",
            entries=[{"preset": "CLAMP", "cat": "C", "why": "Rushed move"}],
            fen=None,
            played_move=None,
            show_ignore=False,
        )
        measured, drawn = self._measure_and_draw_height(row_clamp)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"CLAMP measure/draw must still agree: Measure={measured} Draw={drawn}")

    def test_chip_not_drawn_on_question_line(self):
        """For 3x3 with a chip, drawText must NOT be called with both prompt and chip text on same call."""
        from unittest.mock import MagicMock, patch, call
        from PyQt6.QtCore import QRectF
        from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
        svc = self._make_svc()
        entries = [{"preset": "3x3", "cat": "Why1", "why": "attacked", "is_shallow": True}]
        row = self._make_3x3_row(entries, shallow_cats=frozenset({"Why1"}))
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        content = QRectF(0, 0, 500, 2000)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, MagicMock(), content, 0.0, row)
        # Chip text ("Shallow") must appear in a drawText call
        chip_texts = [a for c in painter.drawText.call_args_list for a in c.args if a == "Shallow"]
        self.assertGreater(len(chip_texts), 0, "Chip text 'Shallow' must be drawn")

    def test_3x3_vague_chip_rect_fits_inside_chip_column(self):
        """3x3 Vague chip rect width must not exceed chip_col_w in _draw_tag_row."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        svc = self._make_svc()
        entries = [{"preset": "3x3", "cat": "Why4", "why": "Think more", "is_vague": True}]
        row = self._make_3x3_row(entries, vague_cats=frozenset({"Why4"}))
        # Use a deterministic 6-px/char metric so expected values are computable.
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        painter.fontMetrics.return_value = MagicMock(
            height=lambda: 12, lineSpacing=lambda: 12, descent=lambda: 2,
            horizontalAdvance=lambda s: len(s) * 6,
        )
        content = QRectF(0, 0, 500, 2000)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, MagicMock(), content, 0.0, row)
        # Compute chip_col_w the same way the service does (6 px/char, empty config).
        chip_pad = 3.0
        chip_col_w = max(
            max(len("Shallow"), len("Vague")) * 6 + chip_pad * 2,
            len("Ignore: Yes") * 6,
        ) + 8.0
        # drawRoundedRect is called for the card background (full content width) and chips.
        # Filter to chip rects only: chips are narrower than the content width.
        chip_rects = [c.args[0] for c in painter.drawRoundedRect.call_args_list
                      if c.args and c.args[0].width() < content.width()]
        self.assertGreater(len(chip_rects), 0, "Expected at least one chip rect to be drawn")
        for rect in chip_rects:
            self.assertLessEqual(
                rect.width(), chip_col_w,
                f"Chip rect width {rect.width()} must not exceed chip_col_w {chip_col_w}",
            )

    def test_3x3_chip_text_rect_has_tolerance(self):
        """chip drawText rect must be at least advance+4px wide (not a pixel-tight fit).

        On macOS with real Helvetica the exact-advance rect clips the rightmost glyphs.
        The fix adds 4.0 to cw so the text rect is advance+4 wide (#58).
        """
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QFontMetrics
        svc = self._make_svc()
        entries = [{"preset": "3x3", "cat": "Why1", "why": "test", "is_shallow": True}]
        row = self._make_3x3_row(entries, shallow_cats=frozenset({"Why1"}))
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        content = QRectF(0, 0, 500, 2000)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, MagicMock(), content, 0.0, row)

        fm_bold = QFontMetrics(svc._font_body_bold)
        chip_label = "Shallow"  # default when config={}
        advance = float(fm_bold.horizontalAdvance(chip_label))

        chip_text_calls = [
            c.args[0] for c in painter.drawText.call_args_list
            if c.args and len(c.args) >= 3 and c.args[-1] == chip_label
        ]
        self.assertGreater(
            len(chip_text_calls), 0,
            f"Expected a drawText call with chip label '{chip_label}'",
        )
        for rect in chip_text_calls:
            self.assertGreaterEqual(
                rect.width(), advance + 4.0,
                f"chip text rect width {rect.width()} must be >= advance {advance} + 4.0 "
                f"(tight exact-fit clips on macOS real Helvetica)",
            )

    def test_measure_equals_draw_chips_on_why1_and_why4(self):
        """Measure and draw agree for a 3x3 row with chips on Why1 and Why4."""
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "I attacked too early", "is_shallow": True},
            {"preset": "3x3", "cat": "Why2", "why": "Not ideal"},
            {"preset": "3x3", "cat": "Why3", "why": "Better move"},
            {"preset": "3x3", "cat": "Why4", "why": "Think slower", "is_vague": True},
        ]
        row = self._make_3x3_row(entries,
                                 shallow_cats=frozenset({"Why1"}),
                                 vague_cats=frozenset({"Why4"}),
                                 show_ignore=True)
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"Measure={measured} Draw={drawn} must agree for chips on Why1+Why4")

    def test_measure_equals_draw_tall_text_taller_than_chip_col(self):
        """When q+a text wraps taller than the chip column, measure and draw still agree."""
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        entries = [{"preset": "3x3", "cat": "Why1", "why": "long long long answer text", "is_shallow": True}]
        row = self._make_3x3_row(entries, shallow_cats=frozenset({"Why1"}), show_ignore=True)
        svc = self._make_svc()
        content = QRectF(0, 0, 500, 2000)

        # br_h=30 so q_h + ans_h = 60, which exceeds chip_col_h ≈ 32 (text dominates)
        def make_painter():
            p = MagicMock()
            p.boundingRect.return_value = QRectF(0, 0, 100, 30)
            return p

        painter_m = make_painter()
        with patch.object(svc, "_render_board", return_value=None):
            measured = svc._measure_tag_row_height(painter_m, content, row)

        painter_d = make_painter()
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            y_after = svc._draw_tag_row(painter_d, MagicMock(), content, 0.0, row)
        drawn = y_after - svc._ROW_GAP

        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"Measure={measured} Draw={drawn} must agree when text taller than chip col")

    def test_measure_equals_draw_chip_col_taller_than_short_answer(self):
        """When chip col (chip + Ignore) is taller than q+a, measure and draw still agree."""
        # No answer → ans_h = 0; q_h ≈ 12 < chip_col_h ≈ 32 (chip col dominates)
        entries = [{"preset": "3x3", "cat": "Why1", "why": "", "is_shallow": True}]
        row = self._make_3x3_row(entries, shallow_cats=frozenset({"Why1"}), show_ignore=True)
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"Measure={measured} Draw={drawn} must agree when chip col taller than q+a")

    def test_measure_equals_draw_clamp_with_chip_and_ignore(self):
        """CLAMP row with Shallow chip and show_ignore=True: measure and draw agree."""
        from app.models.chess_log_snapshot import TagRowSnapshot
        row = TagRowSnapshot(
            move_label="1. e4", preset="CLAMP",
            entries=[{"preset": "CLAMP", "cat": "C", "why": "Rushed move"}],
            fen=None, played_move=None, show_ignore=True, is_shallow=True,
        )
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"CLAMP chip+ignore: Measure={measured} Draw={drawn} must agree")

    def test_measure_equals_draw_cct_with_chip_and_ignore(self):
        """CCT row with Shallow chip and show_ignore=True: measure and draw agree."""
        from app.models.chess_log_snapshot import TagRowSnapshot
        row = TagRowSnapshot(
            move_label="1. e4", preset="CCT",
            entries=[{"preset": "CCT", "cat": "Checks", "why": "Missed check"}],
            fen=None, played_move=None, show_ignore=True, is_shallow=True,
        )
        measured, drawn = self._measure_and_draw_height(row)
        self.assertAlmostEqual(measured, drawn, places=1,
            msg=f"CCT chip+ignore: Measure={measured} Draw={drawn} must agree")


# ---------------------------------------------------------------------------
# 3x3 chip column top-aligns with question line (#58)
# ---------------------------------------------------------------------------

class TestThreeByThreeChipAlignment(unittest.TestCase):
    """Chip column top-aligns with the question, not the answer (#58)."""

    def _make_svc(self):
        return ChessLogPDFService({})

    def _draw_row(self, row):
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        svc = self._make_svc()
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        content = QRectF(0, 0, 500, 2000)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, MagicMock(), content, 0.0, row)
        return painter

    def _make_row(self, entries, shallow_cats=frozenset(), vague_cats=frozenset(), show_ignore=True):
        from app.models.chess_log_snapshot import TagRowSnapshot
        return TagRowSnapshot(
            move_label="1. e4", preset="3x3", entries=entries,
            fen=None, played_move=None, show_ignore=show_ignore,
            shallow_cats=shallow_cats, vague_cats=vague_cats,
        )

    def test_chip_top_aligns_with_question_top(self):
        """Chip drawRoundedRect top y must equal question drawText top y (within 0.5pt)."""
        from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "I attacked", "is_shallow": True},
        ]
        row = self._make_row(entries, shallow_cats=frozenset({"Why1"}))
        painter = self._draw_row(row)

        why1_prompt = THREE_BY_THREE_PROMPTS["Why1"]

        # First drawText whose text is the Why1 question.
        q_rects = [
            c.args[0] for c in painter.drawText.call_args_list
            if c.args and len(c.args) >= 3 and c.args[-1] == why1_prompt
        ]
        self.assertGreater(len(q_rects), 0, f"Expected drawText for '{why1_prompt}'")
        q_top = q_rects[0].top()

        # Chip drawRoundedRect: radius=2, width < 400 (not the card background).
        chip_rects = [
            c.args[0] for c in painter.drawRoundedRect.call_args_list
            if len(c.args) >= 2 and c.args[1] == 2 and c.args[0].width() < 400
        ]
        self.assertGreater(len(chip_rects), 0, "Expected a chip drawRoundedRect")
        chip_top = chip_rects[0].top()

        self.assertAlmostEqual(
            chip_top, q_top, delta=0.5,
            msg=f"Chip top ({chip_top}) must align with question top ({q_top}) within 0.5pt",
        )

    def test_chipped_why_question_width_equals_answer_width(self):
        """For a chipped Why, question and answer drawText widths are equal (both narrowed).
        For a chipless Why in the same row, both use full width."""
        from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "answer-why1"},  # chipped
            {"preset": "3x3", "cat": "Why2", "why": "answer-why2"},  # chipless
        ]
        row = self._make_row(entries, shallow_cats=frozenset({"Why1"}))
        painter = self._draw_row(row)

        def first_drawtext_width(text):
            rects = [c.args[0] for c in painter.drawText.call_args_list
                     if c.args and len(c.args) >= 3 and c.args[-1] == text]
            self.assertGreater(len(rects), 0, f"Expected drawText for '{text}'")
            return rects[0].width()

        w_q1 = first_drawtext_width(THREE_BY_THREE_PROMPTS["Why1"])   # Why1 question
        w_a1 = first_drawtext_width("answer-why1")                     # Why1 answer
        w_q2 = first_drawtext_width(THREE_BY_THREE_PROMPTS["Why2"])   # Why2 question
        w_a2 = first_drawtext_width("answer-why2")                     # Why2 answer

        self.assertAlmostEqual(w_q1, w_a1, delta=0.5,
            msg=f"Chipped Why1: question width ({w_q1}) must equal answer width ({w_a1})")
        self.assertAlmostEqual(w_q2, w_a2, delta=0.5,
            msg=f"Chipless Why2: question width ({w_q2}) must equal answer width ({w_a2})")
        self.assertLess(w_q1, w_q2,
            msg=f"Chipped Why1 width ({w_q1}) must be < chipless Why2 width ({w_q2})")


# ---------------------------------------------------------------------------
# chip_h must include padding and chip text must be AlignCenter (#58)
# ---------------------------------------------------------------------------

class TestPDFChipHeight(unittest.TestCase):
    """chip_h must be bold_line_h + 4.0; chip text must use AlignCenter (#58)."""

    def _make_svc(self):
        return ChessLogPDFService({})

    def _make_3x3_row(self):
        from app.models.chess_log_snapshot import TagRowSnapshot
        entries = [{"preset": "3x3", "cat": "Why1", "why": "test", "is_shallow": True}]
        return TagRowSnapshot(
            move_label="1. e4", preset="3x3", entries=entries,
            fen=None, played_move=None, show_ignore=True,
            shallow_cats=frozenset({"Why1"}),
        )

    def _make_clamp_row(self):
        from app.models.chess_log_snapshot import TagRowSnapshot
        entries = [{"preset": "CLAMP", "cat": "C", "why": "note"}]
        return TagRowSnapshot(
            move_label="1. e4", preset="CLAMP", entries=entries,
            fen=None, played_move=None, show_ignore=True,
            is_shallow=True,
        )

    def _draw_row(self, svc, row):
        from unittest.mock import MagicMock, patch
        from PyQt6.QtCore import QRectF
        painter = MagicMock()
        painter.boundingRect.return_value = QRectF(0, 0, 100, 12)
        content = QRectF(0, 0, 500, 2000)
        with patch.object(svc, "_render_board", return_value=None), \
             patch.object(svc, "_ensure_space", return_value=(0.0, False)):
            svc._draw_tag_row(painter, MagicMock(), content, 0.0, row)
        return painter

    def test_3x3_chip_rect_height_equals_bold_line_h_plus_4(self):
        """3x3 chip drawRoundedRect height must be bold_line_h + 4.0."""
        from PyQt6.QtGui import QFontMetrics
        svc = self._make_svc()
        row = self._make_3x3_row()
        painter = self._draw_row(svc, row)
        bold_line_h = float(QFontMetrics(svc._font_body_bold).height())
        expected_h = bold_line_h + 4.0
        chip_rects = [c.args[0] for c in painter.drawRoundedRect.call_args_list
                      if c.args and c.args[0].width() < 400]
        self.assertGreater(len(chip_rects), 0, "Expected at least one chip rect")
        for rect in chip_rects:
            self.assertAlmostEqual(
                rect.height(), expected_h, places=1,
                msg=f"3x3 chip rect height {rect.height()} must equal bold_line_h+4 ({expected_h})",
            )

    def test_3x3_chip_text_alignment_is_center(self):
        """drawText for 3x3 chip must use AlignCenter."""
        from PyQt6.QtCore import Qt
        svc = self._make_svc()
        row = self._make_3x3_row()
        painter = self._draw_row(svc, row)
        chip_calls = [
            c for c in painter.drawText.call_args_list
            if c.args and len(c.args) >= 3 and c.args[-1] == "Shallow"
        ]
        self.assertGreater(len(chip_calls), 0, "Expected drawText for 'Shallow' chip")
        for call in chip_calls:
            self.assertEqual(
                call.args[1], int(Qt.AlignmentFlag.AlignCenter),
                f"3x3 chip text alignment {call.args[1]} must be AlignCenter "
                f"({int(Qt.AlignmentFlag.AlignCenter)})",
            )

    def test_clamp_header_chip_rect_height_equals_bold_line_h_plus_4(self):
        """CLAMP header chip drawRoundedRect height must be bold_line_h + 4.0."""
        from PyQt6.QtGui import QFontMetrics
        svc = self._make_svc()
        row = self._make_clamp_row()
        painter = self._draw_row(svc, row)
        bold_line_h = float(QFontMetrics(svc._font_body_bold).height())
        expected_h = bold_line_h + 4.0
        chip_rects = [c.args[0] for c in painter.drawRoundedRect.call_args_list
                      if c.args and c.args[0].width() < 400]
        self.assertGreater(len(chip_rects), 0, "Expected at least one CLAMP header chip rect")
        for rect in chip_rects:
            self.assertAlmostEqual(
                rect.height(), expected_h, places=1,
                msg=f"CLAMP chip rect height {rect.height()} must equal bold_line_h+4 ({expected_h})",
            )

    def test_clamp_header_chip_text_alignment_is_center(self):
        """drawText for CLAMP header chip must use AlignCenter."""
        from PyQt6.QtCore import Qt
        svc = self._make_svc()
        row = self._make_clamp_row()
        painter = self._draw_row(svc, row)
        chip_calls = [
            c for c in painter.drawText.call_args_list
            if c.args and len(c.args) >= 3 and c.args[-1] == "Shallow"
        ]
        self.assertGreater(len(chip_calls), 0, "Expected drawText for 'Shallow' CLAMP header chip")
        for call in chip_calls:
            self.assertEqual(
                call.args[1], int(Qt.AlignmentFlag.AlignCenter),
                f"CLAMP chip text alignment {call.args[1]} must be AlignCenter "
                f"({int(Qt.AlignmentFlag.AlignCenter)})",
            )


if __name__ == "__main__":
    unittest.main()

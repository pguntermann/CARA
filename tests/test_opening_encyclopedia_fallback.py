"""Lookup fallback metadata when matched node is a content stub."""

from __future__ import annotations

from pathlib import Path

from app.services.opening_encyclopedia_service import OpeningEncyclopediaService


def _svc() -> OpeningEncyclopediaService:
    root = Path(__file__).resolve().parents[1]
    return OpeningEncyclopediaService(
        {
            "resources": {
                "encyclopedia_db_path": str(
                    root / "app/resources/encyclopedia/openings.db"
                )
            }
        }
    )


def test_ready_lookup_has_no_fallback() -> None:
    entry = _svc().lookup("Bird Opening")
    assert entry is not None
    assert entry.opening_id == "bird-opening"
    assert not entry.used_fallback


def test_pending_stub_falls_back_to_parent() -> None:
    entry = _svc().lookup("Bird Opening: Williams Gambit", "A03")
    assert entry is not None
    assert entry.used_fallback
    assert entry.opening_id == "bird-opening"
    assert entry.matched_content_state == "pending"
    assert entry.display_name == "Bird Opening"
    assert entry.matched_display_name and "Williams" in entry.matched_display_name


def test_skipped_stub_falls_back_to_parent() -> None:
    entry = _svc().lookup("Evans Gambit Declined", "C51")
    assert entry is not None
    assert entry.used_fallback
    assert entry.matched_content_state == "skipped"
    assert entry.opening_id == "evans-gambit"


def test_search_excludes_stubs() -> None:
    page = _svc().search("Williams Gambit", limit=50)
    assert all(r.opening_id != "bird-opening/williams-gambit" for r in page.results)

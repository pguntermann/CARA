"""Encyclopedia suffix specificity lookup and Nearest chip metadata."""

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


def test_colle_system_uses_colle_article_not_queens_pawn() -> None:
    entry = _svc().lookup("Queen's Pawn Game: Colle System", "D05")
    assert entry is not None
    assert entry.opening_id == "colle-system"
    assert entry.display_name == "Colle System"
    assert not entry.used_fallback
    assert entry.used_nearest


def test_queens_pawn_modern_uses_modern_defense() -> None:
    entry = _svc().lookup("Queen's Pawn: Modern", "A40")
    assert entry is not None
    assert entry.opening_id == "modern-defense"
    assert "Modern" in entry.display_name
    assert not entry.used_fallback
    assert entry.used_nearest


def test_multi_clause_in_family_deepens_to_ready_child() -> None:
    entry = _svc().lookup(
        "Italian Game: Giuoco Pianissimo, Italian Four Knights Variation", "C50"
    )
    assert entry is not None
    assert entry.opening_id == "giuoco-pianissimo/italian-four-knights"
    assert entry.display_name == "Giuoco Pianissimo: Italian Four Knights"
    assert not entry.used_fallback
    assert entry.used_nearest


def test_exact_ready_title_has_no_nearest() -> None:
    entry = _svc().lookup("Bird Opening")
    assert entry is not None
    assert entry.opening_id == "bird-opening"
    assert not entry.used_fallback
    assert not entry.used_nearest


def test_pending_stub_still_falls_back_not_nearest() -> None:
    entry = _svc().lookup("Evans Gambit Declined", "C51")
    assert entry is not None
    assert entry.used_fallback
    assert not entry.used_nearest

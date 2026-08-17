"""Encyclopedia suffix specificity lookup and Nearest chip metadata."""

from __future__ import annotations

from pathlib import Path

from app.services.opening_encyclopedia_service import (
    OpeningEncyclopediaService,
    _best_ready_preference,
    _extract_suffix_candidates,
)


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


def test_closed_grand_prix_uses_grand_prix_attack() -> None:
    entry = _svc().lookup(
        "Sicilian: Closed, Grand Prix, 3...e6 4.Nf3 d5", "B23"
    )
    assert entry is not None
    assert entry.opening_id == "sicilian-defense/grand-prix-attack"
    assert entry.display_name == "Sicilian Defense: Grand Prix Attack"
    assert not entry.used_fallback
    assert entry.used_nearest


def test_ready_nr_sibling_beats_suffix_clause() -> None:
    openings = {
        "sicilian-defense/closed": {
            "content_state": "ready",
            "summary": "closed",
            "family_id": "sicilian-defense",
        },
        "sicilian-defense/grand-prix-attack": {
            "content_state": "ready",
            "summary": "gpa",
            "family_id": "sicilian-defense",
        },
    }
    assert (
        _best_ready_preference(
            "sicilian-defense/closed",
            "sicilian-defense/grand-prix-attack",
            openings,
        )
        == "sicilian-defense/grand-prix-attack"
    )


def test_suffix_child_still_deepens_past_ready_nr_parent() -> None:
    openings = {
        "sicilian-defense": {
            "content_state": "ready",
            "summary": "root",
            "family_id": None,
        },
        "sicilian-defense/closed": {
            "content_state": "ready",
            "summary": "closed",
            "family_id": "sicilian-defense",
        },
    }
    assert (
        _best_ready_preference(
            "sicilian-defense/closed",
            "sicilian-defense",
            openings,
        )
        == "sicilian-defense/closed"
    )


def test_cross_family_suffix_still_beats_ready_nr() -> None:
    openings = {
        "colle-system": {
            "content_state": "ready",
            "summary": "colle",
            "family_id": None,
        },
        "queens-pawn-game": {
            "content_state": "ready",
            "summary": "qp",
            "family_id": None,
        },
    }
    assert (
        _best_ready_preference("colle-system", "queens-pawn-game", openings)
        == "colle-system"
    )


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


def test_move_suffix_stays_a_candidate_but_is_family_scoped() -> None:
    parts = [text for text, _rank in _extract_suffix_candidates("Mieses: 1...d5")]
    assert "Mieses: 1...d5" in parts
    assert "1...d5" in parts
    named = [text for text, _rank in _extract_suffix_candidates(
        "Queen's Pawn Game: Colle System"
    )]
    assert "Colle System" in named


def test_mieses_d5_does_not_resolve_to_amar() -> None:
    entry = _svc().lookup("Mieses: 1...d5", "A00")
    assert entry is not None
    assert entry.opening_id == "mieses-opening"
    assert entry.used_fallback
    assert entry.matched_opening_id == "mieses-opening/1-d5"
    assert "Amar" not in entry.display_name


def test_scandinavian_deep_line_uses_ready_qxd5_article() -> None:
    entry = _svc().lookup("Scandinavian: 2...Qxd5 3.Nc3 Qa5 4.d4", "B01")
    assert entry is not None
    assert entry.opening_id == "scandinavian-defense/2-qxd5"
    assert entry.display_name == "Scandinavian Defense: 2...Qxd5"
    assert not entry.used_fallback
    assert entry.used_nearest

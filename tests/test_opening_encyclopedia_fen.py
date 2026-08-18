"""Optional FEN identity hint must not replace or degrade name lookup."""

from __future__ import annotations

from pathlib import Path

from app.services.opening_encyclopedia_service import (
    OpeningEncyclopediaService,
    _prefer_name_then_fen_deepen,
)

# B45 Sicilian: Taimanov, Four Knights, 6.Nxc6 bxc6 7.e5 Nd5
_TAIMANOV_FOUR_KNIGHTS_FEN = (
    "r1bqkb1r/p2p1ppp/2p1p3/3nP3/8/2N5/PPP2PPP/R1BQKB1R w KQkq - 1 8"
)
_TAIMANOV_FOUR_KNIGHTS_NAME = (
    "Sicilian: Taimanov, Four Knights, 6.Nxc6 bxc6 7.e5 Nd5"
)
_MISS_FEN = "8/8/8/8/8/8/8/8 w - - 0 1"


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


def test_prefer_name_keeps_nr_sibling_over_fen_seed() -> None:
    assert (
        _prefer_name_then_fen_deepen(
            "sicilian-defense/four-knights",
            "sicilian-defense/taimanov",
        )
        == "sicilian-defense/four-knights"
    )


def test_prefer_name_deepens_to_fen_descendant() -> None:
    assert (
        _prefer_name_then_fen_deepen(
            "sicilian-defense",
            "sicilian-defense/four-knights",
        )
        == "sicilian-defense/four-knights"
    )


def test_prefer_name_fills_miss_from_fen() -> None:
    assert (
        _prefer_name_then_fen_deepen(None, "sicilian-defense/four-knights")
        == "sicilian-defense/four-knights"
    )


def test_taimanov_four_knights_name_only_is_four_knights() -> None:
    entry = _svc().lookup(_TAIMANOV_FOUR_KNIGHTS_NAME, "B45")
    assert entry is not None
    assert entry.opening_id == "sicilian-defense/four-knights"


def test_taimanov_four_knights_fen_does_not_replace_name() -> None:
    svc = _svc()
    name_only = svc.lookup(_TAIMANOV_FOUR_KNIGHTS_NAME, "B45")
    with_fen = svc.lookup(
        _TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN
    )
    assert name_only is not None and with_fen is not None
    assert name_only.opening_id == "sicilian-defense/four-knights"
    assert with_fen.opening_id == name_only.opening_id


def test_unknown_fen_does_not_change_name_lookup() -> None:
    svc = _svc()
    name_only = svc.lookup(_TAIMANOV_FOUR_KNIGHTS_NAME, "B45")
    with_miss = svc.lookup(_TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_MISS_FEN)
    assert name_only is not None and with_miss is not None
    assert with_miss.opening_id == name_only.opening_id


def test_fen_fills_empty_name_with_four_knights() -> None:
    entry = _svc().lookup("", "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN)
    assert entry is not None
    assert entry.opening_id == "sicilian-defense/four-knights"


def test_lookup_caches_repeated_results() -> None:
    svc = _svc()
    first = svc.lookup(
        _TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN
    )
    second = svc.lookup(
        _TAIMANOV_FOUR_KNIGHTS_NAME, "B45", fen=_TAIMANOV_FOUR_KNIGHTS_FEN
    )
    assert first is second
    assert (_TAIMANOV_FOUR_KNIGHTS_NAME, "B45", _TAIMANOV_FOUR_KNIGHTS_FEN) in svc._lookup_cache

"""Player-to-game matching helpers for Chess Log filtering."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.game_data import GameData


def game_matches_player_color(
    game: "GameData", player_cf: str, color_filter: str
) -> bool:
    """Return True iff game should be included for the given player + color filter.

    Args:
        game:         Game whose White/Black headers are checked.
        player_cf:    Casefolded, stripped player name. Empty string matches all games.
        color_filter: One of "white", "black", or "both" / any other value.
    """
    if not player_cf:
        return True
    white_cf = (game.white or "").casefold().strip()
    black_cf = (game.black or "").casefold().strip()
    is_white = player_cf == white_cf
    is_black = player_cf == black_cf
    if not (is_white or is_black):
        return False
    if color_filter == "white" and not is_white:
        return False
    if color_filter == "black" and not is_black:
        return False
    return True

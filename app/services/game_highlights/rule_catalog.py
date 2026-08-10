"""Built-in game highlight rule catalog (categories, labels, defaults).

Stable rule IDs match ``rule_type`` / registry config keys (snake_case).
User overrides are applied on top of these defaults at detection time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


PHASE_OPENING = "opening"
PHASE_MIDDLEGAME = "middlegame"
PHASE_ENDGAME = "endgame"
ALL_PHASES: Tuple[str, ...] = (PHASE_OPENING, PHASE_MIDDLEGAME, PHASE_ENDGAME)


def normalize_phases(phases: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """Normalize a phases sequence to the known ordered subset (non-empty → all)."""
    if not phases:
        return ALL_PHASES
    allowed = set(ALL_PHASES)
    ordered = tuple(p for p in ALL_PHASES if p in phases and p in allowed)
    return ordered if ordered else ALL_PHASES


def clamp_phases(
    phases: Optional[Sequence[str]],
    applicable: Sequence[str],
) -> Tuple[str, ...]:
    """Intersect ``phases`` with ``applicable``, preserving catalog order.

    Empty intersection falls back to the full applicable set so a rule always
    keeps at least one runnable phase.
    """
    applicable_ordered = normalize_phases(applicable)
    if not phases:
        return applicable_ordered
    wanted = set(phases)
    ordered = tuple(p for p in applicable_ordered if p in wanted)
    return ordered if ordered else applicable_ordered


@dataclass(frozen=True)
class RuleCategory:
    """Display grouping for highlight rules."""

    id: str
    label: str
    sort_order: int


@dataclass(frozen=True)
class BuiltinRuleMeta:
    """Metadata for a built-in highlight rule.

    ``applicable_phases`` is the hard ceiling of phases where the rule can fire
    (logic / chess sense). ``default_phases`` is the user's default enablement
    and is always clamped to ``applicable_phases``.
    """

    id: str
    display_name: str
    description: str
    category_id: str
    default_priority: int
    default_enabled: bool = True
    applicable_phases: Tuple[str, ...] = ALL_PHASES
    default_phases: Tuple[str, ...] = ALL_PHASES

    def __post_init__(self) -> None:
        applicable = normalize_phases(self.applicable_phases)
        object.__setattr__(self, "applicable_phases", applicable)
        object.__setattr__(
            self,
            "default_phases",
            clamp_phases(self.default_phases, applicable),
        )


CATEGORIES: Tuple[RuleCategory, ...] = (
    RuleCategory("tactics", "Tactics", 10),
    RuleCategory("strategy", "Strategy", 20),
    RuleCategory("game_flow", "Game flow", 30),
    RuleCategory("material", "Material & exchanges", 40),
    RuleCategory("defense", "Defense", 50),
    RuleCategory("endgame", "Endgame themes", 60),
    RuleCategory("opening", "Opening & theory", 70),
)

_CATEGORY_BY_ID: Dict[str, RuleCategory] = {c.id: c for c in CATEGORIES}

# Default priority is the typical / primary emit priority used when the user
# customizes priority (variable-priority rules keep their internal values until
# the user overrides).
_MID_AND_END: Tuple[str, ...] = (PHASE_MIDDLEGAME, PHASE_ENDGAME)
_OPEN_AND_MID: Tuple[str, ...] = (PHASE_OPENING, PHASE_MIDDLEGAME)
_ENDGAME_ONLY: Tuple[str, ...] = (PHASE_ENDGAME,)

BUILTIN_RULES: Tuple[BuiltinRuleMeta, ...] = (
    # Tactics
    BuiltinRuleMeta(
        "forcing_combination",
        "Forcing combination",
        "A material sacrifice (not a quiet equal trade) that clearly improves the evaluation",
        "tactics",
        45,
    ),
    BuiltinRuleMeta(
        "tactical_resource",
        "Tactical resource",
        "A strong move that wins net material or creates a large lasting evaluation jump — not a quiet equal trade, a forced reply in a tactical sequence, merely taking a piece the opponent just hung on a blunder, or a plain capture of an undefended unit",
        "tactics",
        28,
    ),
    BuiltinRuleMeta(
        "captured_undefended_piece",
        "Captured undefended piece",
        "A good move that captures an enemy unit which had no defenders — cashing in a hang, not a deeper tactical resource",
        "tactics",
        26,
    ),
    BuiltinRuleMeta(
        "tactical_opportunity",
        "Missed tactical opportunity",
        "A mistake that misses a clearly tactical best move (capture, check, or mate)",
        "tactics",
        30,
    ),
    BuiltinRuleMeta(
        "tactical_sequence",
        "Tactical sequence",
        "A forcing multi-move capture sequence (reply near-forced, then at least one near-best continuation pair) that wins lasting evaluation — preferred over a plain tactical resource or forcing combination on the same start move",
        "tactics",
        42,
    ),
    BuiltinRuleMeta(
        "blundered_piece",
        "Blundered piece",
        "A queen or rook is left en prise by a serious error and taken on the next ply, with a lasting evaluation drop — not an equal trade or immediate recovery",
        "tactics",
        50,
    ),
    BuiltinRuleMeta(
        "delayed_mating",
        "Delayed mating",
        "Misses a forced mate (mate-in 5 or less), and does so again on a later move in the same phase",
        "tactics",
        55,
    ),
    BuiltinRuleMeta(
        "fork",
        "Fork",
        "One move attacks two or more enemy units at once in a way that wins material or forces a concession — not a hanging or easily traded forker",
        "tactics",
        45,
    ),
    BuiltinRuleMeta(
        "skewer",
        "Skewer",
        "A sliding piece lines up two enemy units so the more valuable one is in front, forcing material gain — distinct from a pin",
        "tactics",
        46,
    ),
    BuiltinRuleMeta(
        "pin",
        "Pin",
        "A sliding piece pins an enemy minor or major piece to a heavier unit behind it (usually the king), and the pin is new",
        "tactics",
        38,
    ),
    BuiltinRuleMeta(
        "discovered_attack",
        "Discovered attack",
        "A piece moves off a line and reveals a friendly rook, bishop, or queen attacking a valuable enemy unit (or giving check)",
        "tactics",
        45,
        applicable_phases=_MID_AND_END,
    ),
    BuiltinRuleMeta(
        "battery",
        "Battery",
        "Two friendly heavy pieces newly line up on a file, rank, or diagonal and the battery attacks an enemy piece on that line",
        "tactics",
        35,
        applicable_phases=_MID_AND_END,
    ),
    BuiltinRuleMeta(
        "doubled_on_open_file",
        "Doubled on open file",
        "A rook or queen newly doubles with another friendly heavy piece on a fully open file (no pawns of either side). Yields to battery when the same doubling also attacks an enemy piece on that file",
        "strategy",
        28,
        applicable_phases=_MID_AND_END,
    ),
    BuiltinRuleMeta(
        "decoy",
        "Decoy",
        "Offers a piece that the opponent takes, luring that unit onto a square where a follow-up tactic (fork, pin, skewer, or mate) appears",
        "tactics",
        45,
        applicable_phases=_MID_AND_END,
    ),
    BuiltinRuleMeta(
        "zwischenzug",
        "Zwischenzug",
        "An in-between move: instead of recapturing, a strong check or alternative capture is inserted first",
        "tactics",
        42,
    ),
    BuiltinRuleMeta(
        "interference",
        "Interference",
        "Places a piece between two enemy sliding pieces that previously saw each other, breaking their coordination",
        "tactics",
        38,
    ),
    BuiltinRuleMeta(
        "windmill",
        "Windmill",
        "The same side delivers at least three consecutive capturing checks, with the evaluation improving along the sequence",
        "tactics",
        47,
    ),
    BuiltinRuleMeta(
        "back_rank_weakness",
        "Back-rank weakness",
        "King stuck on its back rank with all forward escape squares blocked by its own pawns, while an enemy rook or queen sits on that same rank",
        "tactics",
        43,
    ),
    BuiltinRuleMeta(
        "exchange_sacrifice",
        "Exchange sacrifice",
        "Gives a rook for a knight or bishop, then the rook is taken back, while the evaluation does not collapse — positional compensation for the exchange",
        "tactics",
        36,
    ),
    BuiltinRuleMeta(
        "breakthrough_sacrifice",
        "Breakthrough sacrifice",
        "Gives up net material (not just an equal capture-recapture) without quickly winning it back, and the evaluation jumps in the sacrificer's favor after the opponent's reply",
        "tactics",
        44,
    ),
    # Strategy
    BuiltinRuleMeta(
        "bishop_pair",
        "Bishop pair",
        "A side ends up with both opposite-colored bishops while the opponent no longer has two, and the advantage is not immediately traded back",
        "strategy",
        32,
    ),
    BuiltinRuleMeta(
        "pawn_break",
        "Pawn break",
        "A central pawn capture that is not a simple pawn trade and opens a file or creates a passed pawn",
        "strategy",
        25,
    ),
    BuiltinRuleMeta(
        "pawn_storm",
        "Pawn storm",
        "Two adjacent flank pawns advance in a short window, staying coordinated and reaching the opponent's half of the board",
        "strategy",
        22,
        applicable_phases=_MID_AND_END,
    ),
    BuiltinRuleMeta(
        "centralization",
        "Centralization",
        "A knight, bishop, or queen moves from a non-central square onto a central square (c4–f5 / d4–e5 area), when the move is accurate (low CPL) or clearly improves the evaluation",
        "strategy",
        15,
    ),
    BuiltinRuleMeta(
        "positional_improvement",
        "Positional improvement",
        "A high-quality move that improves the evaluation without winning material, and without relying on an immediate opponent blunder",
        "strategy",
        25,
    ),
    BuiltinRuleMeta(
        "weak_square",
        "Weak square",
        "A good move that occupies an advanced square which enemy pawns cannot attack and which is defended by the mover's pieces",
        "strategy",
        23,
    ),
    BuiltinRuleMeta(
        "isolated_pawn",
        "Isolated pawn",
        "A pawn move leaves a friendly pawn with no neighboring pawns on adjacent files",
        "strategy",
        21,
    ),
    BuiltinRuleMeta(
        "knight_outpost",
        "Knight outpost",
        "A knight moves to an advanced square (not on the a/h files), supported by a friendly pawn, that enemy pawns cannot attack now or by advancing",
        "strategy",
        26,
    ),
    BuiltinRuleMeta(
        "rook_lift",
        "Rook lift",
        "A rook leaves the back ranks (White ranks 1–2, Black ranks 7–8) and advances toward the opponent, without worsening the evaluation",
        "strategy",
        24,
    ),
    BuiltinRuleMeta(
        "piece_coordination",
        "Piece coordination",
        "Two or more pieces attack the same valuable enemy unit (minor piece or greater, or the king) after a strong move",
        "strategy",
        33,
    ),
    BuiltinRuleMeta(
        "tempo_gain",
        "Tempo gain",
        "A useful move that creates a threat (check, or attacking a valuable enemy piece) and the opponent's inaccurate reply specifically answers that threat — not an unrelated mistake after a quiet attack",
        "strategy",
        32,
    ),
    # Game flow
    BuiltinRuleMeta(
        "initiative",
        "Initiative",
        "A high-quality move that improves the evaluation and forces a poor reply, keeping the advantage afterward",
        "game_flow",
        30,
    ),
    BuiltinRuleMeta(
        "momentum_shift",
        "Momentum shift",
        "The evaluation flips across equal by a meaningful amount and the new side keeps the advantage on a reasonably accurate consolidating move (crossing blunders are not credited)",
        "game_flow",
        45,
    ),
    BuiltinRuleMeta(
        "evaluation_swing",
        "Evaluation swing",
        "A high-quality move that changes the evaluation by a large amount without flipping who is better (best swing kept per side and phase)",
        "game_flow",
        30,
    ),
    BuiltinRuleMeta(
        "perpetual_check",
        "Perpetual check",
        "Three or more consecutive checks whose evaluations stay nearly flat — a draw by repetition is in the air",
        "game_flow",
        46,
    ),
    # Material
    BuiltinRuleMeta(
        "material_imbalance",
        "Material imbalance",
        "Unusual trades such as a rook for a minor piece (when not the engine's best move), or a minor piece credited against multiple pawns",
        "material",
        32,
    ),
    BuiltinRuleMeta(
        "exchange_sequence",
        "Exchange sequence",
        "Both sides capture a rook, or both capture a queen — a direct heavy-piece trade started by either side (evaluation may change)",
        "material",
        30,
    ),
    BuiltinRuleMeta(
        "simplification",
        "Simplification",
        "Both sides trade pieces of similar value off the board while the evaluation stays roughly the same — a quiet, even reduction of complexity",
        "material",
        22,
    ),
    BuiltinRuleMeta(
        "castling",
        "Castling",
        "A player performs a kingside 0-0 or queenside 0-0-0 castleing move",
        "material",
        15,
    ),
    # Defense
    BuiltinRuleMeta(
        "defensive_resource",
        "Defensive resource",
        "The only good defense against a real tactical threat — alternatives are clearly worse and the evaluation holds",
        "defense",
        20,
    ),
    BuiltinRuleMeta(
        "defensive_fortress",
        "Defensive fortress",
        "Holding a near-equal evaluation for several moves despite being down a significant amount of material",
        "defense",
        29,
    ),
    # Endgame themes
    BuiltinRuleMeta(
        "king_activity",
        "King activity",
        "In the endgame, the king advances toward the central ranks without worsening the evaluation",
        "endgame",
        27,
        applicable_phases=_ENDGAME_ONLY,
    ),
    BuiltinRuleMeta(
        "pawn_promotion_threat",
        "Pawn promotion threat",
        "A pawn advances onto the near-promotion ranks (6th/7th for White, 3rd/2nd for Black), is supported, and has a clear path forward on its file — not the promotion move itself",
        "endgame",
        40,
    ),
    BuiltinRuleMeta(
        "zugzwang",
        "Zugzwang",
        "Shown on the move that leaves the opponent to move with no good options in a simplified endgame: every top engine reply is bad and worsens the evaluation",
        "endgame",
        35,
        applicable_phases=_ENDGAME_ONLY,
    ),
    # Opening & theory
    BuiltinRuleMeta(
        "theory_departure",
        "Theory departure",
        "The first move after the opening book that is not the engine's best move — the moment the game leaves known theory",
        "opening",
        20,
        applicable_phases=_OPEN_AND_MID,
    ),
    BuiltinRuleMeta(
        "novelty",
        "Novelty",
        "A strong move (from move 7 on) that is not among the engine's top three choices — an original idea that still holds up in analysis",
        "opening",
        18,
    ),
)

_RULE_BY_ID: Dict[str, BuiltinRuleMeta] = {r.id: r for r in BUILTIN_RULES}


def list_categories() -> List[RuleCategory]:
    """Return categories ordered for display."""
    return sorted(CATEGORIES, key=lambda c: (c.sort_order, c.label))


def list_builtin_rules() -> List[BuiltinRuleMeta]:
    """Return built-in rules in catalog order."""
    return list(BUILTIN_RULES)


def get_rule_meta(rule_id: str) -> Optional[BuiltinRuleMeta]:
    """Return metadata for a rule id, or None if unknown."""
    return _RULE_BY_ID.get(rule_id)


def get_category(category_id: str) -> Optional[RuleCategory]:
    """Return a category by id."""
    return _CATEGORY_BY_ID.get(category_id)

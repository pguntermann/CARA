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


@dataclass(frozen=True)
class RuleCategory:
    """Display grouping for highlight rules."""

    id: str
    label: str
    sort_order: int


@dataclass(frozen=True)
class BuiltinRuleMeta:
    """Metadata for a built-in highlight rule."""

    id: str
    display_name: str
    description: str
    category_id: str
    default_priority: int
    default_enabled: bool = True
    default_phases: Tuple[str, ...] = ALL_PHASES


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
BUILTIN_RULES: Tuple[BuiltinRuleMeta, ...] = (
    # Tactics
    BuiltinRuleMeta(
        "forcing_combination",
        "Forcing combination",
        "Material sacrifices with forced responses",
        "tactics",
        45,
    ),
    BuiltinRuleMeta(
        "tactical_resource",
        "Tactical resource",
        "Strong tactical moves such as captures or clear improvements",
        "tactics",
        28,
    ),
    BuiltinRuleMeta(
        "tactical_opportunity",
        "Missed tactical opportunity",
        "Missed tactical chances",
        "tactics",
        30,
    ),
    BuiltinRuleMeta(
        "tactical_sequence",
        "Tactical sequence",
        "Multi-move tactical sequences",
        "tactics",
        42,
    ),
    BuiltinRuleMeta(
        "blundered_piece",
        "Blundered piece",
        "Blundered queens or rooks",
        "tactics",
        50,
    ),
    BuiltinRuleMeta(
        "delayed_mating",
        "Delayed mating",
        "Consecutive missed mate opportunities",
        "tactics",
        55,
    ),
    BuiltinRuleMeta("fork", "Fork", "Fork tactics", "tactics", 45),
    BuiltinRuleMeta("skewer", "Skewer", "Skewer tactics", "tactics", 40),
    BuiltinRuleMeta("pin", "Pin", "Pin tactics", "tactics", 38),
    BuiltinRuleMeta(
        "discovered_attack",
        "Discovered attack",
        "Discovered attacks",
        "tactics",
        45,
    ),
    BuiltinRuleMeta("battery", "Battery", "Battery formations", "tactics", 35),
    BuiltinRuleMeta("decoy", "Decoy", "Decoy tactics", "tactics", 45),
    BuiltinRuleMeta(
        "zwischenzug",
        "Zwischenzug",
        "In-between moves (zwischenzug)",
        "tactics",
        42,
    ),
    BuiltinRuleMeta(
        "interference",
        "Interference",
        "Interference tactics",
        "tactics",
        38,
    ),
    BuiltinRuleMeta(
        "windmill",
        "Windmill",
        "Windmill combinations",
        "tactics",
        47,
    ),
    BuiltinRuleMeta(
        "back_rank_weakness",
        "Back-rank weakness",
        "Back-rank weaknesses",
        "tactics",
        43,
    ),
    BuiltinRuleMeta(
        "exchange_sacrifice",
        "Exchange sacrifice",
        "Exchange sacrifices",
        "tactics",
        36,
    ),
    BuiltinRuleMeta(
        "breakthrough_sacrifice",
        "Breakthrough sacrifice",
        "Breakthrough sacrifices",
        "tactics",
        44,
    ),
    # Strategy
    BuiltinRuleMeta(
        "bishop_pair",
        "Bishop pair",
        "When the bishop pair is secured or gained",
        "strategy",
        32,
    ),
    BuiltinRuleMeta(
        "pawn_break",
        "Pawn break",
        "Central pawn breaks",
        "strategy",
        25,
    ),
    BuiltinRuleMeta(
        "pawn_storm",
        "Pawn storm",
        "Coordinated pawn advances on a flank",
        "strategy",
        22,
    ),
    BuiltinRuleMeta(
        "centralization",
        "Centralization",
        "Piece centralization",
        "strategy",
        15,
    ),
    BuiltinRuleMeta(
        "positional_improvement",
        "Positional improvement",
        "Positional improvements",
        "strategy",
        25,
    ),
    BuiltinRuleMeta(
        "weak_square",
        "Weak square",
        "Weak-square exploitation",
        "strategy",
        23,
    ),
    BuiltinRuleMeta(
        "isolated_pawn",
        "Isolated pawn",
        "Isolated pawn structures",
        "strategy",
        21,
    ),
    BuiltinRuleMeta(
        "knight_outpost",
        "Knight outpost",
        "Knight outposts",
        "strategy",
        26,
    ),
    BuiltinRuleMeta(
        "rook_lift",
        "Rook lift",
        "Rook lift maneuvers",
        "strategy",
        24,
    ),
    BuiltinRuleMeta(
        "piece_coordination",
        "Piece coordination",
        "Coordinated piece play",
        "strategy",
        33,
    ),
    BuiltinRuleMeta(
        "tempo_gain",
        "Tempo gain",
        "Tempo gains",
        "strategy",
        32,
    ),
    # Game flow
    BuiltinRuleMeta(
        "initiative",
        "Initiative",
        "When initiative is seized",
        "game_flow",
        30,
    ),
    BuiltinRuleMeta(
        "momentum_shift",
        "Momentum shift",
        "When advantage switches sides",
        "game_flow",
        45,
    ),
    BuiltinRuleMeta(
        "evaluation_swing",
        "Evaluation swing",
        "Large evaluation changes",
        "game_flow",
        30,
    ),
    BuiltinRuleMeta(
        "perpetual_check",
        "Perpetual check",
        "Perpetual check patterns",
        "game_flow",
        46,
    ),
    # Material
    BuiltinRuleMeta(
        "material_imbalance",
        "Material imbalance",
        "Unusual material trades",
        "material",
        32,
    ),
    BuiltinRuleMeta(
        "exchange_sequence",
        "Exchange sequence",
        "Queen or rook exchanges",
        "material",
        30,
    ),
    BuiltinRuleMeta(
        "simplification",
        "Simplification",
        "Simplifying trades",
        "material",
        22,
    ),
    BuiltinRuleMeta(
        "castling",
        "Castling",
        "Castling moves",
        "material",
        15,
    ),
    # Defense
    BuiltinRuleMeta(
        "defensive_resource",
        "Defensive resource",
        "Defensive moves when under threat",
        "defense",
        20,
    ),
    BuiltinRuleMeta(
        "defensive_fortress",
        "Defensive fortress",
        "Defensive fortress formations",
        "defense",
        29,
    ),
    # Endgame themes
    BuiltinRuleMeta(
        "king_activity",
        "King activity",
        "Active king play",
        "endgame",
        27,
    ),
    BuiltinRuleMeta(
        "pawn_promotion_threat",
        "Pawn promotion threat",
        "Pawn promotion threats",
        "endgame",
        40,
    ),
    BuiltinRuleMeta(
        "zugzwang",
        "Zugzwang",
        "Zugzwang positions",
        "endgame",
        35,
    ),
    # Opening & theory
    BuiltinRuleMeta(
        "theory_departure",
        "Theory departure",
        "Leaving opening theory",
        "opening",
        20,
    ),
    BuiltinRuleMeta(
        "novelty",
        "Novelty",
        "Strong moves outside the engine top choices",
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


def normalize_phases(phases: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """Normalize a phases sequence to the known ordered subset (non-empty → all)."""
    if not phases:
        return ALL_PHASES
    allowed = set(ALL_PHASES)
    ordered = tuple(p for p in ALL_PHASES if p in phases and p in allowed)
    return ordered if ordered else ALL_PHASES

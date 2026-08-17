"""Service for detecting error patterns in player performance."""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.models.database_model import GameData
from app.models.moveslist_model import MoveData
from app.services.game_summary_service import GameSummary, PlayerStatistics, PhaseStatistics
from app.controllers.game_controller import GameController
from app.services.opening_service import OpeningService
from app.services.missed_tactic_ranking import STATS_MISS_KIND_LABELS

COVERAGE_CUTOFF_MIN = 5.0
COVERAGE_CUTOFF_MAX = 95.0
COVERAGE_CUTOFF_DEFAULT = 25.0


def error_pattern_config_block(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the error-patterns config block (UI path, then top-level fallback)."""
    cfg = config if isinstance(config, dict) else {}
    top = (cfg.get("player_stats") or {}).get("error_patterns")
    if isinstance(top, dict) and top:
        return top
    ui_block = (
        ((cfg.get("ui") or {}).get("panels") or {})
        .get("detail", {})
        .get("player_stats", {})
        .get("error_patterns")
    )
    return ui_block if isinstance(ui_block, dict) else {}


def coverage_cutoff_range(config: Optional[Dict[str, Any]] = None) -> Tuple[float, float, float]:
    """Return ``(min, max, default)`` for the display-only coverage slider."""
    block = error_pattern_config_block(config)
    raw = block.get("coverage_cutoff")
    cc = raw if isinstance(raw, dict) else {}
    try:
        min_pct = float(cc.get("min", COVERAGE_CUTOFF_MIN))
    except (TypeError, ValueError):
        min_pct = COVERAGE_CUTOFF_MIN
    try:
        max_pct = float(cc.get("max", COVERAGE_CUTOFF_MAX))
    except (TypeError, ValueError):
        max_pct = COVERAGE_CUTOFF_MAX
    try:
        default = float(cc.get("default", COVERAGE_CUTOFF_DEFAULT))
    except (TypeError, ValueError):
        default = COVERAGE_CUTOFF_DEFAULT
    if max_pct < min_pct:
        min_pct, max_pct = max_pct, min_pct
    default = min(max_pct, max(min_pct, default))
    return min_pct, max_pct, default


def clamp_coverage_cutoff(
    value: Any,
    *,
    min_pct: float = COVERAGE_CUTOFF_MIN,
    max_pct: float = COVERAGE_CUTOFF_MAX,
    default: float = COVERAGE_CUTOFF_DEFAULT,
) -> float:
    """Clamp a coverage cutoff to the allowed slider range."""
    try:
        cutoff = float(value)
    except (TypeError, ValueError):
        cutoff = float(default)
    if cutoff != cutoff:  # NaN
        cutoff = float(default)
    return max(float(min_pct), min(float(max_pct), cutoff))


def filter_patterns_by_coverage(
    patterns: Optional[List["ErrorPattern"]],
    cutoff: float,
) -> List["ErrorPattern"]:
    """Keep patterns whose ``game_coverage`` is at least ``cutoff`` (0–100)."""
    if not patterns:
        return []
    floor = float(cutoff)
    return [
        p for p in patterns
        if float(getattr(p, "game_coverage", 0.0) or 0.0) + 1e-9 >= floor
    ]


def normalize_player_stats_error_patterns_settings(
    raw: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize persisted Error Patterns display settings."""
    min_pct, max_pct, default = coverage_cutoff_range(config)
    cutoff = default
    if isinstance(raw, dict) and "coverage_cutoff" in raw:
        cutoff = clamp_coverage_cutoff(
            raw.get("coverage_cutoff"),
            min_pct=min_pct,
            max_pct=max_pct,
            default=default,
        )
    else:
        cutoff = default
    return {"coverage_cutoff": cutoff}


@dataclass
class ErrorPattern:
    """Represents a detected error pattern."""
    pattern_type: str  # e.g., "phase_blunders", "tactical_misses", "opening_errors"
    description: str  # Human-readable description
    frequency: int  # Number of occurrences
    percentage: float  # Pattern-specific rate (0-100); card wording may use this
    severity: str  # "low", "moderate", "high", "critical"
    related_games: List[GameData]  # Games where this pattern occurs
    # Optional: (game, ref_ply) per occurrence for jump-to-move (e.g. repeated position, brilliant/miss/blunder)
    related_ref_plies: Optional[List[Tuple[GameData, int]]] = None  # (game, ply) for each occurrence
    # Share of relevant games (0-100) used by the display slider. Opportunity-based
    # patterns use the situation denominator (winning / worse / this opening).
    game_coverage: float = 0.0


class ErrorPatternService:
    """Service for detecting error patterns in player performance."""
    
    def __init__(self, config: Dict[str, Any], game_controller: Optional[GameController] = None):
        """Initialize the error pattern service.
        
        Args:
            config: Configuration dictionary.
            game_controller: Optional GameController for extracting moves.
        """
        self.config = config
        self.game_controller = game_controller
        self.opening_service = OpeningService.get_instance(config)
        
        pattern_config = error_pattern_config_block(config)
        self.thresholds = pattern_config.get('thresholds', {}) if isinstance(pattern_config.get('thresholds'), dict) else {}
        self.phase_blunder_threshold = self.thresholds.get('phase_blunder_percentage', 20.0)
        self.tactical_miss_threshold = self.thresholds.get('tactical_miss_count', 2)
        self.opening_error_threshold = self.thresholds.get('opening_error_rate', 30.0)
        try:
            self.min_pattern_games = max(1, int(pattern_config.get('min_pattern_games', 2)))
        except (TypeError, ValueError):
            self.min_pattern_games = 2

    def _moves_for(
        self,
        index: int,
        game: GameData,
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> Optional[List[MoveData]]:
        """Resolve moves for a game: use precomputed list when set, else extract via controller."""
        if precomputed_moves is not None and index < len(precomputed_moves):
            cached = precomputed_moves[index]
            if cached is not None:
                return cached
        if self.game_controller:
            try:
                return self.game_controller.extract_moves_from_game(game)
            except Exception:
                return None
        return None

    @staticmethod
    def _unique_games(items: List[GameData]) -> List[GameData]:
        related: List[GameData] = []
        seen = set()
        for game in items:
            if id(game) not in seen:
                seen.add(id(game))
                related.append(game)
        return related

    @staticmethod
    def _coverage(hits: int, base: int) -> float:
        if base <= 0:
            return 0.0
        return (hits / base) * 100.0

    def _meets_game_floor(self, n_games: int) -> bool:
        return n_games >= self.min_pattern_games

    @staticmethod
    def _player_lost(game: GameData, player_name: str) -> bool:
        result = (getattr(game, "result", None) or "").strip()
        is_white = game.white == player_name
        if is_white:
            return result == "0-1"
        return result == "1-0"

    @staticmethod
    def _player_stats(summary: Any, is_white: bool) -> Any:
        return summary.white_stats if is_white else summary.black_stats

    def detect_error_patterns(
        self,
        player_name: str,
        games: List[GameData],
        aggregated_stats: Optional[Any],
        game_summaries: List[GameSummary],
        precomputed_moves: Optional[List[Optional[List[MoveData]]]] = None,
    ) -> List[ErrorPattern]:
        """Detect error patterns for a player.

        Args:
            player_name: Player name.
            games: List of GameData instances (analyzed games).
            aggregated_stats: AggregatedPlayerStats instance.
            game_summaries: List of GameSummary instances for the games.
            precomputed_moves: Optional list aligned with ``games`` — one move list per game
                (e.g. from a single ``extract_moves_from_game`` pass). Avoids re-parsing PGN
                in each detector.

        Returns:
            List of ErrorPattern instances.
        """
        patterns: List[ErrorPattern] = []
        
        if not aggregated_stats or not games or not game_summaries:
            return patterns
        
        # Pattern 1: Phase-specific blunders (only show phase with most blunders)
        phase_patterns = self._detect_phase_blunder_patterns(
            player_name, games, game_summaries, aggregated_stats, precomputed_moves
        )
        patterns.extend(phase_patterns)
        
        # Pattern 2: Tactical misses (named PV1 tactics / mates from game summaries)
        tactical_patterns = self._detect_tactical_miss_patterns(
            player_name, games, game_summaries
        )
        patterns.extend(tactical_patterns)
        
        # Pattern 3: Opening-specific errors
        opening_patterns = self._detect_opening_error_patterns(
            player_name, games, game_summaries, aggregated_stats, precomputed_moves
        )
        patterns.extend(opening_patterns)
        
        # Pattern 4: High CPL patterns (consistently high centipawn loss)
        high_cpl_patterns = self._detect_high_cpl_patterns(
            player_name, games, game_summaries, aggregated_stats, precomputed_moves
        )
        patterns.extend(high_cpl_patterns)
        
        # Pattern 5: Missed top 3 moves
        missed_top3_patterns = self._detect_missed_top3_patterns(
            player_name, games, game_summaries, aggregated_stats
        )
        patterns.extend(missed_top3_patterns)
        
        # Pattern 6: Conversion issues (problems in winning positions)
        conversion_patterns = self._detect_conversion_issues(
            player_name, games, game_summaries
        )
        patterns.extend(conversion_patterns)
        
        # Pattern 7: Defensive weaknesses (problems when defending)
        defensive_patterns = self._detect_defensive_weaknesses(
            player_name, games, game_summaries, precomputed_moves
        )
        patterns.extend(defensive_patterns)
        
        # Pattern 8: Consistent inaccuracies (many small errors)
        inaccuracy_patterns = self._detect_consistent_inaccuracies(
            player_name, games, game_summaries, aggregated_stats
        )
        patterns.extend(inaccuracy_patterns)
        
        # Pattern 9: Repeated errors in the same position (blunders, misses, inaccuracies)
        repeated_position_patterns = self._detect_repeated_position_errors(
            player_name, games, precomputed_moves
        )
        patterns.extend(repeated_position_patterns)
        
        patterns.sort(key=lambda p: (-p.game_coverage, -p.percentage))
        return patterns
    
    def _detect_phase_blunder_patterns(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        aggregated_stats: Any,
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> List[ErrorPattern]:
        """Detect blunder patterns by phase."""
        patterns: List[ErrorPattern] = []
        
        # Count blunders by phase
        opening_blunders = aggregated_stats.opening_stats.blunders
        middlegame_blunders = aggregated_stats.middlegame_stats.blunders
        endgame_blunders = aggregated_stats.endgame_stats.blunders
        
        # Calculate total blunders as sum of phase blunders to ensure consistency
        # This ensures total_blunders includes blunders from all games (both colors),
        # matching how phase blunders are counted
        total_blunders = opening_blunders + middlegame_blunders + endgame_blunders
        if total_blunders == 0:
            return patterns
        
        # Find the phase with the most blunders
        phase_blunders = [
            ("opening", opening_blunders),
            ("middlegame", middlegame_blunders),
            ("endgame", endgame_blunders)
        ]
        # Sort by blunder count (descending)
        phase_blunders.sort(key=lambda x: x[1], reverse=True)
        
        # Only add pattern for the phase with the most blunders
        if phase_blunders and phase_blunders[0][1] > 0:
            phase_name, phase_blunder_count = phase_blunders[0]
            phase_percentage = (phase_blunder_count / total_blunders) * 100
            related_games = self._find_games_with_phase_blunders(
                player_name, games, game_summaries, phase_name
            )
            if not self._meets_game_floor(len(related_games)):
                return patterns
            related_ref_plies = self._collect_phase_blunder_ref_plies(
                player_name, games, game_summaries, phase_name, precomputed_moves
            )
            coverage = self._coverage(len(related_games), len(games))
            severity = self._determine_severity(phase_percentage, [30, 50, 70])
            patterns.append(ErrorPattern(
                pattern_type="phase_blunders",
                description=f"Frequent blunders in {phase_name} ({phase_percentage:.1f}% of blunders)",
                frequency=phase_blunder_count,
                percentage=phase_percentage,
                severity=severity,
                related_games=related_games,
                related_ref_plies=related_ref_plies or None,
                game_coverage=coverage,
            ))
        
        return patterns
    
    def _detect_tactical_miss_patterns(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
    ) -> List[ErrorPattern]:
        """Detect repeated missed tactics from each game's missed-tactics list.

        Uses the summary ranking (not the highlight composer). Named board tactics
        and missed mates are counted; generic capture/check misses are ignored.
        """
        patterns: List[ErrorPattern] = []
        by_kind: Dict[str, List[Tuple[GameData, int]]] = {
            kind: [] for kind in STATS_MISS_KIND_LABELS
        }

        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            summary = game_summaries[i]
            is_white = game.white == player_name
            misses = (
                getattr(summary, "white_missed_tactics", None)
                if is_white
                else getattr(summary, "black_missed_tactics", None)
            ) or []
            for move in misses:
                kind = str(getattr(move, "tactic_type", "") or "").strip()
                if kind not in by_kind:
                    continue
                move_number = int(getattr(move, "move_number", 0) or 0)
                if move_number <= 0:
                    continue
                ref_ply = move_number * 2 - 1 if is_white else move_number * 2
                by_kind[kind].append((game, ref_ply))

        occ_floor = max(1, int(self.tactical_miss_threshold))
        for kind, pairs in by_kind.items():
            related_games = self._unique_games([game for game, _ply in pairs])
            n_occ = len(pairs)
            n_games = len(related_games)
            if n_occ < occ_floor or not self._meets_game_floor(n_games):
                continue
            coverage = self._coverage(n_games, len(games))
            plural = STATS_MISS_KIND_LABELS[kind]
            severity = self._determine_severity(
                n_occ, [occ_floor, occ_floor * 2, occ_floor * 3]
            )
            patterns.append(
                ErrorPattern(
                    pattern_type="tactical_misses",
                    description=(
                        f"Frequently misses {plural} ({n_occ} occurrence"
                        f"{'s' if n_occ != 1 else ''} in {n_games} game"
                        f"{'s' if n_games != 1 else ''})"
                    ),
                    frequency=n_occ,
                    percentage=coverage,
                    severity=severity,
                    related_games=related_games,
                    related_ref_plies=pairs,
                    game_coverage=coverage,
                )
            )

        return patterns
    
    def _detect_opening_error_patterns(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        aggregated_stats: Any,
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> List[ErrorPattern]:
        """Detect opening-specific error patterns."""
        patterns: List[ErrorPattern] = []
        
        # Group games by last named book opening (OpeningService).
        opening_stats: Dict[str, Dict[str, Any]] = {}
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            summary = game_summaries[i]
            
            # Determine if player is white or black
            is_white = (game.white == player_name)
            
            moves = self._moves_for(i, game, precomputed_moves)
            if not moves:
                continue
            
            eco = "Unknown"
            opening_name = None
            last_opening = self.opening_service.last_opening_for_pgn(game.pgn or "")
            if last_opening:
                eco = last_opening.eco
                opening_name = last_opening.name
            elif game.eco:
                eco = game.eco
            
            # Use ECO as key (may include opening name in the value for description)
            if eco not in opening_stats:
                opening_stats[eco] = {
                    'games': [],
                    'lost_games': [],
                    'total_moves': 0,
                    'errors': 0,
                    'blunders': 0,
                    'mistakes': 0,
                    'opening_name': opening_name,  # Store opening name from first game with this ECO
                    # Concrete (game, ref_ply) locations of opening-phase errors for this ECO.
                    'ref_plies': [],
                    'lost_ref_plies': [],
                }
            
            opening_stats[eco]['games'].append(game)
            lost = self._player_lost(game, player_name)
            if lost:
                opening_stats[eco]['lost_games'].append(game)
            
            # Store opening name if we found one and haven't stored one yet
            if opening_name and not opening_stats[eco]['opening_name']:
                opening_stats[eco]['opening_name'] = opening_name
            
            # Get player stats for this game
            if is_white:
                stats = summary.white_opening
                opening_moves = summary.white_opening.moves
            else:
                stats = summary.black_opening
                opening_moves = summary.black_opening.moves
            
            opening_stats[eco]['total_moves'] += stats.moves
            opening_stats[eco]['errors'] += stats.inaccuracies + stats.mistakes + stats.blunders
            opening_stats[eco]['blunders'] += stats.blunders
            opening_stats[eco]['mistakes'] += stats.mistakes

            # Collect specific opening-phase errors for jump-to-move support.
            if opening_moves > 0:
                player_move_index = 0
                for mv in moves:
                    if is_white and getattr(mv, "white_move", None):
                        player_move_index += 1
                        if player_move_index <= opening_moves:
                            assess = (getattr(mv, "assess_white", "") or "").strip()
                            if assess in ("Inaccuracy", "Mistake", "Miss", "Blunder"):
                                ref_ply = mv.move_number * 2 - 1
                                opening_stats[eco]['ref_plies'].append((game, ref_ply))
                                if lost:
                                    opening_stats[eco]['lost_ref_plies'].append((game, ref_ply))
                    elif (not is_white) and getattr(mv, "black_move", None):
                        player_move_index += 1
                        if player_move_index <= opening_moves:
                            assess = (getattr(mv, "assess_black", "") or "").strip()
                            if assess in ("Inaccuracy", "Mistake", "Miss", "Blunder"):
                                ref_ply = mv.move_number * 2
                                opening_stats[eco]['ref_plies'].append((game, ref_ply))
                                if lost:
                                    opening_stats[eco]['lost_ref_plies'].append((game, ref_ply))
        
        # Check for openings with high error rates
        for eco, stats in opening_stats.items():
            if stats['total_moves'] < 10:  # Need minimum moves for meaningful stats
                continue
            
            error_rate = (stats['errors'] / stats['total_moves']) * 100
            if error_rate < self.opening_error_threshold:
                continue
            lost_games = self._unique_games(stats.get('lost_games') or [])
            opening_games = stats.get('games') or []
            if not self._meets_game_floor(len(lost_games)):
                continue
            coverage = self._coverage(len(lost_games), len(opening_games))
            opening_name = stats.get('opening_name')
            if opening_name and eco != "Unknown":
                description = f"High error rate in {eco} ({opening_name}) ({error_rate:.1f}% of moves)"
            else:
                description = f"High error rate in {eco} ({error_rate:.1f}% of moves)"
            severity = self._determine_severity(error_rate, [40, 50, 60])
            patterns.append(ErrorPattern(
                pattern_type="opening_errors",
                description=description,
                frequency=stats['errors'],
                percentage=error_rate,
                severity=severity,
                related_games=lost_games,
                related_ref_plies=stats.get('lost_ref_plies') or None,
                game_coverage=coverage,
            ))
        
        return patterns
    
    def _find_games_with_phase_blunders(self, player_name: str, games: List[GameData],
                                       game_summaries: List[GameSummary],
                                       phase: str) -> List[GameData]:
        """Find games where player has blunders in the specified phase."""
        related_games: List[GameData] = []
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            is_white = (game.white == player_name)
            summary = game_summaries[i]
            
            if phase == "opening":
                phase_stats = summary.white_opening if is_white else summary.black_opening
            elif phase == "middlegame":
                phase_stats = summary.white_middlegame if is_white else summary.black_middlegame
            else:  # endgame
                phase_stats = summary.white_endgame if is_white else summary.black_endgame
            
            if phase_stats.blunders > 0:
                related_games.append(game)
        
        return related_games

    def _collect_phase_blunder_ref_plies(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        phase: str,
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> List[Tuple[GameData, int]]:
        """Collect (game, ref_ply) pairs for blunders in the specified phase.

        Uses per-phase move counts from GameSummary to map a player's moves to
        opening/middlegame/endgame and records blunders in the dominant phase.
        """
        results: List[Tuple[GameData, int]] = []

        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue

            is_white = (game.white == player_name)
            summary = game_summaries[i]

            if is_white:
                opening_moves = summary.white_opening.moves
                middlegame_moves = summary.white_middlegame.moves
                endgame_moves = summary.white_endgame.moves
            else:
                opening_moves = summary.black_opening.moves
                middlegame_moves = summary.black_middlegame.moves
                endgame_moves = summary.black_endgame.moves

            moves = self._moves_for(i, game, precomputed_moves)
            if not moves:
                continue

            player_move_index = 0

            for mv in moves:
                if is_white and getattr(mv, "white_move", None):
                    player_move_index += 1
                    assess = (getattr(mv, "assess_white", "") or "").strip()
                    if assess != "Blunder":
                        continue
                    if player_move_index <= opening_moves:
                        move_phase = "opening"
                    elif player_move_index <= opening_moves + middlegame_moves:
                        move_phase = "middlegame"
                    else:
                        move_phase = "endgame"
                    if move_phase != phase:
                        continue
                    ref_ply = mv.move_number * 2 - 1
                    results.append((game, ref_ply))
                elif (not is_white) and getattr(mv, "black_move", None):
                    player_move_index += 1
                    assess = (getattr(mv, "assess_black", "") or "").strip()
                    if assess != "Blunder":
                        continue
                    if player_move_index <= opening_moves:
                        move_phase = "opening"
                    elif player_move_index <= opening_moves + middlegame_moves:
                        move_phase = "middlegame"
                    else:
                        move_phase = "endgame"
                    if move_phase != phase:
                        continue
                    ref_ply = mv.move_number * 2
                    results.append((game, ref_ply))

        return results
    
    def _detect_high_cpl_patterns(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        aggregated_stats: Any,
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> List[ErrorPattern]:
        """Detect games with high centipawn loss (no career-average gate)."""
        patterns: List[ErrorPattern] = []
        
        high_cpl_threshold = self.thresholds.get('high_cpl_threshold', 50.0)
        related_games: List[GameData] = []
        related_ref_plies: List[Tuple[GameData, int]] = []
        cpl_values: List[float] = []
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            is_white = (game.white == player_name)
            summary = game_summaries[i]
            player_stats = self._player_stats(summary, is_white)
            game_cpl = float(getattr(player_stats, "average_cpl", 0.0) or 0.0)
            if game_cpl < high_cpl_threshold:
                continue
            related_games.append(game)
            cpl_values.append(game_cpl)
            moves = self._moves_for(i, game, precomputed_moves)
            if not moves:
                continue
            cpl_field = "cpl_white" if is_white else "cpl_black"
            move_field = "white_move" if is_white else "black_move"
            worst: List[Tuple[float, int]] = []
            for mv in moves:
                if not getattr(mv, move_field, None):
                    continue
                cpl_str = getattr(mv, cpl_field, "") or ""
                if not cpl_str:
                    continue
                try:
                    cpl_val = float(cpl_str)
                except (TypeError, ValueError):
                    continue
                if is_white:
                    ref_ply = mv.move_number * 2 - 1
                else:
                    ref_ply = mv.move_number * 2
                worst.append((cpl_val, ref_ply))
            if worst:
                worst.sort(key=lambda x: x[0], reverse=True)
                for _, ref_ply in worst[:3]:
                    related_ref_plies.append((game, ref_ply))

        if not self._meets_game_floor(len(related_games)):
            return patterns

        avg_cpl = sum(cpl_values) / len(cpl_values) if cpl_values else 0.0
        coverage = self._coverage(len(related_games), len(games))
        severity = self._determine_severity(avg_cpl, [60, 80, 100])
        patterns.append(ErrorPattern(
            pattern_type="high_cpl",
            description=(
                f"High centipawn loss ({len(related_games)} game"
                f"{'s' if len(related_games) != 1 else ''}, avg {avg_cpl:.1f} CPL)"
            ),
            frequency=len(related_games),
            percentage=coverage,
            severity=severity,
            related_games=related_games,
            related_ref_plies=related_ref_plies or None,
            game_coverage=coverage,
        ))
        
        return patterns
    
    def _detect_missed_top3_patterns(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        aggregated_stats: Any,
    ) -> List[ErrorPattern]:
        """Detect games where the player's own top-3 hit rate is below the bar."""
        patterns: List[ErrorPattern] = []
        missed_top3_threshold = self.thresholds.get('missed_top3_threshold', 60.0)
        related_games: List[GameData] = []
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            is_white = (game.white == player_name)
            player_stats = self._player_stats(game_summaries[i], is_white)
            top3 = getattr(player_stats, "top3_move_percentage", None)
            if top3 is None:
                continue
            if float(top3) < missed_top3_threshold:
                related_games.append(game)

        if not self._meets_game_floor(len(related_games)):
            return patterns

        career_top3 = float(
            getattr(getattr(aggregated_stats, "player_stats", None), "top3_move_percentage", 0.0) or 0.0
        )
        coverage = self._coverage(len(related_games), len(games))
        severity = self._determine_severity(coverage, [30, 50, 70])
        patterns.append(ErrorPattern(
            pattern_type="missed_top3",
            description=f"Frequently misses top 3 moves ({career_top3:.1f}% in top 3)",
            frequency=len(related_games),
            percentage=coverage,
            severity=severity,
            related_games=related_games,
            game_coverage=coverage,
        ))
        
        return patterns
    
    def _detect_conversion_issues(self, player_name: str, games: List[GameData],
                                 game_summaries: List[GameSummary]) -> List[ErrorPattern]:
        """Detect problems converting winning positions."""
        patterns: List[ErrorPattern] = []
        
        conversion_issues = 0
        winning_games = 0
        related_games: List[GameData] = []
        related_ref_plies: List[Tuple[GameData, int]] = []
        winning_threshold = self.thresholds.get('winning_eval_threshold', 200.0)  # +2.0 pawns
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            is_white = (game.white == player_name)
            summary = game_summaries[i]
            
            # Check if player had a winning position but lost or drew
            had_winning_position = False
            max_winning_eval = 0.0
            winning_ply_indices: List[int] = []
            
            for ply_index, eval_value in summary.evaluation_data:
                # Determine if this evaluation is for the player
                # Evaluation is after the move, so we need to check whose turn it was
                # For simplicity, check if eval was favorable for the player
                if is_white:
                    # Positive eval is good for white
                    if eval_value >= winning_threshold:
                        had_winning_position = True
                        max_winning_eval = max(max_winning_eval, eval_value)
                        winning_ply_indices.append(ply_index)
                else:
                    # Negative eval is good for black (more negative = better)
                    if eval_value <= -winning_threshold:
                        had_winning_position = True
                        max_winning_eval = max(max_winning_eval, abs(eval_value))
                        winning_ply_indices.append(ply_index)
            
            # Check if player lost or drew despite having winning position
            if had_winning_position:
                winning_games += 1
                if is_white and game.result in ["0-1", "1/2-1/2"]:
                    conversion_issues += 1
                    related_games.append(game)
                    if winning_ply_indices:
                        related_ref_plies.append((game, int(winning_ply_indices[-1])))
                elif not is_white and game.result in ["1-0", "1/2-1/2"]:
                    conversion_issues += 1
                    related_games.append(game)
                    if winning_ply_indices:
                        related_ref_plies.append((game, int(winning_ply_indices[-1])))
        
        if not self._meets_game_floor(conversion_issues) or winning_games <= 0:
            return patterns
        conversion_rate = self._coverage(conversion_issues, winning_games)
        severity = self._determine_severity(conversion_rate, [20, 30, 40])
        patterns.append(ErrorPattern(
            pattern_type="conversion_issues",
            description=(
                f"Struggles to convert winning positions "
                f"({conversion_issues} of {winning_games} games)"
            ),
            frequency=conversion_issues,
            percentage=conversion_rate,
            severity=severity,
            related_games=related_games,
            related_ref_plies=related_ref_plies or None,
            game_coverage=conversion_rate,
        ))
        
        return patterns
    
    def _detect_defensive_weaknesses(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> List[ErrorPattern]:
        """Detect problems when defending (playing from worse positions)."""
        patterns: List[ErrorPattern] = []
        
        defensive_errors = 0
        worse_games = 0
        related_games: List[GameData] = []
        related_ref_plies: List[Tuple[GameData, int]] = []
        losing_threshold = self.thresholds.get('losing_eval_threshold', -200.0)  # -2.0 pawns
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            is_white = (game.white == player_name)
            summary = game_summaries[i]
            
            # Check if player was in a losing position
            had_losing_position = False
            defensive_blunders = 0
            game_ref_plies: List[Tuple[GameData, int]] = []
            
            moves = self._moves_for(i, game, precomputed_moves)
            if not moves:
                continue
            
            # evaluation_data stores (ply_index, eval_cp) pairs
            # ply_index 0 = initial position, 1 = after white's first move, 2 = after black's first move, etc.
            # For white: check evaluations at even ply_indices (0, 2, 4...) before their moves
            # For black: check evaluations at odd ply_indices (1, 3, 5...) before their moves
            eval_dict = dict(summary.evaluation_data)
            
            for move in moves:
                move_num = move.move_number
                # Calculate ply_index before this move
                # move_num 1 = white's first move (ply_index 0 -> 1)
                # move_num 1 = black's first move (ply_index 1 -> 2)
                if is_white:
                    # White's move: ply_index before = (move_num - 1) * 2
                    ply_before = (move_num - 1) * 2
                    eval_before = eval_dict.get(ply_before)
                    if eval_before is not None and eval_before <= losing_threshold:
                        had_losing_position = True
                        if move.assess_white == "Blunder":
                            defensive_blunders += 1
                            ref_ply = ply_before + 1
                            game_ref_plies.append((game, ref_ply))
                else:
                    # Black's move: ply_index before = (move_num - 1) * 2 + 1
                    ply_before = (move_num - 1) * 2 + 1
                    eval_before = eval_dict.get(ply_before)
                    if eval_before is not None and eval_before >= -losing_threshold:
                        had_losing_position = True
                        if move.assess_black == "Blunder":
                            defensive_blunders += 1
                            ref_ply = ply_before + 1
                            game_ref_plies.append((game, ref_ply))
            
            if had_losing_position:
                worse_games += 1
                if defensive_blunders >= 2:
                    defensive_errors += 1
                    related_games.append(game)
                    if game_ref_plies:
                        related_ref_plies.extend(game_ref_plies)
        
        if not self._meets_game_floor(defensive_errors) or worse_games <= 0:
            return patterns
        defensive_rate = self._coverage(defensive_errors, worse_games)
        severity = self._determine_severity(defensive_rate, [25, 35, 45])
        patterns.append(ErrorPattern(
            pattern_type="defensive_weaknesses",
            description=(
                f"Struggles when defending "
                f"({defensive_errors} of {worse_games} games with multiple blunders)"
            ),
            frequency=defensive_errors,
            percentage=defensive_rate,
            severity=severity,
            related_games=related_games,
            related_ref_plies=related_ref_plies or None,
            game_coverage=defensive_rate,
        ))
        
        return patterns
    
    def _detect_consistent_inaccuracies(
        self,
        player_name: str,
        games: List[GameData],
        game_summaries: List[GameSummary],
        aggregated_stats: Any,
    ) -> List[ErrorPattern]:
        """Detect games where inaccuracies are a large share of that game's moves."""
        patterns: List[ErrorPattern] = []
        inaccuracy_threshold = self.thresholds.get('inaccuracy_rate_threshold', 25.0)
        related_games: List[GameData] = []
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            is_white = (game.white == player_name)
            player_stats = self._player_stats(game_summaries[i], is_white)
            total_moves = int(getattr(player_stats, "total_moves", 0) or 0)
            if total_moves <= 0:
                continue
            inaccuracies = int(getattr(player_stats, "inaccuracies", 0) or 0)
            rate = (inaccuracies / total_moves) * 100
            if rate >= inaccuracy_threshold:
                related_games.append(game)

        if not self._meets_game_floor(len(related_games)):
            return patterns

        career_stats = getattr(aggregated_stats, "player_stats", None)
        career_total = int(getattr(career_stats, "total_moves", 0) or 0)
        career_inacc = int(getattr(career_stats, "inaccuracies", 0) or 0)
        career_rate = (career_inacc / career_total * 100) if career_total > 0 else 0.0
        coverage = self._coverage(len(related_games), len(games))
        severity = self._determine_severity(coverage, [30, 50, 70])
        patterns.append(ErrorPattern(
            pattern_type="consistent_inaccuracies",
            description=f"Many small errors ({career_rate:.1f}% of moves are inaccuracies)",
            frequency=len(related_games),
            percentage=coverage,
            severity=severity,
            related_games=related_games,
            game_coverage=coverage,
        ))
        
        return patterns
    
    @staticmethod
    def _normalize_fen(fen: str) -> str:
        """Normalize FEN to board + side to move so same position matches across games."""
        if not (fen or "").strip():
            return ""
        parts = fen.strip().split()
        return " ".join(parts[:2]) if len(parts) >= 2 else fen.strip()
    
    def _detect_repeated_position_errors(
        self,
        player_name: str,
        games: List[GameData],
        precomputed_moves: Optional[List[Optional[List[MoveData]]]],
    ) -> List[ErrorPattern]:
        """Detect repeated blunders, mistakes, misses, or inaccuracies in the same position across games."""
        patterns: List[ErrorPattern] = []
        if not games:
            return patterns
        
        start_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        # (normalized_fen, assessment_type) -> list of (game, ref_ply) where player made that error in that position
        collector: Dict[tuple, List[Tuple[GameData, int]]] = {}
        
        for gi, game in enumerate(games):
            moves = self._moves_for(gi, game, precomputed_moves)
            if not moves:
                continue
            is_white = (game.white == player_name)
            prev = None
            for i, move in enumerate(moves):
                if is_white and (move.white_move or getattr(move, "white_move", None)):
                    fen_before = (prev.fen_black if prev and getattr(prev, "fen_black", None) else None) or start_fen
                    assessment = (move.assess_white or "").strip()
                    if assessment in ("Blunder", "Mistake", "Miss", "Inaccuracy"):
                        key = (self._normalize_fen(fen_before), assessment)
                        ply = move.move_number * 2 - 1  # after white's move
                        if key not in collector:
                            collector[key] = []
                        # Allow same game multiple times if same position repeated in one game (one entry per occurrence)
                        collector[key].append((game, ply))
                if not is_white and (move.black_move or getattr(move, "black_move", None)):
                    fen_before = (move.fen_white or "").strip()
                    if fen_before:
                        assessment = (move.assess_black or "").strip()
                        if assessment in ("Blunder", "Mistake", "Miss", "Inaccuracy"):
                            key = (self._normalize_fen(fen_before), assessment)
                            ply = move.move_number * 2  # after black's move
                            if key not in collector:
                                collector[key] = []
                            collector[key].append((game, ply))
                prev = move
        
        min_blunder = self.thresholds.get("repeated_position_min_games_blunder", 2)
        min_mistake = self.thresholds.get("repeated_position_min_games_mistake", 2)
        min_miss = self.thresholds.get("repeated_position_min_games_miss", 2)
        min_inaccuracy = self.thresholds.get("repeated_position_min_games_inaccuracy", 2)
        
        for assessment_type, min_games, pattern_type, description_label in [
            ("Blunder", min_blunder, "repeated_blunders_same_position", "Repeated blunders in the same position"),
            ("Mistake", min_mistake, "repeated_mistakes_same_position", "Repeated mistakes in the same position"),
            ("Miss", min_miss, "repeated_misses_same_position", "Repeated misses in the same position"),
            ("Inaccuracy", min_inaccuracy, "repeated_inaccuracies_same_position", "Repeated inaccuracies in the same position"),
        ]:
            positions_with_repeats = [
                (key, pairs) for key, pairs in collector.items()
                if key[1] == assessment_type and len(pairs) >= min_games
            ]
            # Require at least min_games distinct games (same position in same game counts as one game)
            positions_with_repeats = [
                (key, pairs) for key, pairs in positions_with_repeats
                if len(set(id(g) for g, _ in pairs)) >= min_games
            ]
            if not positions_with_repeats:
                continue
            all_games: List[GameData] = []
            seen = set()
            related_ref_plies: List[Tuple[GameData, int]] = []
            for _, pairs in positions_with_repeats:
                for g, ply in pairs:
                    related_ref_plies.append((g, ply))
                    if id(g) not in seen:
                        seen.add(id(g))
                        all_games.append(g)
            num_positions = len(positions_with_repeats)
            num_games = len(all_games)
            if not self._meets_game_floor(num_games):
                continue
            coverage = self._coverage(num_games, len(games))
            severity = self._determine_severity(num_games, [3, 5, 8])
            desc = f"{description_label} ({num_positions} position{'s' if num_positions != 1 else ''} in {num_games} game{'s' if num_games != 1 else ''})"
            patterns.append(ErrorPattern(
                pattern_type=pattern_type,
                description=desc,
                frequency=num_positions,
                percentage=coverage,
                severity=severity,
                related_games=all_games,
                related_ref_plies=related_ref_plies,
                game_coverage=coverage,
            ))
        
        return patterns
    
    def _determine_severity(self, value: float, thresholds: List[float]) -> str:
        """Determine severity based on value and thresholds.
        
        Args:
            value: Value to evaluate.
            thresholds: List of [moderate, high, critical] thresholds.
            
        Returns:
            Severity string: "low", "moderate", "high", or "critical".
        """
        if len(thresholds) < 3:
            return "low"
        
        if value >= thresholds[2]:
            return "critical"
        elif value >= thresholds[1]:
            return "high"
        elif value >= thresholds[0]:
            return "moderate"
        else:
            return "low"


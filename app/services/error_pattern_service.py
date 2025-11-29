"""Service for detecting error patterns in player performance."""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.models.database_model import GameData
from app.services.game_summary_service import GameSummary, PlayerStatistics, PhaseStatistics
from app.services.game_highlights.base_rule import GameHighlight
from app.services.game_highlights.highlight_detector import HighlightDetector
from app.services.game_highlights.rule_registry import RuleRegistry
from app.controllers.game_controller import GameController
from app.services.opening_service import OpeningService


@dataclass
class ErrorPattern:
    """Represents a detected error pattern."""
    pattern_type: str  # e.g., "phase_blunders", "tactical_misses", "opening_errors"
    description: str  # Human-readable description
    frequency: int  # Number of occurrences
    percentage: float  # Percentage (0-100)
    severity: str  # "low", "moderate", "high", "critical"
    related_games: List[GameData]  # Games where this pattern occurs


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
        self.opening_service = OpeningService(config)
        
        # Get thresholds from config
        pattern_config = config.get('player_stats', {}).get('error_patterns', {})
        self.thresholds = pattern_config.get('thresholds', {})
        self.phase_blunder_threshold = self.thresholds.get('phase_blunder_percentage', 20.0)
        self.tactical_miss_threshold = self.thresholds.get('tactical_miss_count', 10)
        self.opening_error_threshold = self.thresholds.get('opening_error_rate', 30.0)
    
    def detect_error_patterns(self, player_name: str, games: List[GameData],
                             aggregated_stats: Optional[Any],
                             game_summaries: List[GameSummary]) -> List[ErrorPattern]:
        """Detect error patterns for a player.
        
        Args:
            player_name: Player name.
            games: List of GameData instances (analyzed games).
            aggregated_stats: AggregatedPlayerStats instance.
            game_summaries: List of GameSummary instances for the games.
            
        Returns:
            List of ErrorPattern instances.
        """
        patterns: List[ErrorPattern] = []
        
        if not aggregated_stats or not games or not game_summaries:
            return patterns
        
        # Pattern 1: Phase-specific blunders (only show phase with most blunders)
        phase_patterns = self._detect_phase_blunder_patterns(
            player_name, games, game_summaries, aggregated_stats
        )
        patterns.extend(phase_patterns)
        
        # Pattern 2: Tactical misses
        tactical_patterns = self._detect_tactical_miss_patterns(
            player_name, games
        )
        patterns.extend(tactical_patterns)
        
        # Pattern 3: Opening-specific errors
        opening_patterns = self._detect_opening_error_patterns(
            player_name, games, game_summaries, aggregated_stats
        )
        patterns.extend(opening_patterns)
        
        # Pattern 4: High CPL patterns (consistently high centipawn loss)
        high_cpl_patterns = self._detect_high_cpl_patterns(
            player_name, games, game_summaries, aggregated_stats
        )
        patterns.extend(high_cpl_patterns)
        
        # Pattern 5: Missed top 3 moves
        missed_top3_patterns = self._detect_missed_top3_patterns(
            player_name, aggregated_stats
        )
        patterns.extend(missed_top3_patterns)
        
        # Pattern 6: Conversion issues (problems in winning positions)
        conversion_patterns = self._detect_conversion_issues(
            player_name, games, game_summaries
        )
        patterns.extend(conversion_patterns)
        
        # Pattern 7: Defensive weaknesses (problems when defending)
        defensive_patterns = self._detect_defensive_weaknesses(
            player_name, games, game_summaries
        )
        patterns.extend(defensive_patterns)
        
        # Pattern 8: Consistent inaccuracies (many small errors)
        inaccuracy_patterns = self._detect_consistent_inaccuracies(
            player_name, aggregated_stats
        )
        patterns.extend(inaccuracy_patterns)
        
        # Sort patterns: those without related_games first, then by severity/percentage
        patterns.sort(key=lambda p: (
            0 if p.related_games else 1,  # No games first (0 < 1)
            -p.percentage,  # Then by percentage descending
        ))
        
        return patterns
    
    def _detect_phase_blunder_patterns(self, player_name: str, games: List[GameData],
                                      game_summaries: List[GameSummary],
                                      aggregated_stats: Any) -> List[ErrorPattern]:
        """Detect blunder patterns by phase."""
        patterns: List[ErrorPattern] = []
        
        total_blunders = aggregated_stats.player_stats.blunders
        if total_blunders == 0:
            return patterns
        
        # Count blunders by phase
        opening_blunders = aggregated_stats.opening_stats.blunders
        middlegame_blunders = aggregated_stats.middlegame_stats.blunders
        endgame_blunders = aggregated_stats.endgame_stats.blunders
        
        # Find the phase with the most blunders
        phase_blunders = [
            ("opening", opening_blunders),
            ("middlegame", middlegame_blunders),
            ("endgame", endgame_blunders)
        ]
        # Sort by blunder count (descending)
        phase_blunders.sort(key=lambda x: x[1], reverse=True)
        
        # Only add pattern for the phase with the most blunders (if it meets threshold)
        if phase_blunders and phase_blunders[0][1] > 0:
            phase_name, phase_blunder_count = phase_blunders[0]
            phase_percentage = (phase_blunder_count / total_blunders) * 100
            if phase_percentage >= self.phase_blunder_threshold:
                related_games = self._find_games_with_phase_blunders(
                    player_name, games, game_summaries, phase_name
                )
                severity = self._determine_severity(phase_percentage, [30, 50, 70])
                patterns.append(ErrorPattern(
                    pattern_type="phase_blunders",
                    description=f"Frequent blunders in {phase_name} ({phase_percentage:.1f}% of blunders)",
                    frequency=phase_blunder_count,
                    percentage=phase_percentage,
                    severity=severity,
                    related_games=related_games
                ))
        
        return patterns
    
    def _detect_tactical_miss_patterns(self, player_name: str, games: List[GameData]) -> List[ErrorPattern]:
        """Detect missed tactical opportunities."""
        patterns: List[ErrorPattern] = []
        
        if not self.game_controller:
            return patterns
        
        # Count missed tactical opportunities across games
        missed_forks = 0
        missed_pins = 0
        missed_skewers = 0
        related_games_forks: List[GameData] = []
        related_games_pins: List[GameData] = []
        related_games_skewers: List[GameData] = []
        
        # This would require running highlight detection on all games
        # For now, return empty - this can be enhanced later
        # TODO: Implement tactical miss detection using HighlightDetector
        
        return patterns
    
    def _detect_opening_error_patterns(self, player_name: str, games: List[GameData],
                                      game_summaries: List[GameSummary],
                                      aggregated_stats: Any) -> List[ErrorPattern]:
        """Detect opening-specific error patterns."""
        patterns: List[ErrorPattern] = []
        
        if not self.game_controller:
            return patterns
        
        # Get repeat indicator from config
        repeat_indicator = self.config.get('resources', {}).get('opening_repeat_indicator', '*')
        
        # Group games by opening (ECO) - get ECO from last move with non-"*" opening name
        opening_stats: Dict[str, Dict[str, Any]] = {}
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            summary = game_summaries[i]
            
            # Determine if player is white or black
            is_white = (game.white == player_name)
            
            # Get moves for this game
            moves = self.game_controller.extract_moves_from_game(game)
            if not moves:
                continue
            
            # Find the last move with a non-"*" opening name
            # Use both ECO and opening name from that move
            eco = "Unknown"
            opening_name = None
            for move in reversed(moves):
                if move.opening_name and move.opening_name != repeat_indicator:
                    eco = move.eco if move.eco else "Unknown"
                    opening_name = move.opening_name
                    break
            
            # If no move with opening name found, fall back to game header ECO
            if eco == "Unknown" and not opening_name:
                eco = game.eco if game.eco else "Unknown"
            
            # Use ECO as key (may include opening name in the value for description)
            if eco not in opening_stats:
                opening_stats[eco] = {
                    'games': [],
                    'total_moves': 0,
                    'errors': 0,
                    'blunders': 0,
                    'mistakes': 0,
                    'opening_name': opening_name  # Store opening name from first game with this ECO
                }
            
            opening_stats[eco]['games'].append(game)
            
            # Store opening name if we found one and haven't stored one yet
            if opening_name and not opening_stats[eco]['opening_name']:
                opening_stats[eco]['opening_name'] = opening_name
            
            # Get player stats for this game
            if is_white:
                stats = summary.white_opening
            else:
                stats = summary.black_opening
            
            opening_stats[eco]['total_moves'] += stats.moves
            opening_stats[eco]['errors'] += stats.inaccuracies + stats.mistakes + stats.blunders
            opening_stats[eco]['blunders'] += stats.blunders
            opening_stats[eco]['mistakes'] += stats.mistakes
        
        # Check for openings with high error rates
        for eco, stats in opening_stats.items():
            if stats['total_moves'] < 10:  # Need minimum moves for meaningful stats
                continue
            
            error_rate = (stats['errors'] / stats['total_moves']) * 100
            if error_rate >= self.opening_error_threshold:
                # Get opening name from stored value (from last move with non-"*" opening name)
                opening_name = stats.get('opening_name')
                
                # Build description with ECO and opening name if available
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
                    related_games=stats['games']
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
    
    def _detect_high_cpl_patterns(self, player_name: str, games: List[GameData],
                                  game_summaries: List[GameSummary],
                                  aggregated_stats: Any) -> List[ErrorPattern]:
        """Detect patterns of consistently high centipawn loss."""
        patterns: List[ErrorPattern] = []
        
        avg_cpl = aggregated_stats.player_stats.average_cpl
        high_cpl_threshold = self.thresholds.get('high_cpl_threshold', 50.0)
        
        if avg_cpl >= high_cpl_threshold:
            # Find games with high CPL
            related_games: List[GameData] = []
            for i, game in enumerate(games):
                if i >= len(game_summaries):
                    continue
                is_white = (game.white == player_name)
                summary = game_summaries[i]
                player_stats = summary.white_stats if is_white else summary.black_stats
                if player_stats.average_cpl >= high_cpl_threshold:
                    related_games.append(game)
            
            severity = self._determine_severity(avg_cpl, [60, 80, 100])
            patterns.append(ErrorPattern(
                pattern_type="high_cpl",
                description=f"Consistently high centipawn loss (avg {avg_cpl:.1f} CPL)",
                frequency=len(related_games),
                percentage=(len(related_games) / len(games) * 100) if games else 0.0,
                severity=severity,
                related_games=related_games
            ))
        
        return patterns
    
    def _detect_missed_top3_patterns(self, player_name: str,
                                     aggregated_stats: Any) -> List[ErrorPattern]:
        """Detect patterns of frequently missing top 3 moves."""
        patterns: List[ErrorPattern] = []
        
        top3_percentage = aggregated_stats.player_stats.top3_move_percentage
        missed_top3_threshold = self.thresholds.get('missed_top3_threshold', 60.0)
        
        if top3_percentage < missed_top3_threshold:
            missed_moves = aggregated_stats.player_stats.total_moves - int(
                aggregated_stats.player_stats.total_moves * top3_percentage / 100
            )
            severity = self._determine_severity(100 - top3_percentage, [30, 40, 50])
            patterns.append(ErrorPattern(
                pattern_type="missed_top3",
                description=f"Frequently misses top 3 moves ({top3_percentage:.1f}% in top 3)",
                frequency=missed_moves,
                percentage=100 - top3_percentage,
                severity=severity,
                related_games=[]  # Would need to analyze individual games to find specific instances
            ))
        
        return patterns
    
    def _detect_conversion_issues(self, player_name: str, games: List[GameData],
                                 game_summaries: List[GameSummary]) -> List[ErrorPattern]:
        """Detect problems converting winning positions."""
        patterns: List[ErrorPattern] = []
        
        if not self.game_controller:
            return patterns
        
        conversion_issues = 0
        related_games: List[GameData] = []
        winning_threshold = self.thresholds.get('winning_eval_threshold', 200.0)  # +2.0 pawns
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            is_white = (game.white == player_name)
            summary = game_summaries[i]
            
            # Check if player had a winning position but lost or drew
            had_winning_position = False
            max_winning_eval = 0.0
            
            for move_num, eval_value in summary.evaluation_data:
                # Determine if this evaluation is for the player
                # Evaluation is after the move, so we need to check whose turn it was
                # For simplicity, check if eval was favorable for the player
                if is_white:
                    # Positive eval is good for white
                    if eval_value >= winning_threshold:
                        had_winning_position = True
                        max_winning_eval = max(max_winning_eval, eval_value)
                else:
                    # Negative eval is good for black (more negative = better)
                    if eval_value <= -winning_threshold:
                        had_winning_position = True
                        max_winning_eval = max(max_winning_eval, abs(eval_value))
            
            # Check if player lost or drew despite having winning position
            if had_winning_position:
                if is_white and game.result in ["0-1", "1/2-1/2"]:
                    conversion_issues += 1
                    related_games.append(game)
                elif not is_white and game.result in ["1-0", "1/2-1/2"]:
                    conversion_issues += 1
                    related_games.append(game)
        
        if conversion_issues > 0:
            conversion_rate = (conversion_issues / len(games) * 100) if games else 0.0
            if conversion_rate >= self.thresholds.get('conversion_issue_threshold', 15.0):
                severity = self._determine_severity(conversion_rate, [20, 30, 40])
                patterns.append(ErrorPattern(
                    pattern_type="conversion_issues",
                    description=f"Struggles to convert winning positions ({conversion_issues} games)",
                    frequency=conversion_issues,
                    percentage=conversion_rate,
                    severity=severity,
                    related_games=related_games
                ))
        
        return patterns
    
    def _detect_defensive_weaknesses(self, player_name: str, games: List[GameData],
                                    game_summaries: List[GameSummary]) -> List[ErrorPattern]:
        """Detect problems when defending (playing from worse positions)."""
        patterns: List[ErrorPattern] = []
        
        if not self.game_controller:
            return patterns
        
        defensive_errors = 0
        related_games: List[GameData] = []
        losing_threshold = self.thresholds.get('losing_eval_threshold', -200.0)  # -2.0 pawns
        
        for i, game in enumerate(games):
            if i >= len(game_summaries):
                continue
            
            is_white = (game.white == player_name)
            summary = game_summaries[i]
            
            # Check if player was in a losing position
            had_losing_position = False
            defensive_blunders = 0
            
            # Get moves for this game
            moves = self.game_controller.extract_moves_from_game(game)
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
                else:
                    # Black's move: ply_index before = (move_num - 1) * 2 + 1
                    ply_before = (move_num - 1) * 2 + 1
                    eval_before = eval_dict.get(ply_before)
                    if eval_before is not None and eval_before >= -losing_threshold:
                        had_losing_position = True
                        if move.assess_black == "Blunder":
                            defensive_blunders += 1
            
            if had_losing_position and defensive_blunders >= 2:
                defensive_errors += 1
                related_games.append(game)
        
        if defensive_errors > 0:
            defensive_rate = (defensive_errors / len(games) * 100) if games else 0.0
            if defensive_rate >= self.thresholds.get('defensive_weakness_threshold', 20.0):
                severity = self._determine_severity(defensive_rate, [25, 35, 45])
                patterns.append(ErrorPattern(
                    pattern_type="defensive_weaknesses",
                    description=f"Struggles when defending ({defensive_errors} games with multiple blunders)",
                    frequency=defensive_errors,
                    percentage=defensive_rate,
                    severity=severity,
                    related_games=related_games
                ))
        
        return patterns
    
    def _detect_consistent_inaccuracies(self, player_name: str,
                                       aggregated_stats: Any) -> List[ErrorPattern]:
        """Detect patterns of many small errors (inaccuracies)."""
        patterns: List[ErrorPattern] = []
        
        inaccuracies = aggregated_stats.player_stats.inaccuracies
        total_moves = aggregated_stats.player_stats.total_moves
        
        if total_moves == 0:
            return patterns
        
        inaccuracy_rate = (inaccuracies / total_moves * 100)
        inaccuracy_threshold = self.thresholds.get('inaccuracy_rate_threshold', 25.0)
        
        if inaccuracy_rate >= inaccuracy_threshold:
            severity = self._determine_severity(inaccuracy_rate, [30, 40, 50])
            patterns.append(ErrorPattern(
                pattern_type="consistent_inaccuracies",
                description=f"Many small errors ({inaccuracy_rate:.1f}% of moves are inaccuracies)",
                frequency=inaccuracies,
                percentage=inaccuracy_rate,
                severity=severity,
                related_games=[]  # Would need individual game analysis for specific instances
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


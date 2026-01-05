"""Game summary service for calculating game statistics from analysis data."""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from asteval import Interpreter

from app.models.moveslist_model import MoveData
from app.models.move_classification_model import MoveClassificationModel
from app.services.game_highlights.base_rule import GameHighlight


@dataclass
class PlayerStatistics:
    """Statistics for a single player (White or Black)."""
    total_moves: int
    analyzed_moves: int
    book_moves: int
    brilliant_moves: int
    best_moves: int
    good_moves: int
    inaccuracies: int
    mistakes: int
    misses: int
    blunders: int
    average_cpl: float
    median_cpl: float
    min_cpl: float
    max_cpl: float
    accuracy: float
    estimated_elo: int
    best_move_percentage: float
    top3_move_percentage: float
    blunder_rate: float


@dataclass
class PhaseStatistics:
    """Statistics for a game phase (Opening, Middlegame, Endgame)."""
    moves: int
    average_cpl: float
    accuracy: float
    book_moves: int
    brilliant_moves: int
    best_moves: int
    good_moves: int
    inaccuracies: int
    mistakes: int
    misses: int
    blunders: int


@dataclass
class CriticalMove:
    """Represents a critical move (best or worst)."""
    move_number: int
    move_notation: str
    cpl: float
    assessment: str
    evaluation: str
    best_move: str = ""  # Best alternative move suggested by engine


@dataclass
class GameSummary:
    """Complete game summary statistics."""
    white_stats: PlayerStatistics
    black_stats: PlayerStatistics
    white_opening: PhaseStatistics
    white_middlegame: PhaseStatistics
    white_endgame: PhaseStatistics
    black_opening: PhaseStatistics
    black_middlegame: PhaseStatistics
    black_endgame: PhaseStatistics
    white_top_worst: List[CriticalMove]
    white_top_best: List[CriticalMove]
    black_top_worst: List[CriticalMove]
    black_top_best: List[CriticalMove]
    evaluation_data: List[Tuple[int, float]]  # (move_number, evaluation) pairs
    opening_end: int  # Move number where opening phase ends
    middlegame_end: int  # Move number where middlegame phase ends
    endgame_type: Optional[str]  # Endgame type: "Pawn-Endgame", "Minor Piece-Endgame", "Rook-Endgame", "Queen-Endgame", "Endgame", or None
    highlights: List[GameHighlight]  # Game highlights (key moments and facts)


class GameSummaryService:
    """Service for calculating game summary statistics from analysis data."""
    
    def __init__(self, config: Dict[str, Any], classification_model: Optional[MoveClassificationModel] = None) -> None:
        """Initialize the game summary service.
        
        Args:
            config: Configuration dictionary.
            classification_model: Optional MoveClassificationModel instance for classification settings.
        """
        self.config = config
        self.classification_model = classification_model
        
        # Get assessment thresholds from model or config
        if self.classification_model:
            self.good_move_max_cpl = self.classification_model.good_move_max_cpl
            self.inaccuracy_max_cpl = self.classification_model.inaccuracy_max_cpl
            self.mistake_max_cpl = self.classification_model.mistake_max_cpl
        else:
            # Fallback to config if no model provided
            game_analysis_config = config.get('game_analysis', {})
            thresholds = game_analysis_config.get('assessment_thresholds', {})
            self.good_move_max_cpl = thresholds.get('good_move_max_cpl', 50)
            self.inaccuracy_max_cpl = thresholds.get('inaccuracy_max_cpl', 100)
            self.mistake_max_cpl = thresholds.get('mistake_max_cpl', 200)
        
        # Get phase analysis config
        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        phase_config = summary_config.get('phase_analysis', {})
        self.opening_moves = phase_config.get('opening_moves', 15)
        self.endgame_moves = phase_config.get('endgame_moves', 10)
        
        # Get highlights config
        highlights_config = summary_config.get('highlights', {})
        self.highlights_per_phase_limit = highlights_config.get('max_per_phase', 7)
    
    def _evaluate_accuracy_formula(self, **kwargs) -> float:
        """Evaluate accuracy formula using asteval.
        
        Args:
            **kwargs: All available variables for the formula.
            
        Returns:
            Calculated accuracy value (0.0 to 100.0).
        """
        game_analysis_config = self.config.get('game_analysis', {})
        accuracy_config = game_analysis_config.get('accuracy_formula', {})
        formula = accuracy_config.get('formula', None)
        value_on_error = accuracy_config.get('value_on_error', 0.0)
        
        # Default formula (current hardcoded one)
        default_formula = "max(5.0, min(100.0, 100.0 - (average_cpl / 3.5)))"
        
        formula_to_use = formula if formula else default_formula
        
        try:
            aeval = Interpreter()
            # Set variables in the symtable
            for key, value in kwargs.items():
                aeval.symtable[key] = value
            # Add built-in functions
            aeval.symtable['min'] = min
            aeval.symtable['max'] = max
            # Evaluate the formula
            result = aeval(formula_to_use)
            if result is None:
                return float(value_on_error)
            accuracy = float(result)
            # Clamp to reasonable range
            return max(0.0, min(100.0, accuracy))
        except Exception as e:
            # Log error for debugging
            import sys
            print(f"Error evaluating accuracy formula: {e}", file=sys.stderr)
            return float(value_on_error)
    
    def _evaluate_elo_formula(self, **kwargs) -> int:
        """Evaluate ELO formula using asteval.
        
        Args:
            **kwargs: All available variables for the formula.
            
        Returns:
            Calculated ELO value (clamped to >= 0).
        """
        game_analysis_config = self.config.get('game_analysis', {})
        elo_config = game_analysis_config.get('elo_estimation', {})
        formula = elo_config.get('formula', None)
        value_on_error = elo_config.get('value_on_error', 0)
        
        # Default formula (current hardcoded one)
        default_formula = "max(0, int(2800 - (average_cpl * 8.5) - ((blunder_rate * 50 + mistake_rate * 20) * 40)))"
        
        formula_to_use = formula if formula else default_formula
        
        try:
            aeval = Interpreter()
            # Set variables in the symtable
            for key, value in kwargs.items():
                aeval.symtable[key] = value
            # Add built-in functions
            aeval.symtable['min'] = min
            aeval.symtable['max'] = max
            aeval.symtable['int'] = int
            # Evaluate the formula
            result = aeval(formula_to_use)
            if result is None:
                return int(value_on_error)
            estimated_elo = int(result)
            # Clamp to >= 0 
            return max(0, estimated_elo)
        except Exception as e:
            # Log error for debugging
            import sys
            print(f"Error evaluating ELO formula: {e}", file=sys.stderr)
            return int(value_on_error)
    
    def calculate_summary(self, moves: List[MoveData], total_moves: int, game_result: Optional[str] = None) -> GameSummary:
        """Calculate complete game summary from moves data.
        
        Args:
            moves: List of MoveData instances from MovesListModel.
            total_moves: Total number of moves in the game.
            
        Returns:
            GameSummary instance with all calculated statistics.
        """
        # Calculate player statistics
        white_stats = self._calculate_player_statistics(moves, is_white=True, game_result=game_result)
        black_stats = self._calculate_player_statistics(moves, is_white=False, game_result=game_result)
        
        # Determine phase boundaries (same for both players - game-level concept)
        opening_end, middlegame_end = self._determine_phase_boundaries(moves, total_moves)
        
        # Classify endgame type - check all moves in the endgame phase to find the most specific type
        endgame_type: Optional[str] = None
        if middlegame_end <= total_moves:
            # Check all moves from middlegame_end onwards to find the most specific endgame type
            # This ensures we catch more specific rules that might match later in the endgame
            for move in moves:
                if move.move_number >= middlegame_end:
                    move_endgame_type = self._classify_endgame_type(move)
                    if move_endgame_type is not None:
                        # If we haven't found a type yet, or if this is more specific than the current one
                        # (more specific = not "Endgame" catch-all)
                        if endgame_type is None:
                            endgame_type = move_endgame_type
                        elif endgame_type == "Endgame" and move_endgame_type != "Endgame":
                            # Found a more specific type, use it
                            endgame_type = move_endgame_type
                        # If we already have a specific type, keep it (don't downgrade to catch-all)
                        elif endgame_type != "Endgame" and move_endgame_type == "Endgame":
                            # Keep the more specific type we already found
                            pass
        
        # Calculate phase statistics for each player
        white_opening, white_middlegame, white_endgame = self._calculate_phase_statistics(
            moves, total_moves, is_white=True, opening_end=opening_end, middlegame_end=middlegame_end
        )
        black_opening, black_middlegame, black_endgame = self._calculate_phase_statistics(
            moves, total_moves, is_white=False, opening_end=opening_end, middlegame_end=middlegame_end
        )
        
        # Find critical moves
        white_top_worst = self._find_top_worst_moves(moves, is_white=True, count=3)
        white_top_best = self._find_top_best_moves(moves, is_white=True, count=3)
        black_top_worst = self._find_top_worst_moves(moves, is_white=False, count=3)
        black_top_best = self._find_top_best_moves(moves, is_white=False, count=3)
        
        # Extract evaluation data for graph
        evaluation_data = self._extract_evaluation_data(moves)
        
        # Detect game highlights
        # Use new highlight detector
        from app.services.game_highlights.rule_registry import RuleRegistry
        from app.services.game_highlights.highlight_detector import HighlightDetector
        
        highlights_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('summary', {}).get('highlights', {})
        rule_config = highlights_config.get('rules', {})
        
        rule_registry = RuleRegistry({'rules': rule_config})
        highlight_detector = HighlightDetector(
            {'highlights_per_phase_limit': self.highlights_per_phase_limit}, 
            rule_registry,
            good_move_max_cpl=self.good_move_max_cpl,
            inaccuracy_max_cpl=self.inaccuracy_max_cpl,
            mistake_max_cpl=self.mistake_max_cpl
        )
        highlights = highlight_detector.detect_highlights(moves, total_moves, opening_end, middlegame_end)
        
        return GameSummary(
            white_stats=white_stats,
            black_stats=black_stats,
            white_opening=white_opening,
            white_middlegame=white_middlegame,
            white_endgame=white_endgame,
            black_opening=black_opening,
            black_middlegame=black_middlegame,
            black_endgame=black_endgame,
            white_top_worst=white_top_worst,
            white_top_best=white_top_best,
            black_top_worst=black_top_worst,
            black_top_best=black_top_best,
            evaluation_data=evaluation_data,
            opening_end=opening_end,
            middlegame_end=middlegame_end,
            endgame_type=endgame_type,
            highlights=highlights
        )
    
    def _calculate_player_statistics(self, moves: List[MoveData], is_white: bool, game_result: Optional[str] = None) -> PlayerStatistics:
        """Calculate statistics for a single player.
        
        Args:
            moves: List of MoveData instances.
            is_white: True for White, False for Black.
            game_result: Optional game result string ("1-0", "0-1", "1/2-1/2", "", "*", or None).
            
        Returns:
            PlayerStatistics instance.
        """
        # Get relevant fields based on player
        if is_white:
            cpl_field = 'cpl_white'
            assess_field = 'assess_white'
            move_field = 'white_move'
            is_top3_field = 'white_is_top3'
        else:
            cpl_field = 'cpl_black'
            assess_field = 'assess_black'
            move_field = 'black_move'
            is_top3_field = 'black_is_top3'
        
        # Count moves and classifications
        total_moves = 0
        non_book_moves = 0  # All moves except book moves (renamed from analyzed_moves)
        book_moves = 0
        brilliant_moves = 0
        best_moves = 0
        top3_moves = 0
        good_moves = 0
        inaccuracies = 0
        mistakes = 0
        misses = 0
        blunders = 0
        
        cpl_values: List[float] = []
        
        for move in moves:
            move_str = getattr(move, move_field)
            if not move_str:  # Skip empty moves
                continue
            
            total_moves += 1
            assessment = getattr(move, assess_field)
            cpl_str = getattr(move, cpl_field)
            is_top3 = getattr(move, is_top3_field, False)
            
            # Count top3 moves (excluding book moves)
            if is_top3 and assessment != "Book Move":
                top3_moves += 1
            
            # Count classifications
            if assessment == "Book Move":
                book_moves += 1
            elif assessment == "Brilliant":
                brilliant_moves += 1
                non_book_moves += 1
            elif assessment == "Best Move":
                best_moves += 1
                non_book_moves += 1
            elif assessment == "Good Move":
                good_moves += 1
                non_book_moves += 1
            elif assessment == "Inaccuracy":
                inaccuracies += 1
                non_book_moves += 1
            elif assessment == "Mistake":
                mistakes += 1
                non_book_moves += 1
            elif assessment == "Miss":
                misses += 1
                non_book_moves += 1
            elif assessment == "Blunder":
                blunders += 1
                non_book_moves += 1
            
            # Parse CPL (exclude book moves)
            if cpl_str and assessment != "Book Move":
                try:
                    cpl = float(cpl_str)
                    cpl_values.append(cpl)
                except (ValueError, TypeError):
                    pass
        
        # Calculate CPL statistics
        # Cap very high CPL values (e.g., from blunders leading to mate) to prevent skewing the average
        # A reasonable cap is 500 centipawns - represents a catastrophic blunder but not infinite loss
        CPL_CAP_FOR_AVERAGE = 500.0  # Cap CPL at 500 centipawns for average calculation
        if cpl_values:
            cpl_values_sorted = sorted(cpl_values)
            # Cap CPL values when calculating average to prevent extreme outliers from skewing results
            capped_cpl_values = [min(cpl, CPL_CAP_FOR_AVERAGE) for cpl in cpl_values]
            average_cpl = sum(capped_cpl_values) / len(capped_cpl_values)
            # Calculate median correctly
            n = len(cpl_values_sorted)
            if n % 2 == 0:
                median_cpl = (cpl_values_sorted[n // 2 - 1] + cpl_values_sorted[n // 2]) / 2.0
            else:
                median_cpl = cpl_values_sorted[n // 2]
            min_cpl = min(cpl_values)
            max_cpl = max(cpl_values)
        else:
            average_cpl = 0.0
            median_cpl = 0.0
            min_cpl = 0.0
            max_cpl = 0.0
        
        # Calculate game result variables
        if is_white:
            has_won = 1 if game_result == "1-0" else 0
            has_drawn = 1 if (game_result == "1/2-1/2" or not game_result or game_result == "*") else 0
        else:
            has_won = 1 if game_result == "0-1" else 0
            has_drawn = 1 if (game_result == "1/2-1/2" or not game_result or game_result == "*") else 0
        
        # Calculate rates
        if total_moves > 0:
            blunder_rate = blunders / total_moves
            mistake_rate = mistakes / total_moves
        else:
            blunder_rate = 0.0
            mistake_rate = 0.0
        
        # Calculate accuracy using customizable formula
        accuracy = self._evaluate_accuracy_formula(
            average_cpl=average_cpl,
            total_moves=total_moves,
            non_book_moves=non_book_moves,
            book_moves=book_moves,
            blunders=blunders,
            mistakes=mistakes,
            inaccuracies=inaccuracies,
            misses=misses,
            best_moves=best_moves,
            good_moves=good_moves,
            brilliant_moves=brilliant_moves,
            median_cpl=median_cpl,
            min_cpl=min_cpl,
            max_cpl=max_cpl,
            blunder_rate=blunder_rate,
            mistake_rate=mistake_rate,
            has_won=has_won,
            has_drawn=has_drawn
        )
        
        # Calculate estimated ELO using customizable formula
        estimated_elo = self._evaluate_elo_formula(
            average_cpl=average_cpl,
            total_moves=total_moves,
            non_book_moves=non_book_moves,
            book_moves=book_moves,
            blunders=blunders,
            mistakes=mistakes,
            inaccuracies=inaccuracies,
            misses=misses,
            best_moves=best_moves,
            good_moves=good_moves,
            brilliant_moves=brilliant_moves,
            median_cpl=median_cpl,
            min_cpl=min_cpl,
            max_cpl=max_cpl,
            blunder_rate=blunder_rate,
            mistake_rate=mistake_rate,
            accuracy=accuracy,
            has_won=has_won,
            has_drawn=has_drawn
        )
        
        # Calculate percentages
        best_move_percentage = (best_moves / total_moves * 100) if total_moves > 0 else 0.0
        top3_move_percentage = (top3_moves / total_moves * 100) if total_moves > 0 else 0.0
        blunder_rate_percentage = (blunders / total_moves * 100) if total_moves > 0 else 0.0
        
        return PlayerStatistics(
            total_moves=total_moves,
            analyzed_moves=non_book_moves,  # Keep field name for backward compatibility
            book_moves=book_moves,
            brilliant_moves=brilliant_moves,
            best_moves=best_moves,
            good_moves=good_moves,
            inaccuracies=inaccuracies,
            mistakes=mistakes,
            misses=misses,
            blunders=blunders,
            average_cpl=average_cpl,
            median_cpl=median_cpl,
            min_cpl=min_cpl,
            max_cpl=max_cpl,
            accuracy=accuracy,
            estimated_elo=estimated_elo,
            best_move_percentage=best_move_percentage,
            top3_move_percentage=top3_move_percentage,
            blunder_rate=blunder_rate_percentage
        )
    
    def _determine_phase_boundaries(self, moves: List[MoveData], total_moves: int) -> Tuple[int, int]:
        """Determine phase boundaries for the game (same for both players).
        
        Args:
            moves: List of MoveData instances.
            total_moves: Total number of moves in the game.
            
        Returns:
            Tuple of (opening_end, middlegame_end) move numbers.
        """
        # Determine opening phase end using new rules:
        # 1. Find last book move (check both white and black)
        # 2. Find first non-pawn capture (check both white and black)
        # 3. Opening ends at: max(last_book_move_number + 1, first_non_pawn_capture_move_number) if non-pawn capture exists
        #    OR opening_moves if no non-pawn capture exists
        last_book_move_number = 0
        first_non_pawn_capture_move_number = 0
        
        for move in moves:
            move_num = move.move_number
            
            # Check if white's move is a book move
            if move.white_move and move.assess_white == "Book Move":
                last_book_move_number = max(last_book_move_number, move_num)
            
            # Check if black's move is a book move
            if move.black_move and move.assess_black == "Book Move":
                last_book_move_number = max(last_book_move_number, move_num)
            
            # Check if white's move has a non-pawn capture
            if move.white_capture and move.white_capture in ["r", "n", "b", "q"]:
                if first_non_pawn_capture_move_number == 0:
                    first_non_pawn_capture_move_number = move_num
            
            # Check if black's move has a non-pawn capture
            if move.black_capture and move.black_capture in ["r", "n", "b", "q"]:
                if first_non_pawn_capture_move_number == 0:
                    first_non_pawn_capture_move_number = move_num
        
        # Determine opening end
        if first_non_pawn_capture_move_number > 0:
            # Non-pawn capture exists - opening ends at max of last book move + 1 and first non-pawn capture
            opening_end = max(last_book_move_number + 1, first_non_pawn_capture_move_number)
        else:
            # No non-pawn capture exists - use move count threshold
            opening_end = self.opening_moves
        
        # Determine middlegame end using the new ruleset
        # Check each move to see if it meets any endgame criteria
        middlegame_end = total_moves + 1  # Default: no endgame (all moves are middlegame)
        
        for move in moves:
            move_num = move.move_number
            
            # Classify endgame type for this position
            # This returns a specific type if it's an endgame, or None if not
            endgame_type = self._classify_endgame_type(move)
            
            # If this position is classified as an endgame (any type), middlegame ends here
            if endgame_type is not None:
                middlegame_end = move_num
                break
        
        return (opening_end, middlegame_end)
    
    def _classify_endgame_type(self, move: MoveData) -> Optional[str]:
        """Classify endgame type based on piece counts.
        
        Args:
            move: MoveData instance with piece counts.
            
        Returns:
            Endgame type string: "Pawn", "Minor Piece", "Rook", "Queen", "Heavy Piece",
            "Asymmetric Heavy Piece", "Strong Material Imbalance", "Transitional" (late middlegame
            with reduced material), "Endgame" (catch-all for simplified positions), or None if not an endgame.
        """
        # Get piece counts for both sides
        w_q = move.white_queens
        w_r = move.white_rooks
        w_b = move.white_bishops
        w_n = move.white_knights
        w_p = move.white_pawns
        
        b_q = move.black_queens
        b_r = move.black_rooks
        b_b = move.black_bishops
        b_n = move.black_knights
        b_p = move.black_pawns
        
        # Calculate non-pawn material (in points, not centipawns)
        # Piece values: Q=9, R=5, B=3, N=3, P=1
        w_non_pawn = w_q * 9 + w_r * 5 + w_b * 3 + w_n * 3
        b_non_pawn = b_q * 9 + b_r * 5 + b_b * 3 + b_n * 3
        
        # Calculate minor pieces (bishops + knights)
        w_minors = w_b + w_n
        b_minors = b_b + b_n
        
        # Rule 1: Pawn-Only Endgame
        # Both sides have no queens, no rooks, no bishops, no knights
        if (w_q == 0 and w_r == 0 and w_b == 0 and w_n == 0 and
            b_q == 0 and b_r == 0 and b_b == 0 and b_n == 0):
            return "Pawn"
        
        # Rule 2: Minor Piece Endgame
        # No queens, no rooks, each side has ≤ 1 minor piece, remaining material ≤ 6 points per side
        if (w_q == 0 and w_r == 0 and b_q == 0 and b_r == 0 and
            w_minors <= 1 and b_minors <= 1 and
            w_non_pawn <= 6 and b_non_pawn <= 6):
            return "Minor Piece"
        
        # Rule 2.75: Two Minor Piece Endgame
        # No queens, no rooks, each side has exactly 2 minor pieces (any combination of bishops/knights)
        # Total non-pawn material per side is ≤ 6 points (2 minors = 6)
        # This catches positions like: bishop pair vs bishop pair, knight pair vs knight pair,
        # bishop + knight vs bishop + knight, etc.
        if (w_q == 0 and w_r == 0 and b_q == 0 and b_r == 0 and
            w_minors == 2 and b_minors == 2 and
            w_non_pawn <= 6 and b_non_pawn <= 6):
            return "Two Minor Piece"
        
        # Rule 2.95: Rook + Two Minor Piece Endgame
        # No queens, exactly 1 rook per side, exactly 2 minor pieces per side (any combination: 2 bishops, 2 knights, or 1 bishop + 1 knight)
        # Total non-pawn material per side is ≤ 11 points (rook = 5 + 2 minors = 6, total = 11)
        # This catches positions like: rook + bishop + knight vs rook + bishop + knight,
        # rook + 2 knights vs rook + 2 knights, rook + 2 bishops vs rook + 2 bishops
        if (w_q == 0 and b_q == 0 and w_r == 1 and b_r == 1 and
            w_minors == 2 and b_minors == 2 and
            w_non_pawn <= 11 and b_non_pawn <= 11):
            return "Rook + Two Minor Piece"
        
        # Rule 2.97: Rook vs Rook (Unequal Minors) Endgame
        # No queens, exactly 1 rook per side
        # One side has exactly 2 minor pieces, the other side has exactly 1 minor piece
        # Material thresholds:
        #   Side with 2 minors: ≤14 non-pawn points (rook = 5 + 2 minors = 6, total = 11, allows up to 14 for flexibility)
        #   Side with 1 minor: ≤10 non-pawn points (rook = 5 + 1 minor = 3, total = 8, allows up to 10 for flexibility)
        # This catches positions like: rook + bishop + knight vs rook + knight,
        # rook + two knights vs rook + bishop, rook + bishop + knight vs rook + bishop
        if (w_q == 0 and b_q == 0 and w_r == 1 and b_r == 1):
            # Check if one side has 2 minors and the other has 1 minor
            if w_minors == 2 and b_minors == 1:
                # White has 2 minors, Black has 1 minor
                if w_non_pawn <= 14 and b_non_pawn <= 10:
                    return "Rook vs Rook (Unequal Minors)"
            elif w_minors == 1 and b_minors == 2:
                # White has 1 minor, Black has 2 minors
                if w_non_pawn <= 10 and b_non_pawn <= 14:
                    return "Rook vs Rook (Unequal Minors)"
        
        # Rule 2.5: Rook vs Minor Piece Endgame
        # No queens, one side has exactly 1 rook, the other side has no rooks but exactly 1 minor piece
        # Total non-pawn material per side is ≤ 8 points
        # This catches positions like: rook + pawns vs bishop + pawns, rook + pawns vs knight + pawns
        if (w_q == 0 and b_q == 0 and
            ((w_r == 1 and b_r == 0 and b_minors == 1 and w_minors == 0) or
             (b_r == 1 and w_r == 0 and w_minors == 1 and b_minors == 0)) and
            w_non_pawn <= 8 and b_non_pawn <= 8):
            return "Rook vs Minor Piece"
        
        # Rule 3: Rook Endgame
        # No queens, at least one rook, each side has ≤ 1 minor piece, total non-pawn material ≤ 10 points per side
        if (w_q == 0 and b_q == 0 and (w_r > 0 or b_r > 0) and
            w_minors <= 1 and b_minors <= 1 and
            w_non_pawn <= 10 and b_non_pawn <= 10):
            return "Rook"
        
        # Rule 3.25: Double Rook Endgame
        # No queens, exactly 2 rooks per side, each side has ≤ 1 minor piece, total non-pawn material ≤ 15 points per side
        # This catches positions like: two rooks vs two rooks, two rooks + one minor vs two rooks + one minor
        if (w_q == 0 and b_q == 0 and w_r == 2 and b_r == 2 and
            w_minors <= 1 and b_minors <= 1 and
            w_non_pawn <= 15 and b_non_pawn <= 15):
            return "Double Rook"
        
        # Rule 3.5: Rook + Minor Piece Endgame
        # No queens, at least one rook, each side has ≤ 1 minor piece, total non-pawn material ≤ 13 points per side
        # This catches positions like: two rooks + one minor vs two rooks + one minor (with pawns)
        # Note: This rule applies to positions that don't match Rule 3.25 (Double Rook Endgame)
        if (w_q == 0 and b_q == 0 and (w_r > 0 or b_r > 0) and
            w_minors <= 1 and b_minors <= 1 and
            w_non_pawn <= 13 and b_non_pawn <= 13):
            return "Rook + Minor Piece"
        
        # Rule 3.75: Heavy Piece Endgame
        # At least one queen per side, at least one rook per side, each side has ≤ 1 minor piece
        # Symmetric minors (both sides have the same minor count) to avoid overlap with Rule 3.7
        # Total non-pawn material per side is ≤ 15 points (increased from 14 to catch edge cases)
        # This catches positions like: queen + rook vs queen + rook + pawns
        if (w_q > 0 and b_q > 0 and w_r > 0 and b_r > 0 and
            w_minors <= 1 and b_minors <= 1 and
            w_minors == b_minors and  # Symmetric minors to avoid overlap with Rule 3.7
            w_non_pawn <= 15 and b_non_pawn <= 15):
            return "Heavy Piece"
        
        # Rule 3.7: Asymmetric Heavy Piece Endgame
        # At least one queen per side
        # Either: both sides have rooks (asymmetric minors), OR only one side has rooks
        # Each side has ≤1 minor piece
        # Thresholds based on piece composition:
        #   - Queen only (no rooks): ≤12 points
        #   - Queen + Rook (no minors): ≤14 points
        #   - Queen + Rook + Minor: ≤17 points
        # This catches positions like: queen + rook vs queen + rook + minor, queen vs queen + rook
        if (w_q > 0 and b_q > 0 and w_minors <= 1 and b_minors <= 1):
            # Case 1: Both sides have rooks (asymmetric minors)
            if (w_r > 0 and b_r > 0 and
                ((w_minors == 0 and b_minors <= 1) or (b_minors == 0 and w_minors <= 1))):
                # Check thresholds based on minor count for each side
                w_threshold_ok = (w_minors == 0 and w_non_pawn <= 14) or (w_minors <= 1 and w_non_pawn <= 17)
                b_threshold_ok = (b_minors == 0 and b_non_pawn <= 14) or (b_minors <= 1 and b_non_pawn <= 17)
                if w_threshold_ok and b_threshold_ok:
                    return "Asymmetric Heavy Piece"
            # Case 2: Only one side has rooks
            elif ((w_r > 0 and b_r == 0) or (w_r == 0 and b_r > 0)):
                # Check thresholds based on piece composition for each side
                # Side with queen only (no rooks): ≤12 points
                # Side with queen + rook: ≤14 points (no minors) or ≤17 points (with minor)
                w_threshold_ok = False
                b_threshold_ok = False
                
                if w_r == 0:
                    # White has queen only (no rooks)
                    w_threshold_ok = w_non_pawn <= 12
                else:
                    # White has queen + rook
                    w_threshold_ok = (w_minors == 0 and w_non_pawn <= 14) or (w_minors <= 1 and w_non_pawn <= 17)
                
                if b_r == 0:
                    # Black has queen only (no rooks)
                    b_threshold_ok = b_non_pawn <= 12
                else:
                    # Black has queen + rook
                    b_threshold_ok = (b_minors == 0 and b_non_pawn <= 14) or (b_minors <= 1 and b_non_pawn <= 17)
                
                if w_threshold_ok and b_threshold_ok:
                    return "Asymmetric Heavy Piece"
        
        # Rule 4: Queen Endgame
        # At least one queen, no rooks, each side has ≤ 1 minor piece, total non-pawn material ≤ 12 points per side
        if ((w_q > 0 or b_q > 0) and w_r == 0 and b_r == 0 and
            w_minors <= 1 and b_minors <= 1 and
            w_non_pawn <= 12 and b_non_pawn <= 12):
            return "Queen"
        
        # Rule 4.5: Queen + Two Minor Piece Endgame
        # At least one queen per side, no rooks, exactly 2 minor pieces per side (any combination: 2 bishops, 2 knights, or 1 bishop + 1 knight)
        # Total non-pawn material per side is ≤ 15 points (queen = 9 + 2 minors = 6, total = 15)
        # This catches positions like: queen + 2 bishops vs queen + 2 bishops,
        # queen + 2 knights vs queen + 2 knights, queen + bishop + knight vs queen + bishop + knight
        if (w_q > 0 and b_q > 0 and w_r == 0 and b_r == 0 and
            w_minors == 2 and b_minors == 2 and
            w_non_pawn <= 15 and b_non_pawn <= 15):
            return "Queen + Two Minor Piece"
        
        # Rule 4.75: Strong Material Imbalance Endgame
        # One side has very low material (≤8 points) while the other side has moderate material (≤30 points)
        # This catches asymmetric endgames where one side is clearly in an endgame situation
        # (trying to convert/defend) even if the other side has more material
        # Examples: 1 rook vs 2 queens, 1 queen vs 2 queens + rooks, etc.
        # Threshold of 30 for the stronger side catches cases like 2 queens + 2 rooks (28 points)
        # while avoiding middlegame positions with excessive material
        if ((w_non_pawn <= 8 and b_non_pawn <= 30) or (b_non_pawn <= 8 and w_non_pawn <= 30)):
            return "Strong Material Imbalance"
        
        # Rule 5: Material Threshold Catch-All
        # Regardless of piece types, if non-pawn material ≤ 15 points per side
        # Only applies if the more specific rules above don't match
        # Threshold increased to ≤15 points to match the highest specific rule threshold
        if w_non_pawn <= 15 and b_non_pawn <= 15:
            # Distinguish between true endgames and transitional positions
            # If queens are present, classify as "Transitional" (late middlegame/transition)
            # True endgames typically have no queens and simplified positions
            if w_q > 0 or b_q > 0:
                return "Transitional"
            else:
                return "Endgame"
        
        # Not an endgame
        return None
    
    def _calculate_phase_statistics(self, moves: List[MoveData], total_moves: int, 
                                    is_white: bool, opening_end: int, middlegame_end: int) -> Tuple[PhaseStatistics, PhaseStatistics, PhaseStatistics]:
        """Calculate statistics for each game phase.
        
        Args:
            moves: List of MoveData instances.
            total_moves: Total number of moves in the game.
            is_white: True for White, False for Black.
            opening_end: Move number where opening phase ends.
            middlegame_end: Move number where middlegame phase ends.
            
        Returns:
            Tuple of (opening, middlegame, endgame) PhaseStatistics.
        """
        # Get relevant fields
        if is_white:
            cpl_field = 'cpl_white'
            assess_field = 'assess_white'
            move_field = 'white_move'
        else:
            cpl_field = 'cpl_black'
            assess_field = 'assess_black'
            move_field = 'black_move'
        
        # Collect moves for each phase
        opening_moves: List[MoveData] = []
        middlegame_moves: List[MoveData] = []
        endgame_moves: List[MoveData] = []
        
        for move in moves:
            move_num = move.move_number
            move_str = getattr(move, move_field)
            if not move_str:
                continue
            
            if move_num <= opening_end:
                opening_moves.append(move)
            elif move_num < middlegame_end:
                middlegame_moves.append(move)
            else:
                endgame_moves.append(move)
        
        # Calculate statistics for each phase
        opening = self._calculate_phase_stats(opening_moves, cpl_field, assess_field)
        middlegame = self._calculate_phase_stats(middlegame_moves, cpl_field, assess_field)
        endgame = self._calculate_phase_stats(endgame_moves, cpl_field, assess_field)
        
        return (opening, middlegame, endgame)
    
    def _calculate_phase_stats(self, phase_moves: List[MoveData], 
                               cpl_field: str, assess_field: str) -> PhaseStatistics:
        """Calculate statistics for a single phase.
        
        Args:
            phase_moves: List of MoveData instances for this phase.
            cpl_field: Field name for CPL ('cpl_white' or 'cpl_black').
            assess_field: Field name for assessment ('assess_white' or 'assess_black').
            
        Returns:
            PhaseStatistics instance.
        """
        moves_count = len(phase_moves)
        book_moves = 0
        brilliant_moves = 0
        best_moves = 0
        good_moves = 0
        inaccuracies = 0
        mistakes = 0
        misses = 0
        blunders = 0
        
        cpl_values: List[float] = []
        
        for move in phase_moves:
            assessment = getattr(move, assess_field)
            cpl_str = getattr(move, cpl_field)
            
            # Count classifications
            if assessment == "Book Move":
                book_moves += 1
            elif assessment == "Brilliant":
                brilliant_moves += 1
            elif assessment == "Best Move":
                best_moves += 1
            elif assessment == "Good Move":
                good_moves += 1
            elif assessment == "Inaccuracy":
                inaccuracies += 1
            elif assessment == "Mistake":
                mistakes += 1
            elif assessment == "Miss":
                misses += 1
            elif assessment == "Blunder":
                blunders += 1
            
            # Parse CPL (exclude book moves)
            if cpl_str and assessment != "Book Move":
                try:
                    cpl = float(cpl_str)
                    cpl_values.append(cpl)
                except (ValueError, TypeError):
                    pass
        
        # Calculate average CPL
        # Cap very high CPL values (e.g., from blunders leading to mate) to prevent skewing the average
        CPL_CAP_FOR_AVERAGE = 500.0  # Cap CPL at 500 centipawns for average calculation
        if cpl_values:
            # Cap CPL values when calculating average to prevent extreme outliers from skewing results
            capped_cpl_values = [min(cpl, CPL_CAP_FOR_AVERAGE) for cpl in cpl_values]
            average_cpl = sum(capped_cpl_values) / len(capped_cpl_values)
        else:
            average_cpl = 0.0
        
        # Calculate accuracy (improved formula: uses larger divisor and minimum floor)
        # Formula: max(5.0, 100.0 - ACPL/3.5) ensures minimum 5% accuracy for reasonable play
        accuracy = max(5.0, min(100.0, 100.0 - (average_cpl / 3.5)))
        
        return PhaseStatistics(
            moves=moves_count,
            average_cpl=average_cpl,
            accuracy=accuracy,
            book_moves=book_moves,
            brilliant_moves=brilliant_moves,
            best_moves=best_moves,
            good_moves=good_moves,
            inaccuracies=inaccuracies,
            mistakes=mistakes,
            misses=misses,
            blunders=blunders
        )
    
    def _find_top_worst_moves(self, moves: List[MoveData], is_white: bool, count: int) -> List[CriticalMove]:
        """Find top N worst moves (highest CPL).
        
        Args:
            moves: List of MoveData instances.
            is_white: True for White, False for Black.
            count: Number of moves to return.
            
        Returns:
            List of CriticalMove instances sorted by CPL descending.
        """
        if is_white:
            cpl_field = 'cpl_white'
            assess_field = 'assess_white'
            eval_field = 'eval_white'
            move_field = 'white_move'
            best_field = 'best_white'
        else:
            cpl_field = 'cpl_black'
            assess_field = 'assess_black'
            eval_field = 'eval_black'
            move_field = 'black_move'
            best_field = 'best_black'
        
        critical_moves: List[CriticalMove] = []
        
        for move in moves:
            move_str = getattr(move, move_field)
            if not move_str:
                continue
            
            cpl_str = getattr(move, cpl_field)
            if not cpl_str:
                continue
            
            try:
                cpl = float(cpl_str)
                assessment = getattr(move, assess_field)
                evaluation = getattr(move, eval_field)
                best_move = getattr(move, best_field, "") or ""
                
                # Format move notation (e.g., "23. Qd4")
                move_notation = f"{move.move_number}. {move_str}"
                
                critical_moves.append(CriticalMove(
                    move_number=move.move_number,
                    move_notation=move_notation,
                    cpl=cpl,
                    assessment=assessment,
                    evaluation=evaluation,
                    best_move=best_move
                ))
            except (ValueError, TypeError):
                continue
        
        # Sort by CPL descending and return top N
        critical_moves.sort(key=lambda x: x.cpl, reverse=True)
        return critical_moves[:count]
    
    def _find_top_best_moves(self, moves: List[MoveData], is_white: bool, count: int) -> List[CriticalMove]:
        """Find top N best moves (lowest CPL, excluding book moves).
        
        Args:
            moves: List of MoveData instances.
            is_white: True for White, False for Black.
            count: Number of moves to return.
            
        Returns:
            List of CriticalMove instances sorted by CPL ascending.
        """
        if is_white:
            cpl_field = 'cpl_white'
            assess_field = 'assess_white'
            eval_field = 'eval_white'
            move_field = 'white_move'
            best_field = 'best_white'
        else:
            cpl_field = 'cpl_black'
            assess_field = 'assess_black'
            eval_field = 'eval_black'
            move_field = 'black_move'
            best_field = 'best_black'
        
        critical_moves: List[CriticalMove] = []
        
        for move in moves:
            move_str = getattr(move, move_field)
            if not move_str:
                continue
            
            assessment = getattr(move, assess_field)
            # Skip book moves for best moves
            if assessment == "Book Move":
                continue
            
            cpl_str = getattr(move, cpl_field)
            if not cpl_str:
                continue
            
            try:
                cpl = float(cpl_str)
                evaluation = getattr(move, eval_field)
                best_move = getattr(move, best_field, "") or ""
                
                # Format move notation (e.g., "23. Qd4")
                move_notation = f"{move.move_number}. {move_str}"
                
                critical_moves.append(CriticalMove(
                    move_number=move.move_number,
                    move_notation=move_notation,
                    cpl=cpl,
                    assessment=assessment,
                    evaluation=evaluation,
                    best_move=best_move
                ))
            except (ValueError, TypeError):
                continue
        
        # Sort to prioritize brilliant moves: brilliant moves first (by CPL ascending), then others (by CPL ascending)
        brilliant_moves = [m for m in critical_moves if m.assessment == "Brilliant"]
        other_moves = [m for m in critical_moves if m.assessment != "Brilliant"]
        
        # Sort each group by CPL ascending
        brilliant_moves.sort(key=lambda x: x.cpl)
        other_moves.sort(key=lambda x: x.cpl)
        
        # Combine: brilliant moves first, then others
        sorted_moves = brilliant_moves + other_moves
        return sorted_moves[:count]
    
    def _extract_evaluation_data(self, moves: List[MoveData]) -> List[Tuple[int, float]]:
        """Extract evaluation data for graph (move number, evaluation in centipawns).
        
        Args:
            moves: List of MoveData instances.
            
        Returns:
            List of (move_number, evaluation_centipawns) tuples.
        """
        evaluation_data: List[Tuple[int, float]] = []
        
        # Starting position (move 0, evaluation 0.0)
        evaluation_data.append((0, 0.0))
        
        for move in moves:
            # Get white evaluation
            if move.eval_white:
                eval_cp = self._parse_evaluation(move.eval_white)
                if eval_cp is not None:
                    # White move is at move_number * 2 - 1 (ply index)
                    ply_index = move.move_number * 2 - 1
                    evaluation_data.append((ply_index, eval_cp))
            
            # Get black evaluation
            if move.eval_black:
                eval_cp = self._parse_evaluation(move.eval_black)
                if eval_cp is not None:
                    # Black move is at move_number * 2 (ply index)
                    ply_index = move.move_number * 2
                    evaluation_data.append((ply_index, eval_cp))
        
        return evaluation_data
    
    def _parse_evaluation(self, eval_str: str) -> Optional[float]:
        """Parse evaluation string to centipawns.
        
        Args:
            eval_str: Evaluation string (e.g., "+1.5", "M3", "-M2").
            
        Returns:
            Evaluation in centipawns, or None if invalid.
        """
        if not eval_str:
            return None
        
        eval_str = eval_str.strip()
        
        # Handle mate notation (M3, -M2, M0, -M0)
        if eval_str.startswith('M') or eval_str.startswith('-M'):
            # Mate positions - use large centipawn values
            # M3 = mate in 3 for white = +30000 centipawns
            # -M2 = mate in 2 for black = -30000 centipawns
            # M0 = checkmate = +30000 or -30000 depending on sign
            try:
                if eval_str.startswith('-M'):
                    mate_moves = int(eval_str[2:])
                    # Negative mate = black winning
                    return -30000.0 + mate_moves  # Closer to mate = higher absolute value
                else:
                    mate_moves = int(eval_str[1:])
                    # Positive mate = white winning
                    return 30000.0 - mate_moves  # Closer to mate = higher absolute value
            except (ValueError, TypeError):
                return None
        
        # Handle regular centipawn evaluation (e.g., "+1.5", "-0.8")
        try:
            pawns = float(eval_str)
            return pawns * 100.0  # Convert to centipawns
        except (ValueError, TypeError):
            return None
    
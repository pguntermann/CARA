"""Main positional analyzer service."""

from typing import Dict, Optional
import chess

from app.services.positional_heatmap.rule_registry import RuleRegistry
from app.services.positional_heatmap.score_aggregator import ScoreAggregator


class PositionalAnalyzer:
    """Main service for analyzing chess positions and generating heat-map scores.
    
    Coordinates rule evaluation, score aggregation, and caching for performance.
    """
    
    def __init__(self, config: Dict, rule_registry: RuleRegistry) -> None:
        """Initialize the positional analyzer.
        
        Args:
            config: Configuration dictionary.
            rule_registry: RuleRegistry instance with registered rules.
        """
        self.config = config
        self.registry = rule_registry
        self.aggregator = ScoreAggregator(config.get('aggregation', {}))
        self._cache: Dict[str, Dict[chess.Square, float]] = {}
        self.cache_enabled = config.get('cache_enabled', True)
        self.max_cache_size = config.get('max_cache_size', 1000)
    
    def analyze_position(self, board: chess.Board, 
                        perspective: Optional[chess.Color] = None) -> Dict[chess.Square, float]:
        """Analyze position and return heat-map scores.
        
        Args:
            board: Current chess position (python-chess Board).
            perspective: Color to evaluate from (None = side to move).
                        Positive scores favor this color, negative scores favor opponent.
        
        Returns:
            Dictionary mapping square -> aggregated score.
            Scores are from the perspective's viewpoint.
        """
        if perspective is None:
            perspective = board.turn
        
        # Check cache
        fen = board.fen()
        cache_key = f"{fen}_{perspective}"
        if self.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]
        
        # Get enabled rules
        rules = self.registry.get_enabled_rules()
        
        # Evaluate each rule (with error isolation)
        rule_results = []
        for rule in rules:
            try:
                scores = rule.evaluate(board, perspective)
                rule_results.append(scores)
            except Exception as e:
                # Log error but continue with other rules
                # Error isolation: one bad rule doesn't break everything
                # In production, you might want to log this to error_collector
                continue
        
        # Aggregate scores
        aggregated = self.aggregator.aggregate(rule_results, rules)
        
        # Cache result (with size limit)
        if self.cache_enabled:
            if len(self._cache) >= self.max_cache_size:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[cache_key] = aggregated
        
        return aggregated
    
    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self._cache.clear()
    
    def get_cache_size(self) -> int:
        """Get current cache size.
        
        Returns:
            Number of cached positions.
        """
        return len(self._cache)
    
    def get_detailed_evaluation(self, board: chess.Board, 
                                perspective: Optional[chess.Color] = None) -> Dict:
        """Get detailed evaluation showing which rules apply to each piece.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from (None = side to move).
        
        Returns:
            Dictionary with detailed evaluation info:
            {
                'pieces': {
                    square: {
                        'piece': piece_symbol,
                        'color': 'white' or 'black',
                        'rules': [
                            {
                                'name': rule_name,
                                'score': raw_score,
                                'weight': rule_weight,
                                'weighted_score': raw_score * weight
                            },
                            ...
                        ],
                        'total_score': aggregated_score
                    },
                    ...
                }
            }
        """
        if perspective is None:
            perspective = board.turn
        
        # Get enabled rules
        rules = self.registry.get_enabled_rules()
        
        # Evaluate each rule separately
        rule_results = []
        for rule in rules:
            try:
                scores = rule.evaluate(board, perspective)
                rule_results.append((rule, scores))
            except Exception as e:
                # Skip rules that error
                continue
        
        # Build detailed evaluation
        detailed = {
            'pieces': {}
        }
        
        # Collect scores for each square
        for rule, scores in rule_results:
            weight = rule.weight
            rule_name = rule.get_name()
            
            for square, score in scores.items():
                piece = board.piece_at(square)
                if piece is None:
                    continue
                
                if square not in detailed['pieces']:
                    # Get piece symbol
                    piece_symbol = chess.piece_symbol(piece.piece_type)
                    if piece.color == chess.WHITE:
                        piece_symbol = piece_symbol.upper()
                    
                    detailed['pieces'][square] = {
                        'piece': piece_symbol,
                        'color': 'white' if piece.color == chess.WHITE else 'black',
                        'square': chess.square_name(square),
                        'rules': [],
                        'total_score': 0.0
                    }
                
                # Add rule contribution
                weighted_score = score * weight
                detailed['pieces'][square]['rules'].append({
                    'name': rule_name,
                    'score': score,
                    'weight': weight,
                    'weighted_score': weighted_score
                })
                detailed['pieces'][square]['total_score'] += weighted_score
        
        # Get final aggregated scores (with normalization)
        aggregated = self.aggregator.aggregate([scores for _, scores in rule_results], rules)
        
        # Update total scores with normalized values
        for square in detailed['pieces']:
            if square in aggregated:
                detailed['pieces'][square]['total_score'] = aggregated[square]
        
        return detailed


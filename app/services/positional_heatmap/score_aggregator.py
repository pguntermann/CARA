"""Score aggregator for combining scores from multiple rules."""

from typing import Dict, List
import math
import chess


class ScoreAggregator:
    """Aggregates scores from multiple positional rules.
    
    Combines scores from different rules using weighted summation,
    with optional normalization (hard clamping or soft scaling).
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the score aggregator.
        
        Args:
            config: Configuration dictionary with aggregation settings.
        """
        self.config = config
        self.score_range = config.get('score_range', [-100, 100])
        self.normalize = config.get('normalize', True)
        self.min_score, self.max_score = self.score_range
        
        # Normalization method: "hard" (clamp) or "soft" (tanh scaling)
        aggregation_config = config.get('aggregation', {})
        self.normalization_method = aggregation_config.get('normalization_method', 'hard')
        self.soft_scale_factor = aggregation_config.get('soft_scale_factor', 50.0)
    
    def aggregate(self, rule_results: List[Dict[chess.Square, float]], 
                  rules: List) -> Dict[chess.Square, float]:
        """Combine scores from multiple rules.
        
        Args:
            rule_results: List of score dictionaries from each rule.
                         Each dictionary maps square -> score.
            rules: List of corresponding PositionalRule instances (for weights).
        
        Returns:
            Aggregated scores per square (weighted sum of all rule scores).
        """
        aggregated: Dict[chess.Square, float] = {}
        
        # Combine scores from all rules
        for rule_result, rule in zip(rule_results, rules):
            weight = rule.weight
            for square, score in rule_result.items():
                if square not in aggregated:
                    aggregated[square] = 0.0
                aggregated[square] += score * weight
        
        # Normalize if enabled
        if self.normalize:
            if self.normalization_method == 'soft':
                # Soft scaling using tanh: preserves proportionality better than hard clamp
                # Formula: tanh(score / scale_factor) * max_score
                for square in aggregated:
                    raw_score = aggregated[square]
                    # Apply tanh scaling: tanh(score / scale_factor) * max_score
                    # This preserves relative importance while keeping scores in range
                    scaled_score = math.tanh(raw_score / self.soft_scale_factor) * self.max_score
                    aggregated[square] = scaled_score
            else:
                # Hard clamp (default): simple but can distort relative importance
                for square in aggregated:
                    aggregated[square] = max(self.min_score, min(self.max_score, aggregated[square]))
        
        return aggregated


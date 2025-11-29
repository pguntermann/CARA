"""Base rule interface for positional evaluation rules."""

from abc import ABC, abstractmethod
from typing import Dict, Any
import chess


class PositionalRule(ABC):
    """Abstract base class for all positional evaluation rules.
    
    Each rule evaluates a position and returns scores for squares.
    Rules are independent, testable, and configurable.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the rule with configuration.
        
        Args:
            config: Rule-specific configuration dictionary.
        """
        self.config = config
        self.enabled = config.get('enabled', True)
        self.weight = config.get('weight', 1.0)
        self.name = config.get('name', self.__class__.__name__)
        self.description = config.get('description', '')
    
    @abstractmethod
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate position and return scores for each square.
        
        Args:
            board: Current chess position (python-chess Board).
            perspective: Color to evaluate from (chess.WHITE or chess.BLACK).
                        Positive scores favor this color, negative scores favor opponent.
        
        Returns:
            Dictionary mapping square -> score (typically -100 to +100).
            Only include squares that have a non-zero score.
            Scores should be from the perspective's viewpoint.
        """
        pass
    
    def get_name(self) -> str:
        """Get rule name.
        
        Returns:
            Rule name string.
        """
        return self.name
    
    def get_description(self) -> str:
        """Get rule description.
        
        Returns:
            Rule description string.
        """
        return self.description
    
    def is_enabled(self) -> bool:
        """Check if rule is enabled.
        
        Returns:
            True if rule is enabled, False otherwise.
        """
        return self.enabled


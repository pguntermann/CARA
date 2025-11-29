"""Rule registry for managing positional evaluation rules."""

from typing import Dict, List, Optional
from app.services.positional_heatmap.base_rule import PositionalRule


class RuleRegistry:
    """Manages positional evaluation rules with discovery and configuration.
    
    The registry allows for flexible rule management - rules can be
    registered, enabled/disabled, and retrieved dynamically.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the rule registry.
        
        Args:
            config: Configuration dictionary containing rule configurations.
        """
        self.config = config
        self._rules: Dict[str, PositionalRule] = {}
        self._load_rules()
    
    def _load_rules(self) -> None:
        """Load all rules from configuration.
        
        This method imports and registers all available rules.
        Rules are loaded from the rules configuration section.
        """
        rules_config = self.config.get('rules', {})
        
        # Import rule classes (lazy import to avoid circular dependencies)
        from app.services.positional_heatmap.rules.passed_pawn_rule import PassedPawnRule
        from app.services.positional_heatmap.rules.backward_pawn_rule import BackwardPawnRule
        from app.services.positional_heatmap.rules.isolated_pawn_rule import IsolatedPawnRule
        from app.services.positional_heatmap.rules.doubled_pawn_rule import DoubledPawnRule
        from app.services.positional_heatmap.rules.king_safety_rule import KingSafetyRule
        from app.services.positional_heatmap.rules.weak_square_rule import WeakSquareRule
        from app.services.positional_heatmap.rules.piece_activity_rule import PieceActivityRule
        from app.services.positional_heatmap.rules.undeveloped_piece_rule import UndevelopedPieceRule
        from app.services.positional_heatmap.rules.outpost_square_rule import OutpostSquareRule
        
        # Register built-in rules
        if 'passed_pawn' in rules_config:
            self.register_rule(PassedPawnRule(rules_config.get('passed_pawn', {})))
        
        if 'backward_pawn' in rules_config:
            self.register_rule(BackwardPawnRule(rules_config.get('backward_pawn', {})))
        
        if 'isolated_pawn' in rules_config:
            self.register_rule(IsolatedPawnRule(rules_config.get('isolated_pawn', {})))
        
        if 'doubled_pawn' in rules_config:
            self.register_rule(DoubledPawnRule(rules_config.get('doubled_pawn', {})))
        
        if 'king_safety' in rules_config:
            self.register_rule(KingSafetyRule(rules_config.get('king_safety', {})))
        
        if 'weak_square' in rules_config:
            self.register_rule(WeakSquareRule(rules_config.get('weak_square', {})))
        
        if 'piece_activity' in rules_config:
            self.register_rule(PieceActivityRule(rules_config.get('piece_activity', {})))
        
        if 'undeveloped_piece' in rules_config:
            self.register_rule(UndevelopedPieceRule(rules_config.get('undeveloped_piece', {})))
        
        if 'outpost_square' in rules_config:
            self.register_rule(OutpostSquareRule(rules_config.get('outpost_square', {})))
    
    def register_rule(self, rule: PositionalRule) -> None:
        """Register a rule.
        
        Args:
            rule: PositionalRule instance to register.
        """
        self._rules[rule.get_name()] = rule
    
    def get_all_rules(self) -> List[PositionalRule]:
        """Get all registered rules.
        
        Returns:
            List of all registered rules (enabled and disabled).
        """
        return list(self._rules.values())
    
    def get_enabled_rules(self) -> List[PositionalRule]:
        """Get only enabled rules.
        
        Returns:
            List of enabled rules.
        """
        return [rule for rule in self._rules.values() if rule.is_enabled()]
    
    def get_rule(self, name: str) -> Optional[PositionalRule]:
        """Get a specific rule by name.
        
        Args:
            name: Rule name.
        
        Returns:
            PositionalRule instance if found, None otherwise.
        """
        return self._rules.get(name)
    
    def get_rule_names(self) -> List[str]:
        """Get names of all registered rules.
        
        Returns:
            List of rule names.
        """
        return list(self._rules.keys())


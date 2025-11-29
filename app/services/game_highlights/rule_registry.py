"""Rule registry for managing game highlight detection rules."""

from typing import Dict, List
from app.services.game_highlights.base_rule import HighlightRule


class RuleRegistry:
    """Manages game highlight detection rules with discovery and configuration.
    
    The registry allows for flexible rule management - rules can be
    registered, enabled/disabled, and retrieved dynamically.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the rule registry.
        
        Args:
            config: Configuration dictionary containing rule configurations.
        """
        self.config = config
        self._rules: Dict[str, HighlightRule] = {}
        self._load_rules()
    
    def _load_rules(self) -> None:
        """Load all rules from configuration.
        
        This method imports and registers all available rules.
        Rules are loaded from the rules configuration section.
        """
        rules_config = self.config.get('rules', {})
        
        # Import rule classes
        from app.services.game_highlights.rules.bishop_pair_rule import BishopPairRule
        from app.services.game_highlights.rules.material_imbalance_rule import MaterialImbalanceRule
        from app.services.game_highlights.rules.exchange_sequence_rule import ExchangeSequenceRule
        from app.services.game_highlights.rules.theory_departure_rule import TheoryDepartureRule
        from app.services.game_highlights.rules.novelty_rule import NoveltyRule
        from app.services.game_highlights.rules.castling_rule import CastlingRule
        from app.services.game_highlights.rules.pawn_break_rule import PawnBreakRule
        from app.services.game_highlights.rules.simplification_rule import SimplificationRule
        from app.services.game_highlights.rules.evaluation_swing_rule import EvaluationSwingRule
        from app.services.game_highlights.rules.momentum_shift_rule import MomentumShiftRule
        from app.services.game_highlights.rules.forcing_combination_rule import ForcingCombinationRule
        from app.services.game_highlights.rules.tactical_opportunity_rule import TacticalOpportunityRule
        from app.services.game_highlights.rules.defensive_resource_rule import DefensiveResourceRule
        from app.services.game_highlights.rules.blundered_piece_rule import BlunderedPieceRule
        from app.services.game_highlights.rules.positional_improvement_rule import PositionalImprovementRule
        from app.services.game_highlights.rules.initiative_rule import InitiativeRule
        from app.services.game_highlights.rules.tactical_resource_rule import TacticalResourceRule
        from app.services.game_highlights.rules.centralization_rule import CentralizationRule
        from app.services.game_highlights.rules.pawn_storm_rule import PawnStormRule
        from app.services.game_highlights.rules.delayed_mating_rule import DelayedMatingRule
        from app.services.game_highlights.rules.fork_rule import ForkRule
        from app.services.game_highlights.rules.skewer_rule import SkewerRule
        from app.services.game_highlights.rules.pin_rule import PinRule
        from app.services.game_highlights.rules.discovered_attack_rule import DiscoveredAttackRule
        from app.services.game_highlights.rules.battery_rule import BatteryRule
        from app.services.game_highlights.rules.decoy_rule import DecoyRule
        from app.services.game_highlights.rules.zwischenzug_rule import ZwischenzugRule
        from app.services.game_highlights.rules.interference_rule import InterferenceRule
        from app.services.game_highlights.rules.windmill_rule import WindmillRule
        from app.services.game_highlights.rules.back_rank_weakness_rule import BackRankWeaknessRule
        from app.services.game_highlights.rules.weak_square_rule import WeakSquareRule
        from app.services.game_highlights.rules.isolated_pawn_rule import IsolatedPawnRule
        from app.services.game_highlights.rules.perpetual_check_rule import PerpetualCheckRule
        from app.services.game_highlights.rules.zugzwang_rule import ZugzwangRule
        from app.services.game_highlights.rules.piece_coordination_rule import PieceCoordinationRule
        from app.services.game_highlights.rules.king_activity_rule import KingActivityRule
        from app.services.game_highlights.rules.pawn_promotion_threat_rule import PawnPromotionThreatRule
        from app.services.game_highlights.rules.tempo_gain_rule import TempoGainRule
        from app.services.game_highlights.rules.exchange_sacrifice_rule import ExchangeSacrificeRule
        from app.services.game_highlights.rules.rook_lift_rule import RookLiftRule
        from app.services.game_highlights.rules.knight_outpost_rule import KnightOutpostRule
        from app.services.game_highlights.rules.breakthrough_sacrifice_rule import BreakthroughSacrificeRule
        from app.services.game_highlights.rules.defensive_fortress_rule import DefensiveFortressRule
        from app.services.game_highlights.rules.tactical_sequence_rule import TacticalSequenceRule
        
        # Register all rules (default enabled)
        self.register_rule(BishopPairRule(rules_config.get('bishop_pair', {})))
        self.register_rule(MaterialImbalanceRule(rules_config.get('material_imbalance', {})))
        self.register_rule(ExchangeSequenceRule(rules_config.get('exchange_sequence', {})))
        self.register_rule(TheoryDepartureRule(rules_config.get('theory_departure', {})))
        self.register_rule(NoveltyRule(rules_config.get('novelty', {})))
        self.register_rule(CastlingRule(rules_config.get('castling', {})))
        self.register_rule(PawnBreakRule(rules_config.get('pawn_break', {})))
        self.register_rule(SimplificationRule(rules_config.get('simplification', {})))
        self.register_rule(EvaluationSwingRule(rules_config.get('evaluation_swing', {})))
        self.register_rule(MomentumShiftRule(rules_config.get('momentum_shift', {})))
        self.register_rule(ForcingCombinationRule(rules_config.get('forcing_combination', {})))
        self.register_rule(TacticalOpportunityRule(rules_config.get('tactical_opportunity', {})))
        self.register_rule(DefensiveResourceRule(rules_config.get('defensive_resource', {})))
        self.register_rule(BlunderedPieceRule(rules_config.get('blundered_piece', {})))
        self.register_rule(PositionalImprovementRule(rules_config.get('positional_improvement', {})))
        self.register_rule(InitiativeRule(rules_config.get('initiative', {})))
        self.register_rule(TacticalResourceRule(rules_config.get('tactical_resource', {})))
        self.register_rule(CentralizationRule(rules_config.get('centralization', {})))
        self.register_rule(PawnStormRule(rules_config.get('pawn_storm', {})))
        self.register_rule(DelayedMatingRule(rules_config.get('delayed_mating', {})))
        self.register_rule(ForkRule(rules_config.get('fork', {})))
        self.register_rule(SkewerRule(rules_config.get('skewer', {})))
        self.register_rule(PinRule(rules_config.get('pin', {})))
        self.register_rule(DiscoveredAttackRule(rules_config.get('discovered_attack', {})))
        self.register_rule(BatteryRule(rules_config.get('battery', {})))
        self.register_rule(DecoyRule(rules_config.get('decoy', {})))
        self.register_rule(ZwischenzugRule(rules_config.get('zwischenzug', {})))
        self.register_rule(InterferenceRule(rules_config.get('interference', {})))
        self.register_rule(WindmillRule(rules_config.get('windmill', {})))
        self.register_rule(BackRankWeaknessRule(rules_config.get('back_rank_weakness', {})))
        self.register_rule(WeakSquareRule(rules_config.get('weak_square', {})))
        self.register_rule(IsolatedPawnRule(rules_config.get('isolated_pawn', {})))
        self.register_rule(PerpetualCheckRule(rules_config.get('perpetual_check', {})))
        self.register_rule(ZugzwangRule(rules_config.get('zugzwang', {})))
        self.register_rule(PieceCoordinationRule(rules_config.get('piece_coordination', {})))
        self.register_rule(KingActivityRule(rules_config.get('king_activity', {})))
        self.register_rule(PawnPromotionThreatRule(rules_config.get('pawn_promotion_threat', {})))
        self.register_rule(TempoGainRule(rules_config.get('tempo_gain', {})))
        self.register_rule(ExchangeSacrificeRule(rules_config.get('exchange_sacrifice', {})))
        self.register_rule(RookLiftRule(rules_config.get('rook_lift', {})))
        self.register_rule(KnightOutpostRule(rules_config.get('knight_outpost', {})))
        self.register_rule(BreakthroughSacrificeRule(rules_config.get('breakthrough_sacrifice', {})))
        self.register_rule(DefensiveFortressRule(rules_config.get('defensive_fortress', {})))
        self.register_rule(TacticalSequenceRule(rules_config.get('tactical_sequence', {})))
    
    def register_rule(self, rule: HighlightRule) -> None:
        """Register a rule.
        
        Args:
            rule: HighlightRule instance to register.
        """
        self._rules[rule.get_name()] = rule
    
    def get_all_rules(self) -> List[HighlightRule]:
        """Get all registered rules.
        
        Returns:
            List of all registered rules (enabled and disabled).
        """
        return list(self._rules.values())
    
    def get_enabled_rules(self) -> List[HighlightRule]:
        """Get only enabled rules.
        
        Returns:
            List of enabled rules.
        """
        return [rule for rule in self._rules.values() if rule.is_enabled()]


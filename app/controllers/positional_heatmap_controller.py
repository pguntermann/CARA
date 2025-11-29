"""Controller for positional heat-map feature."""

from typing import Dict, Any, Optional

from app.services.positional_heatmap.rule_registry import RuleRegistry
from app.services.positional_heatmap.positional_analyzer import PositionalAnalyzer
from app.models.positional_heatmap_model import PositionalHeatmapModel


class PositionalHeatmapController:
    """Controller for managing positional heat-map feature.
    
    Orchestrates the interaction between services, models, and views.
    Coordinates positional heatmap analysis.
    """
    
    def __init__(self, config: Dict[str, Any], board_controller, game_controller=None) -> None:
        """Initialize the positional heat-map controller.
        
        Args:
            config: Configuration dictionary.
            board_controller: BoardController instance for accessing board state.
            game_controller: Optional GameController instance.
        """
        self.config = config
        self.board_controller = board_controller
        self.game_controller = game_controller
        
        # Get positional heat-map configuration
        heatmap_config = config.get('ui', {}).get('positional_heatmap', {})
        
        # Initialize components
        self.registry = RuleRegistry(heatmap_config)
        self.analyzer = PositionalAnalyzer(heatmap_config, self.registry)
        self.model = PositionalHeatmapModel(heatmap_config, self.analyzer)
        
        # Connect to board position changes
        if board_controller:
            board_controller.get_board_model().position_changed.connect(self._on_position_changed)
    
    def _on_position_changed(self) -> None:
        """Handle position change from board model."""
        if self.model.is_visible:
            # Clear cache when position changes to ensure fresh evaluation
            self.analyzer.clear_cache()
            board = self.board_controller.get_board_model().board
            self.model.update_position(board)
    
    def toggle_visibility(self) -> None:
        """Toggle heat-map visibility."""
        self.model.set_visible(not self.model.is_visible)
        if self.model.is_visible:
            # Clear cache to ensure fresh evaluation with updated rules
            self.analyzer.clear_cache()
            # Update scores when enabling
            board = self.board_controller.get_board_model().board
            self.model.update_position(board)
    
    def get_model(self) -> PositionalHeatmapModel:
        """Get the positional heat-map model.
        
        Returns:
            PositionalHeatmapModel instance.
        """
        return self.model
    
    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analyzer.clear_cache()


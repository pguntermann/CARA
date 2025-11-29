"""Game Info header view for main panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from typing import Dict, Any


class MainGameInfoView(QWidget):
    """Game information header view displaying player names, ELOs, and opening."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the game info view.
        
        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        self.config = config
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the game info UI."""
        layout = QVBoxLayout(self)
        
        # Get gameinfo config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('main', {})
        gameinfo_config = panel_config.get('gameinfo', {})
        
        # Get spacing and padding from config
        padding = gameinfo_config.get('padding', [10, 10, 10, 10])
        layout.setContentsMargins(padding[0], padding[1], padding[2], padding[3])
        spacing = gameinfo_config.get('spacing', 8)
        layout.setSpacing(spacing)
        
        # Get font settings
        font_family = gameinfo_config.get('font_family', 'Helvetica Neue')
        player_name_size = gameinfo_config.get('player_name_size', 16)
        player_elo_size = gameinfo_config.get('player_elo_size', 12)
        opening_size = gameinfo_config.get('opening_size', 14)
        text_color = gameinfo_config.get('text_color', [240, 240, 240])
        
        # Get colors
        color_rgb = f"rgb({text_color[0]}, {text_color[1]}, {text_color[2]})"
        
        # Players row (both on same line)
        players_layout = QHBoxLayout()
        players_layout.setSpacing(8)
        players_layout.addStretch()
        
        white_name_font = QFont(font_family, player_name_size)
        white_elo_font = QFont(font_family, player_elo_size)
        
        self.white_name_label = QLabel("Player 1")
        self.white_name_label.setFont(white_name_font)
        self.white_name_label.setStyleSheet(f"color: {color_rgb}; font-weight: 600;")
        players_layout.addWidget(self.white_name_label)
        
        self.white_elo_label = QLabel("(1800)")
        self.white_elo_label.setFont(white_elo_font)
        self.white_elo_label.setStyleSheet(f"color: {color_rgb};")
        players_layout.addWidget(self.white_elo_label)
        
        # Result (replaces separator)
        result_config = gameinfo_config.get('result', {})
        result_size = result_config.get('font_size', player_name_size)
        result_font = QFont(font_family, result_size)
        
        self.result_label = QLabel("*")
        self.result_label.setFont(result_font)
        self.result_label.setStyleSheet(f"color: {color_rgb}; font-weight: 600;")
        players_layout.addWidget(self.result_label)
        
        black_name_font = QFont(font_family, player_name_size)
        black_elo_font = QFont(font_family, player_elo_size)
        
        self.black_name_label = QLabel("Player 2")
        self.black_name_label.setFont(black_name_font)
        self.black_name_label.setStyleSheet(f"color: {color_rgb}; font-weight: 600;")
        players_layout.addWidget(self.black_name_label)
        
        self.black_elo_label = QLabel("(2000)")
        self.black_elo_label.setFont(black_elo_font)
        self.black_elo_label.setStyleSheet(f"color: {color_rgb};")
        players_layout.addWidget(self.black_elo_label)
        
        players_layout.addStretch()
        layout.addLayout(players_layout)
        
        # Opening row
        opening_layout = QHBoxLayout()
        opening_layout.addStretch()
        
        opening_font = QFont(font_family, opening_size)
        
        self.opening_label = QLabel("A00 - Unknown Opening")
        self.opening_label.setFont(opening_font)
        self.opening_label.setStyleSheet(f"color: {color_rgb};")
        opening_layout.addWidget(self.opening_label)
        
        opening_layout.addStretch()
        layout.addLayout(opening_layout)
        
        # Center align layout
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def set_white_player(self, name: str, elo: int) -> None:
        """Set white player name and ELO.
        
        Args:
            name: Player name.
            elo: Player ELO rating.
        """
        self.white_name_label.setText(name)
        self.white_elo_label.setText(f"({elo})")
    
    def set_black_player(self, name: str, elo: int) -> None:
        """Set black player name and ELO.
        
        Args:
            name: Player name.
            elo: Player ELO rating.
        """
        self.black_name_label.setText(name)
        self.black_elo_label.setText(f"({elo})")
    
    def set_result(self, result: str) -> None:
        """Set game result.
        
        Args:
            result: Game result (e.g., "1-0", "0-1", "1/2-1/2", "*").
        """
        # Format result for display
        if result == "1-0":
            display_result = "1 - 0"
        elif result == "0-1":
            display_result = "0 - 1"
        elif result == "1/2-1/2":
            display_result = "1/2 - 1/2"
        else:
            # Default to "*" for unknown/unfinished games
            display_result = "*"
        
        self.result_label.setText(display_result)
    
    def set_opening(self, eco: str, name: str) -> None:
        """Set opening ECO code and name.
        
        Args:
            eco: ECO code (e.g., "A00").
            name: Opening name (e.g., "Unknown Opening").
        """
        self.opening_label.setText(f"{eco} - {name}")


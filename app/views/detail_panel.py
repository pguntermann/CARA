"""Right-hand Detail-Panel containing different Views/Tabs."""

from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QSplitter
)
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt
from typing import Dict, Any

from app.views.detail_pgn_view import DetailPgnView
from app.views.detail_moveslist_view import DetailMovesListView
from app.views.detail_metadata_view import DetailMetadataView
from app.views.detail_summary_view import DetailSummaryView
from app.views.detail_manual_analysis_view import DetailManualAnalysisView
from app.views.detail_annotation_view import DetailAnnotationView
from app.views.detail_ai_chat_view import DetailAIChatView
from app.models.game_model import GameModel
from app.models.moveslist_model import MovesListModel
from app.models.metadata_model import MetadataModel
from app.models.engine_model import EngineModel
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.models.database_model import DatabaseModel
from app.controllers.game_controller import GameController
from typing import Optional


class DetailPanel(QWidget):
    """Detail panel with tabs for different views."""
    
    def __init__(self, config: Dict[str, Any], game_model: Optional[GameModel] = None,
                 game_controller: Optional[GameController] = None,
                 engine_model: Optional[EngineModel] = None,
                 manual_analysis_controller = None,
                 database_model: Optional[DatabaseModel] = None,
                 classification_model = None,
                 annotation_controller = None,
                 board_widget = None,
                 ai_chat_controller = None,
                 game_summary_controller = None,
                 player_stats_controller = None) -> None:
        """Initialize the detail panel.
        
        Args:
            config: Configuration dictionary.
            game_model: Optional GameModel to observe.
            game_controller: Optional GameController for extracting moves from games.
            engine_model: Optional EngineModel to observe for engine assignments.
            database_model: Optional DatabaseModel to pass to metadata view.
            classification_model: Optional MoveClassificationModel for classification settings.
        """
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._game_controller = game_controller
        self._engine_model = engine_model
        self._manual_analysis_controller = manual_analysis_controller
        self._database_model = database_model
        self._classification_model = classification_model
        self._annotation_controller = annotation_controller
        self._board_widget = board_widget
        self._ai_chat_controller = ai_chat_controller
        self._game_summary_controller = game_summary_controller
        self._player_stats_controller = player_stats_controller
        self._database_panel = None  # Will be set from MainWindow after database_panel is created
        self._setup_ui()
        
        # Connect to game model if provided
        if game_model:
            self.set_game_model(game_model)
    
    def _setup_ui(self) -> None:
        """Setup the detail panel UI with PGN notation and tabs."""
        layout = QVBoxLayout(self)
        ui_config = self.config.get('ui', {})
        margins = ui_config.get('margins', {}).get('detail_panel', [0, 0, 0, 0])
        layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        layout.setSpacing(0)
        
        # Get panel config
        panel_config = ui_config.get('panels', {}).get('detail', {})
        
        # Vertical splitter to separate PGN notation from tabs
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)
        
        # PGN Notation view (top) - will be connected to game model in set_game_model
        self.pgn_view = DetailPgnView(self.config, game_controller=self._game_controller)
        splitter.addWidget(self.pgn_view)
        
        # Tab widget for different detail views (bottom)
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(False)  # Disable document mode for better control
        
        # Apply tab styling from config
        self._apply_tab_styling()
        
        # Initialize tabs
        self._initialize_tabs()
        
        # Configure QTabBar for macOS compatibility (left-aligned, content-sized tabs)
        # Must be done after tabs are added
        self._configure_tab_bar()
        
        splitter.addWidget(self.tab_widget)
        
        # Set splitter sizes from config
        splitter_config = panel_config.get('splitter', {})
        pgn_height = splitter_config.get('pgn_height', 200)
        tabs_height = splitter_config.get('tabs_height', 300)
        pgn_stretch = splitter_config.get('pgn_stretch_factor', 2)
        tabs_stretch = splitter_config.get('tabs_stretch_factor', 3)
        
        splitter.setSizes([pgn_height, tabs_height])
        splitter.setStretchFactor(0, pgn_stretch)
        splitter.setStretchFactor(1, tabs_stretch)
        
        # Set minimum size so widget is visible
        min_width = panel_config.get('minimum_width', 200)
        min_height = panel_config.get('minimum_height', 200)
        self.setMinimumSize(min_width, min_height)
        
        # Set background color from config using palette
        debug_config = self.config.get("debug", {})
        if debug_config.get("enable_debug_backgrounds", False):
            # Use debug background color
            color = debug_config.get("background_color_debug_detailpanel", [255, 255, 255])
        else:
            # Use normal background color
            color = panel_config.get("background_color", [40, 40, 45])
        
        # Set background for the panel itself
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(color[0], color[1], color[2]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
    
    def _apply_tab_styling(self) -> None:
        """Apply styling to the tab widget based on configuration."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        tabs_config = panel_config.get('tabs', {})
        
        # Get font settings
        font_family = resolve_font_family(tabs_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(tabs_config.get('font_size', 10))
        tab_height = tabs_config.get('tab_height', 24)
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        
        # Get color settings
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        hover = colors_config.get('hover', {})
        active = colors_config.get('active', {})
        
        # Normal state colors
        norm_bg = normal.get('background', [45, 45, 50])
        norm_text = normal.get('text', [200, 200, 200])
        norm_border = normal.get('border', [60, 60, 65])
        
        # Hover state colors
        hover_bg = hover.get('background', [55, 55, 60])
        hover_text = hover.get('text', [230, 230, 230])
        hover_border = hover.get('border', [80, 80, 85])
        
        # Active state colors
        active_bg = active.get('background', [70, 90, 130])
        active_text = active.get('text', [240, 240, 240])
        active_border = active.get('border', [100, 120, 160])
        
        # Create stylesheet
        stylesheet = f"""
            QTabWidget::pane {{
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
            }}
            
            QTabBar {{
                alignment: left;
            }}
            
            QTabBar::tab {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                min-width: 80px;
                height: {tab_height}px;
                font-family: "{font_family}";
                font-size: {font_size}pt;
                margin-right: 2px;
            }}
            
            QTabBar::tab:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
                border-color: rgb({hover_border[0]}, {hover_border[1]}, {hover_border[2]});
            }}
            
            QTabBar::tab:selected {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
                border-color: rgb({active_border[0]}, {active_border[1]}, {active_border[2]});
                font-weight: 500;
            }}
            
            QTabBar::tab:focus {{
                outline: none;
            }}
            
            QTabBar::tab:!selected {{
                margin-top: 2px;
            }}
            
            QTabBar::tab:first:selected {{
                margin-left: 0px;
            }}
            
            QTabBar::tab:last:selected {{
                margin-right: 0px;
            }}
        """
        
        self.tab_widget.setStyleSheet(stylesheet)
    
    def _configure_tab_bar(self) -> None:
        """Configure QTabBar for macOS compatibility (left-aligned, content-sized tabs)."""
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setExpanding(False)  # Allow tabs to size to content instead of filling space
        tab_bar.setElideMode(Qt.TextElideMode.ElideNone)  # Prevent text truncation
        tab_bar.setUsesScrollButtons(True)  # Enable scroll buttons when tabs don't fit
        tab_bar.setDrawBase(False)  # Don't draw base line
    
    def _initialize_tabs(self) -> None:
        """Initialize the detail panel tabs."""
        # Moves List tab - initialize with empty model for now
        # Game model and controller will be connected in set_game_model
        from app.models.moveslist_model import MovesListModel
        self.moveslist_model = MovesListModel()
        self.moves_view = DetailMovesListView(self.config, self.moveslist_model, game_controller=self._game_controller)
        self.tab_widget.addTab(self.moves_view, "Moves List")
        
        # Metadata tab - initialize with empty model for now
        # Game model will be connected in set_game_model
        self.metadata_model = MetadataModel(self.config)
        self.metadata_view = DetailMetadataView(self.config, self.metadata_model, 
                                                 database_model=self._database_model,
                                                 database_panel=self._database_panel)
        self.tab_widget.addTab(self.metadata_view, "Metadata")
        
        # Manual Analysis tab
        self.manual_analysis_view = DetailManualAnalysisView(
            self.config,
            game_model=self._game_model,
            engine_model=self._engine_model
        )
        self.tab_widget.addTab(self.manual_analysis_view, "Manual Analysis")
        
        # Game Summary tab - initialize with game model and moves list model if available
        self.summary_view = DetailSummaryView(
            self.config, 
            game_model=self._game_model,
            game_controller=self._game_controller,
            summary_controller=self._game_summary_controller
        )
        self.tab_widget.addTab(self.summary_view, "Game Summary")
        
        # Player Stats tab
        from app.views.detail_player_stats_view import DetailPlayerStatsView
        from app.controllers.database_controller import DatabaseController
        database_controller = None
        if hasattr(self, '_database_model') and self._database_model:
            # Try to get database controller from parent if available
            # This will be set properly when database_panel is connected
            pass
        
        self.player_stats_view = DetailPlayerStatsView(
            self.config,
            database_controller=database_controller,  # Will be set later
            game_model=self._game_model,
            game_controller=self._game_controller,
            stats_controller=self._player_stats_controller,
            database_panel=self._database_panel  # Pass database panel for highlighting games
        )
        self.tab_widget.addTab(self.player_stats_view, "Player Stats")
        
        # Annotation tab
        self.annotation_view = DetailAnnotationView(
            self.config,
            game_model=self._game_model,
            annotation_controller=self._annotation_controller,
            board_widget=self._board_widget
        )
        self.tab_widget.addTab(self.annotation_view, "Annotations")
        
        # AI Summary tab
        self.ai_chat_view = DetailAIChatView(
            self.config,
            game_model=self._game_model,
            ai_chat_controller=self._ai_chat_controller
        )
        self.tab_widget.addTab(self.ai_chat_view, "AI Summary")
        
        # Connect manual analysis controller if provided
        if self._manual_analysis_controller:
            self.manual_analysis_view.set_analysis_controller(self._manual_analysis_controller)
        
        # Connect annotation view to game model if available
        if self._game_model:
            self.annotation_view.set_game_model(self._game_model)
        
        # Connect AI chat view to game model if available
        if self._game_model:
            self.ai_chat_view.set_game_model(self._game_model)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
        
        self._game_model = model
        
        # Connect to model signals
        model.active_game_changed.connect(self._on_active_game_changed)
        
        # Connect PGN view to game model for active move tracking
        self.pgn_view.set_game_model(model)
        
        # Connect moves list view to game model for active move tracking
        if hasattr(self, 'moves_view'):
            self.moves_view.set_game_model(model)
        
        # Connect metadata view to game model for active game tracking
        if hasattr(self, 'metadata_view'):
            self.metadata_view.set_game_model(model)
        
        # Connect summary view to game model for analysis status tracking
        if hasattr(self, 'summary_view'):
            self.summary_view.set_game_model(model)
        
        # Connect manual analysis view to game model if it exists
        if hasattr(self, 'manual_analysis_view'):
            self.manual_analysis_view.set_game_model(model)
        
        # Connect manual analysis view to engine model if it exists
        if hasattr(self, 'manual_analysis_view') and self._engine_model:
            self.manual_analysis_view.set_engine_model(self._engine_model)
        
        # Connect annotation view to game model if it exists
        if hasattr(self, 'annotation_view'):
            self.annotation_view.set_game_model(model)
        
        # Connect AI chat view to game model if it exists
        if hasattr(self, 'ai_chat_view'):
            self.ai_chat_view.set_game_model(model)
        
        # Connect AI chat view to controller if it exists
        if hasattr(self, 'ai_chat_view') and self._ai_chat_controller:
            self.ai_chat_view.set_ai_chat_controller(self._ai_chat_controller)
        
        # Initialize with current active game if any
        if model.active_game:
            self._on_active_game_changed(model.active_game)
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change from model.
        
        Args:
            game: GameData instance or None.
        """
        if game is None:
            # Clear PGN view
            self.pgn_view.set_pgn_text("")
            # Clear moves list
            if hasattr(self, 'moveslist_model'):
                self.moveslist_model.clear()
            return
        
        # Update PGN view with game's PGN notation
        self.pgn_view.set_pgn_text(game.pgn)
        
        # Update moves list with moves from game
        if hasattr(self, 'moveslist_model') and self._game_controller:
            moves = self._game_controller.extract_moves_from_game(game)
            # Clear existing moves
            self.moveslist_model.clear()
            # Add extracted moves
            for move in moves:
                self.moveslist_model.add_move(move)


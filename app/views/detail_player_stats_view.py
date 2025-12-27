"""Player Statistics view for detail panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QGridLayout, QSizePolicy, QComboBox, QPushButton, QRadioButton, QButtonGroup, QApplication,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QRectF, QEvent, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QAbstractAnimation, QTimer, QSize, QThread, pyqtSignal, QMutex, QMutexLocker
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QPalette
from app.views.detail_summary_view import PieChartWidget
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
from app.models.database_model import DatabaseModel

from app.models.game_model import GameModel
from app.controllers.game_controller import GameController
from app.utils.font_utils import resolve_font_family, scale_font_size

if TYPE_CHECKING:
    from app.controllers.player_stats_controller import PlayerStatsController
    from app.controllers.database_controller import DatabaseController
    from app.services.player_stats_service import AggregatedPlayerStats
    from app.services.error_pattern_service import ErrorPattern




class PlayerDropdownWorker(QThread):
    """Worker thread for populating player dropdown asynchronously."""
    
    players_ready = pyqtSignal(list)  # List of (player_name, game_count, analyzed_count) tuples
    progress_update = pyqtSignal(int, str)  # progress_percent, status_message
    
    def __init__(self, stats_controller: "PlayerStatsController", use_all_databases: bool) -> None:
        """Initialize the dropdown worker.
        
        Args:
            stats_controller: PlayerStatsController instance.
            use_all_databases: Whether to use all databases or just active.
        """
        super().__init__()
        self.stats_controller = stats_controller
        self.use_all_databases = use_all_databases
        self._cancelled = False
        self._mutex = QMutex()
    
    def cancel(self) -> None:
        """Cancel the worker."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
    
    def _is_cancelled(self) -> bool:
        """Check if worker is cancelled."""
        with QMutexLocker(self._mutex):
            return self._cancelled
    
    def run(self) -> None:
        """Run the worker to populate dropdown."""
        try:
            if self._is_cancelled():
                return
            
            self.progress_update.emit(10, "Collecting player names...")
            
            # Get unique players
            players = self.stats_controller.get_unique_players(self.use_all_databases)
            
            if self._is_cancelled() or not players:
                self.players_ready.emit([])
                return
            
            # Filter to only include players with at least 2 analyzed games
            players_with_analyzed = []
            total_players = len(players)
            
            for idx, (player_name, game_count) in enumerate(players):
                if self._is_cancelled():
                    return
                
                # Update progress
                progress_percent = 10 + int((idx / total_players) * 80)
                self.progress_update.emit(progress_percent, f"Checking players: {idx + 1}/{total_players}...")
                
                # Check if this player has at least 2 analyzed games
                analyzed_count, _ = self.stats_controller.get_analyzed_game_count(
                    player_name,
                    self.use_all_databases
                )
                
                if analyzed_count >= 2:
                    players_with_analyzed.append((player_name, game_count, analyzed_count))
            
            if not self._is_cancelled():
                try:
                    self.progress_update.emit(100, f"Found {len(players_with_analyzed)} player(s)")
                    self.players_ready.emit(players_with_analyzed)
                except RuntimeError:
                    # Receiver might be deleted, ignore
                    pass
        
        except Exception as e:
            # Emit empty list on error
            import sys
            print(f"Error in PlayerDropdownWorker: {e}", file=sys.stderr)
            self.players_ready.emit([])


class PlayerStatsCalculationWorker(QThread):
    """Worker thread for calculating player statistics asynchronously."""
    
    stats_ready = pyqtSignal(object, list, list)  # AggregatedPlayerStats, List[ErrorPattern], List[GameSummary]
    stats_unavailable = pyqtSignal(str)  # Reason key
    progress_update = pyqtSignal(int, str)  # progress_percent, status_message
    
    def __init__(self, stats_controller: "PlayerStatsController", player_name: str, use_all_databases: bool) -> None:
        """Initialize the stats calculation worker.
        
        Args:
            stats_controller: PlayerStatsController instance.
            player_name: Player name to analyze.
            use_all_databases: Whether to use all databases or just active.
        """
        super().__init__()
        self.stats_controller = stats_controller
        self.player_name = player_name
        self.use_all_databases = use_all_databases
        self._cancelled = False
        self._mutex = QMutex()
    
    def cancel(self) -> None:
        """Cancel the worker."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
    
    def _is_cancelled(self) -> bool:
        """Check if worker is cancelled."""
        with QMutexLocker(self._mutex):
            return self._cancelled
    
    def run(self) -> None:
        """Run the worker to calculate statistics."""
        try:
            if self._is_cancelled():
                return
            
            if not self.player_name or not self.player_name.strip():
                self.stats_unavailable.emit("no_player")
                return
            
            # Get databases
            self.progress_update.emit(5, "Loading databases...")
            
            if self.use_all_databases:
                panel_model = self.stats_controller._database_controller.get_panel_model()
                databases = panel_model.get_all_database_models()
            else:
                active_db = self.stats_controller._database_controller.get_active_database()
                databases = [active_db] if active_db else []
            
            if self._is_cancelled():
                return
            
            if not databases:
                self.stats_unavailable.emit("no_database")
                return
            
            # Get player games
            self.progress_update.emit(10, "Finding player games...")
            
            player_games, total_count = self.stats_controller.player_stats_service.get_player_games(
                self.player_name, databases, only_analyzed=False
            )
            
            if self._is_cancelled():
                return
            
            if not player_games:
                self.stats_unavailable.emit("player_not_found")
                return
            
            # Separate analyzed and unanalyzed
            analyzed_games = [g for g in player_games if g.analyzed]
            if not analyzed_games:
                self.stats_unavailable.emit("no_analyzed_games")
                return
            
            # Aggregate statistics
            self.progress_update.emit(20, f"Aggregating statistics from {len(analyzed_games)} game(s)...")
            
            aggregated_stats = self.stats_controller.player_stats_service.aggregate_player_statistics(
                self.player_name, analyzed_games, self.stats_controller._game_controller
            )
            
            if self._is_cancelled():
                return
            
            if not aggregated_stats:
                self.stats_unavailable.emit("calculation_error")
                return
            
            # Calculate game summaries for error pattern detection
            self.progress_update.emit(50, f"Analyzing {len(analyzed_games)} game(s) for patterns...")
            
            game_summaries: List = []
            total_games = len(analyzed_games)
            
            for idx, game in enumerate(analyzed_games):
                if self._is_cancelled():
                    return
                
                if not self.stats_controller._game_controller:
                    continue
                
                # Update progress
                progress_percent = 50 + int((idx / total_games) * 40)
                self.progress_update.emit(progress_percent, f"Analyzing game {idx + 1}/{total_games}...")
                
                moves = self.stats_controller._game_controller.extract_moves_from_game(game)
                if moves:
                    summary = self.stats_controller.summary_service.calculate_summary(moves, len(moves))
                    if summary:
                        game_summaries.append(summary)
            
            if self._is_cancelled():
                return
            
            # Detect error patterns
            self.progress_update.emit(90, "Detecting error patterns...")
            
            error_patterns = self.stats_controller.error_pattern_service.detect_error_patterns(
                self.player_name, analyzed_games, aggregated_stats, game_summaries
            )
            
            if not self._is_cancelled():
                try:
                    self.progress_update.emit(100, f"Statistics calculated for {self.player_name}")
                    self.stats_ready.emit(aggregated_stats, error_patterns, game_summaries)
                except RuntimeError:
                    # Receiver might be deleted, ignore
                    pass
        
        except Exception as e:
            # Emit error signal
            import sys
            print(f"Error in PlayerStatsCalculationWorker: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self.stats_unavailable.emit("error")


class PhaseBarChartWidget(QWidget):
    """Widget for displaying a horizontal bar chart comparing phase performance."""
    
    def __init__(self, config: Dict[str, Any], text_color: QColor, label_font: QFont, value_font: QFont, parent: Optional[QWidget] = None) -> None:
        """Initialize the phase bar chart widget.
        
        Args:
            config: Configuration dictionary.
            text_color: Text color for labels.
            label_font: Font for labels.
            value_font: Font for values.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.text_color = text_color
        self.label_font = label_font
        self.value_font = value_font
        
        # Get colors from config
        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        colors_config = player_stats_config.get('colors', {})
        phase_bar_chart_config = player_stats_config.get('phase_bar_chart', {})
        
        # Phase colors (use distinct colors for each phase)
        self.phase_colors = {
            'Opening': QColor(*colors_config.get('phase_opening_color', [100, 150, 255])),
            'Middlegame': QColor(*colors_config.get('phase_middlegame_color', [150, 255, 100])),
            'Endgame': QColor(*colors_config.get('phase_endgame_color', [255, 200, 100])),
        }
        
        # Chart configuration from config
        self.bar_height = phase_bar_chart_config.get('bar_height', 30)
        self.bar_spacing = phase_bar_chart_config.get('bar_spacing', 10)
        self.bar_padding = phase_bar_chart_config.get('bar_padding', 10)
        self.label_width = phase_bar_chart_config.get('label_width', 100)
        self.value_width = phase_bar_chart_config.get('value_width', 60)
        self.min_chart_width = phase_bar_chart_config.get('min_chart_width', 200)
        self.bar_border_radius = phase_bar_chart_config.get('bar_border_radius', 3)
        self.bar_pen_width = phase_bar_chart_config.get('bar_pen_width', 1)
        self.bar_value_spacing = phase_bar_chart_config.get('bar_value_spacing', 5)
        
        # Data: {phase_name: accuracy_percentage}
        self.data: Dict[str, float] = {}
        
        # Calculate minimum height: (bar_height * 3) + (bar_spacing * 2) + (bar_padding * 2)
        min_height = (self.bar_height * 3) + (self.bar_spacing * 2) + (self.bar_padding * 2)
        # Only set minimum height, allow width to shrink
        self.setMinimumHeight(min_height)
        self.setMinimumWidth(0)
    
    def set_data(self, data: Dict[str, float]) -> None:
        """Set bar chart data.
        
        Args:
            data: Dictionary mapping phase names to accuracy percentages.
        """
        self.data = data
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the bar chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        if not self.data:
            # No data - draw placeholder
            painter.setPen(self.text_color)
            painter.setFont(self.label_font)
            painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, "No data")
            return
        
        # Calculate max accuracy for scaling (use 100% as max)
        max_accuracy = 100.0
        
        # Calculate available width for bars (excluding labels and values)
        available_width = width - self.label_width - self.value_width - (self.bar_padding * 2)
        
        # Draw bars for each phase
        y_pos = self.bar_padding
        phases = ['Opening', 'Middlegame', 'Endgame']
        
        for phase in phases:
            if phase not in self.data:
                continue
            
            accuracy = self.data[phase]
            
            # Draw phase label
            painter.setPen(self.text_color)
            painter.setFont(self.label_font)
            label_rect = QRectF(self.bar_padding, y_pos, self.label_width, self.bar_height)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, phase)
            
            # Calculate bar width
            bar_width = (accuracy / max_accuracy) * available_width if max_accuracy > 0 else 0
            bar_x = self.bar_padding + self.label_width
            bar_rect = QRectF(bar_x, y_pos, bar_width, self.bar_height)
            
            # Draw bar
            color = self.phase_colors.get(phase, self.text_color)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color, self.bar_pen_width))
            painter.drawRoundedRect(bar_rect, self.bar_border_radius, self.bar_border_radius)
            
            # Draw value label
            painter.setPen(self.text_color)
            painter.setFont(self.value_font)
            value_rect = QRectF(bar_x + available_width + self.bar_value_spacing, y_pos, self.value_width, self.bar_height)
            painter.drawText(value_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{accuracy:.1f}%")
            
            y_pos += self.bar_height + self.bar_spacing


class DetailPlayerStatsView(QWidget):
    """Player statistics view displaying aggregated player performance."""
    
    def __init__(self, config: Dict[str, Any],
                 database_controller: Optional["DatabaseController"] = None,
                 game_model: Optional[GameModel] = None,
                 game_controller: Optional[GameController] = None,
                 stats_controller: Optional["PlayerStatsController"] = None,
                 database_panel = None) -> None:
        """Initialize the player stats view.
        
        Args:
            config: Configuration dictionary.
            database_controller: Optional DatabaseController for accessing databases.
            game_model: Optional GameModel instance to observe.
            game_controller: Optional GameController for navigation.
            stats_controller: Optional PlayerStatsController for providing statistics data.
            database_panel: Optional DatabasePanel instance for highlighting games.
        """
        super().__init__()
        self.config = config
        self._database_controller = database_controller
        self._game_model: Optional[GameModel] = None
        self._game_controller = game_controller
        self._stats_controller: Optional["PlayerStatsController"] = None
        self._database_panel = database_panel  # For highlighting games in database panel
        
        self.current_stats: Optional["AggregatedPlayerStats"] = None
        self.current_patterns: List["ErrorPattern"] = []
        self._current_player: Optional[str] = None
        self._use_all_databases: bool = False
        self._last_unavailable_reason: str = "no_player"
        
        # Async workers
        self._dropdown_worker: Optional[PlayerDropdownWorker] = None
        self._stats_worker: Optional[PlayerStatsCalculationWorker] = None
        
        # Database change tracking
        self._connected_databases: List[DatabaseModel] = []
        self._database_update_timer = QTimer()
        self._database_update_timer.setSingleShot(True)
        self._database_update_timer.timeout.connect(self._on_database_update_debounced)
        self._database_update_debounce_ms = 500  # Debounce database updates by 500ms
        
        # Get player stats config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        self.player_stats_config = panel_config.get('player_stats', {})
        self.placeholder_text_no_player = self.player_stats_config.get(
            'placeholder_text_no_player',
            'Select a player to view statistics'
        )
        self.placeholder_text_no_analyzed = self.player_stats_config.get(
            'placeholder_text_no_analyzed',
            'No analyzed games found for this player'
        )
        
        self._setup_ui()
        
        # Always create player selection section immediately (not just when stats are available)
        self._create_player_selection_section()
        
        # Initially show placeholder message (but keep player selection visible)
        self._set_disabled_placeholder_visible(True, self.placeholder_text_no_player)
        
        # Connect to models/controllers if provided
        if game_model:
            self.set_game_model(game_model)
        
        if stats_controller:
            self.set_stats_controller(stats_controller)
        
        # Connect to database panel model for active database changes
        # Note: This might be None initially, connection will be set up when controller is available
        self._connect_to_database_panel_model()
        
        # Connect to database change signals for automatic updates
        self._connect_to_database_changes()
        
        # Responsive width handling
        self._move_accuracy_widget: Optional[QWidget] = None
        self._pie_chart_widget: Optional[QWidget] = None
        self._move_classification_legend_widget: Optional[QWidget] = None
        self._move_classification_opacity_effect: Optional[QGraphicsOpacityEffect] = None
        self._move_classification_animation: Optional[QParallelAnimationGroup] = None
        self._move_classification_width_animation: Optional[QPropertyAnimation] = None
        self._move_classification_visible: bool = True
        self._move_classification_visibility_pending: bool = False
        self._move_classification_full_width: int = 0
        
        # Error patterns responsive handling
        self._error_patterns_widget: Optional[QWidget] = None
        self._error_pattern_items: List[Dict[str, Any]] = []  # List of {item, button, desc_label, full_text}
        
        # Openings responsive handling
        self._openings_widget: Optional[QWidget] = None
        self._openings_items: List[Dict[str, Any]] = []  # List of {label, value, full_text, compact_text}
        
        # Get responsive config
        responsive_config = self.player_stats_config.get('responsive', {})
        self.move_classification_collapse_threshold = responsive_config.get('move_classification_collapse_threshold', 500)
        self.error_patterns_collapse_threshold = responsive_config.get('error_patterns_collapse_threshold', 300)
        self.openings_collapse_threshold = responsive_config.get('openings_collapse_threshold', 350)
        self.animation_duration = responsive_config.get('animation_duration_ms', 200)
        
        # Event filter will be installed on scroll_area in _setup_ui
    
    def cleanup(self) -> None:
        """Clean up resources when view is being destroyed."""
        # Stop timer first
        self._database_update_timer.stop()
        
        # Cancel and wait for workers
        if self._dropdown_worker:
            if self._dropdown_worker.isRunning():
                self._dropdown_worker.cancel()
                self._dropdown_worker.wait(3000)  # Wait up to 3 seconds
            # Disconnect signals before deleting
            try:
                self._dropdown_worker.players_ready.disconnect()
                self._dropdown_worker.progress_update.disconnect()
                self._dropdown_worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._dropdown_worker.deleteLater()
            self._dropdown_worker = None
        
        if self._stats_worker:
            if self._stats_worker.isRunning():
                self._stats_worker.cancel()
                self._stats_worker.wait(3000)  # Wait up to 3 seconds
            # Disconnect signals before deleting
            try:
                self._stats_worker.stats_ready.disconnect()
                self._stats_worker.stats_unavailable.disconnect()
                self._stats_worker.progress_update.disconnect()
                self._stats_worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._stats_worker.deleteLater()
            self._stats_worker = None
        
        # Disconnect from databases
        for database in self._connected_databases:
            try:
                database.dataChanged.disconnect(self._on_database_data_changed)
            except (RuntimeError, TypeError):
                pass
        self._connected_databases.clear()
    
    def _setup_ui(self) -> None:
        """Setup the player stats UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Get layout config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        layout_config = player_stats_config.get('layout', {})
        margins = layout_config.get('margins', [10, 10, 10, 10])
        spacing = layout_config.get('spacing', 15)
        
        # Scrollable content area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # Get background color for scroll area - use pane_background from tabs config
        tabs_config = panel_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        # Apply scrollbar styling using StyleManager
        from app.views.style import StyleManager
        border_color = [min(255, pane_bg[0] + 20), min(255, pane_bg[1] + 20), min(255, pane_bg[2] + 20)]
        StyleManager.style_scroll_area(
            self.scroll_area,
            self.config,
            pane_bg,
            border_color,
            0  # No border radius
        )
        
        # Content widget
        self.content_widget = QWidget()
        # Set minimum width to 0 to allow proper shrinking
        self.content_widget.setMinimumWidth(0)
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        self.content_layout.setSpacing(spacing)
        
        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)
        
        # Install event filter on scroll area to monitor width changes
        self.scroll_area.installEventFilter(self)
        
        # Disabled state placeholder (matches summary view style)
        # This will be shown when no player is selected, inside the content layout
        placeholder_config = player_stats_config.get('placeholder', {})
        placeholder_text_color = placeholder_config.get('text_color', [150, 150, 150])
        placeholder_font_size = int(scale_font_size(placeholder_config.get('font_size', 14)))
        placeholder_padding = placeholder_config.get('padding', 20)
        
        self.disabled_placeholder = QLabel(self.placeholder_text_no_player)
        self.disabled_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.disabled_placeholder.setWordWrap(True)
        self.disabled_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.disabled_placeholder.setStyleSheet(f"""
            QLabel {{
                color: rgb({placeholder_text_color[0]}, {placeholder_text_color[1]}, {placeholder_text_color[2]});
                font-size: {placeholder_font_size}pt;
                padding: {placeholder_padding}px;
            }}
        """)
        self.disabled_placeholder.hide()
        # Don't add to main layout - will be added to content_layout after player selection section
    
    def set_game_model(self, game_model: GameModel) -> None:
        """Set the game model to observe."""
        if self._game_model:
            try:
                self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
            except (RuntimeError, TypeError):
                pass
        
        self._game_model = game_model
        if self._game_model:
            self._game_model.active_game_changed.connect(self._on_active_game_changed)
            # Auto-select player from active game if available
            if self._game_model.active_game:
                self._on_active_game_changed(self._game_model.active_game)
    
    def set_stats_controller(self, stats_controller: "PlayerStatsController") -> None:
        """Attach the stats controller supplying data for this view."""
        if self._stats_controller:
            try:
                self._stats_controller.stats_updated.disconnect(self._handle_stats_updated)
                self._stats_controller.stats_unavailable.disconnect(self._handle_stats_unavailable)
            except (RuntimeError, TypeError):
                pass
        
        self._stats_controller = stats_controller
        
        if self._stats_controller:
            self._stats_controller.stats_updated.connect(self._handle_stats_updated)
            self._stats_controller.stats_unavailable.connect(self._handle_stats_unavailable)
            
            # Update database controller reference if available
            if not self._database_controller and hasattr(self._stats_controller, '_database_controller'):
                self._database_controller = self._stats_controller._database_controller
                # Reconnect to database changes now that we have the controller
                self._connect_to_database_changes()
                self._connect_to_database_panel_model()
            
            # Populate player dropdown if selection section already exists
            # Use QTimer.singleShot to ensure this happens after the UI is fully set up
            has_combo_attr = hasattr(self, 'player_combo')
            if has_combo_attr:
                combo_value = getattr(self, 'player_combo', None)
                if combo_value is not None:
                    QTimer.singleShot(100, self._populate_player_dropdown)
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change - auto-select player if available."""
        if not game:
            return
        
        # Try to auto-select player from active game
        if self._stats_controller and hasattr(self, 'player_combo'):
            # Check if player is in dropdown
            player_name = game.white or game.black
            if player_name:
                # Find and select in combo box
                for i in range(self.player_combo.count()):
                    item_text = self.player_combo.itemText(i)
                    if item_text.startswith(player_name):
                        self.player_combo.setCurrentIndex(i)
                        self._on_player_selected()
                        break
    
    def _handle_stats_updated(self, stats: "AggregatedPlayerStats", 
                              patterns: List["ErrorPattern"],
                              game_summaries: List) -> None:
        """Render the stats content when new data is available."""
        self.current_stats = stats
        self.current_patterns = patterns
        self._last_unavailable_reason = ""
        
        self._set_disabled_placeholder_visible(False)
        
        self._clear_content()
        self._build_stats_content()
    
    def _handle_stats_unavailable(self, reason: str) -> None:
        """Show appropriate placeholder when stats data is unavailable."""
        self.current_stats = None
        self.current_patterns = []
        self._last_unavailable_reason = reason or "no_player"
        
        self._clear_content()
        
        placeholder_text = self.placeholder_text_no_player
        if reason == "no_analyzed_games":
            placeholder_text = self.placeholder_text_no_analyzed
        elif reason == "player_not_found":
            placeholder_text = "Player not found in selected database(s)"
        elif reason == "no_database":
            placeholder_text = "No database available"
        
        self._set_disabled_placeholder_visible(True, placeholder_text)
    
    def _set_disabled_placeholder_visible(self, visible: bool, text: Optional[str] = None) -> None:
        """Show or hide the disabled placeholder.
        
        Note: This only hides/shows the placeholder label, not the entire content widget.
        The player selection section should always be visible.
        """
        if not hasattr(self, 'disabled_placeholder') or not self.disabled_placeholder:
            return
        
        try:
            if visible:
                if text:
                    self.disabled_placeholder.setText(text)
                # When visible, use Expanding to fill available space
                self.disabled_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self.disabled_placeholder.show()
            else:
                # When hidden, use Minimum to not reserve space
                self.disabled_placeholder.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                self.disabled_placeholder.hide()
        except RuntimeError:
            pass
    
    def _clear_content(self) -> None:
        """Clear all content widgets except placeholder and player selection."""
        # Don't clear - we want to keep player selection section visible
        # This method is called when stats are unavailable, but we still want player selection
        pass
    
    def _clear_stats_sections(self) -> None:
        """Clear only the stats sections (coverage banner, overview, phases, patterns).
        
        Keeps the player selection section visible.
        Also removes spacing items to prevent accumulation.
        """
        # Clear stored widget references first to prevent access to deleted widgets
        self._move_accuracy_widget = None
        self._pie_chart_widget = None
        self._move_classification_legend_widget = None
        self._openings_widget = None
        self._error_patterns_widget = None
        
        # Find player selection widget index
        player_selection_index = -1
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # Check if this is the player selection widget (has player_combo attribute)
                if hasattr(widget, 'player_combo') or (hasattr(self, 'player_selection_widget') and widget == self.player_selection_widget):
                    player_selection_index = i
                    break
        
        # Remove all items (widgets AND spacing) after player selection
        # Keep placeholder (last item) and player selection
        items_to_remove = []
        for i in range(self.content_layout.count() - 1, -1, -1):  # Iterate backwards
            if i <= player_selection_index:
                continue  # Keep player selection and everything before it
            item = self.content_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget and widget != self.disabled_placeholder:
                    items_to_remove.append(i)
                elif not widget:  # This is a spacing item (QSpacerItem)
                    items_to_remove.append(i)
        
        for i in items_to_remove:
            item = self.content_layout.takeAt(i)
            if item:
                widget = item.widget()
                if widget:
                    try:
                        # Disconnect any signals before deletion to prevent callbacks on deleted widgets
                        # Note: Most widgets don't have signals, but buttons might
                        if hasattr(widget, 'clicked'):
                            try:
                                widget.clicked.disconnect()
                            except (RuntimeError, TypeError):
                                pass
                        widget.setParent(None)
                        widget.deleteLater()
                    except RuntimeError:
                        pass
                del item
    
    
    def _build_stats_content(self) -> None:
        """Build the player statistics content widgets."""
        if not self.current_stats:
            return
        
        # Clear existing stats content (but keep player selection section)
        # Find and remove stats sections (everything after player selection)
        # This also clears all stored widget references
        self._clear_stats_sections()
        
        # Ensure all widget references are None before creating new widgets
        self._move_accuracy_widget = None
        self._pie_chart_widget = None
        self._move_classification_legend_widget = None
        self._openings_widget = None
        self._error_patterns_widget = None
        
        # Get config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        colors_config = player_stats_config.get('colors', {})
        fonts_config = player_stats_config.get('fonts', {})
        layout_config = player_stats_config.get('layout', {})
        widgets_config = player_stats_config.get('widgets', {})
        
        text_color = QColor(*colors_config.get('text_color', [220, 220, 220]))
        header_text_color = QColor(*colors_config.get('header_text', [240, 240, 240]))
        background_color = QColor(*colors_config.get('background', [40, 40, 45]))
        section_bg_color = QColor(*colors_config.get('section_background', [35, 35, 40]))
        border_color = QColor(*colors_config.get('border', [60, 60, 65]))
        
        # Widget styling configuration
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        row_spacing = widgets_config.get('row_spacing', 5)
        
        header_font = QFont(resolve_font_family(fonts_config.get('header_font_family', 'Helvetica Neue')),
                           int(scale_font_size(fonts_config.get('header_font_size', 14))))
        header_font.setBold(fonts_config.get('header_font_weight', 'bold') == 'bold')
        label_font = QFont(resolve_font_family(fonts_config.get('label_font_family', 'Helvetica Neue')),
                          int(scale_font_size(fonts_config.get('label_font_size', 11))))
        value_font = QFont(resolve_font_family(fonts_config.get('value_font_family', 'Helvetica Neue')),
                          int(scale_font_size(fonts_config.get('value_font_size', 11))))
        
        section_spacing_val = layout_config.get('section_spacing', 20)
        
        # Analysis Coverage Banner removed - redundant with "Total Games" in Overview
        
        # Overview Section
        self._add_section_header("Overview", header_font, header_text_color)
        overview_widget = self._create_overview_widget(
            self.current_stats, text_color, label_font, value_font,
            section_bg_color, border_color, widgets_config
        )
        self.content_layout.addWidget(overview_widget)
        self.content_layout.addSpacing(section_spacing_val)
        
        # Move Accuracy Section
        self._add_section_header("Move Accuracy", header_font, header_text_color)
        move_accuracy_widget = self._create_move_accuracy_widget(
            self.current_stats, text_color, label_font, value_font,
            section_bg_color, border_color, widgets_config
        )
        # Store reference for responsive width handling
        self._move_accuracy_widget = move_accuracy_widget
        self.content_layout.addWidget(move_accuracy_widget)
        self.content_layout.addSpacing(section_spacing_val)
        
        # Performance by Phase Section
        self._add_section_header("Performance by Phase", header_font, header_text_color)
        phase_widget = self._create_phase_performance_widget(
            self.current_stats, text_color, label_font, value_font,
            section_bg_color, border_color, widgets_config
        )
        self.content_layout.addWidget(phase_widget)
        self.content_layout.addSpacing(section_spacing_val)
        
        # Openings Section
        if self.current_stats and (self.current_stats.top_openings or 
                                    self.current_stats.worst_accuracy_openings or 
                                    self.current_stats.best_accuracy_openings):
            self._add_section_header("Openings", header_font, header_text_color)
            openings_widget = self._create_openings_widget(
                self.current_stats, text_color, label_font, value_font,
                section_bg_color, border_color, widgets_config
            )
            self.content_layout.addWidget(openings_widget)
            self.content_layout.addSpacing(section_spacing_val)
        
        # Error Patterns Section
        if self.current_patterns:
            self._add_section_header("Error Patterns", header_font, header_text_color)
            patterns_widget = self._create_error_patterns_widget(
                self.current_patterns, text_color, label_font, value_font,
                section_bg_color, border_color, widgets_config
            )
            self.content_layout.addWidget(patterns_widget)
            self.content_layout.addSpacing(section_spacing_val)
        
        # Add stretch at end
        self.content_layout.addStretch()
    
    def _create_player_selection_section(self) -> None:
        """Create the player selection section."""
        # Avoid creating duplicate if already exists
        if hasattr(self, 'player_selection_widget') and self.player_selection_widget:
            return
        
        # Get config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        selection_config = player_stats_config.get('player_selection', {})
        
        colors_config = player_stats_config.get('colors', {})
        section_bg_color = QColor(*colors_config.get('section_background', [35, 35, 40]))
        border_color = QColor(*colors_config.get('border', [60, 60, 65]))
        text_color = QColor(*colors_config.get('text_color', [220, 220, 220]))
        
        fonts_config = player_stats_config.get('fonts', {})
        label_font = QFont(resolve_font_family(fonts_config.get('label_font_family', 'Helvetica Neue')),
                          int(scale_font_size(fonts_config.get('label_font_size', 11))))
        
        widgets_config = player_stats_config.get('widgets', {})
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        
        # Create container
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: rgb({section_bg_color.red()}, {section_bg_color.green()}, {section_bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Player dropdown row
        player_row = QHBoxLayout()
        selection_row_spacing = selection_config.get('row_spacing', 8)
        player_row.setSpacing(selection_row_spacing)
        
        player_label = QLabel("Player:")
        player_label.setFont(label_font)
        player_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        player_row.addWidget(player_label)
        
        # Player combo box - make non-editable and clickable anywhere to open dropdown
        self.player_combo = QComboBox()
        self.player_combo.currentIndexChanged.connect(self._on_player_selected)
        self.player_combo.activated.connect(self._on_player_activated)  # Fired when user selects from dropdown
        player_row.addWidget(self.player_combo, 1)  # Use stretch factor to make it responsive
        
        # Apply combobox styling using StyleManager
        # StyleManager reads combobox-specific settings (like padding) from centralized config automatically
        button_config = player_stats_config.get('button', {})
        font_config = player_stats_config.get('fonts', {})
        
        # Get colors - use text color from view config, input colors from standard defaults (matching dialogs)
        combo_text = list(colors_config.get('text_color', [220, 220, 220]))
        combo_bg = [30, 30, 35]  # Standard input background (matching dialogs)
        combo_border = [60, 60, 65]  # Standard input border (matching dialogs)
        combo_focus = [70, 90, 130]  # Standard focus border (matching dialogs)
        
        # Get fonts from view config
        font_family = resolve_font_family(font_config.get('label_font_family', 'Helvetica Neue'))
        font_size = scale_font_size(font_config.get('label_font_size', 11))
        
        # Get button height to match button styling
        button_height = button_config.get('height', 28)
        
        # Selection colors - use standard defaults (matching dialogs)
        selection_bg = [70, 90, 130]
        selection_text = [240, 240, 240]
        
        from app.views.style import StyleManager
        StyleManager.style_comboboxes(
            [self.player_combo],
            self.config,
            combo_text,
            font_family,
            font_size,
            combo_bg,
            combo_border,
            combo_focus,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=3,
            editable=False
        )
        
        # Set button height to match button styling
        self.player_combo.setMinimumHeight(button_height)
        self.player_combo.setMaximumHeight(button_height)
        
        # Refresh button removed - dropdown auto-refreshes when databases change
        
        layout.addLayout(player_row)
        
        # Data source radio buttons
        source_row = QHBoxLayout()
        source_row.setSpacing(selection_row_spacing)
        
        source_label = QLabel("Data Source:")
        source_label.setFont(label_font)
        source_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        source_row.addWidget(source_label)
        
        self.source_button_group = QButtonGroup()
        self.active_db_radio = QRadioButton("Active Database")
        self.all_db_radio = QRadioButton("All Open Databases")
        self.source_button_group.addButton(self.active_db_radio, 0)
        self.source_button_group.addButton(self.all_db_radio, 1)
        
        # Always default to "Active Database"
        self.active_db_radio.setChecked(True)
        self._use_all_databases = False
        
        self.active_db_radio.toggled.connect(self._on_source_changed)
        self.all_db_radio.toggled.connect(self._on_source_changed)
        
        # Style radio buttons with text color and palette to prevent macOS override
        radio_style = f"QRadioButton {{ color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); }}"
        self.active_db_radio.setStyleSheet(radio_style)
        self.all_db_radio.setStyleSheet(radio_style)
        
        # Set palette to prevent macOS override
        radio_palette = self.active_db_radio.palette()
        radio_palette.setColor(self.active_db_radio.foregroundRole(), text_color)
        self.active_db_radio.setPalette(radio_palette)
        self.active_db_radio.update()
        
        all_db_palette = self.all_db_radio.palette()
        all_db_palette.setColor(self.all_db_radio.foregroundRole(), text_color)
        self.all_db_radio.setPalette(all_db_palette)
        self.all_db_radio.update()
        
        source_row.addWidget(self.active_db_radio)
        source_row.addWidget(self.all_db_radio)
        source_row.addStretch()
        
        layout.addLayout(source_row)
        
        # Store reference to widget
        self.player_selection_widget = container
        
        # Insert at the beginning
        self.content_layout.insertWidget(0, container)
        
        # Add placeholder after player selection (will be shown/hidden as needed)
        self.content_layout.addWidget(self.disabled_placeholder, 1)  # Give it stretch factor
        
        # Populate player dropdown if controller is available
        # Use QTimer.singleShot to ensure this happens after the UI is fully set up
        if self._stats_controller:
            QTimer.singleShot(100, self._populate_player_dropdown)
    
    def _populate_player_dropdown(self) -> None:
        """Populate the player dropdown with available players asynchronously."""
        if not self._stats_controller:
            return
        
        # Update database controller reference if available
        if not self._database_controller and hasattr(self._stats_controller, '_database_controller'):
            self._database_controller = self._stats_controller._database_controller
        
        # Schedule async update
        self._schedule_dropdown_update()
    
    def _on_player_activated(self, index: int) -> None:
        """Handle player selection from dropdown (user clicked on item)."""
        if index < 0:
            return
        self._on_player_selected(index)
    
    def _on_player_selected(self, index: int = -1) -> None:
        """Handle player selection from combo box."""
        if not hasattr(self, 'player_combo') or not self.player_combo:
            return
        
        # Get selected index if not provided
        if index == -1:
            index = self.player_combo.currentIndex()
        
        if index == -1 or index < 0:
            # Check if there's text in the editable field
            text = self.player_combo.currentText()
            if text and " (" in text:
                # Extract player name from display text
                player_name = text.split(" (")[0].strip()
                if player_name:
                    # Find matching item
                    for i in range(self.player_combo.count()):
                        item_data = self.player_combo.itemData(i)
                        if item_data == player_name:
                            index = i
                            break
                    if index >= 0:
                        # Temporarily disconnect to avoid recursion
                        self.player_combo.currentIndexChanged.disconnect()
                        self.player_combo.setCurrentIndex(index)
                        self.player_combo.currentIndexChanged.connect(self._on_player_selected)
            
            if index == -1 or index < 0:
                self._current_player = None
                self._set_disabled_placeholder_visible(True, self.placeholder_text_no_player)
                self._clear_stats_sections()
                return
        
        # Get player name from combo box data
        player_name = self.player_combo.itemData(index)
        if not player_name:
            # Fallback: extract from display text
            display_text = self.player_combo.itemText(index)
            if " (" in display_text:
                player_name = display_text.split(" (")[0]
            else:
                player_name = display_text.strip()
        
        if player_name and player_name != self._current_player:
            self._current_player = player_name
            self._schedule_stats_recalculation()
    
    def _apply_button_styling(self, button: QPushButton) -> None:
        """Apply standard button styling from config."""
        ui_config = self.config.get('ui', {})
        detail_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = detail_config.get('player_stats', {})
        button_config = player_stats_config.get('button', {})
        
        button_height = button_config.get('height', 28)
        button_border_radius = button_config.get('border_radius', 4)
        padding_values = button_config.get('padding', [6, 4])
        if not isinstance(padding_values, (list, tuple)) or len(padding_values) < 2:
            padding_values = [6, 4]
        button_padding = [padding_values[0], padding_values[1]]
        
        background_color = button_config.get('background_color', [50, 50, 55])
        text_color = button_config.get('text_color', [200, 200, 200])
        border_color = button_config.get('border_color', [60, 60, 65])
        hover_bg = button_config.get('hover_background_color', [60, 60, 65])
        hover_text = button_config.get('hover_text_color', [240, 240, 240])
        pressed_offset = button_config.get('pressed_background_offset', 10)
        from app.utils.font_utils import resolve_font_family, scale_font_size
        font_family = resolve_font_family(button_config.get('font_family', 'Helvetica Neue'))
        font_size = int(scale_font_size(button_config.get('font_size', 10)))
        
        button_stylesheet = f"""
            QPushButton {{
                background-color: rgb({background_color[0]}, {background_color[1]}, {background_color[2]});
                color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
                border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
                border-radius: {button_border_radius}px;
                padding: {button_padding[0]}px {button_padding[1]}px;
                min-height: {button_height}px;
                max-height: {button_height}px;
                font-family: "{font_family}";
                font-size: {font_size}pt;
            }}
            QPushButton:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            QPushButton:pressed {{
                background-color: rgb({min(255, background_color[0] + pressed_offset)}, {min(255, background_color[1] + pressed_offset)}, {min(255, background_color[2] + pressed_offset)});
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """
        button.setMinimumHeight(button_height)
        button.setStyleSheet(button_stylesheet)
    
    
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self._populate_player_dropdown()
    
    def _on_source_changed(self) -> None:
        """Handle data source radio button change."""
        # Update flag
        self._use_all_databases = self.all_db_radio.isChecked()
        
        # Reconnect to database changes (different set of databases)
        self._connect_to_database_changes()
        
        # Repopulate dropdown asynchronously
        # Use QTimer to debounce rapid changes
        QTimer.singleShot(100, self._populate_player_dropdown)
        
        # If a player is selected, recalculate stats with new source
        if self._current_player:
            QTimer.singleShot(200, self._schedule_stats_recalculation)
    
    def _schedule_stats_recalculation(self) -> None:
        """Schedule an asynchronous statistics recalculation."""
        if not self._current_player or not self._stats_controller:
            return
        
        # If a worker is already running, cancel it and wait for it to finish
        if self._stats_worker:
            if self._stats_worker.isRunning():
                self._stats_worker.cancel()
                # Wait for worker to finish (with timeout)
                if not self._stats_worker.wait(2000):  # Wait up to 2 seconds
                    # If it didn't finish, disconnect signals and delete later
                    try:
                        self._stats_worker.stats_ready.disconnect()
                        self._stats_worker.stats_unavailable.disconnect()
                        self._stats_worker.progress_update.disconnect()
                        self._stats_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._stats_worker.deleteLater()
                    self._stats_worker = None
                else:
                    # Worker finished, disconnect and clean up
                    try:
                        self._stats_worker.stats_ready.disconnect()
                        self._stats_worker.stats_unavailable.disconnect()
                        self._stats_worker.progress_update.disconnect()
                        self._stats_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._stats_worker.deleteLater()
                    self._stats_worker = None
            else:
                # Worker not running, just clean up
                try:
                    self._stats_worker.stats_ready.disconnect()
                    self._stats_worker.stats_unavailable.disconnect()
                    self._stats_worker.progress_update.disconnect()
                    self._stats_worker.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self._stats_worker.deleteLater()
                self._stats_worker = None
        
        # Create and start new worker
        self._stats_worker = PlayerStatsCalculationWorker(
            self._stats_controller,
            self._current_player,
            self._use_all_databases
        )
        self._stats_worker.stats_ready.connect(self._on_stats_ready)
        self._stats_worker.stats_unavailable.connect(self._handle_stats_unavailable)
        self._stats_worker.progress_update.connect(self._on_stats_progress)
        self._stats_worker.finished.connect(self._on_stats_worker_finished)
        self._stats_worker.start()
    
    def _on_stats_progress(self, progress: int, status: str) -> None:
        """Handle progress update from stats worker."""
        # Show progress in status bar
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_indeterminate(False)
        progress_service.set_progress(progress)
        progress_service.set_status(status)
    
    def _on_stats_ready(self, stats: "AggregatedPlayerStats", patterns: List["ErrorPattern"], game_summaries: List) -> None:
        """Handle stats ready from worker."""
        # Hide progress
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.hide_progress()
        
        # Update controller's current stats
        if self._stats_controller:
            self._stats_controller.current_stats = stats
            self._stats_controller.current_patterns = patterns
            self._stats_controller.current_game_summaries = game_summaries
        
        # Handle the stats update
        self._handle_stats_updated(stats, patterns, game_summaries)
    
    def _on_stats_worker_finished(self) -> None:
        """Handle stats worker finished."""
        # Clean up worker reference - use deleteLater to ensure safe deletion
        # Only clean up if this is still the current worker (might have been replaced)
        if self._stats_worker and self.sender() == self._stats_worker:
            worker = self._stats_worker
            self._stats_worker = None
            # Disconnect signals before deleting
            try:
                worker.stats_ready.disconnect()
                worker.stats_unavailable.disconnect()
                worker.progress_update.disconnect()
                worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            worker.deleteLater()
    
    def _connect_to_database_panel_model(self) -> None:
        """Connect to database panel model signals for active database changes."""
        if not self._database_controller:
            return
        
        panel_model = self._database_controller.get_panel_model()
        if not panel_model:
            return
        
        # Disconnect first to avoid duplicate connections
        try:
            panel_model.active_database_changed.disconnect(self._on_active_database_changed)
            panel_model.database_added.disconnect(self._on_database_added)
            panel_model.database_removed.disconnect(self._on_database_removed)
        except (RuntimeError, TypeError):
            pass  # Not connected yet, that's fine
        
        # Connect to active database changes
        panel_model.active_database_changed.connect(self._on_active_database_changed)
        panel_model.database_added.connect(self._on_database_added)
        panel_model.database_removed.connect(self._on_database_removed)
    
    def _connect_to_database_changes(self) -> None:
        """Connect to DatabaseModel dataChanged signals to detect game updates."""
        if not self._database_controller:
            return
        
        # Disconnect from all previously connected databases
        for database in self._connected_databases:
            try:
                database.dataChanged.disconnect(self._on_database_data_changed)
            except (RuntimeError, TypeError):
                pass
        
        self._connected_databases.clear()
        
        # Connect to all current databases
        panel_model = self._database_controller.get_panel_model()
        if panel_model:
            databases = panel_model.get_all_database_models()
            for database in databases:
                database.dataChanged.connect(self._on_database_data_changed)
                self._connected_databases.append(database)
    
    def _on_database_added(self, identifier: str, info) -> None:
        """Handle database added - connect to its signals."""
        if info and info.model:
            info.model.dataChanged.connect(self._on_database_data_changed)
            if info.model not in self._connected_databases:
                self._connected_databases.append(info.model)
            # Always trigger dropdown update when database is added
            # (will update if using all databases, or if this becomes the active database)
            # Use QTimer to ensure this happens after the database is fully initialized
            QTimer.singleShot(200, self._schedule_dropdown_update)
    
    def _on_database_removed(self, identifier: str) -> None:
        """Handle database removed - disconnect from its signals."""
        # Remove from connected list (will be cleaned up on next connection refresh)
        # The database model may already be destroyed, so we just refresh connections
        self._connect_to_database_changes()
    
    def _on_database_data_changed(self, top_left, bottom_right, roles=None) -> None:
        """Handle database data changed signal - debounce and update."""
        # Debounce the update to avoid excessive recalculations
        self._database_update_timer.stop()
        self._database_update_timer.start(self._database_update_debounce_ms)
    
    def _on_database_update_debounced(self) -> None:
        """Handle debounced database update - refresh dropdown and recalculate stats."""
        # Update dropdown asynchronously
        self._schedule_dropdown_update()
        
        # If a player is selected, update their counts and recalculate stats
        if self._current_player:
            self._update_selected_player_counts()
            self._schedule_stats_recalculation()
    
    def _schedule_dropdown_update(self) -> None:
        """Schedule an asynchronous dropdown update."""
        if not self._stats_controller:
            return
        
        # Check if combo box exists - use getattr with default to avoid AttributeError
        try:
            combo_value = getattr(self, 'player_combo', None)
        except Exception:
            combo_value = None
        
        if combo_value is None:
            return
        
        # If a worker is already running, cancel it and wait for it to finish
        if self._dropdown_worker:
            if self._dropdown_worker.isRunning():
                self._dropdown_worker.cancel()
                # Wait for worker to finish (with timeout)
                if not self._dropdown_worker.wait(2000):  # Wait up to 2 seconds
                    # If it didn't finish, disconnect signals and delete later
                    try:
                        self._dropdown_worker.players_ready.disconnect()
                        self._dropdown_worker.progress_update.disconnect()
                        self._dropdown_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._dropdown_worker.deleteLater()
                    self._dropdown_worker = None
                else:
                    # Worker finished, disconnect and clean up
                    try:
                        self._dropdown_worker.players_ready.disconnect()
                        self._dropdown_worker.progress_update.disconnect()
                        self._dropdown_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._dropdown_worker.deleteLater()
                    self._dropdown_worker = None
            else:
                # Worker not running, just clean up
                try:
                    self._dropdown_worker.players_ready.disconnect()
                    self._dropdown_worker.progress_update.disconnect()
                    self._dropdown_worker.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self._dropdown_worker.deleteLater()
                self._dropdown_worker = None
        
        # Create and start new worker
        try:
            self._dropdown_worker = PlayerDropdownWorker(self._stats_controller, self._use_all_databases)
            self._dropdown_worker.players_ready.connect(self._on_dropdown_players_ready)
            self._dropdown_worker.progress_update.connect(self._on_dropdown_progress)
            self._dropdown_worker.finished.connect(self._on_dropdown_worker_finished)
            self._dropdown_worker.start()
        except Exception as e:
            import sys
            print(f"Error starting dropdown worker: {e}", file=sys.stderr)
            if self._dropdown_worker:
                self._dropdown_worker.deleteLater()
                self._dropdown_worker = None
    
    def _on_dropdown_progress(self, progress: int, status: str) -> None:
        """Handle progress update from dropdown worker."""
        # Optionally show progress in status bar for long operations
        # For now, we'll keep it silent to avoid UI noise
        pass
    
    def _on_dropdown_players_ready(self, players_with_analyzed: List[Tuple[str, int, int]]) -> None:
        """Handle players ready from dropdown worker."""
        # Check if view still exists and combo box is available
        try:
            has_combo_attr = hasattr(self, 'player_combo')
            if not has_combo_attr:
                return
            
            combo_value = getattr(self, 'player_combo', None)
            if combo_value is None:
                return
            
            # Try to access a method to verify the widget is still valid
            try:
                # This will raise RuntimeError if the widget has been deleted
                combo_value.count()
            except RuntimeError:
                return
        except RuntimeError:
            # View might be destroyed
            return
        
        # Temporarily disconnect signal to prevent auto-selection
        try:
            self.player_combo.currentIndexChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        
        # Store current selection
        current_player = self._current_player
        current_index = self.player_combo.currentIndex()
        
        # Clear and repopulate dropdown
        try:
            self.player_combo.clear()
        except RuntimeError:
            return
        
        # Track if current player still exists and what their new counts are
        current_player_found = False
        current_player_analyzed = 0
        current_player_total = 0
        
        try:
            for player_name, game_count, analyzed_count in players_with_analyzed:
                display_text = f"{player_name} ({analyzed_count} analyzed, {game_count} total)"
                self.player_combo.addItem(display_text, player_name)
                
                if current_player and player_name == current_player:
                    current_player_found = True
                    current_player_analyzed = analyzed_count
                    current_player_total = game_count
            
            # Reconnect signal
            self.player_combo.currentIndexChanged.connect(self._on_player_selected)
            
            # Restore selection or update if player still exists
            if current_player_found:
                # Find the index of the current player
                index = self.player_combo.findData(current_player)
                if index != -1:
                    # Temporarily disconnect to avoid triggering selection
                    try:
                        self.player_combo.currentIndexChanged.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self.player_combo.setCurrentIndex(index)
                    self.player_combo.currentIndexChanged.connect(self._on_player_selected)
                    
                    # Update the item text silently if counts changed
                    current_text = self.player_combo.currentText()
                    expected_text = f"{current_player} ({current_player_analyzed} analyzed, {current_player_total} total)"
                    if current_text != expected_text:
                        self.player_combo.setItemText(index, expected_text)
            elif current_player:
                # Player no longer in list, clear selection
                self.player_combo.setCurrentIndex(-1)
                self._current_player = None
                self._set_disabled_placeholder_visible(True, self.placeholder_text_no_player)
                self._clear_stats_sections()
            else:
                # No previous selection, ensure combo is empty
                self.player_combo.setCurrentIndex(-1)
        except RuntimeError:
            # View might be destroyed during update
            return
    
    def _on_dropdown_worker_finished(self) -> None:
        """Handle dropdown worker finished."""
        # Clean up worker reference - use deleteLater to ensure safe deletion
        # Only clean up if this is still the current worker (might have been replaced)
        if self._dropdown_worker and self.sender() == self._dropdown_worker:
            worker = self._dropdown_worker
            self._dropdown_worker = None
            # Disconnect signals before deleting
            try:
                worker.players_ready.disconnect()
                worker.progress_update.disconnect()
                worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            worker.deleteLater()
    
    def _update_selected_player_counts(self) -> None:
        """Update the counts for the currently selected player in the dropdown."""
        if not self._current_player or not hasattr(self, 'player_combo') or not self.player_combo:
            return
        
        if not self._stats_controller:
            return
        
        # Get updated counts
        analyzed_count, total_count = self._stats_controller.get_analyzed_game_count(
            self._current_player,
            self._use_all_databases
        )
        
        # Find the player in the dropdown
        index = self.player_combo.findData(self._current_player)
        if index != -1:
            # Update the item text silently
            new_text = f"{self._current_player} ({analyzed_count} analyzed, {total_count} total)"
            current_text = self.player_combo.itemText(index)
            if current_text != new_text:
                # Temporarily disconnect to avoid triggering selection
                try:
                    self.player_combo.currentIndexChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self.player_combo.setItemText(index, new_text)
                self.player_combo.currentIndexChanged.connect(self._on_player_selected)
    
    def _on_active_database_changed(self, database) -> None:
        """Handle active database change - repopulate dropdown if 'Active Database' is selected."""
        # Reconnect to database changes
        self._connect_to_database_changes()
        
        # Only repopulate if "Active Database" is selected (not "All Open Databases")
        if not self._use_all_databases:
            # Only populate if we have a controller and combo box exists
            if self._stats_controller and hasattr(self, 'player_combo') and self.player_combo:
                self._populate_player_dropdown()
            # If a player was selected, recalculate (might be in different database now)
            if self._current_player:
                self._schedule_stats_recalculation()
        # If using all databases, the dropdown should already be up to date
        # but we can refresh it to ensure it includes the new active database
    
    def _create_analysis_coverage_banner(self, analyzed_count: int, total_count: int,
                                        text_color: QColor, label_font: QFont,
                                        bg_color: QColor, border_color: QColor) -> QWidget:
        """Create banner showing analysis coverage."""
        # Get config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        coverage_config = player_stats_config.get('analysis_coverage', {})
        colors_config = coverage_config.get('colors', {})
        thresholds = coverage_config.get('thresholds', {})
        
        # Calculate percentage
        percentage = (analyzed_count / total_count * 100) if total_count > 0 else 0
        
        # Determine color based on coverage
        if percentage >= thresholds.get('good_coverage_percent', 80):
            indicator_color = QColor(*colors_config.get('good_coverage', [100, 200, 100]))
        elif percentage >= thresholds.get('moderate_coverage_percent', 50):
            indicator_color = QColor(*colors_config.get('moderate_coverage', [255, 200, 100]))
        else:
            indicator_color = QColor(*colors_config.get('low_coverage', [255, 150, 150]))
        
        # Create banner frame
        banner = QFrame()
        banner_margins = coverage_config.get('banner_margins', [10, 8, 10, 8])
        banner_spacing = coverage_config.get('banner_spacing', 5)
        banner_bg = QColor(*coverage_config.get('banner_background_color', [45, 45, 50]))
        banner_border = QColor(*coverage_config.get('banner_border_color', [60, 60, 65]))
        banner_text_color = QColor(*coverage_config.get('banner_text_color', [200, 200, 200]))
        banner_font_size = coverage_config.get('banner_font_size', 10)
        
        banner.setStyleSheet(f"""
            QFrame {{
                background-color: rgb({banner_bg.red()}, {banner_bg.green()}, {banner_bg.blue()});
                border: 1px solid rgb({banner_border.red()}, {banner_border.green()}, {banner_border.blue()});
                border-radius: 5px;
            }}
        """)
        
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(banner_margins[0], banner_margins[1], banner_margins[2], banner_margins[3])
        layout.setSpacing(banner_spacing)
        
        # Create small colored indicator widget
        indicator_size = coverage_config.get('indicator_size', [12, 12])
        indicator = QWidget()
        indicator.setFixedSize(indicator_size[0], indicator_size[1])
        indicator.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({indicator_color.red()}, {indicator_color.green()}, {indicator_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
            }}
        """)
        layout.addWidget(indicator)
        
        # Create text label
        text = QLabel(f"Statistics based on {analyzed_count} analyzed games ({analyzed_count}/{total_count} total)")
        text.setFont(label_font)
        text.setStyleSheet(f"""
            QLabel {{
                color: rgb({banner_text_color.red()}, {banner_text_color.green()}, {banner_text_color.blue()});
                font-size: {banner_font_size}pt;
            }}
        """)
        layout.addWidget(text)
        layout.addStretch()
        
        return banner
    
    def _create_overview_widget(self, stats: "AggregatedPlayerStats",
                               text_color: QColor, label_font: QFont, value_font: QFont,
                               bg_color: QColor, border_color: QColor,
                               widgets_config: Dict[str, Any]) -> QWidget:
        """Create overview statistics widget."""
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Statistics grid
        # Use 3 columns: labels (left), stretch (flexible space), values (right)
        grid = QGridLayout()
        grid.setSpacing(grid_spacing)
        # Make columns responsive to width - label column takes minimum needed, stretch column is flexible, value column fixed
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        grid_config = player_stats_config.get('grid', {})
        label_col_min_width = grid_config.get('label_column_minimum_width', 150)
        value_col_min_width = grid_config.get('value_column_minimum_width', 100)
        grid.setColumnStretch(0, 0)  # Label column - no stretch, use minimum width
        grid.setColumnStretch(1, 1)  # Stretch column - flexible space between labels and values (will shrink first)
        grid.setColumnStretch(2, 0)  # Value column - no stretch, use minimum width
        # Use preferred width hints instead of minimum widths to allow shrinking when needed
        # The stretch column will collapse first when width is reduced
        grid.setColumnMinimumWidth(0, 0)  # Allow labels to shrink if needed
        grid.setColumnMinimumWidth(1, 0)  # No minimum for stretch column - this will collapse first
        grid.setColumnMinimumWidth(2, 0)  # Allow values to shrink if needed
        
        # Allow widget to expand horizontally to use available space
        # This ensures KPIs can move to the left when width is reduced
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # Set minimum width to 0 to allow proper shrinking
        widget.setMinimumWidth(0)
        
        # Total Games
        self._add_stat_row(grid, 0, "Total Games:", str(stats.total_games), label_font, value_font, text_color)
        # Win Rate
        self._add_stat_row(grid, 1, "Win Rate:", f"{stats.win_rate:.1f}%", label_font, value_font, text_color)
        # Wins/Draws/Losses
        self._add_stat_row(grid, 2, "Record:", f"{stats.wins}-{stats.draws}-{stats.losses}", label_font, value_font, text_color)
        # Average Accuracy
        accuracy = stats.player_stats.accuracy if stats.player_stats.accuracy is not None else 0.0
        self._add_stat_row(grid, 3, "Average Accuracy:", f"{accuracy:.1f}%", label_font, value_font, text_color)
        # Estimated Elo
        est_elo = stats.player_stats.estimated_elo if stats.player_stats.estimated_elo is not None else 0
        self._add_stat_row(grid, 4, "Estimated Elo:", str(est_elo), label_font, value_font, text_color)
        # Average CPL
        avg_cpl = stats.player_stats.average_cpl if stats.player_stats.average_cpl is not None else 0.0
        self._add_stat_row(grid, 5, "Average CPL:", f"{avg_cpl:.1f}", label_font, value_font, text_color)
        # Top 3 Move %
        top3_move_pct = stats.player_stats.top3_move_percentage if stats.player_stats.top3_move_percentage is not None else 0.0
        self._add_stat_row(grid, 6, "Top 3 Move %:", f"{top3_move_pct:.1f}%", label_font, value_font, text_color)
        
        # The grid itself has a stretch column between labels and values for flexible spacing
        # The grid widget will expand to fill available space, and the stretch column will shrink when width is reduced
        # Create a widget to hold the grid that can expand
        grid_widget = QWidget()
        # Remove any default styling that might add borders
        grid_widget.setStyleSheet("QWidget { border: none; background: transparent; }")
        grid_widget.setLayout(grid)
        grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # Set minimum width to 0 so it can shrink when needed
        grid_widget.setMinimumWidth(0)
        
        layout.addWidget(grid_widget)  # Grid widget expands to fill available space
        layout.addStretch()
        
        return widget
    
    def _create_move_accuracy_widget(self, stats: "AggregatedPlayerStats",
                                    text_color: QColor, label_font: QFont, value_font: QFont,
                                    bg_color: QColor, border_color: QColor,
                                    widgets_config: Dict[str, Any]) -> QWidget:
        """Create move accuracy widget with pie chart and percentages for all move classifications."""
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        player_stats = stats.player_stats
        total_moves = player_stats.total_moves if player_stats.total_moves else 0
        
        if total_moves > 0:
            # Create horizontal layout for pie chart and stats grid
            content_layout = QHBoxLayout()
            content_layout.setSpacing(section_spacing)
            content_layout.setContentsMargins(0, 0, 0, 0)  # No margins to allow full expansion
            
            # Pie chart on the left
            pie_data = {
                'Book Move': player_stats.book_moves if player_stats.book_moves else 0,
                'Brilliant': player_stats.brilliant_moves if player_stats.brilliant_moves else 0,
                'Best Move': player_stats.best_moves if player_stats.best_moves else 0,
                'Good Move': player_stats.good_moves if player_stats.good_moves else 0,
                'Inaccuracy': player_stats.inaccuracies if player_stats.inaccuracies else 0,
                'Mistake': player_stats.mistakes if player_stats.mistakes else 0,
                'Miss': player_stats.misses if player_stats.misses else 0,
                'Blunder': player_stats.blunders if player_stats.blunders else 0,
            }
            
            pie_chart = PieChartWidget(self.config)
            pie_chart.set_data(pie_data)
            # Allow pie chart to expand when legend is hidden
            pie_chart.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            # Store reference for responsive width handling
            self._pie_chart_widget = pie_chart
            content_layout.addWidget(pie_chart, 1)  # Give it stretch factor
            
            # Statistics grid on the right
            grid = QGridLayout()
            grid.setSpacing(grid_spacing)
            ui_config = self.config.get('ui', {})
            panel_config = ui_config.get('panels', {}).get('detail', {})
            player_stats_config = panel_config.get('player_stats', {})
            summary_config = panel_config.get('summary', {})
            grid_config = player_stats_config.get('grid', {})
            
            # Get colors from summary config (same as game summary view)
            colors_config = summary_config.get('colors', {})
            
            # Get color indicator size from summary widgets config (same as game summary view)
            summary_widgets_config = summary_config.get('widgets', {})
            color_indicator_size = summary_widgets_config.get('color_indicator_size', [12, 12])
            
            value_col_min_width = grid_config.get('value_column_minimum_width', 100)
            grid.setColumnStretch(0, 0)  # Color indicator + Label column (combined)
            grid.setColumnStretch(1, 0)  # Value column
            grid.setColumnMinimumWidth(0, 0)  # No minimum - let content determine width
            grid.setColumnMinimumWidth(1, value_col_min_width)
            
            row = 0
            # Book Moves
            book_pct = (player_stats.book_moves / total_moves * 100) if player_stats.book_moves else 0.0
            book_color = colors_config.get('book_move', [150, 150, 150])
            self._add_stat_row_with_color(grid, row, "Book Move:", f"{book_pct:.1f}%", book_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Brilliant Moves
            brilliant_pct = (player_stats.brilliant_moves / total_moves * 100) if player_stats.brilliant_moves else 0.0
            brilliant_color = colors_config.get('brilliant', [255, 215, 0])
            self._add_stat_row_with_color(grid, row, "Brilliant:", f"{brilliant_pct:.1f}%", brilliant_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Best Moves
            best_pct = (player_stats.best_moves / total_moves * 100) if player_stats.best_moves else 0.0
            best_color = colors_config.get('best_move', [100, 255, 100])
            self._add_stat_row_with_color(grid, row, "Best Move:", f"{best_pct:.1f}%", best_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Good Moves
            good_pct = (player_stats.good_moves / total_moves * 100) if player_stats.good_moves else 0.0
            good_color = colors_config.get('good_move', [150, 255, 150])
            self._add_stat_row_with_color(grid, row, "Good Move:", f"{good_pct:.1f}%", good_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Inaccuracies
            inaccuracy_pct = (player_stats.inaccuracies / total_moves * 100) if player_stats.inaccuracies else 0.0
            inaccuracy_color = colors_config.get('inaccuracy', [255, 255, 100])
            self._add_stat_row_with_color(grid, row, "Inaccuracy:", f"{inaccuracy_pct:.1f}%", inaccuracy_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Mistakes
            mistake_pct = (player_stats.mistakes / total_moves * 100) if player_stats.mistakes else 0.0
            mistake_color = colors_config.get('mistake', [255, 200, 100])
            self._add_stat_row_with_color(grid, row, "Mistake:", f"{mistake_pct:.1f}%", mistake_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Misses
            miss_pct = (player_stats.misses / total_moves * 100) if player_stats.misses else 0.0
            miss_color = colors_config.get('miss', [200, 100, 255])
            self._add_stat_row_with_color(grid, row, "Miss:", f"{miss_pct:.1f}%", miss_color, color_indicator_size, border_color, label_font, value_font, text_color)
            row += 1
            
            # Blunders
            blunder_pct = (player_stats.blunders / total_moves * 100) if player_stats.blunders else 0.0
            blunder_color = colors_config.get('blunder', [255, 100, 100])
            self._add_stat_row_with_color(grid, row, "Blunder:", f"{blunder_pct:.1f}%", blunder_color, color_indicator_size, border_color, label_font, value_font, text_color)
            
            grid_widget = QWidget()
            grid_widget.setLayout(grid)
            # Set size policy to prevent it from expanding
            grid_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            # Set minimum width to 0 so it can collapse completely
            grid_widget.setMinimumWidth(0)
            
            # Store reference for responsive width handling
            self._move_classification_legend_widget = grid_widget
            
            # Setup opacity effect and animation for responsive width
            self._move_classification_opacity_effect = QGraphicsOpacityEffect(grid_widget)
            grid_widget.setGraphicsEffect(self._move_classification_opacity_effect)
            
            # Setup animation
            self._setup_move_classification_animation()
            
            content_layout.addWidget(grid_widget, 0)  # No stretch - will be hidden when narrow
            
            layout.addLayout(content_layout)
            
            # Update visibility based on initial width (defer to allow layout to complete)
            QTimer.singleShot(0, self._update_move_classification_visibility)
        
        layout.addStretch()
        
        # Set size policy to prevent excessive width usage
        widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        
        return widget
    
    def _create_phase_performance_widget(self, stats: "AggregatedPlayerStats",
                                        text_color: QColor, label_font: QFont, value_font: QFont,
                                        bg_color: QColor, border_color: QColor,
                                        widgets_config: Dict[str, Any]) -> QWidget:
        """Create phase performance widget with bar chart and accuracy values."""
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Set size policy to allow shrinking
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        widget.setMinimumWidth(0)
        
        # Create horizontal layout for bar chart and stats grid
        content_layout = QHBoxLayout()
        content_layout.setSpacing(section_spacing)
        
        # Bar chart on the left
        phase_bar_chart = PhaseBarChartWidget(self.config, text_color, label_font, value_font)
        phase_data = {
            'Opening': stats.opening_stats.accuracy,
            'Middlegame': stats.middlegame_stats.accuracy,
            'Endgame': stats.endgame_stats.accuracy,
        }
        phase_bar_chart.set_data(phase_data)
        phase_bar_chart.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content_layout.addWidget(phase_bar_chart, 1)  # Stretch factor for chart
        
        # Phase statistics grid on the right
        grid = QGridLayout()
        grid.setSpacing(grid_spacing)
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        grid_config = player_stats_config.get('grid', {})
        label_col_min_width = grid_config.get('label_column_minimum_width', 150)
        value_col_min_width = grid_config.get('value_column_minimum_width', 100)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        # Allow columns to shrink - remove fixed minimum widths
        grid.setColumnMinimumWidth(0, 0)
        grid.setColumnMinimumWidth(1, 0)
        
        # Header row
        header_font = QFont(label_font)
        header_font.setBold(True)
        self._add_stat_row(grid, 0, "Phase", "Avg CPL", header_font, header_font, text_color)
        self._add_stat_row(grid, 1, "Opening", f"{stats.opening_stats.average_cpl:.1f}", label_font, value_font, text_color)
        self._add_stat_row(grid, 2, "Middlegame", f"{stats.middlegame_stats.average_cpl:.1f}", label_font, value_font, text_color)
        self._add_stat_row(grid, 3, "Endgame", f"{stats.endgame_stats.average_cpl:.1f}", label_font, value_font, text_color)
        
        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        grid_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        grid_widget.setMinimumWidth(0)
        content_layout.addWidget(grid_widget)
        
        layout.addLayout(content_layout)
        layout.addStretch()
        
        return widget
    
    def _create_openings_widget(self, stats: "AggregatedPlayerStats",
                               text_color: QColor, label_font: QFont, value_font: QFont,
                               bg_color: QColor, border_color: QColor,
                               widgets_config: Dict[str, Any]) -> QWidget:
        """Create openings widget showing most played, worst, and best accuracy openings."""
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Set size policy to allow shrinking when width is reduced
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        widget.setMinimumWidth(0)  # Allow widget to shrink
        
        # Store reference for responsive width handling
        self._openings_widget = widget
        self._openings_items = []
        
        # Get grid config for column widths
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        grid_config = player_stats_config.get('grid', {})
        label_col_min_width = grid_config.get('label_column_minimum_width', 150)
        value_col_min_width = grid_config.get('value_column_minimum_width', 100)
        
        # Most Played Openings
        if stats.top_openings:
            grid_most = QGridLayout()
            grid_most.setSpacing(grid_spacing * 2)  # Increase spacing between label and value
            # 2-column layout: labels (left), values (right, expanding)
            grid_most.setColumnStretch(0, 0)  # Label column - no stretch
            grid_most.setColumnStretch(1, 1)  # Value column - expanding to fill space
            grid_most.setColumnMinimumWidth(0, label_col_min_width)  # Set minimum width for label column
            grid_most.setColumnMinimumWidth(1, 0)  # Allow value column to shrink
            
            openings_lines = []
            openings_lines_eco_only = []
            for eco, opening_name, count in stats.top_openings:
                if opening_name and eco != "Unknown":
                    openings_lines.append(f"{eco} ({opening_name}):\n({count} games)")
                    openings_lines_eco_only.append(f"{eco}: ({count} games)")
                elif eco != "Unknown":
                    openings_lines.append(f"{eco}:\n({count} games)")
                    openings_lines_eco_only.append(f"{eco}: ({count} games)")
                else:
                    openings_lines.append(f"Unknown:\n({count} games)")
                    openings_lines_eco_only.append(f"?: ({count} games)")
            
            if openings_lines:
                # Add spacing between items for better readability
                openings_text = "\n\n".join(openings_lines)
                openings_text_eco_only = "\n\n".join(openings_lines_eco_only)
                label = QLabel("Most Played:")
                label.setFont(label_font)
                label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                label.setMinimumWidth(0)  # Allow label to shrink
                grid_most.addWidget(label, 0, 0)
                
                value = QLabel(openings_text)
                value.setFont(value_font)
                value.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)  # Left-aligned for better readability
                value.setWordWrap(True)  # Allow wrapping for graceful width reduction
                value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                value.setMinimumWidth(0)  # Allow value to shrink
                
                # Setup opacity effect for fading opening names
                opening_name_opacity = QGraphicsOpacityEffect(value)
                value.setGraphicsEffect(opening_name_opacity)
                opening_name_opacity.setOpacity(1.0)
                
                grid_most.addWidget(value, 0, 1)  # Column 1 for expanding values
                
                # Store for responsive handling
                self._openings_items.append({
                    'label': label,
                    'value': value,
                    'opacity_effect': opening_name_opacity,
                    'full_text': openings_text,
                    'eco_only_text': openings_text_eco_only
                })
            
            # Wrap grid in a widget to ensure it expands properly
            grid_widget_most = QWidget()
            grid_widget_most.setLayout(grid_most)
            grid_widget_most.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addWidget(grid_widget_most)
            layout.addSpacing(section_spacing)
        
        # Worst Accuracy Openings
        if stats.worst_accuracy_openings:
            grid_worst = QGridLayout()
            grid_worst.setSpacing(grid_spacing * 2)  # Increase spacing between label and value
            # 2-column layout: labels (left), values (right, expanding)
            grid_worst.setColumnStretch(0, 0)  # Label column - no stretch
            grid_worst.setColumnStretch(1, 1)  # Value column - expanding to fill space
            grid_worst.setColumnMinimumWidth(0, label_col_min_width)  # Set minimum width for label column
            grid_worst.setColumnMinimumWidth(1, 0)  # Allow value column to shrink
            
            worst_lines = []
            worst_lines_eco_only = []
            for eco, opening_name, avg_cpl, count in stats.worst_accuracy_openings:
                if opening_name and eco != "Unknown":
                    worst_lines.append(f"{eco} ({opening_name}):\n{avg_cpl:.1f} CPL ({count} games)")
                    worst_lines_eco_only.append(f"{eco}: {avg_cpl:.1f} CPL ({count} games)")
                elif eco != "Unknown":
                    worst_lines.append(f"{eco}: {avg_cpl:.1f} CPL ({count} games)")
                    worst_lines_eco_only.append(f"{eco}: {avg_cpl:.1f} CPL ({count} games)")
                else:
                    worst_lines.append(f"Unknown: {avg_cpl:.1f} CPL ({count} games)")
                    worst_lines_eco_only.append(f"?: {avg_cpl:.1f} CPL ({count} games)")
            
            if worst_lines:
                # Add spacing between items for better readability
                worst_text = "\n\n".join(worst_lines)
                worst_text_eco_only = "\n\n".join(worst_lines_eco_only)
                label = QLabel("Worst Accuracy:")
                label.setFont(label_font)
                label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                label.setMinimumWidth(0)  # Allow label to shrink
                grid_worst.addWidget(label, 0, 0)
                
                value = QLabel(worst_text)
                value.setFont(value_font)
                value.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)  # Left-aligned for better readability
                value.setWordWrap(True)  # Allow wrapping for graceful width reduction
                value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                value.setMinimumWidth(0)  # Allow value to shrink
                
                # Setup opacity effect for fading opening names
                opening_name_opacity = QGraphicsOpacityEffect(value)
                value.setGraphicsEffect(opening_name_opacity)
                opening_name_opacity.setOpacity(1.0)
                
                grid_worst.addWidget(value, 0, 1)  # Column 1 for expanding values
                
                # Store for responsive handling
                self._openings_items.append({
                    'label': label,
                    'value': value,
                    'opacity_effect': opening_name_opacity,
                    'full_text': worst_text,
                    'eco_only_text': worst_text_eco_only
                })
            
            # Wrap grid in a widget to ensure it expands properly
            grid_widget_worst = QWidget()
            grid_widget_worst.setLayout(grid_worst)
            grid_widget_worst.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addWidget(grid_widget_worst)
            layout.addSpacing(section_spacing)
        
        # Best Accuracy Openings
        if stats.best_accuracy_openings:
            grid_best = QGridLayout()
            grid_best.setSpacing(grid_spacing * 2)  # Increase spacing between label and value
            # 2-column layout: labels (left), values (right, expanding)
            grid_best.setColumnStretch(0, 0)  # Label column - no stretch
            grid_best.setColumnStretch(1, 1)  # Value column - expanding to fill space
            grid_best.setColumnMinimumWidth(0, label_col_min_width)  # Set minimum width for label column
            grid_best.setColumnMinimumWidth(1, 0)  # Allow value column to shrink
            
            best_lines = []
            best_lines_eco_only = []
            for eco, opening_name, avg_cpl, count in stats.best_accuracy_openings:
                if opening_name and eco != "Unknown":
                    best_lines.append(f"{eco} ({opening_name}):\n{avg_cpl:.1f} CPL ({count} games)")
                    best_lines_eco_only.append(f"{eco}: {avg_cpl:.1f} CPL ({count} games)")
                elif eco != "Unknown":
                    best_lines.append(f"{eco}: {avg_cpl:.1f} CPL ({count} games)")
                    best_lines_eco_only.append(f"{eco}: {avg_cpl:.1f} CPL ({count} games)")
                else:
                    best_lines.append(f"Unknown: {avg_cpl:.1f} CPL ({count} games)")
                    best_lines_eco_only.append(f"?: {avg_cpl:.1f} CPL ({count} games)")
            
            if best_lines:
                # Add spacing between items for better readability
                best_text = "\n\n".join(best_lines)
                best_text_eco_only = "\n\n".join(best_lines_eco_only)
                label = QLabel("Best Accuracy:")
                label.setFont(label_font)
                label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                label.setMinimumWidth(0)  # Allow label to shrink
                grid_best.addWidget(label, 0, 0)
                
                value = QLabel(best_text)
                value.setFont(value_font)
                value.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)  # Left-aligned for better readability
                value.setWordWrap(True)  # Allow wrapping for graceful width reduction
                value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                value.setMinimumWidth(0)  # Allow value to shrink
                
                # Setup opacity effect for fading opening names
                opening_name_opacity = QGraphicsOpacityEffect(value)
                value.setGraphicsEffect(opening_name_opacity)
                opening_name_opacity.setOpacity(1.0)
                
                grid_best.addWidget(value, 0, 1)  # Column 1 for expanding values
                
                # Store for responsive handling
                self._openings_items.append({
                    'label': label,
                    'value': value,
                    'opacity_effect': opening_name_opacity,
                    'full_text': best_text,
                    'eco_only_text': best_text_eco_only
                })
            
            # Wrap grid in a widget to ensure it expands properly
            grid_widget_best = QWidget()
            grid_widget_best.setLayout(grid_best)
            grid_widget_best.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addWidget(grid_widget_best)
        
        layout.addStretch()
        
        # Update visibility based on initial width
        QTimer.singleShot(0, self._update_openings_visibility)
        
        return widget
    
    def _create_error_patterns_widget(self, patterns: List["ErrorPattern"],
                                     text_color: QColor, label_font: QFont, value_font: QFont,
                                     bg_color: QColor, border_color: QColor,
                                     widgets_config: Dict[str, Any]) -> QWidget:
        """Create error patterns widget."""
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        # Set size policy to prevent expansion - use Minimum instead of Expanding
        widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        widget.setMinimumWidth(0)  # Allow widget to shrink
        widget.setMaximumWidth(16777215)  # Will be constrained by parent
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Store reference for responsive width handling
        self._error_patterns_widget = widget
        self._error_pattern_items = []
        
        # Add each pattern
        for pattern in patterns:
            pattern_data = self._create_error_pattern_item(
                pattern, text_color, label_font, value_font, bg_color, border_color, widgets_config
            )
            pattern_widget = pattern_data['item']
            layout.addWidget(pattern_widget)
            self._error_pattern_items.append(pattern_data)
        
        layout.addStretch()
        
        # Update visibility based on initial width
        QTimer.singleShot(0, self._update_error_patterns_visibility)
        
        return widget
    
    def _create_error_pattern_item(self, pattern: "ErrorPattern",
                                  text_color: QColor, label_font: QFont, value_font: QFont,
                                  bg_color: QColor, border_color: QColor,
                                  widgets_config: Dict[str, Any]) -> QWidget:
        """Create a single error pattern item."""
        # Get error patterns config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        error_patterns_config = player_stats_config.get('error_patterns', {})
        
        item = QFrame()
        item.setFrameShape(QFrame.Shape.NoFrame)
        item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        item.setMinimumWidth(0)  # Allow item to shrink
        # Set maximum width to prevent horizontal scrolling
        item.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX (will be constrained by parent)
        
        # Get spacing and margins from config
        item_spacing = error_patterns_config.get('item_spacing', 8)
        item_margins = error_patterns_config.get('item_margins', [8, 6, 8, 6])
        
        layout = QHBoxLayout(item)
        layout.setSpacing(item_spacing)
        layout.setContentsMargins(item_margins[0], item_margins[1], item_margins[2], item_margins[3])
        # Ensure layout doesn't add extra spacing that prevents shrinking
        layout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetNoConstraint)
        
        # Severity indicator (colored square)
        severity_indicator_config = error_patterns_config.get('severity_indicator', {})
        severity_colors_config = severity_indicator_config.get('colors', {})
        severity_colors = {
            "critical": severity_colors_config.get('critical', [255, 100, 100]),
            "high": severity_colors_config.get('high', [255, 150, 100]),
            "moderate": severity_colors_config.get('moderate', [255, 200, 100]),
            "low": severity_colors_config.get('low', [200, 200, 100])
        }
        severity_color = severity_colors.get(pattern.severity, severity_colors_config.get('default', [150, 150, 150]))
        indicator_size = severity_indicator_config.get('size', [12, 12])
        indicator_border_radius = severity_indicator_config.get('border_radius', 6)
        
        indicator = QWidget()
        indicator.setFixedSize(indicator_size[0], indicator_size[1])
        indicator.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({severity_color[0]}, {severity_color[1]}, {severity_color[2]});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {indicator_border_radius}px;
            }}
        """)
        layout.addWidget(indicator)
        
        # Pattern description - allow wrapping and shrinking
        desc_label = QLabel(pattern.description)
        desc_label.setFont(label_font)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
        desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        desc_label.setMinimumWidth(0)  # Allow description to shrink
        layout.addWidget(desc_label, 1)  # Give it stretch factor
        
        # Frequency/percentage - compact display
        freq_text = f"({pattern.frequency}, {pattern.percentage:.1f}%)"
        freq_label = QLabel(freq_text)
        freq_label.setFont(value_font)
        freq_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        freq_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        layout.addWidget(freq_label, 0)  # No stretch
        
        # View games button (if games available)
        view_button = None
        if pattern.related_games:
            view_button = QPushButton(f"View {len(pattern.related_games)} →")
            self._apply_button_styling(view_button)
            view_button.clicked.connect(lambda checked, p=pattern: self._on_view_pattern_games(p))
            view_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            layout.addWidget(view_button, 0)  # No stretch
        
        # Return item data for responsive handling
        return {
            'item': item,
            'button': view_button,
            'desc_label': desc_label,
            'freq_label': freq_label,
            'full_text': pattern.description
        }
    
    def _on_view_pattern_games(self, pattern: "ErrorPattern") -> None:
        """Handle click on 'View games' button for a pattern.
        
        Groups games by database, switches to the database with the most games,
        highlights all games in that database, and sorts them to the top.
        """
        if not pattern.related_games or not self._database_panel or not self._stats_controller:
            return
        
        # Group games by database: {database: [row_indices]}
        # Use controller method to find games (avoids direct model access)
        games_by_database: Dict[DatabaseModel, List[int]] = {}
        
        for game in pattern.related_games:
            result = self._stats_controller.find_game_in_databases(game, use_all_databases=True)
            if result:
                database, row_index = result
                if database not in games_by_database:
                    games_by_database[database] = []
                games_by_database[database].append(row_index)
        
        if not games_by_database:
            return
        
        # Find the database with the most games (or first one if tie)
        target_database = max(games_by_database.items(), key=lambda x: len(x[1]))[0]
        target_row_indices = games_by_database[target_database]
        
        # Highlight all games in the target database and sort them to the top
        self._database_panel.highlight_rows(target_database, target_row_indices)
    
    def _add_section_header(self, text: str, font: QFont, color: QColor) -> None:
        """Add a section header label."""
        header = QLabel(text)
        header.setFont(font)
        header.setStyleSheet(f"color: rgb({color.red()}, {color.green()}, {color.blue()}); border: none;")
        self.content_layout.addWidget(header)
    
    def _add_stat_row(self, grid: QGridLayout, row: int, label_text: str, value_text: str,
                     label_font: QFont, value_font: QFont, text_color: QColor) -> None:
        """Add a statistics row to a grid.
        
        Grid has 3 columns: 0=label (left), 1=stretch (flexible), 2=value (right)
        """
        label = QLabel(label_text)
        label.setFont(label_font)
        label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Set size policy to use preferred width but allow shrinking
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        label.setMinimumWidth(0)  # Allow label to shrink if needed
        grid.addWidget(label, row, 0)
        
        # Column 1 is the stretch column - no widget needed, it's handled by column stretch
        
        value = QLabel(value_text)
        value.setFont(value_font)
        value.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Set size policy to use preferred width but allow shrinking
        value.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        value.setMinimumWidth(0)  # Allow value to shrink if needed
        grid.addWidget(value, row, 2)  # Value in column 2
    
    def _add_stat_row_with_color(self, grid: QGridLayout, row: int, label_text: str, value_text: str,
                                 color: List[int], color_indicator_size: List[int], border_color: QColor,
                                 label_font: QFont, value_font: QFont, text_color: QColor) -> None:
        """Add a statistics row to a grid with a colored circle indicator."""
        # Create a horizontal layout for color indicator and label (close together)
        indicator_label_layout = QHBoxLayout()
        indicator_label_layout.setContentsMargins(0, 0, 0, 0)
        indicator_label_layout.setSpacing(5)  # Small spacing between indicator and label
        
        # Color indicator widget - use QLabel to avoid default widget borders
        color_widget = QLabel()
        color_widget.setFixedSize(color_indicator_size[0], color_indicator_size[1])
        # Ensure color is a valid tuple/list with 3 elements
        color_r = color[0] if isinstance(color, (list, tuple)) and len(color) >= 1 else 150
        color_g = color[1] if isinstance(color, (list, tuple)) and len(color) >= 2 else 150
        color_b = color[2] if isinstance(color, (list, tuple)) and len(color) >= 3 else 150
        color_widget.setStyleSheet(f"""
            QLabel {{
                background-color: rgb({color_r}, {color_g}, {color_b});
                border: none;
                border-radius: {color_indicator_size[0] // 2}px;
            }}
        """)
        color_widget.setText("")  # Empty text, just background color
        indicator_label_layout.addWidget(color_widget)
        
        # Label
        label = QLabel(label_text)
        label.setFont(label_font)
        label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicator_label_layout.addWidget(label)
        indicator_label_layout.addStretch()  # Push content to the left
        
        # Create a widget to hold the indicator and label layout
        indicator_label_widget = QWidget()
        indicator_label_widget.setLayout(indicator_label_layout)
        # Ensure parent widget has no border that might show through
        indicator_label_widget.setStyleSheet("QWidget { border: none; background: transparent; }")
        grid.addWidget(indicator_label_widget, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Value
        value = QLabel(value_text)
        value.setFont(value_font)
        value.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(value, row, 1)
    
    def _setup_move_classification_animation(self) -> None:
        """Setup animation for move classification legend fade in/out and width change."""
        if not self._move_classification_legend_widget or not self._move_classification_opacity_effect:
            return
        
        # Check if widget is still valid (not deleted)
        try:
            if not hasattr(self._move_classification_legend_widget, 'parent'):
                self._move_classification_legend_widget = None
                return
        except RuntimeError:
            # Widget was deleted
            self._move_classification_legend_widget = None
            return
        
        # Opacity animation
        opacity_animation = QPropertyAnimation(self._move_classification_opacity_effect, b"opacity", self)
        opacity_animation.setDuration(self.animation_duration)
        opacity_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Width animation (to allow pie chart to expand) - animate both min and max width
        self._move_classification_width_animation = QPropertyAnimation(self._move_classification_legend_widget, b"maximumWidth", self)
        self._move_classification_width_animation.setDuration(self.animation_duration)
        self._move_classification_width_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Also animate minimum width to ensure complete collapse
        self._move_classification_min_width_animation = QPropertyAnimation(self._move_classification_legend_widget, b"minimumWidth", self)
        self._move_classification_min_width_animation.setDuration(self.animation_duration)
        self._move_classification_min_width_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Store full width for restoration
        if self._move_classification_full_width <= 0:
            self._move_classification_full_width = max(0, self._move_classification_legend_widget.sizeHint().width())
        
        self._move_classification_animation = QParallelAnimationGroup(self)
        self._move_classification_animation.addAnimation(opacity_animation)
        self._move_classification_animation.addAnimation(self._move_classification_width_animation)
        self._move_classification_animation.addAnimation(self._move_classification_min_width_animation)
        self._move_classification_animation.finished.connect(self._on_move_classification_animation_finished)
    
    def _update_move_classification_visibility(self) -> None:
        """Update visibility of move classification legend based on available width."""
        if not self._move_classification_legend_widget or not hasattr(self, 'scroll_area'):
            return
        
        # Get current width of the scroll area viewport (actual visible width)
        available_width = self.scroll_area.viewport().width()
        
        # If widget hasn't been laid out yet (width is 0), skip check
        if available_width == 0:
            return
        
        # Estimate minimum width needed for legend
        # Pie chart needs ~200px, legend needs ~250px, spacing ~20px
        # Total: ~470px, use threshold from config
        should_show = available_width >= self.move_classification_collapse_threshold
        
        # Get current state
        animation_running = False
        if self._move_classification_animation:
            animation_running = self._move_classification_animation.state() == QAbstractAnimation.State.Running
        
        is_visible = self._move_classification_visible
        
        # Only update if state changed and animation is not running
        if should_show != is_visible and not animation_running:
            self._set_move_classification_visible(should_show)
    
    def _set_move_classification_visible(self, visible: bool) -> None:
        """Set move classification legend visibility with animation."""
        if not self._move_classification_legend_widget or not self._move_classification_opacity_effect:
            return
        
        # Check if widget is still valid (not deleted)
        try:
            if not hasattr(self._move_classification_legend_widget, 'parent'):
                self._move_classification_legend_widget = None
                return
        except RuntimeError:
            # Widget was deleted
            self._move_classification_legend_widget = None
            return
        
        if not self._move_classification_animation or not self._move_classification_width_animation:
            # No animation - just set visibility and width
            try:
                self._move_classification_legend_widget.setVisible(visible)
                if visible:
                    self._move_classification_legend_widget.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                else:
                    self._move_classification_legend_widget.setMaximumWidth(0)
                self._move_classification_visible = visible
            except RuntimeError:
                # Widget was deleted
                self._move_classification_legend_widget = None
            return
        
        if self._move_classification_visible == visible and not self._move_classification_visibility_pending:
            return
        
        self._move_classification_visibility_pending = True
        
        self._move_classification_animation.stop()
        
        try:
            if visible:
                self._move_classification_legend_widget.setVisible(True)
                # Restore full width
                if self._move_classification_full_width <= 0:
                    self._move_classification_full_width = max(0, self._move_classification_legend_widget.sizeHint().width())
            
            # Animate opacity
            current_opacity = self._move_classification_opacity_effect.opacity()
            self._move_classification_animation.animationAt(0).setStartValue(current_opacity)
            self._move_classification_animation.animationAt(0).setEndValue(1.0 if visible else 0.0)
            
            # Animate maximum width
            current_max_width = self._move_classification_legend_widget.maximumWidth()
            end_max_width = self._move_classification_full_width if visible else 0
            if end_max_width <= 0 and visible:
                end_max_width = max(0, self._move_classification_legend_widget.sizeHint().width())
        except RuntimeError:
            # Widget was deleted during operation
            self._move_classification_legend_widget = None
            return
        
        self._move_classification_width_animation.setStartValue(max(0, current_max_width))
        self._move_classification_width_animation.setEndValue(max(0, end_max_width))
        
        # Animate minimum width (to ensure complete collapse)
        current_min_width = self._move_classification_legend_widget.minimumWidth()
        end_min_width = 0 if not visible else self._move_classification_legend_widget.sizeHint().width()
        
        self._move_classification_min_width_animation.setStartValue(current_min_width)
        self._move_classification_min_width_animation.setEndValue(end_min_width)
        
        self._move_classification_animation.start()
    
    def _on_move_classification_animation_finished(self) -> None:
        """Handle move classification animation finished."""
        # Check if widgets are still valid before accessing
        if not self._move_classification_legend_widget:
            return
        try:
            if not hasattr(self._move_classification_legend_widget, 'parent'):
                self._move_classification_legend_widget = None
                return
        except RuntimeError:
            self._move_classification_legend_widget = None
            return
        
        self._move_classification_visible = not (self._move_classification_opacity_effect.opacity() < 0.5)
        self._move_classification_visibility_pending = False
        
        try:
            if not self._move_classification_visible:
                self._move_classification_legend_widget.setVisible(False)
                self._move_classification_legend_widget.setMaximumWidth(0)
                self._move_classification_legend_widget.setMinimumWidth(0)
            else:
                # Restore widths to allow natural sizing
                self._move_classification_legend_widget.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                # Let minimum width be determined by content
            
            # Force layout update to redistribute space
            if self._move_accuracy_widget:
                try:
                    # Get the content layout (parent of pie chart and legend)
                    parent = self._move_classification_legend_widget.parent()
                    if parent:
                        layout = parent.layout()
                        if layout:
                            # Invalidate the layout to force recalculation
                            layout.invalidate()
                            parent.updateGeometry()
                            parent.update()
                            # Also update the move accuracy widget
                            if hasattr(self._move_accuracy_widget, 'updateGeometry'):
                                self._move_accuracy_widget.updateGeometry()
                                self._move_accuracy_widget.update()
                            # Force a layout recalculation
                            QApplication.processEvents()
                except RuntimeError:
                    # Widgets were deleted
                    self._move_accuracy_widget = None
                    self._move_classification_legend_widget = None
        except RuntimeError:
            # Widget was deleted during operation
            self._move_classification_legend_widget = None
    
    def _update_error_patterns_visibility(self) -> None:
        """Update error patterns visibility and text truncation based on available width."""
        if not self._error_patterns_widget or not hasattr(self, 'scroll_area'):
            return
        
        # Check if widget is still valid (not deleted)
        try:
            if not hasattr(self._error_patterns_widget, 'parent'):
                self._error_patterns_widget = None
                return
        except RuntimeError:
            # Widget was deleted
            self._error_patterns_widget = None
            return
        
        # Get current width of the scroll area viewport
        available_width = self.scroll_area.viewport().width()
        
        # If widget hasn't been laid out yet (width is 0), skip check
        if available_width == 0:
            return
        
        # Determine if we should show full content or compact
        should_show_full = available_width >= self.error_patterns_collapse_threshold
        
        # Update each error pattern item
        for pattern_data in self._error_pattern_items:
            button = pattern_data.get('button')
            desc_label = pattern_data.get('desc_label')
            freq_label = pattern_data.get('freq_label')
            full_text = pattern_data.get('full_text', '')
            
            if not desc_label:
                continue
            
            # Update button visibility with fade
            if button:
                if should_show_full:
                    # Show button
                    button.setVisible(True)
                    button.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                    if hasattr(button, 'graphicsEffect') and button.graphicsEffect():
                        button.graphicsEffect().setOpacity(1.0)
                else:
                    # Fade out and hide button
                    if not hasattr(button, 'graphicsEffect') or not button.graphicsEffect():
                        opacity_effect = QGraphicsOpacityEffect(button)
                        button.setGraphicsEffect(opacity_effect)
                    button.graphicsEffect().setOpacity(0.0)
                    button.setMaximumWidth(0)
                    button.setVisible(False)
            
            # Hide frequency label when width is reduced (more aggressive shrinking)
            if freq_label:
                if should_show_full:
                    freq_label.setVisible(True)
                    freq_label.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                else:
                    freq_label.setVisible(False)
                    freq_label.setMaximumWidth(0)
            
            # Update description text - truncate if needed
            item = pattern_data.get('item')
            if should_show_full:
                # Show full text
                desc_label.setText(full_text)
                desc_label.setWordWrap(True)  # Allow wrapping when there's space
                desc_label.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX - remove width constraint
                desc_label.setMinimumWidth(0)  # Allow to shrink
                desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                # Reset item width constraint and size policy
                if item:
                    item.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                    item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            else:
                # Truncate text with ellipsis - be more aggressive
                # Estimate available width: total width - margins - indicator - spacing
                # Frequency label is hidden, so don't account for it
                # Button is also hidden
                # Get config values
                ui_config = self.config.get('ui', {})
                panel_config = ui_config.get('panels', {}).get('detail', {})
                player_stats_config = panel_config.get('player_stats', {})
                error_patterns_config = player_stats_config.get('error_patterns', {})
                item_margins_config = error_patterns_config.get('item_margins', [8, 6, 8, 6])
                item_margins = item_margins_config[0] + item_margins_config[2]  # Left + right margins
                severity_indicator_config = error_patterns_config.get('severity_indicator', {})
                indicator_size = severity_indicator_config.get('size', [12, 12])
                indicator_width = indicator_size[0]
                spacing = error_patterns_config.get('item_spacing', 8)
                truncation_config = error_patterns_config.get('truncation', {})
                min_text_width = truncation_config.get('min_text_width', 50)
                # More aggressive: use more of the available width for text
                estimated_available = max(min_text_width, available_width - item_margins - indicator_width - spacing)
                font_metrics = desc_label.fontMetrics()
                elided_text = font_metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, estimated_available)
                desc_label.setText(elided_text)
                desc_label.setWordWrap(False)  # Disable wrapping when truncated
                # Force the label to use the calculated width to prevent unused space
                desc_label.setMaximumWidth(estimated_available)
                desc_label.setMinimumWidth(0)  # Allow to shrink further if needed
                # Change size policy to Minimum to prevent expansion
                desc_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
                # Also ensure the item itself doesn't expand beyond available width
                if item:
                    item.setMaximumWidth(available_width)
                    # Change item size policy to prevent expansion
                    item.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
    
    def _update_openings_visibility(self) -> None:
        """Update openings text based on available width - switch to ECO-only when narrow."""
        if not self._openings_widget or not hasattr(self, 'scroll_area'):
            return
        
        # Check if widget is still valid (not deleted)
        try:
            if not hasattr(self._openings_widget, 'parent'):
                self._openings_widget = None
                return
        except RuntimeError:
            # Widget was deleted
            self._openings_widget = None
            return
        
        # Get current width of the scroll area viewport
        available_width = self.scroll_area.viewport().width()
        
        # If widget hasn't been laid out yet (width is 0), skip check
        if available_width == 0:
            return
        
        # Determine if we should show full content or compact
        # With line breaks in full text, we can use a slightly lower threshold
        should_show_full = available_width >= self.openings_collapse_threshold
        
        # Update each openings item
        for item_data in self._openings_items:
            value_label = item_data.get('value')
            opacity_effect = item_data.get('opacity_effect')
            full_text = item_data.get('full_text', '')
            eco_only_text = item_data.get('eco_only_text', '')
            
            if not value_label:
                continue
            
            # Update text and width constraints
            if should_show_full:
                # Show full text with opening names (now with line breaks for better wrapping)
                value_label.setText(full_text)
                # Calculate reasonable max width based on available space
                # Leave room for label column (~120px) and margins (~40px)
                # Allow natural wrapping with line breaks - use expanding policy
                max_value_width = max(150, available_width - 160)
                value_label.setMaximumWidth(max_value_width)
                if opacity_effect:
                    # Animate opacity to 1.0 (fully visible)
                    opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
                    opacity_anim.setDuration(self.animation_duration)
                    opacity_anim.setStartValue(opacity_effect.opacity())
                    opacity_anim.setEndValue(1.0)
                    opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    opacity_anim.start()
            else:
                # Show ECO-only text (single line, more compact)
                value_label.setText(eco_only_text if eco_only_text else full_text)
                # Set maximum width to prevent overflow
                # Leave room for label column (~120px) and margins (~40px)
                estimated_available = max(100, available_width - 160)
                value_label.setMaximumWidth(estimated_available)
                if opacity_effect:
                    # Keep opacity at 1.0 for ECO-only text
                    opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
                    opacity_anim.setDuration(self.animation_duration)
                    opacity_anim.setStartValue(opacity_effect.opacity())
                    opacity_anim.setEndValue(1.0)
                    opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    opacity_anim.start()
    
    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        """Event filter to monitor width changes for responsive layout."""
        if obj == self.scroll_area and event.type() == QEvent.Type.Resize:
            # Defer update until after layout has been processed
            QTimer.singleShot(0, self._update_move_classification_visibility)
            QTimer.singleShot(0, self._update_error_patterns_visibility)
            QTimer.singleShot(0, self._update_openings_visibility)
        return super().eventFilter(obj, event)


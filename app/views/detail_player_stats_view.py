"""Player Statistics view for detail panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QGridLayout, QSizePolicy, QComboBox, QPushButton, QApplication,
    QGraphicsOpacityEffect, QMenu
)
from PyQt6.QtCore import Qt, QRectF, QEvent, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QAbstractAnimation, QTimer, QSize, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QFontMetrics, QContextMenuEvent
from app.views.detail_summary_view import PieChartWidget
from typing import Callable, Dict, Any, Optional, List, Tuple, TYPE_CHECKING
from app.models.database_model import DatabaseModel

from app.models.game_model import GameModel
from app.controllers.game_controller import GameController
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.services.logging_service import LoggingService

if TYPE_CHECKING:
    from app.controllers.player_stats_controller import PlayerStatsController
    from app.controllers.database_controller import DatabaseController
    from app.services.player_stats_service import AggregatedPlayerStats
    from app.services.error_pattern_service import ErrorPattern




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


class AccuracyDistributionWidget(QWidget):
    """Widget for displaying a simple histogram of per-game accuracy values."""

    def __init__(
        self,
        config: Dict[str, Any],
        accuracy_values: List[float],
        text_color: QColor,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._accuracy_values: List[float] = accuracy_values or []

        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        colors_config = player_stats_config.get('colors', {})
        dist_config = player_stats_config.get('accuracy_distribution', {})

        self._bar_color = QColor(*dist_config.get('bar_color', colors_config.get('phase_opening_color', [100, 150, 255])))
        self._grid_line_color = QColor(*dist_config.get('grid_line_color', [70, 70, 75]))
        self._axis_color = QColor(*dist_config.get('axis_color', [140, 140, 145]))
        self._text_color = text_color

        self._bin_size = float(dist_config.get('bin_size', 5.0))
        if self._bin_size <= 0:
            self._bin_size = 5.0
        self._height = int(dist_config.get('height', 90))
        self._margins = dist_config.get('margins', [10, 10, 10, 10])

        label_font_size = scale_font_size(dist_config.get('label_font_size', 9))
        fonts_config = player_stats_config.get('fonts', {})
        label_font_family = resolve_font_family(fonts_config.get('label_font_family', 'Helvetica Neue'))
        self._label_font = QFont(label_font_family, int(label_font_size))

        self.setMinimumHeight(self._height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Hover state: store bin geometry and ranges for tooltips
        # Each entry: (x_left, x_right, start_acc, end_acc, count)
        self._bin_info: List[Tuple[float, float, float, float, int]] = []
        self.setMouseTracking(True)

    def set_accuracy_values(self, values: List[float]) -> None:
        self._accuracy_values = values or []
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(200, self._height)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, self._height)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        left = self._margins[0]
        top = self._margins[1]
        right = rect.width() - self._margins[2]
        bottom = rect.height() - self._margins[3]
        if right <= left or bottom <= top:
            return

        # Reserve space for axis labels
        painter.setFont(self._label_font)
        fm = QFontMetrics(self._label_font)
        label_height = fm.height() + 4

        # Reserve horizontal space on the left for y-axis labels
        # (labels for game counts at 0, mid, max)
        # Use max label width based on a rough upper bound of counts
        max_label_text = "999"  # enough for typical game counts
        y_label_width = fm.horizontalAdvance(max_label_text) + 4

        plot_left = left + y_label_width
        plot_top = top
        plot_bottom = bottom - label_height
        if plot_bottom <= plot_top:
            plot_bottom = top + 10
        plot_height = plot_bottom - plot_top
        plot_width = right - plot_left

        # Draw background grid lines
        painter.setPen(QPen(self._grid_line_color, 1, Qt.PenStyle.SolidLine))
        for frac in (0.0, 0.5, 1.0):
            y = plot_bottom - int(plot_height * frac)
            painter.drawLine(plot_left, y, right, y)

        # Build histogram bins from accuracy values (dynamic range)
        values = [max(0.0, min(100.0, v)) for v in self._accuracy_values]
        if not values:
            # No data: draw a simple placeholder text
            painter.setPen(QPen(self._text_color))
            text = "No analyzed games"
            text_width = fm.horizontalAdvance(text)
            x_text = plot_left + (plot_width - text_width) // 2
            y_text = plot_top + plot_height // 2 + fm.ascent() // 2
            painter.drawText(x_text, y_text, text)
            return

        # Dynamic range based on data with a small margin
        data_min = min(values)
        data_max = max(values)
        margin = 2.5
        low = max(0.0, data_min - margin)
        high = min(100.0, data_max + margin)
        if high <= low:
            high = min(100.0, low + 5.0)
        bin_count = 10
        bin_size = (high - low) / float(bin_count)
        bins = [0] * bin_count
        for v in values:
            idx = int((v - low) // bin_size) if bin_size > 0 else 0
            if idx >= bin_count:
                idx = bin_count - 1
            bins[idx] += 1

        max_count = max(bins) if bins else 0
        if max_count == 0:
            max_count = 1

        bar_width = plot_width / float(bin_count)

        # Reset bin info for hover handling
        self._bin_info = []

        # Draw bars
        painter.setBrush(QBrush(self._bar_color))
        painter.setPen(Qt.PenStyle.NoPen)
        for i, count in enumerate(bins):
            if count <= 0:
                continue
            height_frac = count / float(max_count)
            bar_h = max(2, int(plot_height * height_frac))
            x = plot_left + int(i * bar_width)
            y = plot_bottom - bar_h
            w = max(1, int(bar_width) - 1)
            painter.drawRect(x, y, w, bar_h)

            # Store bin hover region and metadata
            start_acc = low + i * bin_size
            end_acc = low + (i + 1) * bin_size if i < bin_count - 1 else high
            self._bin_info.append((float(x), float(x + w), float(start_acc), float(end_acc), int(count)))

        # Draw axis line
        painter.setPen(QPen(self._axis_color, 1))
        painter.drawLine(plot_left, plot_bottom, right, plot_bottom)

        # Draw y-axis labels. Use 0 and max; add a middle label only when meaningful.
        painter.setPen(QPen(self._text_color))
        y_ticks: List[Tuple[float, float]] = []
        if max_count <= 1:
            y_ticks = [(0.0, 0.0), (1.0, float(max_count))]
        else:
            mid_val = max_count / 2.0
            y_ticks = [(0.0, 0.0), (0.5, mid_val), (1.0, float(max_count))]

        for frac, value in y_ticks:
            y = plot_bottom - int(plot_height * frac)
            label = f"{int(round(value))}"
            label_width = fm.horizontalAdvance(label)
            x = plot_left - 4 - label_width
            painter.drawText(x, y + fm.ascent() // 2, label)

        # Draw x-axis labels; density depends on available width
        painter.setPen(QPen(self._text_color))
        if high > low and plot_width > 0:
            # Decide tick count based on width
            if plot_width >= 480:
                tick_count = 7
            elif plot_width >= 320:
                tick_count = 5
            elif plot_width >= 200:
                tick_count = 3
            else:
                tick_count = 2

            for i in range(tick_count):
                if tick_count == 1:
                    value = (low + high) / 2.0
                else:
                    t = i / float(tick_count - 1)
                    value = low + t * (high - low)
                label = f"{value:.0f}%"
                x_pos = plot_left + int(((value - low) / (high - low)) * plot_width)
                text_width = fm.horizontalAdvance(label)
                x = x_pos - text_width // 2
                y = bottom - self._margins[3] + fm.ascent()
                painter.drawText(x, y, label)

    def mouseMoveEvent(self, event) -> None:
        """Update tooltip based on hovered bin."""
        if not self._bin_info:
            self.setToolTip("")
            super().mouseMoveEvent(event)
            return

        pos_x = float(event.position().x())
        tooltip_text = ""
        for x_left, x_right, start_acc, end_acc, count in self._bin_info:
            if x_left <= pos_x <= x_right and count > 0:
                label = f"{start_acc:.1f}–{end_acc:.1f}%"
                game_word = "game" if count == 1 else "games"
                tooltip_text = f"{label} ({count} {game_word})"
                break

        self.setToolTip(tooltip_text)
        super().mouseMoveEvent(event)


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
        self._on_open_pattern_games_in_search_results: Optional[Callable[["ErrorPattern"], None]] = None
        self._on_open_best_games_in_search_results: Optional[Callable[[], None]] = None
        self._on_open_worst_games_in_search_results: Optional[Callable[[], None]] = None
        
        self.current_stats: Optional["AggregatedPlayerStats"] = None
        self.current_patterns: List["ErrorPattern"] = []
        
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
        self.placeholder_text_no_source = self.player_stats_config.get(
            'placeholder_text_no_source',
            'Select a data source above to view player statistics.'
        )
        
        self._setup_ui()
        
        # Always create player selection section immediately (not just when stats are available)
        self._create_player_selection_section()
        
        # Initially show placeholder message (but keep player selection visible)
        # Default to "None" source, so show "no source" placeholder
        self._set_disabled_placeholder_visible(True, self.placeholder_text_no_source)
        
        # Connect to models/controllers if provided
        if game_model:
            self.set_game_model(game_model)
        
        if stats_controller:
            self.set_stats_controller(stats_controller)
        
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
        # Top games responsive handling (shares behavior with error patterns buttons)
        self._top_games_widget: Optional[QWidget] = None
        self._top_games_items: List[Dict[str, Any]] = []  # List of {button}
        
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
        # Controller handles worker cleanup
        pass
    
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
        # Get border color offset from config
        scroll_area_config = player_stats_config.get('scroll_area', {})
        border_color_offset = scroll_area_config.get('border_color_offset', 20)
        border_color = [min(255, pane_bg[0] + border_color_offset), min(255, pane_bg[1] + border_color_offset), min(255, pane_bg[2] + border_color_offset)]
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
                self._stats_controller.players_ready.disconnect(self._on_players_ready)
                self._stats_controller.player_selection_cleared.disconnect(self._on_player_selection_cleared)
                self._stats_controller.source_selection_changed.disconnect(self._on_source_selection_changed)
            except (RuntimeError, TypeError):
                pass
        
        self._stats_controller = stats_controller
        
        if self._stats_controller:
            # Connect to controller signals
            self._stats_controller.stats_updated.connect(self._handle_stats_updated)
            self._stats_controller.stats_unavailable.connect(self._handle_stats_unavailable)
            self._stats_controller.players_ready.connect(self._on_players_ready)
            self._stats_controller.player_selection_cleared.connect(self._on_player_selection_cleared)
            self._stats_controller.source_selection_changed.connect(self._on_source_selection_changed)
            
            # Update database controller reference if available
            if not self._database_controller and hasattr(self._stats_controller, '_database_controller'):
                self._database_controller = self._stats_controller._database_controller
            
            # Initialize source selection from controller
            source_index = stats_controller.get_source_selection()
            if hasattr(self, 'source_combo'):
                if source_index != self.source_combo.currentIndex():
                    self.source_combo.setCurrentIndex(source_index)
            
            # Populate player dropdown if selection section already exists and source is not None
            if source_index != 0:
                has_combo_attr = hasattr(self, 'player_combo')
                if has_combo_attr:
                    combo_value = getattr(self, 'player_combo', None)
                    if combo_value is not None:
                        QTimer.singleShot(100, lambda: stats_controller._schedule_dropdown_update())
    
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
        overview_widget.setProperty("section_name", "Overview")
        self.content_layout.addWidget(overview_widget)
        self.content_layout.addSpacing(section_spacing_val)

        # Accuracy Distribution Section (optional)
        accuracy_dist_config = player_stats_config.get('accuracy_distribution', {})
        if accuracy_dist_config.get('enabled', True) and getattr(self.current_stats, "accuracy_values", None):
            self._add_section_header("Accuracy Distribution", header_font, header_text_color)
            dist_widget = self._create_accuracy_distribution_widget(
                self.current_stats,
                text_color,
                section_bg_color,
                border_color,
                accuracy_dist_config,
            )
            dist_widget.setProperty("section_name", "Accuracy Distribution")
            self.content_layout.addWidget(dist_widget)
            self.content_layout.addSpacing(section_spacing_val)
        
        # Move Accuracy Section
        self._add_section_header("Move Accuracy", header_font, header_text_color)
        move_accuracy_widget = self._create_move_accuracy_widget(
            self.current_stats, text_color, label_font, value_font,
            section_bg_color, border_color, widgets_config
        )
        # Store reference for responsive width handling
        self._move_accuracy_widget = move_accuracy_widget
        move_accuracy_widget.setProperty("section_name", "Move Accuracy")
        self.content_layout.addWidget(move_accuracy_widget)
        self.content_layout.addSpacing(section_spacing_val)
        
        # Performance by Phase Section
        self._add_section_header("Performance by Phase", header_font, header_text_color)
        phase_widget = self._create_phase_performance_widget(
            self.current_stats, text_color, label_font, value_font,
            section_bg_color, border_color, widgets_config
        )
        phase_widget.setProperty("section_name", "Performance by Phase")
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
            openings_widget.setProperty("section_name", "Openings")
            self.content_layout.addWidget(openings_widget)
            self.content_layout.addSpacing(section_spacing_val)

        # Top Games Section (Best/Worst games for this player)
        self._add_section_header("Games by Performance", header_font, header_text_color)
        top_games_widget = self._create_top_games_widget(
            self.current_stats, text_color, label_font, value_font,
            section_bg_color, border_color, widgets_config
        )
        top_games_widget.setProperty("section_name", "Top Games")
        self.content_layout.addWidget(top_games_widget)
        self.content_layout.addSpacing(section_spacing_val)
        
        # Error Patterns Section
        if self.current_patterns:
            self._add_section_header("Error Patterns", header_font, header_text_color)
            patterns_widget = self._create_error_patterns_widget(
                self.current_patterns, text_color, label_font, value_font,
                section_bg_color, border_color, widgets_config
            )
            patterns_widget.setProperty("section_name", "Error Patterns")
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
        
        # Get styling configuration first (needed for both comboboxes)
        button_config = player_stats_config.get('button', {})
        font_config = player_stats_config.get('fonts', {})
        
        # Get colors - use text color from view config, input colors from input_widgets config
        combo_text = list(colors_config.get('text_color', [220, 220, 220]))
        input_widgets_config = player_stats_config.get('input_widgets', {})
        combo_bg = input_widgets_config.get('background_color', [30, 30, 35])
        combo_border = input_widgets_config.get('border_color', [60, 60, 65])
        combo_focus = input_widgets_config.get('focus_border_color', [70, 90, 130])
        
        # Get fonts from view config
        font_family = resolve_font_family(font_config.get('label_font_family', 'Helvetica Neue'))
        font_size = scale_font_size(font_config.get('label_font_size', 11))
        
        # Get button height to match button styling
        button_height = button_config.get('height', 28)
        
        # Selection colors from input_widgets config
        selection_bg = input_widgets_config.get('selection_background_color', [70, 90, 130])
        selection_text = input_widgets_config.get('selection_text_color', [240, 240, 240])
        
        from app.views.style import StyleManager
        
        # Calculate label width to ensure alignment
        # Use the longer label text to determine minimum width
        label_font_metrics = QFontMetrics(label_font)
        source_label_text = "Data Source:"
        player_label_text = "Player:"
        # Get label padding from selection config if available
        label_padding = selection_config.get('label_padding', 10)
        label_width = max(
            label_font_metrics.horizontalAdvance(source_label_text),
            label_font_metrics.horizontalAdvance(player_label_text)
        ) + label_padding
        
        selection_row_spacing = selection_config.get('row_spacing', 8)
        
        # Data source combobox (replacing radio buttons for better styling consistency) - MOVED TO TOP
        source_row = QHBoxLayout()
        source_row.setSpacing(selection_row_spacing)
        
        source_label = QLabel("Data Source:")
        source_label.setFont(label_font)
        source_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        source_label.setMinimumWidth(label_width)
        source_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        source_row.addWidget(source_label)
        
        # Create combobox for data source selection
        self.source_combo = QComboBox()
        self.source_combo.addItem("None")
        self.source_combo.addItem("Active Database")
        self.source_combo.addItem("All Open Databases")
        self.source_combo.setCurrentIndex(0)  # Default to "None"
        
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        
        # Apply combobox styling using StyleManager (same as player_combo)
        StyleManager.style_comboboxes(
            [self.source_combo],
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
        
        # Set button height to match player combo
        self.source_combo.setMinimumHeight(button_height)
        self.source_combo.setMaximumHeight(button_height)
        
        source_row.addWidget(self.source_combo, 1)  # Use stretch factor like player combo
        source_row.addStretch()
        
        layout.addLayout(source_row)
        
        # Player dropdown row
        player_row = QHBoxLayout()
        player_row.setSpacing(selection_row_spacing)
        
        player_label = QLabel("Player:")
        player_label.setFont(label_font)
        player_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        player_label.setMinimumWidth(label_width)
        player_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        player_row.addWidget(player_label)
        
        # Player combo box - make non-editable and clickable anywhere to open dropdown
        self.player_combo = QComboBox()
        self.player_combo.currentIndexChanged.connect(self._on_player_selected)
        self.player_combo.activated.connect(self._on_player_activated)  # Fired when user selects from dropdown
        player_row.addWidget(self.player_combo, 1)  # Use stretch factor to make it responsive
        
        # Apply combobox styling using StyleManager
        # StyleManager reads combobox-specific settings (like padding) from centralized config automatically
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
        
        # Store reference to widget
        self.player_selection_widget = container
        
        # Insert at the beginning
        self.content_layout.insertWidget(0, container)
        
        # Add placeholder after player selection (will be shown/hidden as needed)
        self.content_layout.addWidget(self.disabled_placeholder, 1)  # Give it stretch factor
        
        # Populate player dropdown if controller is available and source is not None
        # Use QTimer.singleShot to ensure this happens after the UI is fully set up
        if self._stats_controller:
            source_index = self._stats_controller.get_source_selection()
            if source_index != 0:
                QTimer.singleShot(100, lambda: self._stats_controller._schedule_dropdown_update())
    
    def _on_player_activated(self, index: int) -> None:
        """Handle player selection from dropdown (user clicked on item)."""
        if index < 0:
            return
        self._on_player_selected(index)
    
    def _on_player_selected(self, index: int = -1) -> None:
        """Handle player selection from combo box."""
        if not self._stats_controller or not hasattr(self, 'player_combo') or not self.player_combo:
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
                # Clear selection - call controller method
                self._stats_controller.set_player_selection(None)
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
        
        # Call controller method to handle player selection
        if player_name:
            self._stats_controller.set_player_selection(player_name)
    
    def _apply_button_styling(self, button: QPushButton, error_pattern_button: bool = False) -> None:
        """Apply standard button styling from config using StyleManager.
        
        Args:
            button: The button to style.
            error_pattern_button: If True, use error_patterns button config instead of default button config.
        """
        ui_config = self.config.get('ui', {})
        detail_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = detail_config.get('player_stats', {})
        tabs_config = detail_config.get('tabs', {})
        
        # Get button config - use error_patterns button config if specified, otherwise default button config
        if error_pattern_button:
            error_patterns_config = player_stats_config.get('error_patterns', {})
            button_config = error_patterns_config.get('button', {})
            # Fallback to default button config if error_patterns button config not found
            if not button_config:
                button_config = player_stats_config.get('button', {})
        else:
            button_config = player_stats_config.get('button', {})
        
        # Get base background color from view (pane_background)
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        button_height = button_config.get('height', 28)
        border_color = button_config.get('border_color', [60, 60, 65])
        
        # Calculate background offset from button_config if available
        # If button_config has explicit background_color, calculate offset from pane_bg
        button_bg_color = button_config.get('background_color', [50, 50, 55])
        default_background_offset = button_config.get('background_offset', 20)
        background_offset = button_bg_color[0] - pane_bg[0] if button_bg_color[0] > pane_bg[0] else default_background_offset
        
        bg_color_list = [pane_bg[0], pane_bg[1], pane_bg[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        # Calculate minimum width for "View 99999 →" (5 digits) to ensure consistent button widths
        # Get font settings from unified config
        styles_config = ui_config.get('styles', {})
        button_style_config = styles_config.get('button', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        font_family = resolve_font_family(button_style_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(button_style_config.get('font_size', 11))
        button_font = QFont(font_family, int(font_size))
        font_metrics = QFontMetrics(button_font)
        # Calculate width for "View 99999 →" (5 digits) plus padding
        max_text = "View 99999 →"
        text_width = font_metrics.horizontalAdvance(max_text)
        padding = button_style_config.get('padding', 5)
        # Get border width from button config if available, otherwise use default
        border_width = button_config.get('border_width', 1)
        min_button_width = text_width + (padding * 2) + (border_width * 2)
        
        # Apply button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        StyleManager.style_buttons(
            [button],
            self.config,
            bg_color_list,
            border_color_list,
            background_offset=background_offset,
            min_height=button_height,
            min_width=min_button_width
        )
        # Set max height manually (StyleManager doesn't support max_height)
        button.setMaximumHeight(button_height)

    @staticmethod
    def _html_escape(s: str) -> str:
        """Escape for use inside HTML content."""
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _build_two_line_html(
        self,
        title: str,
        detail: str,
        section_config: Dict[str, Any],
        label_font: QFont,
        value_font: QFont,
        text_color: QColor,
    ) -> str:
        """Build rich-text HTML for the two-line block so the inter-line gap is one fixed margin."""
        fm = QFontMetrics(label_font)
        gap_factor = float(section_config.get("two_line_gap_factor", 0.15))
        gap_px = max(0, int(fm.lineSpacing() * gap_factor))
        r, g, b = text_color.red(), text_color.green(), text_color.blue()
        color = f"rgb({r},{g},{b})"
        font_family = label_font.family()
        size1 = label_font.pointSize() if label_font.pointSize() > 0 else 11
        size2 = value_font.pointSize() if value_font.pointSize() > 0 else 11
        p1 = f'<p style="margin:0; padding:0; font-family:\'{font_family}\'; font-size:{size1}pt; color:{color};">{self._html_escape(title)}</p>'
        if not detail:
            return p1
        margin_top = f"margin-top:{gap_px}px;"
        p2 = f'<p style="margin:0; padding:0; {margin_top} font-family:\'{font_family}\'; font-size:{size2}pt; color:{color};">{self._html_escape(detail)}</p>'
        return p1 + p2

    def _create_two_line_text_column(
        self,
        title_text: str,
        detail_text: str,
        label_font: QFont,
        value_font: QFont,
        text_color: QColor,
        section_config: Dict[str, Any],
        wrap_title: bool = True,
        wrap_detail: bool = False,
    ) -> Tuple[QVBoxLayout, QLabel, QLabel]:
        """Create a single label with two lines (rich text) so the inter-line gap is one fixed CSS margin.
        Row height is capped at two lines so all cards (Games by Performance and Error Patterns) match.
        """
        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)

        fm_title = QFontMetrics(label_font)
        fm_detail = QFontMetrics(value_font)
        gap_factor = float(section_config.get("two_line_gap_factor", 0.15))
        gap_px = max(0, int(fm_title.lineSpacing() * gap_factor))
        two_line_height = fm_title.lineSpacing() + gap_px + fm_detail.lineSpacing()

        html = self._build_two_line_html(
            title_text, detail_text, section_config, label_font, value_font, text_color
        )
        block_label = QLabel()
        block_label.setTextFormat(Qt.TextFormat.RichText)
        block_label.setWordWrap(wrap_title)
        block_label.setText(html)
        block_label.setStyleSheet(
            "border: none; background: transparent; padding: 0; margin: 0;"
        )
        block_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        block_label.setFixedHeight(two_line_height)
        text_column.addWidget(block_label)

        return text_column, block_label, block_label
    
    def _create_indicator_item_row(
        self,
        title_text: str,
        detail_text: str,
        indicator_color: List[int],
        label_font: QFont,
        value_font: QFont,
        text_color: QColor,
        bg_color: QColor,
        border_color: QColor,
        section_config: Dict[str, Any],
        button_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a standardized indicator + two-line-text + button row used by multiple cards."""
        # Layout config
        item_margins = section_config.get("item_margins", [8, 6, 8, 6])
        item_spacing = section_config.get("item_spacing", 8)
        button_column_spacing = section_config.get("button_column_spacing", 8)
        severity_indicator_config = section_config.get("severity_indicator", {})
        indicator_size = severity_indicator_config.get("size", [12, 12])
        indicator_border_radius = severity_indicator_config.get("border_radius", 6)

        # Root item frame
        item = QFrame()
        item.setFrameShape(QFrame.Shape.NoFrame)
        item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        item.setMinimumWidth(0)
        item.setMaximumWidth(16777215)

        row = QHBoxLayout(item)
        row.setSpacing(button_column_spacing)
        row.setContentsMargins(item_margins[0], item_margins[1], item_margins[2], item_margins[3])
        row.setSizeConstraint(QHBoxLayout.SizeConstraint.SetNoConstraint)

        # Left column: indicator + two-line text
        left_column = QHBoxLayout()
        left_column.setSpacing(item_spacing)
        left_column.setContentsMargins(0, 0, 0, 0)

        indicator = QWidget()
        indicator.setFixedSize(indicator_size[0], indicator_size[1])
        indicator.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({indicator_color[0]}, {indicator_color[1]}, {indicator_color[2]});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {indicator_border_radius}px;
            }}
        """)
        left_column.addWidget(indicator)

        text_column, title_label, detail_label = self._create_two_line_text_column(
            title_text,
            detail_text,
            label_font,
            value_font,
            text_color,
            section_config,
            wrap_title=True,
            wrap_detail=False,
        )
        text_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        left_column.addLayout(text_column, 1)

        row.addLayout(left_column, 1)

        # Right column: button (optional)
        button: Optional[QPushButton] = None
        if button_text:
            button = QPushButton(button_text)
            self._apply_button_styling(button, error_pattern_button=True)
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

        return {
            "item": item,
            "button": button,
            "title_label": title_label,
            "detail_label": detail_label,
        }
    
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        if self._stats_controller:
            self._stats_controller._schedule_dropdown_update()
    
    def _on_source_changed(self, index: int = -1) -> None:
        """Handle data source combobox change."""
        if not self._stats_controller:
            return
        
        # Get selected index if not provided
        if index < 0:
            index = self.source_combo.currentIndex()
        
        # Call controller method to handle source selection
        self._stats_controller.set_source_selection(index)
    
    
    def _on_players_ready(self, players_with_analyzed: List[Tuple[str, int, int]]) -> None:
        """Handle players ready from controller signal."""
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
        
        # Store current selection from controller
        current_player = self._stats_controller.get_current_player() if self._stats_controller else None
        current_index = self.player_combo.currentIndex()
        
        # Clear and repopulate dropdown
        try:
            self.player_combo.clear()
        except RuntimeError:
            return
        
        # If no players found, show placeholder and return
        if not players_with_analyzed:
            # Clear player selection in controller if one was set
            if self._stats_controller and self._stats_controller.get_current_player():
                self._stats_controller.set_player_selection(None)
            # Reconnect signal
            self.player_combo.currentIndexChanged.connect(self._on_player_selected)
            self.player_combo.setCurrentIndex(-1)
            self._clear_stats_sections()
            # Show placeholder indicating no players with at least 2 analyzed games
            placeholder_text = self.player_stats_config.get(
                'placeholder_text_no_analyzed_players',
                'No players with at least 2 analyzed games found in selected database(s).'
            )
            self._set_disabled_placeholder_visible(True, placeholder_text)
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
            
            # Hide placeholder since we have players
            self._set_disabled_placeholder_visible(False)
            
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
                self._stats_controller.set_player_selection(None) if self._stats_controller else None
                self._set_disabled_placeholder_visible(True, self.placeholder_text_no_player)
                self._clear_stats_sections()
            else:
                # No previous selection, ensure combo is empty and show placeholder
                self.player_combo.setCurrentIndex(-1)
                self._set_disabled_placeholder_visible(True, self.placeholder_text_no_player)
        except RuntimeError:
            # View might be destroyed during update
            return
    
    def _on_player_selection_cleared(self) -> None:
        """Handle player selection cleared from controller."""
        if hasattr(self, 'player_combo') and self.player_combo:
            try:
                self.player_combo.currentIndexChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.player_combo.setCurrentIndex(-1)
            self.player_combo.currentIndexChanged.connect(self._on_player_selected)
        self._clear_stats_sections()
        self._set_disabled_placeholder_visible(True, self.placeholder_text_no_player)
    
    def _on_source_selection_changed(self, index: int) -> None:
        """Handle source selection changed from controller."""
        if index == 0:
            # "None" selected - clear player dropdown and stats
            if hasattr(self, 'player_combo') and self.player_combo:
                try:
                    self.player_combo.currentIndexChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self.player_combo.clear()
                self.player_combo.currentIndexChanged.connect(self._on_player_selected)
            self._clear_stats_sections()
            self._set_disabled_placeholder_visible(True, self.placeholder_text_no_source)
        else:
            # Show loading placeholder to prevent layout shift while dropdown is being populated
            loading_text = self.player_stats_config.get(
                'placeholder_text_loading',
                'Loading players...'
            )
            self._set_disabled_placeholder_visible(True, loading_text)
    
    
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
        # Average Accuracy (include per-game min/max if available)
        accuracy = stats.player_stats.accuracy if stats.player_stats.accuracy is not None else 0.0
        min_acc = getattr(stats, "min_accuracy", None)
        max_acc = getattr(stats, "max_accuracy", None)
        if min_acc is not None and max_acc is not None and stats.analyzed_games > 1:
            accuracy_text = f"{accuracy:.1f}% (Min: {min_acc:.1f}%, Max: {max_acc:.1f}%)"
        else:
            accuracy_text = f"{accuracy:.1f}%"
        self._add_stat_row(grid, 3, "Average Accuracy:", accuracy_text, label_font, value_font, text_color)
        # Estimated Elo
        est_elo = stats.player_stats.estimated_elo if stats.player_stats.estimated_elo is not None else 0
        self._add_stat_row(grid, 4, "Estimated Elo:", str(est_elo), label_font, value_font, text_color)
        # Average CPL (include per-game min/max if available)
        avg_cpl = stats.player_stats.average_cpl if stats.player_stats.average_cpl is not None else 0.0
        min_acpl = getattr(stats, "min_acpl", None)
        max_acpl = getattr(stats, "max_acpl", None)
        if min_acpl is not None and max_acpl is not None and stats.analyzed_games > 1:
            cpl_text = f"{avg_cpl:.1f} (Min: {min_acpl:.1f}, Max: {max_acpl:.1f})"
        else:
            cpl_text = f"{avg_cpl:.1f}"
        self._add_stat_row(grid, 5, "Average CPL:", cpl_text, label_font, value_font, text_color)
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

    def _create_top_games_widget(self, stats: "AggregatedPlayerStats",
                                 text_color: QColor, label_font: QFont, value_font: QFont,
                                 bg_color: QColor, border_color: QColor,
                                 widgets_config: Dict[str, Any]) -> QWidget:
        """Create 'Games by Performance' widget with Best/Worst sub-cards and View buttons."""
        widget = QWidget()
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)

        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)

        layout = QVBoxLayout(widget)
        # Match error patterns card: ensure bottom padding is at least top padding
        bottom_margin = max(section_margins[1], section_margins[3])
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], bottom_margin)
        layout.setSpacing(section_spacing)

        # Store reference for responsive handling
        self._top_games_widget = widget
        self._top_games_items = []

        # Determine how many best/worst games are available (may be less than configured max)
        best_count = 0
        worst_count = 0
        best_min_acc: Optional[float] = None
        best_max_acc: Optional[float] = None
        worst_min_acc: Optional[float] = None
        worst_max_acc: Optional[float] = None

        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        error_patterns_config = player_stats_config.get('error_patterns', {})
        top_games_config = player_stats_config.get('top_games', {})
        max_best = int(top_games_config.get('max_best', 3))
        max_worst = int(top_games_config.get('max_worst', 3))

        if self._stats_controller and stats:
            try:
                best_count, best_min_acc, best_max_acc = self._stats_controller.get_top_best_games_summary(max_best)
                worst_count, worst_min_acc, worst_max_acc = self._stats_controller.get_top_worst_games_summary(max_worst, max_best)
            except Exception:
                best_count = 0
                worst_count = 0
                best_min_acc = best_max_acc = None
                worst_min_acc = worst_max_acc = None

        # Reuse the exact layout pattern of error pattern items, including indicator dots.
        # Best games sub-card
        severity_indicator_config = error_patterns_config.get('severity_indicator', {})
        severity_colors_config = severity_indicator_config.get('colors', {})
        # Use a "low" (typically greenish) severity color for best games
        best_color = severity_colors_config.get('low', [120, 200, 120])
        indicator_size = severity_indicator_config.get('size', [12, 12])
        indicator_border_radius = severity_indicator_config.get('border_radius', 6)

        if best_min_acc is not None and best_max_acc is not None:
            best_detail_text = (
                f"(lowest CPL, Accuracy {best_min_acc:.1f}–{best_max_acc:.1f}%, {best_count} game(s))"
            )
        else:
            best_detail_text = f"(lowest CPL, {best_count} game(s))"
        best_button_text = f"View {best_count} →" if best_count > 0 else "View →"

        best_row_data = self._create_indicator_item_row(
            title_text="Best Games",
            detail_text=best_detail_text,
            indicator_color=best_color,
            label_font=label_font,
            value_font=value_font,
            text_color=text_color,
            bg_color=bg_color,
            border_color=border_color,
            section_config=error_patterns_config,
            button_text=best_button_text,
        )
        best_item = best_row_data["item"]
        best_button = best_row_data["button"]

        if best_count > 0 and self._on_open_best_games_in_search_results:
            best_button.clicked.connect(lambda checked=False: self._on_open_best_games_in_search_results())
        else:
            best_button.setEnabled(False)
        layout.addWidget(best_item)
        # Register for responsive button visibility updates
        self._top_games_items.append({'button': best_button})

        # Worst games sub-card
        # Use the "critical" (red) severity color for worst games
        worst_color = severity_colors_config.get('critical', [255, 100, 100])

        if worst_min_acc is not None and worst_max_acc is not None:
            worst_detail_text = (
                f"(highest CPL, Accuracy {worst_min_acc:.1f}–{worst_max_acc:.1f}%, {worst_count} game(s))"
            )
        else:
            worst_detail_text = f"(highest CPL, {worst_count} game(s))"
        worst_button_text = f"View {worst_count} →" if worst_count > 0 else "View →"

        worst_row_data = self._create_indicator_item_row(
            title_text="Worst Games",
            detail_text=worst_detail_text,
            indicator_color=worst_color,
            label_font=label_font,
            value_font=value_font,
            text_color=text_color,
            bg_color=bg_color,
            border_color=border_color,
            section_config=error_patterns_config,
            button_text=worst_button_text,
        )
        worst_item = worst_row_data["item"]
        worst_button = worst_row_data["button"]

        if worst_count > 0 and self._on_open_worst_games_in_search_results:
            worst_button.clicked.connect(lambda checked=False: self._on_open_worst_games_in_search_results())
        else:
            worst_button.setEnabled(False)
        layout.addWidget(worst_item)
        # Register for responsive button visibility updates
        self._top_games_items.append({'button': worst_button})
        # Add a tiny spacer after the last sub-card so buttons don't visually touch the outer border
        layout.addSpacing(2)

        # Initial responsive update
        QTimer.singleShot(0, self._update_top_games_visibility)

        return widget

    def _create_accuracy_distribution_widget(
        self,
        stats: "AggregatedPlayerStats",
        text_color: QColor,
        bg_color: QColor,
        border_color: QColor,
        dist_config: Dict[str, Any],
    ) -> QWidget:
        """Create accuracy distribution section widget."""
        border_radius = dist_config.get('border_radius', 5)
        section_margins = dist_config.get('margins', [10, 10, 10, 10])
        section_spacing = dist_config.get('section_spacing', 6)

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

        dist_widget = AccuracyDistributionWidget(self.config, getattr(stats, "accuracy_values", []), text_color, widget)
        layout.addWidget(dist_widget)

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
        # Ensure bottom margin matches top margin for consistent padding
        # Use top margin value for bottom to ensure equal padding
        bottom_margin = max(section_margins[1], section_margins[3])  # Use the larger of top or original bottom
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], bottom_margin)
        layout.setSpacing(section_spacing)
        
        # Store reference for responsive width handling and HTML rebuild
        self._error_patterns_widget = widget
        self._error_pattern_items = []
        self._error_patterns_label_font = label_font
        self._error_patterns_value_font = value_font
        self._error_patterns_text_color = text_color

        # Add each pattern
        for i, pattern in enumerate(patterns):
            pattern_data = self._create_error_pattern_item(
                pattern, text_color, label_font, value_font, bg_color, border_color, widgets_config
            )
            pattern_widget = pattern_data['item']
            layout.addWidget(pattern_widget)
            self._error_pattern_items.append(pattern_data)
            
            # Add extra spacing after the last item to ensure bottom padding
            if i == len(patterns) - 1:
                # Add explicit spacing to guarantee bottom margin is visible
                layout.addSpacing(2)
        
        # Update visibility based on initial width
        QTimer.singleShot(0, self._update_error_patterns_visibility)
        
        return widget
    
    def _create_error_pattern_item(self, pattern: "ErrorPattern",
                                  text_color: QColor, label_font: QFont, value_font: QFont,
                                  bg_color: QColor, border_color: QColor,
                                  widgets_config: Dict[str, Any]) -> QWidget:
        """Create a single error pattern item using the unified row builder."""
        # Get error patterns config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        error_patterns_config = player_stats_config.get('error_patterns', {})
        
        severity_indicator_config = error_patterns_config.get('severity_indicator', {})
        severity_colors_config = severity_indicator_config.get('colors', {})
        severity_colors = {
            "critical": severity_colors_config.get('critical', [255, 100, 100]),
            "high": severity_colors_config.get('high', [255, 150, 100]),
            "moderate": severity_colors_config.get('moderate', [255, 200, 100]),
            "low": severity_colors_config.get('low', [200, 200, 100])
        }
        severity_color = severity_colors.get(pattern.severity, severity_colors_config.get('default', [150, 150, 150]))
        
        freq_text = f"({pattern.frequency} occurrences, {pattern.percentage:.1f}%)"
        button_text = f"View {len(pattern.related_games)} →" if pattern.related_games else None
        
        row_data = self._create_indicator_item_row(
            title_text=pattern.description,
            detail_text=freq_text,
            indicator_color=severity_color,
            label_font=label_font,
            value_font=value_font,
            text_color=text_color,
            bg_color=bg_color,
            border_color=border_color,
            section_config=error_patterns_config,
            button_text=button_text,
        )
        
        view_button = row_data["button"]
        if view_button and pattern.related_games:
            view_button.clicked.connect(lambda checked, p=pattern: self._on_view_pattern_games(p))
        
        # Return item data for responsive handling (title_label and detail_label are the same block label)
        return {
            'item': row_data["item"],
            'button': view_button,
            'desc_label': row_data["title_label"],
            'freq_label': row_data["detail_label"],
            'full_text': pattern.description,
            'freq_text': freq_text,
        }
    
    def _on_view_pattern_games(self, pattern: "ErrorPattern") -> None:
        """Handle click on 'View games' button for a pattern.

        If an open-in-search-results callback is set, opens the pattern's games in a Search Results tab.
        Otherwise falls back to grouping by database and highlighting in the database with the most games.
        """
        if not pattern.related_games:
            return
        if self._on_open_pattern_games_in_search_results:
            self._on_open_pattern_games_in_search_results(pattern)
            return
        if not self._database_panel or not self._stats_controller:
            return
        # Fallback: group games by database, switch to database with most games, highlight
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
        target_database = max(games_by_database.items(), key=lambda x: len(x[1]))[0]
        target_row_indices = games_by_database[target_database]
        self._stats_controller.highlight_rows(target_database, target_row_indices)
    
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

        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        error_patterns_config = player_stats_config.get('error_patterns', {})
        label_font = getattr(self, '_error_patterns_label_font', None)
        value_font = getattr(self, '_error_patterns_value_font', None)
        text_color = getattr(self, '_error_patterns_text_color', None)
        if not label_font or not value_font or not text_color:
            return

        # Update each error pattern item
        for pattern_data in self._error_pattern_items:
            button = pattern_data.get('button')
            desc_label = pattern_data.get('desc_label')
            full_text = pattern_data.get('full_text', '')
            freq_text = pattern_data.get('freq_text', '')

            if not desc_label:
                continue

            # Update button visibility with fade
            if button:
                if should_show_full:
                    button.setVisible(True)
                    button.setMaximumWidth(16777215)
                    if hasattr(button, 'graphicsEffect') and button.graphicsEffect():
                        button.graphicsEffect().setOpacity(1.0)
                else:
                    if not hasattr(button, 'graphicsEffect') or not button.graphicsEffect():
                        opacity_effect = QGraphicsOpacityEffect(button)
                        button.setGraphicsEffect(opacity_effect)
                    button.graphicsEffect().setOpacity(0.0)
                    button.setMaximumWidth(0)
                    button.setVisible(False)

            # Update block label content (two-line HTML). Keep title to one line (elide) so row height matches Games cards.
            item = pattern_data.get('item')
            item_margins_config = error_patterns_config.get('item_margins', [8, 6, 8, 6])
            item_margins = item_margins_config[0] + item_margins_config[2]
            severity_indicator_config = error_patterns_config.get('severity_indicator', {})
            indicator_size = severity_indicator_config.get('size', [12, 12])
            indicator_width = indicator_size[0]
            spacing = error_patterns_config.get('item_spacing', 8)
            truncation_config = error_patterns_config.get('truncation', {})
            min_text_width = truncation_config.get('min_text_width', 50)
            # Reserve space for button when full (so title elides to one line and row height stays consistent)
            button_reserve = 90 if should_show_full else 0
            estimated_available = max(min_text_width, available_width - item_margins - indicator_width - spacing - button_reserve)
            font_metrics = QFontMetrics(label_font)
            title_one_line = font_metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, estimated_available)

            if should_show_full:
                html = self._build_two_line_html(
                    title_one_line, freq_text, error_patterns_config,
                    label_font, value_font, text_color,
                )
                desc_label.setTextFormat(Qt.TextFormat.RichText)
                desc_label.setText(html)
                desc_label.setWordWrap(False)
                desc_label.setMaximumWidth(16777215)
                desc_label.setMinimumWidth(0)
                desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                if item:
                    item.setMaximumWidth(16777215)
                    item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            else:
                html = self._build_two_line_html(
                    title_one_line, "", error_patterns_config,
                    label_font, value_font, text_color,
                )
                desc_label.setTextFormat(Qt.TextFormat.RichText)
                desc_label.setText(html)
                desc_label.setWordWrap(False)
                desc_label.setMaximumWidth(estimated_available)
                desc_label.setMinimumWidth(0)
                desc_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                if item:
                    item.setMaximumWidth(available_width)
                    item.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

    def _update_top_games_visibility(self) -> None:
        """Update Games by Performance button visibility based on available width.

        Uses the same collapse threshold and fade-out behavior as error patterns.
        """
        if not self._top_games_widget or not hasattr(self, 'scroll_area'):
            return

        # Get current width of the scroll area viewport
        available_width = self.scroll_area.viewport().width()

        if available_width == 0:
            return

        # Reuse the error patterns collapse threshold for consistent behavior
        should_show_full = available_width >= self.error_patterns_collapse_threshold

        for item_data in self._top_games_items:
            button = item_data.get('button')
            if not button:
                continue

            # Update button visibility with the same fade pattern as error patterns
            if should_show_full:
                button.setVisible(True)
                button.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                if hasattr(button, 'graphicsEffect') and button.graphicsEffect():
                    button.graphicsEffect().setOpacity(1.0)
            else:
                if not hasattr(button, 'graphicsEffect') or not button.graphicsEffect():
                    opacity_effect = QGraphicsOpacityEffect(button)
                    button.setGraphicsEffect(opacity_effect)
                button.graphicsEffect().setOpacity(0.0)
                button.setMaximumWidth(0)
                button.setVisible(False)
    
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
                # Get width calculation values from config
                panel_config = self.config.get('ui', {}).get('panels', {}).get('detail', {})
                player_stats_config = panel_config.get('player_stats', {})
                openings_config = player_stats_config.get('openings', {})
                label_column_width = openings_config.get('label_column_width', 120)
                margins_width = openings_config.get('margins_width', 40)
                min_value_width = openings_config.get('min_value_width', 150)
                max_value_width = max(min_value_width, available_width - label_column_width - margins_width)
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
                # Get width calculation values from config
                panel_config = self.config.get('ui', {}).get('panels', {}).get('detail', {})
                player_stats_config = panel_config.get('player_stats', {})
                openings_config = player_stats_config.get('openings', {})
                label_column_width = openings_config.get('label_column_width', 120)
                margins_width = openings_config.get('margins_width', 40)
                min_eco_width = openings_config.get('min_eco_width', 100)
                estimated_available = max(min_eco_width, available_width - label_column_width - margins_width)
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
            QTimer.singleShot(0, self._update_top_games_visibility)
            QTimer.singleShot(0, self._update_error_patterns_visibility)
            QTimer.singleShot(0, self._update_openings_visibility)
        return super().eventFilter(obj, event)
    
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Handle context menu event for copying sections or full stats.
        
        Args:
            event: Context menu event.
        """
        if not self.current_stats:
            return
        
        # Find which section was clicked by checking widget geometries
        section_name = None
        
        try:
            if hasattr(self, 'content_widget') and self.content_widget:
                # Get global position
                global_pos = event.globalPos()
                
                # Check all section containers to see if click is within their bounds
                for i in range(self.content_layout.count()):
                    item = self.content_layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        section = widget.property("section_name")
                        if section:
                            # Get widget's global geometry
                            widget_global_pos = widget.mapToGlobal(QPoint(0, 0))
                            widget_global_rect = widget.geometry()
                            widget_global_rect.moveTopLeft(widget_global_pos)
                            
                            # Check if click is within this widget's bounds
                            if widget_global_rect.contains(global_pos):
                                section_name = section
                                break
        except (RuntimeError, AttributeError, TypeError):
            # If detection fails, just show full stats option
            pass
        
        # Create context menu
        menu = QMenu(self)
        
        # Get config for styling
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        colors_config = player_stats_config.get('colors', {})
        bg_color = colors_config.get('background', [40, 40, 45])
        
        # Style the menu
        from app.views.style import StyleManager
        StyleManager.style_context_menu(menu, self.config, bg_color)
        
        # Add actions
        if section_name:
            copy_section_action = menu.addAction("Copy section to clipboard")
            copy_section_action.triggered.connect(lambda checked=False, name=section_name: self._copy_section_to_clipboard(name))
        
        copy_full_action = menu.addAction("Copy stats to clipboard")
        copy_full_action.triggered.connect(self._copy_full_stats_to_clipboard)
        
        # Show menu
        menu.exec(event.globalPos())
    
    def _copy_section_to_clipboard(self, section_name: str) -> None:
        """Copy a specific section to clipboard.
        
        Args:
            section_name: Name of the section to copy.
        """
        if not self.current_stats:
            return
        
        from app.utils.player_stats_text_formatter import PlayerStatsTextFormatter
        current_player = self._stats_controller.get_current_player() if self._stats_controller else None
        text = PlayerStatsTextFormatter.format_section(
            self.current_stats, self.current_patterns, section_name, current_player or "Player"
        )
        
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            
            # Update status bar through controller
            if self._stats_controller:
                self._stats_controller.set_status(f"Copied '{section_name}' section to clipboard")
    
    def _copy_full_stats_to_clipboard(self) -> None:
        """Copy the full stats to clipboard."""
        if not self.current_stats:
            return
        
        from app.utils.player_stats_text_formatter import PlayerStatsTextFormatter
        current_player = self._stats_controller.get_current_player() if self._stats_controller else None
        text = PlayerStatsTextFormatter.format_full_stats(
            self.current_stats, self.current_patterns, current_player or "Player"
        )
        
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            
            # Update status bar through controller
            if self._stats_controller:
                self._stats_controller.set_status("Copied player statistics to clipboard")


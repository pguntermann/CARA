"""Top-level window orchestration."""

import chess
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QSplitterHandle,
    QApplication,
    QMenuBar,
    QMenu,
    QDialog,
    QFileDialog,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QAction, QKeySequence, QCloseEvent, QColor, QDesktopServices, QCursor
from PyQt6.QtCore import Qt, QEvent, QTimer, QUrl, QThread, pyqtSignal

from app.views.main_panel import MainPanel
from app.views.detail_panel import DetailPanel
from app.views.database_panel import DatabasePanel
from app.views.status_panel import StatusPanel
from app.views.engine_dialog import EngineDialog
from app.views.engine_configuration_dialog import EngineConfigurationDialog
from app.views.classification_settings_dialog import ClassificationSettingsDialog
from app.views.about_dialog import AboutDialog
from app.views.message_dialog import MessageDialog
from app.views.confirmation_dialog import ConfirmationDialog
from app.controllers.app_controller import AppController
from app.input.shortcut_manager import ShortcutManager
from app.models.column_profile_model import DEFAULT_PROFILE_NAME
from app.models.database_model import DatabaseModel, GameData
from app.controllers.engine_controller import TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS
from app.services.pgn_cleaning_service import PgnCleaningService
from app.utils.font_utils import resolve_font_family, scale_font_size
from typing import Dict, Any, Optional, List


class MainWindow(QMainWindow):
    """Main application window with four distinct sections."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the main window.
        
        Args:
            config: Configuration dictionary loaded from ConfigLoader.
        """
        super().__init__()
        self.config = config
        
        # Debug log: MainWindow initialization started
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.debug("MainWindow initialization started")
        
        # Initialize controller
        # Note: user_settings_service will be set after column profile controller is created
        # We'll update it in _load_user_settings
        self.controller = AppController(config, None)
        
        # UCI debug flags (for console output)
        self._uci_debug_outbound = False
        self._uci_debug_inbound = False
        self._uci_debug_lifecycle = False
        
        # AI debug flags (for console output)
        self._ai_debug_outbound = False
        self._ai_debug_inbound = False
        
        self._setup_window()
        self._setup_tooltip_styling()
        self._setup_menu_bar()
        self._setup_ui()
        self._setup_shortcuts()
        
        # Load user settings after UI is set up (so detail_panel is available)
        self._load_user_settings()
        
        # Set up UCI debug callbacks
        self._setup_uci_debug_callbacks()
        
        # Set up AI debug callbacks
        self._setup_ai_debug_callbacks()
        
        # Log application initialized
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.info("Application initialized: config loaded, services ready")
    
    def _setup_window(self) -> None:
        """Setup window properties."""
        self.setWindowTitle("CARA: Chess Analysis and Review Application")
        x = self.config.get('ui', {}).get('window', {}).get('x', 100)
        y = self.config.get('ui', {}).get('window', {}).get('y', 100)
        width = self.config.get('ui', {}).get('window', {}).get('width', 1200)
        height = self.config.get('ui', {}).get('window', {}).get('height', 800)
        self.setGeometry(x, y, width, height)
    
    def _setup_tooltip_styling(self) -> None:
        """Setup QToolTip styling to ensure proper colors regardless of OS theme."""
        # Get tooltip configuration
        tooltip_config = self.config.get('ui', {}).get('positional_heatmap', {}).get('tooltip', {})
        
        # Extract colors with defaults
        bg_color = tooltip_config.get('background_color', [45, 45, 50])
        text_color = tooltip_config.get('text_color', [220, 220, 220])
        border_color = tooltip_config.get('border_color', [60, 60, 65])
        border_width = tooltip_config.get('border_width', 1)
        border_radius = tooltip_config.get('border_radius', 5)
        padding = tooltip_config.get('padding', 10)
        
        # Create QToolTip stylesheet
        tooltip_stylesheet = f"""
            QToolTip {{
                background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
                color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
                border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
                border-radius: {border_radius}px;
                padding: {padding}px;
            }}
        """
        
        # Apply stylesheet to QApplication instance (tooltips are application-wide)
        app = QApplication.instance()
        if app:
            # Get existing stylesheet and append tooltip styling
            existing_stylesheet = app.styleSheet()
            if existing_stylesheet:
                app.setStyleSheet(existing_stylesheet + "\n" + tooltip_stylesheet)
            else:
                app.setStyleSheet(tooltip_stylesheet)
    
    def _setup_menu_bar(self) -> None:
        """Setup the menu bar with menu items."""
        
        # Debug log
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.debug("Setting up menus")
        
        menu_bar = self.menuBar()
        
        # Apply menu bar styling from config
        self._apply_menu_bar_styling(menu_bar)
        
        # Setup each menu section
        self._setup_file_menu(menu_bar)
        self._setup_edit_menu(menu_bar)
        self._setup_board_menu(menu_bar)
        self._setup_pgn_menu(menu_bar)
        self._setup_moves_list_menu(menu_bar)
        self._setup_game_analysis_menu(menu_bar)
        self._setup_manual_analysis_menu(menu_bar)
        self._setup_annotations_menu(menu_bar)
        self._setup_engines_menu(menu_bar)
        self._setup_ai_summary_menu(menu_bar)
        self._setup_view_menu(menu_bar)
        self._setup_help_menu(menu_bar)
        self._setup_debug_menu(menu_bar)
    
    def _setup_file_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the File menu."""
        file_menu = menu_bar.addMenu("File")
        
        # Open PGN Database action
        open_pgn_database_action = QAction("Open PGN Database", self)
        open_pgn_database_action.setShortcut(QKeySequence("Ctrl+O"))
        open_pgn_database_action.triggered.connect(self._open_pgn_database)
        file_menu.addAction(open_pgn_database_action)
        
        file_menu.addSeparator()
        
        # Close PGN Database action
        self.close_pgn_database_action = QAction("Close PGN Database", self)
        self.close_pgn_database_action.setShortcut(QKeySequence("Ctrl+W"))
        self.close_pgn_database_action.triggered.connect(self._close_pgn_database)
        file_menu.addAction(self.close_pgn_database_action)
        
        # Close All PGN Databases action
        self.close_all_databases_action = QAction("Close All PGN Databases", self)
        self.close_all_databases_action.setShortcut(QKeySequence("Ctrl+Alt+W"))
        self.close_all_databases_action.triggered.connect(self._close_all_pgn_databases)
        file_menu.addAction(self.close_all_databases_action)
        
        # Clear Clipboard Database action
        clear_clipboard_action = QAction("Clear Clipboard Database", self)
        clear_clipboard_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        clear_clipboard_action.triggered.connect(self._clear_clipboard_database)
        file_menu.addAction(clear_clipboard_action)
        
        file_menu.addSeparator()
        
        # Save PGN Database action
        self.save_pgn_database_action = QAction("Save PGN Database", self)
        self.save_pgn_database_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_pgn_database_action.triggered.connect(self._save_pgn_database)
        self.save_pgn_database_action.setEnabled(False)  # Disabled by default
        file_menu.addAction(self.save_pgn_database_action)
        
        # Save PGN Database as action
        save_pgn_database_as_action = QAction("Save PGN Database as...", self)
        save_pgn_database_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_pgn_database_as_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        save_pgn_database_as_action.triggered.connect(self._save_pgn_database_as)
        file_menu.addAction(save_pgn_database_as_action)
        
        file_menu.addSeparator()
        
        # Import Games from Online action
        import_online_games_action = QAction("Import Games from Online...", self)
        import_online_games_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        import_online_games_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        import_online_games_action.triggered.connect(self._import_online_games)
        file_menu.addAction(import_online_games_action)
        
        file_menu.addSeparator()
        
        # Bulk Replace action
        bulk_replace_action = QAction("Bulk Replace Tags...", self)
        bulk_replace_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        bulk_replace_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        bulk_replace_action.triggered.connect(self._bulk_replace)
        file_menu.addAction(bulk_replace_action)
        
        # Bulk Add/Remove Tags action
        bulk_tag_action = QAction("Bulk Add/Remove Tags...", self)
        bulk_tag_action.setShortcut(QKeySequence("Ctrl+Alt+T"))
        bulk_tag_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        bulk_tag_action.triggered.connect(self._bulk_tag)
        file_menu.addAction(bulk_tag_action)
        
        # Bulk Clean PGN action
        bulk_clean_pgn_action = QAction("Bulk Clean PGN...", self)
        bulk_clean_pgn_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        bulk_clean_pgn_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        bulk_clean_pgn_action.triggered.connect(self._bulk_clean_pgn)
        file_menu.addAction(bulk_clean_pgn_action)
        
        file_menu.addSeparator()
        
        # Deduplicate Games action
        deduplicate_games_action = QAction("Deduplicate Games in Active Database...", self)
        deduplicate_games_action.setShortcut(QKeySequence("Ctrl+Shift+U"))
        deduplicate_games_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        deduplicate_games_action.triggered.connect(self._deduplicate_games)
        file_menu.addAction(deduplicate_games_action)
        
        file_menu.addSeparator()
        
        # Search Games action
        search_games_action = QAction("Search Games...", self)
        search_games_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        search_games_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        search_games_action.triggered.connect(self._search_games)
        file_menu.addAction(search_games_action)
        
        # Close Search Results action
        self.close_search_results_action = QAction("Close Search Results", self)
        self.close_search_results_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
        self.close_search_results_action.triggered.connect(self._close_search_results)
        self.close_search_results_action.setEnabled(False)  # Disabled by default
        file_menu.addAction(self.close_search_results_action)
        
        file_menu.addSeparator()
        
        # Close Application action
        close_action = QAction("Close Application", self)
        close_action.setShortcut("Ctrl+Q")
        close_action.triggered.connect(self._close_application)
        file_menu.addAction(close_action)
    
    def _setup_edit_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Edit menu."""
        edit_menu = menu_bar.addMenu("Edit")
        
        # Copy FEN action
        copy_fen_action = QAction("Copy FEN", self)
        copy_fen_action.setShortcut(QKeySequence("Shift+F"))
        copy_fen_action.triggered.connect(self._copy_fen_to_clipboard)
        edit_menu.addAction(copy_fen_action)
        
        # Copy PGN action
        copy_pgn_action = QAction("Copy PGN", self)
        copy_pgn_action.setShortcut(QKeySequence("Ctrl+P"))
        copy_pgn_action.triggered.connect(self._copy_pgn_to_clipboard)
        edit_menu.addAction(copy_pgn_action)
        
        edit_menu.addSeparator()
        
        # Copy selected Games action
        copy_selected_games_action = QAction("Copy selected Games", self)
        copy_selected_games_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_selected_games_action.triggered.connect(self._copy_selected_games)
        edit_menu.addAction(copy_selected_games_action)
        
        # Cut selected Games action
        cut_selected_games_action = QAction("Cut selected Games", self)
        cut_selected_games_action.setShortcut(QKeySequence("Ctrl+Shift+X"))
        cut_selected_games_action.triggered.connect(self._cut_selected_games)
        edit_menu.addAction(cut_selected_games_action)
        
        edit_menu.addSeparator()
        
        # Paste FEN to Board action
        paste_fen_action = QAction("Paste FEN to Board", self)
        paste_fen_action.setShortcut(QKeySequence("Ctrl+F"))
        paste_fen_action.triggered.connect(self._paste_fen_to_board)
        edit_menu.addAction(paste_fen_action)
        
        edit_menu.addSeparator()
        
        # Paste PGN to Clipboard DB action
        paste_pgn_clipboard_action = QAction("Paste PGN to Clipboard DB", self)
        paste_pgn_clipboard_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_pgn_clipboard_action.triggered.connect(self._paste_pgn_to_clipboard_db)
        edit_menu.addAction(paste_pgn_clipboard_action)
        
        # Paste PGN to active DB action
        paste_pgn_active_action = QAction("Paste PGN to active DB", self)
        paste_pgn_active_action.setShortcut(QKeySequence("Ctrl+Alt+V"))
        paste_pgn_active_action.triggered.connect(self._paste_pgn_to_active_db)
        edit_menu.addAction(paste_pgn_active_action)
    
    def _setup_board_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Board menu."""
        board_menu = menu_bar.addMenu("Board")
        
        # Rotate Board action (checkable to show toggle state)
        self.rotate_action = QAction("Rotate Board", self)
        self.rotate_action.setShortcut(QKeySequence("X"))
        self.rotate_action.setCheckable(True)
        self.rotate_action.triggered.connect(self.controller.rotate_board)
        board_menu.addAction(self.rotate_action)
        
        board_menu.addSeparator()
        
        # Show Game Info action (checkable to show toggle state)
        self.game_info_action = QAction("Show Game Info", self)
        self.game_info_action.setShortcut(QKeySequence("Alt+I"))
        self.game_info_action.setCheckable(True)
        self.game_info_action.triggered.connect(self.controller.toggle_game_info_visibility)
        board_menu.addAction(self.game_info_action)
        
        # Show/Hide Coordinates action (checkable to show toggle state)
        self.coordinates_action = QAction("Show Coordinates", self)
        self.coordinates_action.setShortcut(QKeySequence("Alt+C"))
        self.coordinates_action.setCheckable(True)
        self.coordinates_action.triggered.connect(self.controller.toggle_coordinates_visibility)
        board_menu.addAction(self.coordinates_action)
        
        # Show Turn Indicator action (checkable to show toggle state)
        self.turn_indicator_action = QAction("Show Turn Indicator", self)
        self.turn_indicator_action.setShortcut(QKeySequence("Alt+T"))
        self.turn_indicator_action.setCheckable(True)
        self.turn_indicator_action.triggered.connect(self.controller.toggle_turn_indicator_visibility)
        board_menu.addAction(self.turn_indicator_action)
        
        # Show Material Widget action (checkable to show toggle state)
        self.material_widget_action = QAction("Show Material", self)
        self.material_widget_action.setShortcut(QKeySequence("Alt+U"))
        self.material_widget_action.setCheckable(True)
        self.material_widget_action.triggered.connect(self.controller.toggle_material_widget_visibility)
        board_menu.addAction(self.material_widget_action)
        
        board_menu.addSeparator()
        
        # Show Evaluation Bar action (checkable to show toggle state)
        self.evaluation_bar_action = QAction("Show Evaluation Bar", self)
        self.evaluation_bar_action.setShortcut(QKeySequence("Alt+E"))
        self.evaluation_bar_action.setCheckable(True)
        self.evaluation_bar_action.triggered.connect(self.controller.toggle_evaluation_bar_visibility)
        board_menu.addAction(self.evaluation_bar_action)
        
        # Show Positional Heat-map action (checkable to show toggle state)
        self.positional_heatmap_action = QAction("Show Positional Heat-map", self)
        self.positional_heatmap_action.setShortcut(QKeySequence("Alt+H"))
        self.positional_heatmap_action.setCheckable(True)
        self.positional_heatmap_action.triggered.connect(self.controller.toggle_positional_heatmap_visibility)
        board_menu.addAction(self.positional_heatmap_action)
        
        board_menu.addSeparator()
        
        # Show Played Move action (checkable to show toggle state)
        self.playedmove_arrow_action = QAction("Show Played Move", self)
        self.playedmove_arrow_action.setShortcut(QKeySequence("Alt+P"))
        self.playedmove_arrow_action.setCheckable(True)
        self.playedmove_arrow_action.triggered.connect(self.controller.toggle_playedmove_arrow_visibility)
        board_menu.addAction(self.playedmove_arrow_action)
        
        # Show Best Next Move action (checkable to show toggle state)
        self.bestnextmove_arrow_action = QAction("Show Best Next Move", self)
        self.bestnextmove_arrow_action.setShortcut(QKeySequence("Alt+B"))
        self.bestnextmove_arrow_action.setCheckable(True)
        self.bestnextmove_arrow_action.triggered.connect(self.controller.toggle_bestnextmove_arrow_visibility)
        board_menu.addAction(self.bestnextmove_arrow_action)
        
        # Show Next Best Move (PV2) action (checkable to show toggle state)
        self.pv2_arrow_action = QAction("Show Next Best Move (PV2)", self)
        self.pv2_arrow_action.setShortcut(QKeySequence("Alt+2"))
        self.pv2_arrow_action.setCheckable(True)
        self.pv2_arrow_action.triggered.connect(self.controller.toggle_pv2_arrow_visibility)
        board_menu.addAction(self.pv2_arrow_action)
        
        # Show Next Best Move (PV3) action (checkable to show toggle state)
        self.pv3_arrow_action = QAction("Show Next Best Move (PV3)", self)
        self.pv3_arrow_action.setShortcut(QKeySequence("Alt+3"))
        self.pv3_arrow_action.setCheckable(True)
        self.pv3_arrow_action.triggered.connect(self.controller.toggle_pv3_arrow_visibility)
        board_menu.addAction(self.pv3_arrow_action)
        
        # Show Best Alternative Move action (checkable to show toggle state)
        self.bestalternativemove_arrow_action = QAction("Show Best Alternative Move", self)
        self.bestalternativemove_arrow_action.setShortcut(QKeySequence("Alt+A"))
        self.bestalternativemove_arrow_action.setCheckable(True)
        self.bestalternativemove_arrow_action.triggered.connect(self.controller.toggle_bestalternativemove_arrow_visibility)
        board_menu.addAction(self.bestalternativemove_arrow_action)
        
        board_menu.addSeparator()
        
        # Show Annotations Layer action (checkable to show toggle state)
        self.show_annotations_layer_action = QAction("Show Annotations Layer", self)
        self.show_annotations_layer_action.setShortcut(QKeySequence("Alt+L"))
        self.show_annotations_layer_action.setCheckable(True)
        self.show_annotations_layer_action.setChecked(True)  # Default to showing annotations
        self.show_annotations_layer_action.triggered.connect(self._on_show_annotations_layer_toggled)
        board_menu.addAction(self.show_annotations_layer_action)
        
        board_menu.addSeparator()
        
        # Path trajectory style submenu
        trajectory_style_menu = board_menu.addMenu("Path trajectory style")
        
        # Straight lines action (checkable)
        self.trajectory_style_straight_action = QAction("Straight", self)
        self.trajectory_style_straight_action.setCheckable(True)
        # Load initial state from user settings (fallback to config default)
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        user_settings = settings_service.get_settings()
        board_visibility = user_settings.get('board_visibility', {})
        use_straight_lines = board_visibility.get('use_straight_lines')
        if use_straight_lines is None:
            # Fallback to config default
            positional_plans_config = self.config.get('ui', {}).get('panels', {}).get('main', {}).get('board', {}).get('positional_plans', {})
            use_straight_lines = positional_plans_config.get('use_straight_lines', False)
        self.trajectory_style_straight_action.setChecked(use_straight_lines)
        self.trajectory_style_straight_action.triggered.connect(lambda: self._on_trajectory_style_selected(True))
        trajectory_style_menu.addAction(self.trajectory_style_straight_action)
        
        # Bezier curves action (checkable)
        self.trajectory_style_bezier_action = QAction("Bezier", self)
        self.trajectory_style_bezier_action.setCheckable(True)
        self.trajectory_style_bezier_action.setChecked(not use_straight_lines)
        self.trajectory_style_bezier_action.triggered.connect(lambda: self._on_trajectory_style_selected(False))
        trajectory_style_menu.addAction(self.trajectory_style_bezier_action)
        
        # Connect to board model state changes to update menu toggles
        board_model = self.controller.get_board_controller().get_board_model()
        board_model.flip_state_changed.connect(self._on_board_flip_state_changed)
        board_model.coordinates_visibility_changed.connect(self._on_coordinates_visibility_changed)
        board_model.turn_indicator_visibility_changed.connect(self._on_turn_indicator_visibility_changed)
        board_model.game_info_visibility_changed.connect(self._on_game_info_visibility_changed)
        board_model.playedmove_arrow_visibility_changed.connect(self._on_playedmove_arrow_visibility_changed)
        board_model.bestnextmove_arrow_visibility_changed.connect(self._on_bestnextmove_arrow_visibility_changed)
        board_model.bestalternativemove_arrow_visibility_changed.connect(self._on_bestalternativemove_arrow_visibility_changed)
        board_model.evaluation_bar_visibility_changed.connect(self._on_evaluation_bar_visibility_changed)
        board_model.material_widget_visibility_changed.connect(self._on_material_widget_visibility_changed)
        
        # Set initial toggle states
        self._update_rotate_action_state(board_model.is_flipped)
        self._update_coordinates_action_state(board_model.show_coordinates)
        self._update_turn_indicator_action_state(board_model.show_turn_indicator)
        self._update_game_info_action_state(board_model.show_game_info)
        self._update_playedmove_arrow_action_state(board_model.show_playedmove_arrow)
        self._update_bestnextmove_arrow_action_state(board_model.show_bestnextmove_arrow)
        self._update_pv2_arrow_action_state(board_model.show_pv2_arrow)
        self._update_pv3_arrow_action_state(board_model.show_pv3_arrow)
        self._update_bestalternativemove_arrow_action_state(board_model.show_bestalternativemove_arrow)
        self._update_evaluation_bar_action_state(board_model.show_evaluation_bar)
        self._update_material_widget_action_state(board_model.show_material_widget)
        
        # Connect positional heat-map model signals and set initial state
        positional_heatmap_model = self.controller.get_positional_heatmap_controller().get_model()
        positional_heatmap_model.visibility_changed.connect(self._on_positional_heatmap_visibility_changed)
        self._update_positional_heatmap_action_state(positional_heatmap_model.is_visible)
    
    def _setup_pgn_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the PGN menu."""
        pgn_menu = menu_bar.addMenu("PGN")
        
        # Show Metadata action (checkable to show toggle state)
        self.show_metadata_action = QAction("Show Metadata", self)
        self.show_metadata_action.setShortcut(QKeySequence("Ctrl+M"))
        self.show_metadata_action.setCheckable(True)
        self.show_metadata_action.setChecked(True)  # Default to showing metadata (will be loaded from settings)
        self.show_metadata_action.triggered.connect(self._on_show_metadata_toggled)
        pgn_menu.addAction(self.show_metadata_action)
        
        # Show Comments action
        self.show_comments_action = QAction("Show Comments", self)
        self.show_comments_action.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.show_comments_action.setCheckable(True)
        self.show_comments_action.setChecked(True)  # Default to showing comments (will be loaded from settings)
        self.show_comments_action.triggered.connect(self._on_show_comments_toggled)
        pgn_menu.addAction(self.show_comments_action)
        
        # Show Variations action
        self.show_variations_action = QAction("Show Variations", self)
        self.show_variations_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self.show_variations_action.setCheckable(True)
        self.show_variations_action.setChecked(True)  # Default to showing variations (will be loaded from settings)
        self.show_variations_action.triggered.connect(self._on_show_variations_toggled)
        pgn_menu.addAction(self.show_variations_action)
        
        # Show Non-Standard Tags action (tags like [%evp], [%mdl] in comments)
        self.show_non_standard_tags_action = QAction("Show Non-Standard Tags", self)
        self.show_non_standard_tags_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.show_non_standard_tags_action.setCheckable(True)
        self.show_non_standard_tags_action.setChecked(False)  # Default to hiding non-standard tags (will be loaded from settings)
        self.show_non_standard_tags_action.triggered.connect(self._on_show_non_standard_tags_toggled)
        pgn_menu.addAction(self.show_non_standard_tags_action)
        
        # Show Annotations action
        self.show_annotations_action = QAction("Show Annotations", self)
        self.show_annotations_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.show_annotations_action.setCheckable(True)
        self.show_annotations_action.setChecked(True)  # Default to showing annotations (will be loaded from settings)
        self.show_annotations_action.triggered.connect(self._on_show_annotations_toggled)
        pgn_menu.addAction(self.show_annotations_action)
        
        # Show Results action
        self.show_results_action = QAction("Show Results", self)
        self.show_results_action.setShortcut(QKeySequence("Ctrl+R"))
        self.show_results_action.setCheckable(True)
        self.show_results_action.setChecked(True)  # Default to showing results (will be loaded from settings)
        self.show_results_action.triggered.connect(self._on_show_results_toggled)
        pgn_menu.addAction(self.show_results_action)
        
        # Separator for cleaning actions
        pgn_menu.addSeparator()
        
        # Remove Comments action
        self.remove_comments_action = QAction("Remove Comments", self)
        self.remove_comments_action.triggered.connect(self._on_remove_comments_clicked)
        pgn_menu.addAction(self.remove_comments_action)
        
        # Remove Variations action
        self.remove_variations_action = QAction("Remove Variations", self)
        self.remove_variations_action.triggered.connect(self._on_remove_variations_clicked)
        pgn_menu.addAction(self.remove_variations_action)
        
        # Remove Non-Standard Tags action
        self.remove_non_standard_tags_action = QAction("Remove Non-Standard Tags", self)
        self.remove_non_standard_tags_action.triggered.connect(self._on_remove_non_standard_tags_clicked)
        pgn_menu.addAction(self.remove_non_standard_tags_action)
        
        # Remove Annotations action
        self.remove_annotations_action = QAction("Remove Annotations", self)
        self.remove_annotations_action.triggered.connect(self._on_remove_annotations_clicked)
        pgn_menu.addAction(self.remove_annotations_action)
    
    def _setup_moves_list_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Moves List menu."""
        moves_list_menu = menu_bar.addMenu("Moves List")
        
        # Get column profile model and controller
        profile_model = self.controller.get_column_profile_controller().get_profile_model()
        profile_controller = self.controller.get_column_profile_controller()
        
        # Store menu reference for updates
        self.moves_list_menu = moves_list_menu
        self.profile_model = profile_model
        self.profile_controller = profile_controller
        
        # Profile actions (will be populated dynamically)
        self.profile_actions: Dict[str, QAction] = {}
        
        # Column visibility actions
        self.column_actions: Dict[str, QAction] = {}
        
        # Connect to profile model signals
        profile_model.active_profile_changed.connect(self._on_active_profile_changed)
        profile_model.profile_added.connect(self._on_profile_added)
        profile_model.profile_removed.connect(self._on_profile_removed)
        profile_model.column_visibility_changed.connect(self._on_column_visibility_changed)
        
        # Initialize menu with current profiles and columns
        self._update_moves_list_menu()
    
    def _setup_game_analysis_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Game Analysis menu."""
        game_analysis_menu = menu_bar.addMenu("Game Analysis")
        
        # Start Game Analysis action
        self.start_game_analysis_action = QAction("Start Game Analysis", self)
        self.start_game_analysis_action.setShortcut(QKeySequence("Ctrl+G"))
        self.start_game_analysis_action.triggered.connect(self._start_game_analysis)
        game_analysis_menu.addAction(self.start_game_analysis_action)
        
        # Cancel Game Analysis action (initially disabled)
        self.cancel_game_analysis_action = QAction("Cancel Game Analysis", self)
        self.cancel_game_analysis_action.setShortcut(QKeySequence("Escape"))
        self.cancel_game_analysis_action.triggered.connect(self._cancel_game_analysis)
        self.cancel_game_analysis_action.setEnabled(False)
        game_analysis_menu.addAction(self.cancel_game_analysis_action)
        
        # Separator
        game_analysis_menu.addSeparator()
        
        # Bulk Analyze Database action
        self.bulk_analyze_database_action = QAction("Bulk Analyze Database...", self)
        self.bulk_analyze_database_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        self.bulk_analyze_database_action.triggered.connect(self._on_bulk_analyze_database)
        game_analysis_menu.addAction(self.bulk_analyze_database_action)
        
        # Separator
        game_analysis_menu.addSeparator()
        
        # Configure Classification Settings action
        self.configure_classification_action = QAction("Configure Classification Settings...", self)
        self.configure_classification_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        self.configure_classification_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        self.configure_classification_action.triggered.connect(self._open_classification_settings)
        game_analysis_menu.addAction(self.configure_classification_action)
        
        # Separator
        game_analysis_menu.addSeparator()
        
        # Normalized Evaluation Graph
        self.normalized_graph_action = QAction("Normalized Evaluation Graph", self)
        self.normalized_graph_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.normalized_graph_action.setCheckable(True)
        self.normalized_graph_action.setChecked(False)  # Default (will be loaded from settings)
        self.normalized_graph_action.triggered.connect(self._on_normalized_graph_toggled)
        game_analysis_menu.addAction(self.normalized_graph_action)
        
        # Separator
        game_analysis_menu.addSeparator()
        
        # Post-Game Brilliancy Refinement toggle
        self.post_game_brilliancy_refinement_action = QAction("Post‑Game Brilliancy Refinement", self)
        self.post_game_brilliancy_refinement_action.setCheckable(True)
        self.post_game_brilliancy_refinement_action.triggered.connect(self._on_post_game_brilliancy_refinement_toggled)
        game_analysis_menu.addAction(self.post_game_brilliancy_refinement_action)
        
        # Return to PLY 0 after analysis completes
        self.return_to_first_move_action = QAction("Return to PLY 0 after analysis completes", self)
        self.return_to_first_move_action.setCheckable(True)
        self.return_to_first_move_action.setChecked(False)  # Default (will be loaded from settings)
        self.return_to_first_move_action.triggered.connect(self._on_return_to_first_move_toggled)
        game_analysis_menu.addAction(self.return_to_first_move_action)
        
        # Switch to Moves List at the start of Analysis
        self.switch_to_moves_list_action = QAction("Switch to Moves List at the start of Analysis", self)
        self.switch_to_moves_list_action.setCheckable(True)
        self.switch_to_moves_list_action.setChecked(True)  # Default (will be loaded from settings)
        self.switch_to_moves_list_action.triggered.connect(self._on_switch_to_moves_list_toggled)
        game_analysis_menu.addAction(self.switch_to_moves_list_action)
        
        # Switch to Game Summary after Analysis
        self.switch_to_summary_action = QAction("Switch to Game Summary after Analysis", self)
        self.switch_to_summary_action.setCheckable(True)
        self.switch_to_summary_action.setChecked(False)  # Default (will be loaded from settings)
        self.switch_to_summary_action.triggered.connect(self._on_switch_to_summary_toggled)
        game_analysis_menu.addAction(self.switch_to_summary_action)
        
        # Separator
        game_analysis_menu.addSeparator()
        
        # Store Analysis results in PGN Tag toggle
        self.store_analysis_results_action = QAction("Store Analysis results in PGN Tag", self)
        self.store_analysis_results_action.setCheckable(True)
        self.store_analysis_results_action.triggered.connect(self._on_store_analysis_results_toggled)
        game_analysis_menu.addAction(self.store_analysis_results_action)
    
    def _setup_manual_analysis_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Manual Analysis menu."""
        manual_analysis_menu = menu_bar.addMenu("Manual Analysis")
        
        # Start/Stop Manual Analysis action (checkable to show toggle state)
        self.start_manual_analysis_action = QAction("Start Manual Analysis", self)
        self.start_manual_analysis_action.setShortcut(QKeySequence("Alt+M"))
        self.start_manual_analysis_action.setCheckable(True)
        self.start_manual_analysis_action.setChecked(False)
        self.start_manual_analysis_action.triggered.connect(self._on_start_manual_analysis_toggled)
        manual_analysis_menu.addAction(self.start_manual_analysis_action)
        
        manual_analysis_menu.addSeparator()
        
        # Add PV Line action
        self.add_pv_line_action = QAction("Add PV Line", self)
        self.add_pv_line_action.setShortcut(QKeySequence("Alt+N"))
        self.add_pv_line_action.triggered.connect(self._on_add_pv_line)
        manual_analysis_menu.addAction(self.add_pv_line_action)
        
        # Remove PV Line action
        self.remove_pv_line_action = QAction("Remove PV Line", self)
        self.remove_pv_line_action.setShortcut(QKeySequence("Alt+R"))
        self.remove_pv_line_action.triggered.connect(self._on_remove_pv_line)
        manual_analysis_menu.addAction(self.remove_pv_line_action)
        
        # Separator
        manual_analysis_menu.addSeparator()
        
        # Enable miniature preview action (checkable toggle)
        self.enable_miniature_preview_action = QAction("Enable miniature preview", self)
        self.enable_miniature_preview_action.setCheckable(True)
        self.enable_miniature_preview_action.setChecked(True)  # Default (will be loaded from settings)
        self.enable_miniature_preview_action.triggered.connect(self._on_enable_miniature_preview_toggled)
        manual_analysis_menu.addAction(self.enable_miniature_preview_action)
        
        # Set miniature preview scale factor menu (submenu)
        self.miniature_preview_scale_menu = manual_analysis_menu.addMenu("Set miniature preview scale factor")
        # Apply menu styling to submenu (same as other submenus)
        self._apply_menu_styling(self.miniature_preview_scale_menu)
        scale_factors = [1.0, 1.25, 1.5, 1.75, 2.0]
        self.miniature_preview_scale_actions = {}
        for scale in scale_factors:
            action = QAction(f"{scale}x", self)
            action.setCheckable(True)
            action.setData(scale)
            action.triggered.connect(lambda checked, s=scale: self._on_miniature_preview_scale_factor_selected(s))
            self.miniature_preview_scale_menu.addAction(action)
            self.miniature_preview_scale_actions[scale] = action
        
        # Separator
        manual_analysis_menu.addSeparator()
        
        # Explore PV1 Positional Plans action (checkable toggle)
        self.explore_pv1_plans_action = QAction("Explore PV1 Positional Plans", self)
        self.explore_pv1_plans_action.setCheckable(True)
        self.explore_pv1_plans_action.setChecked(False)
        self.explore_pv1_plans_action.triggered.connect(self._on_explore_pv1_plans_toggled)
        manual_analysis_menu.addAction(self.explore_pv1_plans_action)
        
        # Explore PV2 Positional Plans action (checkable toggle)
        self.explore_pv2_plans_action = QAction("Explore PV2 Positional Plans", self)
        self.explore_pv2_plans_action.setCheckable(True)
        self.explore_pv2_plans_action.setChecked(False)
        self.explore_pv2_plans_action.triggered.connect(self._on_explore_pv2_plans_toggled)
        manual_analysis_menu.addAction(self.explore_pv2_plans_action)
        
        # Explore PV3 Positional Plans action (checkable toggle)
        self.explore_pv3_plans_action = QAction("Explore PV3 Positional Plans", self)
        self.explore_pv3_plans_action.setCheckable(True)
        self.explore_pv3_plans_action.setChecked(False)
        self.explore_pv3_plans_action.triggered.connect(self._on_explore_pv3_plans_toggled)
        manual_analysis_menu.addAction(self.explore_pv3_plans_action)
        
        #manual_analysis_menu.addSeparator()
        
        # Max number of pieces to explore submenu
        max_pieces_menu = manual_analysis_menu.addMenu("Max number of pieces to explore")
        
        # Load initial state from user settings (fallback to defaults)
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        user_settings = settings_service.get_settings()
        manual_analysis_settings = user_settings.get('manual_analysis', {})
        max_pieces = manual_analysis_settings.get('max_pieces_to_explore', 1)
        
        # Max pieces 1 action (checkable)
        self.max_pieces_1_action = QAction("1", self)
        self.max_pieces_1_action.setCheckable(True)
        self.max_pieces_1_action.setChecked(max_pieces == 1)
        self.max_pieces_1_action.triggered.connect(lambda: self._on_max_pieces_selected(1))
        max_pieces_menu.addAction(self.max_pieces_1_action)
        
        # Max pieces 2 action (checkable)
        self.max_pieces_2_action = QAction("2", self)
        self.max_pieces_2_action.setCheckable(True)
        self.max_pieces_2_action.setChecked(max_pieces == 2)
        self.max_pieces_2_action.triggered.connect(lambda: self._on_max_pieces_selected(2))
        max_pieces_menu.addAction(self.max_pieces_2_action)
        
        # Max pieces 3 action (checkable)
        self.max_pieces_3_action = QAction("3", self)
        self.max_pieces_3_action.setCheckable(True)
        self.max_pieces_3_action.setChecked(max_pieces == 3)
        self.max_pieces_3_action.triggered.connect(lambda: self._on_max_pieces_selected(3))
        max_pieces_menu.addAction(self.max_pieces_3_action)
        
        #manual_analysis_menu.addSeparator()
        
        # Max exploration depth submenu
        max_depth_menu = manual_analysis_menu.addMenu("Max Exploration depth")
        
        # Load initial state from user settings (fallback to defaults)
        max_depth = manual_analysis_settings.get('max_exploration_depth', 2)
        
        # Max depth 2 action (checkable)
        self.max_depth_2_action = QAction("2", self)
        self.max_depth_2_action.setCheckable(True)
        self.max_depth_2_action.setChecked(max_depth == 2)
        self.max_depth_2_action.triggered.connect(lambda: self._on_max_exploration_depth_selected(2))
        max_depth_menu.addAction(self.max_depth_2_action)
        
        # Max depth 3 action (checkable)
        self.max_depth_3_action = QAction("3", self)
        self.max_depth_3_action.setCheckable(True)
        self.max_depth_3_action.setChecked(max_depth == 3)
        self.max_depth_3_action.triggered.connect(lambda: self._on_max_exploration_depth_selected(3))
        max_depth_menu.addAction(self.max_depth_3_action)
        
        # Max depth 4 action (checkable)
        self.max_depth_4_action = QAction("4", self)
        self.max_depth_4_action.setCheckable(True)
        self.max_depth_4_action.setChecked(max_depth == 4)
        self.max_depth_4_action.triggered.connect(lambda: self._on_max_exploration_depth_selected(4))
        max_depth_menu.addAction(self.max_depth_4_action)
        
        #manual_analysis_menu.addSeparator()
        
        # Hide other arrows during plan exploration action (checkable toggle)
        # Load initial state from user settings (fallback to default)
        board_visibility = user_settings.get('board_visibility', {})
        hide_other_arrows = board_visibility.get('hide_other_arrows_during_plan_exploration', False)
        
        self.hide_other_arrows_during_plan_exploration_action = QAction("Hide other arrows during plan exploration", self)
        self.hide_other_arrows_during_plan_exploration_action.setCheckable(True)
        self.hide_other_arrows_during_plan_exploration_action.setChecked(hide_other_arrows)
        self.hide_other_arrows_during_plan_exploration_action.triggered.connect(self._on_hide_other_arrows_during_plan_exploration_toggled)
        manual_analysis_menu.addAction(self.hide_other_arrows_during_plan_exploration_action)
        
        # Store menu reference
        self.manual_analysis_menu = manual_analysis_menu
        
        # Connect to manual analysis model signals
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        manual_analysis_model = manual_analysis_controller.get_analysis_model()
        manual_analysis_model.is_analyzing_changed.connect(self._on_manual_analysis_state_changed)
        manual_analysis_model.lines_changed.connect(self._on_manual_analysis_lines_changed)
        
        # Set initial action states
        self._update_manual_analysis_action_states(manual_analysis_model.is_analyzing, manual_analysis_model.multipv)
    
    def _setup_annotations_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Annotations menu."""
        annotations_menu = menu_bar.addMenu("Annotations")
        
        clear_all_annotations_action = QAction("Clear all Annotations for current game", self)
        clear_all_annotations_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        clear_all_annotations_action.triggered.connect(self._clear_all_annotations_for_game)
        annotations_menu.addAction(clear_all_annotations_action)
        
        clear_move_annotations_action = QAction("Clear all Annotations for current move", self)
        clear_move_annotations_action.setShortcut(QKeySequence("Ctrl+Alt+D"))
        clear_move_annotations_action.triggered.connect(self._clear_annotations_for_current_move)
        annotations_menu.addAction(clear_move_annotations_action)
        
        save_annotations_action = QAction("Save Annotations to current game", self)
        save_annotations_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
        save_annotations_action.triggered.connect(self._save_annotations_to_current_game)
        annotations_menu.addAction(save_annotations_action)
        
        annotations_menu.addSeparator()
        
        setup_preferences_action = QAction("Setup Preferences...", self)
        setup_preferences_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        setup_preferences_action.triggered.connect(self._show_annotation_preferences)
        annotations_menu.addAction(setup_preferences_action)
    
    def _setup_engines_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Engines menu."""
        engines_menu = menu_bar.addMenu("Engines")
        
        # Add Engine action
        add_engine_action = QAction("Add Engine...", self)
        add_engine_action.setShortcut(QKeySequence("Ctrl+E"))
        add_engine_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        add_engine_action.triggered.connect(self._add_engine)
        engines_menu.addAction(add_engine_action)
        
        engines_menu.addSeparator()
        
        # Engine list submenus (will be populated dynamically)
        self.engine_submenus: Dict[str, QMenu] = {}
        self.no_engines_action: Optional[QAction] = None
        
        # Connect to engine model signals
        engine_model = self.controller.get_engine_controller().get_engine_model()
        engine_model.engine_added.connect(self._on_engine_added)
        engine_model.engine_removed.connect(self._on_engine_removed)
        engine_model.engines_changed.connect(self._update_engines_menu)
        engine_model.assignment_changed.connect(self._update_engines_menu)
        
        # Store menu reference for updates
        self.engines_menu = engines_menu
        self.engine_model = engine_model
        
        # Initialize menu with current engines
        self._update_engines_menu()
    
    def _setup_ai_summary_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the AI Summary menu."""
        ai_summary_menu = menu_bar.addMenu("AI Summary")
        
        # AI Model Settings action (top of menu)
        ai_model_settings_action = QAction("AI Model Settings...", self)
        ai_model_settings_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        ai_model_settings_action.triggered.connect(self._show_ai_model_settings)
        ai_summary_menu.addAction(ai_model_settings_action)
        
        ai_summary_menu.addSeparator()
        
        # Provider toggles (mutually exclusive)
        self.ai_summary_use_openai_action = QAction("Use OpenAI Models", self)
        self.ai_summary_use_openai_action.setCheckable(True)
        self.ai_summary_use_openai_action.triggered.connect(lambda: self._on_ai_summary_provider_selected("openai"))
        ai_summary_menu.addAction(self.ai_summary_use_openai_action)
        
        self.ai_summary_use_anthropic_action = QAction("Use Anthropic Models", self)
        self.ai_summary_use_anthropic_action.setCheckable(True)
        self.ai_summary_use_anthropic_action.triggered.connect(lambda: self._on_ai_summary_provider_selected("anthropic"))
        ai_summary_menu.addAction(self.ai_summary_use_anthropic_action)
        
        ai_summary_menu.addSeparator()
        
        # Include Analysis Data in Pre-Prompt toggle
        self.ai_summary_include_analysis_action = QAction("Include Game Analysis Data in Pre-Prompt", self)
        self.ai_summary_include_analysis_action.setCheckable(True)
        self.ai_summary_include_analysis_action.triggered.connect(self._on_ai_summary_include_analysis_toggled)
        ai_summary_menu.addAction(self.ai_summary_include_analysis_action)
        
        self.ai_summary_include_metadata_action = QAction("Include PGN Metadata tags in Pre-Prompt", self)
        self.ai_summary_include_metadata_action.setCheckable(True)
        self.ai_summary_include_metadata_action.triggered.connect(self._on_ai_summary_include_metadata_toggled)
        ai_summary_menu.addAction(self.ai_summary_include_metadata_action)
    
    def _setup_view_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the View menu."""
        view_menu = menu_bar.addMenu("View")
        
        # Moves List action
        self.view_moves_list_action = QAction("Moves List", self)
        self.view_moves_list_action.setShortcut(QKeySequence("F1"))
        self.view_moves_list_action.setCheckable(True)
        self.view_moves_list_action.triggered.connect(lambda: self._switch_detail_tab(0))
        view_menu.addAction(self.view_moves_list_action)
        
        # Metadata action
        self.view_metadata_action = QAction("Metadata", self)
        self.view_metadata_action.setShortcut(QKeySequence("F2"))
        self.view_metadata_action.setCheckable(True)
        self.view_metadata_action.triggered.connect(lambda: self._switch_detail_tab(1))
        view_menu.addAction(self.view_metadata_action)
        
        # Manual Analysis action
        self.view_manual_analysis_action = QAction("Manual Analysis", self)
        self.view_manual_analysis_action.setShortcut(QKeySequence("F3"))
        self.view_manual_analysis_action.setCheckable(True)
        self.view_manual_analysis_action.triggered.connect(lambda: self._switch_detail_tab(2))
        view_menu.addAction(self.view_manual_analysis_action)
        
        # Game Summary action
        self.view_game_summary_action = QAction("Game Summary", self)
        self.view_game_summary_action.setShortcut(QKeySequence("F4"))
        self.view_game_summary_action.setCheckable(True)
        self.view_game_summary_action.triggered.connect(lambda: self._switch_detail_tab(3))
        view_menu.addAction(self.view_game_summary_action)
        
        # Player Stats action
        self.view_player_stats_action = QAction("Player Stats", self)
        self.view_player_stats_action.setShortcut(QKeySequence("F5"))
        self.view_player_stats_action.setCheckable(True)
        self.view_player_stats_action.triggered.connect(lambda: self._switch_detail_tab(4))
        view_menu.addAction(self.view_player_stats_action)
        
        # Annotations action
        self.view_annotations_action = QAction("Annotations", self)
        self.view_annotations_action.setShortcut(QKeySequence("F6"))
        self.view_annotations_action.setCheckable(True)
        self.view_annotations_action.triggered.connect(lambda: self._switch_detail_tab(5))
        view_menu.addAction(self.view_annotations_action)
        
        # AI Summary action
        self.view_ai_summary_action = QAction("AI Summary", self)
        self.view_ai_summary_action.setShortcut(QKeySequence("F7"))
        self.view_ai_summary_action.setCheckable(True)
        self.view_ai_summary_action.triggered.connect(lambda: self._switch_detail_tab(6))
        view_menu.addAction(self.view_ai_summary_action)
        
        # Separator
        view_menu.addSeparator()
        
        # Hide Database Panel action
        self.view_hide_database_panel_action = QAction("Hide Database Panel", self)
        self.view_hide_database_panel_action.setCheckable(True)
        self.view_hide_database_panel_action.setChecked(False)  # Initial state (panel is visible)
        self.view_hide_database_panel_action.triggered.connect(self._toggle_database_panel)
        view_menu.addAction(self.view_hide_database_panel_action)
        
        # Store view menu actions for later connection
        self.view_menu_actions = [
            self.view_moves_list_action,
            self.view_metadata_action,
            self.view_manual_analysis_action,
            self.view_game_summary_action,
            self.view_player_stats_action,
            self.view_annotations_action,
            self.view_ai_summary_action
        ]
    
    def _setup_help_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Help menu."""
        help_menu = menu_bar.addMenu("Help")
        
        # Open Manual action
        open_manual_action = QAction("Open Manual", self)
        open_manual_action.triggered.connect(self._open_manual)
        help_menu.addAction(open_manual_action)
        
        help_menu.addSeparator()
        
        # Check for Updates action
        check_updates_action = QAction("Check for Updates...", self)
        check_updates_action.triggered.connect(self._check_for_updates)
        help_menu.addAction(check_updates_action)
        
        help_menu.addSeparator()
        
        # About action
        about_action = QAction("About...", self)
        # Set menu role to NoRole to prevent macOS from moving it to the application menu
        about_action.setMenuRole(QAction.MenuRole.NoRole)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _setup_debug_menu(self, menu_bar: QMenuBar) -> None:
        """Setup the Debug menu (only if enabled in config)."""
        debug_config = self.config.get('debug', {})
        show_debug_menu = debug_config.get('show_debug_menu', False)
        if show_debug_menu:
            debug_menu = menu_bar.addMenu("Debug")
            
            # Copy PGN HTML action
            debug_copy_pgn_html_action = QAction("Copy PGN HTML", self)
            debug_copy_pgn_html_action.triggered.connect(self._debug_copy_pgn_html)
            debug_menu.addAction(debug_copy_pgn_html_action)
            
            # Copy Deserialize Analysis Tag action
            debug_copy_deserialize_analysis_action = QAction("Copy Deserialize Analysis Tag", self)
            debug_copy_deserialize_analysis_action.triggered.connect(self._debug_copy_deserialize_analysis_tag)
            debug_menu.addAction(debug_copy_deserialize_analysis_action)
            
            # Copy Deserialize Annotation Tag action
            debug_copy_deserialize_annotation_action = QAction("Copy Deserialize Annotation Tag", self)
            debug_copy_deserialize_annotation_action.triggered.connect(self._debug_copy_deserialize_annotation_tag)
            debug_menu.addAction(debug_copy_deserialize_annotation_action)
            
            # Copy Game Highlights HTML action
            debug_copy_highlights_html_action = QAction("Copy Game Highlights HTML", self)
            debug_copy_highlights_html_action.triggered.connect(self._debug_copy_game_highlights_html)
            debug_menu.addAction(debug_copy_highlights_html_action)
            
            # Copy Game Highlights JSON action
            debug_copy_highlights_json_action = QAction("Copy Game Highlights JSON", self)
            debug_copy_highlights_json_action.triggered.connect(self._debug_copy_game_highlights_json)
            debug_menu.addAction(debug_copy_highlights_json_action)
            
            debug_menu.addSeparator()
            
            # Create Highlight Rule Test Data action
            debug_create_highlight_test_data_action = QAction("Create Highlight Rule Test Data", self)
            debug_create_highlight_test_data_action.triggered.connect(self._debug_create_highlight_rule_test_data)
            debug_menu.addAction(debug_create_highlight_test_data_action)
            
            # Separator
            debug_menu.addSeparator()
            
            # Debug UCI Lifecycle toggle
            self.debug_uci_lifecycle_action = QAction("Debug UCI Lifecycle", self)
            self.debug_uci_lifecycle_action.setCheckable(True)
            self.debug_uci_lifecycle_action.setChecked(self._uci_debug_lifecycle)
            self.debug_uci_lifecycle_action.triggered.connect(self._toggle_uci_debug_lifecycle)
            debug_menu.addAction(self.debug_uci_lifecycle_action)
            
            # Debug UCI Outbound toggle
            self.debug_uci_outbound_action = QAction("Debug UCI Outbound", self)
            self.debug_uci_outbound_action.setCheckable(True)
            self.debug_uci_outbound_action.setChecked(self._uci_debug_outbound)
            self.debug_uci_outbound_action.triggered.connect(self._toggle_uci_debug_outbound)
            debug_menu.addAction(self.debug_uci_outbound_action)
            
            # Debug UCI Inbound toggle
            self.debug_uci_inbound_action = QAction("Debug UCI Inbound", self)
            self.debug_uci_inbound_action.setCheckable(True)
            self.debug_uci_inbound_action.setChecked(self._uci_debug_inbound)
            self.debug_uci_inbound_action.triggered.connect(self._toggle_uci_debug_inbound)
            debug_menu.addAction(self.debug_uci_inbound_action)
            
            # Separator
            debug_menu.addSeparator()
            
            # Debug AI Outbound toggle
            self.debug_ai_outbound_action = QAction("Debug AI Outbound", self)
            self.debug_ai_outbound_action.setCheckable(True)
            self.debug_ai_outbound_action.setChecked(self._ai_debug_outbound)
            self.debug_ai_outbound_action.triggered.connect(self._toggle_ai_debug_outbound)
            debug_menu.addAction(self.debug_ai_outbound_action)
            
            # Debug AI Inbound toggle
            self.debug_ai_inbound_action = QAction("Debug AI Inbound", self)
            self.debug_ai_inbound_action.setCheckable(True)
            self.debug_ai_inbound_action.setChecked(self._ai_debug_inbound)
            self.debug_ai_inbound_action.triggered.connect(self._toggle_ai_debug_inbound)
            debug_menu.addAction(self.debug_ai_inbound_action)
            
            # Separator
            debug_menu.addSeparator()
            
            # Toggle Game Analysis State (for debugging)
            self.debug_toggle_game_analysis_action = QAction("Toggle Game Analysis State", self)
            self.debug_toggle_game_analysis_action.setCheckable(True)
            # Get initial state from game model
            game_model = self.controller.get_game_controller().get_game_model()
            self.debug_toggle_game_analysis_action.setChecked(game_model.is_game_analyzed)
            self.debug_toggle_game_analysis_action.triggered.connect(self._toggle_game_analysis_state)
            debug_menu.addAction(self.debug_toggle_game_analysis_action)
            
            # Connect to game model signal to update menu toggle state
            game_model.is_game_analyzed_changed.connect(self._on_game_analysis_state_changed)
    
    def _apply_menu_bar_styling(self, menu_bar: QMenuBar) -> None:
        """Apply styling to the menu bar based on configuration.
        
        Args:
            menu_bar: The QMenuBar instance to style.
        """
        ui_config = self.config.get('ui', {})
        menu_config = ui_config.get('menu', {})
        
        # Get font settings
        font_family = resolve_font_family(menu_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(menu_config.get('font_size', 10))
        
        # Get color settings
        colors_config = menu_config.get('colors', {})
        normal = colors_config.get('normal', {})
        hover = colors_config.get('hover', {})
        
        # Normal state colors
        norm_bg = normal.get('background', [45, 45, 50])
        norm_text = normal.get('text', [200, 200, 200])
        
        # Hover state colors
        hover_bg = hover.get('background', [55, 55, 60])
        hover_text = hover.get('text', [230, 230, 230])
        
        # Get spacing and padding from config
        menu_spacing = menu_config.get('spacing', 4)
        menu_bar_config = menu_config.get('menu_bar', {})
        menu_bar_item_padding = menu_bar_config.get('item_padding', [4, 8])
        
        menu_config_obj = menu_config.get('menu', {})
        menu_border_width = menu_config_obj.get('border_width', 1)
        menu_border_color = menu_config_obj.get('border_color', [60, 60, 65])
        menu_item_padding = menu_config_obj.get('item_padding', [4, 20, 4, 8])
        
        separator_config = menu_config.get('separator', {})
        separator_height = separator_config.get('height', 1)
        separator_bg_color = separator_config.get('background_color', [60, 60, 65])
        separator_margin = separator_config.get('margin', [2, 4])
        
        # Create stylesheet
        stylesheet = f"""
            QMenuBar {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                font-family: "{font_family}";
                font-size: {font_size}pt;
                spacing: {menu_spacing}px;
            }}
            
            QMenuBar::item {{
                background-color: transparent;
                padding: {menu_bar_item_padding[0]}px {menu_bar_item_padding[1]}px;
            }}
            
            QMenuBar::item:selected {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            
            QMenuBar::item:pressed {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
            }}
            
            QMenu {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: {menu_border_width}px solid rgb({menu_border_color[0]}, {menu_border_color[1]}, {menu_border_color[2]});
                font-family: "{font_family}";
                font-size: {font_size}pt;
            }}
            
            QMenu::item {{
                padding: {menu_item_padding[0]}px {menu_item_padding[1]}px {menu_item_padding[2]}px {menu_item_padding[3]}px;
            }}
            
            QMenu::item:selected {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            
            QMenu::separator {{
                height: {separator_height}px;
                background-color: rgb({separator_bg_color[0]}, {separator_bg_color[1]}, {separator_bg_color[2]});
                margin: {separator_margin[0]}px {separator_margin[1]}px;
            }}
        """
        
        menu_bar.setStyleSheet(stylesheet)
    
    def _apply_menu_styling(self, menu: QMenu) -> None:
        """Apply styling to a QMenu (used for submenus).
        
        Args:
            menu: The QMenu instance to style.
        """
        ui_config = self.config.get('ui', {})
        menu_config = ui_config.get('menu', {})
        
        # Get font settings
        font_family = resolve_font_family(menu_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(menu_config.get('font_size', 10))
        
        # Get color settings
        colors_config = menu_config.get('colors', {})
        normal = colors_config.get('normal', {})
        hover = colors_config.get('hover', {})
        
        # Normal state colors
        norm_bg = normal.get('background', [45, 45, 50])
        norm_text = normal.get('text', [200, 200, 200])
        
        # Hover state colors
        hover_bg = hover.get('background', [55, 55, 60])
        hover_text = hover.get('text', [230, 230, 230])
        
        menu_config_obj = menu_config.get('menu', {})
        menu_border_width = menu_config_obj.get('border_width', 1)
        menu_border_color = menu_config_obj.get('border_color', [60, 60, 65])
        menu_item_padding = menu_config_obj.get('item_padding', [4, 20, 4, 8])
        
        separator_config = menu_config.get('separator', {})
        separator_height = separator_config.get('height', 1)
        separator_bg_color = separator_config.get('background_color', [60, 60, 65])
        separator_margin = separator_config.get('margin', [2, 4])
        
        # Create stylesheet for QMenu (same as in menu bar styling)
        stylesheet = f"""
            QMenu {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: {menu_border_width}px solid rgb({menu_border_color[0]}, {menu_border_color[1]}, {menu_border_color[2]});
                font-family: "{font_family}";
                font-size: {font_size}pt;
            }}
            QMenu::item {{
                padding: {menu_item_padding[0]}px {menu_item_padding[1]}px {menu_item_padding[2]}px {menu_item_padding[3]}px;
            }}
            QMenu::item:selected {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            QMenu::separator {{
                height: {separator_height}px;
                background-color: rgb({separator_bg_color[0]}, {separator_bg_color[1]}, {separator_bg_color[2]});
                margin: {separator_margin[0]}px {separator_margin[1]}px;
            }}
        """
        
        menu.setStyleSheet(stylesheet)
    
    def _require_active_database(self) -> Optional[DatabaseModel]:
        """Helper method to validate and return active database.
        
        Shows error dialog if no active database is available.
        
        Returns:
            DatabaseModel if active database exists, None otherwise.Kjjjjjlllllkllljlkjlljlkjljlllkjllkjklkkljllljkkl
        """
        database_controller = self.controller.get_database_controller()
        active_database = database_controller.get_active_database()
        
        if not active_database:
            MessageDialog.show_warning(
                self.config,
                "No Database",
                "No active database selected. Please open or select a database first.",
                self
            )
            return None
        
        return active_database
    
    def _clear_clipboard_database(self) -> None:
        """Clear the clipboard database and reset active game."""
        self.controller.get_database_controller().clear_database()
        # Reset active game to None
        self.controller.get_game_controller().set_active_game(None)
        self.controller.set_status("Clipboard database cleared")
    
    def _open_pgn_database(self) -> None:
        """Open one or more PGN databases from file(s)."""
        # Open file dialog to select PGN file(s) - supports multiple selection
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open PGN Database(s)",
            "",
            "PGN Files (*.pgn);;All Files (*)"
        )
        
        if not file_paths:
            # User cancelled
            return
        
        database_controller = self.controller.get_database_controller()
        
        # Handle single file (backward compatible behavior)
        if len(file_paths) == 1:
            file_path = file_paths[0]
            success, message, first_game = database_controller.open_pgn_database(file_path)
            
            # Update UI based on result
            if success:
                # Update save menu state
                self._update_save_menu_state()
                # Update close menu state
                self._update_close_menu_state()
                
                # Set first game as active if available
                if first_game:
                    self.controller.get_game_controller().set_active_game(first_game)
            
            # Set status message
            self.controller.set_status(message)
            return
        
        # Handle multiple files - delegate to controller
        opened_count, skipped_count, failed_count, messages, last_successful_database, last_first_game = database_controller.open_pgn_databases(file_paths)
        
        # Update save menu state if any databases were opened
        if opened_count > 0:
            self._update_save_menu_state()
            # Update close menu state
            self._update_close_menu_state()
            
            # Set last successfully opened database as active
            if last_successful_database:
                database_controller.set_active_database(last_successful_database)
            
            # Set first game from last opened database as active if available
            if last_first_game:
                self.controller.get_game_controller().set_active_game(last_first_game)
        
        # Create aggregated status message
        status_parts = []
        if opened_count > 0:
            status_parts.append(f"Opened {opened_count} database(s)")
        if skipped_count > 0:
            status_parts.append(f"Skipped {skipped_count} (already open)")
        if failed_count > 0:
            status_parts.append(f"Failed {failed_count}")
        
        if status_parts:
            status_message = ", ".join(status_parts)
        else:
            status_message = "No databases opened"
        
        self.controller.set_status(status_message)
    
    def _close_pgn_database(self) -> None:
        """Close the currently selected PGN database tab."""
        # Close the active PGN database via controller (handles business logic)
        database_controller = self.controller.get_database_controller()
        closed = database_controller.close_active_pgn_database()
        
        if closed:
            # Clear active game if it was from the closed tab
            # (The game might still be active, but we clear it for safety)
            self.controller.get_game_controller().set_active_game(None)
            self.controller.set_status("PGN database closed")
            # Update save menu state
            self._update_save_menu_state()
            # Update close menu state
            self._update_close_menu_state()
        else:
            self.controller.set_status("No PGN database tab selected to close")
    
    def _close_all_pgn_databases(self) -> None:
        """Close all PGN databases except clipboard and search results."""
        database_controller = self.controller.get_database_controller()
        closed_count = database_controller.close_all_pgn_databases()
        
        if closed_count > 0:
            # Clear active game if it was from a closed tab
            self.controller.get_game_controller().set_active_game(None)
            if closed_count == 1:
                self.controller.set_status("1 database closed")
            else:
                self.controller.set_status(f"{closed_count} databases closed")
            # Update save menu state
            self._update_save_menu_state()
            # Update close menu state
            self._update_close_menu_state()
        else:
            self.controller.set_status("No databases to close")
    
    def _on_database_tab_changed(self, index_or_database) -> None:
        """Handle database tab change to update save menu state and close search results menu state.
        
        Args:
            index_or_database: Index of the newly selected tab (from tab widget)
                             or DatabaseModel instance (from panel model signal).
        """
        self._update_save_menu_state()
        self._update_close_menu_state()
        
        # Update close search results menu state
        if hasattr(self, 'close_search_results_action'):
            has_search_results = self._find_search_results_tab() is not None
            self.close_search_results_action.setEnabled(has_search_results)
    
    def _connect_database_tab_changes(self) -> None:
        """Connect to database panel tab changes after UI is set up."""
        if hasattr(self, 'database_panel') and hasattr(self.database_panel, 'tab_widget'):
            # Connect to tab widget for UI-specific updates
            self.database_panel.tab_widget.currentChanged.connect(self._on_database_tab_changed)
            # Also connect to panel model for consistency
            database_controller = self.controller.get_database_controller()
            panel_model = database_controller.get_panel_model()
            panel_model.active_database_changed.connect(self._on_database_tab_changed)
            # Initialize save and close menu state
            self._update_save_menu_state()
            self._update_close_menu_state()
    
    def _can_save_or_close_database(self) -> bool:
        """Check if the active database can be saved or closed.
        
        Returns:
            True if the active database can be saved/closed, False otherwise.
            Returns False for Clipboard or Search Results databases.
        """
        if not hasattr(self, 'database_panel'):
            return False
        
        # Get active database info
        database_info = self.database_panel.get_active_database_info()
        
        # Cannot save/close if no database info
        if not database_info:
            return False
        
        identifier = database_info.get('identifier')
        file_path = database_info.get('file_path')
        
        # Cannot save/close Clipboard (no file_path) or Search Results
        if identifier == 'search_results' or file_path is None:
            return False
        
        return True
    
    def _update_save_menu_state(self) -> None:
        """Update the enabled state of the Save PGN Database menu item."""
        if not hasattr(self, 'save_pgn_database_action'):
            return
        
        can_save = self._can_save_or_close_database()
        self.save_pgn_database_action.setEnabled(can_save)
    
    def _update_close_menu_state(self) -> None:
        """Update the enabled state of the Close PGN Database and Close All PGN Databases menu items."""
        if not hasattr(self, 'close_pgn_database_action'):
            return
        
        can_close = self._can_save_or_close_database()
        self.close_pgn_database_action.setEnabled(can_close)
        
        # Update Close All PGN Databases action
        if hasattr(self, 'close_all_databases_action'):
            # Check if there are any file-based databases to close
            database_controller = self.controller.get_database_controller()
            panel_model = database_controller.get_panel_model()
            all_databases = panel_model.get_all_databases()
            
            # Count file-based databases (exclude clipboard and search_results)
            file_based_count = sum(
                1 for identifier in all_databases.keys()
                if identifier != "clipboard" and identifier != "search_results"
            )
            
            self.close_all_databases_action.setEnabled(file_based_count > 0)
    
    def _save_pgn_database(self) -> None:
        """Save the current PGN database to its existing file."""
        if not hasattr(self, 'database_panel'):
            return
        
        # Get active database info
        database_info = self.database_panel.get_active_database_info()
        if not database_info or database_info.get('file_path') is None:
            # Clipboard database or no file path - should not happen if menu is disabled
            self.controller.set_status("Cannot save: No file associated with current database")
            return
        
        file_path = database_info['file_path']
        model = database_info['model']
        
        # Save to existing file using controller
        database_controller = self.controller.get_database_controller()
        success, message = database_controller.save_pgn_to_file(model, file_path)
        self.controller.set_status(message)
    
    def _save_pgn_database_as(self) -> None:
        """Save the current PGN database to a new file."""
        if not hasattr(self, 'database_panel'):
            return
        
        # Get active database info
        database_info = self.database_panel.get_active_database_info()
        if not database_info:
            self.controller.set_status("No active database selected")
            return
        
        model = database_info['model']
        identifier = database_info.get('identifier')
        current_file_path = database_info.get('file_path')
        
        # Determine default path
        if identifier == 'search_results':
            # Prefill with "Search Results DATETIME.pgn"
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_path = f"Search Results {timestamp}.pgn"
        else:
            default_path = current_file_path if current_file_path else ""
        
        # Open file dialog to choose save location (UI concern - stays in view)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PGN Database As...",
            default_path,
            "PGN Files (*.pgn);;All Files (*)"
        )
        
        if not file_path:
            # User cancelled
            return
        
        # Delegate to controller for business logic
        database_controller = self.controller.get_database_controller()
        success, message = database_controller.save_pgn_database_as(model, file_path)
        self.controller.set_status(message)
        
        if success:
            # If this was a search results database, close the search results tab
            if identifier == 'search_results':
                self._close_search_results_after_save()
            else:
                # The controller creates a new database entry and sets it as active
                # The view will automatically update via signal-driven updates from the model
                # Update save menu state
                self._update_save_menu_state()
    
    def _bulk_replace(self) -> None:
        """Open bulk replace dialog."""
        if not hasattr(self, 'database_panel'):
            return
        
        active_database = self._require_active_database()
        if not active_database:
            return
        
        # Get selected game indices from database panel (if any)
        selected_game_indices = []
        active_info = self.database_panel.get_active_database_info()
        if active_info and active_info.get('model') == active_database:
            selected_game_indices = self.database_panel.get_selected_game_indices()
        
        # Get bulk replace controller
        bulk_replace_controller = self.controller.get_bulk_replace_controller()
        
        # Import and show dialog
        from app.views.bulk_replace_dialog import BulkReplaceDialog
        dialog = BulkReplaceDialog(
            self.config,
            bulk_replace_controller,
            active_database,
            selected_game_indices=selected_game_indices if selected_game_indices else None,
            parent=self
        )
        dialog.exec()
    
    def _bulk_tag(self) -> None:
        """Open bulk tag dialog."""
        if not hasattr(self, 'database_panel'):
            return
        
        active_database = self._require_active_database()
        if not active_database:
            return
        
        # Get selected game indices from database panel (if any)
        selected_game_indices = []
        active_info = self.database_panel.get_active_database_info()
        if active_info and active_info.get('model') == active_database:
            selected_game_indices = self.database_panel.get_selected_game_indices()
        
        # Get bulk tag controller
        bulk_tag_controller = self.controller.get_bulk_tag_controller()
        
        # Import and show dialog
        from app.views.bulk_tag_dialog import BulkTagDialog
        dialog = BulkTagDialog(
            self.config,
            bulk_tag_controller,
            active_database,
            selected_game_indices=selected_game_indices if selected_game_indices else None,
            parent=self
        )
        dialog.exec()
    
    def _import_online_games(self) -> None:
        """Open import games from online dialog."""
        if not hasattr(self, 'database_panel'):
            return
        
        # Get active database
        database_controller = self.controller.get_database_controller()
        active_database = database_controller.get_active_database()
        
        # Import and show dialog
        from app.views.import_games_dialog import ImportGamesDialog
        
        dialog = ImportGamesDialog(
            self.config,
            database_controller,
            active_database,
            self
        )
        dialog.exec()
    
    def _search_games(self) -> None:
        """Open search games dialog."""
        if not hasattr(self, 'database_panel'):
            return
        
        # Get active database
        active_database = self._require_active_database()
        if not active_database:
            return
        
        # Get all open databases from panel model for dialog
        database_controller = self.controller.get_database_controller()
        panel_model = database_controller.get_panel_model()
        all_databases = []
        for identifier, db_info in panel_model.get_all_databases().items():
            all_databases.append(db_info.model)
        
        # Import and show dialog
        from app.views.search_dialog import SearchDialog
        
        dialog = SearchDialog(
            self.config,
            active_database,
            all_databases,
            self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            search_query = dialog.get_search_query()
            if search_query and search_query.criteria:
                # Delegate search to controller
                search_controller = self.controller.get_search_controller()
                search_results_model, status_message = search_controller.perform_search(
                    search_query,
                    active_database
                )
                
                if search_results_model is None:
                    # Show error dialog if search failed
                    MessageDialog.show_warning(
                        self.config,
                        "Search Failed",
                        status_message,
                        self
                    )
                    return
                
                # Report search status
                self.controller.set_status(status_message)
                
                # Add search results tab to database panel and switch to it
                tab_index = self.database_panel.add_search_results_tab(search_results_model)
                # Switch to the search results tab
                self.database_panel.tab_widget.setCurrentIndex(tab_index)
                # Update menu state (will enable close search results action)
                self._on_database_tab_changed(tab_index)
    
    def _find_search_results_tab(self) -> Optional[int]:
        """Find the index of the Search Results tab.
        
        Returns:
            Tab index if found, None otherwise.
        """
        if not hasattr(self, 'database_panel'):
            return None
        
        for tab_idx, tab_data in self.database_panel._tab_models.items():
            if tab_data.get('identifier') == 'search_results':
                return tab_idx
        return None
    
    
    def _close_search_results_tab(self) -> None:
        """Close the Search Results tab and set the previous database as active.
        
        This is a shared helper method used by both _close_search_results()
        and _close_search_results_after_save().
        """
        if not hasattr(self, 'database_panel'):
            return
        
        # Find the Search Results tab
        search_results_tab_idx = self._find_search_results_tab()
        if search_results_tab_idx is None:
            return
        
        # Get the currently active database from panel model
        # (search results tabs don't change the active database, so this should be correct)
        database_controller = self.controller.get_database_controller()
        panel_model = database_controller.get_panel_model()
        current_active = panel_model.get_active_database()
        
        # The active database should already be set correctly since search results
        # tabs don't modify the panel model's active database.
        # However, we need to ensure the UI switches to the correct tab.
        # If the active database is already set, we don't need to change it.
        # If it's not set (shouldn't happen), fall back to Clipboard.
        new_active_model = current_active
        if new_active_model is None:
            clipboard_model = panel_model.get_database_by_identifier("clipboard")
            if clipboard_model:
                new_active_model = clipboard_model
        
        # Remove the tab
        self.database_panel._remove_database_tab(search_results_tab_idx)
        
        # Set the new active database (this will trigger tab switch via signal)
        if new_active_model:
            panel_model.set_active_database(new_active_model)
            # Explicitly switch to the correct tab to ensure UI updates
            self.database_panel._set_active_tab_for_database(new_active_model)
        else:
            # Fallback: switch to Clipboard tab (index 0)
            self.database_panel.tab_widget.setCurrentIndex(0)
        
        # Update menu state
        current_index = self.database_panel.tab_widget.currentIndex()
        self._on_database_tab_changed(current_index)
    
    def _close_search_results_after_save(self) -> None:
        """Close the Search Results tab after a successful Save As operation."""
        self._close_search_results_tab()
    
    def _close_search_results(self) -> None:
        """Close the Search Results tab and set the previous database as active."""
        if self._find_search_results_tab() is None:
            self.close_search_results_action.setEnabled(False)
            return
        
        self._close_search_results_tab()
    
    def _bulk_clean_pgn(self) -> None:
        """Open bulk clean PGN dialog."""
        if not hasattr(self, 'database_panel'):
            return
        
        active_database = self._require_active_database()
        if not active_database:
            return
        
        # Get bulk clean PGN controller
        bulk_clean_pgn_controller = self.controller.get_bulk_clean_pgn_controller()
        
        # Import and show dialog
        from app.views.bulk_clean_pgn_dialog import BulkCleanPgnDialog
        dialog = BulkCleanPgnDialog(
            self.config,
            bulk_clean_pgn_controller,
            active_database,
            self
        )
        dialog.exec()
    
    def _deduplicate_games(self) -> None:
        """Deduplicate games in the active database."""
        if not hasattr(self, 'database_panel'):
            return
        
        active_database = self._require_active_database()
        if not active_database:
            return
        
        # Get total number of games for confirmation message
        total_games = len(active_database.get_all_games())
        if total_games == 0:
            MessageDialog.show_warning(
                self.config,
                "Empty Database",
                "The active database is empty. No games to deduplicate.",
                self
            )
            return
        
        # Get deduplication controller
        deduplication_controller = self.controller.get_deduplication_controller()
        
        # Perform deduplication (shows criteria dialog first, which serves as confirmation)
        result = deduplication_controller.deduplicate(active_database, self)
        
        # If dialog was cancelled, return early
        if result is None:
            return
        
        # Show result message if there were errors
        if not result.success:
            error_msg = result.error_message or "Unknown error occurred"
            MessageDialog.show_warning(
                self.config,
                "Deduplication Failed",
                f"Deduplication failed: {error_msg}",
                self
            )
    
    def _open_manual(self) -> None:
        """Open the user manual in the default browser."""
        # Get the path to the manual HTML file
        # __file__ is app/main_window.py, so parent is app/, then resources/manual/index.html
        manual_path = Path(__file__).resolve().parent / "resources" / "manual" / "index.html"
        # Convert to QUrl and open in default browser
        url = QUrl.fromLocalFile(str(manual_path))
        QDesktopServices.openUrl(url)
    
    def _show_about_dialog(self) -> None:
        """Show the about dialog."""
        dialog = AboutDialog(self.config, self)
        dialog.exec()
    
    def _check_for_updates(self) -> None:
        """Check for application updates."""
        # Run version check in a separate thread to avoid blocking UI
        class VersionCheckThread(QThread):
            finished = pyqtSignal(bool, bool, str, str)  # success, is_newer, remote_version, error_message
            
            def __init__(self, controller, url):
                super().__init__()
                self.controller = controller
                self.url = url
            
            def run(self):
                success, is_newer, remote_version, error_message = self.controller.check_for_updates(self.url)
                self.finished.emit(success, is_newer or False, remote_version or "", error_message or "")
        
        # Get URL from config or use default
        update_url = self.config.get('update_check_url', 'https://pguntermann.github.io/CARA/')
        
        # Create and start thread
        self._version_check_thread = VersionCheckThread(self.controller, update_url)
        self._version_check_thread.finished.connect(self._on_version_check_complete)
        self._version_check_thread.start()
    
    def _on_version_check_complete(self, success: bool, is_newer: bool, remote_version: str, error_message: str) -> None:
        """Handle version check completion.
        
        Args:
            success: True if check completed successfully.
            is_newer: True if remote version is newer.
            remote_version: Remote version string.
            error_message: Error message if check failed.
        """
        current_version = self.config.get('version', '1.0')
        
        if not success:
            # Show error message
            MessageDialog.show_error(
                self.config,
                "Update Check Failed",
                f"Could not check for updates:\n\n{error_message}",
                self
            )
        elif is_newer:
            # Show new version available confirmation dialog
            message = (f"A newer version is available!\n\n"
                      f"Current version: {current_version}\n"
                      f"Available version: {remote_version}\n\n"
                      f"Would you like to go to the download page?")
            
            confirmed = ConfirmationDialog.show_confirmation(
                self.config,
                "Update Available",
                message,
                self
            )
            
            if confirmed:
                # Open download page in browser
                download_url = self.config.get('download_url', 'https://pguntermann.github.io/CARA/')
                QDesktopServices.openUrl(QUrl(download_url))
        else:
            # Show up-to-date message
            MessageDialog.show_information(
                self.config,
                "Up to Date",
                f"You are using the latest version.\n\nCurrent version: {current_version}",
                self
            )
    
    def _close_application(self) -> None:
        """Close the application."""
        self._save_user_settings()
        QApplication.instance().quit()
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event.
        
        Args:
            event: Close event.
        """
        # Log application closing
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.info("Application closing: saving settings, cleaning up")
        
        self._save_user_settings()
        event.accept()
    
    def _on_board_flip_state_changed(self, is_flipped: bool) -> None:
        """Handle board flip state change to update menu toggle.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        self._update_rotate_action_state(is_flipped)
    
    def _update_rotate_action_state(self, is_flipped: bool) -> None:
        """Update the rotate board menu action toggle state.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if hasattr(self, 'rotate_action'):
            self.rotate_action.setChecked(is_flipped)
    
    def _on_show_annotations_layer_toggled(self, checked: bool) -> None:
        """Handle Show Annotations Layer toggle.
        
        Args:
            checked: True if checked, False otherwise.
        """
        if self.controller and self.controller.get_annotation_controller():
            self.controller.get_annotation_controller().toggle_annotations_visibility()
    
    def _on_annotations_layer_visibility_changed(self, visible: bool) -> None:
        """Handle annotation layer visibility change from model.
        
        Args:
            visible: True if visible, False otherwise.
        """
        if hasattr(self, 'show_annotations_layer_action'):
            self.show_annotations_layer_action.setChecked(visible)
    
    def _clear_all_annotations_for_game(self) -> None:
        """Clear all annotations for the current game."""
        if not self.controller:
            return
        
        annotation_controller = self.controller.get_annotation_controller()
        if annotation_controller:
            annotation_controller.clear_all_annotations()
    
    def _clear_annotations_for_current_move(self) -> None:
        """Clear annotations for the current move."""
        if not self.controller:
            return
        
        annotation_controller = self.controller.get_annotation_controller()
        if annotation_controller:
            annotation_controller.clear_current_annotations()
    
    def _save_annotations_to_current_game(self) -> None:
        """Save annotations into the active game's PGN tag."""
        if not self.controller:
            return
        
        annotation_controller = self.controller.get_annotation_controller()
        if annotation_controller:
            annotation_controller.save_annotations()
    
    def _show_ai_model_settings(self) -> None:
        """Show the AI model settings dialog."""
        from app.views.ai_model_settings_dialog import AIModelSettingsDialog
        from app.services.user_settings_service import UserSettingsService
        
        settings_service = UserSettingsService.get_instance()
        dialog = AIModelSettingsDialog(self.config, settings_service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_ai_summary_models()
    
    def _show_annotation_preferences(self) -> None:
        """Show annotation preferences dialog."""
        from app.views.annotation_preferences_dialog import AnnotationPreferencesDialog
        dialog = AnnotationPreferencesDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload colors in annotation view if it exists
            if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'annotation_view'):
                annotation_view = self.detail_panel.annotation_view
                if annotation_view:
                    annotation_view.reload_colors()
            
            # Trigger repaint of chessboard to update font for existing annotations
            if hasattr(self, 'main_panel') and hasattr(self.main_panel, 'chessboard_view'):
                if hasattr(self.main_panel.chessboard_view, 'chessboard'):
                    self.main_panel.chessboard_view.chessboard.update()
    
    def _on_coordinates_visibility_changed(self, show: bool) -> None:
        """Handle coordinates visibility change to update menu toggle.
        
        Args:
            show: True if coordinates are visible, False otherwise.
        """
        self._update_coordinates_action_state(show)
    
    def _update_coordinates_action_state(self, show: bool) -> None:
        """Update the coordinates visibility menu action toggle state.
        
        Args:
            show: True if coordinates are visible, False otherwise.
        """
        if hasattr(self, 'coordinates_action'):
            self.coordinates_action.setChecked(show)
    
    def _on_turn_indicator_visibility_changed(self, show: bool) -> None:
        """Handle turn indicator visibility change to update menu toggle.
        
        Args:
            show: True if turn indicator is visible, False otherwise.
        """
        self._update_turn_indicator_action_state(show)
    
    def _update_turn_indicator_action_state(self, show: bool) -> None:
        """Update the turn indicator visibility menu action toggle state.
        
        Args:
            show: True if turn indicator is visible, False otherwise.
        """
        if hasattr(self, 'turn_indicator_action'):
            self.turn_indicator_action.setChecked(show)
    
    def _on_game_info_visibility_changed(self, show: bool) -> None:
        """Handle game info visibility change to update menu toggle.
        
        Args:
            show: True if game info is visible, False otherwise.
        """
        self._update_game_info_action_state(show)
    
    def _update_game_info_action_state(self, show: bool) -> None:
        """Update the game info visibility menu action toggle state.
        
        Args:
            show: True if game info is visible, False otherwise.
        """
        if hasattr(self, 'game_info_action'):
            self.game_info_action.setChecked(show)
    
    def _on_playedmove_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle played move arrow visibility change to update menu toggle.
        
        Args:
            visible: True if played move arrow is visible, False otherwise.
        """
        self._update_playedmove_arrow_action_state(visible)
    
    def _update_playedmove_arrow_action_state(self, visible: bool) -> None:
        """Update played move arrow menu action checked state.
        
        Args:
            visible: True if played move arrow is visible, False otherwise.
        """
        if hasattr(self, 'playedmove_arrow_action'):
            self.playedmove_arrow_action.setChecked(visible)
    
    def _on_bestnextmove_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle best next move arrow visibility change to update menu toggle.
        
        Args:
            visible: True if best next move arrow is visible, False otherwise.
        """
        self._update_bestnextmove_arrow_action_state(visible)
    
    def _update_bestnextmove_arrow_action_state(self, visible: bool) -> None:
        """Update best next move arrow menu action checked state.
        
        Args:
            visible: True if best next move arrow is visible, False otherwise.
        """
        if hasattr(self, 'bestnextmove_arrow_action'):
            self.bestnextmove_arrow_action.setChecked(visible)
    
    def _update_pv2_arrow_action_state(self, visible: bool) -> None:
        """Update PV2 arrow menu action checked state.
        
        Args:
            visible: True if PV2 arrow is visible, False otherwise.
        """
        if hasattr(self, 'pv2_arrow_action'):
            self.pv2_arrow_action.setChecked(visible)
    
    def _update_pv3_arrow_action_state(self, visible: bool) -> None:
        """Update PV3 arrow menu action checked state.
        
        Args:
            visible: True if PV3 arrow is visible, False otherwise.
        """
        if hasattr(self, 'pv3_arrow_action'):
            self.pv3_arrow_action.setChecked(visible)
    
    def _on_bestalternativemove_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle best alternative move arrow visibility change to update menu toggle.
        
        Args:
            visible: True if best alternative move arrow is visible, False otherwise.
        """
        self._update_bestalternativemove_arrow_action_state(visible)
    
    def _update_bestalternativemove_arrow_action_state(self, visible: bool) -> None:
        """Update best alternative move arrow menu action checked state.
        
        Args:
            visible: True if best alternative move arrow is visible, False otherwise.
        """
        if hasattr(self, 'bestalternativemove_arrow_action'):
            self.bestalternativemove_arrow_action.setChecked(visible)
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change to update best alternative move arrow.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        self._update_best_alternative_move(ply_index)
    
    def _on_active_move_changed_for_material(self, ply_index: int) -> None:
        """Handle active move change to notify material widget.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        # Notify material widget when at starting position
        # This ensures initial pieces are set even if we navigate to ply_index 0
        if hasattr(self, 'main_panel') and hasattr(self.main_panel, 'chessboard_view'):
            chessboard_view = self.main_panel.chessboard_view
            if hasattr(chessboard_view, 'chessboard') and hasattr(chessboard_view.chessboard, 'material_widget'):
                material_widget = chessboard_view.chessboard.material_widget
                material_widget.set_at_starting_position(ply_index == 0)
    
    def _set_material_widget_initial_pieces(self, game) -> None:
        """Set initial pieces for material widget from game's starting FEN.
        
        This extracts the starting FEN from the game's PGN headers and sets
        the initial piece counts in the material widget. This ensures the widget
        works correctly even with custom starting positions.
        
        Args:
            game: GameData instance.
        """
        if not game or not game.pgn:
            return
        
        try:
            import chess.pgn
            import io
            
            # Parse the PGN to get the starting FEN
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return
            
            # Get the starting position from the game
            headers = chess_game.headers
            
            # Check for FEN header (SetUp "1" indicates custom position)
            if headers.get("SetUp") == "1" and "FEN" in headers:
                fen = headers.get("FEN")
            else:
                # Standard starting position
                fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
            
            # Set initial pieces in material widget
            if hasattr(self, 'main_panel') and hasattr(self.main_panel, 'chessboard_view'):
                chessboard_view = self.main_panel.chessboard_view
                if hasattr(chessboard_view, 'chessboard') and hasattr(chessboard_view.chessboard, 'material_widget'):
                    material_widget = chessboard_view.chessboard.material_widget
                    material_widget.set_initial_pieces_from_fen(fen)
        except Exception:
            # If parsing fails, material widget will use fallback in _update_captured_pieces()
            pass
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change to clear best alternative move arrow.
        
        Args:
            game: GameData instance or None.
        """
        if game is None:
            # Clear best alternative move when no game is active
            board_model = self.controller.get_board_controller().get_board_model()
            board_model.set_best_alternative_move(None)
        else:
            # Update best alternative move for the current position
            game_model = self.controller.get_game_controller().get_game_model()
            ply_index = game_model.get_active_move_ply()
            self._update_best_alternative_move(ply_index)
            
            # Set initial pieces for material widget from game's starting FEN
            self._set_material_widget_initial_pieces(game)
    
    def _update_best_alternative_move(self, ply_index: int) -> None:
        """Update best alternative move from movelist based on current position.
        
        Args:
            ply_index: Ply index of the current position (0 = starting position).
        """
        # Check if we have access to the movelist model
        if not hasattr(self, 'detail_panel') or not hasattr(self.detail_panel, 'moveslist_model'):
            board_model = self.controller.get_board_controller().get_board_model()
            board_model.set_best_alternative_move(None)
            return
        
        # Delegate to controller for business logic
        moveslist_model = self.detail_panel.moveslist_model
        game_controller = self.controller.get_game_controller()
        game_controller.update_best_alternative_move(ply_index, moveslist_model)
    
    def _on_last_move_changed_for_best_alternative(self, last_move) -> None:
        """Handle last move change to re-check if best alternative move matches played move.
        
        This is called after the board position is updated, so we can properly compare
        the best alternative move with the played move.
        
        Args:
            last_move: The last move that was played, or None.
        """
        # Delegate to controller for business logic
        game_controller = self.controller.get_game_controller()
        game_controller.check_best_alternative_move_matches_played(last_move)
    
    def _on_evaluation_bar_visibility_changed(self, show: bool) -> None:
        """Handle evaluation bar visibility change to update menu toggle.
        
        Args:
            show: True if evaluation bar is visible, False otherwise.
        """
        self._update_evaluation_bar_action_state(show)
    
    def _on_material_widget_visibility_changed(self, show: bool) -> None:
        """Handle material widget visibility change to update menu toggle.
        
        Args:
            show: True if material widget is visible, False otherwise.
        """
        self._update_material_widget_action_state(show)
    
    def _update_evaluation_bar_action_state(self, show: bool) -> None:
        """Update the evaluation bar visibility menu action toggle state.
        
        Args:
            show: True if evaluation bar is visible, False otherwise.
        """
        if hasattr(self, 'evaluation_bar_action'):
            self.evaluation_bar_action.setChecked(show)
    
    def _update_material_widget_action_state(self, show: bool) -> None:
        """Update the material widget visibility menu action toggle state.
        
        Args:
            show: True if material widget is visible, False otherwise.
        """
        if hasattr(self, 'material_widget_action'):
            self.material_widget_action.setChecked(show)
    
    def _update_positional_heatmap_action_state(self, show: bool) -> None:
        """Update the positional heat-map visibility menu action toggle state.
        
        Args:
            show: True if positional heat-map is visible, False otherwise.
        """
        if hasattr(self, 'positional_heatmap_action'):
            self.positional_heatmap_action.setChecked(show)
    
    def _on_positional_heatmap_visibility_changed(self, show: bool) -> None:
        """Handle positional heat-map visibility change.
        
        Args:
            show: True if positional heat-map should be shown, False otherwise.
        """
        self._update_positional_heatmap_action_state(show)
    
    def _start_evaluation_if_bar_visible(self) -> None:
        """Start evaluation if the bar is visible (called after loading settings)."""
        board_model = self.controller.get_board_controller().get_board_model()
        if board_model.show_evaluation_bar:
            fen = board_model.get_fen()
            self.controller.get_evaluation_controller().start_evaluation(fen)
    
    def _setup_ui(self) -> None:
        """Setup the UI layout with four panels."""
        
        # Debug log
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.debug("Setting up UI")
        
        # Central widget container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout (vertical)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top splitter: Main-Panel and Detail-Panel (horizontal)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Main application area / Main-Panel
        board_model = self.controller.get_board_controller().get_board_model()
        game_model = self.controller.get_game_controller().get_game_model()
        game_controller = self.controller.get_game_controller()
        evaluation_model = self.controller.get_evaluation_controller().get_evaluation_model()
        self.main_panel = MainPanel(self.config, board_model, game_model, game_controller, evaluation_model)
        top_splitter.addWidget(self.main_panel)
        
        # Connect positional heat-map model to chessboard widget
        positional_heatmap_controller = self.controller.get_positional_heatmap_controller()
        positional_heatmap_model = positional_heatmap_controller.get_model()
        if hasattr(self.main_panel, 'chessboard_view') and hasattr(self.main_panel.chessboard_view, 'chessboard'):
            self.main_panel.chessboard_view.chessboard.set_positional_heatmap_model(
                positional_heatmap_model, 
                positional_heatmap_controller
            )
        
        # Right-hand Detail-Panel containing different Views/Tabs
        engine_model = self.controller.get_engine_controller().get_engine_model()
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        annotation_controller = self.controller.get_annotation_controller()
        # Get database model for metadata view
        database_model = self.controller.get_database_controller().get_database_model()
        classification_model = self.controller.get_move_classification_controller().get_classification_model()
        # Get chessboard widget for annotation drawing
        board_widget = None
        if hasattr(self.main_panel, 'chessboard_view') and hasattr(self.main_panel.chessboard_view, 'chessboard'):
            board_widget = self.main_panel.chessboard_view.chessboard
        ai_chat_controller = self.controller.get_ai_chat_controller()
        game_summary_controller = self.controller.get_game_summary_controller()
        player_stats_controller = self.controller.get_player_stats_controller()
        metadata_controller = self.controller.get_metadata_controller()
        self.detail_panel = DetailPanel(self.config, game_model, game_controller, engine_model, 
                                        manual_analysis_controller, database_model, classification_model,
                                        annotation_controller, board_widget, ai_chat_controller,
                                        game_summary_controller, player_stats_controller,
                                        metadata_controller)
        top_splitter.addWidget(self.detail_panel)
        
        # Connect column profile model to moves list view
        self._connect_column_profile_to_moves_list()
        
        # Connect detail panel tab change signal to update View menu checkmarks
        self._connect_detail_panel_tabs()
        
        # Set initial sizes (Main-Panel: 60%, Detail-Panel: 40%)
        ui_config = self.config.get('ui', {})
        splitter_config = ui_config.get('splitter', {}).get('top', {})
        main_size = splitter_config.get('main_size', 600)
        detail_size = splitter_config.get('detail_size', 400)
        main_stretch = splitter_config.get('main_stretch_factor', 3)
        detail_stretch = splitter_config.get('detail_stretch_factor', 2)
        top_splitter.setSizes([main_size, detail_size])
        top_splitter.setStretchFactor(0, main_stretch)
        top_splitter.setStretchFactor(1, detail_stretch)
        
        # Middle splitter: Database-Panel
        # Database-Panel can be collapsed if not needed at the moment
        # Connect to database panel model
        database_controller = self.controller.get_database_controller()
        panel_model = database_controller.get_panel_model()
        # Connect double-click handler to set active game
        # Connect "+" tab click handler to open PGN database
        self.database_panel = DatabasePanel(
            self.config, 
            panel_model,
            on_row_double_click=self._on_database_row_double_click,
            on_add_tab_clicked=self._open_pgn_database
        )
        
        
        # Pass database_panel to detail_panel so metadata view can refresh table views
        if hasattr(self, 'detail_panel'):
            self.detail_panel._database_panel = self.database_panel
            if hasattr(self.detail_panel, 'metadata_view'):
                self.detail_panel.metadata_view._database_panel = self.database_panel
            # Pass database_controller and database_panel to player_stats_view
            if hasattr(self.detail_panel, 'player_stats_view'):
                self.detail_panel.player_stats_view._database_controller = database_controller
                self.detail_panel.player_stats_view._database_panel = self.database_panel
                # Database connections are now handled by the controller
        
        # Set moves list model in game analysis controller
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            self.controller.set_moves_list_model(self.detail_panel.moveslist_model)
        
        # Connect to game model to update best alternative move when position changes
        game_model = self.controller.get_game_controller().get_game_model()
        game_model.active_move_changed.connect(self._on_active_move_changed)
        game_model.active_game_changed.connect(self._on_active_game_changed)
        
        # Connect to game model to notify material widget when at starting position
        game_model.active_move_changed.connect(self._on_active_move_changed_for_material)
        
        # Also connect to board model's last_move_changed to re-check best alternative move
        # This ensures we check after the board position is updated
        board_model = self.controller.get_board_controller().get_board_model()
        board_model.last_move_changed.connect(self._on_last_move_changed_for_best_alternative)
        
        # Connect to database panel tab changes to update save menu state
        # Use QTimer to ensure this happens after menu is set up
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._connect_database_tab_changes)
        
        # Status-Panel replaces PyQt's native Statusbar
        # Shows formatted status message and visual progress bar
        # Connect to progress model
        progress_model = self.controller.get_progress_model()
        self.status_panel = StatusPanel(self.config, progress_model)
        
        # Vertical splitter for top panels and database panel
        self.middle_splitter = QSplitter(Qt.Orientation.Vertical)
        self.middle_splitter.addWidget(top_splitter)
        self.middle_splitter.addWidget(self.database_panel)
        
        # Store reference to database panel index for collapse/expand
        self.database_panel_index = 1
        
        # Track collapsed state
        self._database_panel_collapsed = False
        ui_config = self.config.get('ui', {})
        database_config = ui_config.get('panels', {}).get('database', {})
        self._stored_size = database_config.get('default_height', 240)
        
        # Set initial sizes for vertical splitter
        # Top panels: 80%, Database-Panel: 20%
        middle_splitter_config = ui_config.get('splitter', {}).get('middle', {})
        top_size = middle_splitter_config.get('top_size', 640)
        database_size = middle_splitter_config.get('database_size', 160)
        top_stretch = middle_splitter_config.get('top_stretch_factor', 4)
        database_stretch = middle_splitter_config.get('database_stretch_factor', 1)
        self.middle_splitter.setSizes([top_size, database_size])
        self.middle_splitter.setStretchFactor(0, top_stretch)
        self.middle_splitter.setStretchFactor(1, database_stretch)
        
        # Enable collapsible on database panel
        self.middle_splitter.setCollapsible(self.database_panel_index, True)
        
        # Setup double-click handler on splitter handle to collapse/expand database panel
        self._setup_splitter_double_click()
        
        # Fix cursor on splitter handles for macOS compatibility
        self._fix_splitter_cursors()
        
        # Apply splitter styling to prevent macOS theme override
        self._apply_splitter_styling()
        
        # Main layout: Middle splitter (with top and database panels) and status panel
        main_layout.addWidget(self.middle_splitter, 1)  # Takes most space
        main_layout.addWidget(self.status_panel, 0)  # Fixed height
        
        # The relative sizes of the panels can be changed by the user with separators
    
    def _toggle_database_panel(self) -> None:
        """Toggle collapse/expand state of database panel."""
        # Get collapsed height from config
        ui_config = self.config.get('ui', {})
        database_config = ui_config.get('panels', {}).get('database', {})
        collapsed_height = database_config.get('collapsed_height', 30)
        default_height = database_config.get('default_height', 240)
        
        # Toggle the collapsed state
        self._database_panel_collapsed = not self._database_panel_collapsed
        
        if self._database_panel_collapsed:
            # Collapse by setting size to minimum visible height
            current_sizes = self.middle_splitter.sizes()
            # Store the current size if it's larger than collapsed height
            if current_sizes[1] > collapsed_height:
                self._stored_size = current_sizes[1]
            else:
                # If already collapsed or very small, use default
                self._stored_size = getattr(self, '_stored_size', default_height)
            self.middle_splitter.setSizes([current_sizes[0], collapsed_height])
        else:
            # Expand by restoring stored size
            current_sizes = self.middle_splitter.sizes()
            restored_size = getattr(self, '_stored_size', default_height)
            self.middle_splitter.setSizes([current_sizes[0], restored_size])
        
        # Update panel content visibility
        self.database_panel.set_collapsed_state(self._database_panel_collapsed)
        
        # Update menu item checkmark state
        if hasattr(self, 'view_hide_database_panel_action'):
            self.view_hide_database_panel_action.setChecked(self._database_panel_collapsed)
    
    def _setup_splitter_double_click(self) -> None:
        """Setup double-click handler on the splitter handle to collapse/expand database panel."""
        # Get the handle for the database panel (index 1)
        handle = self.middle_splitter.handle(self.database_panel_index)
        if handle:
            # Install event filter to detect double-clicks
            handle.installEventFilter(self)
    
    def _fix_splitter_cursors(self) -> None:
        """Fix cursor on all splitter handles for macOS compatibility.
        
        On macOS, child widgets can reset the cursor, causing the resize cursor
        to only show briefly. This function explicitly sets the cursor on all
        splitter handles to ensure it persists.
        """
        # Fix cursor on top_splitter (horizontal splitter needs vertical resize cursor)
        top_splitter = self.middle_splitter.widget(0)
        if isinstance(top_splitter, QSplitter):
            for i in range(top_splitter.count() - 1):
                handle = top_splitter.handle(i)
                if handle:
                    handle.setCursor(Qt.CursorShape.SizeHorCursor)
        
        # Fix cursor on middle_splitter (vertical splitter needs horizontal resize cursor)
        for i in range(self.middle_splitter.count() - 1):
            handle = self.middle_splitter.handle(i)
            if handle:
                handle.setCursor(Qt.CursorShape.SizeVerCursor)
    
    def eventFilter(self, obj, event) -> bool:
        """Filter events to detect double-clicks on splitter handle."""
        # Check if this is a double-click on the database panel splitter handle
        if event.type() == QEvent.Type.MouseButtonDblClick:
            handle = self.middle_splitter.handle(self.database_panel_index)
            if obj == handle:
                self._toggle_database_panel()
                return True  # Event handled
        # Let other events pass through
        return super().eventFilter(obj, event)
    
    def _fix_splitter_cursors(self) -> None:
        """Fix cursor on all splitter handles for macOS compatibility.
        
        On macOS, child widgets can reset the cursor, causing the resize cursor
        to only show briefly. This function explicitly sets the cursor on all
        splitter handles to ensure it persists.
        """
        # Fix cursor on top_splitter (horizontal splitter needs vertical resize cursor)
        top_splitter = self.middle_splitter.widget(0)
        if isinstance(top_splitter, QSplitter):
            for i in range(top_splitter.count() - 1):
                handle = top_splitter.handle(i)
                if handle:
                    handle.setCursor(Qt.CursorShape.SizeHorCursor)
        
        # Fix cursor on middle_splitter (vertical splitter needs horizontal resize cursor)
        for i in range(self.middle_splitter.count() - 1):
            handle = self.middle_splitter.handle(i)
            if handle:
                handle.setCursor(Qt.CursorShape.SizeVerCursor)
    
    def _apply_splitter_styling(self) -> None:
        """Apply styling to splitter handles to prevent macOS theme override."""
        ui_config = self.config.get('ui', {})
        splitter_config = ui_config.get('splitter', {})
        handle_color = splitter_config.get('handle_color', [30, 30, 30])
        
        # Create stylesheet for splitter handles
        stylesheet = f"""
            QSplitter::handle {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
            QSplitter::handle:horizontal {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
            QSplitter::handle:vertical {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
        """
        
        # Apply to middle_splitter
        self.middle_splitter.setStyleSheet(stylesheet)
        
        # Apply to top_splitter (nested inside middle_splitter)
        top_splitter = self.middle_splitter.widget(0)
        if isinstance(top_splitter, QSplitter):
            top_splitter.setStyleSheet(stylesheet)
    
    def _setup_shortcuts(self) -> None:
        """Setup global keyboard shortcuts."""

        # Debug log
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.debug("Setting up shortcuts")

        # Initialize shortcut manager with MainWindow as parent
        shortcut_manager = ShortcutManager(self)
        
        # Register shortcuts
        # X key: Rotate board 180 degrees (handled by menu action, no need to register separately)
        # shortcut_manager.register_shortcut("X", self.controller.rotate_board)  # Removed - handled by menu action
        
        # Shift+F: Copy FEN (handled by menu action)
        # Ctrl+P: Copy PGN (handled by menu action)
        
        # Ctrl+V: Paste PGN to Clipboard DB (handled by menu action)
        # Ctrl+Alt+V: Paste PGN to active DB (handled by menu action)
        
        # Right Arrow: Navigate to next move
        shortcut_manager.register_shortcut("Right", self._navigate_to_next_move)
        
        # Left Arrow: Navigate to previous move
        shortcut_manager.register_shortcut("Left", self._navigate_to_previous_move)
    
    def _copy_fen_to_clipboard(self) -> None:
        """Copy the current board position FEN to clipboard."""
        fen, status_message = self.controller.copy_fen_to_clipboard()
        self.controller.set_status(status_message)
    
    def _copy_pgn_to_clipboard(self) -> None:
        """Copy the current active game PGN to clipboard."""
        success, status_message = self.controller.copy_pgn_to_clipboard()
        self.controller.set_status(status_message)
    
    def _copy_selected_games(self) -> None:
        """Copy selected games from active database to clipboard."""
        if not hasattr(self, 'database_panel'):
            self.controller.set_status("No database panel available")
            return
        
        success, status_message = self.controller.copy_selected_games_to_clipboard(self.database_panel)
        self.controller.set_status(status_message)
    
    def _cut_selected_games(self) -> None:
        """Cut selected games from active database to clipboard (copy and remove)."""
        if not hasattr(self, 'database_panel'):
            self.controller.set_status("No database panel available")
            return
        
        success, status_message = self.controller.cut_selected_games_to_clipboard(self.database_panel)
        self.controller.set_status(status_message)
    
    def _paste_fen_from_clipboard(self) -> None:
        """Paste FEN from clipboard and update board position."""
        success, status_message = self.controller.paste_fen_from_clipboard()
        self.controller.set_status(status_message)
    
    def _paste_pgn_from_clipboard(self) -> None:
        """Paste PGN from clipboard and add to database panel."""
        # Parse PGN from clipboard through controller
        success, status_message = self.controller.paste_pgn_from_clipboard()

        # Display formatted message from controller
        self.controller.set_status(status_message)
    
    def _paste_pgn_to_clipboard_db(self) -> None:
        """Paste PGN from clipboard to clipboard database."""
        # Parse PGN from clipboard through controller
        success, status_message, first_game_index, games_added = self.controller.paste_pgn_to_clipboard_db()
        
        # Display formatted message from controller
        self.controller.set_status(status_message)
        
        # If successful, set clipboard database as active and highlight all added rows
        if success and first_game_index is not None and games_added > 0:
            # Get clipboard database model
            database_controller = self.controller.get_database_controller()
            clipboard_database = database_controller.get_database_model()
            
            # Set clipboard database as active (view will update automatically)
            database_controller.set_active_database(clipboard_database)
            
            # Calculate all indices for pasted games and highlight them all
            pasted_indices = list(range(first_game_index, first_game_index + games_added))
            self.database_panel.highlight_rows(clipboard_database, pasted_indices)
    
    def _paste_pgn_to_active_db(self) -> None:
        """Paste PGN from clipboard to the currently active database."""
        # Delegate to controller for business logic
        success, message, first_game_index, games_added = self.controller.paste_pgn_to_active_database()
        
        if success:
            # If successful, highlight all added rows
            if first_game_index is not None and games_added > 0:
                database_controller = self.controller.get_database_controller()
                active_database = database_controller.get_active_database()
                if active_database:
                    # Calculate all indices for pasted games
                    pasted_indices = list(range(first_game_index, first_game_index + games_added))
                    self.database_panel.highlight_rows(active_database, pasted_indices)
        
        # Display status message
        self.controller.set_status(message)
    
    def _paste_fen_to_board(self) -> None:
        """Paste FEN from clipboard and update board position."""
        success, status_message = self.controller.paste_fen_from_clipboard()
        self.controller.set_status(status_message)
    
    def _debug_copy_pgn_html(self) -> None:
        """DEBUG: Copy PGN HTML and current visibility settings to clipboard."""
        from PyQt6.QtWidgets import QApplication
        
        # Get PGN view from detail panel
        pgn_view = self.detail_panel.pgn_view
        
        # Get HTML and settings
        html, settings = pgn_view.get_debug_info()
        
        # Format debug info
        debug_text = f"""=== PGN VIEW DEBUG INFO ===

Visibility Settings:
- Show Metadata: {settings['show_metadata']}
- Show Comments: {settings['show_comments']}
- Show Variations: {settings['show_variations']}
- Show Annotations: {settings['show_annotations']}
- Show Results: {settings['show_results']}

=== HTML OUTPUT ===

{html}

=== END DEBUG INFO ===
"""
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(debug_text)
        
        self.controller.set_status("DEBUG: PGN HTML and settings copied to clipboard")
    
    def _debug_copy_game_highlights_html(self) -> None:
        """DEBUG: Copy game highlights section from the summary controller as HTML."""
        from PyQt6.QtWidgets import QApplication
        
        summary_controller = self.controller.get_game_summary_controller()
        highlights_html = summary_controller.get_highlights_html() if summary_controller else ""
        if not highlights_html:
            self.controller.set_status("DEBUG: No game highlights available to copy")
            return
        
        clipboard = QApplication.clipboard()
        clipboard.setText(highlights_html)
        self.controller.set_status("DEBUG: Game highlights HTML copied to clipboard")
    
    def _debug_copy_game_highlights_json(self) -> None:
        """DEBUG: Copy game highlights data as JSON."""
        from PyQt6.QtWidgets import QApplication
        import json
        
        summary_controller = self.controller.get_game_summary_controller()
        highlights_data = summary_controller.get_highlights_json() if summary_controller else []
        if not highlights_data:
            self.controller.set_status("DEBUG: No game highlights available to copy")
            return
        
        clipboard = QApplication.clipboard()
        clipboard.setText(json.dumps(highlights_data, indent=2, ensure_ascii=False))
        self.controller.set_status("DEBUG: Game highlights JSON copied to clipboard")
    
    def _debug_create_highlight_rule_test_data(self) -> None:
        """DEBUG: Prompt for filename and save analysis JSON for highlight rule tests."""
        from pathlib import Path
        import json
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        from app.views.input_dialog import InputDialog
        
        try:
            # Ensure we have an active analyzed game with CARAAnalysisData
            game_controller = self.controller.get_game_controller()
            game_model = game_controller.get_game_model()
            active_game = game_model.active_game
            
            if not active_game:
                self.controller.set_status("DEBUG: No active game")
                return
            
            if not AnalysisDataStorageService.has_analysis_data(active_game):
                self.controller.set_status("DEBUG: Game does not have CARAAnalysisData tag")
                return
            
            raw_json = AnalysisDataStorageService.get_raw_analysis_data(active_game)
            if raw_json is None:
                self.controller.set_status("DEBUG: Failed to deserialize CARAAnalysisData tag")
                return
            
            # Prompt for filename
            filename, ok = InputDialog.get_text(
                self.config,
                "Create Highlight Rule Test Data",
                "Enter filename (e.g., my_rule_case.json):",
                "",
                self
            )
            
            if not ok or not filename:
                return
            
            filename = filename.strip()
            if not filename.lower().endswith(".json"):
                filename += ".json"
            
            project_root = Path(__file__).resolve().parent.parent
            games_dir = project_root / "tests" / "highlight_rules" / "games"
            games_dir.mkdir(parents=True, exist_ok=True)
            target_path = games_dir / filename
            
            if target_path.exists():
                self.controller.set_status(f"DEBUG: File already exists: {target_path.name}")
                return
            
            data = json.loads(raw_json)
            
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.controller.set_status(f"DEBUG: Highlight test data saved to {target_path.name}")
        except json.JSONDecodeError:
            self.controller.set_status("DEBUG: Analysis data is not valid JSON")
        except Exception as exc:
            self.controller.set_status(f"DEBUG: Error creating highlight test data: {exc}")
    
    
    def _update_moves_list_menu(self) -> None:
        """Update the Moves List menu with current profiles and columns."""
        menu = self.moves_list_menu
        menu.clear()
        
        # Clear action dictionaries
        self.profile_actions.clear()
        self.column_actions.clear()
        
        # Get current profile names and active profile
        # get_profile_names() returns Default first, followed by profiles in creation order
        profile_names = self.profile_model.get_profile_names()
        active_profile_name = self.profile_model.get_active_profile_name()
        
        # Add profile toggle actions (at top)
        # Assign keyboard shortcuts 1-9 to the first 9 profiles
        for index, profile_name in enumerate(profile_names):
            profile_action = QAction(profile_name, self)
            profile_action.setCheckable(True)
            profile_action.setChecked(profile_name == active_profile_name)
            profile_action.triggered.connect(lambda checked, name=profile_name: self._on_profile_selected(name))
            
            # Assign keyboard shortcut 1-9 to first 9 profiles
            if index < 9:
                shortcut = QKeySequence(str(index + 1))
                profile_action.setShortcut(shortcut)
            
            menu.addAction(profile_action)
            self.profile_actions[profile_name] = profile_action
        
        # Add separator
        if profile_names:
            menu.addSeparator()
        
        # Save Profile action (overwrites current profile, not available for default)
        if active_profile_name != DEFAULT_PROFILE_NAME:
            save_profile_action = QAction("Save Profile", self)
            save_profile_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
            save_profile_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
            save_profile_action.triggered.connect(self._save_current_profile)
            menu.addAction(save_profile_action)
        
        # Save Profile as... action (creates new profile)
        save_profile_as_action = QAction("Save Profile as...", self)
        save_profile_as_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        save_profile_as_action.setShortcut(QKeySequence("Ctrl+Alt+P"))
        save_profile_as_action.triggered.connect(self._save_profile_as)
        menu.addAction(save_profile_as_action)
        
        # Remove Profile action (only if not default profile)
        if active_profile_name != DEFAULT_PROFILE_NAME:
            remove_profile_action = QAction("Remove Profile", self)
            remove_profile_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
            remove_profile_action.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
            remove_profile_action.triggered.connect(self._remove_profile)
            menu.addAction(remove_profile_action)
        
        # Add separator
        menu.addSeparator()
        
        # Setup Profile... action (opens dialog)
        setup_profile_action = QAction("Setup Profile...", self)
        setup_profile_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from hiding/moving this action
        setup_profile_action.triggered.connect(self._on_setup_profile)
        menu.addAction(setup_profile_action)
        
        # Add separator
        menu.addSeparator()
        
        # Add column visibility toggle actions organized into categories
        column_names = self.profile_model.get_column_names()
        column_visibility = self.profile_model.get_current_column_visibility()
        
        # Define column categories
        from app.models.column_profile_model import (
            COL_NUM, COL_WHITE, COL_BLACK, COL_COMMENT,
            COL_EVAL_WHITE, COL_EVAL_BLACK, COL_CPL_WHITE, COL_CPL_BLACK,
            COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3,
            COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3,
            COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3,
            COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_WHITE_DEPTH, COL_BLACK_DEPTH,
            COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL,
            COL_ECO, COL_OPENING, COL_FEN_WHITE, COL_FEN_BLACK
        )
        
        column_categories = {
            "Basic Columns": [COL_NUM, COL_WHITE, COL_BLACK, COL_COMMENT],
            "Evaluation Columns": [COL_EVAL_WHITE, COL_EVAL_BLACK, COL_CPL_WHITE, COL_CPL_BLACK,
                                  COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3],
            "Best Moves Columns": [
                COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3,
                COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3
            ],
            "Analysis Columns": [COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_WHITE_DEPTH, COL_BLACK_DEPTH],
            "Material Columns": [COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL],
            "Position Columns": [COL_ECO, COL_OPENING, COL_FEN_WHITE, COL_FEN_BLACK]
        }
        
        # Create submenus for each category
        categorized_columns = set()
        for category_name, category_columns in column_categories.items():
            category_menu = menu.addMenu(category_name)
            
            for column_name in category_columns:
                if column_name in column_names:
                    categorized_columns.add(column_name)
                    display_name = self.profile_model.get_column_display_name(column_name)
                    visible = column_visibility.get(column_name, True)
                    
                    column_action = QAction(display_name, self)
                    column_action.setCheckable(True)
                    column_action.setChecked(visible)
                    column_action.triggered.connect(lambda checked, name=column_name: self._on_column_toggled(name))
                    category_menu.addAction(column_action)
                    self.column_actions[column_name] = column_action
        
        # Handle any columns not in categories (for future extensibility)
        uncategorized_columns = [col for col in column_names if col not in categorized_columns]
        if uncategorized_columns:
            other_menu = menu.addMenu("Other")
            for column_name in uncategorized_columns:
                display_name = self.profile_model.get_column_display_name(column_name)
                visible = column_visibility.get(column_name, True)
                
                column_action = QAction(display_name, self)
                column_action.setCheckable(True)
                column_action.setChecked(visible)
                column_action.triggered.connect(lambda checked, name=column_name: self._on_column_toggled(name))
                other_menu.addAction(column_action)
                self.column_actions[column_name] = column_action
        
        # Add separator
        menu.addSeparator()
    
    def _on_profile_selected(self, profile_name: str) -> None:
        """Handle profile selection.
        
        Args:
            profile_name: Name of the selected profile.
        """
        # When switching profiles, we don't save the current profile's state automatically
        # The user must explicitly save using "Save Profile" if they want to persist changes
        # Just switch to the new profile
        success = self.profile_controller.set_active_profile(profile_name)
        if success:
            self.controller.set_status(f"Profile '{profile_name}' activated")
            # Update menu to reflect active profile
            self._update_moves_list_menu()
            # Update column visibility in moves list model
            self._update_moves_list_column_visibility()
        else:
            self.controller.set_status(f"Failed to activate profile '{profile_name}'")
    
    def _on_active_profile_changed(self, profile_name: str) -> None:
        """Handle active profile change from model.
        
        Args:
            profile_name: Name of the new active profile.
        """
        # Update menu to reflect active profile
        self._update_moves_list_menu()
        # Update column visibility in moves list model
        self._update_moves_list_column_visibility()
    
    def _on_profile_added(self, profile_name: str) -> None:
        """Handle profile addition from model.
        
        Args:
            profile_name: Name of the added profile.
        """
        self._update_moves_list_menu()
        self.controller.set_status(f"Profile '{profile_name}' added")
    
    def _on_profile_removed(self, profile_name: str) -> None:
        """Handle profile removal from model.
        
        Args:
            profile_name: Name of the removed profile.
        """
        self._update_moves_list_menu()
        self.controller.set_status(f"Profile '{profile_name}' removed")
    
    def _on_column_visibility_changed(self, column_name: str, visible: bool) -> None:
        """Handle column visibility change from model.
        
        Args:
            column_name: Name of the column.
            visible: True if column is visible, False otherwise.
        """
        # Update menu to reflect column visibility
        if column_name in self.column_actions:
            self.column_actions[column_name].setChecked(visible)
        
        # Update column visibility in moves list model
        self._update_moves_list_column_visibility()
    
    def _on_setup_profile(self) -> None:
        """Open the profile setup dialog."""
        from app.views.moveslist_profile_setup_dialog import MovesListProfileSetupDialog
        
        dialog = MovesListProfileSetupDialog(self.config, self.profile_controller, self)
        dialog.exec()
        
        # Refresh menu after dialog closes (in case changes were applied)
        self._update_moves_list_menu()
        
        # Reapply column order and widths in the moves list view
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            moves_view = self.detail_panel.moves_view
            moves_view._apply_column_order_and_widths()
    
    def _on_column_toggled(self, column_name: str) -> None:
        """Handle column visibility toggle.
        
        Args:
            column_name: Name of the column to toggle.
        """
        visible = self.profile_controller.toggle_column_visibility(column_name)
        display_name = self.profile_model.get_column_display_name(column_name)
        status = "shown" if visible else "hidden"
        self.controller.set_status(f"Column '{display_name}' {status}")
        
        # Update moves list model column visibility immediately
        self._update_moves_list_column_visibility()
    
    def _setup_uci_debug_callbacks(self) -> None:
        """Set up UCI debug callbacks in UCICommunicationService."""
        from app.services.uci_communication_service import set_debug_callbacks, set_debug_flags
        set_debug_callbacks(
            outbound_callback=self.get_uci_debug_outbound,
            inbound_callback=self.get_uci_debug_inbound
        )
        # Also set thread-safe flags
        set_debug_flags(
            outbound_enabled=self._uci_debug_outbound,
            inbound_enabled=self._uci_debug_inbound,
            lifecycle_enabled=self._uci_debug_lifecycle
        )
    
    def _toggle_uci_debug_outbound(self) -> None:
        """Toggle UCI outbound debug output."""
        self._uci_debug_outbound = self.debug_uci_outbound_action.isChecked()
        # Update thread-safe flag
        from app.services.uci_communication_service import set_debug_flags
        set_debug_flags(
            outbound_enabled=self._uci_debug_outbound,
            inbound_enabled=self._uci_debug_inbound,
            lifecycle_enabled=self._uci_debug_lifecycle
        )
    
    def _toggle_uci_debug_inbound(self) -> None:
        """Toggle UCI inbound debug output."""
        self._uci_debug_inbound = self.debug_uci_inbound_action.isChecked()
        # Update thread-safe flag
        from app.services.uci_communication_service import set_debug_flags
        set_debug_flags(
            outbound_enabled=self._uci_debug_outbound,
            inbound_enabled=self._uci_debug_inbound,
            lifecycle_enabled=self._uci_debug_lifecycle
        )
    
    def _toggle_uci_debug_lifecycle(self) -> None:
        """Toggle UCI lifecycle debug output."""
        self._uci_debug_lifecycle = self.debug_uci_lifecycle_action.isChecked()
        # Update thread-safe flag
        from app.services.uci_communication_service import set_debug_flags
        set_debug_flags(
            outbound_enabled=self._uci_debug_outbound,
            inbound_enabled=self._uci_debug_inbound,
            lifecycle_enabled=self._uci_debug_lifecycle
        )
    
    def get_uci_debug_outbound(self) -> bool:
        """Get current UCI outbound debug state.
        
        Returns:
            True if outbound debugging is enabled, False otherwise.
        """
        return self._uci_debug_outbound
    
    def get_uci_debug_inbound(self) -> bool:
        """Get current UCI inbound debug state.
        
        Returns:
            True if inbound debugging is enabled, False otherwise.
        """
        return self._uci_debug_inbound
    
    def _setup_ai_debug_callbacks(self) -> None:
        """Set up AI debug callbacks in AIService."""
        from app.services.ai_service import set_debug_callbacks, set_debug_flags
        set_debug_callbacks(
            outbound_callback=self.get_ai_debug_outbound,
            inbound_callback=self.get_ai_debug_inbound
        )
        # Also set thread-safe flags
        set_debug_flags(
            outbound_enabled=self._ai_debug_outbound,
            inbound_enabled=self._ai_debug_inbound
        )
    
    def _toggle_ai_debug_outbound(self) -> None:
        """Toggle AI outbound debug output."""
        self._ai_debug_outbound = self.debug_ai_outbound_action.isChecked()
        # Update thread-safe flag
        from app.services.ai_service import set_debug_flags
        set_debug_flags(
            outbound_enabled=self._ai_debug_outbound,
            inbound_enabled=self._ai_debug_inbound
        )
    
    def _toggle_ai_debug_inbound(self) -> None:
        """Toggle AI inbound debug output."""
        self._ai_debug_inbound = self.debug_ai_inbound_action.isChecked()
        # Update thread-safe flag
        from app.services.ai_service import set_debug_flags
        set_debug_flags(
            outbound_enabled=self._ai_debug_outbound,
            inbound_enabled=self._ai_debug_inbound
        )
    
    def get_ai_debug_outbound(self) -> bool:
        """Get current AI outbound debug state.
        
        Returns:
            True if outbound debugging is enabled, False otherwise.
        """
        return self._ai_debug_outbound
    
    def get_ai_debug_inbound(self) -> bool:
        """Get current AI inbound debug state.
        
        Returns:
            True if inbound debugging is enabled, False otherwise.
        """
        return self._ai_debug_inbound
    
    def get_uci_debug_lifecycle(self) -> bool:
        """Get current UCI lifecycle debug state.
        
        Returns:
            True if lifecycle debugging is enabled, False otherwise.
        """
        return self._uci_debug_lifecycle
    
    def _toggle_game_analysis_state(self) -> None:
        """Toggle game analysis state (for debugging)."""
        game_model = self.controller.get_game_controller().get_game_model()
        # Toggle the flag based on current menu action state
        new_state = self.debug_toggle_game_analysis_action.isChecked()
        game_model.set_is_game_analyzed(new_state)
    
    def _on_game_analysis_state_changed(self, is_analyzed: bool) -> None:
        """Handle game analysis state change to update menu toggle.
        
        Args:
            is_analyzed: True if game has been analyzed, False otherwise.
        """
        if hasattr(self, 'debug_toggle_game_analysis_action'):
            self.debug_toggle_game_analysis_action.setChecked(is_analyzed)
    
    
    
    def _debug_copy_deserialize_analysis_tag(self) -> None:
        """DEBUG: Copy deserialized and decompressed CARAAnalysisData tag to clipboard."""
        from PyQt6.QtWidgets import QApplication
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        
        try:
            # Get current active game
            game_controller = self.controller.get_game_controller()
            game_model = game_controller.get_game_model()
            active_game = game_model.active_game
            
            if not active_game:
                self.controller.set_status("DEBUG: No active game")
                return
            
            # Check if game has CARAAnalysisData tag
            if not AnalysisDataStorageService.has_analysis_data(active_game):
                self.controller.set_status("DEBUG: Game does not have CARAAnalysisData tag")
                return
            
            # Get raw decompressed JSON
            json_str = AnalysisDataStorageService.get_raw_analysis_data(active_game)
            
            if json_str is None:
                self.controller.set_status("DEBUG: Failed to deserialize CARAAnalysisData tag")
                return
            
            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(json_str)
            
            self.controller.set_status("DEBUG: Deserialized CARAAnalysisData copied to clipboard")
        except Exception as e:
            self.controller.set_status(f"DEBUG: Error copying analysis data: {e}")
    
    def _debug_copy_deserialize_annotation_tag(self) -> None:
        """DEBUG: Copy deserialized and decompressed CARAAnnotations tag to clipboard."""
        from PyQt6.QtWidgets import QApplication
        from app.services.annotation_storage_service import AnnotationStorageService
        
        try:
            # Get current active game
            game_controller = self.controller.get_game_controller()
            game_model = game_controller.get_game_model()
            active_game = game_model.active_game
            
            if not active_game:
                self.controller.set_status("DEBUG: No active game")
                return
            
            # Check if game has CARAAnnotations tag
            if not AnnotationStorageService.has_annotations(active_game):
                self.controller.set_status("DEBUG: Game does not have CARAAnnotations tag")
                return
            
            # Get raw decompressed JSON
            json_str = AnnotationStorageService.get_raw_annotations_data(active_game)
            
            if json_str is None:
                self.controller.set_status("DEBUG: Failed to deserialize CARAAnnotations tag")
                return
            
            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(json_str)
            
            self.controller.set_status("DEBUG: Deserialized CARAAnnotations copied to clipboard")
        except Exception as e:
            self.controller.set_status(f"DEBUG: Error copying annotation data: {e}")
    
    def _save_current_profile(self) -> None:
        """Save current column configuration to the active profile (overwrites)."""
        active_profile_name = self.profile_model.get_active_profile_name()
        
        # Cannot save default profile
        if active_profile_name == DEFAULT_PROFILE_NAME:
            self.controller.set_status("Cannot save default profile")
            return
        
        # Get current column widths and order from view and save to profile model
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            moves_view = self.detail_panel.moves_view
            if hasattr(moves_view, '_save_column_widths'):
                moves_view._save_column_widths()
            if hasattr(moves_view, '_save_column_order'):
                moves_view._save_column_order()
        
        # Update the active profile with current column configuration and persist
        success, message = self.profile_controller.update_current_profile()
        if success:
            self._update_moves_list_menu()
        self.controller.set_status(message)
    
    def _save_profile_as(self) -> None:
        """Save current column configuration as a new profile."""
        # Ask user for profile name using custom styled dialog
        from app.views.input_dialog import InputDialog
        profile_name, ok = InputDialog.get_text(
            self.config,
            "Save Profile as...",
            "Enter profile name:",
            "",
            self
        )
        
        if not ok or not profile_name:
            return
        
        # Get current column widths and order from view before creating new profile
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            moves_view = self.detail_panel.moves_view
            if hasattr(moves_view, '_save_column_widths'):
                moves_view._save_column_widths()
            if hasattr(moves_view, '_save_column_order'):
                moves_view._save_column_order()
        
        # Save profile
        success, message = self.profile_controller.add_profile(profile_name)
        if success:
            # Set the newly created profile as active
            self.profile_controller.set_active_profile(profile_name)
            self._update_moves_list_menu()
            self._update_moves_list_column_visibility()
        self.controller.set_status(message)
    
    def _remove_profile(self) -> None:
        """Remove the current active profile."""
        active_profile_name = self.profile_model.get_active_profile_name()
        
        # Cannot remove default profile
        if active_profile_name == DEFAULT_PROFILE_NAME:
            self.controller.set_status("Cannot remove default profile")
            return
        
        # Ask for confirmation using custom styled dialog
        confirmed = self._show_confirmation_dialog(
            "Remove Profile",
            f"Are you sure you want to remove profile '{active_profile_name}'?"
        )
        
        if confirmed:
            success, message = self.profile_controller.remove_profile(active_profile_name)
            if success:
                self._update_moves_list_menu()
            self.controller.set_status(message)
    
    def _on_show_metadata_toggled(self, checked: bool) -> None:
        """Handle Show Metadata toggle.
        
        Args:
            checked: True if metadata should be shown, False otherwise.
        """
        # Update PGN view to show/hide metadata
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_metadata'):
                pgn_view.set_show_metadata(checked)
                # Refresh PGN display with current text
                if hasattr(pgn_view, '_current_pgn_text'):
                    pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        status = "shown" if checked else "hidden"
        self.controller.set_status(f"Metadata {status} in PGN view")
    
    def _on_show_comments_toggled(self, checked: bool) -> None:
        """Handle Show Comments toggle.
        
        Args:
            checked: True if comments should be shown, False otherwise.
        """
        # Update PGN view to show/hide comments
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_comments'):
                pgn_view.set_show_comments(checked)
                # Refresh PGN display with current text
                if hasattr(pgn_view, '_current_pgn_text'):
                    pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        status = "shown" if checked else "hidden"
        self.controller.set_status(f"Comments {status} in PGN view")
    
    def _on_show_variations_toggled(self, checked: bool) -> None:
        """Handle Show Variations toggle.
        
        Args:
            checked: True if variations should be shown, False otherwise.
        """
        # Update PGN view to show/hide variations
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_variations'):
                pgn_view.set_show_variations(checked)
                # Refresh PGN display with current text
                if hasattr(pgn_view, '_current_pgn_text'):
                    pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        status = "shown" if checked else "hidden"
        self.controller.set_status(f"Variations {status} in PGN view")
    
    def _on_show_annotations_toggled(self, checked: bool) -> None:
        """Handle Show Annotations toggle.
        
        Args:
            checked: True if annotations should be shown, False otherwise.
        """
        # Update PGN view to show/hide annotations
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_annotations'):
                pgn_view.set_show_annotations(checked)
                # Refresh PGN display with current text
                if hasattr(pgn_view, '_current_pgn_text'):
                    pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        status = "shown" if checked else "hidden"
        self.controller.set_status(f"Annotations {status} in PGN view")
    
    def _on_show_results_toggled(self, checked: bool) -> None:
        """Handle Show Results toggle.
        
        Args:
            checked: True if results should be shown, False otherwise.
        """
        # Update PGN view to show/hide results
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_results'):
                pgn_view.set_show_results(checked)
                # Refresh PGN display with current text
                if hasattr(pgn_view, '_current_pgn_text'):
                    pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        status = "shown" if checked else "hidden"
        self.controller.set_status(f"Results {status} in PGN view")
    
    def _on_show_non_standard_tags_toggled(self, checked: bool) -> None:
        """Handle Show Non-Standard Tags toggle.
        
        Args:
            checked: True if non-standard tags (like [%evp], [%mdl]) should be shown, False otherwise.
        """
        # Update PGN view to show/hide non-standard tags
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_non_standard_tags'):
                pgn_view.set_show_non_standard_tags(checked)
                # Refresh PGN display with current text
                if hasattr(pgn_view, '_current_pgn_text'):
                    pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        status = "shown" if checked else "hidden"
        self.controller.set_status(f"Non-standard tags {status} in PGN view")
    
    def _on_remove_comments_clicked(self) -> None:
        """Handle Remove Comments menu action."""
        self._clean_pgn_element("comments")
    
    def _on_remove_variations_clicked(self) -> None:
        """Handle Remove Variations menu action."""
        self._clean_pgn_element("variations")
    
    def _on_remove_non_standard_tags_clicked(self) -> None:
        """Handle Remove Non-Standard Tags menu action."""
        self._clean_pgn_element("non_standard_tags")
    
    def _on_remove_annotations_clicked(self) -> None:
        """Handle Remove Annotations menu action."""
        self._clean_pgn_element("annotations")
    
    def _clean_pgn_element(self, element_type: str) -> None:
        """Clean a specific element from the active game's PGN.
        
        Args:
            element_type: Type of element to remove ("comments", "variations", "non_standard_tags", "annotations").
        """
        # Get active game
        game_model = self.controller.get_game_controller().get_game_model()
        game = game_model.active_game
        
        if not game:
            MessageDialog.show_warning(self.config, "No Active Game", "No game is currently active.", self)
            return
        
        # Determine element name for status message
        element_name = ""
        if element_type == "comments":
            element_name = "comments"
        elif element_type == "variations":
            element_name = "variations"
        elif element_type == "non_standard_tags":
            element_name = "non-standard tags"
        elif element_type == "annotations":
            element_name = "annotations"
        
        # Store current ply before modification
        current_ply = game_model.get_active_move_ply()
        
        # Call appropriate service method
        success = False
        
        if element_type == "comments":
            success = PgnCleaningService.remove_comments_from_game(game)
        elif element_type == "variations":
            success = PgnCleaningService.remove_variations_from_game(game)
        elif element_type == "non_standard_tags":
            success = PgnCleaningService.remove_non_standard_tags_from_game(game)
        elif element_type == "annotations":
            success = PgnCleaningService.remove_annotations_from_game(game)
        
        if not success:
            MessageDialog.show_warning(self.config, "Error", f"Failed to remove {element_name} from PGN.", self)
            return
        
        # Find the database model that contains this game and update it
        database_model = self._find_database_model_for_game(game)
        if database_model:
            database_model.update_game(game)
            # Mark database as having unsaved changes
            database_controller = self.controller.get_database_controller()
            database_controller.mark_database_unsaved(database_model)
        
        # Refresh moves list if variations were removed (game structure changed)
        game_controller = self.controller.get_game_controller()
        if element_type == "variations":
            # Variations removal changes the main line, so refresh moves list
            if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
                try:
                    moves = game_controller.extract_moves_from_game(game)
                    if moves:
                        self.detail_panel.moveslist_model.clear()
                        for move in moves:
                            self.detail_panel.moveslist_model.add_move(move)
                        # Re-apply active move ply to restore highlighting
                        self.detail_panel.moveslist_model.set_active_move_ply(current_ply)
                except Exception:
                    pass
            
            # Validate and clamp active move ply to new game length
            try:
                game_controller.validate_and_clamp_active_move_ply()
            except Exception:
                pass
        # Emit metadata_updated signal to notify views (e.g., PGN view) that PGN changed
        # This will trigger set_pgn_text and highlighting in the PGN view
        game_model.metadata_updated.emit()
        
        # For non-variations removals, sync board position and highlighting after PGN view updates
        # We need to wait for the PGN view to finish updating before navigating
        if element_type != "variations":
            from PyQt6.QtCore import QTimer
            def ensure_navigation_and_highlighting():
                # Navigate to current ply to ensure board position and highlighting are in sync
                # This triggers active_move_changed which re-applies highlighting in PGN view
                try:
                    game_controller.navigate_to_ply(current_ply)
                except Exception:
                    pass
            
            # Use a delay to ensure PGN view has finished updating and move info is extracted
            # The metadata_updated signal triggers set_pgn_text which has its own highlighting timer (100ms),
            # so we wait a bit longer to ensure everything is ready
            QTimer.singleShot(200, ensure_navigation_and_highlighting)
        
        self.controller.set_status(f"Removed {element_name} from PGN")
    
    def _find_database_model_for_game(self, game: GameData) -> Optional[DatabaseModel]:
        """Find the database model that contains the given game.
        
        Args:
            game: GameData instance to find.
            
        Returns:
            DatabaseModel that contains the game, or None if not found.
        """
        # First try the active database
        database_controller = self.controller.get_database_controller()
        active_database = database_controller.get_active_database()
        
        if active_database and active_database.find_game(game) is not None:
            return active_database
        
        # If not found, search through all databases in the panel model
        panel_model = database_controller.get_panel_model()
        if panel_model:
            all_databases = panel_model.get_all_databases()
            for identifier, info in all_databases.items():
                if info.model.find_game(game) is not None:
                    return info.model
        
        return None
    
    def _on_return_to_first_move_toggled(self, checked: bool) -> None:
        """Handle Return to PLY 0 after analysis completes toggle.
        
        Args:
            checked: True if should return to PLY 0 after analysis completes, False otherwise.
        """
        # Settings will be saved automatically on application exit
        # No immediate action needed - behavior is handled in _on_game_analysis_completed
    
    def _on_switch_to_moves_list_toggled(self, checked: bool) -> None:
        """Handle Switch to Moves List at the start of Analysis toggle.
        
        Args:
            checked: True if should switch to Moves List tab at the start of analysis, False otherwise.
        """
        # Settings will be saved automatically on application exit
        # No immediate action needed - behavior is handled in _on_game_analysis_started
    
    def _on_switch_to_summary_toggled(self, checked: bool) -> None:
        """Handle Switch to Game Summary after Analysis toggle.
        
        Args:
            checked: True if should switch to Game Summary tab after analysis, False otherwise.
        """
        # Settings will be saved automatically on application exit
    
    def _on_post_game_brilliancy_refinement_toggled(self, checked: bool) -> None:
        """Handle Post‑Game Brilliancy Refinement toggle.
        
        Args:
            checked: True if post-game brilliancy refinement is enabled, False otherwise.
        """
        # Update in-memory settings immediately
        if hasattr(self, '_settings_service'):
            self._settings_service.update_game_analysis({"post_game_brilliancy_refinement": checked})
        # Pass setting to game analysis controller
        if hasattr(self.controller, 'game_analysis_controller'):
            self.controller.game_analysis_controller.set_post_game_brilliancy_refinement(checked)
        # Settings will be saved automatically on application exit
        # No immediate action needed - behavior is handled in _on_game_analysis_completed
    
    def _on_store_analysis_results_toggled(self, checked: bool) -> None:
        """Handle Store Analysis results in PGN Tag toggle.
        
        Args:
            checked: True if storing analysis results in PGN tag is enabled, False otherwise.
        """
        # Update in-memory settings immediately so analysis controller can read it
        if hasattr(self, '_settings_service'):
            self._settings_service.update_game_analysis({"store_analysis_results_in_pgn_tag": checked})
        # Settings will be saved automatically on application exit
        # No immediate action needed - behavior is handled when analysis completes
    
    def _on_normalized_graph_toggled(self, checked: bool) -> None:
        """Handle Normalized Evaluation Graph toggle.
        
        Args:
            checked: True if normalized graph mode should be enabled, False for zero-based mode.
        """
        # Apply setting to evaluation graph widget immediately
        self._update_evaluation_graph_mode(checked)
    
    def _update_evaluation_graph_mode(self, normalized: bool) -> None:
        """Update evaluation graph mode in the detail panel.
        
        Args:
            normalized: True for normalized mode (0.00 in middle), False for zero-based mode.
        """
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'summary_view'):
            summary_view = self.detail_panel.summary_view
            if hasattr(summary_view, 'evaluation_graph'):
                summary_view.evaluation_graph.set_normalized_mode(normalized)
    
    def _on_start_manual_analysis_toggled(self, checked: bool) -> None:
        """Handle start/stop manual analysis toggle from menu.
        
        Args:
            checked: True if analysis should start, False if it should stop.
        """
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        
        if checked:
            # Check if engine is configured and assigned for manual analysis
            is_configured, error_type = self.controller.is_engine_configured_for_task(TASK_MANUAL_ANALYSIS)
            if not is_configured:
                # Uncheck the button first (before showing dialog) to prevent UI state issues
                if hasattr(self, 'start_manual_analysis_action'):
                    self.start_manual_analysis_action.blockSignals(True)
                    self.start_manual_analysis_action.setChecked(False)
                    self.start_manual_analysis_action.blockSignals(False)
                
                # Show warning message from config
                title, message = self.controller.get_engine_validation_message(error_type, TASK_MANUAL_ANALYSIS)
                MessageDialog.show_warning(self.config, title, message, self)
                return
            
            # Switch to Manual Analysis tab FIRST for immediate visual feedback
            # Do this before calling start_analysis() to ensure tab switches immediately
            if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'tab_widget'):
                # Find the index of the Manual Analysis tab
                tab_widget = self.detail_panel.tab_widget
                for i in range(tab_widget.count()):
                    if tab_widget.tabText(i) == "Manual Analysis":
                        tab_widget.setCurrentIndex(i)
                        # Force immediate UI update by processing events
                        from PyQt6.QtWidgets import QApplication
                        QApplication.processEvents()
                        break
            
            # Start analysis (this will update UI immediately, then do background work)
            manual_analysis_controller.start_analysis()
        else:
            # Stop analysis
            manual_analysis_controller.stop_analysis()
    
    def _on_add_pv_line(self) -> None:
        """Handle add PV line from menu."""
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        if not manual_analysis_controller:
            return
        
        manual_analysis_controller.add_pv_line()
    
    def _on_remove_pv_line(self) -> None:
        """Handle remove PV line from menu."""
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        if not manual_analysis_controller:
            return
        
        manual_analysis_controller.remove_pv_line()
    
    def _on_enable_miniature_preview_toggled(self) -> None:
        """Handle enable miniature preview toggle from menu."""
        enabled = self.enable_miniature_preview_action.isChecked()
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        if manual_analysis_controller:
            manual_analysis_model = manual_analysis_controller.get_analysis_model()
            if manual_analysis_model:
                manual_analysis_model.enable_miniature_preview = enabled
    
    def _on_miniature_preview_scale_factor_selected(self, scale_factor: float) -> None:
        """Handle miniature preview scale factor selection from menu.
        
        Args:
            scale_factor: Selected scale factor (1.0, 1.25, 1.5, 1.75, or 2.0).
        """
        # Uncheck all other scale factor actions
        for scale, action in self.miniature_preview_scale_actions.items():
            action.setChecked(scale == scale_factor)
        
        # Update model
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        if manual_analysis_controller:
            manual_analysis_model = manual_analysis_controller.get_analysis_model()
            if manual_analysis_model:
                manual_analysis_model.miniature_preview_scale_factor = scale_factor
    
    def _on_explore_pv1_plans_toggled(self) -> None:
        """Handle PV1 positional plans toggle."""
        checked = self.explore_pv1_plans_action.isChecked()
        if checked:
            # Uncheck other PV plan actions (mutually exclusive)
            self.explore_pv2_plans_action.setChecked(False)
            self.explore_pv3_plans_action.setChecked(False)
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_controller.set_explore_pv_plan(1)
        else:
            # Disable plan exploration
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_controller.set_explore_pv_plan(0)
    
    def _on_explore_pv2_plans_toggled(self) -> None:
        """Handle PV2 positional plans toggle."""
        checked = self.explore_pv2_plans_action.isChecked()
        if checked:
            # Uncheck other PV plan actions (mutually exclusive)
            self.explore_pv1_plans_action.setChecked(False)
            self.explore_pv3_plans_action.setChecked(False)
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_controller.set_explore_pv_plan(2)
        else:
            # Disable plan exploration
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_controller.set_explore_pv_plan(0)
    
    def _on_explore_pv3_plans_toggled(self) -> None:
        """Handle PV3 positional plans toggle."""
        checked = self.explore_pv3_plans_action.isChecked()
        if checked:
            # Uncheck other PV plan actions (mutually exclusive)
            self.explore_pv1_plans_action.setChecked(False)
            self.explore_pv2_plans_action.setChecked(False)
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_controller.set_explore_pv_plan(3)
        else:
            # Disable plan exploration
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_controller.set_explore_pv_plan(0)
    
    def _on_max_pieces_selected(self, max_pieces: int) -> None:
        """Handle max pieces selection.
        
        Args:
            max_pieces: Number of pieces to explore (1-3).
        """
        # Uncheck other max pieces actions (mutually exclusive)
        if max_pieces == 1:
            self.max_pieces_2_action.setChecked(False)
            self.max_pieces_3_action.setChecked(False)
        elif max_pieces == 2:
            self.max_pieces_1_action.setChecked(False)
            self.max_pieces_3_action.setChecked(False)
        else:  # max_pieces == 3
            self.max_pieces_1_action.setChecked(False)
            self.max_pieces_2_action.setChecked(False)
        
        # Update controller
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        manual_analysis_controller.set_max_pieces_to_explore(max_pieces)
        
        # Save to user settings
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_manual_analysis({'max_pieces_to_explore': max_pieces})
        settings_service.save()
    
    def _on_max_exploration_depth_selected(self, max_depth: int) -> None:
        """Handle max exploration depth selection.
        
        Args:
            max_depth: Maximum number of moves to show in trajectory (2-4).
        """
        # Uncheck other max depth actions (mutually exclusive)
        if max_depth == 2:
            self.max_depth_3_action.setChecked(False)
            self.max_depth_4_action.setChecked(False)
        elif max_depth == 3:
            self.max_depth_2_action.setChecked(False)
            self.max_depth_4_action.setChecked(False)
        else:  # max_depth == 4
            self.max_depth_2_action.setChecked(False)
            self.max_depth_3_action.setChecked(False)
        
        # Update controller
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        manual_analysis_controller.set_max_exploration_depth(max_depth)
        
        # Save to user settings
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_manual_analysis({'max_exploration_depth': max_depth})
        settings_service.save()
    
    def _on_hide_other_arrows_during_plan_exploration_toggled(self) -> None:
        """Handle hide other arrows during plan exploration toggle."""
        checked = self.hide_other_arrows_during_plan_exploration_action.isChecked()
        board_model = self.controller.get_board_controller().get_board_model()
        board_model.set_hide_other_arrows_during_plan_exploration(checked)
        # Force update of chessboard widget to reflect the change
        if hasattr(self, 'main_panel') and hasattr(self.main_panel, 'chessboard_view'):
            if hasattr(self.main_panel.chessboard_view, 'chessboard'):
                self.main_panel.chessboard_view.chessboard.update()
    
    def _on_trajectory_style_selected(self, use_straight_lines: bool) -> None:
        """Handle trajectory style selection (Straight or Bezier).
        
        Args:
            use_straight_lines: True for straight lines, False for bezier curves.
        """
        # Update menu check states (mutually exclusive)
        self.trajectory_style_straight_action.setChecked(use_straight_lines)
        self.trajectory_style_bezier_action.setChecked(not use_straight_lines)
        
        # Update user settings (using board_visibility to match other board settings)
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_board_visibility({'use_straight_lines': use_straight_lines})
        settings_service.save()
        
        # Reload board widget config and update
        if hasattr(self, 'main_panel') and hasattr(self.main_panel, 'chessboard_view'):
            if hasattr(self.main_panel.chessboard_view, 'chessboard'):
                chessboard = self.main_panel.chessboard_view.chessboard
                chessboard._load_config()
                chessboard.update()
    
    def _on_ai_summary_provider_selected(self, provider: str) -> None:
        """Handle AI Summary provider toggle selection."""
        use_openai = provider == "openai"
        use_anthropic = provider == "anthropic"
        
        # Update menu states to enforce exclusivity
        self.ai_summary_use_openai_action.setChecked(use_openai)
        self.ai_summary_use_anthropic_action.setChecked(use_anthropic)
        
        # Persist setting
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_ai_summary_settings({
            "use_openai_models": use_openai,
            "use_anthropic_models": use_anthropic
        })
        settings_service.save()
        
        # Refresh AI Summary dropdown (if available)
        self._refresh_ai_summary_models()
    
    def _on_ai_summary_include_analysis_toggled(self) -> None:
        """Handle AI Summary include analysis data toggle."""
        enabled = self.ai_summary_include_analysis_action.isChecked()
        
        # Persist setting
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_ai_summary_settings({
            "include_analysis_data_in_preprompt": enabled
        })
        settings_service.save()
    
    def _on_ai_summary_include_metadata_toggled(self) -> None:
        """Handle AI Summary include metadata toggle."""
        enabled = self.ai_summary_include_metadata_action.isChecked()
        
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_ai_summary_settings({
            "include_metadata_in_preprompt": enabled
        })
        settings_service.save()
    
    def _refresh_ai_summary_models(self) -> None:
        """Refresh the AI Summary model dropdown based on provider selection."""
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'ai_chat_view'):
            ai_chat_view = self.detail_panel.ai_chat_view
            if hasattr(ai_chat_view, 'refresh_model_list'):
                ai_chat_view.refresh_model_list()
    
    def _on_manual_analysis_state_changed(self, is_analyzing: bool) -> None:
        """Handle manual analysis state change to update menu toggle.
        
        Args:
            is_analyzing: True if analysis is running, False otherwise.
        """
        self._update_manual_analysis_action_states(is_analyzing, None)
    
    def _on_manual_analysis_lines_changed(self) -> None:
        """Handle manual analysis lines change to update menu actions."""
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        manual_analysis_model = manual_analysis_controller.get_analysis_model()
        self._update_manual_analysis_action_states(manual_analysis_model.is_analyzing, manual_analysis_model.multipv)
    
    def _update_manual_analysis_action_states(self, is_analyzing: bool, multipv: Optional[int] = None) -> None:
        """Update manual analysis menu action states.
        
        Args:
            is_analyzing: True if analysis is running, False otherwise.
            multipv: Current number of PV lines (optional, will be retrieved if None).
        """
        if hasattr(self, 'start_manual_analysis_action'):
            # Update start/stop action text and checked state
            if is_analyzing:
                self.start_manual_analysis_action.setText("Stop Manual Analysis")
                self.start_manual_analysis_action.setChecked(True)
            else:
                self.start_manual_analysis_action.setText("Start Manual Analysis")
                self.start_manual_analysis_action.setChecked(False)
        
        # Get multipv if not provided
        if multipv is None:
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            manual_analysis_model = manual_analysis_controller.get_analysis_model()
            multipv = manual_analysis_model.multipv
        
        # Update add/remove PV line actions
        if hasattr(self, 'add_pv_line_action'):
            # Add PV line is always enabled (can always add more lines)
            self.add_pv_line_action.setEnabled(True)
        
        if hasattr(self, 'remove_pv_line_action'):
            # Remove PV line is only enabled if we have more than 1 line
            self.remove_pv_line_action.setEnabled(multipv > 1)
    
    def _connect_column_profile_to_moves_list(self) -> None:
        """Connect column profile model to moves list model and view."""
        # Get moves list view from detail panel
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            moves_view = self.detail_panel.moves_view
            # Set column profile model on the view
            moves_view.set_column_profile_model(self.profile_model)
        
        # Also update moves list model column visibility
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            moveslist_model = self.detail_panel.moveslist_model
            column_visibility = self.profile_model.get_current_column_visibility()
            moveslist_model.set_column_visibility(column_visibility)
        
        # Ensure column visibility, order and widths are applied on startup
        # Use a small delay to ensure everything is initialized
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            from PyQt6.QtCore import QTimer
            def apply_startup_settings():
                moves_view = self.detail_panel.moves_view
                moves_view._apply_column_visibility()
                moves_view._apply_column_order_and_widths()
            QTimer.singleShot(50, apply_startup_settings)
        
        # Note: column_visibility_changed is already connected in _setup_menu_bar
        # so we don't need to connect it again here
    
    def _connect_detail_panel_tabs(self) -> None:
        """Connect detail panel tab change signal to update View menu checkmarks."""
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'tab_widget'):
            # Connect tab change signal
            self.detail_panel.tab_widget.currentChanged.connect(self._on_detail_tab_changed)
            # Set initial checkmark state
            current_index = self.detail_panel.tab_widget.currentIndex()
            self._on_detail_tab_changed(current_index)
    
    def _switch_detail_tab(self, index: int) -> None:
        """Switch to the specified detail panel tab.
        
        Args:
            index: Tab index (0=Moves List, 1=Metadata, 2=Manual Analysis, 3=Game Summary, 4=Player Stats, 5=Annotations, 6=AI Summary).
        """
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'tab_widget'):
            tab_widget = self.detail_panel.tab_widget
            if 0 <= index < tab_widget.count():
                tab_widget.setCurrentIndex(index)
    
    def _on_detail_tab_changed(self, index: int) -> None:
        """Handle detail panel tab change to update View menu checkmarks.
        
        Args:
            index: Index of the newly selected tab.
        """
        if hasattr(self, 'view_menu_actions') and 0 <= index < len(self.view_menu_actions):
            # Uncheck all actions
            for action in self.view_menu_actions:
                action.setChecked(False)
            # Check the active tab's action
            self.view_menu_actions[index].setChecked(True)
    
    def _update_moves_list_column_visibility(self) -> None:
        """Update column visibility in the moves list model."""
        # Get moves list model from detail panel
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            moveslist_model = self.detail_panel.moveslist_model
            column_visibility = self.profile_model.get_current_column_visibility()
            moveslist_model.set_column_visibility(column_visibility)
    
    def _navigate_to_next_move(self) -> None:
        """Navigate to the next move in the active game."""
        game_controller = self.controller.get_game_controller()
        success = game_controller.navigate_to_next_move()
        # Navigation updates the model, which will trigger view updates automatically
    
    def _navigate_to_previous_move(self) -> None:
        """Navigate to the previous move in the active game."""
        game_controller = self.controller.get_game_controller()
        success = game_controller.navigate_to_previous_move()
        # Navigation updates the model, which will trigger view updates automatically
    
    def _on_database_row_double_click(self, row: int, model: Optional[DatabaseModel] = None) -> None:
        """Handle double-click on database table row.
        
        Args:
            row: Row index in the database table.
            model: Optional DatabaseModel instance. If None, uses the default database model.
        """
        # Use provided model or default database model
        if model is None:
            model = self.controller.get_database_controller().get_database_model()
        
        # Get game from the model
        game = model.get_game(row)
        if game is None:
            return
        
        # Set the game as active
        self.controller.get_game_controller().set_active_game(game)
        status_message = self.controller.get_game_controller().format_active_game_status_message(game)
        if status_message:
            self.controller.set_status(status_message)
    
    def _add_engine(self) -> None:
        """Open dialog to add a new engine."""
        engine_controller = self.controller.get_engine_controller()
        dialog = EngineDialog(self.config, engine_controller, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_status("Engine added successfully")
    
    def _update_engines_menu(self) -> None:
        """Update the Engines menu with current engines and assignments."""
        menu = self.engines_menu
        # Clear existing engine submenus (keep "Add Engine..." and separator)
        for submenu in list(self.engine_submenus.values()):
            menu.removeAction(submenu.menuAction())
        self.engine_submenus.clear()
        
        # Remove "no engines" placeholder if it exists
        if self.no_engines_action is not None:
            menu.removeAction(self.no_engines_action)
            self.no_engines_action = None
        
        # Get current engines
        engines = self.engine_model.get_engines()
        
        if not engines:
            # No engines, add placeholder (only one)
            if self.no_engines_action is None:
                self.no_engines_action = QAction("(No engines configured)", self)
                self.no_engines_action.setEnabled(False)
                menu.addAction(self.no_engines_action)
            return
        
        # Get current assignments
        engine_controller = self.controller.get_engine_controller()
        game_analysis_id = engine_controller.get_engine_assignment(TASK_GAME_ANALYSIS)
        evaluation_id = engine_controller.get_engine_assignment(TASK_EVALUATION)
        manual_analysis_id = engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
        
        # Add engine submenus with assignment options
        for engine in engines:
            # Create submenu for this engine
            engine_submenu = QMenu(engine.name, self)
            
            # Apply menu styling to submenu (same as menu bar styling)
            self._apply_menu_styling(engine_submenu)
            
            # Remove Engine action
            remove_action = QAction("Remove Engine", self)
            remove_action.triggered.connect(lambda checked, eid=engine.id: self._remove_engine(eid))
            engine_submenu.addAction(remove_action)
            
            # Engine Configuration action
            config_action = QAction("Engine Configuration", self)
            config_action.triggered.connect(lambda checked, eid=engine.id: self._open_engine_configuration(eid))
            engine_submenu.addAction(config_action)
            
            engine_submenu.addSeparator()
            
            # Set as Game Analysis Engine
            game_analysis_action = QAction("Set as Game Analysis Engine", self)
            game_analysis_action.setCheckable(True)
            game_analysis_action.setChecked(game_analysis_id == engine.id)
            game_analysis_action.triggered.connect(lambda checked, eid=engine.id: self._set_engine_assignment(TASK_GAME_ANALYSIS, eid))
            engine_submenu.addAction(game_analysis_action)
            
            # Set as Evaluation Engine
            evaluation_action = QAction("Set as Evaluation Engine", self)
            evaluation_action.setCheckable(True)
            evaluation_action.setChecked(evaluation_id == engine.id)
            evaluation_action.triggered.connect(lambda checked, eid=engine.id: self._set_engine_assignment(TASK_EVALUATION, eid))
            engine_submenu.addAction(evaluation_action)
            
            # Set as Manual Analysis Engine
            manual_analysis_action = QAction("Set as Manual Analysis Engine", self)
            manual_analysis_action.setCheckable(True)
            manual_analysis_action.setChecked(manual_analysis_id == engine.id)
            manual_analysis_action.triggered.connect(lambda checked, eid=engine.id: self._set_engine_assignment(TASK_MANUAL_ANALYSIS, eid))
            engine_submenu.addAction(manual_analysis_action)
            
            # Add submenu to main menu and store reference
            menu.addMenu(engine_submenu)
            self.engine_submenus[engine.id] = engine_submenu
    
    def _on_engine_added(self, engine_id: str) -> None:
        """Handle engine addition.
        
        Args:
            engine_id: ID of the added engine.
        """
        self._update_engines_menu()
        self.controller.set_status(f"Engine added")
    
    def _on_engine_removed(self, engine_id: str) -> None:
        """Handle engine removal.
        
        Args:
            engine_id: ID of the removed engine.
        """
        self._update_engines_menu()
        self.controller.set_status(f"Engine removed")
    
    def _remove_engine(self, engine_id: str) -> None:
        """Remove an engine.
        
        Args:
            engine_id: ID of the engine to remove.
        """
        engine = self.engine_model.get_engine(engine_id)
        if not engine:
            return
        
        # Ask for confirmation using custom styled dialog
        confirmed = self._show_confirmation_dialog(
            "Remove Engine",
            f"Are you sure you want to remove engine '{engine.name}'?"
        )
        
        if confirmed:
            success, message = self.controller.get_engine_controller().remove_engine(engine_id)
            if success:
                self.controller.set_status(message)
            else:
                MessageDialog.show_warning(self.config, "Remove Engine Failed", message, self)
    
    def _show_confirmation_dialog(self, title: str, message: str) -> bool:
        """Show a styled confirmation dialog.
        
        Args:
            title: Dialog title.
            message: Confirmation message.
            
        Returns:
            True if user confirmed (Yes), False if cancelled (No).
        """
        from app.views.confirmation_dialog import ConfirmationDialog
        return ConfirmationDialog.show_confirmation(self.config, title, message, self)
    
    def _open_engine_configuration(self, engine_id: str) -> None:
        """Open engine configuration dialog.
        
        Args:
            engine_id: ID of the engine to configure.
        """
        dialog = EngineConfigurationDialog(
            self.config,
            engine_id,
            self.controller.get_engine_controller(),
            self
        )
        dialog.exec()
    
    def _set_engine_assignment(self, task: str, engine_id: str) -> None:
        """Set engine assignment for a task.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            engine_id: Engine ID to assign.
        """
        success, message = self.controller.get_engine_controller().set_engine_assignment(task, engine_id)
        if success:
            self.controller.set_status(message)
            # Menu will update automatically via assignment_changed signal
        else:
            MessageDialog.show_warning(self.config, "Set Engine Assignment Failed", message, self)
    
    def _load_user_settings(self) -> None:
        """Load user settings and apply them to the UI.
        
        Settings are loaded in the same order as they appear in the menu structure.
        """
        # Get singleton service instance (all components use the same instance)
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings = settings_service.get_settings()
        
        # Store settings service reference for saving later
        self._settings_service = settings_service
        
        # Update controller with settings service (should already be the same instance)
        self.controller.user_settings_service = settings_service
        # Reload settings in game analysis controller
        self.controller.game_analysis_controller.user_settings_service = settings_service
        self.controller.game_analysis_controller.reload_settings()
        
        board_model = self.controller.get_board_controller().get_board_model()
        board_visibility = settings.get("board_visibility", {})
        
        # Load annotation layer visibility
        show_annotations_layer = board_visibility.get("show_annotations_layer", True)
        if self.controller and self.controller.get_annotation_controller():
            annotation_model = self.controller.get_annotation_controller().get_annotation_model()
            # Set visibility (this will emit signal if changed)
            annotation_model.set_show_annotations(show_annotations_layer)
            # Connect signal to update menu (only connect once)
            try:
                annotation_model.annotations_visibility_changed.disconnect(self._on_annotations_layer_visibility_changed)
            except (TypeError, RuntimeError):
                pass  # Not connected yet, that's fine
            annotation_model.annotations_visibility_changed.connect(self._on_annotations_layer_visibility_changed)
            # Update menu state
            if hasattr(self, 'show_annotations_layer_action'):
                self.show_annotations_layer_action.setChecked(show_annotations_layer)
        
        # ===== BOARD MENU SETTINGS (in menu order) =====
        # Show Game Info
        show_game_info = board_visibility.get("show_game_info", True)
        board_model.set_show_game_info(show_game_info)
        self._update_game_info_action_state(show_game_info)
        
        # Show Coordinates
        show_coordinates = board_visibility.get("show_coordinates", True)
        board_model.set_show_coordinates(show_coordinates)
        self._update_coordinates_action_state(show_coordinates)
        
        # Show Turn Indicator
        show_turn_indicator = board_visibility.get("show_turn_indicator", True)
        board_model.set_show_turn_indicator(show_turn_indicator)
        self._update_turn_indicator_action_state(show_turn_indicator)
        
        # Show Material
        show_material_widget = board_visibility.get("show_material_widget", False)
        board_model.set_show_material_widget(show_material_widget)
        self._update_material_widget_action_state(show_material_widget)
        
        # Show Evaluation Bar
        show_evaluation_bar = board_visibility.get("show_evaluation_bar", False)
        board_model.set_show_evaluation_bar(show_evaluation_bar)
        self._update_evaluation_bar_action_state(show_evaluation_bar)
        # If evaluation bar is visible, start evaluation (this handles the case where
        # the app starts with the bar already visible from saved settings)
        if show_evaluation_bar:
            # Use a small delay to ensure board model is fully initialized
            QTimer.singleShot(100, self._start_evaluation_if_bar_visible)
        
        # Show Played Move
        show_playedmove_arrow = board_visibility.get("show_playedmove_arrow", True)
        board_model.set_show_playedmove_arrow(show_playedmove_arrow)
        self._update_playedmove_arrow_action_state(show_playedmove_arrow)
        
        # Show Best Next Move
        show_bestnextmove_arrow = board_visibility.get("show_bestnextmove_arrow", True)
        board_model.set_show_bestnextmove_arrow(show_bestnextmove_arrow)
        self._update_bestnextmove_arrow_action_state(show_bestnextmove_arrow)
        
        # Show Next Best Move (PV2)
        show_pv2_arrow = board_visibility.get("show_pv2_arrow", True)
        board_model.set_show_pv2_arrow(show_pv2_arrow)
        self._update_pv2_arrow_action_state(show_pv2_arrow)
        
        # Show Next Best Move (PV3)
        show_pv3_arrow = board_visibility.get("show_pv3_arrow", True)
        board_model.set_show_pv3_arrow(show_pv3_arrow)
        self._update_pv3_arrow_action_state(show_pv3_arrow)
        
        # Show Best Alternative Move
        show_bestalternativemove_arrow = board_visibility.get("show_bestalternativemove_arrow", True)
        board_model.set_show_bestalternativemove_arrow(show_bestalternativemove_arrow)
        self._update_bestalternativemove_arrow_action_state(show_bestalternativemove_arrow)
        
        # Show Annotations Layer (already loaded above, just ensure signal is connected)
        # Signal connection is done above in the annotation layer loading section
        
        # Path trajectory style
        use_straight_lines = board_visibility.get("use_straight_lines")
        if use_straight_lines is None:
            # Fallback to config default
            positional_plans_config = self.config.get('ui', {}).get('panels', {}).get('main', {}).get('board', {}).get('positional_plans', {})
            use_straight_lines = positional_plans_config.get('use_straight_lines', False)
        if hasattr(self, 'trajectory_style_straight_action') and hasattr(self, 'trajectory_style_bezier_action'):
            self.trajectory_style_straight_action.setChecked(use_straight_lines)
            self.trajectory_style_bezier_action.setChecked(not use_straight_lines)
        
        # ===== PGN MENU SETTINGS (in menu order) =====
        # Load PGN visibility settings
        pgn_visibility = settings.get("pgn_visibility", {})
        show_metadata = pgn_visibility.get("show_metadata", True)
        show_comments = pgn_visibility.get("show_comments", True)
        show_variations = pgn_visibility.get("show_variations", True)
        show_annotations = pgn_visibility.get("show_annotations", True)
        show_results = pgn_visibility.get("show_results", True)
        show_non_standard_tags = pgn_visibility.get("show_non_standard_tags", False)
        
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, 'set_show_metadata'):
                pgn_view.set_show_metadata(show_metadata)
            if hasattr(pgn_view, 'set_show_comments'):
                pgn_view.set_show_comments(show_comments)
            if hasattr(pgn_view, 'set_show_variations'):
                pgn_view.set_show_variations(show_variations)
            if hasattr(pgn_view, 'set_show_annotations'):
                pgn_view.set_show_annotations(show_annotations)
            if hasattr(pgn_view, 'set_show_results'):
                pgn_view.set_show_results(show_results)
            if hasattr(pgn_view, 'set_show_non_standard_tags'):
                pgn_view.set_show_non_standard_tags(show_non_standard_tags)
            # Refresh PGN display if there's current text
            if hasattr(pgn_view, '_current_pgn_text') and pgn_view._current_pgn_text:
                pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        # Update menu toggle states
        self.show_metadata_action.setChecked(show_metadata)
        self.show_comments_action.setChecked(show_comments)
        self.show_variations_action.setChecked(show_variations)
        self.show_annotations_action.setChecked(show_annotations)
        self.show_results_action.setChecked(show_results)
        self.show_non_standard_tags_action.setChecked(show_non_standard_tags)
        
        # ===== GAME ANALYSIS MENU SETTINGS (in menu order) =====
        game_analysis_settings = settings.get("game_analysis", {})
        
        # Normalized Evaluation Graph
        normalized_graph = game_analysis_settings.get("normalized_evaluation_graph", False)
        if hasattr(self, 'normalized_graph_action'):
            self.normalized_graph_action.setChecked(normalized_graph)
            # Apply setting to evaluation graph widget
            self._update_evaluation_graph_mode(normalized_graph)
        
        # Post-Game Brilliancy Refinement
        post_game_brilliancy_refinement = game_analysis_settings.get("post_game_brilliancy_refinement", False)
        if hasattr(self, 'post_game_brilliancy_refinement_action'):
            self.post_game_brilliancy_refinement_action.setChecked(post_game_brilliancy_refinement)
        # Pass setting to game analysis controller
        if hasattr(self.controller, 'game_analysis_controller'):
            self.controller.game_analysis_controller.set_post_game_brilliancy_refinement(post_game_brilliancy_refinement)
        
        # Return to PLY 0 after analysis completes
        return_to_first_move = game_analysis_settings.get("return_to_first_move_after_analysis", False)
        if hasattr(self, 'return_to_first_move_action'):
            self.return_to_first_move_action.setChecked(return_to_first_move)
        
        # Switch to Moves List at the start of Analysis
        switch_to_moves_list = game_analysis_settings.get("switch_to_moves_list_at_start_of_analysis", True)
        if hasattr(self, 'switch_to_moves_list_action'):
            self.switch_to_moves_list_action.setChecked(switch_to_moves_list)
        
        # Switch to Game Summary after Analysis
        switch_to_summary = game_analysis_settings.get("switch_to_summary_after_analysis", False)
        if hasattr(self, 'switch_to_summary_action'):
            self.switch_to_summary_action.setChecked(switch_to_summary)
        
        # Store Analysis results in PGN Tag
        store_analysis_results = game_analysis_settings.get("store_analysis_results_in_pgn_tag", False)
        if hasattr(self, 'store_analysis_results_action'):
            self.store_analysis_results_action.setChecked(store_analysis_results)
        
        # ===== MANUAL ANALYSIS MENU SETTINGS (in menu order) =====
        manual_analysis_settings = settings.get("manual_analysis", {})
        
        # Enable miniature preview
        enable_miniature_preview = manual_analysis_settings.get("enable_miniature_preview", True)
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        if manual_analysis_controller:
            manual_analysis_model = manual_analysis_controller.get_analysis_model()
            if manual_analysis_model:
                manual_analysis_model.enable_miniature_preview = enable_miniature_preview
        if hasattr(self, 'enable_miniature_preview_action'):
            self.enable_miniature_preview_action.setChecked(enable_miniature_preview)
        
        # Miniature preview scale factor
        scale_factor = manual_analysis_settings.get("miniature_preview_scale_factor", 1.0)
        if manual_analysis_controller:
            manual_analysis_model = manual_analysis_controller.get_analysis_model()
            if manual_analysis_model:
                manual_analysis_model.miniature_preview_scale_factor = scale_factor
        if hasattr(self, 'miniature_preview_scale_actions'):
            # Check the appropriate scale factor action
            for scale, action in self.miniature_preview_scale_actions.items():
                action.setChecked(abs(scale - scale_factor) < 0.01)  # Use small epsilon for float comparison
        
        # Max number of pieces to explore
        max_pieces = manual_analysis_settings.get("max_pieces_to_explore", 1)
        if manual_analysis_controller:
            manual_analysis_controller.set_max_pieces_to_explore(max_pieces)
        if hasattr(self, 'max_pieces_1_action'):
            self.max_pieces_1_action.setChecked(max_pieces == 1)
            self.max_pieces_2_action.setChecked(max_pieces == 2)
            self.max_pieces_3_action.setChecked(max_pieces == 3)
        
        # Max Exploration depth
        max_depth = manual_analysis_settings.get("max_exploration_depth", 2)
        if manual_analysis_controller:
            manual_analysis_controller.set_max_exploration_depth(max_depth)
        if hasattr(self, 'max_depth_2_action'):
            self.max_depth_2_action.setChecked(max_depth == 2)
            self.max_depth_3_action.setChecked(max_depth == 3)
            self.max_depth_4_action.setChecked(max_depth == 4)
        
        # Hide other arrows during plan exploration
        hide_other_arrows_during_plan_exploration = board_visibility.get("hide_other_arrows_during_plan_exploration", False)
        board_model.set_hide_other_arrows_during_plan_exploration(hide_other_arrows_during_plan_exploration)
        if hasattr(self, 'hide_other_arrows_during_plan_exploration_action'):
            self.hide_other_arrows_during_plan_exploration_action.setChecked(hide_other_arrows_during_plan_exploration)
        
        # ===== AI SUMMARY MENU SETTINGS =====
        ai_summary_settings = settings.get("ai_summary", {})
        use_openai = ai_summary_settings.get("use_openai_models", True)
        use_anthropic = ai_summary_settings.get("use_anthropic_models", False)
        if use_openai == use_anthropic:
            use_openai = True
            use_anthropic = False
        if hasattr(self, 'ai_summary_use_openai_action'):
            self.ai_summary_use_openai_action.setChecked(use_openai)
        if hasattr(self, 'ai_summary_use_anthropic_action'):
            self.ai_summary_use_anthropic_action.setChecked(use_anthropic)
        
        # Include Analysis Data in Pre-Prompt toggle
        include_analysis_data = ai_summary_settings.get("include_analysis_data_in_preprompt", False)
        if hasattr(self, 'ai_summary_include_analysis_action'):
            self.ai_summary_include_analysis_action.setChecked(include_analysis_data)
        
        include_metadata = ai_summary_settings.get("include_metadata_in_preprompt", True)
        if hasattr(self, 'ai_summary_include_metadata_action'):
            self.ai_summary_include_metadata_action.setChecked(include_metadata)
        
        # ===== ENGINES MENU SETTINGS =====
        # Load engines settings
        engines_data = settings.get("engines", [])
        engine_model = self.controller.get_engine_controller().get_engine_model()
        engine_model.load_engines(engines_data)
        
        # Load engine assignments
        assignments_data = settings.get("engine_assignments", {})
        engine_model.load_assignments(assignments_data)
        
        self._update_engines_menu()
    
    def _save_user_settings(self) -> None:
        """Save current user settings to file.
        
        Collects settings from views and delegates to controller
        to persist all settings to disk.
        """
        # Collect PGN visibility settings from view
        pgn_visibility_settings = None
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, '_show_metadata'):
                pgn_visibility_settings = {
                    "show_metadata": pgn_view._show_metadata,
                    "show_comments": pgn_view._show_comments if hasattr(pgn_view, '_show_comments') else True,
                    "show_variations": pgn_view._show_variations if hasattr(pgn_view, '_show_variations') else True,
                    "show_annotations": pgn_view._show_annotations if hasattr(pgn_view, '_show_annotations') else True,
                    "show_results": pgn_view._show_results if hasattr(pgn_view, '_show_results') else True,
                    "show_non_standard_tags": pgn_view._show_non_standard_tags if hasattr(pgn_view, '_show_non_standard_tags') else False
                }
        
        # Collect game analysis settings from view
        game_analysis_settings = None
        if hasattr(self, 'return_to_first_move_action'):
            game_analysis_settings = {
                "return_to_first_move_after_analysis": self.return_to_first_move_action.isChecked() if hasattr(self, 'return_to_first_move_action') else False,
                "switch_to_moves_list_at_start_of_analysis": self.switch_to_moves_list_action.isChecked() if hasattr(self, 'switch_to_moves_list_action') else True,
                "switch_to_summary_after_analysis": self.switch_to_summary_action.isChecked() if hasattr(self, 'switch_to_summary_action') else False,
                "normalized_evaluation_graph": self.normalized_graph_action.isChecked() if hasattr(self, 'normalized_graph_action') else False,
                "post_game_brilliancy_refinement": self.post_game_brilliancy_refinement_action.isChecked() if hasattr(self, 'post_game_brilliancy_refinement_action') else False,
                "store_analysis_results_in_pgn_tag": self.store_analysis_results_action.isChecked() if hasattr(self, 'store_analysis_results_action') else False
            }
        
        # Persist AI summary provider toggles before saving
        if hasattr(self, 'ai_summary_use_openai_action'):
            ai_summary_settings = {
                "use_openai_models": self.ai_summary_use_openai_action.isChecked(),
                "use_anthropic_models": self.ai_summary_use_anthropic_action.isChecked() if hasattr(self, 'ai_summary_use_anthropic_action') else False
            }
            settings_service = getattr(self, '_settings_service', None)
            if settings_service is None:
                from app.services.user_settings_service import UserSettingsService
                settings_service = UserSettingsService.get_instance()
            settings_service.update_ai_summary_settings(ai_summary_settings)
        
        # Delegate to controller for business logic
        self.controller.save_user_settings(pgn_visibility_settings, game_analysis_settings)
    
    def _start_game_analysis(self) -> None:
        """Handle start game analysis from menu."""
        # Check if engine is configured and assigned for game analysis
        is_configured, error_type = self.controller.is_engine_configured_for_task(TASK_GAME_ANALYSIS)
        if not is_configured:
            title, message = self.controller.get_engine_validation_message(error_type, TASK_GAME_ANALYSIS)
            MessageDialog.show_warning(self.config, title, message, self)
            return
        
        game_analysis_controller = self.controller.get_game_analysis_controller()
        
        # Check if moves list model is set
        if game_analysis_controller.moves_list_model is None:
            # Try to set it now if detail panel exists
            if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
                self.controller.set_moves_list_model(self.detail_panel.moveslist_model)
            else:
                from app.services.progress_service import ProgressService
                progress_service = ProgressService.get_instance()
                progress_service.set_status("Error: Moves list model not available")
                return
        
        # Check if there's an active game
        game_model = self.controller.get_game_controller().get_game_model()
        if game_model.active_game is None:
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            progress_service.set_status("Error: No active game to analyze")
            return
        
        success, error_message = game_analysis_controller.start_analysis()
        if success:
            # Update menu actions
            self.start_game_analysis_action.setEnabled(False)
            self.cancel_game_analysis_action.setEnabled(True)
            
            # Switch to Moves List tab if enabled (do this immediately after successful start)
            if hasattr(self, 'switch_to_moves_list_action') and self.switch_to_moves_list_action.isChecked():
                if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'tab_widget'):
                    # Find Moves List tab index (should be index 0: Moves List=0, Metadata=1, Manual Analysis=2, Game Summary=3)
                    tab_widget = self.detail_panel.tab_widget
                    for i in range(tab_widget.count()):
                        if tab_widget.tabText(i) == "Moves List":
                            tab_widget.setCurrentIndex(i)
                            break
            
            # Connect to analysis signals
            game_analysis_controller.analysis_started.connect(self._on_game_analysis_started)
            game_analysis_controller.analysis_completed.connect(self._on_game_analysis_completed)
            game_analysis_controller.analysis_cancelled.connect(self._on_game_analysis_cancelled)
            game_analysis_controller.analysis_progress.connect(self._on_game_analysis_progress)
            game_analysis_controller.move_analyzed.connect(self._on_move_analyzed)
        else:
            # Report specific error
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            error_msg = error_message or "Unknown error"
            progress_service.set_status(f"Error: Could not start game analysis - {error_msg}")
    
    def _cancel_game_analysis(self) -> None:
        """Handle cancel game analysis from menu or Escape key."""
        game_analysis_controller = self.controller.get_game_analysis_controller()
        game_analysis_controller.cancel_analysis()
    
    def _on_bulk_analyze_database(self) -> None:
        """Handle bulk analyze database from menu."""
        from app.views.bulk_analysis_dialog import BulkAnalysisDialog
        
        # Get active database
        database_panel = self.database_panel
        if not database_panel:
            dialog = MessageDialog(
                self.config,
                "No Database",
                "No database is currently open.",
                message_type="information",
                parent=self
            )
            dialog.exec()
            return
        
        active_info = database_panel.get_active_database_info()
        if not active_info:
            dialog = MessageDialog(
                self.config,
                "No Active Database",
                "Please open a database first.",
                message_type="information",
                parent=self
            )
            dialog.exec()
            return
        
        database_model = active_info.get('model')
        if not database_model:
            return
        
        # Get selected games from database panel (if any)
        selected_games = []
        if active_info.get('model') == database_model:
            selected_indices = database_panel.get_selected_game_indices()
            for idx in selected_indices:
                game = database_model.get_game(idx)
                if game:
                    selected_games.append(game)
        
        # Get bulk analysis controller
        bulk_analysis_controller = self.controller.get_bulk_analysis_controller()
        
        # Create and show dialog
        dialog = BulkAnalysisDialog(
            self.config,
            bulk_analysis_controller,
            selected_games=selected_games if selected_games else None,
            parent=self
        )
        dialog.exec()
    
    def _open_classification_settings(self) -> None:
        """Open the classification settings dialog."""
        classification_controller = self.controller.get_move_classification_controller()
        
        dialog = ClassificationSettingsDialog(
            self.config,
            classification_controller,
            self
        )
        dialog.exec()
    
    def _on_game_analysis_started(self) -> None:
        """Handle game analysis started signal."""
        # Update menu actions
        self.start_game_analysis_action.setEnabled(False)
        self.cancel_game_analysis_action.setEnabled(True)
        # Note: Tab switching is handled directly in _start_game_analysis() after start_analysis() succeeds
        # because the signal is emitted synchronously before we connect to it
    
    def _on_game_analysis_completed(self) -> None:
        """Handle game analysis completed signal."""
        # Update menu actions
        self.start_game_analysis_action.setEnabled(True)
        self.cancel_game_analysis_action.setEnabled(False)
        # Disconnect from signals
        game_analysis_controller = self.controller.get_game_analysis_controller()
        game_analysis_controller.analysis_started.disconnect(self._on_game_analysis_started)
        game_analysis_controller.analysis_completed.disconnect(self._on_game_analysis_completed)
        game_analysis_controller.analysis_cancelled.disconnect(self._on_game_analysis_cancelled)
        game_analysis_controller.analysis_progress.disconnect(self._on_game_analysis_progress)
        game_analysis_controller.move_analyzed.disconnect(self._on_move_analyzed)
        
        # Handle post-analysis actions based on settings
        # Return to PLY 0 if enabled
        if hasattr(self, 'return_to_first_move_action') and self.return_to_first_move_action.isChecked():
            game_controller = self.controller.get_game_controller()
            game_controller.navigate_to_ply(0)  # Navigate to starting position (ply 0)
        
        # Switch to Game Summary tab if enabled
        if hasattr(self, 'switch_to_summary_action') and self.switch_to_summary_action.isChecked():
            if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'tab_widget'):
                # Find Game Summary tab index (should be index 3: Moves List=0, Metadata=1, Manual Analysis=2, Game Summary=3)
                tab_widget = self.detail_panel.tab_widget
                for i in range(tab_widget.count()):
                    if tab_widget.tabText(i) == "Game Summary":
                        tab_widget.setCurrentIndex(i)
                        break
    
    def _on_game_analysis_cancelled(self) -> None:
        """Handle game analysis cancelled signal."""
        # Update menu actions
        self.start_game_analysis_action.setEnabled(True)
        self.cancel_game_analysis_action.setEnabled(False)
        # Disconnect from signals
        game_analysis_controller = self.controller.get_game_analysis_controller()
        game_analysis_controller.analysis_started.disconnect(self._on_game_analysis_started)
        game_analysis_controller.analysis_completed.disconnect(self._on_game_analysis_completed)
        game_analysis_controller.analysis_cancelled.disconnect(self._on_game_analysis_cancelled)
        game_analysis_controller.analysis_progress.disconnect(self._on_game_analysis_progress)
        game_analysis_controller.move_analyzed.disconnect(self._on_move_analyzed)
    
    def _on_game_analysis_progress(self, current_move: int, total_moves: int, depth: int,
                                   centipawns: float, engine_name: str, threads: int, elapsed_ms: int,
                                   avg_depth: float = 0.0, avg_seldepth: float = 0.0, movetime_ms: int = 0) -> None:
        """Handle game analysis progress update.
        
        Args:
            current_move: Current move number being analyzed.
            total_moves: Total number of moves to analyze.
            depth: Current search depth.
            centipawns: Current evaluation in centipawns.
            engine_name: Engine name.
            threads: Number of threads.
            elapsed_ms: Elapsed time in milliseconds.
            avg_depth: Average depth from completed moves (0.0 if not available).
            avg_seldepth: Average seldepth from completed moves (0.0 if not available).
            movetime_ms: Movetime limit in milliseconds.
        """
        # Update status bar with progress
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Format evaluation
        eval_str = f"{centipawns/100.0:+.1f}" if centipawns != 0 else "0.0"
        
        # Calculate estimated remaining time
        estimated_remaining_time = None
        if current_move > 0 and total_moves > current_move:
            elapsed_seconds = elapsed_ms / 1000.0
            remaining_moves = total_moves - current_move
            
            if elapsed_seconds > 0:
                # Estimate based on average time per completed move
                # current_move is the move currently being analyzed (1-indexed)
                # So we've completed approximately (current_move - 1) moves
                # Use max(1, current_move - 1) to avoid division by zero and get a more accurate estimate
                completed_moves = max(1, current_move - 1)
                avg_time_per_move = elapsed_seconds / completed_moves
                estimated_remaining_seconds = avg_time_per_move * remaining_moves
                
                if estimated_remaining_seconds > 0:
                    # Format time
                    estimated_remaining_time = self._format_estimated_time(estimated_remaining_seconds)
        
        # Format movetime for display
        movetime_str = ""
        if movetime_ms > 0:
            if movetime_ms < 1000:
                movetime_str = f"{movetime_ms}ms"
            else:
                movetime_seconds = movetime_ms / 1000.0
                if movetime_seconds < 60:
                    movetime_str = f"{movetime_seconds:.1f}s"
                else:
                    movetime_minutes = movetime_seconds / 60.0
                    movetime_str = f"{movetime_minutes:.1f}m"
        
        # Format status message
        status_parts = [
            f"Game Analysis: Move {current_move}/{total_moves}",
            f"Depth: {depth}",
            f"Eval: {eval_str}",
            f"Engine: {engine_name}",
            f"Threads: {threads}"
        ]
        
        # Add movetime if available
        if movetime_str:
            status_parts.append(f"Movetime: {movetime_str}")
        
        # Add average depth if available (only if we have completed moves with depth data)
        if avg_depth > 0:
            status_parts.append(f"Avg Depth: {int(avg_depth)}")
        
        # Add average seldepth if available (only if we have completed moves with seldepth data)
        if avg_seldepth > 0:
            status_parts.append(f"Avg SelDepth: {int(avg_seldepth)}")
        
        if estimated_remaining_time:
            status_parts.append(f"Est. remaining: {estimated_remaining_time}")
        
        status = " | ".join(status_parts)
        progress_service.set_status(status)
        
        # Update progress bar
        if total_moves > 0:
            percent = int((current_move / total_moves) * 100)
            progress_service.report_progress(status, percent)
    
    def _format_estimated_time(self, seconds: float) -> str:
        """Format estimated time in seconds to human-readable string.
        
        Args:
            seconds: Time in seconds.
            
        Returns:
            Formatted time string (e.g., "5s", "2m 30s", "1h 15m 20s").
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            if secs == 0:
                return f"{minutes}m"
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            parts = [f"{hours}h"]
            if minutes > 0:
                parts.append(f"{minutes}m")
            if secs > 0:
                parts.append(f"{secs}s")
            return " ".join(parts)
    
    def _on_move_analyzed(self, row_index: int) -> None:
        """Handle move analyzed signal - scroll to the analyzed move and force repaint.
        
        Args:
            row_index: Row index of the analyzed move.
        """
        # Scroll to the analyzed move in the moves list view and force update
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            moves_view = self.detail_panel.moves_view
            if hasattr(moves_view, 'moves_table') and hasattr(moves_view, '_moveslist_model'):
                model = moves_view._moveslist_model
                table = moves_view.moves_table
                if model and 0 <= row_index < model.rowCount():
                    # Qt automatically updates the view when dataChanged is emitted
                    # We only need to scroll to the analyzed row
                    from PyQt6.QtCore import QTimer
                    from PyQt6.QtWidgets import QTableView
                    
                    def scroll_to_row():
                        # Scroll to the row - Qt handles view updates automatically
                        visible_col = 0
                        if model.columnCount() > 0:
                            index = model.index(row_index, visible_col)
                            if index.isValid():
                                table.scrollTo(
                                    index,
                                    QTableView.ScrollHint.EnsureVisible
                                )
                    
                    # Use QTimer.singleShot(0) to defer until after signal processing
                    QTimer.singleShot(0, scroll_to_row)


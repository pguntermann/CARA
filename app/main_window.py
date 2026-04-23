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
from app.views.dialogs.engine_dialog import EngineDialog
from app.views.dialogs.engine_configuration_dialog import EngineConfigurationDialog
from app.views.dialogs.classification_settings_dialog import ClassificationSettingsDialog
from app.views.dialogs.about_dialog import AboutDialog
from app.views.dialogs.inline_content_dialog import InlineContentDialog
from app.views.dialogs.message_dialog import MessageDialog
from app.views.dialogs.confirmation_dialog import ConfirmationDialog
from app.controllers.app_controller import AppController
from app.input.shortcut_manager import ShortcutManager
from app.models.column_profile_model import DEFAULT_PROFILE_NAME
from app.models.database_model import DatabaseModel, GameData
from app.controllers.engine_controller import TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS, TASK_BRILLIANCY_DETECTION
from app.services.pgn_cleaning_service import PgnCleaningService
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.tooltip_utils import wrap_tooltip_text
from typing import Dict, Any, Optional, List


class MainWindow(QMainWindow):
    """Main application window with four distinct sections."""
    
    def __init__(self, config: Dict[str, Any], *, active_style_ref: str = "") -> None:
        """Initialize the main window.
        
        Args:
            config: Configuration dictionary loaded from ConfigLoader.
            active_style_ref: The currently active style config reference that was used to
                load ``config`` (e.g. from persisted user settings at startup). Used to
                sync the View → Theme menu without re-reading settings from disk.
        """
        super().__init__()
        self.config = config
        self._active_style_ref = str(active_style_ref or "")
        self._menubar_action_icon_svgs: Dict[Any, str] = {}

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
        
        # First-run welcome dialog (deferred until the window is shown).
        self._welcome_dialog_pending = False
        self._welcome_dialog_done = False
        self._welcome_dialog_title = ""
        self._welcome_dialog_message = ""
        
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
        app = QApplication.instance()
        if app:
            from app.views.style.tooltip import apply_tooltip_styling

            apply_tooltip_styling(app, self.config)
    
    def _setup_menu_bar(self) -> None:
        """Setup the menu bar with menu items."""
        
        # Debug log
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.debug("Setting up menus")
        
        menu_bar = self.menuBar()
        
        # Apply menu bar styling from config
        self._apply_menu_bar_styling(menu_bar)
        
        # Setup each menu section (definitions live in app/views/menus/)
        from app.views.menus.menu_bar import setup_menu_bar as _setup_menu_bar_definitions

        _setup_menu_bar_definitions(self, menu_bar)
        self._connect_menu_icon_color_scheme_refresh()

    def _setup_theme_menu(self, parent_menu: QMenu) -> None:
        """Add a View → Theme submenu.

        Theme discovery/loading is handled via ThemeService; this method only wires UI actions.
        """
        from PyQt6.QtGui import QActionGroup
        from app.services.theme_service import discover_style_configs
        from app.utils.themed_icon import SVG_MENU_PALETTE, set_menubar_themable_action_icon

        theme_menu = parent_menu.addMenu("Theme")
        self._apply_menu_styling(theme_menu)
        set_menubar_themable_action_icon(self, theme_menu.menuAction(), SVG_MENU_PALETTE)

        group = QActionGroup(self)
        group.setExclusive(True)

        # Discover themes next to config.json.
        # Use ConfigLoader default path resolution (app/config/config.json).
        from app.config.config_loader import ConfigLoader

        opts = discover_style_configs(config_path=ConfigLoader().config_path)

        # Reuse the already-determined active style ref (set at startup / apply_theme).
        cur_style = str(getattr(self, "_active_style_ref", "") or "")
        if not cur_style:
            # Safe default when unset (e.g., tests).
            try:
                cur_style = str(self.config.get("default_style_config", "") or "")
            except Exception:
                cur_style = ""

        if not opts:
            a = theme_menu.addAction("(no themes found)")
            a.setEnabled(False)
            return

        self._theme_menu_actions = []
        for opt in opts:
            act = theme_menu.addAction(opt.label)
            act.setCheckable(True)
            act.setActionGroup(group)
            if cur_style and (cur_style == opt.style_ref or cur_style.endswith(opt.absolute_path.name)):
                act.setChecked(True)
            act.triggered.connect(lambda checked=False, sr=opt.style_ref: self.apply_theme(style_ref=sr))
            self._theme_menu_actions.append((act, opt))

    def apply_theme(self, *, style_ref: str) -> None:
        """Switch the active style config and rebuild UI for immediate effect."""
        from app.config.config_loader import ConfigLoader
        from app.services.theme_service import load_config_for_style
        from app.utils.themed_icon import refresh_all_menubar_themable_action_icons

        # Preserve a small amount of UI state.
        detail_tab = -1
        ps_current_player = None
        ps_source_sel = None
        try:
            if hasattr(self, "detail_panel") and hasattr(self.detail_panel, "tab_widget"):
                detail_tab = int(self.detail_panel.tab_widget.currentIndex())
        except Exception:
            detail_tab = -1

        # Preserve Player Stats selection (fixes view needing manual reselect after rebuild).
        try:
            psc = self.controller.get_player_stats_controller() if hasattr(self, "controller") else None
            if psc is not None and hasattr(psc, "get_current_player"):
                ps_current_player = psc.get_current_player()
            if psc is not None and hasattr(psc, "get_source_selection"):
                ps_source_sel = psc.get_source_selection()
        except Exception:
            ps_current_player = None
            ps_source_sel = None

        db_collapsed = bool(getattr(self, "_database_panel_collapsed", False))
        splitter_sizes = None
        try:
            splitter_sizes = self.middle_splitter.sizes() if hasattr(self, "middle_splitter") else None
        except Exception:
            splitter_sizes = None

        # Load merged config with the selected style defaults (no disk mutation).
        cfg_path = ConfigLoader().config_path
        new_config = load_config_for_style(config_path=cfg_path, style_ref=style_ref)

        # Store the active style ref for menu syncing without extra lookups.
        self._active_style_ref = str(style_ref or "")

        # Update config references.
        self.config = new_config
        try:
            self.controller.set_config(new_config)
        except Exception:
            pass

        # Persist theme choice in user settings (save happens by existing shutdown flow).
        try:
            from app.services.user_settings_service import UserSettingsService

            svc = UserSettingsService.get_instance()
            model = svc.get_model()
            cur = model.get_settings()
            ui = cur.get("ui", {}) if isinstance(cur.get("ui"), dict) else {}
            theme = ui.get("theme", {}) if isinstance(ui.get("theme"), dict) else {}
            theme["default_style_config"] = str(style_ref)
            ui["theme"] = theme
            updated = dict(cur)
            updated["ui"] = ui
            model.update_from_dict(updated)
        except Exception:
            pass

        # Re-apply global tooltip styling.
        self._setup_tooltip_styling()

        # Re-apply menu bar + menu styling (menubar is not rebuilt in _setup_ui()).
        try:
            mb = self.menuBar()
            self._apply_menu_bar_styling(mb)
            # Also restyle existing menus/submenus (recursive).
            def _restyle_menu_recursive(menu: QMenu) -> None:
                self._apply_menu_styling(menu)
                for a in menu.actions():
                    sm = a.menu()
                    if sm is not None:
                        _restyle_menu_recursive(sm)

            for action in mb.actions():
                m = action.menu()
                if m is not None:
                    _restyle_menu_recursive(m)
        except Exception:
            pass

        # Rebuild themed menu icons for new tint colors.
        try:
            refresh_all_menubar_themable_action_icons(self)
        except Exception:
            pass

        # Rebuild central UI to force widgets to reload styling from config.
        try:
            old = self.takeCentralWidget()
            if old is not None:
                old.deleteLater()
        except Exception:
            pass
        self._setup_ui()

        # Ensure the View → Theme menu reflects the newly selected style.
        try:
            for act, opt in getattr(self, "_theme_menu_actions", []) or []:
                if str(style_ref) == opt.style_ref or str(style_ref).endswith(opt.absolute_path.name):
                    act.setChecked(True)
        except Exception:
            pass

        # Re-apply user settings to the newly created views (Player Stats visibility, etc.).
        try:
            self._load_user_settings()
        except Exception:
            pass

        # Re-emit Player Stats selection to force a refresh (same effect as reselecting in dropdown).
        try:
            psc = self.controller.get_player_stats_controller() if hasattr(self, "controller") else None
            if psc is not None and ps_source_sel is not None and hasattr(psc, "set_source_selection"):
                psc.set_source_selection(int(ps_source_sel))
            if psc is not None and ps_current_player and hasattr(psc, "set_player_selection"):
                # Force refresh even if controller kept the same player across theme switch.
                psc.set_player_selection(None)
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(0, lambda p=str(ps_current_player): psc.set_player_selection(p))
        except Exception:
            pass

        # Restore basic UI state.
        try:
            if detail_tab >= 0 and hasattr(self, "detail_panel") and hasattr(self.detail_panel, "tab_widget"):
                self.detail_panel.tab_widget.setCurrentIndex(detail_tab)
        except Exception:
            pass

        try:
            if splitter_sizes and hasattr(self, "middle_splitter"):
                self.middle_splitter.setSizes(splitter_sizes)
        except Exception:
            pass

        try:
            # Ensure collapsed state matches prior.
            if bool(getattr(self, "_database_panel_collapsed", False)) != db_collapsed:
                self._toggle_database_panel()
        except Exception:
            pass

    def _connect_menu_icon_color_scheme_refresh(self) -> None:
        """Rebuild themed menu icons when the system light/dark preference changes (Qt 6.5+)."""
        app = QApplication.instance()
        if app is None:
            return
        sh = app.styleHints()
        if not hasattr(sh, "colorSchemeChanged"):
            return
        sh.colorSchemeChanged.connect(self._on_menu_icon_color_scheme_changed)

    def _on_menu_icon_color_scheme_changed(self, _scheme) -> None:
        from app.utils.themed_icon import refresh_all_menubar_themable_action_icons

        refresh_all_menubar_themable_action_icons(self)

    def _on_player_stats_reset_to_template_defaults(self) -> None:
        """Restore Player Stats menu settings from ``user_settings.json.template``."""
        from app.services.progress_service import ProgressService
        from app.services.user_settings_service import UserSettingsService

        us_cfg = self.config.get("user_settings", {}) if isinstance(self.config.get("user_settings"), dict) else {}
        reset_cfg = us_cfg.get("player_stats_reset", {}) if isinstance(us_cfg.get("player_stats_reset"), dict) else {}
        confirm_title = str(
            reset_cfg.get("confirmation_title", "Reset Player Stats settings")
        )
        confirm_message = str(
            reset_cfg.get(
                "confirmation_message",
                "Do you want to reset all Player Stats options to the application defaults?",
            )
        )
        status_success = str(
            reset_cfg.get("status_success", "Player Stats options reset to application defaults.")
        )
        status_failed = str(
            reset_cfg.get("status_failed", "Could not reset Player Stats options.")
        )

        confirmed = ConfirmationDialog.show_confirmation(
            self.config,
            confirm_title,
            confirm_message,
            self,
        )
        if not confirmed:
            return
        svc = UserSettingsService.get_instance()
        progress = ProgressService.get_instance()
        if not svc.reset_player_stats_settings_from_template():
            progress.set_status(status_failed)
            MessageDialog.show_warning(
                self.config,
                confirm_title,
                status_failed,
                self,
            )
            return
        progress.set_status(status_success)
        try:
            self.controller.get_menu_options_sync_controller().sync_player_stats_from_settings()
        except Exception:
            pass
        self._sync_player_stats_time_series_menu_from_settings()
        self._sync_player_stats_activity_heatmap_menu_from_settings()
        self._sync_player_stats_accuracy_distribution_menu_from_settings()

    def _sync_player_stats_time_series_menu_from_settings(self) -> None:
        if hasattr(self, "_ps_ts_menu_controller"):
            self._ps_ts_menu_controller.sync_from_settings()

    def _sync_player_stats_activity_heatmap_menu_from_settings(self) -> None:
        if hasattr(self, "_ps_ah_menu_controller"):
            self._ps_ah_menu_controller.sync_from_settings()

    def _sync_player_stats_accuracy_distribution_menu_from_settings(self) -> None:
        if hasattr(self, "_ps_ad_menu_controller"):
            self._ps_ad_menu_controller.sync_from_settings()

    def _apply_menu_bar_styling(self, menu_bar: QMenuBar) -> None:
        """Apply styling to the menu bar based on configuration.
        
        Args:
            menu_bar: The QMenuBar instance to style.
        """
        from app.views.style.menu_bar import apply_menu_bar_styling

        apply_menu_bar_styling(menu_bar, self.config)
    
    def _apply_menu_styling(self, menu: QMenu) -> None:
        """Apply styling to a QMenu (used for submenus).
        
        Args:
            menu: The QMenu instance to style.
        """
        from app.views.style.menu_bar import apply_menu_styling

        apply_menu_styling(menu, self.config)
    
    def _require_active_database(self) -> Optional[DatabaseModel]:
        """Helper method to validate and return active database.
        
        Shows error dialog if no active database is available.
        
        Returns:
            DatabaseModel if active database exists, None otherwise.
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
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open PGN Database(s)",
            "",
            "PGN Files (*.pgn);;All Files (*)"
        )
        if not file_paths:
            return
        self._open_pgn_database_paths(list(file_paths))

    def _open_pgn_database_paths(self, file_paths: List[str]) -> None:
        """Open one or more PGN databases from filesystem paths (dialog or drag-and-drop)."""
        if not file_paths:
            return
        database_controller = self.controller.get_database_controller()

        if len(file_paths) == 1:
            file_path = file_paths[0]
            success, message, first_game = database_controller.open_pgn_database(file_path)

            if success:
                self._update_save_menu_state()
                self._update_close_menu_state()
                if first_game:
                    self.controller.get_game_controller().set_active_game(first_game)

            self.controller.set_status(message)
            return

        opened_count, skipped_count, failed_count, messages, last_successful_database, last_first_game = (
            database_controller.open_pgn_databases(file_paths)
        )

        if opened_count > 0:
            self._update_save_menu_state()
            self._update_close_menu_state()
            if last_successful_database:
                database_controller.set_active_database(last_successful_database)
            if last_first_game:
                self.controller.get_game_controller().set_active_game(last_first_game)

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
    
    def _on_database_removed(self, identifier: str) -> None:
        """When any database tab is closed (file menu or context menu), clear active game and update menu state."""
        self.controller.get_game_controller().set_active_game(None)
        self._update_save_menu_state()
        self._update_close_menu_state()

    def _close_pgn_database(self) -> None:
        """Close the currently selected PGN database tab."""
        database_controller = self.controller.get_database_controller()
        closed = database_controller.close_active_pgn_database()
        if closed:
            self.controller.set_status("PGN database closed")
        else:
            self.controller.set_status("No PGN database tab selected to close")
    
    def _close_all_pgn_databases(self) -> None:
        """Close all PGN databases except clipboard and search results."""
        database_controller = self.controller.get_database_controller()
        closed_count = database_controller.close_all_pgn_databases()
        if closed_count > 0:
            if closed_count == 1:
                self.controller.set_status("1 database closed")
            else:
                self.controller.set_status(f"{closed_count} databases closed")
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
            panel_model.database_removed.connect(self._on_database_removed)
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
        from app.views.dialogs.bulk_replace_dialog import BulkReplaceDialog
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
        from app.views.dialogs.bulk_tag_dialog import BulkTagDialog
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
        from app.views.dialogs.import_games_dialog import ImportGamesDialog
        
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
        from app.views.dialogs.search_dialog import SearchDialog
        
        dialog = SearchDialog(
            self.config,
            active_database,
            all_databases,
            self.controller.get_current_fen,
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

    def _open_pattern_games_in_search_results(self, pattern: Any) -> None:
        """Open the pattern's related games in a Search Results tab (create or replace).
        """
        if not hasattr(self, 'database_panel') or not pattern or not getattr(pattern, 'related_games', None):
            return
        stats_controller = self.controller.get_player_stats_controller()
        games_with_sources = stats_controller.get_pattern_games_with_sources(pattern)
        if not games_with_sources:
            return
        search_controller = self.controller.get_search_controller()
        search_results_model = search_controller.create_search_results_model(games_with_sources)
        tab_index = self.database_panel.add_search_results_tab(search_results_model)
        # Match regular search behavior: explicitly activate the tab
        self.database_panel.tab_widget.setCurrentIndex(tab_index)
        self._on_database_tab_changed(tab_index)

    def _open_activity_heatmap_day_in_search_results(self, day_ordinal: int) -> None:
        """Open analyzed games played on the given calendar day (activity heatmap double-click)."""
        if not hasattr(self, "database_panel"):
            return
        stats_controller = self.controller.get_player_stats_controller()
        games_with_sources = stats_controller.get_activity_heatmap_day_games_with_sources(day_ordinal)
        if not games_with_sources:
            return
        search_controller = self.controller.get_search_controller()
        search_results_model = search_controller.create_search_results_model(games_with_sources)
        tab_index = self.database_panel.add_search_results_tab(search_results_model)
        self.database_panel.tab_widget.setCurrentIndex(tab_index)
        self._on_database_tab_changed(tab_index)

    def _open_best_games_in_search_results(self) -> None:
        """Open the best-performing games for the current player in a Search Results tab."""
        if not hasattr(self, 'database_panel'):
            return
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        top_games_config = player_stats_config.get('top_games', {})
        max_best = int(top_games_config.get('max_best', 3))
        stats_controller = self.controller.get_player_stats_controller()
        games_with_sources = stats_controller.get_top_best_games_with_sources(max_best)
        if not games_with_sources:
            return
        search_controller = self.controller.get_search_controller()
        search_results_model = search_controller.create_search_results_model(games_with_sources)
        tab_index = self.database_panel.add_search_results_tab(search_results_model)
        self.database_panel.tab_widget.setCurrentIndex(tab_index)
        self._on_database_tab_changed(tab_index)

    def _open_worst_games_in_search_results(self) -> None:
        """Open the worst-performing games for the current player in a Search Results tab."""
        if not hasattr(self, 'database_panel'):
            return
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        player_stats_config = panel_config.get('player_stats', {})
        top_games_config = player_stats_config.get('top_games', {})
        max_best = int(top_games_config.get('max_best', 3))
        max_worst = int(top_games_config.get('max_worst', 3))
        stats_controller = self.controller.get_player_stats_controller()
        games_with_sources = stats_controller.get_top_worst_games_with_sources(max_worst, max_best)
        if not games_with_sources:
            return
        search_controller = self.controller.get_search_controller()
        search_results_model = search_controller.create_search_results_model(games_with_sources)
        tab_index = self.database_panel.add_search_results_tab(search_results_model)
        self.database_panel.tab_widget.setCurrentIndex(tab_index)
        self._on_database_tab_changed(tab_index)
    
    def _open_brilliant_moves_in_search_results(self) -> None:
        """Open brilliant moves for the current player in a Search Results tab."""
        self._open_significant_moves_in_search_results("brilliant")

    def _open_misses_in_search_results(self) -> None:
        """Open misses for the current player in a Search Results tab."""
        self._open_significant_moves_in_search_results("misses")

    def _open_blunders_in_search_results(self) -> None:
        """Open blunders for the current player in a Search Results tab."""
        self._open_significant_moves_in_search_results("blunders")

    def _open_significant_moves_in_search_results(self, move_type: str) -> None:
        """Open brilliant moves, misses, or blunders in a Search Results tab."""
        if not hasattr(self, "database_panel"):
            return
        ui_config = self.config.get("ui", {})
        panel_config = ui_config.get("panels", {}).get("detail", {})
        player_stats_config = panel_config.get("player_stats", {})
        significant_config = player_stats_config.get("significant_moves", {})
        if move_type == "brilliant":
            cfg = significant_config.get("brilliant_moves") or player_stats_config.get("brilliant_moves", {})
        elif move_type == "misses":
            cfg = significant_config.get("misses", {})
        else:
            cfg = significant_config.get("blunders", {})
        max_moves = int(cfg.get("max_moves", 999))

        stats_controller = self.controller.get_player_stats_controller()
        if move_type == "brilliant":
            items = stats_controller.get_top_brilliant_moves_with_sources_and_ply(max_moves)
        elif move_type == "misses":
            items = stats_controller.get_top_misses_with_sources_and_ply(max_moves)
        else:
            items = stats_controller.get_top_blunders_with_sources_and_ply(max_moves)
        if not items:
            return

        search_controller = self.controller.get_search_controller()
        search_results_model = search_controller.create_search_results_model(items)
        tab_index = self.database_panel.add_search_results_tab(search_results_model)
        self.database_panel.tab_widget.setCurrentIndex(tab_index)
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
        from app.views.dialogs.bulk_clean_pgn_dialog import BulkCleanPgnDialog
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
        from app.utils.external_open import open_path
        # Get the path to the manual HTML file
        # __file__ is app/main_window.py, so parent is app/, then resources/manual/index.html
        manual_path = Path(__file__).resolve().parent / "resources" / "manual" / "index.html"
        open_path(manual_path, context="help.manual")
    
    def _open_video_tutorials(self) -> None:
        """Open the CARA Chess YouTube channel in the default browser."""
        from app.utils.external_open import open_url
        open_url(QUrl("https://www.youtube.com/@CARA-Chess"), context="help.youtube")
    
    def _open_github_repository(self) -> None:
        """Open the CARA GitHub repository in the default browser."""
        from app.utils.external_open import open_url
        open_url(QUrl("https://github.com/pguntermann/CARA"), context="help.github")
    
    def _open_user_data_directory(self) -> None:
        """Open the user data directory in the file explorer/finder."""
        from app.utils.path_resolver import resolve_data_file_path
        from app.utils.external_open import open_path
        
        # Get the resolved path for a user data file to determine the actual directory being used
        # This works correctly whether in portable mode or user data directory mode
        user_data_file_path, _ = resolve_data_file_path("user_settings.json")
        user_data_dir = user_data_file_path.parent
        
        # Ensure the directory exists
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Open the directory in the file explorer/finder
        open_path(user_data_dir, context="help.user_data_dir")
    
    def _show_about_dialog(self) -> None:
        """Show the about dialog."""
        dialog = AboutDialog(self.config, self)
        dialog.exec()
    
    def _show_release_notes_dialog(self) -> None:
        """Show the release notes dialog with RELEASE_NOTES.md content."""
        dialog = InlineContentDialog(
            self.config,
            window_title="Release Notes",
            content_path=Path("RELEASE_NOTES.md"),
            content_format="markdown",
            fallback_message=(
                "Release notes file not found. Please visit the GitHub repository for the latest release information."
            ),
            parent=self,
        )
        dialog.exec()
    
    def _show_license_dialog(self) -> None:
        """Show the License (GPL-3.0) dialog."""
        dialog = InlineContentDialog(
            self.config,
            window_title="License",
            content_path=Path("LICENSE"),
            content_format="markdown",
            wrap_plain_text_in_code_block=True,
            fallback_message="License file not found. Please see the project repository for license information.",
            parent=self,
        )
        dialog.exec()
    
    def _show_third_party_licenses_dialog(self) -> None:
        """Show the Third Party Licenses dialog."""
        dialog = InlineContentDialog(
            self.config,
            window_title="Third Party Licenses",
            content_path=Path("THIRD_PARTY_LICENSES.md"),
            content_format="markdown",
            fallback_message=(
                "Third party licenses file not found. Please see the project repository for license information."
            ),
            parent=self,
        )
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
                f"Could not check for updates:<br><br>{error_message}",
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
                from app.utils.external_open import open_url
                open_url(QUrl(download_url), context="help.download_url")
        else:
            # Show up-to-date message
            MessageDialog.show_information(
                self.config,
                "Up to Date",
                f"You are using the latest version.<br><br>Current version: {current_version}",
                self
            )
    
    def _close_application(self) -> None:
        """Close the application."""
        # Settings are persisted in closeEvent after quit(); saving here would duplicate that work.
        # self._save_user_settings()
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
        
        # Stop evaluation and manual analysis synchronously before shutdown
        # This ensures threads and processes are cleaned up properly, preventing macOS crash reports
        try:
            # Stop evaluation if running
            evaluation_controller = self.controller.get_evaluation_controller()
            if evaluation_controller:
                evaluation_controller.stop_evaluation()
            
            # Stop manual analysis if running (synchronous=True to wait for cleanup)
            manual_analysis_controller = self.controller.get_manual_analysis_controller()
            if manual_analysis_controller:
                manual_analysis_controller.stop_analysis(synchronous=True)
        except Exception as e:
            # Log error but don't prevent shutdown
            logging_service.error(f"Error during cleanup on shutdown: {e}", exc_info=e)
        
        self._save_user_settings()
        event.accept()

    def showEvent(self, event) -> None:
        """Handle first paint/show for deferred welcome dialogs."""
        super().showEvent(event)

        if self._welcome_dialog_done:
            return

        if not getattr(self, "_welcome_dialog_pending", False):
            return

        # Ensure main window has had a chance to appear before showing a
        # modal dialog.
        self._welcome_dialog_pending = False

        def _show_welcome() -> None:
            if self._welcome_dialog_done:
                return

            # Show welcome dialog (modal).
            MessageDialog.show_information(
                self.config,
                self._welcome_dialog_title or "Welcome to CARA",
                self._welcome_dialog_message
                or 'Welcome to CARA!<br><br>Start by reading <a href="manual://getting-started">Getting Started</a>.',
                self,
            )

            # Mark as shown and persist immediately.
            settings_service = getattr(self, "_settings_service", None)
            if settings_service:
                ui_settings = settings_service.get_settings().get("ui", {})
                if not isinstance(ui_settings, dict):
                    ui_settings = {}
                ui_settings = dict(ui_settings)
                ui_settings["welcome_shown"] = True
                settings_service.get_model().update_from_dict({"ui": ui_settings})
                settings_service.save()

            self._welcome_dialog_done = True

        QTimer.singleShot(0, _show_welcome)
    
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
        self._update_board_visibility_setting("show_annotations_layer", checked)
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

    def _clear_notes_for_current_game(self) -> None:
        """Clear notes for the current game (removes CARANotes tag in memory)."""
        if not self.controller:
            return
        notes_controller = self.controller.get_notes_controller()
        if notes_controller and notes_controller.clear_notes_for_current_game():
            if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'notes_view'):
                self.detail_panel.notes_view.set_notes_text("")
            self.controller.set_status("Notes cleared for current game")

    def _save_notes_to_current_game(self) -> None:
        """Save notes from the Notes view into the active game's PGN tag (in memory)."""
        if not self.controller:
            return
        if not hasattr(self, 'detail_panel') or not hasattr(self.detail_panel, 'notes_view'):
            return
        notes_text = self.detail_panel.notes_view.get_plain_text()
        notes_controller = self.controller.get_notes_controller()
        if notes_controller and notes_controller.save_notes_to_current_game(notes_text):
            # Mark the game as having unsaved changes (same as annotations / metadata)
            database_model = self.controller.get_database_model_for_active_game()
            if database_model:
                game_controller = self.controller.get_game_controller()
                active_game = game_controller.get_game_model().active_game
                if active_game and database_model.update_game(active_game):
                    self.controller.get_database_controller().mark_database_unsaved(database_model)
            self.controller.set_status("Notes saved to current game")

    def _show_ai_model_settings(self) -> None:
        """Show the AI model settings dialog."""
        from app.views.dialogs.ai_model_settings_dialog import AIModelSettingsDialog
        from app.services.user_settings_service import UserSettingsService
        
        settings_service = UserSettingsService.get_instance()
        dialog = AIModelSettingsDialog(self.config, settings_service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_ai_summary_models()
            self._refresh_ai_summary_menu_state()
    
    def _show_annotation_preferences(self) -> None:
        """Show annotation preferences dialog."""
        from app.views.dialogs.annotation_preferences_dialog import AnnotationPreferencesDialog
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
    
    def _on_highlight_annotated_moves_toggled(self, checked: bool) -> None:
        """Handle Highlight annotated moves in moves list toggle.
        
        Args:
            checked: True if the menu item is checked (feature enabled).
        """
        if not hasattr(self, '_settings_service') or self._settings_service is None:
            return
        self._settings_service.update_annotations({"highlight_annotated_moves_in_list": checked})
        self._settings_service.save()
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            self.detail_panel.moveslist_model.set_highlight_annotated_moves(checked)
    
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

    def _on_move_classification_icons_visibility_changed(self, visible: bool) -> None:
        """Handle move classification icons visibility change to update menu toggle."""
        self._update_move_classification_icons_action_state(visible)

    def _update_move_classification_icons_action_state(self, visible: bool) -> None:
        """Update move classification icons menu action checked state."""
        if hasattr(self, 'move_classification_icons_action'):
            self.move_classification_icons_action.setChecked(visible)

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

    def _on_game_tags_widget_visibility_changed(self, show: bool) -> None:
        """Handle game tags widget visibility change to update menu toggle."""
        self._update_game_tags_widget_action_state(show)
    
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

    def _update_game_tags_widget_action_state(self, show: bool) -> None:
        """Update the game tags widget visibility menu action toggle state."""
        if hasattr(self, 'game_tags_widget_action'):
            self.game_tags_widget_action.setChecked(show)
    
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
        notes_controller = self.controller.get_notes_controller()
        self.detail_panel = DetailPanel(self.config, game_model, game_controller,
                                        notes_controller, engine_model,
                                        manual_analysis_controller, database_model, classification_model,
                                        annotation_controller, board_widget, ai_chat_controller,
                                        game_summary_controller, player_stats_controller,
                                        metadata_controller)

        # Wire per-game tag bubbles widget (board overlay) to models/controllers
        if board_widget is not None and hasattr(board_widget, "game_tags_widget") and board_widget.game_tags_widget:
            board_widget.game_tags_widget.set_context(game_model, metadata_controller)
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
            on_add_tab_clicked=self._open_pgn_database,
            on_open_pgn_paths=self._open_pgn_database_paths,
            on_close_database=database_controller.close_database_by_identifier,
            on_close_all_but_database=database_controller.close_all_pgn_databases_except,
            on_close_search_results=self._close_search_results_tab,
            on_copy_game=self._on_context_copy_game,
            on_copy_selected_games=self._on_context_copy_selected_games,
            on_cut_selected_games=self._on_context_cut_selected_games,
            on_paste_games=self._on_context_paste_games,
            on_clear_game_tags_selected=self._on_context_clear_game_tags_selected,
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
                self.detail_panel.player_stats_view._on_open_activity_heatmap_day_in_search_results = (
                    self._open_activity_heatmap_day_in_search_results
                )
            if hasattr(self.detail_panel, 'moves_view'):
                self.detail_panel.moves_view.set_database_controller(database_controller)
                self.detail_panel.player_stats_view._on_open_pattern_games_in_search_results = self._open_pattern_games_in_search_results
                self.detail_panel.player_stats_view._on_open_best_games_in_search_results = self._open_best_games_in_search_results
                self.detail_panel.player_stats_view._on_open_worst_games_in_search_results = self._open_worst_games_in_search_results
                self.detail_panel.player_stats_view._on_open_brilliant_moves_in_search_results = self._open_brilliant_moves_in_search_results
                self.detail_panel.player_stats_view._on_open_misses_in_search_results = self._open_misses_in_search_results
                self.detail_panel.player_stats_view._on_open_blunders_in_search_results = self._open_blunders_in_search_results
                # Database connections are now handled by the controller
            # Inject selected-games callback for Player Stats "Selected games (Active/All)" source
            player_stats_controller = self.controller.get_player_stats_controller()
            player_stats_controller.set_get_selected_games_callback(
                lambda active_only: self.database_panel.get_selected_games(active_only)
            )
            self.database_panel.selection_changed.connect(player_stats_controller.notify_selection_changed)

        # Set moves list model in game analysis controller and on chessboard (for move classification badges)
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            self.controller.set_moves_list_model(self.detail_panel.moveslist_model)
            if hasattr(self, 'main_panel') and hasattr(self.main_panel, 'chessboard_view') and hasattr(self.main_panel.chessboard_view, 'chessboard'):
                self.main_panel.chessboard_view.chessboard.set_moveslist_model(self.detail_panel.moveslist_model)
            # Connect bulk analysis finished so active game's Game Summary becomes available after bulk run
            if not getattr(self, '_bulk_analysis_finished_connected', False):
                self.controller.get_bulk_analysis_controller().finished.connect(
                    self._on_bulk_analysis_finished_refresh_active_game
                )
                self._bulk_analysis_finished_connected = True
            # If bulk analysis updates the active game's PGN (e.g., auto-tags), refresh UI immediately.
            if not getattr(self, "_bulk_analysis_game_analyzed_connected", False):
                self.controller.get_bulk_analysis_controller().game_analyzed.connect(
                    self._on_bulk_analysis_game_analyzed_refresh_active_game_ui
                )
                self._bulk_analysis_game_analyzed_connected = True
        
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

    def _on_context_copy_game(self, game: Any) -> None:
        """Context menu: copy PGN of the game at the right-clicked row."""
        success, message = self.controller.copy_game_pgn_to_clipboard(game)
        self.controller.set_status(message)

    def _on_context_copy_selected_games(self, database_model: Any, selected_indices: List[int]) -> None:
        """Context menu: copy selected games from the table that was right-clicked."""
        if not hasattr(self, "database_panel"):
            self.controller.set_status("No database panel available")
            return
        success, message = self.controller.copy_selected_games_to_clipboard(
            self.database_panel, database_model=database_model, selected_indices=selected_indices
        )
        self.controller.set_status(message)

    def _on_context_cut_selected_games(self, database_model: Any, selected_indices: List[int]) -> None:
        """Context menu: cut selected games from the table that was right-clicked."""
        if not hasattr(self, "database_panel"):
            self.controller.set_status("No database panel available")
            return
        success, message = self.controller.cut_selected_games_to_clipboard(
            self.database_panel, database_model=database_model, selected_indices=selected_indices
        )
        self.controller.set_status(message)

    def _on_context_paste_games(self, database_model: Any) -> None:
        """Context menu: paste PGN into the database tab that was right-clicked."""
        success, message, first_game_index, games_added = self.controller.paste_pgn_to_database(database_model)
        if success and first_game_index is not None and games_added > 0:
            database_controller = self.controller.get_database_controller()
            database_controller.set_active_database(database_model)
            pasted_indices = list(range(first_game_index, first_game_index + games_added))
            self.database_panel.highlight_rows(database_model, pasted_indices)
        self.controller.set_status(message)

    def _on_context_clear_game_tags_selected(self, database_model: Any, selected_indices: List[int]) -> None:
        """Context menu: clear CARA per-game tags on selected rows (not bulk PGN header tools)."""
        if not selected_indices:
            self.controller.set_status("No rows selected")
            return
        n = self.controller.get_metadata_controller().clear_cara_game_tags_for_database_rows(
            database_model, selected_indices
        )
        if n <= 0:
            self.controller.set_status("Selected games have no game tags")
        elif n == 1:
            self.controller.set_status("Cleared game tags from 1 game")
        else:
            self.controller.set_status(f"Cleared game tags from {n} games")

    def _paste_fen_to_board(self) -> None:
        """Paste FEN from clipboard and update board position."""
        success, status_message = self.controller.paste_fen_from_clipboard()
        self.controller.set_status(status_message)
    
    def _debug_copy_pgn_html(self) -> None:
        """DEBUG: Copy PGN HTML and current visibility settings to clipboard."""
        pgn_view = getattr(self.detail_panel, "pgn_view", None) if hasattr(self, "detail_panel") else None
        self.controller.get_debug_controller().copy_pgn_view_debug_to_clipboard(pgn_view)
    
    def _debug_copy_game_highlights_html(self) -> None:
        """DEBUG: Copy game highlights section from the summary controller as HTML."""
        self.controller.get_debug_controller().copy_game_highlights_html_to_clipboard()
    
    def _debug_copy_game_highlights_json(self) -> None:
        """DEBUG: Copy game highlights data as JSON."""
        self.controller.get_debug_controller().copy_game_highlights_json_to_clipboard()
    
    def _debug_create_highlight_rule_test_data(self) -> None:
        """DEBUG: Prompt for filename and save analysis JSON for highlight rule tests."""
        from app.views.dialogs.input_dialog import InputDialog

        filename, ok = InputDialog.get_text(
            self.config,
            "Create Highlight Rule Test Data",
            "Enter filename (e.g., my_rule_case.json):",
            "",
            self,
        )
        if not ok or not filename:
            return

        self.controller.get_debug_controller().create_highlight_rule_test_data_file(filename)
    
    
    def _update_moves_list_menu(self) -> None:
        """Update the Moves List menu with current profiles and columns."""
        from app.views.menus.moves_list_menu import rebuild_moves_list_menu

        rebuild_moves_list_menu(self)
    
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
        from app.views.dialogs.moveslist_profile_setup_dialog import MovesListProfileSetupDialog
        
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
        self.controller.get_debug_controller().copy_deserialized_analysis_tag_to_clipboard()
    
    def _debug_copy_deserialize_annotation_tag(self) -> None:
        """DEBUG: Copy deserialized and decompressed CARAAnnotations tag to clipboard."""
        self.controller.get_debug_controller().copy_deserialized_annotation_tag_to_clipboard()
    
    def _save_current_profile(self) -> None:
        """Save current column configuration to the active profile (overwrites)."""
        active_profile_name = self.profile_model.get_active_profile_name()
        
        # Cannot save default profile
        if active_profile_name == DEFAULT_PROFILE_NAME:
            self.controller.set_status("Cannot save default profile")
            return
        
        # Push current header widths and column order into the active profile (in memory)
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            self.detail_panel.moves_view.sync_moves_list_column_layout_to_active_profile()
        
        # Update the active profile with current column configuration and persist
        success, message = self.profile_controller.update_current_profile()
        if success:
            self._update_moves_list_menu()
        self.controller.set_status(message)
    
    def _save_profile_as(self) -> None:
        """Save current column configuration as a new profile."""
        # Ask user for profile name using custom styled dialog
        from app.views.dialogs.input_dialog import InputDialog
        profile_name, ok = InputDialog.get_text(
            self.config,
            "Save Profile as...",
            "Enter profile name:",
            "",
            self
        )
        
        if not ok or not profile_name:
            return
        
        # Push current header widths and column order into the active profile before snapshot
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moves_view'):
            self.detail_panel.moves_view.sync_moves_list_column_layout_to_active_profile()
        
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
        """Handle Show PGN header tags toggle.
        
        Args:
            checked: True if metadata should be shown, False otherwise.
        """
        self._update_pgn_visibility_setting("show_metadata", checked)
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
        self._update_pgn_visibility_setting("show_comments", checked)
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
        self._update_pgn_visibility_setting("show_variations", checked)
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
        self._update_pgn_visibility_setting("show_annotations", checked)
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
        self._update_pgn_visibility_setting("show_results", checked)
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
    
    def _on_nag_display_mode_selected(self, use_symbols: bool) -> None:
        """Handle NAG display mode selection (Symbols or Text).
        
        Args:
            use_symbols: True for symbols mode, False for text mode.
        """
        # Update check states (exclusive group)
        self.nag_display_symbols_action.setChecked(use_symbols)
        self.nag_display_text_action.setChecked(not use_symbols)
        
        # Update user settings
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_pgn_notation({
            "use_symbols_for_nags": use_symbols,
            "show_nag_text": not use_symbols
        })
        
        # Refresh PGN display
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'pgn_view'):
            pgn_view = self.detail_panel.pgn_view
            if hasattr(pgn_view, '_current_pgn_text'):
                pgn_view.set_pgn_text(pgn_view._current_pgn_text)
        
        mode = "symbols" if use_symbols else "text"
        self.controller.set_status(f"NAG move assessments displayed as {mode}")
    
    def _update_pgn_visibility_setting(self, key: str, checked: bool) -> None:
        """Persist a PGN visibility toggle into the in-memory user settings model."""
        from app.services.user_settings_service import UserSettingsService

        UserSettingsService.get_instance().update_pgn_visibility({key: checked})

    def _update_game_analysis_setting(self, key: str, value: Any) -> None:
        """Persist a game-analysis menu option into the in-memory user settings model."""
        from app.services.user_settings_service import UserSettingsService

        UserSettingsService.get_instance().update_game_analysis({key: value})

    def _update_manual_analysis_setting(self, key: str, value: Any) -> None:
        """Persist a manual-analysis menu option into the in-memory user settings model."""
        from app.services.user_settings_service import UserSettingsService

        UserSettingsService.get_instance().update_manual_analysis({key: value})

    def _update_board_visibility_setting(self, key: str, value: Any) -> None:
        """Persist a board-visibility option into the in-memory user settings model."""
        from app.services.user_settings_service import UserSettingsService

        UserSettingsService.get_instance().update_board_visibility({key: value})

    def _on_show_non_standard_tags_toggled(self, checked: bool) -> None:
        """Handle Show Non-Standard Tags toggle.
        
        Args:
            checked: True if non-standard tags (like [%evp], [%mdl]) should be shown, False otherwise.
        """
        self._update_pgn_visibility_setting("show_non_standard_tags", checked)
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
        database_model = self.controller.get_database_controller().find_database_model_for_game(game)
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
    
    def _on_return_to_first_move_toggled(self, checked: bool) -> None:
        """Handle Return to PLY 0 after analysis completes toggle.
        
        Args:
            checked: True if should return to PLY 0 after analysis completes, False otherwise.
        """
        self._update_game_analysis_setting("return_to_first_move_after_analysis", checked)
    
    def _on_switch_to_moves_list_toggled(self, checked: bool) -> None:
        """Handle Switch to Moves List at the start of Analysis toggle.
        
        Args:
            checked: True if should switch to Moves List tab at the start of analysis, False otherwise.
        """
        self._update_game_analysis_setting("switch_to_moves_list_at_start_of_analysis", checked)
    
    def _on_switch_to_summary_toggled(self, checked: bool) -> None:
        """Handle Switch to Game Summary after Analysis toggle.
        
        Args:
            checked: True if should switch to Game Summary tab after analysis, False otherwise.
        """
        self._update_game_analysis_setting("switch_to_summary_after_analysis", checked)
    
    def _on_brilliant_move_detection_toggled(self, checked: bool) -> None:
        """Handle Brilliant Move Detection toggle.
        
        Args:
            checked: True if brilliant move detection is enabled, False otherwise.
        """
        # Update in-memory settings immediately
        if hasattr(self, '_settings_service'):
            self._settings_service.update_game_analysis({"brilliant_move_detection": checked})
        # Pass setting to game analysis controller
        if hasattr(self.controller, 'game_analysis_controller'):
            self.controller.game_analysis_controller.set_brilliant_move_detection(checked)
        # Settings will be saved automatically on application exit
        # No immediate action needed - behavior is handled in _on_game_analysis_completed

    def _on_auto_game_tagging_toggled(self, checked: bool) -> None:
        """Handle Auto Tag Games toggle.

        Args:
            checked: True if auto game tagging is enabled, False otherwise.
        """
        # Update in-memory settings immediately
        if hasattr(self, '_settings_service'):
            self._settings_service.update_game_analysis({"auto_game_tagging": checked})
        # Pass setting to game analysis controller (used by bulk analysis)
        if hasattr(self.controller, 'game_analysis_controller'):
            self.controller.game_analysis_controller.set_auto_game_tagging(checked)
        # Enable/disable the tag selection submenu
        try:
            if hasattr(self, "select_auto_tags_menu") and self.select_auto_tags_menu:
                self.select_auto_tags_menu.setEnabled(bool(checked))
        except Exception:
            pass

    def _on_auto_game_tagging_tag_toggled(self, tag_name: str, checked: bool) -> None:
        """Handle per-tag enable/disable for Auto Tag Games."""
        tag_name = str(tag_name or "").strip()
        if not tag_name:
            return
        try:
            from app.services.game_auto_tagging_service import AUTO_TAGS
        except Exception:
            AUTO_TAGS = ()  # type: ignore

        # Read current selection from settings (fallback: all enabled)
        enabled = None
        try:
            settings = self._settings_service.get_settings() if hasattr(self, "_settings_service") else {}
            ga = settings.get("game_analysis", {}) if isinstance(settings, dict) else {}
            enabled = ga.get("auto_game_tagging_enabled_tags", None) if isinstance(ga, dict) else None
        except Exception:
            enabled = None
        enabled_src = list(AUTO_TAGS) if enabled is None else enabled
        enabled_list = [t for t in (enabled_src or []) if isinstance(t, str) and t.strip()]
        enabled_cf = {t.casefold() for t in enabled_list}
        if checked:
            enabled_cf.add(tag_name.casefold())
        else:
            enabled_cf.discard(tag_name.casefold())

        # Preserve original casing from AUTO_TAGS order when saving
        saved = [t for t in list(AUTO_TAGS) if t.casefold() in enabled_cf]
        if hasattr(self, "_settings_service"):
            self._settings_service.update_game_analysis({"auto_game_tagging_enabled_tags": saved})
        if hasattr(self.controller, "game_analysis_controller"):
            self.controller.game_analysis_controller.set_auto_game_tagging_enabled_tags(saved)
    
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
        self._update_game_analysis_setting("normalized_evaluation_graph", checked)
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
    
    def _on_start_manual_analysis_toggled(self, _checked: bool = False) -> None:
        """Handle start/stop manual analysis from menu (play/stop icon reflects state)."""
        manual_analysis_controller = self.controller.get_manual_analysis_controller()
        manual_analysis_model = manual_analysis_controller.get_analysis_model()

        if manual_analysis_model.is_analyzing:
            manual_analysis_controller.stop_analysis()
            return

        # Check if engine is configured and assigned for manual analysis
        is_configured, error_type = self.controller.is_engine_configured_for_task(TASK_MANUAL_ANALYSIS)
        if not is_configured:
            title, message = self.controller.get_engine_validation_message(error_type, TASK_MANUAL_ANALYSIS)
            MessageDialog.show_warning(self.config, title, message, self)
            return

        # Switch to Manual Analysis tab FIRST for immediate visual feedback
        if hasattr(self, "detail_panel") and hasattr(self.detail_panel, "tab_widget"):
            tab_widget = self.detail_panel.tab_widget
            for i in range(tab_widget.count()):
                if tab_widget.tabText(i) == "Manual Analysis":
                    tab_widget.setCurrentIndex(i)
                    from PyQt6.QtWidgets import QApplication

                    QApplication.processEvents()
                    break

        manual_analysis_controller.start_analysis()
    
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
        self._update_manual_analysis_setting("enable_miniature_preview", enabled)
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
        
        self._update_manual_analysis_setting("miniature_preview_scale_factor", scale_factor)
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
        self._update_board_visibility_setting("hide_other_arrows_during_plan_exploration", checked)
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
    
    def _sync_game_info_center_menu_actions(self, mode: str) -> None:
        """Keep Board menu actions aligned with ``game_info_center_mode``."""
        if not hasattr(self, "game_info_center_mode_group"):
            return
        if mode not in ("center_in_view", "center_over_board"):
            mode = "center_in_view"
        self.game_info_center_mode_group.blockSignals(True)
        try:
            self.game_info_center_in_view_action.setChecked(mode == "center_in_view")
            self.game_info_center_over_board_action.setChecked(mode == "center_over_board")
        finally:
            self.game_info_center_mode_group.blockSignals(False)

    def _on_game_info_center_mode_menu_triggered(self, mode: str) -> None:
        """Apply game info horizontal alignment; persisted on app exit like other board prefs."""
        if mode == "center_in_view" and not self.game_info_center_in_view_action.isChecked():
            return
        if mode == "center_over_board" and not self.game_info_center_over_board_action.isChecked():
            return
        if hasattr(self, "main_panel"):
            self.main_panel.set_game_info_center_mode(mode)
        from app.services.user_settings_service import UserSettingsService
        UserSettingsService.get_instance().update_board_visibility({"game_info_center_mode": mode})
    
    def _on_ai_summary_provider_selected(self, provider: str) -> None:
        """Handle AI Summary provider toggle selection."""
        use_openai = provider == "openai"
        use_anthropic = provider == "anthropic"
        use_custom = provider == "custom"
        
        # Update menu states to enforce exclusivity
        self.ai_summary_use_openai_action.setChecked(use_openai)
        self.ai_summary_use_anthropic_action.setChecked(use_anthropic)
        self.ai_summary_use_custom_action.setChecked(use_custom)
        
        # Persist setting
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_service.update_ai_summary_settings({
            "use_openai_models": use_openai,
            "use_anthropic_models": use_anthropic,
            "use_custom_models": use_custom
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
    
    def _refresh_ai_summary_menu_state(self) -> None:
        """Refresh the AI Summary menu checkboxes based on current settings."""
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings = settings_service.get_settings()
        ai_summary_settings = settings.get("ai_summary", {})
        use_openai = ai_summary_settings.get("use_openai_models", True)
        use_anthropic = ai_summary_settings.get("use_anthropic_models", False)
        use_custom = ai_summary_settings.get("use_custom_models", False)
        
        # Enforce exactly one provider: default to OpenAI if invalid
        if sum([use_openai, use_anthropic, use_custom]) != 1:
            use_openai = True
            use_anthropic = False
            use_custom = False
        
        if hasattr(self, 'ai_summary_use_openai_action'):
            self.ai_summary_use_openai_action.setChecked(use_openai)
        if hasattr(self, 'ai_summary_use_anthropic_action'):
            self.ai_summary_use_anthropic_action.setChecked(use_anthropic)
        if hasattr(self, 'ai_summary_use_custom_action'):
            self.ai_summary_use_custom_action.setChecked(use_custom)
    
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
        if hasattr(self, "start_manual_analysis_action"):
            from app.utils.themed_icon import SVG_MENU_PLAY, SVG_MENU_STOP, set_menubar_themable_action_icon

            if is_analyzing:
                self.start_manual_analysis_action.setText("Stop Manual Analysis")
                set_menubar_themable_action_icon(
                    self, self.start_manual_analysis_action, SVG_MENU_STOP
                )
            else:
                self.start_manual_analysis_action.setText("Start Manual Analysis")
                set_menubar_themable_action_icon(
                    self, self.start_manual_analysis_action, SVG_MENU_PLAY
                )
        
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
            moves_view.set_column_profile_controller(self.controller.get_column_profile_controller())
        
        # Also update moves list model column visibility
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            moveslist_model = self.detail_panel.moveslist_model
            column_visibility = self.controller.get_column_profile_controller().get_column_visibility()
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
            index: Tab index (0=Moves List, 1=Metadata, 2=Manual Analysis, 3=Game Summary, 4=Player Stats, 5=Annotations, 6=AI Summary, 7=Notes).
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
            column_visibility = self.controller.get_column_profile_controller().get_column_visibility()
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
        
        game_controller = self.controller.get_game_controller()
        # Set the game as active
        game_controller.set_active_game(game)
        status_message = game_controller.format_active_game_status_message(game)
        if status_message:
            self.controller.set_status(status_message)
        # If this row has a reference ply (e.g. from a brilliant-move search), navigate to it
        ref_ply = getattr(game, "ref_ply", 0)
        if isinstance(ref_ply, int) and ref_ply > 0:
            game_controller.navigate_to_ply(ref_ply)
    
    def _add_engine(self) -> None:
        """Open dialog to add a new engine."""
        engine_controller = self.controller.get_engine_controller()
        dialog = EngineDialog(self.config, engine_controller, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_status("Engine added successfully")
    
    def _update_engines_menu(self) -> None:
        """Update the Engines menu with current engines and assignments."""
        from app.views.menus.engines_menu import rebuild_engines_menu

        rebuild_engines_menu(self)
    
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
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog
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
    
    def _set_engine_for_all_tasks(self, engine_id: str) -> None:
        """Set this engine for all tasks (Game Analysis, Evaluation, Manual Analysis, Brilliancy Detection)."""
        success, message = self.controller.get_engine_controller().set_engine_for_all_tasks(engine_id)
        if success:
            self.controller.set_status(message)
            # Menu will update automatically via assignment_changed signal
        else:
            MessageDialog.show_warning(self.config, "Set Engine for All Tasks Failed", message, self)
    
    def _set_engine_assignment(self, task: str, engine_id: str) -> None:
        """Set engine assignment for a task.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS, TASK_BRILLIANCY_DETECTION).
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

        if hasattr(self, "detail_panel"):
            psv = getattr(self.detail_panel, "player_stats_view", None)
            if psv:
                # Menubar is built before detail_panel; wire Player Stats toggles once the view exists.
                actions = getattr(self, "_player_stats_section_actions", None)
                if actions:
                    self.controller.get_menu_options_sync_controller().bind_player_stats(
                        view=psv,
                        section_actions=actions,
                    )
                else:
                    psv.reload_player_stats_section_prefs_from_settings()

        if hasattr(self, "_sync_player_stats_time_series_menu_from_settings"):
            self._sync_player_stats_time_series_menu_from_settings()
        if hasattr(self, "_sync_player_stats_activity_heatmap_menu_from_settings"):
            self._sync_player_stats_activity_heatmap_menu_from_settings()
        if hasattr(self, "_sync_player_stats_accuracy_distribution_menu_from_settings"):
            self._sync_player_stats_accuracy_distribution_menu_from_settings()

        # First-run welcome message: only set a pending flag here.
        # The actual dialog is shown in `showEvent()` so the main window
        # appears first.
        ui_settings = settings.get("ui", {}) if isinstance(settings.get("ui", {}), dict) else {}
        welcome_shown = bool(ui_settings.get("welcome_shown", False))
        if not welcome_shown:
            welcome_cfg = self.config.get("ui", {}).get("welcome_dialog", {})
            self._welcome_dialog_title = welcome_cfg.get("title", "Welcome to CARA")
            self._welcome_dialog_message = welcome_cfg.get(
                "message",
                'Hi!<br><br>Thanks for installing CARA. On this first start, start with <a href="manual://getting-started">Getting Started</a> (engines, analysis, and navigating moves).',
            )
            self._welcome_dialog_pending = True
        
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
        
        # Annotation moves list highlight: wire annotation model to moves list and load toggle state
        annotations_settings = settings.get("annotations", {})
        highlight_annotated_moves = annotations_settings.get("highlight_annotated_moves_in_list", False)
        if hasattr(self, 'detail_panel') and hasattr(self.detail_panel, 'moveslist_model'):
            moveslist_model = self.detail_panel.moveslist_model
            annotation_controller = self.controller.get_annotation_controller() if self.controller else None
            if annotation_controller:
                moveslist_model.set_annotation_model(annotation_controller.get_annotation_model())
            moveslist_model.set_highlight_annotated_moves(highlight_annotated_moves)
        if hasattr(self, 'highlight_annotated_moves_action'):
            self.highlight_annotated_moves_action.setChecked(highlight_annotated_moves)
        
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

        # Show Game Tags
        show_game_tags_widget = board_visibility.get("show_game_tags_widget", True)
        board_model.set_show_game_tags_widget(show_game_tags_widget)
        self._update_game_tags_widget_action_state(show_game_tags_widget)
        
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
        
        # Show Move Classification Icons
        show_move_classification_icons = board_visibility.get("show_move_classification_icons", False)
        board_model.set_show_move_classification_icons(show_move_classification_icons)
        self._update_move_classification_icons_action_state(show_move_classification_icons)
        
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
        
        game_info_center_mode = board_visibility.get("game_info_center_mode", "center_in_view")
        if game_info_center_mode not in ("center_in_view", "center_over_board"):
            game_info_center_mode = "center_in_view"
        if hasattr(self, "main_panel"):
            self.main_panel.set_game_info_center_mode(game_info_center_mode)
        self._sync_game_info_center_menu_actions(game_info_center_mode)
        
        # ===== PGN MENU SETTINGS (in menu order) =====
        # Load PGN visibility settings
        pgn_visibility = settings.get("pgn_visibility", {})
        show_metadata = pgn_visibility.get("show_metadata", True)
        show_comments = pgn_visibility.get("show_comments", True)
        show_variations = pgn_visibility.get("show_variations", True)
        show_annotations = pgn_visibility.get("show_annotations", True)
        show_results = pgn_visibility.get("show_results", True)
        show_non_standard_tags = pgn_visibility.get("show_non_standard_tags", False)
        
        # Load PGN notation settings
        pgn_notation = settings.get("pgn_notation", {})
        use_symbols_for_nags = pgn_notation.get("use_symbols_for_nags", True)
        show_nag_text = pgn_notation.get("show_nag_text", False)
        
        # Update NAG display menu actions
        if hasattr(self, 'nag_display_symbols_action') and hasattr(self, 'nag_display_text_action'):
            self.nag_display_symbols_action.setChecked(use_symbols_for_nags)
            self.nag_display_text_action.setChecked(not use_symbols_for_nags)
        
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
        
        # Brilliant Move Detection
        brilliant_move_detection = game_analysis_settings.get("brilliant_move_detection", False)
        if hasattr(self, 'brilliant_move_detection_action'):
            self.brilliant_move_detection_action.setChecked(brilliant_move_detection)
        # Pass setting to game analysis controller
        if hasattr(self.controller, 'game_analysis_controller'):
            self.controller.game_analysis_controller.set_brilliant_move_detection(brilliant_move_detection)

        # Auto Tag Games (default ON)
        auto_game_tagging = game_analysis_settings.get("auto_game_tagging", True)
        if hasattr(self, "auto_game_tagging_action"):
            self.auto_game_tagging_action.setChecked(auto_game_tagging)
        if hasattr(self.controller, "game_analysis_controller"):
            self.controller.game_analysis_controller.set_auto_game_tagging(auto_game_tagging)

        # Enabled auto-tags (default: all)
        enabled_auto_tags = game_analysis_settings.get("auto_game_tagging_enabled_tags", None)
        try:
            from app.services.game_auto_tagging_service import AUTO_TAGS
        except Exception:
            AUTO_TAGS = ()  # type: ignore
        if enabled_auto_tags is None or not isinstance(enabled_auto_tags, list):
            enabled_auto_tags = list(AUTO_TAGS)
        enabled_cf = {str(t).casefold() for t in enabled_auto_tags if str(t).strip()}
        # Sync menu checks if present
        try:
            if hasattr(self, "auto_game_tagging_tag_actions") and isinstance(self.auto_game_tagging_tag_actions, dict):
                for t, act in self.auto_game_tagging_tag_actions.items():
                    try:
                        act.blockSignals(True)
                        act.setChecked(str(t).casefold() in enabled_cf)
                    finally:
                        act.blockSignals(False)
        except Exception:
            pass
        # Enable submenu only if auto-tagging enabled
        try:
            if hasattr(self, "select_auto_tags_menu") and self.select_auto_tags_menu:
                self.select_auto_tags_menu.setEnabled(bool(auto_game_tagging))
        except Exception:
            pass
        if hasattr(self.controller, "game_analysis_controller"):
            self.controller.game_analysis_controller.set_auto_game_tagging_enabled_tags(
                [t for t in list(AUTO_TAGS) if str(t).casefold() in enabled_cf]
            )
        
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
        scale_factor = manual_analysis_settings.get("miniature_preview_scale_factor", 1.25)
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
        use_custom = ai_summary_settings.get("use_custom_models", False)
        if sum([use_openai, use_anthropic, use_custom]) != 1:
            use_openai = True
            use_anthropic = False
            use_custom = False
        if hasattr(self, 'ai_summary_use_openai_action'):
            self.ai_summary_use_openai_action.setChecked(use_openai)
        if hasattr(self, 'ai_summary_use_anthropic_action'):
            self.ai_summary_use_anthropic_action.setChecked(use_anthropic)
        if hasattr(self, 'ai_summary_use_custom_action'):
            self.ai_summary_use_custom_action.setChecked(use_custom)
        
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
        
        # Collect PGN notation settings from menu actions
        pgn_notation_settings = None
        if hasattr(self, 'nag_display_symbols_action') and hasattr(self, 'nag_display_text_action'):
            pgn_notation_settings = {
                "use_symbols_for_nags": self.nag_display_symbols_action.isChecked(),
                "show_nag_text": self.nag_display_text_action.isChecked()
            }
        
        # Collect game analysis settings from view
        game_analysis_settings = None
        if hasattr(self, 'return_to_first_move_action'):
            game_analysis_settings = {
                "return_to_first_move_after_analysis": self.return_to_first_move_action.isChecked() if hasattr(self, 'return_to_first_move_action') else False,
                "switch_to_moves_list_at_start_of_analysis": self.switch_to_moves_list_action.isChecked() if hasattr(self, 'switch_to_moves_list_action') else True,
                "switch_to_summary_after_analysis": self.switch_to_summary_action.isChecked() if hasattr(self, 'switch_to_summary_action') else False,
                "normalized_evaluation_graph": self.normalized_graph_action.isChecked() if hasattr(self, 'normalized_graph_action') else False,
                "brilliant_move_detection": self.brilliant_move_detection_action.isChecked() if hasattr(self, 'brilliant_move_detection_action') else False,
                "auto_game_tagging": self.auto_game_tagging_action.isChecked() if hasattr(self, "auto_game_tagging_action") else True,
                "store_analysis_results_in_pgn_tag": self.store_analysis_results_action.isChecked() if hasattr(self, 'store_analysis_results_action') else False
            }
        
        # Persist AI summary provider toggles before saving
        if hasattr(self, 'ai_summary_use_openai_action'):
            ai_summary_settings = {
                "use_openai_models": self.ai_summary_use_openai_action.isChecked(),
                "use_anthropic_models": self.ai_summary_use_anthropic_action.isChecked() if hasattr(self, 'ai_summary_use_anthropic_action') else False,
                "use_custom_models": self.ai_summary_use_custom_action.isChecked() if hasattr(self, 'ai_summary_use_custom_action') else False
            }
            settings_service = getattr(self, '_settings_service', None)
            if settings_service is None:
                from app.services.user_settings_service import UserSettingsService
                settings_service = UserSettingsService.get_instance()
            settings_service.update_ai_summary_settings(ai_summary_settings)
        
        # Save PGN notation settings if collected
        if pgn_notation_settings:
            settings_service = getattr(self, '_settings_service', None)
            if settings_service is None:
                from app.services.user_settings_service import UserSettingsService
                settings_service = UserSettingsService.get_instance()
            settings_service.update_pgn_notation(pgn_notation_settings)
        
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
        from app.views.dialogs.bulk_analysis_dialog import BulkAnalysisDialog
        
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

        # Auto-tagging pass (optional) — updates CARAGameTags in-memory, marks DB unsaved via metadata controller.
        if hasattr(self, "auto_game_tagging_action") and self.auto_game_tagging_action.isChecked():
            try:
                game_controller = self.controller.get_game_controller()
                game_model = game_controller.get_game_model() if game_controller else None
                game = getattr(game_model, "active_game", None) if game_model else None
                if game and hasattr(self, "detail_panel") and hasattr(self.detail_panel, "moveslist_model"):
                    moves = self.detail_panel.moveslist_model.get_all_moves()
                    if moves:
                        from app.services.game_auto_tagging_service import GameAutoTaggingService
                        from app.utils.game_tags_utils import PGN_TAG_NAME_GAME_TAGS, format_game_tags

                        tagging_service = GameAutoTaggingService(self.config)
                        enabled_tags = []
                        try:
                            settings = self._settings_service.get_settings() if hasattr(self, "_settings_service") else {}
                            ga = settings.get("game_analysis", {}) if isinstance(settings, dict) else {}
                            enabled_tags = ga.get("auto_game_tagging_enabled_tags", []) if isinstance(ga, dict) else []
                        except Exception:
                            enabled_tags = []
                        result = tagging_service.detect_tags(
                            moves,
                            game_result=getattr(game, "result", None),
                            enabled_tags=enabled_tags,
                        )
                        merged = tagging_service.merge_with_existing_tags(
                            getattr(game, "game_tags_raw", "") or "",
                            result.detected_tags,
                        )

                        raw = format_game_tags(merged)
                        metadata_controller = self.controller.get_metadata_controller()
                        if raw:
                            metadata_controller.update_metadata_tag(PGN_TAG_NAME_GAME_TAGS, raw)
                        else:
                            metadata_controller.remove_metadata_tag(PGN_TAG_NAME_GAME_TAGS)

                        # Refresh board widget chips immediately (if present)
                        if hasattr(self, "main_panel") and hasattr(self.main_panel, "chessboard_view"):
                            board_widget = getattr(self.main_panel.chessboard_view, "chessboard", None)
                            if board_widget is not None and hasattr(board_widget, "game_tags_widget") and board_widget.game_tags_widget:
                                board_widget.game_tags_widget._refresh()
            except Exception as e:
                from app.services.logging_service import LoggingService

                LoggingService.get_instance().warning(f"Auto-tagging after analysis failed: {e}", exc_info=e)
    
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
    
    def _on_bulk_analysis_finished_refresh_active_game(self, success: bool, message: str) -> None:
        """When bulk analysis finishes (success or cancel), refresh active game state so Game Summary
        becomes available if the active game was among those already analyzed."""
        if not hasattr(self, 'detail_panel') or not hasattr(self.detail_panel, 'moveslist_model'):
            return
        game_controller = self.controller.get_game_controller()
        game_controller.refresh_active_game_analysis_state(self.detail_panel.moveslist_model)

    def _on_bulk_analysis_game_analyzed_refresh_active_game_ui(self, game) -> None:
        """If the analyzed game is currently active, refresh UI elements that depend on PGN headers."""
        try:
            game_controller = self.controller.get_game_controller()
            game_model = game_controller.get_game_model() if game_controller else None
            active_game = getattr(game_model, "active_game", None) if game_model else None
            if not active_game or not game:
                return

            same_game = False
            if active_game is game:
                same_game = True
            else:
                # Fallback: compare by game_number if available (stable across copies).
                agn = getattr(active_game, "game_number", None)
                ggn = getattr(game, "game_number", None)
                if agn is not None and ggn is not None and agn == ggn:
                    same_game = True

            if not same_game:
                return

            # Signal metadata change so views can re-read header-derived fields.
            if hasattr(game_model, "metadata_updated"):
                game_model.metadata_updated.emit()
            game_model.game_tags_changed.emit()

            # Refresh board tags widget immediately (avoid needing a game switch).
            if hasattr(self, "main_panel") and hasattr(self.main_panel, "chessboard_view"):
                board_widget = getattr(self.main_panel.chessboard_view, "chessboard", None)
                if board_widget is not None and hasattr(board_widget, "game_tags_widget") and board_widget.game_tags_widget:
                    board_widget.game_tags_widget._refresh()
        except Exception as e:
            from app.services.logging_service import LoggingService

            LoggingService.get_instance().warning(
                f"Failed to refresh active game UI after bulk analysis update: {e}", exc_info=e
            )
    
    def _on_game_analysis_progress(self, current_move: int, total_moves: int, depth: int,
                                   centipawns: float, engine_name: str, threads: int, elapsed_ms: int,
                                   avg_depth: float = 0.0, avg_seldepth: float = 0.0, movetime_ms: int = 0, avg_nps: float = 0.0) -> None:
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
        
        # Add average NPS if available (only if we have completed moves with NPS data)
        if avg_nps > 0:
            # Format nps nicely (e.g., 1.5M, 500K, etc.)
            if avg_nps >= 1_000_000:
                nps_str = f"{avg_nps / 1_000_000:.1f}M"
            elif avg_nps >= 1_000:
                nps_str = f"{avg_nps / 1_000:.1f}K"
            else:
                nps_str = str(int(avg_nps))
            status_parts.append(f"Avg NPS: {nps_str}")
        
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


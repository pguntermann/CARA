"""PGN Notation view for detail panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QMenu
from PyQt6.QtGui import QPalette, QColor, QFont, QTextCursor, QTextCharFormat, QMouseEvent, QContextMenuEvent, QAction, QKeyEvent, QKeySequence, QShortcut, QTextDocument
from PyQt6.QtCore import Qt, QPoint
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING, Callable, Sequence

from app.services.pgn_formatter_service import (
    PgnFormatterService,
    PgnRangeMap,
    build_pgn_range_map_from_fragments,
    clean_pgn_text,
)
from app.models.game_model import GameModel
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.pgn_variation_path import Path, is_mainline_path
from app.views.style.style_manager import StyleManager
from app.views.widgets.branch_select_overlay import BranchSelectOverlay

if TYPE_CHECKING:
    from app.controllers.game_controller import GameController


def _range_map_from_document(document: Optional[QTextDocument]) -> PgnRangeMap:
    """Extract move/comment ranges from cara-* href anchors in the rendered document."""
    if document is None:
        return PgnRangeMap()
    fragments: List[Tuple[int, int, str]] = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                if fmt.isAnchor():
                    href = fmt.anchorHref() or ""
                    if href:
                        fragments.append((frag.position(), frag.length(), href))
            it += 1
        block = block.next()
    return build_pgn_range_map_from_fragments(fragments)


class ClickablePgnTextEdit(QTextEdit):
    """Custom QTextEdit that handles mouse clicks for move navigation."""
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the clickable PGN text edit.
        
        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._click_handler: Optional[Callable[[int], int]] = None
        self._move_checker: Optional[Callable[[int], int]] = None
        self._comment_double_click_handler: Optional[Callable[[int], bool]] = None
        self._key_handler: Optional[Callable[[QKeyEvent], bool]] = None
        
        # Install a shortcut to override default Ctrl+C behavior
        # This ensures our custom copy() method is called even if Qt handles the shortcut
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        copy_shortcut.activated.connect(self.copy)
        # Also handle Cmd+C on macOS
        copy_shortcut_mac = QShortcut(QKeySequence("Meta+C"), self)
        copy_shortcut_mac.activated.connect(self.copy)
    
    def set_click_handler(self, handler: Callable[[int], int]) -> None:
        """Set the handler function to call when a move is clicked.
        
        Args:
            handler: Function that takes a document position and returns ply index (or 0 if no move).
        """
        self._click_handler = handler
    
    def set_move_checker(self, checker: Callable[[int], int]) -> None:
        """Set the function to check if there's a move at a position (without navigating).
        
        Args:
            checker: Function that takes a document position and returns ply index (or 0 if no move).
        """
        self._move_checker = checker
    
    def set_comment_double_click_handler(self, handler: Optional[Callable[[int], bool]]) -> None:
        """Set handler for left double-clicks on PGN comment text (returns True if handled)."""
        self._comment_double_click_handler = handler
    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._comment_double_click_handler
        ):
            cursor = self.cursorForPosition(event.pos())
            if self._comment_double_click_handler(cursor.position()):
                event.accept()
                return
        super().mouseDoubleClickEvent(event)
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse click to navigate to clicked move.
        
        Args:
            event: Mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton and self._click_handler:
            # Get cursor position from click
            cursor = self.cursorForPosition(event.pos())
            click_pos = cursor.position()
            
            # Call handler to find move and navigate
            ply_index = self._click_handler(click_pos)
            
            if ply_index > 0:
                # Move was found and navigation should happen
                # Don't call super() to prevent default text selection behavior
                event.accept()
                return
        
        # For non-move clicks or if no handler, use default behavior
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to change cursor when over clickable moves.
        
        Args:
            event: Mouse event.
        """
        if self._move_checker:
            # Get cursor position from mouse position
            cursor = self.cursorForPosition(event.pos())
            click_pos = cursor.position()
            
            # Check if there's a move at this position (without navigating)
            ply_index = self._move_checker(click_pos)
            
            if ply_index > 0:
                # Over a clickable move - show pointing hand cursor
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                # Not over a move - show default text cursor
                self.setCursor(Qt.CursorShape.IBeamCursor)
        
        super().mouseMoveEvent(event)
    
    def set_key_handler(self, handler: Optional[Callable[[QKeyEvent], bool]]) -> None:
        """Set an optional key handler; return True if the event was consumed."""
        self._key_handler = handler

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Override key press to intercept Ctrl+C (or Cmd+C on macOS) and use our custom copy.
        
        Args:
            event: Key event.
        """
        # Check for Ctrl+C (or Cmd+C on macOS)
        # ControlModifier works for both Ctrl on Windows/Linux and Cmd on macOS
        if event.key() == Qt.Key.Key_C and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            # Call our custom copy method
            self.copy()
            event.accept()
            return

        if self._key_handler is not None and self._key_handler(event):
            event.accept()
            return
        
        # For all other keys, use default behavior
        super().keyPressEvent(event)
    
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Override context menu to ensure copy action uses our cleaned text.
        
        Args:
            event: Context menu event.
        """
        # Create standard context menu (copy/paste/select actions etc.)
        menu = self.createStandardContextMenu()

        # Apply context menu styling (font/size/bg from ui.styles.context_menu).
        parent_view = self.parent()
        cfg = getattr(parent_view, "config", None) if parent_view else None
        if isinstance(cfg, dict):
            from app.views.style import StyleManager
            from app.views.style.context_menu import apply_dark_standard_textedit_context_menu_icons

            StyleManager.style_context_menu(menu, cfg)
            apply_dark_standard_textedit_context_menu_icons(menu, cfg)

        # Find and replace the copy action to use our custom copy method
        copy_action = None
        for action in menu.actions():
            # Check for copy action by text (handles different locales)
            action_text = action.text().lower().replace('&', '')
            if 'copy' in action_text:
                copy_action = action
                break
        
        if copy_action:
            # Disconnect any existing connections (ignore errors if not connected)
            try:
                copy_action.triggered.disconnect()
            except TypeError:
                # Action wasn't connected, that's fine
                pass
            # Connect to our custom copy method
            copy_action.triggered.connect(self.copy)
        
        # Append the PGN menubar menu items to the context menu (mirrors layout).
        from PyQt6.QtWidgets import QApplication
        from app.views.menus.pgn_context_menu import append_pgn_menu_items_to_context_menu

        mw = QApplication.activeWindow()
        if mw is not None and isinstance(cfg, dict):
            menu.addSeparator()
            append_pgn_menu_items_to_context_menu(menu, mw, config=cfg)

        from app.views.style.context_menu import try_wire_context_menu_shared_action_icons

        try_wire_context_menu_shared_action_icons(menu)
        menu.exec(event.globalPos())
    
    def copy(self) -> None:
        """Override copy to normalize PGN text before placing it on the clipboard.
        
        This intercepts both keyboard shortcuts (Ctrl+C) and context menu copy actions.
        """
        # Get selected text or all text if no selection
        cursor = self.textCursor()
        if cursor.hasSelection():
            # For selections, use selectedText() (HTML formatting is stripped)
            # Note: This may lose some formatting, but we'll do our best to clean it
            text_to_copy = cursor.selectedText()
        else:
            # If no selection, use the original PGN text from parent view
            # This preserves the original formatting and structure
            parent_view = self.parent()
            if parent_view and hasattr(parent_view, '_current_pgn_text'):
                text_to_copy = parent_view._current_pgn_text
            else:
                # Fallback to toPlainText() if parent view not available
                text_to_copy = self.toPlainText()
        
        # Clean and format the text (header layout, CRLF, fixed-width export)
        cleaned_text = clean_pgn_text(text_to_copy)
        
        # Set clipboard directly (don't call super().copy() to avoid copying uncleaned text)
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(cleaned_text)
        
        # Show status message to user
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        if cursor.hasSelection():
            progress_service.set_status("Copied selected PGN text to clipboard")
        else:
            progress_service.set_status("Copied PGN to clipboard")


class DetailPgnView(QWidget):
    """PGN notation view displaying formatted PGN text with colors."""
    
    def __init__(self, config: Dict[str, Any], game_model: Optional[GameModel] = None,
                 game_controller: Optional['GameController'] = None) -> None:
        """Initialize the PGN notation view.
        
        Args:
            config: Configuration dictionary.
            game_model: Optional GameModel to observe for active move changes.
            game_controller: Optional GameController for navigating to specific plies.
        """
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._game_controller: Optional['GameController'] = None
        self._current_pgn_text: str = ""  # Store plain PGN text for re-formatting
        self._current_formatted_html: str = ""  # Store formatted HTML (debug / re-display)
        self._move_info: List[Tuple[str, int, bool]] = []  # List of (move_san, move_number, is_white) tuples for each ply
        self._range_map: PgnRangeMap = PgnRangeMap()  # Move/comment ranges from rendered anchors
        self._active_move_ply: int = 0  # Current active move ply (0 = starting position)
        self._active_path: Path = ()
        self._show_metadata: bool = True  # Whether to show metadata tags in PGN view
        self._show_comments: bool = True  # Whether to show comments in PGN view
        self._show_variations: bool = True  # Whether to show variations in PGN view
        self._show_annotations: bool = True  # Whether to show annotations in PGN view
        self._show_results: bool = True  # Whether to show results in PGN view
        self._show_non_standard_tags: bool = False  # Whether to show non-standard tags like [%evp], [%mdl] in comments
        self._pgn_notation_settings: Dict[str, Any] = {}  # PGN notation settings (use_symbols_for_nags, show_nag_text)
        self._open_move_comment_row: Optional[Callable[[int], None]] = None
        self._branch_overlay = BranchSelectOverlay(self.config, parent=self)
        self._branch_overlay.choice_activated.connect(self._on_branch_choice_activated)
        self._branch_overlay.dismissed.connect(self._on_branch_overlay_dismissed)
        # Application-wide Up/Down while the overlay is open (enabled only then so PGN
        # scrolling and other views keep normal arrow-key behavior otherwise).
        self._branch_nav_up = QShortcut(QKeySequence(Qt.Key.Key_Up), self)
        self._branch_nav_up.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._branch_nav_up.setEnabled(False)
        self._branch_nav_up.activated.connect(lambda: self.handle_variation_nav_vertical(-1))
        self._branch_nav_down = QShortcut(QKeySequence(Qt.Key.Key_Down), self)
        self._branch_nav_down.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._branch_nav_down.setEnabled(False)
        self._branch_nav_down.activated.connect(lambda: self.handle_variation_nav_vertical(1))
        self._setup_ui()
        
        # Load initial PGN notation settings from user settings
        self._load_pgn_notation_settings()
        
        # Connect to user settings model for PGN notation changes
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_model = settings_service.get_model()
        settings_model.pgn_notation_changed.connect(self._on_pgn_notation_changed)
        
        # Connect to game model if provided
        if game_model:
            self.set_game_model(game_model)
        
        # Set game controller if provided
        if game_controller:
            self.set_game_controller(game_controller)
    
    def _setup_ui(self) -> None:
        """Setup the PGN notation UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Get PGN config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        pgn_config = panel_config.get('pgn_notation', {})
        
        # PGN Text widget - use custom clickable version
        self.pgn_text = ClickablePgnTextEdit()
        self.pgn_text.setReadOnly(True)  # Display only for now
        self.pgn_text.setAcceptRichText(True)  # Enable HTML/rich text formatting
        # Set click handler to find moves and navigate
        self.pgn_text.set_click_handler(self._handle_pgn_click)
        # Set move checker for cursor changes (without navigating)
        self.pgn_text.set_move_checker(self._find_navigable_move_at_position)
        self.pgn_text.set_comment_double_click_handler(self._handle_pgn_comment_double_click)
        self.pgn_text.set_key_handler(self._handle_pgn_key_while_branch_overlay)
        
        # Configure PGN text styling
        pgn_font_family = resolve_font_family(pgn_config.get('font_family', 'Courier New'))
        pgn_font_size = int(scale_font_size(pgn_config.get('font_size', 11)))
        pgn_text_color = pgn_config.get('text_color', [220, 220, 220])
        pgn_background_color = pgn_config.get('background_color', [30, 30, 35])
        pgn_border_color = pgn_config.get('border_color', [60, 60, 65])
        pgn_border_width = int(pgn_config.get('border_width', 1))
        pgn_padding = int(pgn_config.get('padding', 5))
        
        # Set font
        pgn_font = QFont(pgn_font_family, pgn_font_size)
        self.pgn_text.setFont(pgn_font)
        
        # Set background and text colors via stylesheet
        pgn_bg_rgb = f"rgb({pgn_background_color[0]}, {pgn_background_color[1]}, {pgn_background_color[2]})"
        pgn_text_rgb = f"rgb({pgn_text_color[0]}, {pgn_text_color[1]}, {pgn_text_color[2]})"
        pgn_border_rgb = f"rgb({pgn_border_color[0]}, {pgn_border_color[1]}, {pgn_border_color[2]})"
        text_edit_style = f"""
            QTextEdit {{
                background-color: {pgn_bg_rgb};
                color: {pgn_text_rgb};
                border: {pgn_border_width}px solid {pgn_border_rgb};
                padding: {pgn_padding}px;
            }}
        """
        
        # Apply scrollbar styling using StyleManager
        StyleManager.style_text_edit_scrollbar(
            self.pgn_text,
            self.config,
            pgn_background_color,
            pgn_border_color,
            text_edit_style
        )
        
        # Set placeholder text
        placeholder = pgn_config.get('placeholder_text', 'PGN notation will appear here...')
        self.pgn_text.setPlaceholderText(placeholder)
        layout.addWidget(self.pgn_text)
    
    
    def set_pgn_text(self, text: str) -> None:
        """Set the PGN text content.
        
        Args:
            text: Plain PGN text content (will be formatted to HTML with styling).
        """
        # Store plain text
        self._current_pgn_text = text
        
        # Extract move info from ORIGINAL (unfiltered) PGN text
        # This ensures move extraction works correctly even when filtering is applied
        # Filtering can break PGN structure, making move extraction fail
        original_move_info = []
        if text:
            try:
                _, original_move_info = PgnFormatterService.format_pgn_to_html(
                    text, 
                    self.config, 
                    0  # Don't highlight in HTML formatting
                )
            except Exception:
                # If extraction fails, use empty list
                original_move_info = []
        
        # Filter PGN text based on visibility flags (for display only)
        # Use service to filter PGN text
        pgn_text_to_format = PgnFormatterService.filter_pgn_for_display(
            text,
            show_metadata=self._show_metadata,
            show_comments=self._show_comments,
            show_variations=self._show_variations,
            show_annotations=self._show_annotations,
            show_results=self._show_results,
            show_non_standard_tags=self._show_non_standard_tags
        )
        
        # Format and display filtered PGN
        if pgn_text_to_format:
            formatted_html, _ = PgnFormatterService.format_pgn_to_html(
                pgn_text_to_format, 
                self.config, 
                0,  # Don't highlight in HTML formatting
                pgn_notation_settings=self._pgn_notation_settings  # Pass user settings
            )
            self.pgn_text.setHtml(formatted_html)
            # Store formatted HTML and move info; range map is built once from clean HTML
            # (ExtraSelections highlight does not mutate document formats).
            self._current_formatted_html = formatted_html
            self._move_info = original_move_info
            self._range_map = _range_map_from_document(self.pgn_text.document())
            self.pgn_text.setExtraSelections([])

            # Re-apply highlighting for current active move after HTML is laid out
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._highlight_active_move)
        else:
            self.pgn_text.setPlainText("")
            self.pgn_text.setExtraSelections([])
            self._current_formatted_html = ""
            self._move_info = []
            self._range_map = PgnRangeMap()
    
    def set_show_metadata(self, show: bool) -> None:
        """Set whether to show metadata tags in PGN view.
        
        Args:
            show: True to show metadata tags, False to hide them.
        """
        self._show_metadata = show
    
    def set_show_comments(self, show: bool) -> None:
        """Set whether to show comments in PGN view.
        
        Args:
            show: True to show comments, False to hide them.
        """
        self._show_comments = show
    
    def set_show_variations(self, show: bool) -> None:
        """Set whether to show variations in PGN view.
        
        Args:
            show: True to show variations, False to hide them.
        """
        self._show_variations = show
        if not show and self._game_controller is not None:
            # Viewing a sideline while variations are hidden → snap to mainline.
            if not is_mainline_path(self._active_path):
                self._game_controller.return_to_mainline_ancestor()
            self._branch_overlay.hide_overlay()
    
    def set_show_annotations(self, show: bool) -> None:
        """Set whether to show annotations in PGN view.
        
        Args:
            show: True to show annotations, False to hide them.
        """
        self._show_annotations = show
    
    def set_show_results(self, show: bool) -> None:
        """Set whether to show results in PGN view.
        
        Args:
            show: True to show results, False to hide them.
        """
        self._show_results = show
        # Refresh PGN display to apply filtering
        if self._current_pgn_text:
            self.set_pgn_text(self._current_pgn_text)
    
    def set_show_non_standard_tags(self, show: bool) -> None:
        """Set whether to show non-standard tags (like [%evp], [%mdl]) in comments.
        
        Args:
            show: True to show non-standard tags, False to hide them.
        """
        self._show_non_standard_tags = show
    
    def _load_pgn_notation_settings(self) -> None:
        """Load PGN notation settings from user settings service."""
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings_model = settings_service.get_model()
        self._pgn_notation_settings = settings_model.get_pgn_notation()
    
    def _on_pgn_notation_changed(self) -> None:
        """Handle PGN notation settings change.
        
        Reloads settings and refreshes PGN display.
        """
        self._load_pgn_notation_settings()
        if self._current_pgn_text:
            self.set_pgn_text(self._current_pgn_text)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe for active move changes.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            try:
                self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            except TypeError:
                pass
            try:
                self._game_model.active_path_changed.disconnect(self._on_active_path_changed)
            except TypeError:
                pass
            try:
                self._game_model.metadata_updated.disconnect(self._on_metadata_updated)
            except TypeError:
                pass
        
        self._game_model = model
        
        # Connect to model signals
        model.active_move_changed.connect(self._on_active_move_changed)
        model.active_path_changed.connect(self._on_active_path_changed)
        model.metadata_updated.connect(self._on_metadata_updated)
        
        # Initialize with current active move if any
        self._on_active_path_changed(model.get_active_path())
    
    def set_game_controller(self, controller: 'GameController') -> None:
        """Set the game controller for navigating to specific plies.
        
        Args:
            controller: The GameController instance.
        """
        self._game_controller = controller

    def set_navigate_variations_enabled(self, enabled: bool) -> None:
        """Enable/disable variation navigation UI (overlay + path clicks)."""
        if self._game_controller is not None:
            self._game_controller.set_navigate_variations_enabled(enabled)
        if not enabled:
            self._branch_overlay.hide_overlay()
            if self._game_controller is not None:
                self._game_controller.return_to_mainline_ancestor()
    
    def set_open_move_comment_row_callback(
        self, callback: Optional[Callable[[int], None]]
    ) -> None:
        """Register callback (moves-list row index) to open the move-comment editor from the PGN pane."""
        self._open_move_comment_row = callback
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from model (mainline consumer ply)."""
        self._active_move_ply = ply_index
        if self._game_model is not None:
            self._active_path = self._game_model.get_active_path()
        self._highlight_active_move()

    def _on_active_path_changed(self, path: object) -> None:
        """Handle active variation path changes."""
        if isinstance(path, tuple):
            self._active_path = tuple(int(i) for i in path)
        else:
            self._active_path = ()
        if self._game_model is not None:
            self._active_move_ply = self._game_model.get_active_move_ply()
        self._highlight_active_move()
        # Path changes from outside dismiss an open chooser.
        if self._branch_overlay.is_open():
            self._branch_overlay.hide_overlay()
    
    def _on_metadata_updated(self) -> None:
        """Handle metadata update from model - refresh PGN display.
        
        This is called when metadata tags are added, edited, or removed.
        Also called when PGN is permanently modified (e.g., after removing elements).
        """
        if self._game_model and self._game_model.active_game:
            # Update PGN text (this will re-extract move info and format)
            # Note: set_pgn_text already calls _highlight_active_move via QTimer,
            # but we add an additional call with longer delay to ensure it works
            # after permanent PGN modifications that might change the structure
            self.set_pgn_text(self._game_model.active_game.pgn)
            # Re-apply highlighting for the current active move after a longer delay
            # This ensures the HTML is fully rendered and move extraction completed
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._highlight_active_move())
    
    def get_debug_info(self) -> tuple[str, dict]:
        """Get debug information about current HTML and visibility settings.
        
        Returns:
            Tuple of (html: str, settings: dict) where:
            - html: The current formatted HTML in the PGN view
            - settings: Dictionary with current visibility settings
        """
        settings = {
            'show_metadata': self._show_metadata,
            'show_comments': self._show_comments,
            'show_variations': self._show_variations,
            'show_annotations': self._show_annotations,
            'show_results': self._show_results,
            'show_non_standard_tags': self._show_non_standard_tags,
        }
        return (self._current_formatted_html, settings)
    
    def _highlight_active_move(self) -> None:
        """Highlight the active move via ExtraSelections (document HTML stays unchanged)."""
        if not self.pgn_text.document():
            self.pgn_text.setExtraSelections([])
            return

        document = self.pgn_text.document()
        document_length = document.characterCount()
        if document_length <= 0:
            self.pgn_text.setExtraSelections([])
            return

        move_start = None
        move_end = None
        if self._active_path and not is_mainline_path(self._active_path):
            path_range = self._range_map.path_range(self._active_path)
            if path_range is not None:
                move_start, move_end = path_range.start, path_range.end
        elif self._active_move_ply > 0:
            move_range = self._range_map.move_range(self._active_move_ply)
            if move_range is not None:
                move_start, move_end = move_range.start, move_range.end

        if move_start is None or move_end is None:
            self.pgn_text.setExtraSelections([])
            return
        if move_start < 0 or move_end <= move_start or move_end > document_length:
            self.pgn_text.setExtraSelections([])
            return

        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        pgn_config = panel_config.get('pgn_notation', {})
        formatting = pgn_config.get('formatting', {})
        active_move_config = formatting.get('active_move', {})

        bg_color = active_move_config.get('background_color', [100, 120, 180])
        text_color = active_move_config.get('text_color', [255, 255, 255])
        bold = active_move_config.get('bold', True)

        cursor = QTextCursor(document)
        cursor.setPosition(move_start)
        cursor.setPosition(move_end, QTextCursor.MoveMode.KeepAnchor)

        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(bg_color[0], bg_color[1], bg_color[2]))
        highlight_format.setForeground(QColor(text_color[0], text_color[1], text_color[2]))
        if bold:
            highlight_format.setFontWeight(QFont.Weight.Bold)

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = highlight_format
        self.pgn_text.setExtraSelections([selection])

        # Scroll to the active move without replacing the document selection permanently
        visible = QTextCursor(document)
        visible.setPosition(move_start)
        self.pgn_text.setTextCursor(visible)
        self.pgn_text.ensureCursorVisible()
    
    def get_pgn_text(self) -> str:
        """Get the current PGN text content.
        
        Returns:
            Current PGN text content.
        """
        return self._current_pgn_text if self._current_pgn_text else self.pgn_text.toPlainText()
    
    def _moves_list_row_for_pgn_comment_at_position(self, position: int) -> Optional[int]:
        """Map a document position inside a main-line comment to moves-list row (0-based)."""
        if not self._show_comments:
            return None
        document = self.pgn_text.document()
        if not document or position < 0 or position >= document.characterCount():
            return None
        ply = self._range_map.comment_ply_at(position)
        if ply is None:
            return None
        return (ply - 1) // 2
    
    def _handle_pgn_comment_double_click(self, position: int) -> bool:
        row = self._moves_list_row_for_pgn_comment_at_position(position)
        if row is None or self._open_move_comment_row is None:
            return False
        self._open_move_comment_row(row)
        return True
    
    def _handle_pgn_click(self, click_pos: int) -> int:
        """Handle click on PGN text at given position.
        
        Args:
            click_pos: Document character position where click occurred.
            
        Returns:
            Ply index if main-line move found, 0 otherwise.
        """
        self._branch_overlay.hide_overlay()

        path = self._range_map.path_at(click_pos)
        if (
            path is not None
            and self._game_controller is not None
            and self._game_controller.is_navigate_variations_enabled()
            and self._show_variations
        ):
            self._game_controller.navigate_to_path(path)
            return 0

        ply_index = self._find_mainline_move_at_position(click_pos)
        if ply_index > 0 and self._game_controller:
            self._game_controller.navigate_to_ply(ply_index)
        return ply_index
    
    def _find_mainline_move_at_position(self, position: int) -> int:
        """Find ply index of main-line move at given document position.
        
        Uses the one-way range map built from ``cara-ply`` href anchors.
        Returns 0 if no main-line move found at position.
        
        Args:
            position: Document character position.
            
        Returns:
            Ply index (1-based) if main-line move found, 0 otherwise.
        """
        if not self.pgn_text.document():
            return 0
        
        document = self.pgn_text.document()
        document_length = document.characterCount()
        if document_length == 0 or position < 0 or position >= document_length:
            return 0

        return self._range_map.move_ply_at(position)

    def _find_navigable_move_at_position(self, position: int) -> int:
        """Return non-zero when the cursor is over a clickable mainline or variation move."""
        if self._find_mainline_move_at_position(position) > 0:
            return 1
        if (
            self._game_controller is not None
            and self._game_controller.is_navigate_variations_enabled()
            and self._show_variations
            and self._range_map.path_at(position) is not None
        ):
            return 1
        return 0

    def handle_variation_nav_forward(self) -> bool:
        """Handle Right-key navigation when variation navigation is enabled.

        Returns True if the event was consumed (overlay shown/committed or path advanced).
        """
        if self._game_controller is None or not self._game_controller.is_navigate_variations_enabled():
            return False
        if not self._show_variations:
            return False

        if self._branch_overlay.is_open():
            self._branch_overlay.activate_selected()
            return True

        choices = self._game_controller.get_forward_branch_choices()
        if len(choices) > 1:
            self._show_branch_overlay(choices)
            return True
        if len(choices) == 1:
            return self._game_controller.navigate_to_path(choices[0][0])
        return False

    def handle_variation_nav_back(self) -> bool:
        """Handle Left-key navigation when variation navigation is enabled."""
        if self._game_controller is None or not self._game_controller.is_navigate_variations_enabled():
            return False
        if self._branch_overlay.is_open():
            self._branch_overlay.hide_overlay()
            return True
        return self._game_controller.navigate_to_previous_move()

    def handle_variation_nav_vertical(self, delta: int) -> bool:
        """Handle Up/Down while the branch overlay is open."""
        if not self._branch_overlay.is_open():
            return False
        self._branch_overlay.move_selection(delta)
        return True

    def _set_branch_nav_shortcuts_enabled(self, enabled: bool) -> None:
        self._branch_nav_up.setEnabled(enabled)
        self._branch_nav_down.setEnabled(enabled)

    def _on_branch_overlay_dismissed(self) -> None:
        self._set_branch_nav_shortcuts_enabled(False)

    def _handle_pgn_key_while_branch_overlay(self, event: QKeyEvent) -> bool:
        """Consume arrow/confirm keys in the PGN pane while the branch overlay is open."""
        if not self._branch_overlay.is_open():
            return False
        key = event.key()
        if key == Qt.Key.Key_Up:
            return self.handle_variation_nav_vertical(-1)
        if key == Qt.Key.Key_Down:
            return self.handle_variation_nav_vertical(1)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._branch_overlay.activate_selected()
            return True
        if key == Qt.Key.Key_Escape:
            self._branch_overlay.hide_overlay()
            return True
        return False

    def _show_branch_overlay(self, choices: Sequence[Tuple[Path, str]]) -> None:
        anchor = self._overlay_anchor_global_pos()
        self._branch_overlay.refresh_style(self.config)
        self._branch_overlay.show_choices(
            choices,
            anchor_global=anchor,
            selected_index=0,
            constrain_widget=self.pgn_text.viewport(),
        )
        self._set_branch_nav_shortcuts_enabled(True)

    def _overlay_anchor_global_pos(self) -> QPoint:
        """Place the overlay near the current active move in the PGN pane."""
        document = self.pgn_text.document()
        cursor = QTextCursor(document)
        move_range = None
        if self._active_path and not is_mainline_path(self._active_path):
            move_range = self._range_map.path_range(self._active_path)
        elif self._active_move_ply > 0:
            move_range = self._range_map.move_range(self._active_move_ply)
        if move_range is not None:
            cursor.setPosition(move_range.end)
        rect = self.pgn_text.cursorRect(cursor)
        local = rect.bottomRight()
        return self.pgn_text.mapToGlobal(local)

    def _on_branch_choice_activated(self, path: object) -> None:
        if self._game_controller is None:
            return
        if isinstance(path, tuple):
            self._game_controller.navigate_to_path(path)


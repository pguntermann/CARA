"""PGN Notation view for detail panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QPalette, QColor, QFont, QTextCursor, QTextCharFormat, QMouseEvent
from PyQt6.QtCore import Qt, QRegularExpression
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING, Callable
import re

from app.services.pgn_formatter_service import PgnFormatterService
from app.models.game_model import GameModel
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style.style_manager import StyleManager

if TYPE_CHECKING:
    from app.controllers.game_controller import GameController


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
        self._current_formatted_html: str = ""  # Store formatted HTML for highlighting
        self._move_info: List[Tuple[str, int, bool]] = []  # List of (move_san, move_number, is_white) tuples for each ply
        self._active_move_ply: int = 0  # Current active move ply (0 = starting position)
        self._last_highlighted_start: int = -1  # Track last highlighted position for clearing
        self._last_highlighted_length: int = 0
        self._show_metadata: bool = True  # Whether to show metadata tags in PGN view
        self._show_comments: bool = True  # Whether to show comments in PGN view
        self._show_variations: bool = True  # Whether to show variations in PGN view
        self._show_annotations: bool = True  # Whether to show annotations in PGN view
        self._show_results: bool = True  # Whether to show results in PGN view
        self._show_non_standard_tags: bool = False  # Whether to show non-standard tags like [%evp], [%mdl] in comments
        self._setup_ui()
        
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
        self.pgn_text.set_move_checker(self._find_mainline_move_at_position)
        
        # Configure PGN text styling
        pgn_font_family = resolve_font_family(pgn_config.get('font_family', 'Courier New'))
        pgn_font_size = int(scale_font_size(pgn_config.get('font_size', 11)))
        pgn_text_color = pgn_config.get('text_color', [220, 220, 220])
        pgn_background_color = pgn_config.get('background_color', [30, 30, 35])
        
        # Set font
        pgn_font = QFont(pgn_font_family, pgn_font_size)
        self.pgn_text.setFont(pgn_font)
        
        # Set background and text colors via stylesheet
        pgn_bg_rgb = f"rgb({pgn_background_color[0]}, {pgn_background_color[1]}, {pgn_background_color[2]})"
        pgn_text_rgb = f"rgb({pgn_text_color[0]}, {pgn_text_color[1]}, {pgn_text_color[2]})"
        text_edit_style = f"""
            QTextEdit {{
                background-color: {pgn_bg_rgb};
                color: {pgn_text_rgb};
                border: 1px solid rgb(60, 60, 65);
                padding: 5px;
            }}
        """
        
        # Apply scrollbar styling using StyleManager
        StyleManager.style_text_edit_scrollbar(
            self.pgn_text,
            self.config,
            pgn_background_color,
            [60, 60, 65],  # Border color (matches the border in stylesheet)
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
                0  # Don't highlight in HTML formatting
            )
            self.pgn_text.setHtml(formatted_html)
            # Store formatted HTML and move info for highlighting
            # Use original move info (from unfiltered PGN) for highlighting
            self._current_formatted_html = formatted_html
            self._move_info = original_move_info
            
            # Re-apply highlighting for current active move
            # Use QTimer to ensure the HTML is rendered before highlighting
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._highlight_active_move)
        else:
            self.pgn_text.setPlainText("")
            self._current_formatted_html = ""
            self._move_info = []
            self._last_highlighted_start = -1
            self._last_highlighted_length = 0
    
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
        # Refresh PGN display to apply filtering
        if self._current_pgn_text:
            self.set_pgn_text(self._current_pgn_text)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe for active move changes.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            self._game_model.metadata_updated.disconnect(self._on_metadata_updated)
        
        self._game_model = model
        
        # Connect to model signals
        model.active_move_changed.connect(self._on_active_move_changed)
        model.metadata_updated.connect(self._on_metadata_updated)
        
        # Initialize with current active move if any
        self._on_active_move_changed(model.get_active_move_ply())
    
    def set_game_controller(self, controller: 'GameController') -> None:
        """Set the game controller for navigating to specific plies.
        
        Args:
            controller: The GameController instance.
        """
        self._game_controller = controller
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from model.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        self._active_move_ply = ply_index
        self._highlight_active_move()
    
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
        """Highlight the active move in the PGN text by finding it directly in the document."""
        # Ensure document is ready
        if not self.pgn_text.document():
            return
        
        document = self.pgn_text.document()
        document_length = document.characterCount()
        
        # If document is empty, nothing to highlight
        if document_length == 0:
            return
        
        # Special case: When ply is 0 (starting position), force-clear all highlighting
        if self._active_move_ply == 0:
            # Clear any existing highlighting by re-applying the HTML (which restores formatting)
            # This preserves the PGN formatting while removing the highlight
            if self._current_formatted_html:
                try:
                    # Re-apply the HTML to restore original formatting (without highlight)
                    self.pgn_text.setHtml(self._current_formatted_html)
                except Exception:
                    # If re-applying fails, try to clear just the background/foreground colors
                    # by iterating through the document and clearing only highlight colors
                    try:
                        cursor = QTextCursor(document)
                        cursor.movePosition(QTextCursor.MoveOperation.Start)
                        while not cursor.atEnd():
                            format = cursor.charFormat()
                            # Only clear if there's a background color (indicating highlighting)
                            bg_color = format.background()
                            if bg_color.isValid() and bg_color.alpha() > 0:
                                # Clear background to remove highlighting
                                format.setBackground(QColor())  # Clear background
                                cursor.setCharFormat(format)
                            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                    except Exception:
                        # If all else fails, just reset stored positions
                        pass
            
            # Reset stored positions
            self._last_highlighted_start = -1
            self._last_highlighted_length = 0
            return  # No move to highlight at starting position
        
        # Clear previous highlighting - check if positions are valid first
        if self._last_highlighted_start >= 0 and self._last_highlighted_length > 0:
            # Check if the stored positions are still valid
            if self._last_highlighted_start < document_length:
                # Calculate end position, but cap it at document length
                end_position = min(self._last_highlighted_start + self._last_highlighted_length, document_length)
                if end_position > self._last_highlighted_start:
                    try:
                        cursor = QTextCursor(document)
                        cursor.setPosition(self._last_highlighted_start)
                        cursor.setPosition(end_position, QTextCursor.MoveMode.KeepAnchor)
                        
                        # Create default format to clear highlighting
                        default_format = QTextCharFormat()
                        cursor.setCharFormat(default_format)
                    except Exception:
                        # If setting position fails, just reset the stored positions
                        pass
            
            # Reset stored positions after clearing (or if they were invalid)
            self._last_highlighted_start = -1
            self._last_highlighted_length = 0
        
        # Get active move position if available
        # Check bounds: ensure move_info has enough entries and active_move_ply is valid
        if (self._active_move_ply > 0 and 
            len(self._move_info) > 0 and 
            self._active_move_ply <= len(self._move_info)):
            move_pos_index = self._active_move_ply - 1  # Convert ply to 0-based index
            move_san, move_number, is_white = self._move_info[move_pos_index]
            
            # Get highlight colors from config
            ui_config = self.config.get('ui', {})
            panel_config = ui_config.get('panels', {}).get('detail', {})
            pgn_config = panel_config.get('pgn_notation', {})
            formatting = pgn_config.get('formatting', {})
            active_move_config = formatting.get('active_move', {})
            
            # Find the move text in the document by searching sequentially through moves
            # This ensures we find moves in the main line, not in variations/comments
            # Strategy: Search for all moves in order, counting only main-line moves
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            
            found = False
            
            # Build patterns for all moves up to and including the target move
            # This allows us to search sequentially and find the correct position
            search_cursor = QTextCursor(document)
            search_cursor.movePosition(QTextCursor.MoveOperation.Start)
            
            # Search for moves sequentially until we reach the target move
            # Sequential search is always used because it correctly identifies moves by position
            # even when variations/annotations/results are filtered out
            found = False
            
            # Always use sequential search to correctly identify moves by position
            # This ensures we find the correct move even when the same move string appears multiple times
            if True:
                for i in range(move_pos_index + 1):
                    target_move_san, target_move_number, target_is_white = self._move_info[i]
                    
                    # Strip any annotations from move_san (they might be filtered out)
                    move_san_clean = re.sub(r'[!?]{1,2}$', '', target_move_san)
                    
                    if target_is_white:
                        # White move: search for "move_number. move_san"
                        # Note: move_san is already escaped, so special chars like +, # are handled
                        escaped_move = re.escape(move_san_clean)
                        escaped_number = re.escape(str(target_move_number))
                        # Pattern: move_number followed by period, space(s), then move_san (without annotations)
                        # Don't use word boundary for move_san since it might end with + or #
                        # Instead, look for it followed by whitespace, punctuation, or end
                        # Note: Annotations (!, ?) might be filtered out, so allow them as optional
                        # Also allow for variations being removed (no closing parenthesis needed)
                        pattern = rf'\b{escaped_number}\.\s+{escaped_move}(?:[!?]{{1,2}})?(?=\s|$|\.|,|;|</span>|>|<|\))'
                    else:
                        # Black move: search for move_san (but need to find it after the previous white move)
                        escaped_move = re.escape(move_san_clean)
                        # Don't use word boundary for move_san since it might end with + or #
                        # Instead, look for it followed by whitespace, punctuation, or end
                        # Note: Annotations (!, ?) might be filtered out, so allow them as optional
                        # Also allow for variations being removed (no closing parenthesis needed)
                        pattern = rf'\b{escaped_move}(?:[!?]{{1,2}})?(?=\s|$|\.|,|;|</span>|>|<|\))'
                    
                    regex = QRegularExpression(pattern)
                    
                    # Find the next occurrence of this move
                    # For sequential counting, we need to find main-line moves
                    # But for highlighting, we can also highlight variation moves
                    found_cursor = document.find(regex, search_cursor)
                    move_found = False
                    variation_found_cursor = None
                    
                    # Search for moves - prioritize main-line for sequential counting
                    while not found_cursor.isNull():
                        format_at_pos = found_cursor.charFormat()
                        is_italic = format_at_pos.fontItalic()
                        
                        if not is_italic:
                            # Found main-line move
                            move_found = True
                            
                            if i == move_pos_index:
                                # This is the move we're looking for in main line!
                                # For white moves, adjust selection to exclude move number
                                if target_is_white:
                                    cursor = QTextCursor(found_cursor)
                                    match_start = found_cursor.selectionStart()
                                    match_text = found_cursor.selectedText()
                                    move_number_str = str(target_move_number) + "."
                                    move_text_start_in_match = match_text.find(move_number_str)
                                    if move_text_start_in_match >= 0:
                                        move_text_start_in_match += len(move_number_str)
                                        while (move_text_start_in_match < len(match_text) and 
                                               match_text[move_text_start_in_match] in [' ', '\t']):
                                            move_text_start_in_match += 1
                                        cursor.setPosition(match_start + move_text_start_in_match)
                                        cursor.setPosition(found_cursor.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)
                                    else:
                                        cursor = found_cursor
                                else:
                                    cursor = found_cursor
                                found = True
                                break
                            
                            # Update search position to continue after this move
                            search_cursor = QTextCursor(found_cursor)
                            search_cursor.setPosition(found_cursor.selectionEnd())
                            # Skip annotations, spaces, and HTML tags after the move
                            while search_cursor.position() < document.characterCount() - 1:
                                char = document.characterAt(search_cursor.position())
                                if char in ['+', '#', '!', '?']:
                                    search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                                elif char == ' ' or char == '\t' or char == '\n':
                                    search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                                elif char == '<':
                                    # Skip HTML tags
                                    tag_end = search_cursor.position()
                                    while tag_end < document.characterCount() - 1:
                                        if document.characterAt(tag_end) == '>':
                                            search_cursor.setPosition(tag_end + 1)
                                            break
                                        tag_end += 1
                                    if tag_end >= document.characterCount() - 1:
                                        break
                                else:
                                    break
                            break
                        else:
                            # Found move in variation
                            # For sequential counting, we need main-line moves, so continue searching
                            # But store variation move if this is the target move
                            if i == move_pos_index and variation_found_cursor is None:
                                variation_found_cursor = QTextCursor(found_cursor)
                        
                        # Continue searching for main-line move
                        search_cursor = QTextCursor(found_cursor)
                        search_cursor.setPosition(found_cursor.selectionEnd())
                        # Skip annotations, spaces, and HTML tags
                        while search_cursor.position() < document.characterCount() - 1:
                            char = document.characterAt(search_cursor.position())
                            if char in ['+', '#', '!', '?']:
                                search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                            elif char == ' ' or char == '\t' or char == '\n':
                                search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                            elif char == '<':
                                # Skip HTML tags
                                tag_end = search_cursor.position()
                                while tag_end < document.characterCount() - 1:
                                    if document.characterAt(tag_end) == '>':
                                        search_cursor.setPosition(tag_end + 1)
                                        break
                                    tag_end += 1
                                if tag_end >= document.characterCount() - 1:
                                    break
                            else:
                                break
                        found_cursor = document.find(regex, search_cursor)
                    
                    # If we didn't find main-line move but found variation move for target, use that
                    if not found and variation_found_cursor is not None and i == move_pos_index:
                        found_cursor = variation_found_cursor
                        # For white moves, adjust selection to exclude move number
                        if target_is_white:
                            cursor = QTextCursor(found_cursor)
                            match_start = found_cursor.selectionStart()
                            match_text = found_cursor.selectedText()
                            move_number_str = str(target_move_number) + "."
                            move_text_start_in_match = match_text.find(move_number_str)
                            if move_text_start_in_match >= 0:
                                move_text_start_in_match += len(move_number_str)
                                while (move_text_start_in_match < len(match_text) and 
                                       match_text[move_text_start_in_match] in [' ', '\t']):
                                    move_text_start_in_match += 1
                                cursor.setPosition(match_start + move_text_start_in_match)
                                cursor.setPosition(found_cursor.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)
                            else:
                                cursor = found_cursor
                        else:
                            cursor = found_cursor
                        found = True
                    
                    if found:
                        break
                    
                    # If we didn't find the move at all, something is wrong
                    # For sequential counting, we need main-line moves (except for target move which can be variation)
                    if not move_found and (i < move_pos_index or variation_found_cursor is None):
                        # Couldn't find this move - this might happen if filtering changed the structure
                        # When variations are removed, intermediate moves might not be found in order
                        # For intermediate moves (i < move_pos_index), try to continue by moving forward
                        # For the target move (i == move_pos_index), we'll try a direct search as fallback
                        if i < move_pos_index:
                            # This is an intermediate move we couldn't find - skip it and try to continue
                            # Move search cursor forward to try to find the next move
                            if search_cursor.position() < document_length - 1:
                                # Try to advance past potential HTML/whitespace to find next move
                                for _ in range(10):  # Limit advancement to avoid going too far
                                    if search_cursor.position() >= document_length - 1:
                                        break
                                    search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                            else:
                                # Reached end of document
                                break
                        elif i == move_pos_index:
                            # This is the target move we couldn't find - this is a problem
                            # We'll try a direct search as fallback after the loop
                            break
                    
                    # Continue to next move in sequence
                    # search_cursor is already positioned after the found move (or last searched position)
            
            # If we didn't find the target move through sequential search, try direct search as fallback
            # For black moves, we need to count moves sequentially to find the correct occurrence
            if not found and move_pos_index < len(self._move_info):
                target_move_san, target_move_number, target_is_white = self._move_info[move_pos_index]
                
                # Strip any annotations from move_san (they might be filtered out)
                move_san_clean = re.sub(r'[!?]{1,2}$', '', target_move_san)
                
                if target_is_white:
                    # For white moves, use move number to uniquely identify the move
                    escaped_move = re.escape(move_san_clean)
                    escaped_number = re.escape(str(target_move_number))
                    pattern = rf'\b{escaped_number}\.\s+{escaped_move}(?:[!?]{{1,2}})?(?=\s|$|\.|,|;|</span>|>|<|\))'
                    
                    regex = QRegularExpression(pattern)
                    direct_cursor = QTextCursor(document)
                    direct_cursor.movePosition(QTextCursor.MoveOperation.Start)
                    direct_found = document.find(regex, direct_cursor)
                    
                    # Find first non-italic match (main-line move)
                    while not direct_found.isNull():
                        format_at_pos = direct_found.charFormat()
                        is_italic = format_at_pos.fontItalic()
                        if not is_italic:
                            cursor = QTextCursor(direct_found)
                            match_start = direct_found.selectionStart()
                            match_text = direct_found.selectedText()
                            move_number_str = str(target_move_number) + "."
                            move_text_start_in_match = match_text.find(move_number_str)
                            if move_text_start_in_match >= 0:
                                move_text_start_in_match += len(move_number_str)
                                while (move_text_start_in_match < len(match_text) and 
                                       match_text[move_text_start_in_match] in [' ', '\t']):
                                    move_text_start_in_match += 1
                                cursor.setPosition(match_start + move_text_start_in_match)
                                cursor.setPosition(direct_found.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)
                            else:
                                cursor = direct_found
                            found = True
                            break
                        search_pos = QTextCursor(direct_found)
                        search_pos.setPosition(direct_found.selectionEnd())
                        direct_found = document.find(regex, search_pos)
                else:
                    # For black moves, we need to count moves sequentially to find the correct occurrence
                    # Count how many times this move string appears before the target move
                    # We need to find the nth occurrence where n is determined by counting moves sequentially
                    escaped_move = re.escape(move_san_clean)
                    pattern = rf'\b{escaped_move}(?:[!?]{{1,2}})?(?=\s|$|\.|,|;|</span>|>|<|\))'
                    
                    regex = QRegularExpression(pattern)
                    direct_cursor = QTextCursor(document)
                    direct_cursor.movePosition(QTextCursor.MoveOperation.Start)
                    direct_found = document.find(regex, direct_cursor)
                    
                    # Count moves sequentially to find the correct occurrence
                    # We need to count how many times this move string appears before the target move
                    # Count all previous moves (both white and black) that match the target move string
                    occurrences_to_skip = 0
                    for i in range(move_pos_index):
                        prev_move_san, prev_move_number, prev_is_white = self._move_info[i]
                        # Count all moves (both white and black) that match the target move string
                        # We need to strip annotations for comparison
                        prev_move_clean = re.sub(r'[!?]{1,2}$', '', prev_move_san)
                        if prev_move_clean == move_san_clean:
                            # This is a previous occurrence of the same move string
                            occurrences_to_skip += 1
                    
                    # Find all matches and select the (occurrences_to_skip + 1)th non-italic match
                    matches_found = []
                    while not direct_found.isNull():
                        format_at_pos = direct_found.charFormat()
                        is_italic = format_at_pos.fontItalic()
                        if not is_italic:
                            matches_found.append(direct_found)
                        search_pos = QTextCursor(direct_found)
                        search_pos.setPosition(direct_found.selectionEnd())
                        direct_found = document.find(regex, search_pos)
                    
                    # Select the correct occurrence (occurrences_to_skip + 1)th match
                    if occurrences_to_skip < len(matches_found):
                        match_cursor = matches_found[occurrences_to_skip]
                        cursor = match_cursor
                        found = True
            
            if found:
                # Found the move - select it
                move_start = cursor.selectionStart()
                move_end = cursor.selectionEnd()
                
                # Validate positions are within document bounds
                if move_start >= 0 and move_end >= move_start and move_end <= document_length:
                    # Use main line move highlight styling from config
                    # Note: The active move is always a main-line move (users can only navigate to main-line moves).
                    # The move is already formatted with main line styling by the formatter service.
                    # We just add the highlight on top.
                    bg_color = active_move_config.get('background_color', [100, 120, 180])
                    text_color = active_move_config.get('text_color', [255, 255, 255])
                    bold = active_move_config.get('bold', True)
                    italic = False
                    
                    # Create highlight format
                    highlight_format = QTextCharFormat()
                    highlight_format.setBackground(QColor(bg_color[0], bg_color[1], bg_color[2]))
                    highlight_format.setForeground(QColor(text_color[0], text_color[1], text_color[2]))
                    if bold:
                        highlight_format.setFontWeight(QFont.Weight.Bold)
                    if italic:
                        highlight_format.setFontItalic(True)
                    
                    # Apply formatting
                    cursor.setCharFormat(highlight_format)
                    
                    # Scroll to the highlighted move
                    self.pgn_text.setTextCursor(cursor)
                    self.pgn_text.ensureCursorVisible()
                    
                    # Store for clearing next time (only if valid)
                    self._last_highlighted_start = move_start
                    self._last_highlighted_length = move_end - move_start
    
    def get_pgn_text(self) -> str:
        """Get the current PGN text content.
        
        Returns:
            Current PGN text content.
        """
        return self._current_pgn_text if self._current_pgn_text else self.pgn_text.toPlainText()
    
    def _handle_pgn_click(self, click_pos: int) -> int:
        """Handle click on PGN text at given position.
        
        Args:
            click_pos: Document character position where click occurred.
            
        Returns:
            Ply index if main-line move found, 0 otherwise.
        """
        # Find which main-line move (if any) contains this position
        ply_index = self._find_mainline_move_at_position(click_pos)
        
        if ply_index > 0 and self._game_controller:
            # Navigate to this ply
            self._game_controller.navigate_to_ply(ply_index)
        
        return ply_index
    
    def _find_mainline_move_at_position(self, position: int) -> int:
        """Find ply index of main-line move at given document position.
        
        Only returns ply index for main-line moves, not variation moves.
        Returns 0 if no main-line move found at position.
        
        Args:
            position: Document character position.
            
        Returns:
            Ply index (1-based) if main-line move found, 0 otherwise.
        """
        # Ensure document is ready
        if not self.pgn_text.document():
            return 0
        
        document = self.pgn_text.document()
        document_length = document.characterCount()
        
        # If document is empty or position is out of bounds, nothing to find
        if document_length == 0 or position < 0 or position >= document_length:
            return 0
        
        # If no move info available, can't find move
        if not self._move_info:
            return 0
        
        # Search through all moves sequentially to find which one contains the click position
        # We need to find main-line moves only (not variations)
        search_cursor = QTextCursor(document)
        search_cursor.movePosition(QTextCursor.MoveOperation.Start)
        
        # Iterate through moves in order
        for move_pos_index in range(len(self._move_info)):
            move_san, move_number, is_white = self._move_info[move_pos_index]
            
            # Strip any annotations from move_san (they might be filtered out)
            move_san_clean = re.sub(r'[!?]{1,2}$', '', move_san)
            
            # Build regex pattern for this move
            if is_white:
                # White move: search for "move_number. move_san"
                escaped_move = re.escape(move_san_clean)
                escaped_number = re.escape(str(move_number))
                pattern = rf'\b{escaped_number}\.\s+{escaped_move}(?:[!?]{{1,2}})?(?=\s|$|\.|,|;|</span>|>|<|\))'
            else:
                # Black move: search for move_san
                escaped_move = re.escape(move_san_clean)
                pattern = rf'\b{escaped_move}(?:[!?]{{1,2}})?(?=\s|$|\.|,|;|</span>|>|<|\))'
            
            regex = QRegularExpression(pattern)
            
            # Find all occurrences of this move, but only consider main-line moves
            found_cursor = document.find(regex, search_cursor)
            mainline_move_found = False
            
            while not found_cursor.isNull():
                # Check if this is a main-line move (not italic = not in variation)
                format_at_pos = found_cursor.charFormat()
                is_italic = format_at_pos.fontItalic()
                
                if not is_italic:
                    # Found main-line move - check if click position is within this move
                    move_start = found_cursor.selectionStart()
                    move_end = found_cursor.selectionEnd()
                    
                    # For white moves, the match might include the move number
                    # We want to check if position is within the actual move text
                    if is_white:
                        # Adjust start position to exclude move number
                        match_text = found_cursor.selectedText()
                        move_number_str = str(move_number) + "."
                        move_text_start_in_match = match_text.find(move_number_str)
                        if move_text_start_in_match >= 0:
                            move_text_start_in_match += len(move_number_str)
                            # Skip whitespace after move number
                            while (move_text_start_in_match < len(match_text) and 
                                   match_text[move_text_start_in_match] in [' ', '\t']):
                                move_text_start_in_match += 1
                            move_start = found_cursor.selectionStart() + move_text_start_in_match
                    
                    # Check if click position is within this move's text range
                    if move_start <= position <= move_end:
                        # Found the move! Return ply index (1-based)
                        ply_index = move_pos_index + 1
                        return ply_index
                    
                    # Update search position to continue after this move
                    search_cursor = QTextCursor(found_cursor)
                    search_cursor.setPosition(found_cursor.selectionEnd())
                    # Skip annotations, spaces, and HTML tags after the move
                    while search_cursor.position() < document_length - 1:
                        char = document.characterAt(search_cursor.position())
                        if char in ['+', '#', '!', '?']:
                            search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                        elif char == ' ' or char == '\t' or char == '\n':
                            search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                        elif char == '<':
                            # Skip HTML tags
                            tag_end = search_cursor.position()
                            while tag_end < document_length - 1:
                                if document.characterAt(tag_end) == '>':
                                    search_cursor.setPosition(tag_end + 1)
                                    break
                                tag_end += 1
                            if tag_end >= document_length - 1:
                                break
                        else:
                            break
                    mainline_move_found = True
                    break  # Found main-line move, move to next move in sequence
                
                # This is a variation move, continue searching for main-line move
                # Advance search position past this variation move
                search_pos = QTextCursor(found_cursor)
                search_pos.setPosition(found_cursor.selectionEnd())
                # Skip annotations, spaces, and HTML tags
                while search_pos.position() < document_length - 1:
                    char = document.characterAt(search_pos.position())
                    if char in ['+', '#', '!', '?']:
                        search_pos.movePosition(QTextCursor.MoveOperation.NextCharacter)
                    elif char == ' ' or char == '\t' or char == '\n':
                        search_pos.movePosition(QTextCursor.MoveOperation.NextCharacter)
                    elif char == '<':
                        # Skip HTML tags
                        tag_end = search_pos.position()
                        while tag_end < document_length - 1:
                            if document.characterAt(tag_end) == '>':
                                search_pos.setPosition(tag_end + 1)
                                break
                            tag_end += 1
                        if tag_end >= document_length - 1:
                            break
                    else:
                        break
                found_cursor = document.find(regex, search_pos)
            
            # If we didn't find a main-line move for this move_pos_index,
            # we need to advance the search cursor to avoid getting stuck
            if not mainline_move_found:
                # Couldn't find this move - advance search cursor
                if search_cursor.position() < document_length - 1:
                    # Try to advance past potential HTML/whitespace to find next move
                    for _ in range(10):  # Limit advancement to avoid going too far
                        if search_cursor.position() >= document_length - 1:
                            break
                        search_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        
        # No main-line move found at this position
        return 0

"""AI Summary/Chat view for detail panel."""

import html
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QLabel, QComboBox, QSpinBox,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QPalette, QColor
from typing import Dict, Any, Optional, List

from app.models.game_model import GameModel
from app.controllers.ai_chat_controller import AIChatController
from app.utils.font_utils import resolve_font_family, scale_font_size


class DetailAIChatView(QWidget):
    """AI Summary/Chat view for analyzing chess positions."""
    
    def __init__(self, config: Dict[str, Any],
                 game_model: Optional[GameModel] = None,
                 ai_chat_controller: Optional[AIChatController] = None) -> None:
        """Initialize the AI chat view.
        
        Args:
            config: Configuration dictionary.
            game_model: Optional GameModel to observe for position changes.
            ai_chat_controller: Optional AIChatController for business logic.
        """
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._ai_chat_controller: Optional[AIChatController] = None
        
        # Load config
        self._load_config()
        
        # Setup UI
        self._setup_ui()
        
        # Connect to game model if provided
        if game_model:
            self.set_game_model(game_model)
        
        # Connect to controller if provided
        if ai_chat_controller:
            self.set_ai_chat_controller(ai_chat_controller)
    
    def _load_config(self) -> None:
        """Load configuration values from config dictionary."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        self.chat_config = panel_config.get('ai_chat', {})
        
        # Get styling
        self.background_color = self.chat_config.get('background_color', [40, 40, 45])
        self.text_color = self.chat_config.get('text_color', [200, 200, 200])
        self.font_family = resolve_font_family(self.chat_config.get('font_family', 'Helvetica Neue'))
        self.font_size = scale_font_size(self.chat_config.get('font_size', 11))
        
        separator_config = self.chat_config.get('separator', {})
        default_separator_color = self.chat_config.get('messages', {}).get('system', {}).get('text_color', self.text_color)
        self.separator_line_color = separator_config.get('line_color', default_separator_color)
        self.separator_text_color = separator_config.get('text_color', default_separator_color)
        base_separator_size = separator_config.get('font_size', self.chat_config.get('font_size', 11) - 1)
        self.separator_font_size = scale_font_size(base_separator_size if base_separator_size > 0 else self.font_size)
        
        # Get input config
        input_config = self.chat_config.get('input', {})
        self.input_height = input_config.get('height', 30)
        self.input_padding = input_config.get('padding', 5)
        self.input_bg_color = input_config.get('background_color', [45, 45, 50])
        self.input_text_color = input_config.get('text_color', [200, 200, 200])
        self.input_border_color = input_config.get('border_color', [60, 60, 65])
        self.input_focus_border_color = input_config.get('focus_border_color', [0, 120, 212])
        self.input_border_radius = input_config.get('border_radius', 3)
        self.input_border_width = input_config.get('border_width', 1)
        
        # Get button config
        button_config = self.chat_config.get('button', {})
        self.button_width = button_config.get('width', 80)
        self.button_height = button_config.get('height', 30)
        
        # Control configs
        self.tokens_config = self.chat_config.get('tokens', {})
        self.tokens_collapse_threshold = self.tokens_config.get('collapse_width_threshold', 520)
        self.tokens_animation_duration = self.tokens_config.get('collapse_animation_duration_ms', 200)
        
        # Tokens visibility state
        self._tokens_full_width = 0
        self._tokens_visible = True
        self._tokens_target_visible = True
        self._tokens_visibility_pending = False
        self.tokens_animation = None
        self.tokens_width_animation = None
        self.tokens_opacity_animation = None
        
        # Typing indicator state
        message_config = self.chat_config.get('messages', {})
        typing_config = message_config.get('typing_indicator', {})
        self._typing_indicator_opacity = typing_config.get('opacity', 0.6)
        self._typing_indicator_interval = typing_config.get('animation_interval_ms', 500)
        self._typing_indicator_widget: Optional[QWidget] = None
        self._typing_indicator_label: Optional[QLabel] = None
        self._typing_indicator_timer: Optional[QTimer] = None
        self._typing_indicator_dot_state = 0
    
    def _setup_ui(self) -> None:
        """Setup the AI chat UI."""
        layout = QVBoxLayout(self)
        ui_config = self.config.get('ui', {})
        margins = ui_config.get('margins', {}).get('detail_panel', [0, 0, 0, 0])
        layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        layout.setSpacing(0)
        
        # Set background color
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(*self.background_color))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Chat messages area (scrollable)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Messages container
        self.messages_widget = QWidget()
        self.messages_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(10, 10, 10, 10)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()  # Push messages to top
        
        self.scroll_area.setWidget(self.messages_widget)
        layout.addWidget(self.scroll_area)
        
        # Input area (bottom)
        input_frame = QFrame()
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(8)
        
        # Model selection row frame
        self.model_row_frame = QWidget()
        self.model_layout = QHBoxLayout(self.model_row_frame)
        self.model_layout.setContentsMargins(0, 0, 0, 0)
        self.model_label = QLabel("Model:")
        self.model_layout.addWidget(self.model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        tokens_config = self.tokens_config
        control_height = tokens_config.get('height', self.button_height)
        combo_min_width = 200  # View-specific minimum width
        self.model_combo.setFixedHeight(control_height)
        self.model_combo.setMinimumWidth(combo_min_width)
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.model_layout.addWidget(self.model_combo)
        
        # Token limit spinbox
        self.tokens_container = QWidget()
        tokens_layout = QHBoxLayout(self.tokens_container)
        tokens_layout.setContentsMargins(0, 0, 0, 0)
        tokens_layout.setSpacing(6)
        self.tokens_label = QLabel("Tokens:")
        tokens_layout.addWidget(self.tokens_label)
        
        self.tokens_spin = QSpinBox()
        self.tokens_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.tokens_spin.setRange(
            tokens_config.get('minimum', 256),
            tokens_config.get('maximum', 16000)
        )
        self.tokens_spin.setSingleStep(tokens_config.get('step', 100))
        self.tokens_spin.setValue(tokens_config.get('default', 2000))
        self.tokens_spin.setFixedWidth(tokens_config.get('width', 120))
        self.tokens_spin.setFixedHeight(control_height)
        tokens_layout.addWidget(self.tokens_spin)
        self.tokens_container.setMaximumWidth(self.tokens_spin.width())
        self.tokens_opacity_effect = QGraphicsOpacityEffect(self.tokens_container)
        self.tokens_opacity_effect.setOpacity(1.0)
        self.tokens_container.setGraphicsEffect(self.tokens_opacity_effect)
        self.model_layout.addWidget(self.tokens_container)
        self.model_layout.addStretch()
        
        input_layout.addWidget(self.model_row_frame)
        
        self._setup_tokens_animation()
        self.model_row_frame.installEventFilter(self)
        QTimer.singleShot(0, self._capture_tokens_full_width)
        QTimer.singleShot(0, self._update_tokens_visibility)
        
        # Input row
        input_row_layout = QHBoxLayout()
        input_row_layout.setSpacing(10)
        
        # Text input
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask about the position...")
        self.input_field.returnPressed.connect(self._on_send_clicked)
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        input_row_layout.addWidget(self.input_field, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Send button
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)
        self.send_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        input_row_layout.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        input_layout.addLayout(input_row_layout)
        
        layout.addWidget(input_frame)
        
        # Apply styling
        self._apply_styling()
    
    def _apply_styling(self) -> None:
        """Apply styling to chat components."""
        # Apply scrollbar styling to scroll area using StyleManager
        from app.views.style import StyleManager
        # Use background color for scrollbar background, and a slightly lighter color for border
        border_color = [min(255, self.background_color[0] + 20), 
                       min(255, self.background_color[1] + 20), 
                       min(255, self.background_color[2] + 20)]
        StyleManager.style_scroll_area(
            self.scroll_area,
            self.config,
            self.background_color,
            border_color,
            0  # No border radius for this scroll area
        )
        
        # Messages area styling
        messages_style = f"""
            QWidget {{
                background-color: rgb({self.background_color[0]}, {self.background_color[1]}, {self.background_color[2]});
                color: rgb({self.text_color[0]}, {self.text_color[1]}, {self.text_color[2]});
            }}
        """
        self.messages_widget.setStyleSheet(messages_style)
        
        # Input field styling
        input_config = self.chat_config.get('input', {})
        input_bg = input_config.get('background_color', [45, 45, 50])
        input_text = input_config.get('text_color', [200, 200, 200])
        input_border = input_config.get('border_color', [60, 60, 65])
        input_focus = input_config.get('focus_border_color', [0, 120, 212])
        border_radius = input_config.get('border_radius', 3)
        border_width = input_config.get('border_width', 1)
        
        # Apply unified line edit styling using StyleManager
        from app.views.style import StyleManager
        
        # Resolve font family (font_size is already scaled in _load_config, don't scale again)
        resolved_font_family = resolve_font_family(self.font_family)
        
        # Convert padding from single value to [horizontal, vertical] format
        if isinstance(self.input_padding, (int, float)):
            input_padding = [self.input_padding, self.input_padding]
        elif isinstance(self.input_padding, list) and len(self.input_padding) == 1:
            input_padding = [self.input_padding[0], self.input_padding[0]]
        elif isinstance(self.input_padding, list) and len(self.input_padding) >= 2:
            input_padding = [self.input_padding[0], self.input_padding[1]]
        else:
            input_padding = [5, 5]  # Default fallback
        
        # Apply styling
        StyleManager.style_line_edits(
            [self.input_field],
            self.config,
            font_family=resolved_font_family,  # Match original view font
            font_size=self.font_size,  # Already scaled in _load_config, don't scale again
            bg_color=input_bg,  # Match view background color
            border_color=input_border,  # Match view border color
            focus_border_color=input_focus,  # Match view focus border color
            border_width=border_width,  # Match view border width
            border_radius=border_radius,  # Match view border radius
            padding=input_padding  # Preserve existing padding
        )
        
        # Apply button styling using StyleManager
        button_config = self.chat_config.get('button', {})
        button_bg_offset = button_config.get('background_offset', 20)
        button_hover_offset = button_config.get('hover_background_offset', 30)
        button_pressed_offset = button_config.get('pressed_background_offset', 10)
        border_color = button_config.get('border_color', [60, 60, 65])
        
        bg_color_list = [self.background_color[0], self.background_color[1], self.background_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        # Use same padding as input field to ensure vertical alignment
        StyleManager.style_buttons(
            [self.send_button],
            self.config,
            bg_color_list,
            border_color_list,
            background_offset=button_bg_offset,
            hover_background_offset=button_hover_offset,
            pressed_background_offset=button_pressed_offset,
            padding=self.input_padding,  # Match input field padding
            min_width=self.button_width,
            min_height=self.button_height
        )
        
        # Set fixed height on both widgets to ensure they match exactly
        # This must be done after styling to override any stylesheet height constraints
        self.input_field.setFixedHeight(self.button_height)
        self.input_field.setMinimumHeight(self.button_height)
        self.input_field.setMaximumHeight(self.button_height)
        
        self.send_button.setFixedHeight(self.button_height)
        self.send_button.setMinimumHeight(self.button_height)
        self.send_button.setMaximumHeight(self.button_height)
        
        # Also add height constraints to stylesheet to ensure they're enforced
        # This ensures the height is maintained even if stylesheet is reapplied
        input_stylesheet = self.input_field.styleSheet()
        if 'height:' not in input_stylesheet and 'min-height:' not in input_stylesheet:
            input_stylesheet = input_stylesheet.replace(
                "QLineEdit {",
                f"QLineEdit {{\nmin-height: {self.button_height}px;\nmax-height: {self.button_height}px;"
            )
            self.input_field.setStyleSheet(input_stylesheet)
        
        # Apply combobox styling using StyleManager
        # StyleManager reads combobox-specific settings (like padding) from centralized config automatically
        # Selection colors - use focus color for selection background (matching other dialogs)
        selection_bg = self.input_focus_border_color
        selection_text = [240, 240, 240]
        
        from app.views.style import StyleManager
        StyleManager.style_comboboxes(
            [self.model_combo],
            self.config,
            self.input_text_color,
            self.font_family,
            self.font_size,
            self.input_bg_color,
            self.input_border_color,
            self.input_focus_border_color,
            selection_bg,
            selection_text,
            border_width=self.input_border_width,
            border_radius=self.input_border_radius,
            editable=False
        )
        
        tokens_config = self.tokens_config
        token_bg = tokens_config.get('background_color', self.input_bg_color)
        token_text = tokens_config.get('text_color', self.text_color)
        token_border = tokens_config.get('border_color', self.input_border_color)
        token_border_width = tokens_config.get('border_width', self.input_border_width)
        token_border_radius = tokens_config.get('border_radius', self.input_border_radius)
        token_focus = tokens_config.get('focus_border_color', self.input_focus_border_color)
        token_padding = tokens_config.get('padding', [6, 8])
        token_font_family = tokens_config.get('font_family', self.font_family)
        token_font_size = scale_font_size(tokens_config.get('font_size', self.chat_config.get('font_size', 11)))
        
        spin_style = f"""
            QSpinBox {{
                background-color: rgb({token_bg[0]}, {token_bg[1]}, {token_bg[2]});
                color: rgb({token_text[0]}, {token_text[1]}, {token_text[2]});
                border: {token_border_width}px solid rgb({token_border[0]}, {token_border[1]}, {token_border[2]});
                border-radius: {token_border_radius}px;
                padding-left: {token_padding[0]}px;
                padding-right: {token_padding[1]}px;
                font-family: "{token_font_family}";
                font-size: {token_font_size}pt;
            }}
            QSpinBox:focus {{
                border-color: rgb({token_focus[0]}, {token_focus[1]}, {token_focus[2]});
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                height: 0px;
            }}
        """
        self.tokens_spin.setStyleSheet(spin_style)
        
        # Label styling
        label_style = f"""
            QLabel {{
                color: rgb({self.text_color[0]}, {self.text_color[1]}, {self.text_color[2]});
                font-family: "{self.font_family}";
                font-size: {self.font_size}pt;
            }}
        """
        self.model_label.setStyleSheet(label_style)
        self.tokens_label.setStyleSheet(label_style)
    
    def _setup_tokens_animation(self) -> None:
        if not hasattr(self, 'tokens_container'):
            return
        self.tokens_width_animation = QPropertyAnimation(self.tokens_container, b"maximumWidth", self)
        self.tokens_width_animation.setDuration(self.tokens_animation_duration)
        self.tokens_width_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.tokens_opacity_animation = QPropertyAnimation(self.tokens_opacity_effect, b"opacity", self)
        self.tokens_opacity_animation.setDuration(self.tokens_animation_duration)
        self.tokens_opacity_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.tokens_animation = QParallelAnimationGroup(self)
        self.tokens_animation.addAnimation(self.tokens_width_animation)
        self.tokens_animation.addAnimation(self.tokens_opacity_animation)
        self.tokens_animation.finished.connect(self._on_tokens_animation_finished)
    
    def _capture_tokens_full_width(self) -> None:
        if not hasattr(self, 'tokens_container'):
            return
        width = self.tokens_container.sizeHint().width()
        if width <= 0:
            return
        self._tokens_full_width = width
        if self._tokens_visible:
            self.tokens_container.setMaximumWidth(width)
        else:
            self.tokens_container.setMaximumWidth(0)
    
    def _update_tokens_visibility(self) -> None:
        if not hasattr(self, 'model_row_frame'):
            return
        available_width = self.model_row_frame.width()
        should_show = available_width >= self.tokens_collapse_threshold
        self._set_tokens_visible(should_show)
    
    def _set_tokens_visible(self, visible: bool) -> None:
        if not self.tokens_animation:
            self.tokens_container.setVisible(visible)
            self._tokens_visible = visible
            self._update_model_combo_expansion(visible)
            return
        
        if self._tokens_visible == visible and not self._tokens_visibility_pending:
            return
        
        self._tokens_target_visible = visible
        self._tokens_visibility_pending = True
        
        self.tokens_animation.stop()
        
        if visible:
            self.tokens_container.setVisible(True)
            if self._tokens_full_width <= 0:
                self._tokens_full_width = max(0, self.tokens_container.sizeHint().width())
        
        current_width = self.tokens_container.maximumWidth()
        end_width = self._tokens_full_width if visible else 0
        if end_width <= 0 and visible:
            end_width = max(0, self.tokens_container.sizeHint().width())
        
        self.tokens_width_animation.setStartValue(max(0, current_width))
        self.tokens_width_animation.setEndValue(max(0, end_width))
        
        current_opacity = self.tokens_opacity_effect.opacity()
        self.tokens_opacity_animation.setStartValue(current_opacity)
        self.tokens_opacity_animation.setEndValue(1.0 if visible else 0.0)
        
        # Update model combo expansion state
        self._update_model_combo_expansion(visible)
        
        self.tokens_animation.start()
    
    def _on_tokens_animation_finished(self) -> None:
        self._tokens_visible = self._tokens_target_visible
        self._tokens_visibility_pending = False
        
        if not self._tokens_visible:
            self.tokens_container.setVisible(False)
            self.tokens_container.setMaximumWidth(0)
            self.tokens_opacity_effect.setOpacity(0.0)
        else:
            target_width = self._tokens_full_width or self.tokens_container.sizeHint().width()
            self.tokens_container.setMaximumWidth(max(0, target_width))
            self.tokens_opacity_effect.setOpacity(1.0)
        
        # Ensure model combo expansion state is correct after animation
        self._update_model_combo_expansion(self._tokens_visible)
    
    def _update_model_combo_expansion(self, tokens_visible: bool) -> None:
        """Update model combo to expand when tokens are hidden, or use minimum width when visible."""
        if not hasattr(self, 'model_combo') or not hasattr(self, 'model_layout'):
            return
        
        # Check if stretch exists by looking at the last item
        has_stretch = False
        if self.model_layout.count() > 0:
            last_item = self.model_layout.itemAt(self.model_layout.count() - 1)
            if last_item and last_item.spacerItem() is not None:
                has_stretch = True
        
        if tokens_visible:
            # Restore stretch and use minimum width for combo
            if not has_stretch:
                self.model_layout.addStretch()
            self.model_combo.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        else:
            # Remove stretch and make combo expand
            if has_stretch:
                stretch_item = self.model_layout.takeAt(self.model_layout.count() - 1)
                if stretch_item:
                    del stretch_item
            self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def _show_placeholder(self) -> None:
        """Show placeholder message when no conversation exists."""
        # Don't show placeholder - let the empty chat area speak for itself
        pass
    
    def _format_message_text(self, content: str, role: str) -> str:
        """Format message text with markdown-style bold for AI messages.
        
        Args:
            content: Raw message content.
            role: Message role ("user", "ai", or "system").
            
        Returns:
            Formatted text (HTML for AI messages with bold/linking, plain text for others).
        """
        if role != "ai":
            return content
        
        def _escape_segment(segment: str) -> str:
            return html.escape(segment).replace('\n', '<br>')
        
        link_pattern = re.compile(r'\[\%([^\]]+)\]')
        parts: List[str] = []
        last_index = 0
        ai_config = self.chat_config.get('messages', {}).get('ai', {})
        link_color = ai_config.get('link_color', ai_config.get('text_color', [200, 200, 200]))
        link_color_css = f"rgb({link_color[0]}, {link_color[1]}, {link_color[2]})"
        
        for match in link_pattern.finditer(content):
            segment = content[last_index:match.start()]
            if segment:
                parts.append(_escape_segment(segment))
            move_notation = match.group(1).strip()
            if move_notation:
                safe_move = html.escape(move_notation)
                parts.append(
                    f'<a href="move:{safe_move}" style="color: {link_color_css}; text-decoration: underline;">{safe_move}</a>'
                )
            last_index = match.end()
        
        remaining = content[last_index:]
        if remaining:
            parts.append(_escape_segment(remaining))
        
        formatted = ''.join(parts)
        formatted = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', formatted)
        return formatted
    
    def _add_message(self, role: str, content: str) -> None:
        """Add a message to the chat display.
        
        Args:
            role: Message role ("user", "ai", or "system").
            content: Message content.
        """
        if role == "separator":
            self._add_move_separator(content)
            return
        
        # Style based on role - determine alignment first
        message_config = self.chat_config.get('messages', {})
        user_config = message_config.get('user', {})
        ai_config = message_config.get('ai', {})
        system_config = message_config.get('system', {})
        
        if role == "user":
            bg_color = user_config.get('background_color', [60, 80, 120])
            text_color = user_config.get('text_color', [240, 240, 240])
            align = Qt.AlignmentFlag.AlignRight
        elif role == "ai":
            bg_color = ai_config.get('background_color', [50, 50, 55])
            text_color = ai_config.get('text_color', [200, 200, 200])
            align = Qt.AlignmentFlag.AlignLeft
        else:  # system
            bg_color = system_config.get('background_color', [45, 45, 50])
            text_color = system_config.get('text_color', [150, 150, 150])
            align = Qt.AlignmentFlag.AlignCenter
        
        # Format message text (convert markdown bold for AI messages)
        formatted_content = self._format_message_text(content, role)
        
        # Create message label
        message_label = QLabel(formatted_content)
        message_label.setWordWrap(True)
        
        # Enable RichText format for AI messages (to render bold HTML)
        if role == "ai":
            message_label.setTextFormat(Qt.TextFormat.RichText)
        
        message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        # Set size policy to allow label to expand and wrap text properly
        message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # Set maximum width to use full available space (scroll area width minus margins)
        # This ensures text wraps properly while using maximum available space
        if self.scroll_area and self.scroll_area.width() > 0:
            # Use full width minus margins (10px on each side = 20px total)
            max_width = self.scroll_area.width() - 20
            if max_width > 100:
                message_label.setMaximumWidth(max_width)
        else:
            # Default to a large width if scroll area not yet sized (will be updated on resize)
            message_label.setMaximumWidth(1000)
        
        padding = message_config.get('padding', 10)
        border_radius = message_config.get('border_radius', 5)
        margin = message_config.get('margin', 5)
        
        message_style = f"""
            QLabel {{
                background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
                color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
                padding: {padding}px;
                border-radius: {border_radius}px;
                font-family: "{self.font_family}";
                font-size: {self.font_size}pt;
                margin: {margin}px;
            }}
        """
        message_label.setStyleSheet(message_style)
        
        # Create a horizontal layout for each message to control expansion
        message_row = QWidget()
        message_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout = QHBoxLayout(message_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        
        # Add message label with proper alignment and expansion
        if align == Qt.AlignmentFlag.AlignRight:
            # User messages: stretch before, label expands to use full width
            row_layout.addStretch()
            row_layout.addWidget(message_label, 1)  # Stretch factor 1 to expand
        elif align == Qt.AlignmentFlag.AlignLeft:
            # AI messages: label expands to use full width, no stretch after
            row_layout.addWidget(message_label, 1)  # Stretch factor 1 to expand
        else:  # Center
            row_layout.addStretch()
            row_layout.addWidget(message_label, 1)
            row_layout.addStretch()
        
        if role == "ai":
            message_label.setOpenExternalLinks(False)
            message_label.linkActivated.connect(self._on_ai_move_link_activated)
        
        # Add message row to messages layout
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, message_row)
        
        # Update message width after widget is added (scroll area might not be sized yet)
        QTimer.singleShot(100, lambda: self._update_single_message_width(message_label))
        
        # Scroll to bottom
        QTimer.singleShot(50, self._scroll_to_bottom)
    
    def _add_move_separator(self, label: str) -> None:
        """Insert a visual separator describing the current move."""
        separator_widget = QWidget()
        separator_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(separator_widget)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(10)
        
        line_color = self.separator_line_color or self.text_color
        line_style = (
            f"background-color: rgb({line_color[0]}, {line_color[1]}, {line_color[2]});"
            "border: none;"
        )
        
        def _create_line() -> QFrame:
            line = QFrame()
            line.setFixedHeight(1)
            line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            line.setStyleSheet(line_style)
            return line
        
        left_line = _create_line()
        right_line = _create_line()
        
        label_widget = QLabel(label)
        label_widget.setStyleSheet(
            f"color: rgb({self.separator_text_color[0]}, {self.separator_text_color[1]}, {self.separator_text_color[2]});"
            f"font-family: \"{self.font_family}\";"
            f"font-size: {self.separator_font_size}pt;"
            "font-weight: 600;"
        )
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        layout.addWidget(left_line)
        layout.addWidget(label_widget)
        layout.addWidget(right_line)
        
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, separator_widget)
        QTimer.singleShot(50, self._scroll_to_bottom)
    
    def _scroll_to_bottom(self) -> None:
        """Scroll chat to bottom."""
        if self.scroll_area:
            scroll_bar = self.scroll_area.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.maximum())
    
    def _clear_messages(self) -> None:
        """Clear all messages from the chat."""
        # Remove all widgets except the stretch
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _on_send_clicked(self) -> None:
        """Handle send button click."""
        if not self._ai_chat_controller:
            return
        
        text = self.input_field.text().strip()
        if not text:
            return
        
        # Clear input
        self.input_field.clear()
        
        # Delegate to controller
        success = self._ai_chat_controller.send_message(text)
        if not success:
            # Controller will emit error signal, but we can also disable input if request in progress
            if self._ai_chat_controller.is_request_in_progress():
                self._set_input_enabled(False)
    
    def _set_input_enabled(self, enabled: bool) -> None:
        """Enable or disable input controls.
        
        Args:
            enabled: True to enable, False to disable.
        """
        self.send_button.setEnabled(enabled)
        self.input_field.setEnabled(enabled)
        
        # Restore focus to input field when re-enabled
        if enabled:
            self.input_field.setFocus()
    
    def set_game_model(self, game_model: GameModel) -> None:
        """Set the game model to observe for position changes.
        
        Args:
            game_model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
        
        self._game_model = game_model
        
        # Connect to model signals
        game_model.active_move_changed.connect(self._on_active_move_changed)
        game_model.active_game_changed.connect(self._on_active_game_changed)
        
        # Initialize with current state
        self._on_active_move_changed(game_model.get_active_move_ply())
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from model.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        # Controller handles position change logic
        # This is just for UI updates if needed
        pass
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change from model.
        
        Args:
            game: GameData instance or None.
        """
        # Controller handles game change logic
        # This is just for UI updates if needed
        pass
    
    def set_ai_chat_controller(self, controller: AIChatController) -> None:
        """Set the AI chat controller for business logic.
        
        Args:
            controller: AIChatController instance.
        """
        if self._ai_chat_controller is controller:
            return
        
        if self._ai_chat_controller:
            # Disconnect from old controller
            self._ai_chat_controller.message_added.disconnect(self._on_message_added)
            self._ai_chat_controller.conversation_cleared.disconnect(self._on_conversation_cleared)
            self._ai_chat_controller.error_occurred.disconnect(self._on_error_occurred)
            self._ai_chat_controller.request_started.disconnect(self._on_request_started)
            self._ai_chat_controller.request_completed.disconnect(self._on_request_completed)
            try:
                self.model_combo.currentTextChanged.disconnect(self._on_model_changed)
            except (TypeError, RuntimeError):
                pass
            try:
                self.tokens_spin.valueChanged.disconnect(self._on_tokens_changed)
            except (TypeError, RuntimeError):
                pass
        
        self._ai_chat_controller = controller
        
        # Connect to controller signals
        controller.message_added.connect(self._on_message_added)
        controller.conversation_cleared.connect(self._on_conversation_cleared)
        controller.error_occurred.connect(self._on_error_occurred)
        controller.request_started.connect(self._on_request_started)
        controller.request_completed.connect(self._on_request_completed)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        self.tokens_spin.valueChanged.connect(self._on_tokens_changed)
        self._on_tokens_changed(self.tokens_spin.value())
        
        # Populate model dropdown
        self._populate_models()
        
        # Install event filter to update message widths when scroll area is resized
        self.scroll_area.installEventFilter(self)
    
    def _on_message_added(self, role: str, content: str) -> None:
        """Handle message added from controller.
        
        Args:
            role: Message role ("user", "ai", or "system").
            content: Message content.
        """
        # Hide typing indicator when any message is added (especially AI responses)
        self._hide_typing_indicator()
        self._add_message(role, content)
    
    def _on_conversation_cleared(self) -> None:
        """Handle conversation cleared from controller."""
        self._hide_typing_indicator()
        self._clear_messages()
        # Don't show placeholder - empty chat area is fine
    
    def _on_error_occurred(self, error_message: str) -> None:
        """Handle error from controller.
        
        Args:
            error_message: Error message to display.
        """
        self._add_message("system", f"Error: {error_message}")
    
    def _on_ai_move_link_activated(self, link: str) -> None:
        """Handle clicks on AI move links."""
        if not link or not self._ai_chat_controller:
            return
        if link.startswith("move:"):
            notation = html.unescape(link.split("move:", 1)[1])
            if notation:
                self._ai_chat_controller.handle_move_link_click(notation)
    
    def _on_request_started(self) -> None:
        """Handle request started from controller."""
        self._set_input_enabled(False)
        self._show_typing_indicator()
    
    def _on_request_completed(self) -> None:
        """Handle request completed from controller."""
        self._set_input_enabled(True)
        # Typing indicator will be hidden when message is added, but hide it here too as safety
        self._hide_typing_indicator()
    
    def showEvent(self, event) -> None:
        """Handle show event to update message widths when widget is shown.
        
        Args:
            event: Show event.
        """
        super().showEvent(event)
        # Update message widths after widget is shown (scroll area should be sized now)
        QTimer.singleShot(100, self._update_message_widths)
    
    def _populate_models(self) -> None:
        """Populate the model dropdown with available models."""
        if not self._ai_chat_controller:
            return
        
        self.model_combo.clear()
        self.model_combo.setEnabled(True)
        
        # Get available models from controller
        models = self._ai_chat_controller.get_available_models()
        
        if not models:
            self.model_combo.addItem("No models available")
            self.model_combo.setEnabled(False)
            return
        
        # Add models to dropdown
        for model in models:
            self.model_combo.addItem(model)
        
        # Set default model
        default_model = self._ai_chat_controller.get_default_model()
        if default_model:
            index = self.model_combo.findText(default_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
                self._ai_chat_controller.set_selected_model(default_model)
            else:
                # If default model not in list, select first available
                if self.model_combo.count() > 0:
                    self.model_combo.setCurrentIndex(0)
                    self._ai_chat_controller.set_selected_model(self.model_combo.currentText())
        else:
            # No default model, select first available
            if self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)
                self._ai_chat_controller.set_selected_model(self.model_combo.currentText())
    
    def refresh_model_list(self) -> None:
        """Refresh the model dropdown based on current provider settings."""
        self._populate_models()
    
    def _on_model_changed(self, model_string: str) -> None:
        """Handle model selection change.
        
        Args:
            model_string: Selected model string.
        """
        if self._ai_chat_controller and model_string != "No models available":
            self._ai_chat_controller.set_selected_model(model_string)
    
    def _on_tokens_changed(self, value: int) -> None:
        """Handle token limit changes."""
        if self._ai_chat_controller:
            self._ai_chat_controller.set_token_limit(value)
    
    def eventFilter(self, obj, event: QEvent) -> bool:
        """Event filter to handle scroll area resize events.
        
        Args:
            obj: Object that received the event.
            event: Event that occurred.
            
        Returns:
            False to allow event to continue processing.
        """
        if obj == getattr(self, 'model_row_frame', None) and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            QTimer.singleShot(0, self._update_tokens_visibility)
        if obj == self.scroll_area and event.type() == QEvent.Type.Resize:
            # Update max width of all message labels when scroll area is resized
            self._update_message_widths()
        return super().eventFilter(obj, event)
    
    def _update_message_widths(self) -> None:
        """Update maximum width of all message labels based on scroll area width."""
        if not self.scroll_area or self.scroll_area.width() <= 0:
            return
        
        # Use full width minus margins (10px on each side = 20px total)
        max_width = self.scroll_area.width() - 20
        if max_width <= 100:
            return
        
        # Find all QLabel widgets in messages_widget and update their max width
        for widget in self.messages_widget.findChildren(QLabel):
            widget.setMaximumWidth(max_width)
    
    def _update_single_message_width(self, message_label: QLabel) -> None:
        """Update maximum width of a single message label.
        
        Args:
            message_label: The label to update.
        """
        if not self.scroll_area or self.scroll_area.width() <= 0:
            return
        
        # Use full width minus margins (10px on each side = 20px total)
        max_width = self.scroll_area.width() - 20
        if max_width > 100:
            message_label.setMaximumWidth(max_width)
    
    def _show_typing_indicator(self) -> None:
        """Show typing indicator with animated dots."""
        # Remove existing indicator if present
        self._hide_typing_indicator()
        
        # Get AI message config for styling
        message_config = self.chat_config.get('messages', {})
        ai_config = message_config.get('ai', {})
        bg_color = ai_config.get('background_color', [50, 50, 55])
        text_color = ai_config.get('text_color', [200, 200, 200])
        
        # Create typing indicator label
        self._typing_indicator_label = QLabel("●○○")
        self._typing_indicator_label.setWordWrap(False)
        self._typing_indicator_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._typing_indicator_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        
        # Apply styling with reduced opacity
        padding = message_config.get('padding', 10)
        border_radius = message_config.get('border_radius', 5)
        margin = message_config.get('margin', 5)
        
        # Calculate opacity-adjusted colors
        bg_r, bg_g, bg_b = bg_color
        text_r, text_g, text_b = text_color
        
        typing_style = f"""
            QLabel {{
                background-color: rgba({bg_r}, {bg_g}, {bg_b}, {int(self._typing_indicator_opacity * 255)});
                color: rgba({text_r}, {text_g}, {text_b}, {int(self._typing_indicator_opacity * 255)});
                padding: {padding}px;
                border-radius: {border_radius}px;
                font-family: "{self.font_family}";
                font-size: {self.font_size}pt;
                margin: {margin}px;
            }}
        """
        self._typing_indicator_label.setStyleSheet(typing_style)
        
        # Create container widget for alignment
        self._typing_indicator_widget = QWidget()
        self._typing_indicator_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout = QHBoxLayout(self._typing_indicator_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.addWidget(self._typing_indicator_label, 1)
        
        # Insert into messages layout before stretch
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._typing_indicator_widget)
        
        # Set initial dot state
        self._typing_indicator_dot_state = 0
        
        # Start animation timer
        self._typing_indicator_timer = QTimer(self)
        self._typing_indicator_timer.timeout.connect(self._update_typing_dots)
        self._typing_indicator_timer.start(self._typing_indicator_interval)
        
        # Scroll to bottom to show indicator
        QTimer.singleShot(50, self._scroll_to_bottom)
    
    def _hide_typing_indicator(self) -> None:
        """Hide and remove typing indicator."""
        # Stop timer
        if self._typing_indicator_timer:
            self._typing_indicator_timer.stop()
            self._typing_indicator_timer = None
        
        # Remove widget from layout
        if self._typing_indicator_widget:
            self.messages_layout.removeWidget(self._typing_indicator_widget)
            self._typing_indicator_widget.deleteLater()
            self._typing_indicator_widget = None
            self._typing_indicator_label = None
        
        self._typing_indicator_dot_state = 0
    
    def _update_typing_dots(self) -> None:
        """Update typing indicator dots animation."""
        if not self._typing_indicator_label:
            return
        
        # Cycle through dot states: 0="●○○", 1="○●○", 2="○○●"
        self._typing_indicator_dot_state = (self._typing_indicator_dot_state + 1) % 3
        
        if self._typing_indicator_dot_state == 0:
            self._typing_indicator_label.setText("●○○")
        elif self._typing_indicator_dot_state == 1:
            self._typing_indicator_label.setText("○●○")
        else:
            self._typing_indicator_label.setText("○○●")

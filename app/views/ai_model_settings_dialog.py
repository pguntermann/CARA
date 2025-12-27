"""Dialog for configuring AI model settings."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
    QWidget,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QShowEvent, QPalette, QColor
from typing import Dict, Any, Optional, List
from pathlib import Path




class ModelDiscoveryThread(QThread):
    """Thread for discovering models from API providers."""
    
    models_discovered = pyqtSignal(str, list)  # provider, models
    discovery_failed = pyqtSignal(str, str)  # provider, error_message
    
    def __init__(self, provider: str, api_key: str, discovery_service) -> None:
        """Initialize the discovery thread.
        
        Args:
            provider: Provider name ("openai" or "anthropic").
            api_key: API key for the provider.
            discovery_service: AIModelDiscoveryService instance.
        """
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.discovery_service = discovery_service
    
    def run(self) -> None:
        """Run the model discovery."""
        try:
            if self.provider == "openai":
                models = self.discovery_service.get_openai_models(self.api_key)
            elif self.provider == "anthropic":
                models = self.discovery_service.get_anthropic_models(self.api_key)
            else:
                self.discovery_failed.emit(self.provider, f"Unknown provider: {self.provider}")
                return
            
            if models:
                self.models_discovered.emit(self.provider, models)
            else:
                self.discovery_failed.emit(self.provider, "No models found or API key invalid")
        except Exception as e:
            self.discovery_failed.emit(self.provider, str(e))


class AIModelSettingsDialog(QDialog):
    """Dialog for configuring AI model settings."""
    
    def __init__(self, config: Dict[str, Any], user_settings_service, parent=None) -> None:
        """Initialize the AI model settings dialog.
        
        Args:
            config: Configuration dictionary.
            user_settings_service: UserSettingsService instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.user_settings_service = user_settings_service
        
        # Load current settings
        settings = user_settings_service.get_settings()
        self.current_settings = settings.get("ai_models", {})
        self._provider_models = {
            "openai": list(self.current_settings.get("openai", {}).get("models", [])),
            "anthropic": list(self.current_settings.get("anthropic", {}).get("models", []))
        }
        
        # Store fixed size - set it BEFORE layout is set up
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('ai_model_settings', {})
        width = dialog_config.get('width', 600)
        height = dialog_config.get('height', 400)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size BEFORE UI setup
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Initialize discovery service
        from app.services.ai_model_discovery_service import AIModelDiscoveryService
        self.discovery_service = AIModelDiscoveryService(self.config)
        
        # Store discovery threads
        self.discovery_threads: Dict[str, Optional[ModelDiscoveryThread]] = {
            "openai": None,
            "anthropic": None
        }
        
        # Track refresh state
        self._refresh_results: List[tuple] = []
        
        # Load config values
        self._load_config()
        
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("AI Model Settings")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('ai_model_settings', {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get('width', 600)
        self.dialog_height = dialog_config.get('height', 500)
        
        # Background color
        self.bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.border_color = dialog_config.get('border_color', [60, 60, 65])
        self.text_color = dialog_config.get('text_color', [200, 200, 200])
        from app.utils.font_utils import scale_font_size
        self.font_size = scale_font_size(dialog_config.get('font_size', 11))
        
        # Layout
        layout_config = dialog_config.get('layout', {})
        self.layout_margins = layout_config.get('margins', [20, 20, 20, 20])
        self.layout_spacing = layout_config.get('spacing', 15)
        self.section_spacing = layout_config.get('section_spacing', 20)
        
        # Groups
        self.groups_config = dialog_config.get('groups', {})
        
        # Fields
        self.fields_config = dialog_config.get('fields', {})
        
        # Labels
        self.labels_config = dialog_config.get('labels', {})
        
        # Inputs
        self.inputs_config = dialog_config.get('inputs', {})
        
        # Buttons
        self.buttons_config = dialog_config.get('buttons', {})
    
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event to enforce fixed size and refresh values."""
        super().showEvent(event)
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        
        # Refresh values from settings
        self._load_settings()
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint."""
        return self._fixed_size
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.layout_spacing)
        layout.setContentsMargins(self.layout_margins[0], self.layout_margins[1], self.layout_margins[2], self.layout_margins[3])
        
        # Create scroll area for form
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)  # Remove border on macOS
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(self.section_spacing)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        # OpenAI group
        openai_group = self._create_provider_group("OpenAI", "openai")
        scroll_layout.addWidget(openai_group)
        
        # Anthropic group
        anthropic_group = self._create_provider_group("Anthropic", "anthropic")
        scroll_layout.addWidget(anthropic_group)
        
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Store scroll area for styling
        self.scroll_area = scroll
        
        # Buttons
        button_layout = QHBoxLayout()
        button_spacing = self.buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        
        # Refresh Models button (left side)
        self.refresh_models_button = QPushButton("Refresh Models")
        self.refresh_models_button.clicked.connect(self._refresh_all_models)
        button_layout.addWidget(self.refresh_models_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        # Ensure threads are cleaned up when dialog closes
        self.finished.connect(self._cleanup_threads)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
    
    def _create_provider_group(self, provider_name: str, provider_key: str) -> QGroupBox:
        """Create a provider configuration group box.
        
        Args:
            provider_name: Display name (e.g., "OpenAI").
            provider_key: Internal key (e.g., "openai").
            
        Returns:
            Configured QGroupBox.
        """
        group = QGroupBox(provider_name)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(self.fields_config.get('spacing', 8))
        # Set field growth policy to make fields expand
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        # API Key field
        api_key_label = QLabel("API Key:")
        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("Enter your API key")
        # Make input field expand to fill available width in form layout
        api_key_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Set minimum width to ensure it's not too narrow
        api_key_input.setMinimumWidth(200)
        
        # Store reference
        setattr(self, f"{provider_key}_api_key_input", api_key_input)
        
        form_layout.addRow(api_key_label, api_key_input)
        
        # Model selection field
        model_label = QLabel("Default Model:")
        model_combo = QComboBox()
        model_combo.addItem("(Select model)")
        # Make combo box expand to fill available width in form layout, same as API key input
        model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Set minimum width to ensure it's not too narrow, same as API key input
        model_combo.setMinimumWidth(200)
        
        # Store reference
        setattr(self, f"{provider_key}_model_combo", model_combo)
        
        form_layout.addRow(model_label, model_combo)
        
        group.setLayout(form_layout)
        
        return group
    
    def _populate_model_combo(self, provider_key: str, models: List[str], preferred_model: str = "") -> None:
        """Populate a provider's model combo with the provided list."""
        combo = getattr(self, f"{provider_key}_model_combo", None)
        if combo is None:
            return
        
        clean_models = [model for model in models if model]
        self._provider_models[provider_key] = clean_models
        
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(Select model)")
        for model in clean_models:
            combo.addItem(model)
        
        target_model = preferred_model if preferred_model in clean_models else ""
        if target_model:
            index = combo.findText(target_model)
            if index != -1:
                combo.setCurrentIndex(index)
            else:
                combo.setCurrentIndex(0)
        elif clean_models:
            combo.setCurrentIndex(1)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)
    
    def _get_models_for_provider(self, provider_key: str) -> List[str]:
        """Return the current modeled list for a provider, falling back to combo contents."""
        models = list(self._provider_models.get(provider_key, []))
        if models:
            return models
        
        combo = getattr(self, f"{provider_key}_model_combo", None)
        if combo is None:
            return []
        
        collected = []
        for index in range(combo.count()):
            text = combo.itemText(index).strip()
            if text and text != "(Select model)":
                collected.append(text)
        return collected
    
    def _load_settings(self) -> None:
        """Load settings into UI fields."""
        settings = self.user_settings_service.get_settings()
        self.current_settings = settings.get("ai_models", {})
        
        # OpenAI settings
        openai_settings = self.current_settings.get("openai", {})
        self.openai_api_key_input.setText(openai_settings.get("api_key", ""))
        openai_models = list(openai_settings.get("models", []) or [])
        self._provider_models["openai"] = openai_models
        self._populate_model_combo(
            "openai",
            openai_models,
            openai_settings.get("model", "")
        )
        
        # Anthropic settings
        anthropic_settings = self.current_settings.get("anthropic", {})
        self.anthropic_api_key_input.setText(anthropic_settings.get("api_key", ""))
        anthropic_models = list(anthropic_settings.get("models", []) or [])
        self._provider_models["anthropic"] = anthropic_models
        self._populate_model_combo(
            "anthropic",
            anthropic_models,
            anthropic_settings.get("model", "")
        )
    
    def _refresh_all_models(self) -> None:
        """Refresh model lists for all providers that have API keys."""
        providers_to_refresh = []
        
        # Check OpenAI
        openai_api_key = self.openai_api_key_input.text().strip()
        if openai_api_key:
            providers_to_refresh.append(("openai", openai_api_key))
        
        # Check Anthropic
        anthropic_api_key = self.anthropic_api_key_input.text().strip()
        if anthropic_api_key:
            providers_to_refresh.append(("anthropic", anthropic_api_key))
        
        if not providers_to_refresh:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "API Key Required",
                "Please enter at least one API key before refreshing models.",
                self
            )
            return
        
        # Disable refresh button during discovery
        self.refresh_models_button.setEnabled(False)
        self.refresh_models_button.setText("Loading...")
        
        # Cancel any existing discovery threads
        for provider_key in ["openai", "anthropic"]:
            thread = self.discovery_threads.get(provider_key)
            if thread:
                # Disconnect signals first
                try:
                    thread.models_discovered.disconnect()
                    thread.discovery_failed.disconnect()
                except Exception:
                    pass
                
                # If thread is still running, terminate it
                if thread.isRunning():
                    thread.terminate()
                    thread.wait(2000)  # Wait up to 2 seconds for termination
                
                # Clean up thread reference
                self.discovery_threads[provider_key] = None
        
        # Track how many providers we're refreshing
        self._refresh_count = len(providers_to_refresh)
        self._refresh_completed = 0
        self._refresh_results = []  # Store results for combined status message
        
        # Clear cache before refreshing to ensure we get updated model lists
        self.discovery_service.clear_cache()
        
        # Start discovery threads for each provider
        for provider_key, api_key in providers_to_refresh:
            thread = ModelDiscoveryThread(provider_key, api_key, self.discovery_service)
            thread.models_discovered.connect(self._on_models_discovered)
            thread.discovery_failed.connect(self._on_discovery_failed)
            
            self.discovery_threads[provider_key] = thread
            thread.start()
    
    def _on_models_discovered(self, provider: str, models: List[str]) -> None:
        """Handle successful model discovery.
        
        Args:
            provider: Provider name.
            models: List of discovered model IDs.
        """
        combo = getattr(self, f"{provider}_model_combo")
        previous_selection = combo.currentText() if combo.currentIndex() > 0 else ""
        self._populate_model_combo(provider, models, previous_selection)
        
        # Clean up thread
        self.discovery_threads[provider] = None
        
        # Store result for combined status message
        provider_display = "OpenAI" if provider == "openai" else "Anthropic"
        self._refresh_results.append((provider_display, len(models)))
        
        # Check if all refreshes are complete
        self._refresh_completed += 1
        if self._refresh_completed >= getattr(self, '_refresh_count', 1):
            # Show combined status message
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            
            if len(self._refresh_results) == 1:
                provider_name, model_count = self._refresh_results[0]
                progress_service.set_status(f"Successfully refreshed {model_count} models from {provider_name}")
            else:
                # Multiple providers refreshed
                status_parts = []
                for provider_name, model_count in self._refresh_results:
                    status_parts.append(f"{model_count} from {provider_name}")
                progress_service.set_status(f"Successfully refreshed models: {', '.join(status_parts)}")
            
            # Reset state
            self.refresh_models_button.setEnabled(True)
            self.refresh_models_button.setText("Refresh Models")
            self._refresh_completed = 0
            self._refresh_count = 0
            self._refresh_results = []
    
    def _on_discovery_failed(self, provider: str, error: str) -> None:
        """Handle failed model discovery.
        
        Args:
            provider: Provider name.
            error: Error message.
        """
        # Show error message
        from app.views.message_dialog import MessageDialog
        MessageDialog.show_warning(
            self.config,
            "Model Discovery Failed",
            f"Failed to discover models for {provider.capitalize()}:\n{error}\n\n"
            "Please check your API key and try again.",
            self
        )
        
        # Clean up thread
        self.discovery_threads[provider] = None
        
        # Check if all refreshes are complete
        self._refresh_completed += 1
        if self._refresh_completed >= getattr(self, '_refresh_count', 1):
            self.refresh_models_button.setEnabled(True)
            self.refresh_models_button.setText("Refresh Models")
            self._refresh_completed = 0
            self._refresh_count = 0
    
    def _cleanup_threads(self) -> None:
        """Clean up discovery threads before dialog closes."""
        for provider_key in ["openai", "anthropic"]:
            thread = self.discovery_threads.get(provider_key)
            if thread and thread.isRunning():
                # Disconnect signals to prevent callbacks after dialog closes
                try:
                    thread.models_discovered.disconnect()
                    thread.discovery_failed.disconnect()
                except Exception:
                    pass
                
                # Wait for thread to finish (with timeout)
                if not thread.wait(3000):  # Wait up to 3 seconds
                    # If thread is still running, terminate it
                    thread.terminate()
                    thread.wait(1000)  # Wait for termination
                
                # Clean up thread reference
                self.discovery_threads[provider_key] = None
    
    def _on_save(self) -> None:
        """Handle save button click."""
        # Collect settings
        openai_api_key = self.openai_api_key_input.text().strip()
        openai_model = self.openai_model_combo.currentText() if self.openai_model_combo.currentIndex() > 0 else ""
        openai_models = self._get_models_for_provider("openai") if openai_api_key else []
        if not openai_api_key:
            openai_model = ""
        
        anthropic_api_key = self.anthropic_api_key_input.text().strip()
        anthropic_model = self.anthropic_model_combo.currentText() if self.anthropic_model_combo.currentIndex() > 0 else ""
        anthropic_models = self._get_models_for_provider("anthropic") if anthropic_api_key else []
        if not anthropic_api_key:
            anthropic_model = ""
        
        settings = {
            "openai": {
                "api_key": openai_api_key,
                "model": openai_model,
                "models": openai_models
            },
            "anthropic": {
                "api_key": anthropic_api_key,
                "model": anthropic_model,
                "models": anthropic_models
            }
        }
        
        ai_summary_updates = {}
        has_openai_key = bool(openai_api_key)
        has_anthropic_key = bool(anthropic_api_key)
        if has_openai_key and not has_anthropic_key:
            ai_summary_updates = {
                "use_openai_models": True,
                "use_anthropic_models": False
            }
        elif has_anthropic_key and not has_openai_key:
            ai_summary_updates = {
                "use_openai_models": False,
                "use_anthropic_models": True
            }
        
        # Update user settings
        self.user_settings_service.update_ai_model_settings(settings)
        if ai_summary_updates:
            self.user_settings_service.update_ai_summary_settings(ai_summary_updates)
        
        # Save to file
        if self.user_settings_service.save():
            self.accept()
        else:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Save Failed",
                "Failed to save AI model settings. Please try again.",
                self
            )
    
    def _apply_styling(self) -> None:
        """Apply styling from config."""
        # Dialog background using QPalette
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self.bg_color[0], self.bg_color[1], self.bg_color[2]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Apply scrollbar styling to scroll area
        if hasattr(self, 'scroll_area'):
            from app.views.style import StyleManager
            border_color = self.groups_config.get('border_color', [60, 60, 65])
            border_radius = self.groups_config.get('border_radius', 5)
            StyleManager.style_scroll_area(
                self.scroll_area,
                self.config,
                self.bg_color,
                border_color,
                border_radius
            )
        
        # Group boxes
        group_bg_color = self.groups_config.get('background_color', [45, 45, 50])
        border_color = self.groups_config.get('border_color', [60, 60, 65])
        border_radius = self.groups_config.get('border_radius', 5)
        title_color = self.groups_config.get('title_color', [240, 240, 240])
        title_font_family = self.groups_config.get('title_font_family', 'Helvetica Neue')
        from app.utils.font_utils import scale_font_size
        title_font_size = scale_font_size(self.groups_config.get('title_font_size', 11))
        margin_top = self.groups_config.get('margin_top', 10)
        padding_top = self.groups_config.get('padding_top', 20)
        title_left = self.groups_config.get('title_left', 10)
        title_padding = self.groups_config.get('title_padding', 5)
        
        # Handle title_padding as int or list
        if isinstance(title_padding, list):
            title_padding_left = title_padding[0] if len(title_padding) > 0 else 0
            title_padding_right = title_padding[1] if len(title_padding) > 1 else 5
        else:
            title_padding_left = 0
            title_padding_right = title_padding
        
        group_style = (
            f"QGroupBox {{"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {border_radius}px;"
            f"margin-top: {margin_top}px;"
            f"padding-top: {padding_top}px;"
            f"background-color: rgb({group_bg_color[0]}, {group_bg_color[1]}, {group_bg_color[2]});"
            f"}}"
            f"QGroupBox::title {{"
            f"font-family: \"{title_font_family}\";"
            f"font-size: {title_font_size}pt;"
            f"color: rgb({title_color[0]}, {title_color[1]}, {title_color[2]});"
            f"subcontrol-origin: margin;"
            f"left: {title_left}px;"
            f"padding: {title_padding_left} {title_padding_right}px;"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
            # Set content margins if specified
            content_margins = self.groups_config.get('content_margins')
            if content_margins:
                layout = group.layout()
                if layout:
                    layout.setContentsMargins(
                        content_margins[0], content_margins[1], 
                        content_margins[2], content_margins[3]
                    )
        
        # Labels
        label_font_family = self.labels_config.get('font_family', 'Helvetica Neue')
        from app.utils.font_utils import scale_font_size
        label_font_size = scale_font_size(self.labels_config.get('font_size', 10))
        label_text_color = self.labels_config.get('text_color', [200, 200, 200])
        
        label_style = (
            f"QLabel {{"
            f"font-family: \"{label_font_family}\";"
            f"font-size: {label_font_size}pt;"
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            # Skip group box titles
            if isinstance(label.parent(), QGroupBox) and label.text() in ["OpenAI", "Anthropic"]:
                continue
            label.setStyleSheet(label_style)
            # Also set palette to ensure transparent background on macOS
            label_palette = label.palette()
            label_palette.setColor(label.backgroundRole(), QColor(0, 0, 0, 0))  # Transparent
            label.setPalette(label_palette)
        
        # Input widgets (QLineEdit, QComboBox)
        input_bg_color = self.inputs_config.get('background_color', [45, 45, 50])
        input_text_color = self.inputs_config.get('text_color', [200, 200, 200])
        input_border_color = self.inputs_config.get('border_color', [60, 60, 65])
        input_border_width = self.inputs_config.get('border_width', 1)
        input_border_radius = self.inputs_config.get('border_radius', 3)
        input_padding = self.inputs_config.get('padding', 5)
        from app.utils.font_utils import resolve_font_family
        input_font_family_raw = self.inputs_config.get('font_family', 'Cascadia Mono, Menlo')
        input_font_family = resolve_font_family(input_font_family_raw)
        input_font_size = scale_font_size(self.inputs_config.get('font_size', 11))
        input_focus_border_color = self.inputs_config.get('focus_border_color', [0, 120, 212])
        
        # Handle padding as int or list
        if isinstance(input_padding, list):
            input_padding_h = input_padding[0] if len(input_padding) > 0 else 5
            input_padding_v = input_padding[1] if len(input_padding) > 1 else 5
        else:
            input_padding_h = input_padding
            input_padding_v = input_padding
        
        # Get selection colors from config (use defaults if not available)
        selection_bg = self.inputs_config.get('selection_background_color', [70, 90, 130])
        selection_text = self.inputs_config.get('selection_text_color', [240, 240, 240])
        
        # Apply unified line edit styling using StyleManager
        from app.views.style import StyleManager
        
        # Get all QLineEdit widgets
        line_edits = list(self.findChildren(QLineEdit))
        
        if line_edits:
            # Convert padding from [top, right, bottom, left] to [horizontal, vertical]
            # input_padding is [top, right, bottom, left] format
            input_padding = [input_padding_h, input_padding_v]  # [horizontal, vertical]
            
            # Apply styling with dialog-specific colors and font
            StyleManager.style_line_edits(
                line_edits,
                self.config,
                font_family=input_font_family,  # Match original dialog font (already resolved)
                font_size=input_font_size,  # Match original dialog font size
                bg_color=input_bg_color,  # Match combobox background color
                border_color=input_border_color,  # Match combobox border color
                focus_border_color=input_focus_border_color,  # Match combobox focus border color
                border_width=input_border_width,  # Match combobox border width
                border_radius=input_border_radius,  # Match combobox border radius
                padding=input_padding  # Preserve existing padding for alignment
            )
        
        # Apply combobox styling using StyleManager
        from app.views.style import StyleManager
        comboboxes = list(self.findChildren(QComboBox))
        if comboboxes:
            StyleManager.style_comboboxes(
                comboboxes,
                self.config,
                input_text_color,
                input_font_family,
                input_font_size,
                input_bg_color,
                input_border_color,
                input_focus_border_color,
                selection_bg,
                selection_text,
                border_width=input_border_width,
                border_radius=input_border_radius,
                padding=[input_padding_h, input_padding_v],
                editable=False  # Model comboboxes are non-editable
            )
        
        # Apply button styling using StyleManager (uses unified config)
        button_width = self.buttons_config.get('width', 120)
        button_height = self.buttons_config.get('height', 30)
        bg_color_list = [self.bg_color[0], self.bg_color[1], self.bg_color[2]]
        border_color_list = [self.border_color[0], self.border_color[1], self.border_color[2]]
        
        from app.views.style import StyleManager
        all_buttons = self.findChildren(QPushButton)
        StyleManager.style_buttons(
            all_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )

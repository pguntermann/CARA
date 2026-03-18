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
    QCheckBox,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QShowEvent, QPalette, QColor, QAction, QIcon
from typing import Dict, Any, Optional, List
from pathlib import Path


class ModelDiscoveryThread(QThread):
    """Thread for discovering models from API providers."""
    
    models_discovered = pyqtSignal(str, list)  # provider, models
    discovery_failed = pyqtSignal(str, str)  # provider, error_message
    
    def __init__(self, provider: str, api_key: str, discovery_service,
                 base_url: Optional[str] = None) -> None:
        """Initialize the discovery thread.
        
        Args:
            provider: Provider name ("openai", "anthropic", or "custom").
            api_key: API key for the provider (optional for custom).
            discovery_service: AIModelDiscoveryService instance.
            base_url: For custom provider, the base URL (e.g. http://localhost:1234/v1).
        """
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.discovery_service = discovery_service
        self.base_url = base_url
    
    def run(self) -> None:
        """Run the model discovery."""
        try:
            if self.provider == "openai":
                models = self.discovery_service.get_openai_models(self.api_key)
            elif self.provider == "anthropic":
                models = self.discovery_service.get_anthropic_models(self.api_key)
            elif self.provider == "custom" and self.base_url:
                models = self.discovery_service.get_custom_models(self.base_url, self.api_key or None)
            else:
                self.discovery_failed.emit(self.provider, f"Unknown or misconfigured provider: {self.provider}")
                return
            
            if models:
                self.models_discovered.emit(self.provider, models)
            else:
                self.discovery_failed.emit(self.provider, "No models found or endpoint unreachable")
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
            "anthropic": list(self.current_settings.get("anthropic", {}).get("models", [])),
            "custom": list(self.current_settings.get("custom", {}).get("models", []))
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
            "anthropic": None,
            "custom": None
        }
        
        # Track refresh state
        self._refresh_results: List[tuple] = []
        # Custom endpoint disclaimer: only show once per dialog lifetime,
        # and only on the first user-driven enable action.
        self._custom_endpoint_disclaimer_shown = False
        self._suppress_custom_endpoint_disclaimer = True
        # Password reveal state for API key line edits (id(edit) -> {action, icon_show, icon_hide})
        self._password_reveal_data: Dict[int, Dict[str, Any]] = {}
        
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
        self.default_custom_base_url = dialog_config.get('default_custom_base_url', 'http://localhost:1234/v1')
        # Minimum width for form labels so input fields align across all groups (pixels).
        self.form_label_min_width = dialog_config.get('form_label_min_width', 220)
        
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

        # Custom endpoint disclaimer content (configurable so it can be updated
        # without touching code).
        disclaimer_config = dialog_config.get('custom_endpoint_disclaimer', {})
        self.custom_endpoint_disclaimer_title = disclaimer_config.get(
            'title',
            'Custom Endpoint Disclaimer',
        )
        self.custom_endpoint_disclaimer_message = disclaimer_config.get(
            'message',
            "<b>Experimental feature:</b> Custom endpoint support is an experimental implementation. "
            "Responses from locally run models may not match the quality of top-tier cloud models "
            "(e.g. OpenAI GPT-4, Anthropic Claude)."
            "<br><br>Local models may be less accurate, less consistent, or occasionally produce incorrect "
            "or irrelevant answers. Use at your own discretion.",
        )
    
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
        
        # Custom endpoint group (OpenAI-compatible, e.g. local LLM)
        custom_group = self._create_custom_provider_group()
        scroll_layout.addWidget(custom_group)
        
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Request timeout (applies to all providers)
        timeout_layout = QFormLayout()
        timeout_layout.setSpacing(self.fields_config.get('spacing', 8))
        timeout_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        timeout_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        timeout_label = QLabel("Request timeout (seconds):")
        timeout_label.setMinimumWidth(self.form_label_min_width)
        self.request_timeout_spinbox = QSpinBox()
        self.request_timeout_spinbox.setRange(10, 600)
        self.request_timeout_spinbox.setValue(60)
        self.request_timeout_spinbox.setFixedWidth(56)
        timeout_layout.addRow(timeout_label, self.request_timeout_spinbox)
        timeout_widget = QWidget()
        timeout_widget.setLayout(timeout_layout)
        layout.addWidget(timeout_widget, 0, Qt.AlignmentFlag.AlignLeft)
        
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
        
        # API Key field (masked with reveal toggle)
        api_key_label = QLabel("API Key:")
        api_key_label.setMinimumWidth(self.form_label_min_width)
        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("Enter your API key")
        # Make input field expand to fill available width in form layout
        api_key_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Set minimum width to ensure it's not too narrow
        api_key_input.setMinimumWidth(200)
        self._add_password_reveal(api_key_input)
        
        # Store reference
        setattr(self, f"{provider_key}_api_key_input", api_key_input)
        
        form_layout.addRow(api_key_label, api_key_input)
        
        # Model selection field
        model_label = QLabel("Default Model:")
        model_label.setMinimumWidth(self.form_label_min_width)
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
    
    def _create_custom_provider_group(self) -> QGroupBox:
        """Create the Custom endpoint configuration group (enable checkbox, base URL, optional API key, model)."""
        group = QGroupBox("Custom endpoint")
        
        form_layout = QFormLayout()
        form_layout.setSpacing(self.fields_config.get('spacing', 8))
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        enable_checkbox = QCheckBox("Enable custom endpoint")
        enable_checkbox.setChecked(False)
        enable_checkbox.toggled.connect(self._on_custom_enabled_toggled)
        self.custom_enabled_checkbox = enable_checkbox
        form_layout.addRow(enable_checkbox)
        
        default_url = getattr(self, 'default_custom_base_url', 'http://localhost:1234/v1')
        base_url_label = QLabel("Base URL:")
        base_url_label.setMinimumWidth(self.form_label_min_width)
        base_url_input = QLineEdit()
        base_url_input.setPlaceholderText(default_url)
        base_url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        base_url_input.setMinimumWidth(200)
        self.custom_base_url_input = base_url_input
        form_layout.addRow(base_url_label, base_url_input)
        
        api_key_label = QLabel("API Key (optional):")
        api_key_label.setMinimumWidth(self.form_label_min_width)
        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("Leave empty for local servers")
        api_key_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        api_key_input.setMinimumWidth(200)
        self._add_password_reveal(api_key_input)
        self.custom_api_key_input = api_key_input
        form_layout.addRow(api_key_label, api_key_input)
        
        model_label = QLabel("Default Model:")
        model_label.setMinimumWidth(self.form_label_min_width)
        model_combo = QComboBox()
        model_combo.addItem("(Select model)")
        model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        model_combo.setMinimumWidth(200)
        self.custom_model_combo = model_combo
        form_layout.addRow(model_label, model_combo)
        
        group.setLayout(form_layout)
        return group
    
    def _on_custom_enabled_toggled(self, checked: bool) -> None:
        """Enable or disable custom endpoint input fields based on checkbox."""
        self.custom_base_url_input.setEnabled(checked)
        self.custom_api_key_input.setEnabled(checked)
        self.custom_model_combo.setEnabled(checked)

        if not checked:
            return

        # Show disclaimer only for user-driven enable actions.
        if self._suppress_custom_endpoint_disclaimer or self._custom_endpoint_disclaimer_shown:
            return

        from app.views.message_dialog import MessageDialog

        MessageDialog.show_warning(
            self.config,
            self.custom_endpoint_disclaimer_title,
            self.custom_endpoint_disclaimer_message,
            self,
        )
        self._custom_endpoint_disclaimer_shown = True
    
    def _add_password_reveal(self, line_edit: QLineEdit) -> None:
        """Set password echo mode and add a trailing action to toggle visibility.
        The line edit remains a plain QLineEdit so StyleManager.style_line_edits still applies.
        """
        line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        icons_dir = Path(__file__).parent.parent.parent / "app" / "resources" / "icons"
        icon_show = QIcon(str(icons_dir / "eye.svg"))
        icon_hide = QIcon(str(icons_dir / "eye_off.svg"))
        action = QAction(self)
        action.setIcon(icon_show)
        action.setToolTip("Show password")
        action.triggered.connect(lambda checked=False, le=line_edit: self._toggle_password_reveal(le))
        line_edit.addAction(action, QLineEdit.ActionPosition.TrailingPosition)
        self._password_reveal_data[id(line_edit)] = {
            "action": action,
            "icon_show": icon_show,
            "icon_hide": icon_hide,
        }
    
    def _toggle_password_reveal(self, line_edit: QLineEdit) -> None:
        """Toggle API key visibility and update the reveal action icon and tooltip."""
        data = self._password_reveal_data.get(id(line_edit))
        if not data:
            return
        if line_edit.echoMode() == QLineEdit.EchoMode.Password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            data["action"].setIcon(data["icon_hide"])
            data["action"].setToolTip("Hide password")
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            data["action"].setIcon(data["icon_show"])
            data["action"].setToolTip("Show password")
    
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

        # Suppress disclaimer while we populate the checkbox from persisted settings.
        self._suppress_custom_endpoint_disclaimer = True
        
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
        
        # Custom endpoint settings
        custom_settings = self.current_settings.get("custom", {})
        custom_enabled = custom_settings.get("enabled", False)
        self._custom_endpoint_disclaimer_shown = bool(custom_enabled)
        self.custom_enabled_checkbox.setChecked(custom_enabled)
        custom_base_url_saved = (custom_settings.get("base_url") or "").strip()
        self.custom_base_url_input.setText(
            custom_base_url_saved or self.default_custom_base_url
        )
        self.custom_api_key_input.setText(custom_settings.get("api_key", ""))
        custom_models = list(custom_settings.get("models", []) or [])
        self._provider_models["custom"] = custom_models
        self._populate_model_combo(
            "custom",
            custom_models,
            custom_settings.get("model", "")
        )
        self._on_custom_enabled_toggled(custom_enabled)
        
        # Request timeout (from ai_summary)
        ai_summary = settings.get("ai_summary", {})
        timeout = max(10, min(600, int(ai_summary.get("request_timeout_seconds", 60))))
        self.request_timeout_spinbox.setValue(timeout)

        self._suppress_custom_endpoint_disclaimer = False
    
    def _refresh_all_models(self) -> None:
        """Refresh model lists for all providers that have API keys.
        Providers without API keys will have their models cleared."""
        providers_to_refresh = []
        
        # Check OpenAI
        openai_api_key = self.openai_api_key_input.text().strip()
        if openai_api_key:
            providers_to_refresh.append(("openai", openai_api_key, None))
        else:
            self._populate_model_combo("openai", [], "")
        
        # Check Anthropic
        anthropic_api_key = self.anthropic_api_key_input.text().strip()
        if anthropic_api_key:
            providers_to_refresh.append(("anthropic", anthropic_api_key, None))
        else:
            self._populate_model_combo("anthropic", [], "")
        
        # Check Custom (only if enabled; base URL required; API key optional)
        custom_enabled = self.custom_enabled_checkbox.isChecked()
        custom_base_url = self.custom_base_url_input.text().strip()
        custom_api_key = self.custom_api_key_input.text().strip()
        if custom_enabled and custom_base_url:
            providers_to_refresh.append(("custom", custom_api_key, custom_base_url))
        else:
            self._populate_model_combo("custom", [], "")
        
        if not providers_to_refresh:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Configuration Required",
                "Please enter at least one API key (OpenAI/Anthropic) or a custom base URL before refreshing models.",
                self
            )
            return
        
        # Disable refresh button during discovery
        self.refresh_models_button.setEnabled(False)
        self.refresh_models_button.setText("Loading...")
        
        # Cancel any existing discovery threads
        for provider_key in ["openai", "anthropic", "custom"]:
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
                
                self.discovery_threads[provider_key] = None
        
        # Track how many providers we're refreshing
        self._refresh_count = len(providers_to_refresh)
        self._refresh_completed = 0
        self._refresh_results = []  # Store results for combined status message
        
        # Start discovery threads for each provider
        for provider_key, api_key, base_url in providers_to_refresh:
            thread = ModelDiscoveryThread(
                provider_key, api_key, self.discovery_service,
                base_url=base_url
            )
            thread.models_discovered.connect(self._on_models_discovered)
            thread.discovery_failed.connect(self._on_discovery_failed)
            
            self.discovery_threads[provider_key] = thread
            thread.start()
    
    def _on_models_discovered(self, provider: str, models: List[str]) -> None:
        """Handle successful model discovery.
        
        Args:
            provider: Provider name (openai, anthropic, or custom).
            models: List of discovered model IDs.
        """
        combo = getattr(self, f"{provider}_model_combo")
        previous_selection = combo.currentText() if combo.currentIndex() > 0 else ""
        self._populate_model_combo(provider, models, previous_selection)
        
        # Clean up thread
        self.discovery_threads[provider] = None
        
        # Store result for combined status message
        provider_display = {"openai": "OpenAI", "anthropic": "Anthropic", "custom": "Custom"}.get(provider, provider)
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
            f"Failed to discover models for {provider.capitalize()}:<br>{error}<br><br>"
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
        for provider_key in ["openai", "anthropic", "custom"]:
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
        
        custom_enabled = self.custom_enabled_checkbox.isChecked()
        custom_base_url = self.custom_base_url_input.text().strip()
        custom_api_key = self.custom_api_key_input.text().strip()
        custom_model = self.custom_model_combo.currentText() if self.custom_model_combo.currentIndex() > 0 else ""
        custom_models = self._get_models_for_provider("custom") if (custom_enabled and custom_base_url) else []
        if not custom_base_url:
            custom_model = ""
        
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
            },
            "custom": {
                "enabled": custom_enabled,
                "base_url": custom_base_url,
                "api_key": custom_api_key,
                "model": custom_model,
                "models": custom_models
            }
        }
        
        ai_summary_updates = {"request_timeout_seconds": self.request_timeout_spinbox.value()}
        has_openai_key = bool(openai_api_key)
        has_anthropic_key = bool(anthropic_api_key)
        has_custom = bool(custom_enabled and custom_base_url)
        if has_openai_key and not has_anthropic_key and not has_custom:
            ai_summary_updates.update({
                "use_openai_models": True,
                "use_anthropic_models": False,
                "use_custom_models": False
            })
        elif has_anthropic_key and not has_openai_key and not has_custom:
            ai_summary_updates.update({
                "use_openai_models": False,
                "use_anthropic_models": True,
                "use_custom_models": False
            })
        elif has_custom and not has_openai_key and not has_anthropic_key:
            ai_summary_updates.update({
                "use_openai_models": False,
                "use_anthropic_models": False,
                "use_custom_models": True
            })
        
        # Update user settings
        self.user_settings_service.update_ai_model_settings(settings)
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
        group_bg_color = self.groups_config.get('background_color')  # None = use unified default
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
        
        # Handle title_padding as int or list - convert to array format (Pattern 1)
        if isinstance(title_padding, list):
            title_padding_array = title_padding if len(title_padding) >= 2 else [title_padding[0] if len(title_padding) > 0 else 0, 5]
        else:
            title_padding_array = [0, title_padding]
        
        border_width = self.groups_config.get('border_width', 1)
        
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            from app.views.style import StyleManager
            content_margins = self.groups_config.get('content_margins')
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=border_color,
                border_width=border_width,
                border_radius=border_radius,
                bg_color=group_bg_color,
                margin_top=margin_top,
                padding_top=padding_top,
                title_font_family=title_font_family,
                title_font_size=title_font_size,
                title_color=title_color,
                title_left=title_left,
                title_padding=title_padding_array,
                content_margins=content_margins
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
            if isinstance(label.parent(), QGroupBox) and label.text() in ["OpenAI", "Anthropic", "Custom endpoint"]:
                continue
            label.setStyleSheet(label_style)
            # Also set palette to ensure transparent background on macOS
            label_palette = label.palette()
            label_palette.setColor(label.backgroundRole(), QColor(0, 0, 0, 0))  # Transparent
            label.setPalette(label_palette)
        
        # Checkboxes (e.g. Enable custom endpoint)
        checkboxes = self.findChildren(QCheckBox)
        if checkboxes:
            from pathlib import Path
            from app.views.style import StyleManager
            project_root = Path(__file__).parent.parent.parent
            checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
            checkbox_bg = self.inputs_config.get('background_color', [45, 45, 50])
            checkbox_border = self.inputs_config.get('border_color', [60, 60, 65])
            StyleManager.style_checkboxes(
                checkboxes,
                self.config,
                label_text_color,
                label_font_family,
                label_font_size,
                checkbox_bg,
                checkbox_border,
                checkmark_path
            )
        
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
            # Use a lighter mask character for password fields (· U+00B7) instead of default bullet
            for le in line_edits:
                if le.echoMode() == QLineEdit.EchoMode.Password:
                    le.setStyleSheet(le.styleSheet() + " QLineEdit { lineedit-password-character: 183; }")
        
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
        
        # Apply spinbox styling using StyleManager (e.g. Request timeout)
        spinboxes = list(self.findChildren(QSpinBox))
        if spinboxes:
            spinbox_padding = [input_padding_h, input_padding_v]
            StyleManager.style_spinboxes(
                spinboxes,
                self.config,
                text_color=input_text_color,
                font_family=input_font_family,
                font_size=input_font_size,
                bg_color=input_bg_color,
                border_color=input_border_color,
                focus_border_color=input_focus_border_color,
                border_width=input_border_width,
                border_radius=input_border_radius,
                padding=spinbox_padding
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

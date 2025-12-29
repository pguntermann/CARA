Dialog Style Guide
==================

Overview
--------
This guide provides instructions for implementing new dialogs in CARA. All dialogs must use StyleManager for UI control styling and configuration-driven values from config.json.

Core Principles
---------------
1. **Configuration-Driven**: All styling values MUST come from config.json, never hardcoded
2. **StyleManager-Based**: Use StyleManager for all UI controls to ensure unified styling
3. **Template-Based**: Use BulkTagDialog (`app/views/bulk_tag_dialog.py`) as the reference template
4. **Validation**: All config values must be validated by ConfigLoader

Dialog Implementation Pattern
------------------------------

All dialogs should follow this structure:

```python
class MyDialog(QDialog):
    def __init__(self, config: Dict[str, Any], ...):
        super().__init__()
        self.config = config
        self._load_config()
        self._setup_ui()
        self._apply_styling()
    
    def _load_config(self) -> None:
        """Load configuration values from config.json"""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("my_dialog", {})
        # Load dialog dimensions, colors, spacing, etc.
        # Use scale_font_size() and resolve_font_family() for font values
        from app.utils.font_utils import scale_font_size, resolve_font_family
    
    def _setup_ui(self) -> None:
        """Create and layout UI elements"""
        # Create widgets and layouts
    
    def _apply_styling(self) -> None:
        """Apply styling using StyleManager"""
        from app.views.style import StyleManager
        # Use StyleManager for all UI controls
```

Configuration Structure
-----------------------

Dialog configuration is defined in config.json under `ui.dialogs.<dialog_name>`:

```json
{
  "ui": {
    "dialogs": {
      "my_dialog": {
        "width": 500,
        "height": 400,
        "background_color": [40, 40, 45],
        "border_color": [60, 60, 65],
        "text_color": [200, 200, 200],
        "spacing": {
          "layout": 10,
          "section": 15
        },
        "buttons": {
          "width": 120,
          "height": 30
        },
        "inputs": {
          "font_family": "Cascadia Mono",
          "background_color": [30, 30, 35],
          "border_color": [60, 60, 65]
        }
      }
    }
  }
}
```

StyleManager-Based Styling
---------------------------

CARA uses a centralized `StyleManager` class (`app/views/style/style_manager.py`) for consistent UI control styling. StyleManager reads default values from `ui.styles` in config.json, ensuring consistency while allowing dialog-specific overrides.

### Usage

```python
from app.views.style import StyleManager

# Style buttons
StyleManager.style_buttons(
    [button1, button2],
    self.config,
    bg_color=[40, 40, 45],  # Dialog background color
    border_color=[60, 60, 65],  # Dialog border color
    min_width=120,  # Optional override
    min_height=30   # Optional override
)

# Style line edits
from app.utils.font_utils import resolve_font_family
StyleManager.style_line_edits(
    [line_edit1, line_edit2],
    self.config,
    font_family=resolve_font_family("Cascadia Mono"),  # Resolve font family
    bg_color=[30, 30, 35]  # Optional override
)

# Style comboboxes
from app.utils.font_utils import scale_font_size, resolve_font_family
StyleManager.style_comboboxes(
    [combo1, combo2],
    self.config,
    text_color=[240, 240, 240],
    font_family=resolve_font_family("Cascadia Mono"),  # Resolve font family
    font_size=scale_font_size(11),  # Scale font size for DPI
    bg_color=[30, 30, 35],
    border_color=[60, 60, 65],
    focus_border_color=[0, 120, 212],
    selection_bg_color=[70, 90, 130],
    selection_text_color=[240, 240, 240],
    border_radius=3,
    padding=[8, 6],
    editable=False
)

# Style other controls
StyleManager.style_checkboxes([checkbox1, checkbox2], self.config)
StyleManager.style_radio_buttons([radio1, radio2], self.config)
StyleManager.style_spinboxes([spinbox1, spinbox2], self.config)
StyleManager.style_group_boxes([group1, group2], self.config, ...)
```

### Key Points

- **Always use StyleManager** for buttons, line edits, comboboxes, checkboxes, radio buttons, spinboxes, and group boxes
- **Override parameters** only when dialog-specific styling is needed
- **Unspecified parameters** automatically use unified defaults from `ui.styles` in config.json (with automatic DPI scaling)
- **DPI scaling**: When passing `font_size` or `font_family` parameters to StyleManager, use `scale_font_size()` and `resolve_font_family()` from `app.utils.font_utils`. If these parameters are omitted, StyleManager automatically applies DPI scaling from unified config

Dialog Setup
------------

### Font Loading with DPI Scaling

When loading font sizes and families from dialog config, always use DPI scaling utilities:

```python
from app.utils.font_utils import scale_font_size, resolve_font_family

# Font sizes must be scaled for DPI
font_size = scale_font_size(dialog_config.get("font_size", 11))
label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
input_font_size = scale_font_size(inputs_config.get("font_size", 11))

# Font families must be resolved
font_family = resolve_font_family(dialog_config.get("font_family", "Helvetica Neue"))
input_font_family = resolve_font_family(inputs_config.get("font_family", "Cascadia Mono"))
```

**Note**: StyleManager automatically handles DPI scaling when reading from unified `ui.styles` config. Only apply scaling manually when loading dialog-specific font values.

### Dimensions

```python
dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("my_dialog", {})
width = dialog_config.get("width", 500)
height = dialog_config.get("height", 400)
self.setFixedSize(width, height)
```

### Background Color

```python
bg_color = dialog_config.get("background_color", [40, 40, 45])
from PyQt6.QtGui import QPalette, QColor
palette = self.palette()
palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
self.setPalette(palette)
self.setAutoFillBackground(True)
```

### Layout Spacing

```python
spacing_config = dialog_config.get("spacing", {})
layout_spacing = spacing_config.get("layout", 10)
section_spacing = spacing_config.get("section", 15)
main_layout.setSpacing(layout_spacing)
main_layout.setContentsMargins(10, 10, 10, 10)
```

ConfigLoader Integration
------------------------

All dialog config keys must be added to `ConfigLoader._get_required_keys()`:

```python
'ui.dialogs.my_dialog.width',
'ui.dialogs.my_dialog.height',
'ui.dialogs.my_dialog.background_color',
'ui.dialogs.my_dialog.buttons.width',
'ui.dialogs.my_dialog.buttons.height',
# ... etc
```

ConfigLoader validates all required keys on startup. Missing keys cause application startup to fail with clear error messages.

Template Dialog
---------------

Use **BulkTagDialog** (`app/views/bulk_tag_dialog.py`) as the reference template:

- Complete implementation following `_load_config()`, `_setup_ui()`, `_apply_styling()` pattern
- Uses StyleManager for all UI controls
- Demonstrates proper config loading and dialog-specific overrides
- Shows form layout with labels, inputs, and buttons
- Fixed-size non-resizable dialog implementation

Common Pitfalls
---------------

1. **Hardcoded Values**: Never use magic numbers - always load from config
2. **Manual Styling**: Always use StyleManager, never construct stylesheets manually
3. **Wrong Units**: Use `pt` for fonts, not `px`
4. **Missing DPI Scaling**: Always use `scale_font_size()` and `resolve_font_family()` when loading font values from dialog config or passing them to StyleManager
5. **Missing Config Keys**: Always add all config keys to ConfigLoader

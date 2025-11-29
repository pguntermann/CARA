Dialog Style Guide and Implementation Framework
================================================

Overview
--------
This guide provides comprehensive instructions for implementing new dialogs in CARA. All dialogs must follow a consistent styling approach using configuration-driven values from config.json, ensuring visual consistency and maintainability across the application.

Core Principles
---------------
1. **Configuration-Driven**: All styling values MUST come from config.json, never hardcoded
2. **Consistency**: All dialogs must follow the same styling patterns
3. **Template-Based**: Use existing dialogs (ClassificationSettingsDialog, EngineDialog, EngineConfigurationDialog) as templates
4. **No Magic Numbers**: All dimensions, colors, spacing, and fonts must be configurable
5. **Validation**: All config values must be validated by ConfigLoader

Architecture
------------

1. Configuration Structure
   All dialog styling is defined in config.json under:
   ```
   ui.dialogs.<dialog_name>
   ```

   Required sections:
   - `width`, `height`: Dialog dimensions
   - `background_color`: Dialog background color [R, G, B]
   - `buttons`: Button styling configuration
   - `labels`: Label styling configuration
   - `inputs`: Input field styling configuration
   - `groups`: Group box styling configuration (if used)
   - `spacing`: Layout spacing values

2. Dialog Implementation Pattern
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
           # Load all values with defaults
       
       def _setup_ui(self) -> None:
           """Create and layout UI elements"""
           # Create widgets and layouts
       
       def _apply_styling(self) -> None:
           """Apply styling from config.json to all UI elements"""
           # Apply stylesheets and styling
   ```

Button Styling
--------------

All buttons must use the standardized button styling pattern:

1. Config Structure (config.json):
   ```json
   "buttons": {
     "spacing": 10,
     "width": 120,
     "height": 30,
     "border_radius": 3,
     "padding": 5,
     "background_offset": 20,
     "hover_background_offset": 30,
     "pressed_background_offset": 10
   }
   ```

2. Implementation Pattern:
   ```python
   def _apply_styling(self) -> None:
       dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("my_dialog", {})
       buttons_config = dialog_config.get("buttons", {})
       bg_color = dialog_config.get("background_color", [40, 40, 45])
       border_color = dialog_config.get("border_color", [60, 60, 65])
       text_color = dialog_config.get("text_color", [200, 200, 200])
       font_size = dialog_config.get("font_size", 11)
       
       button_width = buttons_config.get("width", 120)
       button_height = buttons_config.get("height", 30)
       button_border_radius = buttons_config.get("border_radius", 3)
       button_padding = buttons_config.get("padding", 5)
       button_bg_offset = buttons_config.get("background_offset", 20)
       button_hover_offset = buttons_config.get("hover_background_offset", 30)
       button_pressed_offset = buttons_config.get("pressed_background_offset", 10)
       
       button_style = (
           f"QPushButton {{"
           f"min-width: {button_width}px;"
           f"min-height: {button_height}px;"
           f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
           f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
           f"border-radius: {button_border_radius}px;"
           f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
           f"font-size: {font_size}pt;"
           f"padding: {button_padding}px;"
           f"}}"
           f"QPushButton:hover {{"
           f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
           f"}}"
           f"QPushButton:pressed {{"
           f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
           f"}}"
       )
       
       for button in self.findChildren(QPushButton):
           button.setStyleSheet(button_style)
   ```

3. Key Points:
   - Use `background_offset` approach (not explicit RGB values)
   - Use `pt` for font sizes (not `px`)
   - Use `min-width` and `min-height` (not fixed width/height)
   - Apply to all buttons using `findChildren(QPushButton)`
   - Special buttons (e.g., Browse "..." button) can be styled separately if needed

Label Styling
-------------

1. Config Structure:
   ```json
   "labels": {
     "font_family": "Helvetica Neue",
     "font_size": 11,
     "text_color": [200, 200, 200]
   }
   ```

2. Implementation Pattern:
   ```python
   labels_config = dialog_config.get("labels", {})
   label_font_family = labels_config.get("font_family", "Helvetica Neue")
   label_font_size = labels_config.get("font_size", 11)
   label_text_color = labels_config.get("text_color", [200, 200, 200])
   
   label_style = (
       f"QLabel {{"
       f"font-family: {label_font_family};"
       f"font-size: {label_font_size}pt;"
       f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
       f"}}"
   )
   
   for label in self.findChildren(QLabel):
       label.setStyleSheet(label_style)
   ```

Input Field Styling
-------------------

1. Config Structure:
   ```json
   "inputs": {
     "font_family": "Cascadia Mono",
     "font_size": 11,
     "text_color": [240, 240, 240],
     "background_color": [30, 30, 35],
     "border_color": [60, 60, 65],
     "border_radius": 3,
     "padding": [8, 6]
   }
   ```

2. Implementation Pattern:
   ```python
   inputs_config = dialog_config.get("inputs", {})
   input_font_family = inputs_config.get("font_family", "Cascadia Mono")
   input_font_size = inputs_config.get("font_size", 11)
   input_text_color = inputs_config.get("text_color", [240, 240, 240])
   input_bg_color = inputs_config.get("background_color", [30, 30, 35])
   input_border_color = inputs_config.get("border_color", [60, 60, 65])
   input_border_radius = inputs_config.get("border_radius", 3)
   input_padding = inputs_config.get("padding", [8, 6])
   
   input_style = (
       f"QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{"
       f"font-family: {input_font_family};"
       f"font-size: {input_font_size}pt;"
       f"color: rgb({input_text_color[0]}, {input_text_color[1]}, {input_text_color[2]});"
       f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
       f"border: 1px solid rgb({input_border_color[0]}, {input_border_color[1]}, {input_border_color[2]});"
       f"border-radius: {input_border_radius}px;"
       f"padding: {input_padding[1]}px {input_padding[0]}px;"
       f"}}"
   )
   
   for widget in self.findChildren((QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox)):
       widget.setStyleSheet(input_style)
   ```

Group Box Styling
-----------------

1. Config Structure:
   ```json
   "groups": {
     "title_font_family": "Helvetica Neue",
     "title_font_size": 11,
     "title_color": [240, 240, 240],
     "content_margins": [10, 15, 10, 10],
     "margin_top": 10,
     "padding_top": 5
   }
   ```

2. Implementation Pattern:
   ```python
   groups_config = dialog_config.get("groups", {})
   group_title_font = groups_config.get("title_font_family", "Helvetica Neue")
   group_title_size = groups_config.get("title_font_size", 11)
   group_title_color = groups_config.get("title_color", [240, 240, 240])
   content_margins = groups_config.get("content_margins", [10, 15, 10, 10])  # [left, top, right, bottom]
   margin_top = groups_config.get("margin_top", 10)
   padding_top = groups_config.get("padding_top", 5)
   
   group_style = (
       f"QGroupBox {{"
       f"font-family: {group_title_font};"
       f"font-size: {group_title_size}pt;"
       f"color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});"
       f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
       f"border-radius: 3px;"
       f"margin-top: {margin_top}px;"
       f"padding-top: {padding_top}px;"
       f"}}"
       f"QGroupBox::title {{"
       f"subcontrol-origin: margin;"
       f"subcontrol-position: top left;"
       f"padding-left: 5px;"
       f"padding-right: 5px;"
       f"padding-top: {padding_top}px;"
       f"}}"
   )
   
   for group in self.findChildren(QGroupBox):
       group.setStyleSheet(group_style)
       # Set content margins
       layout = group.layout()
       if layout:
           layout.setContentsMargins(content_margins[0], content_margins[1], content_margins[2], content_margins[3])
   ```

ComboBox Styling
----------------

1. Special Considerations:
   - Use custom `NoWheelComboBox` class to prevent mouse wheel from changing values
   - Style dropdown arrow to hide default white box icon

2. Implementation Pattern:
   ```python
   # Create custom combobox class
   class NoWheelComboBox(QComboBox):
       def wheelEvent(self, event):
           # Ignore wheel events to prevent accidental value changes
           event.ignore()
   
   # In styling:
   combo_style = (
       f"QComboBox {{"
       f"font-family: {input_font_family};"
       f"font-size: {input_font_size}pt;"
       f"color: rgb({input_text_color[0]}, {input_text_color[1]}, {input_text_color[2]});"
       f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
       f"border: 1px solid rgb({input_border_color[0]}, {input_border_color[1]}, {input_border_color[2]});"
       f"border-radius: {input_border_radius}px;"
       f"padding: {input_padding[1]}px {input_padding[0]}px;"
       f"}}"
       f"QComboBox::drop-down {{"
       f"width: 0px;"
       f"height: 0px;"
       f"image: none;"
       f"}}"
       f"QComboBox::down-arrow {{"
       f"width: 0px;"
       f"height: 0px;"
       f"image: none;"
       f"}}"
   )
   ```

Layout Management
-----------------

1. Spacing and Margins:
   ```python
   spacing_config = dialog_config.get("spacing", {})
   layout_spacing = spacing_config.get("layout", 10)
   section_spacing = spacing_config.get("section", 15)
   
   main_layout.setSpacing(layout_spacing)
   main_layout.setContentsMargins(10, 10, 10, 10)  # Standard dialog margins
   ```

2. Scroll Areas:
   - Use dynamic height calculation, never fixed heights
   - Calculate: available_height = dialog_height - header - buttons - margins - other_elements
   - Use QSizePolicy.Policy.Expanding for vertical policy

3. Size Policies:
   - Buttons: QSizePolicy.Policy.Fixed (both directions)
   - Labels: QSizePolicy.Policy.Fixed (vertical), QSizePolicy.Policy.Expanding (horizontal)
   - Inputs: QSizePolicy.Policy.Fixed (vertical), QSizePolicy.Policy.Expanding (horizontal)

Dialog Dimensions
-----------------

1. Config Structure:
   ```json
   "width": 500,
   "height": 400,
   "minimum_width": 400,
   "minimum_height": 300
   ```

2. Implementation:
   ```python
   dialog_width = dialog_config.get("width", 500)
   dialog_height = dialog_config.get("height", 400)
   min_width = dialog_config.get("minimum_width", 400)
   min_height = dialog_config.get("minimum_height", 300)
   
   self.setFixedSize(dialog_width, dialog_height)  # Or setMinimumSize if resizable
   self.setMinimumSize(min_width, min_height)
   ```

Background Color
----------------

1. Implementation:
   ```python
   bg_color = dialog_config.get("background_color", [40, 40, 45])
   
   # Method 1: Using QPalette
   from PyQt6.QtGui import QPalette, QColor
   palette = self.palette()
   palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
   self.setPalette(palette)
   self.setAutoFillBackground(True)
   
   # Method 2: Using stylesheet (apply last to ensure it's not overridden)
   dialog_stylesheet = f"""
       QDialog {{
           background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
       }}
   """
   self.setStyleSheet(self.styleSheet() + dialog_stylesheet)
   ```

Config.json Structure
---------------------

Complete example structure for a new dialog:

```json
{
  "ui": {
    "dialogs": {
      "my_dialog": {
        "width": 500,
        "height": 400,
        "minimum_width": 400,
        "minimum_height": 300,
        "background_color": [40, 40, 45],
        "border_color": [60, 60, 65],
        "text_color": [200, 200, 200],
        "font_size": 11,
        "spacing": {
          "layout": 10,
          "section": 15
        },
        "buttons": {
          "spacing": 10,
          "width": 120,
          "height": 30,
          "border_radius": 3,
          "padding": 5,
          "background_offset": 20,
          "hover_background_offset": 30,
          "pressed_background_offset": 10
        },
        "labels": {
          "font_family": "Helvetica Neue",
          "font_size": 11,
          "text_color": [200, 200, 200]
        },
        "inputs": {
          "font_family": "Cascadia Mono",
          "font_size": 11,
          "text_color": [240, 240, 240],
          "background_color": [30, 30, 35],
          "border_color": [60, 60, 65],
          "border_radius": 3,
          "padding": [8, 6]
        },
        "groups": {
          "title_font_family": "Helvetica Neue",
          "title_font_size": 11,
          "title_color": [240, 240, 240],
          "content_margins": [10, 15, 10, 10],
          "margin_top": 10,
          "padding_top": 5
        }
      }
    }
  }
}
```

ConfigLoader Integration
-------------------------

1. Add Required Keys:
   All dialog config keys must be added to `ConfigLoader._get_required_keys()`:
   ```python
   'ui.dialogs.my_dialog.width',
   'ui.dialogs.my_dialog.height',
   'ui.dialogs.my_dialog.background_color',
   'ui.dialogs.my_dialog.buttons.width',
   'ui.dialogs.my_dialog.buttons.height',
   # ... etc
   ```

2. Validation:
   ConfigLoader will automatically validate all required keys exist
   Missing keys will cause application startup to fail with clear error messages

Implementation Checklist
------------------------

When creating a new dialog, ensure:

- [ ] All styling values come from config.json (no hardcoded values)
- [ ] Config keys added to ConfigLoader._get_required_keys()
- [ ] Dialog follows the standard structure (_load_config, _setup_ui, _apply_styling)
- [ ] Buttons use the standardized button styling pattern
- [ ] Labels, inputs, and groups use config-driven styling
- [ ] Dialog dimensions are configurable
- [ ] Background color is applied correctly
- [ ] Layout spacing and margins come from config
- [ ] Scroll areas use dynamic height calculation (if needed)
- [ ] ComboBox widgets use NoWheelComboBox (if needed)
- [ ] All fonts use `pt` units (not `px`)
- [ ] Button styling uses `background_offset` approach
- [ ] Code follows existing dialog patterns (use templates)

Template Dialogs
----------------

Use these existing dialogs as templates:

1. **ClassificationSettingsDialog** (`app/views/classification_settings_dialog.py`)
   - Reference implementation for button styling
   - Simple dialog structure
   - Group box usage

2. **EngineDialog** (`app/views/engine_dialog.py`)
   - Add Engine dialog
   - File selection controls
   - Special button styling (Browse button)

3. **EngineConfigurationDialog** (`app/views/engine_configuration_dialog.py`)
   - Complex dialog with tabs
   - Dynamic scroll area
   - Custom combobox implementation
   - Parameter validation integration

4. **ParameterValidationDialog** (in `engine_configuration_dialog.py`)
   - Custom validation dialog
   - Fixed-size non-resizable dialog
   - Severity-based styling

Common Pitfalls
---------------

1. **Hardcoded Values**: Never use magic numbers - always load from config
2. **Wrong Units**: Use `pt` for fonts, not `px`
3. **Fixed Heights**: Never use fixed heights for scroll areas - calculate dynamically
4. **Missing Config Keys**: Always add all config keys to ConfigLoader
5. **Inconsistent Styling**: Always use the same patterns as existing dialogs
6. **Background Color**: Apply dialog background color last to avoid overrides
7. **Button Offsets**: Use `background_offset` approach, not explicit RGB values
8. **ComboBox Wheel Events**: Use NoWheelComboBox to prevent accidental value changes

Testing
-------

When implementing a new dialog:

1. Verify all styling matches existing dialogs
2. Test with different config values
3. Verify dialog is non-resizable (if intended)
4. Test scroll areas with many items
5. Test button hover and pressed states
6. Verify all config keys are validated by ConfigLoader
7. Test on different screen resolutions
8. Verify no hardcoded values remain in code

Future Enhancements
-------------------

Potential improvements to the dialog system:

- Dialog theme support (light/dark)
- Custom dialog animations
- Dialog size persistence
- Accessibility improvements
- High DPI support enhancements


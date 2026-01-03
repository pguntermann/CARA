# CARA v2.5.0 - Cross-Platform UI Improvements and Bug Fixes

**Release Date:** 03.01.2026

This release introduces new features including the ability to copy game analysis and player stats to the clipboard, improves bulk analysis and multi-game import/paste operations, fixes Windows- and macOS-specific issues, enhances UI consistency across platforms, and includes updated documentation.

## Bug Fixes

- **Fixed Database Panel Row Selection Highlighting**: Fixed missing explicit row-highlighting in the database panel when selecting games on Windows systems
- **Windows Row Selection Fix**: Fixed potential issue where rows in the database panel may not be selectable on some Windows configurations
- **macOS Deduplication Dialog Layout**: Fixed the deduplication criteria layout on macOS

## UI Improvements

- **Annotation View Appearance**: Improved appearance of the Annotation view
- **Dialog Layout Standardization**: Further improvements to dialog layouts in order to improve unified cross-platform appearance, including consistent button spacing and layout margins
- **macOS UI Enhancements**: Several UI improvements for macOS

## New Features

- **Copy to Clipboard from Views**: Implemented ability to right-click and copy information from the Game Summary and Player Stats views to the clipboard
- **Bulk Analysis Improvements**: Improved bulk analysis thread utilization and implemented optional limiting
- **Multi-Game Import/Paste**: Improved behaviour when pasting or importing multiple games

## Configuration and Code Improvements

- **Configuration Cleanup**: Removed unused setting `ui.panels.main.board.pieces.miniature_pieces_path` from config.json
- **AI API Endpoints Configuration**: Moved hardcoded AI API endpoints to config.json for easier maintenance

## Documentation

- **Technical Documentation**: Updated and expanded the technical documentation
- **HTML Manual**: Performed some minor improvements to the HTML manual

---

# CARA v2.4.9 - Improved User Settings Persistence and Migration

**Release Date:** 30.12.2025

This minor release improves the handling and migration of user settings persistence and updates default configuration settings.

## User Settings Improvements

- **Enhanced User Settings Persistence**: Improved handling and migration of user settings files, ensuring better reliability when settings are stored in different locations (portable mode vs. user data directory)
- **Template File Support**: Added `user_settings.json.template` file, providing a reference template for default settings that is used when creating a new user settings file

## Configuration Changes

- **Debug Menu Disabled by Default**: The debug menu is now hidden by default in `config.json`. It can be enabled by setting `"show_debug_menu": true` in the configuration file

---

# CARA v2.4.8 - Quality of Life Improvements

**Release Date:** 28.12.2025

This release focuses on quality of life improvements with better visual defaults and minor enhancements.

## Visual Improvements

- **Positional Heatmap Tooltip Enhancements**: Improved tooltip appearance with better spacing, visual separators, enhanced title styling, and full piece names for better readability
- **PGN Pane Scrollbar Styling**: Applied consistent scrollbar styling to the PGN notation pane to match the rest of the application
- **Detail View Color Defaults**: Improved default background colors for detail views for better visual clarity

## User Experience Improvements

- **Engine Configuration Validation**: Added warning messages when users attempt to use engine-dependent features (game analysis, manual analysis, evaluation bar) without having an engine configured

## Code Cleanup

- **Removed Unused Debug Functions**: Cleaned up codebase by removing obsolete debug functions (trajectory debug and brilliant debug toggle) that were no longer needed

---

# CARA v2.4.7 - Visual Appearance Streamlining

**Release Date:** 27.12.2025

This release focuses on streamlining the application's visual appearance and fixing visual inconsistencies across dialogs and UI components.

## Visual Appearance Improvements

- **Unified Control Styling**: Implemented application-wide uniform and centralized styling for the following types of controls:
  - Scrollbars (QScrollArea, QTableWidget, QTableView)
  - Checkboxes (QCheckBox)
  - Comboboxes (QComboBox)
  - Radio Buttons (QRadioButton)
  - Buttons (QPushButton)
  - Text Inputs (QLineEdit)
  - Spin Boxes (QSpinBox, QDoubleSpinBox)
  - Date/Time Editors (QDateEdit, QTimeEdit, QDateTimeEdit)
  - Group Boxes (QGroupBox)
- **Styling Infrastructure**: All styling is centralized through StyleManager for consistent appearance across the entire application. Removed redundant dialog-specific styling definitions. Group boxes now use transparent backgrounds for better visual consistency.
- **Dialog Consistency**: Standardized spacing, margins, and dimensions across dialogs:
  - Fixed annotation preferences dialog spacing and dimensions for better compactness
  - Aligned group box title positioning and padding patterns
  - Reduced visual inconsistencies between different dialogs
- **Detail View Consistency**: Fixed and unified visual appearance issues between different detail views:
  - Standardized styling across all detail panel views (Summary, Metadata, Moves List, Annotations, Manual Analysis, AI Chat, Player Stats)
  - Aligned control appearance and spacing for consistent user experience
  - Fixed visual inconsistencies in fonts, colors, and spacing between views
- **Code Quality**: Improved maintainability by removing hardcoded styling values and consolidating configuration

## Technical Improvements

- **StyleManager Enhancements**: Added unified styling methods for multiple control types, ensuring consistent application of styles throughout the application
- **Configuration Cleanup**: Removed redundant styling property definitions from dialog configurations
- **Visual Refinements**: Adjusted dialog dimensions and spacing values to create a more cohesive user interface

---

# CARA v2.4.6 - macOS Compatibility Update

**Release Date:** 25.12.2025

This release focuses on macOS compatibility improvements, ensuring CARA works seamlessly on macOS systems.

## macOS Compatibility Improvements

- **Cross-platform UI fixes**: Resolved visual styling issues on macOS, including:
  - Fixed tab bar alignment (left-aligned tabs on macOS)
  - Corrected button and label text colors that were overridden by macOS system theme
  - Fixed white backgrounds in scroll areas, combobox dropdowns, and table headers
  - Applied DPI-aware font scaling for consistent text rendering across different display resolutions
  - Fixed splitter handle and tab scroll button colors
  - Resolved menu item visibility issues (About menu, move classification, etc.)
- **Dialog improvements**: Fixed sizing and styling issues in message boxes, confirmation dialogs, and various setup dialogs on macOS
- **Table view fixes**: Corrected white background in table corner buttons and header sections
- **Documentation updates**: Updated user manual with macOS installation instructions and keyboard shortcuts (showing both Windows and macOS equivalents)

## System Requirements Update

- **OS**: Windows 11 (tested), macOS Tahoe 26.2 (tested), Linux (may require some adjustments)

---

# CARA v2.4.5 - Initial Release

**Release Date:** 29.11.2025

Initial public release of CARA (Chess Analysis and Review Application), a desktop application for analyzing and reviewing chess games.

## Features

This release includes:

### Core Features

- **Automatic Game Analysis** with MultiPV engine support, move classification (Good, Inaccuracy, Mistake, Blunder, Brilliancy), and Centipawn Loss (CPL) calculation
- **44 Game Highlight Rules** automatically detecting tactical and positional patterns (pins, forks, skewers, batteries, tactical sequences, and more)
- **Interactive Chessboard** with move arrows, PV visualization, positional heatmap overlay, and extensive customization options
- **Game Summary** providing statistical analysis, phase-by-phase breakdowns, evaluation graphs, and key moments
- **Player Statistics** with aggregated metrics across multiple games, phase-specific analysis, and error pattern detection
- **Manual Analysis** with continuous MultiPV engine analysis and positional plan exploration
- **PGN Database Management** with multi-database support, powerful search, deduplication, and bulk operations
- **Online Import** from Lichess and Chess.com with filtering options
- **Free-form Annotations** with text, arrows, circles, and square highlighting
- **AI Summary** integration with OpenAI and Anthropic models for interactive game discussion
- **Moves List** with 32 available columns and flexible profile management

### Technical Details

- Built with PyQt6 using Model/View/Controller architecture
- Fully customizable UI through configuration files (no hardcoded values)
- Thread-safe background operations with progress tracking
- Extensible rule-based system for highlights and positional analysis
- Support for any UCI-compatible chess engine

## Getting Started

1. Install Python 3.8+ and dependencies: `pip install -r requirements.txt`
2. Configure a UCI-compatible chess engine (Stockfish recommended)
3. Launch: `python cara.py`

For detailed installation instructions and documentation, see the [README](README.md).

## Documentation

- **User Manual**: [Online version](https://pguntermann.github.io/CARA/manual.html) (also accessible from **Help → Open Manual** in the application)

## System Requirements

- **OS**: Windows 11 (tested), macOS Tahoe 26.2 (tested), Linux (may require some adjustments)
- **Python**: 3.8 or higher
- **Screen**: Minimum 1280×1024 pixels recommended
- **Hardware**: Modern multi-core processor recommended

## License

CARA is released under the **GNU General Public License version 3 (GPL-3.0)**.

---

**Copyright (C) 2025 Philipp Guntermann**

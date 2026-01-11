# CARA v2.5.4 - Game Analysis Improvements and UI Enhancements

**Release Date:** 11.01.2026

This release focuses on additional improvements and bug fixes of the bulk analysis function and the game analysis performance in general, along with some smaller UI enhancements and a new function to check for new versions.

## New Features

- **Version Check**: Added "Check for Updates..." menu item in the Help menu to check if a newer version of CARA is available

## Enhancements

### Game Analysis
- **Improved Analysis Performance**: Improved move processing logic to reduce additional analysis queries for determining before-the-move/best move values, by caching  analysis results from previous ply analysis, significantly improving performance when analyzing games
- **Enhanced Single Game Analysis Status Display**: Game analysis status now includes additional information: Average depth, Average selective depth and Move time parameter
- **UI Improvements**: Small improvements to engine settings dialog, disabling settings which are not applicable for a specific engine task, changed the movetime label in the Bulk Analysis dialog from "Time per Move" to "Move Time (ply)" to better reflect the meaning of the setting.

### User Interface
- **File Menu Reordering**: Minor reeorganization of menu items in the File menu for improved UX.
- **Menu Item Naming**: Renamed "Close All Databases" to "Close All PGN Databases" for consistency with other menu items

## Bug Fixes

- **Bulk Analysis Timeout Handling**: Fixed timeout handling during bulk analysis operations
- **Game Analysis Caching**: Fixed caching issue that could occur during game analysis

## Configuration

- **Config Cleanup**: Removed obsolete settings from config.json

## Documentation

- **Manual Updates**: Updated the HTML manual to reflect the new File menu structure and include the "Check for Updates" menu item.

---

# CARA v2.5.3 - PGN Handling Improvements and Performance Enhancements

**Release Date:** 09.01.2026

This release focuses on significant improvements to PGN file handling, including better encoding support, fixed-width formatting fixes, and character cleanup. It also includes performance enhancements through parallel processing for various database operations and several bug fixes.

## New Features

- **Close All Databases**: New menu option to close all open PGN databases at once
- **Parallel Game Parsing**: Parallel processing for game parsing when opening PGN database files, significantly reducing load times for large databases and when opening multiple files simultaneously
- **Parallel Bulk Operations**: Parallel processing for bulk tag replacement, bulk add/remove tags, and bulk cleaning operations
- **Parallel Player Statistics Processing**: Parallel processing for player statistics calculations, improving calculation speed

## Enhancements

### PGN Handling
- **Consistent PGN Export Formatting**: PGN files are now properly formatted on export according to config.json settings, with correct fixed-width line wrapping that works consistently across Windows and macOS
- **Improved Encoding Detection**: Enhanced loading of non-UTF-8 encoded PGN files with better character encoding detection and handling
- **PGN Display-Formatting Improvements**: Improved PGN formatting in the PGN pane, including better display of NAG (Numeric Annotation Glyph) move assessment symbols
- **Pattern-Based Game Boundary Detection**: Implemented faster pattern-based game boundary detection during loading of PGN files, significantly improving load times for large files
- **PGN Import Character Cleanup**: Automatically remove Unicode Private Use Area (PUA) characters from PGN files during import to prevent display issues with ChessBase font characters

## Bug Fixes
- **PGN Database Loading**: Fixed issue where some games were not correctly loaded from PGN databases
- **PGN Formatting and Removal**: Fixed several issues with PGN formatting and removal options
- **Game Sorting on Save**: Fixed reverse-order issue when saving games to a PGN file
- **Window Resizing**: Fixed window resizing issue with bulk replace dialog on Windows app bundle installs

## Documentation

- **Manual Updates**: Updated the Advanced section in the manual with comprehensive documentation for:
  - PGN import settings (strip PUA characters)
  - PGN display formatting customization (colors, NAGs as symbols/text, annotations)

---

# CARA v2.5.2 - Bulk Analysis Improvements and Enhanced Formula Support

**Release Date:** 07.01.2026

This release includes major improvements to the bulk analysis feature, enhanced custom formula support with phase-specific accuracy calculations, manual analysis miniature board scaling, and various bug fixes and UI improvements.

## New Features

- **Bulk Analysis Parallel Games Control**: Added a new spinbox in the bulk analysis dialog to allow users to set the number of parallel games, providing better control over resource utilization
- **Phase-Specific Accuracy Formulas**: Introduced separate customizable formulas for opening, middlegame, and endgame phases, allowing users to fine-tune accuracy calculations for each game phase independently
- **Manual Analysis Miniature Board Scaling**: Added optional scaling for the miniature board preview (1x, 1.25x, 1.5x, 1.75x, 2x) with persistent settings across sessions

## Enhancements

### Bulk Analysis
- **UI Layout Improvements**: Reorganized bulk analysis dialog layout for better usability
- **Dynamic UI Control**: Parallel games spinbox automatically limits to the number of selected games when "Selected games only" is enabled
- **Architecture Refactoring**: Moved bulk analysis coordination logic to a dedicated `BulkAnalysisController`, improving code organization and maintainability
- **Consistent Styling**: All spinboxes now use the same fixed width from configuration

### Custom Formula Support
- **Extended Variable Access**: 
  - Phase-specific formulas have access to phase-specific move counts and CPLs (`opening_moves`, `middlegame_moves`, `endgame_moves`, `average_cpl_opening`, `average_cpl_middlegame`, `average_cpl_endgame`)
  - All formulas have access to overall game statistics with `_overall` suffix variables (e.g., `blunders_overall`, `total_moves_overall`)
- **Additional Functions**: Made `abs()`, `int()`, and `not()` functions available in all formulas
- **Removed Hardcoded Clamping**: Formulas now handle their own clamping using `min()` and `max()`, giving users full control
- **Code Refactoring**: Reduced duplication in formula evaluation logic and improved service consistency

## Bug Fixes

- **Windows Console Window Suppression**: Fixed issue where engine processes would open an empty command line window on Windows app bundles (Issue #25)
- **Manual Analysis PV Line Removal**: Fixed crash when using "Remove PV Line" menu item by implementing proper controller methods (Issue #26)
- **Status Bar Progress Percentage**: Fixed black text color issue on Windows and restored percentage display to the right of the progress bar
- **Bulk Tag Complete Dialog**: Fixed black text color for dialog title on Windows
- **Status Panel Text Truncation**: Fixed issue where status panel would grow instead of truncating text when window is too small

## Documentation

- **Updated User Manual**: The HTML manual (section 7.8) has been updated to reflect the extended formula capabilities, including:
  - Phase-specific accuracy formulas with their configuration and available variables
  - New variables available for all formulas (phase-specific CPLs, move counts, and `_overall` suffix variables)
  - Additional functions (`abs()`, `int()`, `not()`) available in all formulas
  - Updated examples demonstrating the use of new variables and functions

---

# CARA v2.5.1 - Engine Service Improvements and Customizable Formulas

**Release Date:** 05.01.2026

This release includes significant improvements to the UCI layer and engine services for better performance and responsiveness, introduces customizable ELO and accuracy calculation formulas, and includes various bug fixes and documentation updates.

## New Features

- **Customizable ELO and Accuracy Formulas**: Users can now customize the formulas used to calculate estimated ELO ratings and accuracy percentages through `config.json`. The formulas support a wide range of variables including move statistics, CPL metrics, error rates, and game results. See the user manual (section 7.8) for details on available variables, functions, and examples.

## Engine and Analysis Service Improvements

- **UCI Layer Refactoring**: Improved and simplified UCI layer implementation for better reliability and maintainability
- **Manual Analysis Service**: 
  - Removed blocking waits during shutdown to improve UI responsiveness
  - Removed optional `psutil` dependency handling for simpler deployment
- **Evaluation Service**: Removed blocking waits during shutdown for better UI responsiveness
- **Bulk Analysis Service**:
  - Improved thread distribution and utilization with dynamic scaling to use all available CPU cores
  - Enhanced cleanup to ensure proper engine thread termination after analysis completion
  - Improved status reporting with dynamic thread information that reflects actual active threads
  - Better cancellation status handling with clear user feedback

## Bug Fixes

- **Bulk Analysis Cleanup**: Fixed issue where engine processes were not always terminated after bulk analysis completion
- **UI Responsiveness**: Fixed UI unresponsiveness during manual analysis and evaluation service shutdown

## Documentation

- **Formula Customization Guide**: Added documentation section (7.8) in the user manual covering customizable ELO and accuracy formulas
- **Engine Implementation Documentation**: Updated technical documentation to reflect UCI layer and engine service improvements
- **Dependency Documentation**: Updated README, THIRD_PARTY_LICENSES, and manual to include `asteval` dependency

---

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

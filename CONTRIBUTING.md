# Contributing to CARA

Thank you for your interest in contributing to CARA! 

This document provides guidelines and information for contributors.

## Project Architecture

CARA follows **PyQt's Model/View architecture with Controllers** (not strict MVC):

- **Models**: Qt data models (QAbstractItemModel subclasses) that hold application data
  - Models emit signals when data changes
  - Models are independent of UI and can be tested in isolation

- **Views**: UI components (widgets, dialogs, panels) that display data
  - Views observe models and automatically update when model data changes
  - Views never directly modify model data
  - Views trigger controller methods in response to user interactions

- **Controllers**: Orchestration layers that coordinate business logic
  - Controllers handle user actions from views
  - Controllers update models or call services
  - Controllers coordinate between multiple services and models
  - Controllers contain no UI logic

- **Services**: Backend logic, APIs, and utilities
  - Services handle computation, I/O, external APIs
  - Services are independent of UI and models
  - Services can be tested in isolation

Views observe models via Qt's signal/slot mechanism, and controllers handle user actions to update models or call services.

## Code Style

- Follow **PEP 8** conventions:
  - Use `snake_case` for functions and variables
  - Use `PascalCase` for classes
  - Use `UPPER_SNAKE_CASE` for constants

- Add type hints where appropriate

- Include docstrings for public functions and classes

## UI/Styling

- **Centralized styling**: Use `StyleManager` for recurring UI elements (scrollbars, checkboxes, etc.)
  - Store reusable style values in `ui.styles.*` in `config.json`
  - Remove legacy dialog-specific style keys when centralizing common elements

- **Dialog-specific styling**: Many dialogs still use inline `setStyleSheet()` calls — this is acceptable for dialog-specific styling that doesn't need to be shared

- **Configuration-driven**: All styling values must come from `config.json` (no hardcoded colors, sizes, or dimensions)

## Configuration

- Add new configuration keys to both `app/config/config.json` and `app/config/config_loader.py`
- Remove obsolete keys when refactoring to avoid leaving legacy definitions
- Validate JSON syntax to ensure the configuration file is valid

## Documentation

- **Manual updates**: When updating the user manual:
  1. Edit `app/resources/manual/index.html` first
  2. Run `app/resources/manual/inline_html.py` to generate the inlined version
  3. Copy the generated `app/resources/manual/manual-inline.html` to `manual.html` in the application root

- Update relevant documentation in the `doc/` directory for architectural changes

- Keep inline comments clear and concise

## Questions?

If you have questions about contributing, please send an email to pguntermann@me.com.


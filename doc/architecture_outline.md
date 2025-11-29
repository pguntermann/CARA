CARA Application Architecture

1. Goals

• PyQt's Model/View architecture with Controllers and signal observation patterns
• Modular UI components
• Scalable backend logic
• Centralized, strict configuration
• Global keyboard shortcuts
• Clean orchestration and testability
• Single Responsibility Principles
• SOLID coding standards

2. Architecture Pattern

CARA follows PyQt's Model/View architecture with additional separation of business logic using Controllers:

• Models: Qt data models (QAbstractItemModel subclasses) that hold application data
  - Models emit signals when data changes
  - Views observe models through Qt's signal/slot mechanism
  - Models are independent of UI and can be tested in isolation

• Views: UI components (widgets, dialogs, panels) that display data
  - Views observe models and automatically update when model data changes
  - Views never directly modify model data
  - Views trigger controller methods in response to user interactions
  - All UI styling comes from config.json (no hardcoded values)

• Controllers: Orchestration layers that coordinate business logic
  - Controllers handle user actions from views
  - Controllers update models or call services
  - Controllers coordinate between multiple services and models
  - Controllers contain no UI logic

• Services: Backend logic, APIs, and utilities
  - Services handle computation, I/O, external APIs
  - Services are independent of UI and models
  - Services can be tested in isolation

3. 📁 Project Structure

app_root/ 
├── cara.py                         # Entry point 
├── app/ 
│   ├── __init__.py 
│   ├── main_window.py              # Top-level window orchestration 
│   ├── config/                     # Strict configuration system 
│   │   ├── config.json             # Fonts, sizes, colors, dimensions (2,300+ lines)
│   │   └── config_loader.py        # Loads and validates config 
│   ├── views/                      # UI components (widgets, dialogs, panels)
│   │   ├── main_panel.py           # Main chessboard panel
│   │   ├── detail_panel.py         # Detail panel with tabs
│   │   ├── database_panel.py       # Database management panel
│   │   ├── status_panel.py          # Status bar panel
│   │   ├── chessboard_widget.py    # Chessboard widget
│   │   └── [35+ more view files]   # Dialogs, detail views, widgets
│   ├── models/                     # Qt data models (QAbstractItemModel subclasses)
│   │   ├── board_model.py          # Chess board state
│   │   ├── game_model.py           # Game data
│   │   ├── database_model.py       # Database/game collection
│   │   ├── moveslist_model.py      # Moves list table data
│   │   └── [8+ more model files]   # Other data models
│   ├── controllers/                # Logic orchestration 
│   │   ├── app_controller.py       # Central logic hub
│   │   ├── game_controller.py      # Game navigation and state
│   │   ├── board_controller.py     # Board position management
│   │   ├── database_controller.py  # Database operations
│   │   └── [11+ more controller files] # Feature-specific controllers
│   ├── services/                    # Backend logic, APIs, utilities
│   │   ├── game_analysis_engine_service.py  # Game analysis
│   │   ├── evaluation_engine_service.py     # Position evaluation
│   │   ├── manual_analysis_engine_service.py # Manual analysis
│   │   ├── uci_communication_service.py     # UCI protocol
│   │   ├── pgn_service.py          # PGN parsing/formatting
│   │   ├── database_search_service.py # Game search
│   │   ├── game_highlights/        # Highlight detection rules
│   │   │   └── rules/              # 44 highlight detection rules
│   │   ├── positional_heatmap/     # Positional analysis rules
│   │   │   └── rules/              # 9 positional evaluation rules
│   │   └── [30+ more service files] # Other services
│   ├── input/                      # Global input handling
│   │   └── shortcut_manager.py    # Registers and routes global key commands
│   ├── resources/                  # Icons, stylesheets, manual
│   │   ├── icons/
│   │   ├── chesspieces/
│   │   ├── manual/
│   │   └── [other resources]
│   └── utils/                      # Reusable helpers
│       ├── material_tracker.py
│       └── rule_explanation_formatter.py
└── tests/                          # Unit and integration tests
    ├── highlight_rules/            # Highlight rule tests
    └── [test files]

4. ⚙️ Configuration System

• All fonts, sizes, colors, and UI settings are defined in app/config/config.json
• ConfigLoader loads and validates the config on startup
• Strict validation: missing required keys cause immediate app termination
• No fallback logic: all values must be present in config
• Access settings via config.get("ui", {}).get("panels", {}), etc.
• Configuration is hierarchical and well-organized
• All UI styling (fonts, colors, dimensions) comes from config - zero hardcoded values

5. ⌨️ Global Key Command Handling

• ShortcutManager registers global keyboard shortcuts
• Key commands work regardless of widget focus
• Shortcuts are routed to appropriate controllers
• Example: Ctrl+S always triggers save, arrow keys always navigate moves
• Shortcuts are defined in config.json and loaded by ShortcutManager

6. 🔁 Code Flow & Call Hierarchy

1. Startup
   • cara.py loads config via ConfigLoader
   • ConfigLoader validates all required keys (fails fast if missing)
   • Initializes MainWindow with injected config
   • MainWindow creates views, models, and controllers
   • Controllers are initialized with models and services
   • Views are initialized with controllers and models
   • Views connect to model signals for automatic updates
   • Registers global shortcuts via ShortcutManager

2. UI Interaction
   • User interacts with a View (clicks button, types text, etc.)
   • View triggers a Controller method
   • Controller updates a Model or calls a Service
   • Model emits signals when data changes
   • Views automatically update via signal/slot connections

3. Backend Logic
   • Services handle computation, I/O, external APIs
   • Services access config when needed
   • Services emit signals or return results to controllers
   • Controllers update models based on service results

4. Styling
   • Views and widgets pull fonts, sizes, and colors from config
   • No hardcoded UI values anywhere in the codebase
   • All styling is centralized in config.json
   • Configuration-driven styling ensures consistency

5. Global Input
   • ShortcutManager listens for key events globally
   • Routes them to controller logic regardless of focus
   • Works across all views and dialogs

6. Threading
   • Long-running operations (engine analysis) run in QThread instances
   • Threads communicate with UI via signals/slots
   • UI remains responsive during background operations
   • Each engine operation has its own thread

7. 🧠 Design Principles

• PyQt Model/View with Controllers:
  - Models hold data and emit signals
  - Views display data and observe models via signals
  - Controllers orchestrate business logic
  - Services provide backend functionality

• Qt-native patterns:
  - Uses QAbstractItemModel for data models
  - Uses signals/slots for communication
  - Uses QThread for async operations
  - Follows Qt's recommended patterns

• Modular architecture:
  - Each component has a single responsibility
  - Clear separation between views, models, controllers, services
  - Components are loosely coupled

• Testable design:
  - Logic is decoupled from UI
  - Models and services can be tested in isolation
  - Controllers can be tested with mock services

• Strict Configuration:
  - UI consistency via enforced settings
  - No hardcoded values
  - All styling configurable
  - Validation on startup

• Global Input:
  - Consistent behavior across the app
  - Keyboard shortcuts work everywhere
  - Centralized shortcut management

8. Signal/Slot Communication Pattern

The application uses Qt's signal/slot mechanism extensively:

• Model → View: Models emit signals when data changes, views connect to these signals
  - Example: DatabaseModel emits game_selected signal, DatabasePanel connects and updates UI

• View → Controller: Views call controller methods directly
  - Example: User clicks button, view calls controller.handle_button_click()

• Controller → Model: Controllers call model methods to update data
  - Example: Controller calls model.set_position(fen) to update board

• Controller → Service: Controllers call service methods for business logic
  - Example: Controller calls service.analyze_game(game) to start analysis

• Service → Controller: Services emit signals or return results
  - Example: AnalysisService emits analysis_complete signal, Controller connects and updates model

• Thread → UI: Worker threads emit signals to communicate with UI thread
  - Example: EngineThread emits evaluation_updated signal, Controller connects and updates model

9. Threading Architecture

• Engine operations run in separate QThread instances
  - EvaluationEngineThread: Continuous position evaluation
  - GameAnalysisEngineThread: Batch game analysis
  - ManualAnalysisEngineThread: Manual analysis with MultiPV

• Thread communication via signals/slots
  - Threads emit signals with results
  - UI thread connects to these signals
  - Qt automatically handles thread-safe signal delivery

• Thread lifecycle management
  - Threads are created when needed
  - Threads are properly cleaned up on completion
  - Engine processes are managed within threads

10. Error Handling

• Centralized error collection system
  - ErrorHandler collects and reports errors
  - User-facing error messages
  - Developer logging for debugging

• Error propagation
  - Services report errors via signals or exceptions
  - Controllers handle errors and update UI
  - Views display error messages to users

• Validation
  - ConfigLoader validates configuration on startup
  - Services validate inputs before processing
  - Models validate data before storing

11. Best Practices

• No hardcoded values: All UI styling from config.json
• Signal-based communication: Use signals/slots, not direct method calls for model updates
• Single responsibility: Each class has one clear purpose
• Dependency injection: Pass dependencies via constructors
• Error handling: Always handle errors gracefully
• Thread safety: Use signals/slots for thread communication
• Configuration-driven: All behavior configurable via config.json


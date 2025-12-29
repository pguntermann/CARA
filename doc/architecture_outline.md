# CARA Application Architecture

## Goals

- PyQt's Model/View architecture with Controllers and signal observation patterns
- Modular UI components
- Scalable backend logic
- Centralized, strict configuration
- Clean orchestration and testability
- Single Responsibility Principles
- SOLID coding standards

## Architecture Pattern

CARA follows PyQt's Model/View architecture with additional separation of business logic using Controllers:

- **Models**: Qt data models (QAbstractItemModel subclasses) that hold application data
  - Models emit signals when data changes
  - Views observe models through Qt's signal/slot mechanism
  - Models are independent of UI and can be tested in isolation

- **Views**: UI components (widgets, dialogs, panels) that display data
  - Views observe models and automatically update when model data changes
  - Views never directly modify model data
  - Views trigger controller methods in response to user interactions
  - All UI styling comes from config.json (no hardcoded values)

- **Controllers**: Orchestration layers that coordinate business logic
  - Controllers handle user actions from views
  - Controllers update models or call services
  - Controllers coordinate between multiple services and models
  - Controllers contain no UI logic

- **Services**: Backend logic, APIs, and utilities
  - Services handle computation, I/O, external APIs
  - Services are independent of UI and models
  - Services can be tested in isolation

## Project Structure

```
app/
├── main_window.py              # Top-level window orchestration
├── config/                     # Configuration system
│   ├── config.json             # All UI styling and settings
│   └── config_loader.py         # Loads and validates config
├── views/                      # UI components (display only)
│   └── [panels, widgets, dialogs]
├── models/                     # Qt data models (QAbstractItemModel)
│   └── [data models for board, game, database, etc.]
├── controllers/                # Business logic orchestration
│   └── [feature-specific controllers]
├── services/                   # Backend logic and APIs
│   ├── [engine services, PGN, database, etc.]
│   ├── game_highlights/rules/  # Highlight detection rules
│   └── positional_heatmap/rules/  # Positional analysis rules
├── resources/                  # Static resources (icons, manual)
└── utils/                      # Reusable helper utilities
```

## Configuration System

- All fonts, sizes, colors, and UI settings are defined in `app/config/config.json`
- ConfigLoader loads and validates the config on startup
- Strict validation: missing required keys cause immediate app termination
- No fallback logic: all values must be present in config
- Access settings via `config.get("ui", {}).get("panels", {})`, etc.
- Configuration is hierarchical and well-organized
- All UI styling (fonts, colors, dimensions) comes from config - zero hardcoded values

## Application Lifecycle

### Startup

- `cara.py` loads config via ConfigLoader
- ConfigLoader validates all required keys (fails fast if missing)
- Initializes MainWindow with injected config
- MainWindow creates AppController (central hub)
- AppController creates all feature controllers and their models
- Controllers are initialized with models and services
- MainWindow creates views and passes controllers/models to them
- Views connect to model signals for automatic updates

## Runtime Flow

### User Interaction

- User interacts with a View (clicks button, types text, etc.)
- View triggers a Controller method
- Controller updates a Model or calls a Service
- Model emits signals when data changes
- Views automatically update via signal/slot connections

### Backend Processing

- Services handle computation, I/O, external APIs
- Services access config when needed
- Services emit signals or return results to controllers
- Controllers update models based on service results

### Threading

- Long-running operations (engine analysis) run in QThread instances
- Threads communicate with UI via signals/slots
- UI remains responsive during background operations
- Each engine operation has its own thread

## Design Principles

- **PyQt Model/View with Controllers**:
  - Models hold data and emit signals
  - Views display data and observe models via signals
  - Controllers orchestrate business logic
  - Services provide backend functionality

- **Qt-native patterns**:
  - Uses QAbstractItemModel for data models
  - Uses signals/slots for communication
  - Uses QThread for async operations
  - Follows Qt's recommended patterns

- **Modular architecture**:
  - Each component has a single responsibility
  - Clear separation between views, models, controllers, services
  - Components are loosely coupled

- **Testable design**:
  - Logic is decoupled from UI
  - Models and services can be tested in isolation
  - Controllers can be tested with mock services

- **Strict Configuration**:
  - UI consistency via enforced settings
  - No hardcoded values
  - All styling configurable
  - Validation on startup

## Signal/Slot Communication Pattern

The application uses Qt's signal/slot mechanism extensively:

- **Model → View**: Models emit signals when data changes, views connect to these signals
  - Example: DatabaseModel emits `game_selected` signal, DatabasePanel connects and updates UI

- **View → Controller**: Views call controller methods directly
  - Example: User clicks button, view calls `controller.handle_button_click()`

- **Controller → Model**: Controllers call model methods to update data
  - Example: Controller calls `model.set_position(fen)` to update board

- **Controller → Service**: Controllers call service methods for business logic
  - Example: Controller calls `service.analyze_game(game)` to start analysis

- **Service → Controller**: Services emit signals or return results
  - Example: AnalysisService emits `analysis_complete` signal, Controller connects and updates model

- **Thread → UI**: Worker threads emit signals to communicate with UI thread
  - Example: EngineThread emits `evaluation_updated` signal, Controller connects and updates model

## Threading Architecture

- **Engine operations run in separate QThread instances**
  - EvaluationEngineThread: Continuous position evaluation
  - GameAnalysisEngineThread: Batch game analysis
  - ManualAnalysisEngineThread: Manual analysis with MultiPV

- **Thread communication via signals/slots**
  - Threads emit signals with results
  - UI thread connects to these signals
  - Qt automatically handles thread-safe signal delivery

- **Thread lifecycle management**
  - Threads are created when needed
  - Threads are properly cleaned up on completion
  - Engine processes are managed within threads

## Error Handling

- **Fatal error handling**
  - ErrorHandler handles fatal errors by logging to stderr and terminating the application
  - Global exception handler catches uncaught exceptions during execution
  - Used primarily for startup failures and critical errors

- **Error propagation**
  - Services report errors via signals or exceptions
  - Controllers handle errors and update UI
  - Views display error messages to users

- **Validation**
  - ConfigLoader validates configuration on startup
  - Services validate inputs before processing
  - Models validate data before storing

## Implementation Guidelines

- **Signal-based communication**: Use signals/slots for model updates, not direct method calls
- **Dependency injection**: Pass dependencies (models, services, config) via constructors
- **Thread safety**: Use signals/slots for all thread-to-UI communication
- **Error handling**: Services report errors via signals or exceptions; controllers handle and update UI

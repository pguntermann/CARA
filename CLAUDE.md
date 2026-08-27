# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

CARA is a PyQt6-based desktop chess analysis application. Start it with:

```bash
python cara.py
```

On macOS, you may need `python3` instead. Requires Python 3.8+ and a UCI-compatible chess engine (Stockfish, Berserk, etc.) configured via the Engines menu.

**PyQt6 / PyQt6-Qt6 version pinning.** `requirements.txt` pins both `PyQt6` and `PyQt6-Qt6` to the same exact version. They must match — a mismatch produces a misleading error (`Could not find the Qt platform plugin "cocoa"`) that looks like a missing file, broken signature, or corrupt install, none of which is the actual cause. A plain `pip install -r requirements.txt` on a clean venv should no longer produce drift.

If you hit this error despite installing from `requirements.txt` (e.g. after manually upgrading one package), diagnose with:

```bash
pip show PyQt6 PyQt6-Qt6 | grep -E "Name|Version"
```

If the versions don't match, reinstall whichever one is ahead to match the other:

```bash
pip install --force-reinstall --no-deps PyQt6-Qt6==<matching version>
```

PyPI doesn't always have every point-release pair available for both packages — run `pip install PyQt6-Qt6==` (no version, to list what's available) if the exact match isn't found.

## Running Tests

Tests use Python's standard `unittest` framework, living in `tests/` as `test_*.py`.

```bash
# All tests
python -m unittest discover -s tests -p "test_*.py" -v

# A specific subdirectory
python -m unittest discover -s tests/services -p "test_*.py" -v

# A single file, class, or method — same dotted-path pattern
python -m unittest tests.services.test_pgn_service -v
python -m unittest tests.services.test_pgn_service.TestPgnServiceNormalizeMovesFixedWidth -v
```

**Note**: Tests in `tests/opening_integrity/` require local chess engine installations — local only, not run in CI.

## Building

PyInstaller specs exist for macOS, Windows, and Linux (`CARA_macos.spec`, etc. — each requires its target OS to build).

```bash
pip install pyinstaller==6.17.0
pyinstaller CARA_macos.spec  # or _windows / _linux
```

Output bundles land in `dist/`.

## Dependencies

See `requirements.txt` for the full, versioned list. One choice worth knowing the reasoning behind: **asteval**, not raw `eval()`, is used for evaluating user-defined expressions — a deliberate safety choice, not an oversight.

```bash
pip install -r requirements.txt
```

## Architecture

CARA follows **PyQt's Model/View pattern with Controllers**, with signal/slot communication throughout.

1. **Models** (`app/models/`) — Qt data models holding application state. Table models (DatabaseModel, MovesListModel, MetadataModel) inherit `QAbstractTableModel`; state models (BoardModel, GameModel, EvaluationModel) inherit `QObject` and emit custom signals. UI-independent and testable in isolation.

2. **Views** (`app/views/`) — UI components. Display data by observing model signals; never modify model data directly — go through a controller instead. All styling comes from `app/config/config.json` (see Configuration below).

3. **Controllers** (`app/controllers/`) — Handle user interactions from views, update models, call services. No UI logic. Entry point: `AppController` wires all feature controllers together.

4. **Services** (`app/services/`, ~129 files) — Computation, file I/O, engine management, analysis algorithms. UI-independent and testable in isolation.

5. **Configuration** (`app/config/`) — see Configuration System below.

6. **Utils** (`app/utils/`) — Font, path, styling, and tooltip helpers.

### Signal/Slot Communication

- Model → View: models emit on data change, views observe and update automatically.
- View → Controller: views call controller methods on user interaction.
- Controller → Model / Controller → Service: controllers update models and invoke service logic.
- Thread → UI: worker threads emit signals for thread-safe UI updates.

## Configuration System

Three files loaded at startup: `app/config/config.json` (UI styling/dimensions/colors/fonts), `user_settings.json` (user preferences), `engine_parameters.json` (UCI engine parameters).

**Config is split by kind, not just by file.** `config.json` holds *behavioral* config; the `style_*.config.json` theme files hold *style/layout* config. ConfigLoader merges both into memory at startup — treat them as one logical config in code, but a new key's *home file* depends on whether it's behavior or presentation, not convenience.

**Convention for new config keys (confirmed by maintainer):** add every new key to ConfigLoader so a missing one fails loudly at startup. Whether the corresponding `.get()` call in code also carries an inline default doesn't matter either way — the loader is the actual gate, `.get()` defaults are just belt-and-suspenders. (The strict-validation-everywhere language elsewhere in this doc is aspirational, not fully true yet — it's known tech debt from a mid-project design shift, with a config-loader refactor planned but not yet done. Don't be surprised by `.get(..., default)` patterns in the existing code; follow the "always register in ConfigLoader" rule for anything new regardless.)

Style config files (`style_default.config.json`, `style_light.config.json`, `style_scholar.config.json`) define reusable constants with a `$_` prefix, referenced elsewhere via `{"$ref": "$_CONSTANT_NAME"}`. `config.json`'s `default_style_config` key selects the active style file.

Key sections: `ui.window`, `ui.panels`, `ui.dialogs.*`, `ui.styles`, `ui.colors`, `ui.fonts`, `version`.

### Configuration Access

```python
bg_color = config.get("ui", {}).get("dialogs", {}).get("my_dialog", {}).get("background_color", [40, 40, 45])
```

**Note:** the docs describe ConfigLoader as strictly validating at startup, but the pattern above uses `.get()` with an inline default — that's not a contradiction to resolve, it's the current transitional state (see Configuration System above). For new config-reading code: register the key in ConfigLoader regardless of whether you also add a `.get()` default.

### Dialog Implementation

Dialogs follow a standard constructor pattern: load config → build UI → apply styling via `StyleManager` (`app/views/style/style_manager.py`). Use `scale_font_size()` and `resolve_font_family()` from `app.utils.font_utils` for font values from config. See `app/views/dialogs/bulk_operations_dialog.py` as the living template rather than a static skeleton here.

## Threading

- **QThread** for I/O-bound engine operations (EvaluationEngineThread, GameAnalysisEngineThread, ManualAnalysisEngineThread) — Qt handles thread safety via signals/slots.
- **ProcessPoolExecutor** for CPU-bound work (player statistics, PGN parsing, multi-file opening), using `max(1, os.cpu_count() - 2)` workers to keep the UI responsive.

## Key Subsystems

### Game Analysis Pipeline
GameAnalysisController → GameAnalysisEngineService (runs engine per move, MultiPV) → MoveClassificationService (Good/Inaccuracy/Mistake/Blunder/Brilliancy by Centipawn Loss) → MovesListModel → GameSummaryService (aggregated statistics, highlights, top moves).

### Game Highlights
Rule-based detection of 44+ tactical/positional patterns, one rule per file in `app/services/game_highlights/rules/`, each implementing a common interface. Tests: one file per rule in `tests/highlight_rules/`. Extend by adding a new rule file.

### Positional Heatmap
Same extensible rule-based architecture as Game Highlights, in `app/services/positional_heatmap/rules/` — weak squares, passed pawns, outposts, piece activity, king safety.

### Player Statistics
Per-player aggregation: accuracy/progression charts, opening/endgame summaries, significant moves, activity heatmap, and **error pattern hints with pattern detection** — worth a direct look before building anything that tracks recurring mistakes, since it may already do part of that job.

## Naming Conventions

- Controllers: `*_controller.py` / `*Controller`
- Models: `*_model.py` / `*Model`
- Services: `*_service.py` / `*Service`
- Views: `*_view.py` or `*_panel.py` / `*View` or `*Panel`
- Dialogs: `*_dialog.py` / `*Dialog`
- Tests: `test_*.py` / `Test*`
- Signals: `<noun>_changed` (e.g. `position_changed`, `evaluation_updated`)
- Config keys: dotted notation (`"ui.dialogs.my_dialog.width"`)

## Documentation

Architecture and feature docs live in `doc/` — `architecture_outline.md` for high-level design/threading/error handling, `dialog_style_guide.md` for the dialog pattern, plus feature-specific docs (game analysis, highlights, heatmap, player stats, annotations). Check there before re-deriving something already documented.

## Git Workflow

- **Never commit directly to `master`.** Always work on a feature branch.
- Prefer small, focused commits (one logical change each) over large batched ones — easier to review, easier to revert if something's wrong.

## CI/CD

`.github/workflows/tests.yml` runs on Python 3.12 with `QT_QPA_PLATFORM=offscreen` for headless Qt testing, on push to `master`/`development` and on PRs. Manual-trigger build workflows (`build-appbundles.yml`, `build-linux-appbundles.yml`) produce macOS/Windows/Linux bundles as artifacts.

## Version and Release

Version lives in `app/config/config.json` under `"version"` — build scripts read it for bundle naming. Release notes in `RELEASE_NOTES.md`; pre-built bundles on the GitHub Releases page.

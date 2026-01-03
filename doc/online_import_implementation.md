# CARA - Online Import Implementation

## Overview

The Online Import feature allows users to import chess games from online platforms (Lichess and Chess.com) by username. The system fetches games via platform APIs, handles rate limiting, supports date filtering, and provides progress reporting during import. Imported games are added to the active database as PGN strings.

## Architecture

The online import system follows a **Service-Controller** pattern with **stateless API communication**:

### Component Responsibilities

**OnlineImportService** (`app/services/online_import_service.py`):
- Stateless service for importing games from online platforms
- Handles Lichess API communication (NDJSON stream format)
- Handles Chess.com API communication (monthly archive format)
- Parses date filters and applies them to game lists
- Provides progress callbacks for UI updates
- Handles rate limiting and error responses
- Returns PGN strings for imported games

**DatabaseController** (`app/controllers/database_controller.py`):
- Orchestrates import operations
- Calls `OnlineImportService` methods
- Provides progress callbacks that update UI
- Parses imported PGN strings and adds games to database
- Handles import errors and displays messages

### Component Interactions

**Lichess Import Flow**:
1. User provides username and optional filters (date range, game type, max games)
2. Controller calls `OnlineImportService.import_lichess_games()`
3. Service builds API request with parameters
4. Service makes HTTP GET request to Lichess API endpoint
5. Service streams NDJSON response (newline-delimited JSON)
6. Service parses each line as JSON and extracts PGN field
7. Service calls progress callback periodically
8. Service returns list of PGN strings
9. Controller parses each PGN and adds games to database
10. Controller displays success/error message

**Chess.com Import Flow**:
1. User provides username and optional filters (date range, max games)
2. Controller calls `OnlineImportService.import_chesscom_games()`
3. Service fetches archive list for user
4. Service filters archives by date range if specified
5. Service iterates through archives
6. For each archive, service fetches games JSON
7. Service filters games by date if specified
8. Service extracts PGN from each game
9. Service calls progress callback frequently for responsiveness
10. Service returns list of PGN strings
11. Controller parses each PGN and adds games to database
12. Controller displays success/error message

**Progress Reporting Flow**:
1. Service calls progress callback with status message and percentage
2. Controller's callback updates progress service
3. Progress service displays status bar and progress bar
4. Controller calls `QApplication.processEvents()` to keep UI responsive
5. Progress updates occur frequently (every 10-25 games) for large imports

## API Integration

### Lichess API

**Endpoint**: `https://lichess.org/api/games/user/{username}`

**Request Format**:
- Method: GET
- Headers: User-Agent (required), Accept
- Parameters:
  - `max`: Maximum number of games (default: all)
  - `since`: Timestamp in milliseconds (optional)
  - `until`: Timestamp in milliseconds (optional)
  - `perfType`: Game type filter (e.g., "blitz", "rapid", "classical")
  - `pgnInJson`: true (get JSON format with PGN field)
  - `tags`: true (include PGN tags)
  - `clocks`: true (include clock times)
  - `evals`: false (exclude engine evaluations)
  - `opening`: true (include opening information)
  - `moves`: true (include move notation)

**Response Format**:
- Content-Type: `application/x-ndjson` (newline-delimited JSON)
- Each line is a JSON object with `pgn` field
- Streamed response (can be large)

**Rate Limiting**:
- 200 requests per 10 seconds
- Service includes User-Agent header to prevent 403 errors

### Chess.com API

**Endpoint Structure**:
1. Archive list: `https://api.chess.com/pub/player/{username}/games/archives`
2. Monthly archive: `https://api.chess.com/pub/player/{username}/games/{YYYY}/{MM}`

**Request Format**:
- Method: GET
- Headers: User-Agent (required), Accept
- No query parameters (date filtering done client-side)

**Response Format**:
- Archive list: JSON with `archives` array of URLs
- Monthly archive: JSON with `games` array of game objects
- Each game object has `pgn` field

**Rate Limiting**:
- Informal limit: ~10,000 requests per day
- Service includes User-Agent header to prevent 403 errors

## Date Filtering

### Lichess Date Filtering

- Uses `since` and `until` parameters in API request
- Timestamps in milliseconds since epoch
- Applied server-side (efficient)

### Chess.com Date Filtering

- Archive filtering: Filters monthly archives by date range
- Game filtering: Extracts Date tag from PGN and filters client-side
- Date parsing: Handles multiple PGN date formats:
  - `YYYY.MM.DD` (most common)
  - `DD.MM.YYYY` (European format)
  - `YYYY.DD.MM` (alternative format)
  - `YYYY.MM` (year and month)
  - `YYYY` (year only)

Date parsing uses auto-detection based on value ranges to handle different formats.

## Error Handling

### API Errors

**404 Not Found**:
- User not found on platform
- Returns user-friendly error message

**403 Forbidden**:
- Rate limiting or API restrictions
- May indicate missing User-Agent header
- Returns error message with guidance

**429 Too Many Requests**:
- Rate limit exceeded
- Returns error message suggesting retry later

**Network Errors**:
- Connection timeouts, network failures
- Returns error message with details

### Data Errors

**Invalid JSON**:
- Skips invalid lines in NDJSON stream
- Continues processing remaining games

**Missing PGN**:
- Skips games without PGN field
- Continues processing remaining games

**Date Parsing Failures**:
- When filtering by date, skips games with unparseable dates
- Continues processing remaining games

## Progress Reporting

Progress reporting ensures UI remains responsive during large imports:

- **Lichess**: Updates every 10 games during parsing
- **Chess.com**: Updates every 10-25 games (depending on archive size)
- **Progress calculation**: Based on archives processed and games imported
- **Status messages**: Include current progress (e.g., "Imported 150 game(s) from archive 3/12...")
- **UI responsiveness**: Controller calls `processEvents()` in progress callback

## Configuration

Online import uses minimal configuration:

- **User-Agent header**: Includes app version from config
- **Request timeouts**: 30-60 seconds depending on request type
- **Progress update frequency**: Determined by service logic

No platform-specific API keys or authentication required (public APIs).

## Code Locations

- **Service**: `app/services/online_import_service.py`
- **Controller Integration**: `app/controllers/database_controller.py` (import methods)
- **UI Integration**: `app/main_window.py` (import menu actions)
- **Configuration**: `app/config/config.json` (version for User-Agent)


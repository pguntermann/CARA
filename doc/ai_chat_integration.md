# CARA - AI Chat Integration

## Overview

The AI Chat feature provides conversational chess position analysis using Large Language Models (LLMs) from OpenAI and Anthropic. The system integrates with the game model to provide context-aware analysis, supports clickable move links for navigation, and includes prompt generation with FEN, PGN, and formatting rules. The implementation follows a Controller-Service-View pattern with thread-based API calls to keep the UI responsive.

## Architecture

The AI chat system follows a **Model-Controller-Service-View** pattern with **thread-based API communication**:

### Component Responsibilities

**AIChatController** (`app/controllers/ai_chat_controller.py`):
- Orchestrates AI chat operations and manages conversation state
- Tracks position changes via `GameModel` signals
- Generates system prompts with FEN, PGN, and optional analysis data
- Manages move label cache for clickable move links
- Handles model selection and token limit configuration
- Coordinates with `AIService` for API calls via `AIRequestThread`

**AIService** (`app/services/ai_service.py`):
- Stateless service for making API calls to OpenAI and Anthropic
- Handles provider-specific API differences (parameter names, request formats)
- Implements model-specific error recovery (max_tokens vs max_completion_tokens, temperature support)
- Provides debug logging for API communication
- Caches model-specific parameter requirements

**AIRequestThread** (`app/controllers/ai_chat_controller.py`):
- `QThread` subclass for non-blocking API calls
- Executes `AIService.send_message()` in background thread
- Emits `response_received` signal with success status and response text

**AIModelDiscoveryService** (`app/services/ai_model_discovery_service.py`):
- Discovers available models from OpenAI and Anthropic APIs
- Filters models based on configurable exclusion rules
- Returns discovered models which are persisted in user_settings.json

**DetailAIChatView** (`app/views/detail_ai_chat_view.py`):
- UI widget displaying chat messages and input controls
- Observes `AIChatController` signals for message updates
- Parses and renders move links in AI responses (clickable navigation)
- Displays typing indicator during API requests
- Manages token limit control with responsive visibility
- Handles message formatting (bold text, move links, separators)

**UserSettingsService** (Singleton):
- Stores AI model preferences (provider, model, API keys)
- Manages token limit settings
- Tracks provider toggle states (OpenAI vs Anthropic)

### Component Interactions

**Message Send Flow**:
1. User types message and clicks "Send" in `DetailAIChatView`
2. View calls `AIChatController.send_message(user_message)`
3. Controller gets current position (FEN, PGN, ply_index) from `GameController` and `AppController`
4. Controller appends position context to user message
5. Controller checks if position changed (shows separator if needed)
6. Controller adds user message to conversation history
7. Controller generates system prompt (includes FEN, PGN, formatting rules, optional analysis data)
8. Controller creates `AIRequestThread` with provider, model, API key, messages, system prompt
9. Thread starts and calls `AIService.send_message()` in background
10. Service makes HTTP request to provider API (OpenAI or Anthropic)
11. Service handles errors and retries with model-specific parameter adjustments
12. Thread emits `response_received` signal with success and response text
13. Controller's `_on_ai_response()` receives signal
14. Controller adds AI response to conversation history
15. Controller emits `message_added` signal
16. View observes signal and displays message with move link parsing

**Position Change Flow**:
1. User navigates to different position in game
2. `GameModel.active_move_changed` signal fires
3. Controller's `_on_active_move_changed()` receives signal
4. Controller updates `_current_ply` to track position
5. On next message send, controller detects position change
6. Controller shows separator label (e.g., "Move 14. Nf3") if position changed
7. Controller includes new FEN in user message context

**Move Link Click Flow**:
1. AI response contains move notation wrapped in `[%move]` syntax (e.g., `[%14.Nf3]`)
2. View's `_format_message_text()` parses move links using regex pattern
3. View converts move links to HTML anchor tags with `href="move:notation"`
4. View displays message with RichText format
5. User clicks move link
6. View's `_on_ai_move_link_activated()` receives link
7. View extracts move notation and calls `controller.handle_move_link_click(notation)`
8. Controller looks up ply_index from `_move_lookup_by_notation` cache
9. Controller calls `GameController.navigate_to_ply(ply_index)`
10. Game navigates to the position after that move

**Model Discovery Flow**:
1. User opens AI Model Settings dialog
2. Dialog loads previously discovered models from `user_settings.json` (if available)
3. User enters API key and clicks "Refresh Models" button
4. Dialog calls `AIModelDiscoveryService.get_openai_models(api_key)` or `get_anthropic_models(api_key)`
5. Service makes API request to provider
6. Service filters models using exclusion rules (prefixes, contains, exact matches)
7. Service returns list of model IDs
8. Dialog displays models in dropdown
9. When user clicks "Save", discovered models are persisted to `user_settings.json`
10. On subsequent dialog opens, models are loaded from `user_settings.json` until user refreshes them

## System Prompt Generation

### Overview

The system prompt is dynamically generated for each message to ensure the AI model always has current position context. The prompt includes:

1. **FEN Notation**: Exact current position
2. **PGN Context**: Full game moves (optionally with metadata removed)
3. **Formatting Rules**: Strict requirements for response format
4. **Move Sequence**: List of actually played moves for `[%move]` syntax
5. **Analysis Data** (optional): Engine evaluations and move classifications

### Prompt Structure

**First Message**:
- Full initial context with FEN, PGN, formatting rules, and move sequence
- PGN is stored in `_stored_pgn` for subsequent messages

**Subsequent Messages**:
- Regenerates prompt with current FEN (position may have changed)
- Reuses stored PGN (game context remains constant)
- Includes formatting rules and move sequence

### Formatting Rules

The system prompt includes strict formatting requirements:

```
CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE:
1. NEVER use numbered lists (1., 2., 3., etc.) - write in paragraph form only
2. NEVER use bullet points (-, *, •, etc.) - write in paragraph form only
3. NEVER use headings or section breaks - write in continuous paragraph form only
4. Keep all responses SHORT - aim for 2-3 sentences maximum
5. Write in plain, continuous paragraph form with no formatting, lists, or structure
6. Be direct and to the point - no lengthy explanations unless explicitly requested
7. Moves that were NOT actually played in the game but you still want to reference must be bolded using double asterisks: **14.Re4**
8. Moves that WERE actually played in the game must be wrapped exactly as [%14.Re4] for White or [%14...Re4] for Black using the notations provided. Never bold these real moves—only use the [%move] syntax.
9. Only use the [%move] syntax for moves that exactly match the provided list of actual game moves.
```

### Analysis Data Inclusion

If enabled in user settings (`include_analysis_data_in_preprompt`), the system prompt includes raw analysis JSON containing:
- Engine evaluations for each move
- Move classifications (Good, Inaccuracy, Mistake, Blunder)
- Other analysis data stored by the game analysis system

This allows the AI to reference engine evaluations in its analysis.

## Position Tracking and Context Management

### Position Context

Every user message includes current position context:
- FEN notation appended to message: `[Current position: FEN {fen} - {side} to move]`
- This ensures the model always knows the current position, even in multi-turn conversations

### Position Change Detection

The controller tracks position changes:
- Observes `GameModel.active_move_changed` signal
- Updates `_current_ply` when position changes
- On message send, compares `ply_index` with `_last_conversation_ply`
- If different, shows separator label (e.g., "Move 14. Nf3") to indicate position change

### Move Label Cache

The controller builds a cache mapping ply indices to move labels:
- `_move_label_cache`: Maps `ply_index -> "Move 14. Nf3"`
- `_move_lookup_by_notation`: Maps `"14.Nf3" -> ply_index`
- `_played_move_sequence`: List of all move notations in game order
- Cache is rebuilt when active game changes
- Used for separator labels and move link navigation

### PGN Storage

The controller stores PGN for the entire conversation:
- `_stored_pgn`: PGN from first message (game context)
- Subsequent messages reuse stored PGN (game doesn't change during conversation)
- FEN is regenerated each time (position may change as user navigates)

## Multi-Provider API Integration

### Provider Support

The system supports two AI providers:

**OpenAI**:
- Models: GPT-4, GPT-3.5-turbo, o1, o3, etc.
- API Endpoint: `https://api.openai.com/v1/chat/completions`
- System prompt: Included in messages array as role "system"
- Parameters: `max_tokens` or `max_completion_tokens` (model-dependent), `temperature` (model-dependent)

**Anthropic**:
- Models: Claude-3-5-sonnet, Claude-3-opus, etc.
- API Endpoint: `https://api.anthropic.com/v1/messages`
- System prompt: Separate `system` field in request payload
- Parameters: `max_tokens` (fixed), no temperature parameter

### Model-Specific Handling

**Parameter Differences**:
- **max_tokens vs max_completion_tokens**: Newer OpenAI models (o3, o1) use `max_completion_tokens` instead of `max_tokens`
- **Temperature Support**: Some models (o3, o1) don't support temperature parameter
- **Error Recovery**: Service detects parameter errors and retries with correct parameters
- **Caching**: Service caches model-specific parameter requirements to avoid retries

**Error Handling**:
1. If `max_tokens` error occurs, service caches model as requiring `max_completion_tokens` and retries
2. If `temperature` error occurs, service caches model as not supporting temperature and retries
3. If retry fails, returns error message to user
4. Special handling for o3 models requiring v1/responses endpoint (not supported, shows helpful error)

### API Request Format

**OpenAI Request**:
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "max_tokens": 2000,
  "temperature": 0.7
}
```

**Anthropic Request**:
```json
{
  "model": "claude-3-5-sonnet-20241022",
  "system": "...",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "max_tokens": 2000
}
```

## Model Discovery and Persistence

### Discovery Process

1. User provides API key in settings dialog
2. User clicks "Refresh Models" button
3. `AIModelDiscoveryService` makes API request to provider
4. Service filters models using exclusion rules:
   - **Exclude Prefixes**: e.g., "o1-pro-", "text-", "davinci"
   - **Exclude Contains**: e.g., "audio", "realtime", "image"
   - **Exclude Exact**: Specific model IDs to exclude
5. Service returns list of model IDs
6. Discovered models are saved to `user_settings.json` when user clicks "Save"

### Model Persistence

- **Storage Location**: Models are stored in `user_settings.json` under `ai_models.openai.models` and `ai_models.anthropic.models`
- **Persistence**: Models persist across application sessions until user refreshes them
- **Refresh**: Users can refresh models at any time via the "Refresh Models" button, which will replace the existing model list
- **No Time-Based Expiry**: Models remain in settings until manually refreshed

### Filter Configuration

Filters are configurable in `config.json` under `ai.model_filters`:
```json
{
  "ai": {
    "model_filters": {
      "openai": {
        "exclude_prefixes": ["o1-pro-", "text-"],
        "exclude_contains": ["audio", "realtime"],
        "exclude_exact": []
      },
      "anthropic": {
        "exclude_prefixes": [],
        "exclude_contains": [],
        "exclude_exact": []
      }
    }
  }
}
```

## Move Link Handling

### Move Link Syntax

AI responses use special syntax for clickable move links:
- **Played Moves**: `[%14.Nf3]` for White, `[%14...Re4]` for Black
- **Hypothetical Moves**: `**14.Re4**` (bold, not clickable)

### Parsing Process

1. View's `_format_message_text()` uses regex to find `[%...]` patterns
2. Regex pattern: `r'\[%([^\]]+)\]'`
3. For each match, extracts move notation
4. Converts to HTML anchor: `<a href="move:14.Nf3">14.Nf3</a>`
5. Renders message with RichText format

### Navigation

1. User clicks move link
2. View extracts notation from `href="move:14.Nf3"`
3. Calls `controller.handle_move_link_click("14.Nf3")`
4. Controller looks up `ply_index` from `_move_lookup_by_notation` cache
5. Controller calls `GameController.navigate_to_ply(ply_index)`
6. Game navigates to position after that move

### Move Label Cache Building

The cache is built when active game changes:
1. Parse PGN using `chess.pgn.read_game()`
2. Iterate through mainline moves
3. For each move:
   - Calculate move number and side to move
   - Generate label: `"Move 14. Nf3"` or `"Move 14... Re4"`
   - Store in `_move_label_cache[ply_index] = label`
   - Store in `_move_lookup_by_notation["14.Nf3"] = ply_index`
   - Add to `_played_move_sequence` list

## Conversation State Management

### Conversation History

The controller maintains conversation history:
- `_conversation`: List of message dicts with "role" and "content"
- Messages include user messages with position context
- AI responses are added after API calls complete

### Conversation Lifecycle

1. **Start**: Conversation begins with first user message
2. **Continue**: Subsequent messages append to conversation
3. **Position Change**: Separator shown when position changes
4. **Game Change**: Conversation cleared when active game changes
5. **Clear**: User can manually clear conversation

### State Persistence

- Conversation state is **not** persisted (cleared on game change or manual clear)
- Model preferences and API keys are persisted in `user_settings.json`
- Token limits are persisted in `user_settings.json`

## Configuration

AI chat is configured in `config.json` under `ui.panels.detail.ai_chat`:

```json
{
  "ai_chat": {
    "background_color": [40, 40, 45],
    "text_color": [200, 200, 200],
    "font_family": "Helvetica Neue",
    "font_size": 11,
    "messages": {
      "user": {
        "background_color": [60, 80, 120],
        "text_color": [240, 240, 240]
      },
      "ai": {
        "background_color": [50, 50, 55],
        "text_color": [200, 200, 200],
        "link_color": [100, 150, 255]
      },
      "typing_indicator": {
        "opacity": 0.6,
        "animation_interval_ms": 500
      }
    },
    "input": {
      "height": 30,
      "padding": 5,
      "background_color": [45, 45, 50],
      "text_color": [200, 200, 200],
      "border_color": [60, 60, 65],
      "focus_border_color": [0, 120, 212]
    },
    "tokens": {
      "minimum": 256,
      "maximum": 16000,
      "default": 2000,
      "width": 120,
      "collapse_width_threshold": 520
    }
  }
}
```

API endpoints are configured in `ai.api_endpoints`:

```json
{
  "ai": {
    "api_endpoints": {
      "openai": {
        "chat": "https://api.openai.com/v1/chat/completions",
        "models": "https://api.openai.com/v1/models"
      },
      "anthropic": {
        "messages": "https://api.anthropic.com/v1/messages",
        "models": "https://api.anthropic.com/v1/models"
      }
    }
  }
}
```

User settings (stored in `user_settings.json`):

```json
{
  "ai_models": {
    "openai": {
      "api_key": "...",
      "model": "gpt-4",
      "models": ["gpt-4", "gpt-3.5-turbo"]
    },
    "anthropic": {
      "api_key": "...",
      "model": "claude-3-5-sonnet-20241022",
      "models": ["claude-3-5-sonnet-20241022"]
    }
  },
  "ai_summary": {
    "use_openai_models": true,
    "use_anthropic_models": false,
    "include_metadata_in_preprompt": true,
    "include_analysis_data_in_preprompt": false
  }
}
```

## Error Handling

### API Errors

- **Network Errors**: Returned as error messages to user
- **Authentication Errors**: "Invalid API key" message
- **Model Errors**: Model-specific error messages (e.g., "Model requires v1/responses endpoint")
- **Parameter Errors**: Automatic retry with correct parameters (cached for future requests)
- **Token Limit Errors**: Special handling for reasoning tokens in o3 models

### Thread Management

- **Request Cancellation**: Thread can be terminated if user clears conversation during request
- **Thread Cleanup**: Thread reference cleared after completion
- **Concurrent Requests**: Only one request allowed at a time (checked before starting new request)

### User Feedback

- **Error Messages**: Displayed as system messages in chat
- **Typing Indicator**: Shown during requests, hidden on completion or error
- **Input Disabled**: Input field disabled during requests to prevent concurrent requests

## Debug Logging

The `AIService` supports debug logging for API communication:

- **Outbound Logging**: Logs request payloads (API keys hidden)
- **Inbound Logging**: Logs response data (content truncated for readability)
- **Thread-Safe Flags**: Debug flags can be toggled from MainWindow
- **Format**: `[AI SEND/RECV] HH:MM:SS.mmm [Thread-ID]: message`

Debug callbacks are set via `set_debug_callbacks()` and `set_debug_flags()`.

## Code Location

Implementation files:

- `app/controllers/ai_chat_controller.py`: Controller orchestration and conversation management
- `app/services/ai_service.py`: API communication service
- `app/services/ai_model_discovery_service.py`: Model discovery and caching
- `app/views/detail_ai_chat_view.py`: UI view and message rendering
- `app/config/config.json`: Configuration under `ui.panels.detail.ai_chat` and `ai.api_endpoints`
- `app/services/user_settings_service.py`: User preferences storage (Singleton)

## Related Documentation

- **User Settings Persistence**: See `user_settings_persistence.md` for settings storage architecture
- **Game Model**: See `architecture_outline.md` for GameModel signal/slot patterns
- **Analysis Data Storage**: See game analysis documentation for analysis data format


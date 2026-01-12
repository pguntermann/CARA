"""AI Chat controller for managing AI conversation and position analysis."""

from typing import Dict, Any, Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QThread
import chess
import chess.pgn
import io

from app.services.ai_service import AIService, AIProvider
from app.services.user_settings_service import UserSettingsService
from app.services.pgn_formatter_service import PgnFormatterService
from app.services.logging_service import LoggingService


class AIRequestThread(QThread):
    """Thread for making AI API calls without blocking UI."""
    
    response_received = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, provider: str, model: str, api_key: str, 
                 messages: List[Dict[str, str]], system_prompt: Optional[str] = None,
                 token_limit: Optional[int] = None, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the AI request thread.
        
        Args:
            provider: Provider name ("openai" or "anthropic").
            model: Model ID.
            api_key: API key for the provider.
            messages: List of message dicts.
            system_prompt: Optional system prompt.
            token_limit: Optional token limit.
            config: Configuration dictionary.
        """
        super().__init__()
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.messages = messages
        self.system_prompt = system_prompt
        self.token_limit = token_limit
        self.config = config
    
    def run(self) -> None:
        """Execute the AI request in the background thread."""
        ai_service = AIService(self.config)
        success, response = ai_service.send_message(
            self.provider,
            self.model,
            self.api_key,
            self.messages,
            self.system_prompt,
            token_limit=self.token_limit
        )
        self.response_received.emit(success, response)


class AIChatController(QObject):
    """Controller for managing AI chat conversations and position analysis.
    
    This controller orchestrates AI API calls, manages conversation state,
    and handles position change detection.
    """
    
    # Signals
    message_added = pyqtSignal(str, str)  # role, content
    conversation_cleared = pyqtSignal()
    error_occurred = pyqtSignal(str)  # error message
    request_started = pyqtSignal()  # Emitted when request starts
    request_completed = pyqtSignal()  # Emitted when request completes
    
    def __init__(self, config: Dict[str, Any], game_controller, app_controller) -> None:
        """Initialize the AI chat controller.
        
        Args:
            config: Configuration dictionary.
            game_controller: GameController instance for getting game state.
            app_controller: AppController instance for getting FEN.
        """
        super().__init__()
        self.config = config
        self.game_controller = game_controller
        self.app_controller = app_controller
        self.user_settings_service = UserSettingsService.get_instance()
        self.ai_service = AIService(config)
        
        # Conversation state
        self._conversation: List[Dict[str, str]] = []
        self._current_ply: int = -1
        self._last_conversation_ply: Optional[int] = None
        self._move_label_cache: Dict[int, str] = {}
        self._move_lookup_by_notation: Dict[str, int] = {}
        self._played_move_sequence: List[str] = []
        self._request_thread: Optional[AIRequestThread] = None
        self._selected_model: Optional[str] = None  # Format: "OpenAI: gpt-4" or "Anthropic: claude-3-5-sonnet"
        self._stored_pgn: Optional[str] = None  # Store PGN for inclusion in all subsequent system prompts
        tokens_config = config.get('ui', {}).get('panels', {}).get('detail', {}).get('ai_chat', {}).get('tokens', {})
        self._token_min = tokens_config.get('minimum', 256)
        self._token_max = tokens_config.get('maximum', 16000)
        self._token_limit = tokens_config.get('default', 2000)
        self._token_limit: int = self.config.get('ai', {}).get('model_filters', {}).get('openai', {}).get('default_token_limit', 2000)
        
        # Connect to game model for position tracking
        if self.game_controller:
            game_model = self.game_controller.get_game_model()
            game_model.active_move_changed.connect(self._on_active_move_changed)
            game_model.active_game_changed.connect(self._on_active_game_changed)
            self._current_ply = game_model.get_active_move_ply()
            self._build_move_label_cache(game_model.active_game)
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from game model.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        if ply_index != self._current_ply:
            self._current_ply = ply_index
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change from game model.
        
        Args:
            game: GameData instance or None.
        """
        # Clear conversation when game changes
        self._current_ply = -1
        self._build_move_label_cache(game)
        self.clear_conversation()
    
    def clear_conversation(self) -> None:
        """Clear the current conversation."""
        # Cancel any pending request
        if self._request_thread and self._request_thread.isRunning():
            self._request_thread.terminate()
            self._request_thread.wait()
            self._request_thread = None
        
        self._conversation = []
        self._stored_pgn = None  # Clear stored PGN
        self._last_conversation_ply = None
        self.conversation_cleared.emit()
    
    def _get_position_info(self) -> Tuple[str, str, int]:
        """Get current position information.
        
        Returns:
            Tuple of (fen: str, pgn: str, ply_index: int).
        """
        fen = ""
        pgn = ""
        ply_index = 0
        
        if self.app_controller:
            fen = self.app_controller.get_current_fen()
        
        if self.game_controller:
            game_model = self.game_controller.get_game_model()
            ply_index = game_model.get_active_move_ply()
            active_game = game_model.active_game
            if active_game:
                original_pgn = active_game.pgn or ""
                pgn = PgnFormatterService.remove_cara_tags(original_pgn)
        
        return fen, pgn, ply_index
    
    def _generate_initial_prompt(self, fen: str, pgn: str, ply_index: int) -> str:
        """Generate initial prompt for AI analysis.
        
        Args:
            fen: Current FEN position.
            pgn: Game PGN text.
            ply_index: Current ply index.
            
        Returns:
            Initial prompt string.
        """
        ai_summary_settings = self.user_settings_service.get_settings().get("ai_summary", {})
        include_metadata = ai_summary_settings.get("include_metadata_in_preprompt", True)
        include_analysis_data = ai_summary_settings.get("include_analysis_data_in_preprompt", False)

        # Parse FEN to get board state
        try:
            board = chess.Board(fen)
            side_to_move = "White" if board.turn == chess.WHITE else "Black"
            
            # Get piece positions for better context
            prompt = f"""Analyze this EXACT chess position (this is the current board state):

FEN: {fen}

Current position details:
- Side to move: {side_to_move}
- This is the actual current position on the board

"""
        except Exception:
            prompt = f"""Analyze this chess position:

FEN: {fen}

"""
        
        if pgn:
            pgn_for_prompt = pgn
            if not include_metadata:
                try:
                    pgn_for_prompt = PgnFormatterService.remove_metadata_tags(pgn_for_prompt)
                except Exception:
                    pgn_for_prompt = pgn
            # Try to extract move number and side to move
            try:
                pgn_io = chess.pgn.StringIO(pgn_for_prompt)
                game = chess.pgn.read_game(pgn_io)
                if game:
                    # Navigate to current position
                    node = game
                    for i in range(ply_index):
                        if node.variations:
                            node = node.variation(0)
                        else:
                            break
                    
                    # Get move number
                    board = node.board()
                    move_number = (ply_index + 1) // 2 + 1 if ply_index > 0 else 1
                    side_to_move = "White" if board.turn == chess.WHITE else "Black"
                    
                    prompt += f"Game context: Move {move_number} ({side_to_move} to move)\n\n"
            except Exception:
                pass
            
            prompt += f"Game moves (PGN): {pgn_for_prompt}\n\n"
        
        prompt += """IMPORTANT: Analyze the EXACT position given in the FEN notation above. 
Do not suggest moves that are already on the board or make assumptions about pieces that aren't present.
Base your analysis solely on the actual current position described by the FEN.

You have access to the full game context including the PGN (game moves) provided above. Use this context to understand how the position was reached and provide more informed analysis.

Please provide a brief analysis of this position, including:
- The current evaluation and who is better
- Key features of the position (piece activity, pawn structure, king safety, etc.)
- Potential plans or ideas for both sides based on the ACTUAL current position
- Any tactical or strategic considerations"""

        if self._played_move_sequence:
            prompt += "\n\nOnly the following moves were actually played in the game. Wrap these exact notations using [%move] as instructed above and do not use that syntax for any other move:\n"
            prompt += ", ".join(self._played_move_sequence)
        
        # Include analysis data if enabled and game is analyzed
        if self.game_controller and include_analysis_data:
            game_model = self.game_controller.get_game_model()
            if game_model.is_game_analyzed:
                active_game = game_model.active_game
                if active_game:
                    from app.services.analysis_data_storage_service import AnalysisDataStorageService
                    analysis_json = AnalysisDataStorageService.get_raw_analysis_data(active_game)
                    if analysis_json:
                        prompt += "\n\nGame Analysis Data:\n"
                        prompt += "The following analysis data is available for reference. "
                        prompt += "It contains engine evaluations, move classifications (Good, Inaccuracy, Mistake, Blunder), "
                        prompt += "and other analysis for each move. You can refer to this data to provide more accurate and "
                        prompt += "informed analysis of the position:\n\n"
                        prompt += analysis_json
        
        return prompt
    
    def get_available_models(self) -> List[str]:
        """Get list of available models with provider prefixes.
        
        Returns:
            List of model strings in format "Provider: model" (e.g., ["OpenAI: gpt-4", "Anthropic: claude-3-5-sonnet"]).
        """
        models: List[str] = []
        ai_settings = self.user_settings_service.get_settings().get("ai_models", {})
        use_openai, use_anthropic = self._get_provider_preferences()
        
        if use_openai:
            openai_settings = ai_settings.get("openai", {})
            openai_api_key = openai_settings.get("api_key", "")
            openai_models = openai_settings.get("models", []) or []
            if openai_api_key:
                for model in openai_models:
                    models.append(f"OpenAI: {model}")
        
        if use_anthropic:
            anthropic_settings = ai_settings.get("anthropic", {})
            anthropic_api_key = anthropic_settings.get("api_key", "")
            anthropic_models = anthropic_settings.get("models", []) or []
            if anthropic_api_key:
                for model in anthropic_models:
                    models.append(f"Anthropic: {model}")
        
        return models
    
    def get_default_model(self) -> Optional[str]:
        """Get the default model from settings.
        
        Returns:
            Model string in format "Provider: model" or None if not configured.
        """
        ai_settings = self.user_settings_service.get_settings().get("ai_models", {})
        use_openai, use_anthropic = self._get_provider_preferences()
        
        # Check OpenAI first
        if use_openai:
            openai_settings = ai_settings.get("openai", {})
            if openai_settings.get("api_key") and openai_settings.get("model"):
                return f"OpenAI: {openai_settings['model']}"
        
        # Check Anthropic
        if use_anthropic:
            anthropic_settings = ai_settings.get("anthropic", {})
            if anthropic_settings.get("api_key") and anthropic_settings.get("model"):
                return f"Anthropic: {anthropic_settings['model']}"
        
        return None
    
    def set_selected_model(self, model_string: str) -> None:
        """Set the selected model.
        
        Args:
            model_string: Model string in format "Provider: model" (e.g., "OpenAI: gpt-4").
        """
        self._selected_model = model_string
    
    def set_token_limit(self, token_limit: int) -> None:
        """Set the max completion token budget for upcoming requests."""
        clamped = max(self._token_min, min(self._token_max, token_limit))
        self._token_limit = clamped
    
    def _get_model_config(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Get configured AI model settings.
        
        Returns:
            Tuple of (provider: Optional[str], model: Optional[str], api_key: Optional[str]).
            Returns (None, None, None) if no model is configured.
        """
        # Use selected model if set, otherwise fall back to default
        model_string = self._selected_model or self.get_default_model()
        
        if not model_string:
            return None, None, None
        
        # Parse model string (format: "Provider: model")
        if ":" in model_string:
            parts = model_string.split(":", 1)
            provider_name = parts[0].strip()
            model = parts[1].strip()
        else:
            # Fallback: assume OpenAI if no prefix
            provider_name = "OpenAI"
            model = model_string
        
        # Get API key for the provider
        ai_settings = self.user_settings_service.get_settings().get("ai_models", {})
        
        if provider_name.lower() == "openai":
            openai_settings = ai_settings.get("openai", {})
            api_key = openai_settings.get("api_key", "")
            if api_key and model:
                return AIProvider.OPENAI, model, api_key
        elif provider_name.lower() == "anthropic":
            anthropic_settings = ai_settings.get("anthropic", {})
            api_key = anthropic_settings.get("api_key", "")
            if api_key and model:
                return AIProvider.ANTHROPIC, model, api_key
        
        return None, None, None
    
    def _get_provider_preferences(self) -> tuple[bool, bool]:
        """Get provider toggle states from user settings.
        
        Returns:
            Tuple of (use_openai_models, use_anthropic_models) with enforced exclusivity.
        """
        settings = self.user_settings_service.get_settings()
        ai_summary = settings.get("ai_summary", {})
        use_openai = ai_summary.get("use_openai_models", True)
        use_anthropic = ai_summary.get("use_anthropic_models", False)
        
        if use_openai == use_anthropic:
            use_openai = True
            use_anthropic = False
        
        return use_openai, use_anthropic
    
    def _build_move_label_cache(self, game) -> None:
        """Build cache mapping ply indices to move labels for the active game."""
        self._move_label_cache = {}
        self._move_lookup_by_notation = {}
        self._played_move_sequence = []
        if not game or not game.pgn:
            return
        
        try:
            pgn_io = io.StringIO(game.pgn)
            parsed_game = chess.pgn.read_game(pgn_io)
            if parsed_game is None:
                return
            
            board = parsed_game.board()
            ply_index = 0
            for move in parsed_game.mainline_moves():
                is_white_move = board.turn == chess.WHITE
                move_number = board.fullmove_number
                san = board.san(move)
                ply_index += 1
                label = f"Move {move_number}. {san}" if is_white_move else f"Move {move_number}... {san}"
                self._move_label_cache[ply_index] = label
                notation = f"{move_number}.{san}" if is_white_move else f"{move_number}...{san}"
                self._move_lookup_by_notation[notation] = ply_index
                self._played_move_sequence.append(notation)
                board.push(move)
        except Exception as exc:
            logging_service = LoggingService.get_instance()
            logging_service.warning(f"Failed to build move label cache: {exc}", exc_info=exc)

    def handle_move_link_click(self, move_notation: str) -> bool:
        """Handle move link clicks from the AI chat view."""
        if not move_notation:
            return False
        ply_index = self._move_lookup_by_notation.get(move_notation)
        if ply_index is None or not self.game_controller:
            return False
        return bool(self.game_controller.navigate_to_ply(ply_index))
    
    def send_message(self, user_message: str) -> bool:
        """Send a user message to the AI.
        
        Args:
            user_message: The user's message text.
            
        Returns:
            True if message was sent successfully, False if there was an error (e.g., no model configured).
        """
        if not user_message.strip():
            return False
        
        # Check if there's already a request in progress
        if self._request_thread and self._request_thread.isRunning():
            return False
        
        # Get model configuration
        provider, model, api_key = self._get_model_config()
        if not provider or not model or not api_key:
            self.error_occurred.emit("Please configure an AI model in AI Model Settings.")
            return False
        
        # Get position info first (before adding message)
        fen, pgn, ply_index = self._get_position_info()
        
        # Include current position in every user message so model always has current context
        if fen:
            # Parse FEN to get side to move
            try:
                board = chess.Board(fen)
                side_to_move = "White" if board.turn == chess.WHITE else "Black"
                position_context = f"\n\n[Current position: FEN {fen} - {side_to_move} to move]"
            except Exception:
                position_context = f"\n\n[Current position: FEN {fen}]"
            
            user_message_with_context = user_message + position_context
        else:
            user_message_with_context = user_message
        
        # Show separator when this is the first question after a game change, or move changed
        if self._last_conversation_ply is None or self._last_conversation_ply != ply_index:
            separator_label = self._move_label_cache.get(ply_index)
            if separator_label:
                self.message_added.emit("separator", separator_label)
        
        # Add user message to conversation
        self._conversation.append({"role": "user", "content": user_message_with_context})
        self.message_added.emit("user", user_message)  # Emit original message without context for display
        self._last_conversation_ply = ply_index
        
        # Formatting rules that must be included in every system prompt
        formatting_rules = """CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE:
1. NEVER use numbered lists (1., 2., 3., etc.) - write in paragraph form only
2. NEVER use bullet points (-, *, •, etc.) - write in paragraph form only
3. NEVER use headings or section breaks - write in continuous paragraph form only
4. Keep all responses SHORT - aim for 2-3 sentences maximum
5. Write in plain, continuous paragraph form with no formatting, lists, or structure
6. Be direct and to the point - no lengthy explanations unless explicitly requested
7. Moves that were NOT actually played in the game but you still want to reference must be bolded using double asterisks: **14.Re4**
8. Moves that WERE actually played in the game must be wrapped exactly as [%14.Re4] for White or [%14...Re4] for Black using the notations provided. Never bold these real moves—only use the [%move] syntax.
9. Only use the [%move] syntax for moves that exactly match the provided list of actual game moves."""
        
        # Build system prompt - always include formatting rules and PGN context
        if len(self._conversation) == 1:
            # First message: include full initial context
            initial_prompt = self._generate_initial_prompt(fen, pgn, ply_index)
            system_prompt = f"""You are a chess analysis assistant. Analyze chess positions based on FEN notation and game context.

{formatting_rules}

{initial_prompt}"""
            # Store the PGN for subsequent messages (FEN will be updated each time)
            self._stored_pgn = pgn
        else:
            # Subsequent messages: regenerate prompt with current FEN but keep the stored PGN
            # This ensures the model always has access to both current position and full game context
            current_prompt = self._generate_initial_prompt(fen, self._stored_pgn, ply_index)
            system_prompt = f"""You are a chess analysis assistant. Analyze chess positions based on FEN notation and game context.

{formatting_rules}

{current_prompt}"""
        
        # Log AI request sent
        logging_service = LoggingService.get_instance()
        message_length = len(user_message)
        conversation_length = len(self._conversation)
        logging_service.info(f"AI request sent: provider={provider}, model={model}, message_length={message_length}, conversation_length={conversation_length}, token_limit={self._token_limit}")
        
        # Emit request started signal
        self.request_started.emit()
        
        # Make API call in background thread
        self._request_thread = AIRequestThread(
            provider,
            model,
            api_key,
            self._conversation,
            system_prompt,
            token_limit=self._token_limit,
            config=self.config
        )
        self._request_thread.response_received.connect(self._on_ai_response)
        self._request_thread.finished.connect(self._on_request_finished)
        self._request_thread.start()
        
        return True
    
    def _on_ai_response(self, success: bool, response: str) -> None:
        """Handle AI response.
        
        Args:
            success: True if request succeeded.
            response: Response text or error message.
        """
        # Log AI response received
        logging_service = LoggingService.get_instance()
        if success:
            response_length = len(response) if response else 0
            logging_service.info(f"AI response received: success=True, response_length={response_length}")
            self._conversation.append({"role": "ai", "content": response})
            self.message_added.emit("ai", response)
        else:
            logging_service.warning(f"AI response received: success=False, error={response}")
            self.error_occurred.emit(response)
    
    def _on_request_finished(self) -> None:
        """Handle request thread completion."""
        self.request_completed.emit()
        self._request_thread = None
    
    def is_request_in_progress(self) -> bool:
        """Check if a request is currently in progress.
        
        Returns:
            True if a request is in progress, False otherwise.
        """
        return self._request_thread is not None and self._request_thread.isRunning()


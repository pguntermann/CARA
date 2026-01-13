"""Error handling service for fatal errors."""

import sys
from typing import Optional


class ErrorHandler:
    """Handles fatal errors by logging to console and terminating the application."""
    
    @staticmethod
    def handle_fatal_error(error: Exception, context: Optional[str] = None) -> None:
        """Handle a fatal error by logging to console and terminating.
        
        Args:
            error: The exception that occurred.
            context: Optional context message describing where the error occurred.
        """
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        
        # Initialize if not already initialized (thread-safe)
        if not logging_service._initialized:
            with logging_service._instance_lock:
                if not logging_service._initialized:
                    logging_service.initialize()
        
        # Use logging service
        error_msg = f"FATAL ERROR"
        if context:
            error_msg += f" - Context: {context}"
        error_msg += f"\nError Type: {type(error).__name__}\nError Message: {str(error)}\n"
        logging_service.error(error_msg, exc_info=error)
        logging_service.error("Application will now terminate.")
        
        # Flush logs before exit
        logging_service.shutdown()
        
        sys.exit(1)
    
    @staticmethod
    def setup_exception_handler() -> None:
        """Install a global exception handler for uncaught exceptions."""
        def exception_handler(exc_type, exc_value, exc_traceback):
            """Handle uncaught exceptions."""
            if exc_type == KeyboardInterrupt:
                from app.services.logging_service import LoggingService
                logging_service = LoggingService.get_instance()
                if not logging_service._initialized:
                    with logging_service._instance_lock:
                        if not logging_service._initialized:
                            logging_service.initialize()
                logging_service.info("Application interrupted by user.")
                logging_service.shutdown()
                sys.exit(130)  # Standard exit code for SIGINT
            
            error = exc_value if exc_value else exc_type()
            ErrorHandler.handle_fatal_error(error, "Uncaught exception")
        
        sys.excepthook = exception_handler


"""Error handling service for fatal errors."""

import sys
import traceback
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
        # Try to use logging service if available, otherwise fall back to print
        try:
            from app.services.logging_service import LoggingService
            logging_service = LoggingService.get_instance()
            if logging_service._initialized:
                # Use logging service
                error_msg = f"FATAL ERROR"
                if context:
                    error_msg += f" - Context: {context}"
                error_msg += f"\nError Type: {type(error).__name__}\nError Message: {str(error)}\n"
                logging_service.error(error_msg, exc_info=error)
                logging_service.error("Application will now terminate.")
                # Flush logs before exit
                logging_service.shutdown()
            else:
                # Logging service not initialized, use print
                ErrorHandler._print_fatal_error(error, context)
        except Exception:
            # If logging service fails, fall back to print
            ErrorHandler._print_fatal_error(error, context)
        
        sys.exit(1)
    
    @staticmethod
    def _print_fatal_error(error: Exception, context: Optional[str] = None) -> None:
        """Fallback method to print fatal error to console.
        
        Args:
            error: The exception that occurred.
            context: Optional context message describing where the error occurred.
        """
        print("=" * 80, file=sys.stderr)
        print("FATAL ERROR", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        
        if context:
            print(f"Context: {context}", file=sys.stderr)
            print("", file=sys.stderr)
        
        print(f"Error Type: {type(error).__name__}", file=sys.stderr)
        print(f"Error Message: {str(error)}", file=sys.stderr)
        print("", file=sys.stderr)
        
        print("Traceback:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        
        print("=" * 80, file=sys.stderr)
        print("Application will now terminate.", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
    
    @staticmethod
    def setup_exception_handler() -> None:
        """Install a global exception handler for uncaught exceptions."""
        def exception_handler(exc_type, exc_value, exc_traceback):
            """Handle uncaught exceptions."""
            if exc_type == KeyboardInterrupt:
                # Don't print traceback for Ctrl+C
                # Try to use logging service if available
                try:
                    from app.services.logging_service import LoggingService
                    logging_service = LoggingService.get_instance()
                    if logging_service._initialized:
                        logging_service.info("Application interrupted by user.")
                        logging_service.shutdown()
                    else:
                        print("\nApplication interrupted by user.", file=sys.stderr)
                except Exception:
                    print("\nApplication interrupted by user.", file=sys.stderr)
                sys.exit(130)  # Standard exit code for SIGINT
            
            error = exc_value if exc_value else exc_type()
            ErrorHandler.handle_fatal_error(error, "Uncaught exception")
        
        sys.excepthook = exception_handler


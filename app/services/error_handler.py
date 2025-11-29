"""Error handling service for fatal errors."""

import sys
import traceback
from typing import Optional


class ErrorHandler:
    """Handles fatal errors by printing to console and terminating the application."""
    
    @staticmethod
    def handle_fatal_error(error: Exception, context: Optional[str] = None) -> None:
        """Handle a fatal error by printing to console and terminating.
        
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
        
        sys.exit(1)
    
    @staticmethod
    def setup_exception_handler() -> None:
        """Install a global exception handler for uncaught exceptions."""
        def exception_handler(exc_type, exc_value, exc_traceback):
            """Handle uncaught exceptions."""
            if exc_type == KeyboardInterrupt:
                # Don't print traceback for Ctrl+C
                print("\nApplication interrupted by user.", file=sys.stderr)
                sys.exit(130)  # Standard exit code for SIGINT
            
            error = exc_value if exc_value else exc_type()
            ErrorHandler.handle_fatal_error(error, "Uncaught exception")
        
        sys.excepthook = exception_handler


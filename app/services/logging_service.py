"""Logging service for centralized application logging."""

import sys
import queue
import threading
import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from app.utils.path_resolver import resolve_data_file_path


class LoggingService:
    """Service for centralized application logging.
    
    This service provides:
    - Console and/or file output (configurable)
    - Multiple log levels (DEBUG, INFO, WARNING, ERROR)
    - Rolling log files (size-based rotation)
    - Non-blocking async logging via background thread
    - Thread-safe operation
    
    This is a singleton service - use get_instance() to get the shared instance.
    """
    
    _instance: Optional['LoggingService'] = None
    _lock = threading.Lock()
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the logging service.
        
        Args:
            config: Configuration dictionary. If None, will be loaded from config.json.
        """
        self.config = config or {}
        self._logger: Optional[logging.Logger] = None
        self._log_queue: Optional[queue.Queue] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._initialized = False
        self._log_path: Optional[Path] = None
        self._is_portable_mode: bool = False
        
        # Load configuration
        self._load_config()
    
    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> 'LoggingService':
        """Get the singleton instance of LoggingService.
        
        Args:
            config: Configuration dictionary. If provided and instance exists, updates the instance's config.
            
        Returns:
            The singleton LoggingService instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        elif config is not None:
            # Update config if instance already exists
            cls._instance.config = config
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load logging configuration from config dictionary."""
        logging_config = self.config.get('logging', {})
        
        # Console settings
        console_config = logging_config.get('console', {})
        self._console_enabled = console_config.get('enabled', True)
        self._console_level = console_config.get('level', 'INFO')
        
        # File settings
        file_config = logging_config.get('file', {})
        # Explicitly handle False - ensure boolean conversion
        if 'enabled' in file_config:
            # Key exists, use its value (False in JSON becomes False in Python)
            self._file_enabled = bool(file_config['enabled'])
        else:
            # Key not present, use default True
            self._file_enabled = True
        self._file_level = file_config.get('level', 'DEBUG')
        self._log_filename = file_config.get('filename', 'cara.log')
        self._max_size_mb = file_config.get('max_size_mb', 10)
        self._backup_count = file_config.get('backup_count', 5)
    
    def initialize(self) -> None:
        """Initialize the logging service.
        
        Must be called before using the service. Sets up logger, handlers, and worker thread.
        """
        # Reload config in case it was updated
        old_file_enabled = getattr(self, '_file_enabled', None)
        self._load_config()
        
        # If file logging was just disabled, remove any existing file handler immediately
        # This prevents file creation when config changes from True to False
        if old_file_enabled is True and self._file_enabled is False and self._logger:
            for handler in self._logger.handlers[:]:
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    self._logger.removeHandler(handler)
                    handler.close()
                    handler.flush()
                    self._log_path = None
                    self._is_portable_mode = False
        
        if self._initialized:
            # If already initialized, update handlers based on new config
            if self._logger:
                for handler in self._logger.handlers[:]:
                    if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stderr:
                        # Console handler
                        if self._console_enabled:
                            # Update console handler level
                            handler.setLevel(self._get_log_level(self._console_level))
                        else:
                            # Remove console handler if disabled
                            self._logger.removeHandler(handler)
                            handler.close()
                    elif isinstance(handler, logging.handlers.RotatingFileHandler):
                        # File handler
                        if self._file_enabled is True:
                            # Update file handler level
                            handler.setLevel(self._get_log_level(self._file_level))
                        else:
                            # Remove file handler if disabled
                            # CRITICAL: Remove handler before closing to prevent file creation
                            self._logger.removeHandler(handler)
                            handler.close()
                            handler.flush()  # Ensure any pending writes are flushed
                            # Clear log path reference
                            self._log_path = None
                            self._is_portable_mode = False
                
                # Add handlers if they're enabled but don't exist
                has_console_handler = any(
                    isinstance(h, logging.StreamHandler) and h.stream == sys.stderr
                    for h in self._logger.handlers
                )
                has_file_handler = any(
                    isinstance(h, logging.handlers.RotatingFileHandler)
                    for h in self._logger.handlers
                )
                
                # Add console handler if enabled but missing
                if self._console_enabled and not has_console_handler:
                    console_handler = logging.StreamHandler(sys.stderr)
                    console_level = self._get_log_level(self._console_level)
                    console_handler.setLevel(console_level)
                    console_formatter = logging.Formatter(
                        '%(asctime)s [%(levelname)s] [Thread-%(thread)d] %(message)s',
                        datefmt='%H:%M:%S'
                    )
                    console_handler.setFormatter(console_formatter)
                    self._logger.addHandler(console_handler)
                
                # Add file handler if enabled but missing
                if self._file_enabled is True and not has_file_handler:
                    try:
                        # Generate timestamp for log filename
                        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        
                        # Insert timestamp into filename
                        base_filename = self._log_filename
                        if '.' in base_filename:
                            name, ext = base_filename.rsplit('.', 1)
                            timestamped_filename = f"{name}_{timestamp}.{ext}"
                        else:
                            timestamped_filename = f"{base_filename}_{timestamp}"
                        
                        # Resolve log file path
                        log_path, is_portable = resolve_data_file_path(timestamped_filename)
                        self._log_path = log_path
                        self._is_portable_mode = is_portable
                        
                        # Ensure directory exists
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Create rotating file handler
                        max_bytes = self._max_size_mb * 1024 * 1024
                        file_handler = logging.handlers.RotatingFileHandler(
                            str(log_path),
                            maxBytes=max_bytes,
                            backupCount=self._backup_count,
                            encoding='utf-8'
                        )
                        file_handler.setLevel(self._get_log_level(self._file_level))
                        file_formatter = logging.Formatter(
                            '%(asctime)s [%(levelname)s] [Thread-%(thread)d] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S'
                        )
                        file_handler.setFormatter(file_formatter)
                        self._logger.addHandler(file_handler)
                    except Exception as e:
                        print(f"Warning: Failed to initialize file logging: {e}", file=sys.stderr)
            return
        
        # Only initialize if at least one handler is enabled
        if not self._console_enabled and not self._file_enabled:
            self._initialized = True  # Mark as initialized but disabled
            return
        
        # Create logger
        self._logger = logging.getLogger('CARA')
        # Set logger to DEBUG (lowest level) - handlers will filter based on their own levels
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False  # Don't propagate to root logger
        
        # Create log queue for async processing
        self._log_queue = queue.Queue()
        
        # Set up handlers based on configuration
        handlers = []
        
        # Console handler
        if self._console_enabled:
            console_handler = logging.StreamHandler(sys.stderr)
            console_level = self._get_log_level(self._console_level)
            console_handler.setLevel(console_level)
            console_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] [Thread-%(thread)d] %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            handlers.append(console_handler)
        
        # File handler (rolling)
        # Only create file handler if explicitly enabled (RotatingFileHandler creates file on instantiation)
        # Use explicit True check to prevent any accidental file creation
        if self._file_enabled is True:
            try:
                # Generate timestamp for log filename
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                
                # Insert timestamp into filename (e.g., "cara.log" -> "cara_2024-01-15_14-30-00.log")
                base_filename = self._log_filename
                if '.' in base_filename:
                    name, ext = base_filename.rsplit('.', 1)
                    timestamped_filename = f"{name}_{timestamp}.{ext}"
                else:
                    timestamped_filename = f"{base_filename}_{timestamp}"
                
                # Resolve log file path using same pattern as user settings
                log_path, is_portable = resolve_data_file_path(timestamped_filename)
                self._log_path = log_path
                self._is_portable_mode = is_portable
                
                # Ensure directory exists
                log_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create rotating file handler (this will create the file immediately)
                max_bytes = self._max_size_mb * 1024 * 1024  # Convert MB to bytes
                file_handler = logging.handlers.RotatingFileHandler(
                    str(log_path),
                    maxBytes=max_bytes,
                    backupCount=self._backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(self._get_log_level(self._file_level))
                file_formatter = logging.Formatter(
                    '%(asctime)s [%(levelname)s] [Thread-%(thread)d] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                file_handler.setFormatter(file_formatter)
                handlers.append(file_handler)
            except Exception as e:
                # If file logging fails, fall back to console only
                # Use print to avoid circular dependency
                print(f"Warning: Failed to initialize file logging: {e}", file=sys.stderr)
        
        # Add handlers to logger
        for handler in handlers:
            self._logger.addHandler(handler)
        
        # Start background worker thread for async logging
        self._worker_thread = threading.Thread(
            target=self._log_worker,
            name='LoggingWorker',
            daemon=True
        )
        self._worker_thread.start()
        
        self._initialized = True
        
        # Log the resolved log file path (now that logging is initialized)
        if self._file_enabled and self._log_path:
            mode_str = "portable (app_root)" if self._is_portable_mode else "user_data_directory"
            self.debug(f"Log file path resolved: filename={self._log_filename}, path={self._log_path}, mode={mode_str}")
    
    def _get_log_level(self, level_str: str) -> int:
        """Convert log level string to logging constant.
        
        Args:
            level_str: Log level string (DEBUG, INFO, WARNING, ERROR).
            
        Returns:
            Logging level constant.
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
        }
        return level_map.get(level_str.upper(), logging.INFO)
    
    def _log_worker(self) -> None:
        """Background worker thread that processes log messages from queue."""
        while not self._shutdown_event.is_set():
            try:
                # Get message from queue with timeout to allow checking shutdown event
                try:
                    log_record = self._log_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                # Process the log record
                if self._logger:
                    self._logger.handle(log_record)
                
                # Mark task as done
                self._log_queue.task_done()
            except Exception:
                # Silently ignore errors in logging worker to prevent infinite loops
                pass
    
    def _log(self, level: int, message: str, exc_info: Optional[Exception] = None) -> None:
        """Internal logging method that enqueues log messages.
        
        Args:
            level: Logging level constant.
            message: Log message.
            exc_info: Optional exception info for error logging.
        """
        # Auto-initialize on first use if not already initialized
        if not self._initialized:
            self.initialize()
        
        # Early exit if both handlers are disabled to reduce overhead
        if not self._console_enabled and not self._file_enabled:
            return
        
        if not self._initialized or not self._logger or not self._log_queue:
            # Fallback to direct print if logging service isn't working
            if level >= logging.WARNING:
                print(f"[FALLBACK] {message}", file=sys.stderr)
            return
        
        # Create log record with thread information
        # Use makeRecord to automatically capture thread info (threadName, thread)
        import threading
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            __file__,
            0,  # lineno - not meaningful for programmatic calls
            message,
            (),
            exc_info
        )
        # Ensure thread name is preserved (makeRecord captures it, but we verify)
        # The threadName should already be set by makeRecord, but we ensure it's correct
        if not hasattr(record, 'threadName') or not record.threadName:
            record.threadName = threading.current_thread().name
        if not hasattr(record, 'thread') or not record.thread:
            record.thread = threading.get_ident()
        
        # Enqueue for async processing (non-blocking)
        try:
            self._log_queue.put_nowait(record)
        except queue.Full:
            # If queue is full, fall back to direct logging (shouldn't happen in practice)
            if self._logger:
                self._logger.handle(record)
    
    def debug(self, message: str) -> None:
        """Log a DEBUG level message.
        
        Args:
            message: Debug message.
        """
        self._log(logging.DEBUG, message)
    
    def info(self, message: str) -> None:
        """Log an INFO level message.
        
        Args:
            message: Info message.
        """
        self._log(logging.INFO, message)
    
    def warning(self, message: str) -> None:
        """Log a WARNING level message.
        
        Args:
            message: Warning message.
        """
        self._log(logging.WARNING, message)
    
    def error(self, message: str, exc_info: Optional[Exception] = None) -> None:
        """Log an ERROR level message.
        
        Args:
            message: Error message.
            exc_info: Optional exception to include traceback.
        """
        self._log(logging.ERROR, message, exc_info=exc_info)
    
    def shutdown(self) -> None:
        """Shutdown the logging service gracefully.
        
        Flushes all pending log messages and stops the worker thread.
        """
        if not self._initialized:
            return
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Wait for queue to empty (with timeout)
        if self._log_queue:
            try:
                self._log_queue.join(timeout=2.0)
            except Exception:
                pass
        
        # Wait for worker thread to finish
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        
        # Close all handlers
        if self._logger:
            for handler in self._logger.handlers[:]:
                handler.close()
                self._logger.removeHandler(handler)
        
        self._initialized = False

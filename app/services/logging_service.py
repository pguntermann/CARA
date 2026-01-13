"""Logging service for centralized application logging."""

import sys
import multiprocessing
import threading
import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from app.utils.path_resolver import resolve_data_file_path


# Module-level queue for multiprocessing support
# Set by initializer in worker processes, created in main process
_log_queue: Optional[multiprocessing.Queue] = None
_queue_listener: Optional[logging.handlers.QueueListener] = None


def init_worker_logging(queue: multiprocessing.Queue) -> None:
    """Initialize logging queue in worker process.
    
    Called by ProcessPoolExecutor initializer to set the shared queue
    in each worker process's module scope.
    
    Args:
        queue: The shared multiprocessing.Queue instance from main process.
    """
    global _log_queue
    _log_queue = queue


class ResilientQueueHandler(logging.handlers.QueueHandler):
    """QueueHandler that gracefully handles connection errors during shutdown."""
    
    def enqueue(self, record: logging.LogRecord) -> None:
        """Enqueue a log record, handling connection errors gracefully."""
        try:
            super().enqueue(record)
        except (BrokenPipeError, OSError, ConnectionError):
            pass


class LoggingService:
    """Service for centralized application logging.
    
    This service provides:
    - Console and/or file output (configurable)
    - Multiple log levels (DEBUG, INFO, WARNING, ERROR)
    - Rolling log files (size-based rotation)
    - Non-blocking async logging via QueueHandler/QueueListener
    - Thread-safe and process-safe operation
    
    This is a singleton service - use get_instance() to get the shared instance.
    All processes (main and workers) use QueueHandler to send logs to a shared queue.
    The main process runs QueueListener to consume from the queue and write to handlers.
    """
    
    _instance: Optional['LoggingService'] = None
    _lock = threading.Lock()
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the logging service.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self._logger: Optional[logging.Logger] = None
        self._initialized = False
        self._log_path: Optional[Path] = None
        self._instance_lock = threading.Lock()
        
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
            with cls._instance._instance_lock:
                cls._instance.config = config
                cls._instance._load_config()
                if cls._instance._initialized:
                    cls._instance.initialize()
        return cls._instance
    
    @classmethod
    def get_queue(cls) -> multiprocessing.Queue:
        """Get the shared log queue for this process.
        
        Creates the queue if it doesn't exist (for main process).
        Worker processes should have the queue set via initializer.
        
        Returns:
            The shared multiprocessing.Queue instance.
        """
        global _log_queue
        if _log_queue is None:
            _log_queue = multiprocessing.Queue()
        return _log_queue
    
    def _load_config(self) -> None:
        """Load logging configuration from config dictionary."""
        logging_config = self.config.get('logging', {})
        
        console_config = logging_config.get('console', {})
        self._console_enabled = console_config.get('enabled', True)
        self._console_level = console_config.get('level', 'INFO')
        
        file_config = logging_config.get('file', {})
        if 'enabled' in file_config:
            self._file_enabled = bool(file_config['enabled'])
        else:
            self._file_enabled = True
        self._file_level = file_config.get('level', 'DEBUG')
        self._log_filename = file_config.get('filename', 'cara.log')
        self._max_size_mb = file_config.get('max_size_mb', 10)
        self._backup_count = file_config.get('backup_count', 5)
    
    def initialize(self) -> None:
        """Initialize the logging service.
        
        Must be called before using the service. Sets up logger, handlers, and queue listener.
        Must be called with _instance_lock held.
        """
        global _log_queue, _queue_listener
        
        self._load_config()
        
        is_main_process = multiprocessing.parent_process() is None
        
        if self._initialized:
            if is_main_process and _queue_listener:
                _queue_listener.stop()
                _queue_listener = None
            
            if _log_queue is None:
                _log_queue = multiprocessing.Queue()
            
            if self._logger:
                for handler in self._logger.handlers[:]:
                    if isinstance(handler, (logging.handlers.QueueHandler, ResilientQueueHandler)):
                        self._logger.removeHandler(handler)
                queue_handler = ResilientQueueHandler(_log_queue)
                self._logger.addHandler(queue_handler)
            
            if is_main_process:
                handlers = []
                if self._console_enabled:
                    console_handler = logging.StreamHandler(sys.stderr)
                    console_handler.setLevel(self._get_log_level(self._console_level))
                    console_formatter = logging.Formatter(
                        '%(asctime)s [%(levelname)s] [Thread-%(thread)d] %(message)s',
                        datefmt='%H:%M:%S'
                    )
                    console_handler.setFormatter(console_formatter)
                    handlers.append(console_handler)
                
                if self._file_enabled is True:
                    try:
                        # Reuse existing log path if already set (to avoid creating new files on reinitialization)
                        if self._log_path is None:
                            date = datetime.now().strftime('%Y-%m-%d')
                            base_filename = self._log_filename
                            if '.' in base_filename:
                                name, ext = base_filename.rsplit('.', 1)
                                timestamped_filename = f"{name}_{date}.{ext}"
                            else:
                                timestamped_filename = f"{base_filename}_{date}"
                            
                            log_path, _ = resolve_data_file_path(timestamped_filename)
                            self._log_path = log_path
                        else:
                            log_path = self._log_path
                        
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        
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
                        handlers.append(file_handler)
                    except Exception as e:
                        print(f"Warning: Failed to initialize file logging: {e}", file=sys.stderr)
                
                if handlers:
                    _queue_listener = logging.handlers.QueueListener(_log_queue, *handlers, respect_handler_level=True)
                    _queue_listener.start()
            self._initialized = True
            return
        
        if not self._console_enabled and not self._file_enabled:
            self._initialized = True
            return
        
        self._logger = logging.getLogger('CARA')
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        
        if _log_queue is None:
            _log_queue = multiprocessing.Queue()
        
        queue_handler = ResilientQueueHandler(_log_queue)
        self._logger.addHandler(queue_handler)
        
        is_main_process = multiprocessing.parent_process() is None
        
        handlers = []
        
        # Only create console/file handlers in main process
        # Worker processes only use QueueHandler to send logs to the queue
        if is_main_process:
            if self._console_enabled:
                console_handler = logging.StreamHandler(sys.stderr)
                console_handler.setLevel(self._get_log_level(self._console_level))
                console_formatter = logging.Formatter(
                    '%(asctime)s [%(levelname)s] [Thread-%(thread)d] %(message)s',
                    datefmt='%H:%M:%S'
                )
                console_handler.setFormatter(console_formatter)
                handlers.append(console_handler)
            
            if self._file_enabled is True:
                try:
                    # Reuse existing log path if already set (to avoid creating new files on reinitialization)
                    if self._log_path is None:
                        date = datetime.now().strftime('%Y-%m-%d')
                        base_filename = self._log_filename
                        if '.' in base_filename:
                            name, ext = base_filename.rsplit('.', 1)
                            timestamped_filename = f"{name}_{date}.{ext}"
                        else:
                            timestamped_filename = f"{base_filename}_{date}"
                        
                        log_path, _ = resolve_data_file_path(timestamped_filename)
                        self._log_path = log_path
                    else:
                        log_path = self._log_path
                    
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    
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
                    handlers.append(file_handler)
                except Exception as e:
                    print(f"Warning: Failed to initialize file logging: {e}", file=sys.stderr)
        
        if is_main_process and _queue_listener is None and handlers:
            _queue_listener = logging.handlers.QueueListener(_log_queue, *handlers, respect_handler_level=True)
            _queue_listener.start()
        
        self._initialized = True
        
        # Only log file path in main process
        if is_main_process and self._file_enabled and self._log_path:
            self.debug(f"Log file path resolved: filename={self._log_filename}, path={self._log_path}")
    
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
    
    def _log(self, level: int, message: str, exc_info: Optional[Exception] = None) -> None:
        """Internal logging method.
        
        Args:
            level: Logging level constant.
            message: Log message.
            exc_info: Optional exception info for error logging.
        """
        if not self._initialized:
            with self._instance_lock:
                if not self._initialized:
                    self.initialize()
        
        if not self._console_enabled and not self._file_enabled:
            return
        
        if not self._initialized or not self._logger:
            return
        
        exc_info_param = exc_info
        if exc_info is not None and isinstance(exc_info, Exception):
            traceback = getattr(exc_info, '__traceback__', None)
            if traceback is not None:
                exc_info_param = (type(exc_info), exc_info, traceback)
            else:
                message = f"{message}\nException: {type(exc_info).__name__}: {exc_info}"
                exc_info_param = None
        
        try:
            record = self._logger.makeRecord(
                self._logger.name,
                level,
                __file__,
                0,
                message,
                (),
                exc_info_param
            )
        except Exception:
            return
        
        import threading
        if not hasattr(record, 'threadName') or not record.threadName:
            record.threadName = threading.current_thread().name
        if not hasattr(record, 'thread') or not record.thread:
            record.thread = threading.get_ident()
        
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
        
        Flushes all pending log messages and stops the queue listener.
        """
        global _queue_listener, _log_queue
        
        with self._instance_lock:
            if not self._initialized:
                return
            
            if _queue_listener:
                try:
                    _queue_listener.stop()
                    if hasattr(_queue_listener, '_thread') and _queue_listener._thread:
                        _queue_listener._thread.join(timeout=1.0)
                    else:
                        import time
                        time.sleep(0.2)
                except Exception:
                    pass
                _queue_listener = None
            
            if _log_queue:
                try:
                    _log_queue.put_nowait(None)
                    _log_queue.close()
                    _log_queue.join_thread()
                except Exception:
                    pass
                _log_queue = None
            
            if self._logger:
                for handler in self._logger.handlers[:]:
                    try:
                        handler.close()
                        self._logger.removeHandler(handler)
                    except Exception:
                        pass
            
            self._initialized = False

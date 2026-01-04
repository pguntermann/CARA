"""Base UCI communication layer for chess engines.

This module provides a common abstraction for UCI protocol communication,
allowing all engine services to share the same communication logic and
enabling easier debugging of UCI interactions.
"""

import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from enum import Enum

# Module-level debug callbacks (set from MainWindow)
_debug_outbound_callback: Optional[Callable[[], bool]] = None
_debug_inbound_callback: Optional[Callable[[], bool]] = None

# Thread-safe debug flags (updated from MainWindow)
_debug_outbound_enabled = False
_debug_inbound_enabled = False
_debug_lifecycle_enabled = False


def set_debug_callbacks(outbound_callback: Optional[Callable[[], bool]] = None,
                       inbound_callback: Optional[Callable[[], bool]] = None) -> None:
    """Set global debug callbacks for UCI communication.
    
    Args:
        outbound_callback: Callback to check if outbound debugging is enabled.
        inbound_callback: Callback to check if inbound debugging is enabled.
    """
    global _debug_outbound_callback, _debug_inbound_callback
    _debug_outbound_callback = outbound_callback
    _debug_inbound_callback = inbound_callback


def set_debug_flags(outbound_enabled: bool = False, inbound_enabled: bool = False, lifecycle_enabled: bool = False) -> None:
    """Set thread-safe debug flags for UCI communication.
    
    Args:
        outbound_enabled: True if outbound debugging is enabled.
        inbound_enabled: True if inbound debugging is enabled.
        lifecycle_enabled: True if lifecycle debugging is enabled.
    """
    global _debug_outbound_enabled, _debug_inbound_enabled, _debug_lifecycle_enabled
    _debug_outbound_enabled = outbound_enabled
    _debug_inbound_enabled = inbound_enabled
    _debug_lifecycle_enabled = lifecycle_enabled
    # Debug output to verify flags are being set (commented out for production)
    # import sys
    # print("DEBUG: set_debug_flags called - outbound=" + str(outbound_enabled) + ", inbound=" + str(inbound_enabled), file=sys.stderr, flush=True)


class UCICommand(Enum):
    """UCI protocol commands."""
    UCI = "uci"
    UCIOK = "uciok"
    ISREADY = "isready"
    READYOK = "readyok"
    POSITION = "position"
    GO = "go"
    STOP = "stop"
    QUIT = "quit"
    SETOPTION = "setoption"


class UCICommunicationService:
    """Service for UCI protocol communication with chess engines.
    
    This service handles the low-level UCI protocol communication, including:
    - Process spawning and management
    - UCI initialization
    - Command sending and response reading
    - Debug logging of all UCI interactions
    
    Other services should use this service for UCI protocol communication
    and implement higher-level logic like parsing info lines and managing
    search operations.
    """
    
    def __init__(self, engine_path: Path, enable_debug: bool = False, 
                 debug_callback: Optional[Callable[[str], None]] = None,
                 identifier: Optional[str] = None,
                 debug_outbound_callback: Optional[Callable[[], bool]] = None,
                 debug_inbound_callback: Optional[Callable[[], bool]] = None) -> None:
        """Initialize UCI communication.
        
        Args:
            engine_path: Path to UCI engine executable.
            enable_debug: If True, log all UCI commands and responses.
            debug_callback: Optional callback function for debug messages.
                           Called with debug message string.
            identifier: Optional identifier for this UCI communication instance
                       (e.g., "GameAnalysis", "Evaluation", "ManualAnalysis", "Validation").
                       Used in debug logs to identify which service/thread created this instance.
            debug_outbound_callback: Optional callback to check if outbound debugging is enabled.
                                     Returns True if outbound debugging should be active.
            debug_inbound_callback: Optional callback to check if inbound debugging is enabled.
                                    Returns True if inbound debugging should be active.
        """
        self.engine_path = engine_path
        self.enable_debug = enable_debug
        self.debug_callback = debug_callback
        self.identifier = identifier
        self.debug_outbound_callback = debug_outbound_callback
        self.debug_inbound_callback = debug_inbound_callback
        self.process: Optional[subprocess.Popen] = None
        self._initialized = False
        self._uciok_received = False
        self._crash_logged = False  # Track if crash has been logged to avoid duplicates
    
    def _debug_log(self, message: str, direction: str = "INFO") -> None:
        """Log debug message if debugging is enabled.
        
        Args:
            message: Debug message to log.
            direction: Direction of communication: "SEND", "RECV", or "INFO".
        """
        if self.enable_debug and self.debug_callback:
            timestamp = time.strftime("%H:%M:%S.%f")[:-3]  # milliseconds
            identifier_str = f"[{self.identifier}] " if self.identifier else ""
            formatted = f"[UCI {direction}] {identifier_str}{timestamp}: {message}"
            self.debug_callback(formatted)
    
    def _debug_lifecycle(self, event: str, details: str = "") -> None:
        """Log lifecycle event to console if lifecycle debugging is enabled.
        
        Args:
            event: Lifecycle event name (e.g., "STARTED", "STOPPED", "QUIT", "CRASHED").
            details: Optional additional details about the event.
        """
        try:
            if _debug_lifecycle_enabled:
                # Use datetime for timestamp with milliseconds
                now = datetime.now()
                timestamp = now.strftime("%H:%M:%S.") + str(now.microsecond // 1000).zfill(3)
                # Use string concatenation to avoid format string issues
                identifier_str = ("[" + str(self.identifier) + "] ") if self.identifier else ""
                thread_id = threading.get_ident()
                thread_str = (" [Thread-" + str(thread_id) + "]") if thread_id else ""
                pid_str = (" [PID:" + str(self.process.pid) + "]") if self.process else ""
                details_str = (" " + details) if details else ""
                formatted = "[UCI LIFECYCLE] " + identifier_str + timestamp + thread_str + pid_str + ": " + event + details_str
                print(formatted, flush=True)
        except Exception:
            # Silently ignore any errors in debug output to prevent breaking communication
            pass
    
    def _debug_console(self, message: str, direction: str) -> None:
        """Log debug message to console if console debugging is enabled.
        
        Args:
            message: Debug message to log.
            direction: Direction of communication: "SEND" (outbound) or "RECV" (inbound).
        """
        try:
            # Check if console debugging is enabled for this direction
            # Use thread-safe flags first (most reliable), then try callbacks as fallback
            should_log = False
            if direction == "SEND":
                # Check thread-safe flag first
                should_log = _debug_outbound_enabled
                # If flag is False, try callbacks as fallback
                if not should_log:
                    if self.debug_outbound_callback:
                        try:
                            should_log = self.debug_outbound_callback()
                        except Exception:
                            pass
                    elif _debug_outbound_callback:
                        try:
                            should_log = _debug_outbound_callback()
                        except Exception:
                            pass
            elif direction == "RECV":
                # Check thread-safe flag first
                should_log = _debug_inbound_enabled
                # If flag is False, try callbacks as fallback
                if not should_log:
                    if self.debug_inbound_callback:
                        try:
                            should_log = self.debug_inbound_callback()
                        except Exception:
                            pass
                    elif _debug_inbound_callback:
                        try:
                            should_log = _debug_inbound_callback()
                        except Exception:
                            pass
            
            if should_log:
                # Use datetime for timestamp with milliseconds
                now = datetime.now()
                timestamp = now.strftime("%H:%M:%S.") + str(now.microsecond // 1000).zfill(3)
                # Use string concatenation to avoid format string issues
                identifier_str = ("[" + str(self.identifier) + "] ") if self.identifier else ""
                thread_id = threading.get_ident()
                thread_str = (" [Thread-" + str(thread_id) + "]") if thread_id else ""
                # Use string concatenation instead of f-string to avoid format string issues
                formatted = "[UCI " + str(direction) + "] " + identifier_str + str(timestamp) + thread_str + ": " + str(message)
                print(formatted, flush=True)
        except Exception as e:
            # Silently ignore any errors in debug output to prevent breaking communication
            # But log to stderr for debugging
            import sys
            import traceback
            print("DEBUG: Error in _debug_console: " + str(e), file=sys.stderr, flush=True)
            print("DEBUG: Traceback: " + str(traceback.format_exc()), file=sys.stderr, flush=True)
    
    def spawn_process(self) -> bool:
        """Spawn the engine process.
        
        Returns:
            True if process spawned successfully, False otherwise.
        """
        try:
            self._debug_log(f"Spawning engine process: {self.engine_path}", "INFO")
            # Use binary mode to avoid Windows text mode blocking issues
            self.process = subprocess.Popen(
                [str(self.engine_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # Binary mode
                bufsize=0  # Unbuffered for immediate data availability
            )
            # Initialize binary read buffer for manual line splitting
            self._read_buffer = b''
            self._debug_log(f"Engine process spawned (PID: {self.process.pid})", "INFO")
            self._crash_logged = False  # Reset crash flag when engine starts
            self._debug_lifecycle("STARTED", "PID:" + str(self.process.pid))
            return True
        except Exception as e:
            self._debug_log(f"Failed to spawn engine process: {str(e)}", "INFO")
            return False
    
    def initialize_uci(self, timeout: float = 5.0, collect_lines: bool = False) -> tuple[bool, list[str]]:
        """Initialize UCI protocol with the engine.
        
        Args:
            timeout: Maximum time to wait for uciok response in seconds.
            collect_lines: If True, collect and return all lines read during initialization.
            
        Returns:
            Tuple of (success: bool, lines: list[str]). If collect_lines is False, lines is empty.
        """
        if not self.process:
            self._debug_log("Cannot initialize UCI: process not spawned", "INFO")
            return (False, [])
        
        try:
            # Send UCI command
            self.send_command("uci")
            
            # Wait for uciok
            start_time = time.time()
            uciok_received = False
            lines_collected = []
            
            while (time.time() - start_time) < timeout:
                if self.process.poll() is not None:
                    self._debug_log("Engine process terminated during UCI initialization", "INFO")
                    return (False, lines_collected if collect_lines else [])
                
                # Use read_line with short timeout to get debug console output
                line = self.read_line(timeout=0.1)
                if not line:
                    time.sleep(0.01)
                    continue
                
                if collect_lines:
                    lines_collected.append(line)
                
                if line == "uciok":
                    uciok_received = True
                    self._uciok_received = True
                    self._initialized = True
                    self._debug_log("UCI initialization complete", "INFO")
                    break
            
            if not uciok_received:
                self._debug_log(f"UCI initialization timeout (no uciok received within {timeout}s)", "INFO")
                return (False, lines_collected if collect_lines else [])
            
            return (True, lines_collected if collect_lines else [])
        except Exception as e:
            self._debug_log(f"Error during UCI initialization: {str(e)}", "INFO")
            return (False, [])
    
    def send_command(self, command: str) -> bool:
        """Send a command to the engine.
        
        Args:
            command: UCI command string (without newline).
            
        Returns:
            True if command sent successfully, False otherwise.
        """
        if not self.process or self.process.poll() is not None:
            self._debug_log(f"Cannot send command '{command}': process not available", "INFO")
            return False
        
        try:
            self._debug_log(command, "SEND")
            self._debug_console(command, "SEND")
            # Encode string to bytes for binary mode
            self.process.stdin.write(f"{command}\n".encode('utf-8'))
            self.process.stdin.flush()
            return True
        except Exception as e:
            self._debug_log(f"Error sending command '{command}': {str(e)}", "INFO")
            return False
    
    def read_line(self, timeout: float) -> Optional[str]:
        """Read a line from engine stdout using binary mode with manual line buffering.
        
        This avoids Windows text mode blocking issues while maintaining zero latency
        when data is available.
        
        Args:
            timeout: Timeout in seconds (required). Returns None if no line received within timeout.
            
        Returns:
            Line string (stripped) or None if timeout/error.
        """
        if not self.process or self.process.poll() is not None:
            return None
        
        # Ensure buffer exists
        if not hasattr(self, '_read_buffer'):
            self._read_buffer = b''
        
        try:
            # Fast path: check buffer first (zero latency if line already buffered)
            if b'\n' in self._read_buffer:
                newline_pos = self._read_buffer.find(b'\n')
                line_bytes = self._read_buffer[:newline_pos]
                self._read_buffer = self._read_buffer[newline_pos + 1:]
                try:
                    line = line_bytes.decode('utf-8', errors='replace').rstrip('\r').strip()
                    if line:
                        self._debug_log(line, "RECV")
                        self._debug_console(line, "RECV")
                        return line
                except Exception as e:
                    self._debug_log(f"Error decoding line: {str(e)}", "INFO")
                    return None
            
            # Non-blocking read with timeout
            # Note: timeout is required - all callers provide a timeout value
            if timeout is None:
                raise ValueError("read_line() requires a timeout value")
            
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                # Read chunk (returns immediately, empty bytes if no data)
                chunk = self.process.stdout.read(1024)
                if chunk:
                    self._read_buffer += chunk
                    # Check if we now have a complete line
                    if b'\n' in self._read_buffer:
                        newline_pos = self._read_buffer.find(b'\n')
                        line_bytes = self._read_buffer[:newline_pos]
                        self._read_buffer = self._read_buffer[newline_pos + 1:]
                        try:
                            line = line_bytes.decode('utf-8', errors='replace').rstrip('\r').strip()
                            if line:
                                self._debug_log(line, "RECV")
                                self._debug_console(line, "RECV")
                                return line
                        except Exception as e:
                            self._debug_log(f"Error decoding line: {str(e)}", "INFO")
                            return None
                else:
                    # No data available - check timeout immediately (no sleep)
                    if (time.time() - start_time) >= timeout:
                        return None
                    # Continue loop immediately - timeout check limits iterations
            return None
        except Exception as e:
            self._debug_log(f"Error reading line: {str(e)}", "INFO")
            return None
    
    def wait_for_readyok(self, timeout: float = 5.0) -> bool:
        """Wait for readyok response after sending isready.
        
        Args:
            timeout: Maximum time to wait for readyok in seconds.
            
        Returns:
            True if readyok received, False if timeout or error.
        """
        if not self.process or self.process.poll() is not None:
            return False
        
        try:
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                if self.process.poll() is not None:
                    return False
                
                line = self.read_line(timeout=0.1)
                if not line:
                    time.sleep(0.01)
                    continue
                
                if line.strip() == "readyok":
                    return True
            
            # Timeout
            return False
        except Exception:
            return False
    
    def set_option(self, name: str, value: Any, wait_for_ready: bool = False, timeout: float = 5.0) -> bool:
        """Set a UCI option.
        
        Args:
            name: Option name (e.g., "Threads", "MultiPV").
            value: Option value.
            wait_for_ready: If True, send isready and wait for readyok after setting option.
                          Default is False - call confirm_ready() after setting all options.
            timeout: Maximum time to wait for readyok if wait_for_ready is True.
            
        Returns:
            True if option set successfully (and readyok received if wait_for_ready is True), False otherwise.
        """
        command = f"setoption name {name} value {value}"
        success = self.send_command(command)
        if not success:
            return False
        
        if wait_for_ready:
            # Send isready and wait for readyok to ensure engine has processed the option
            if not self.send_command("isready"):
                return False
            return self.wait_for_readyok(timeout=timeout)
        
        return True
    
    def confirm_ready(self, timeout: float = 5.0) -> bool:
        """Send isready and wait for readyok to confirm engine is ready.
        
        This should be called after setting multiple options to ensure the engine
        has processed all option changes. This is more efficient than calling
        set_option with wait_for_ready=True for each option.
        
        Args:
            timeout: Maximum time to wait for readyok in seconds.
            
        Returns:
            True if readyok received, False if timeout or error.
        """
        if not self.process or self.process.poll() is not None:
            return False
        
        if not self.send_command("isready"):
            return False
        
        return self.wait_for_readyok(timeout=timeout)
    
    def set_position(self, fen: str) -> bool:
        """Set the position on the engine board.
        
        Args:
            fen: FEN string of the position.
            
        Returns:
            True if position set successfully, False otherwise.
        """
        command = f"position fen {fen}"
        return self.send_command(command)
    
    def start_search(self, depth: int = 0, movetime: int = 0, **kwargs) -> bool:
        """Start a search with the engine.
        
        Args:
            depth: Maximum depth to search (0 = unlimited).
            movetime: Maximum time per move in milliseconds (0 = unlimited).
            **kwargs: Additional search parameters (e.g., nodes=1000000).
                     Parameters with value 0 are automatically omitted.
            
        Returns:
            True if search started successfully, False otherwise.
        """
        # Build go command, omitting parameters with value 0
        parts = ["go"]
        
        # Handle depth parameter (skip if 0)
        if depth > 0:
            parts.append(f"depth {depth}")
        
        # Handle movetime parameter (skip if 0)
        if movetime > 0:
            parts.append(f"movetime {movetime}")
        
        # Handle other parameters (skip if 0)
        for key, value in kwargs.items():
            # Skip parameters with value 0
            if value != 0:
                parts.append(f"{key} {value}")
        
        # If no parameters were added (all were 0), default to infinite search
        if len(parts) == 1:
            command = "go infinite"
        else:
            command = " ".join(parts)
        
        return self.send_command(command)
    
    def stop_search(self) -> bool:
        """Stop the current search.
        
        Returns:
            True if stop command sent successfully, False otherwise.
        """
        success = self.send_command("stop")
        if success:
            self._debug_lifecycle("STOPPED", "Search stopped")
        return success
    
    def quit_engine(self) -> bool:
        """Send quit command to engine.
        
        Returns:
            True if quit command sent successfully, False otherwise.
        """
        success = self.send_command("quit")
        if success:
            self._debug_lifecycle("QUIT", "Quit command sent")
        return success
    
    def is_initialized(self) -> bool:
        """Check if UCI is initialized.
        
        Returns:
            True if UCI initialized, False otherwise.
        """
        return self._initialized and self._uciok_received
    
    def is_process_alive(self) -> bool:
        """Check if engine process is alive.
        
        Returns:
            True if process is running, False otherwise.
        """
        if self.process is None:
            return False
        
        poll_result = self.process.poll()
        if poll_result is not None:
            # Process has terminated - check if this is a crash (unexpected termination)
            if self._initialized and not self._crash_logged:
                # Engine was initialized, so this is likely a crash
                # Only log once to avoid spam
                self._crash_logged = True
                self._debug_lifecycle("CRASHED", "Exit code:" + str(poll_result))
            return False
        
        return True
    
    def get_process_pid(self) -> Optional[int]:
        """Get the process ID of the engine process.
        
        Returns:
            Process ID if process exists, None otherwise.
        """
        if self.process:
            return self.process.pid
        return None
    
    def wait_for_process(self, timeout: float = 2.0) -> bool:
        """Wait for process to terminate.
        
        Args:
            timeout: Maximum time to wait in seconds.
            
        Returns:
            True if process terminated within timeout, False otherwise.
        """
        if not self.process:
            return True
        
        try:
            self.process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
    
    def kill_process(self) -> None:
        """Kill the engine process."""
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                self.process.wait()
                self._debug_log("Engine process killed", "INFO")
            except Exception as e:
                self._debug_log(f"Error killing process: {str(e)}", "INFO")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self.process:
            was_alive = self.process.poll() is None
            if was_alive:
                try:
                    self.quit_engine()
                    if not self.wait_for_process(timeout=2.0):
                        self.kill_process()
                        self._debug_lifecycle("KILLED", "Process killed after timeout")
                except Exception:
                    self.kill_process()
                    self._debug_lifecycle("KILLED", "Process killed due to exception")
            else:
                # Process already terminated
                exit_code = self.process.poll()
                if exit_code is not None and self._initialized:
                    self._debug_lifecycle("TERMINATED", "Exit code:" + str(exit_code))
            
            # Close pipes
            try:
                if self.process.stdin:
                    self.process.stdin.close()
            except Exception:
                pass
            
            try:
                if self.process.stdout:
                    self.process.stdout.close()
            except Exception:
                pass
            
            try:
                if self.process.stderr:
                    self.process.stderr.close()
            except Exception:
                pass
            
            self.process = None
        
        self._initialized = False
        self._uciok_received = False
        self._debug_log("UCI communication cleaned up", "INFO")


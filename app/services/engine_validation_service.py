"""Engine validation service for validating UCI chess engines."""

import sys
import time
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Callable, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import uuid

from app.services.uci_communication_service import UCICommunicationService
from app.services.engine_parameters_service import EngineParametersService


@dataclass
class EngineValidationResult:
    """Result of engine validation."""
    
    is_valid: bool
    name: str
    author: str
    version: str
    error_message: str


class EngineValidationService:
    """Service for validating UCI chess engines.
    
    This service communicates with engine executables via the UCI protocol
    to validate that they are UCI-compliant engines and extract their
    information (name, author, version).
    """
    
    # UCI protocol constants
    ID_NAME_PREFIX = "id name"
    ID_AUTHOR_PREFIX = "id author"
    OPTION_PREFIX = "option"
    
    # Validation timeout (seconds)
    VALIDATION_TIMEOUT = 5.0
    
    @staticmethod
    def validate_engine(engine_path: Path, 
                       debug_callback: Optional[Callable[[str], None]] = None,
                       save_to_file: bool = True) -> EngineValidationResult:
        """Validate an engine executable via UCI protocol.
        
        Args:
            engine_path: Path to engine executable.
            debug_callback: Optional callback for debug messages.
            save_to_file: Whether to save the parsed options to engine_parameters.json.
                         If False, only validates the engine without saving options.
            
        Returns:
            EngineValidationResult with validation status and engine info.
        """
        # Check if file exists
        if not engine_path.exists():
            return EngineValidationResult(
                is_valid=False,
                name="",
                author="",
                version="",
                error_message=f"Engine file not found: {engine_path}"
            )
        
        # Check if file is executable (basic check)
        if not engine_path.is_file():
            return EngineValidationResult(
                is_valid=False,
                name="",
                author="",
                version="",
                error_message=f"Path is not a file: {engine_path}"
            )
        
        try:
            # Create UCI communication service instance
            uci = UCICommunicationService(
                engine_path, 
                debug_callback=debug_callback,
                identifier="Validation"
            )
            
            # Spawn engine process
            if not uci.spawn_process():
                return EngineValidationResult(
                    is_valid=False,
                    name="",
                    author="",
                    version="",
                    error_message="Failed to spawn engine process"
                )
            
            # Initialize UCI and collect lines
            success, lines = uci.initialize_uci(timeout=EngineValidationService.VALIDATION_TIMEOUT, collect_lines=True)
            if not success:
                uci.cleanup()
                return EngineValidationResult(
                    is_valid=False,
                    name="",
                    author="",
                    version="",
                    error_message="Engine did not respond with 'uciok' (timeout or invalid UCI engine)"
                )
            
            # Parse collected lines for name, author, and options
            name = ""
            author = ""
            uciok_received = False
            options: List[Dict[str, Any]] = []
            
            for line in lines:
                # Parse id name
                if line.startswith(EngineValidationService.ID_NAME_PREFIX):
                    name = line[len(EngineValidationService.ID_NAME_PREFIX):].strip()
                
                # Parse id author
                elif line.startswith(EngineValidationService.ID_AUTHOR_PREFIX):
                    author = line[len(EngineValidationService.ID_AUTHOR_PREFIX):].strip()
                
                # Parse option lines
                elif line.startswith(EngineValidationService.OPTION_PREFIX):
                    option = EngineValidationService._parse_option_line(line)
                    if option:
                        options.append(option)
                
                # Check for uciok
                elif line == "uciok":
                    uciok_received = True
            
            # Cleanup
            uci.cleanup()
            
            # Check validation result
            if not uciok_received:
                return EngineValidationResult(
                    is_valid=False,
                    name="",
                    author="",
                    version="",
                    error_message="Engine did not respond with 'uciok' (timeout or invalid UCI engine)"
                )
            
            if not name:
                return EngineValidationResult(
                    is_valid=False,
                    name="",
                    author="",
                    version="",
                    error_message="Engine did not provide 'id name' response"
                )
            
            # Extract version from author string (common pattern: "Engine Name version")
            version = EngineValidationService._extract_version(author, name)
            
            # Store engine options if validation was successful and save_to_file is True
            if uciok_received and name and save_to_file:
                EngineValidationService._store_engine_options(engine_path, options)
            
            return EngineValidationResult(
                is_valid=True,
                name=name,
                author=author,
                version=version,
                error_message=""
            )
            
        except subprocess.TimeoutExpired:
            return EngineValidationResult(
                is_valid=False,
                name="",
                author="",
                version="",
                error_message="Engine validation timed out"
            )
        except Exception as e:
            return EngineValidationResult(
                is_valid=False,
                name="",
                author="",
                version="",
                error_message=f"Error validating engine: {str(e)}"
            )
    
    @staticmethod
    def _extract_version(author: str, name: str) -> str:
        """Extract version string from author or name.
        
        Args:
            author: Author string from engine.
            name: Name string from engine.
            
        Returns:
            Version string if found, empty string otherwise.
        """
        import re
        
        # Common version patterns: "v1.2.3", "version 15.0", "15.0", "1.2.3"
        version_patterns = [
            r'v?(\d+\.\d+(?:\.\d+)?)',
            r'version\s+(\d+\.\d+(?:\.\d+)?)',
            r'(\d+\.\d+(?:\.\d+)?)',
        ]
        
        # Try author first, then name
        for text in [author, name]:
            if not text:
                continue
            
            for pattern in version_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1)
        
        return ""
    
    @staticmethod
    def _parse_option_line(line: str) -> Optional[Dict[str, Any]]:
        """Parse a UCI option line.
        
        UCI option format:
        option name <name> type <type> [default <default>] [min <min>] [max <max>] [var <value1> var <value2> ...]
        
        Args:
            line: Option line from engine (e.g., "option name Threads type spin default 1 min 1 max 512").
            
        Returns:
            Dictionary with option data, or None if parsing failed.
        """
        if not line.startswith(EngineValidationService.OPTION_PREFIX):
            return None
        
        # Remove "option" prefix
        line = line[len(EngineValidationService.OPTION_PREFIX):].strip()
        
        option: Dict[str, Any] = {
            "name": "",
            "type": "",
            "default": None,
            "min": None,
            "max": None,
            "var": []
        }
        
        # Parse tokens
        tokens = line.split()
        i = 0
        
        while i < len(tokens):
            if tokens[i] == "name" and i + 1 < len(tokens):
                # Option name can contain spaces, so collect all tokens until "type"
                name_parts = []
                i += 1
                while i < len(tokens) and tokens[i] != "type":
                    name_parts.append(tokens[i])
                    i += 1
                option["name"] = " ".join(name_parts)
                continue
            
            elif tokens[i] == "type" and i + 1 < len(tokens):
                option["type"] = tokens[i + 1]
                i += 2
                continue
            
            elif tokens[i] == "default" and i + 1 < len(tokens):
                default_value = tokens[i + 1]
                # Try to convert to appropriate type
                if option["type"] == "spin":
                    try:
                        option["default"] = int(default_value)
                    except ValueError:
                        option["default"] = default_value
                elif option["type"] == "check":
                    option["default"] = default_value.lower() == "true"
                else:
                    option["default"] = default_value
                i += 2
                continue
            
            elif tokens[i] == "min" and i + 1 < len(tokens):
                try:
                    option["min"] = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            
            elif tokens[i] == "max" and i + 1 < len(tokens):
                try:
                    option["max"] = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            
            elif tokens[i] == "var" and i + 1 < len(tokens):
                # Collect var value (var keyword followed by value)
                i += 1
                if i < len(tokens):
                    option["var"].append(tokens[i])
                    i += 1
                continue
            
            i += 1
        
        # Validate that we have at least name and type
        if not option["name"] or not option["type"]:
            return None
        
        return option
    
    @staticmethod
    def refresh_engine_options(engine_path: Path,
                              debug_callback: Optional[Callable[[str], None]] = None,
                              save_to_file: bool = True) -> Tuple[bool, List[Dict[str, Any]]]:
        """Refresh engine options by re-querying the engine via UCI.
        
        This method re-connects to an already-validated engine and re-parses
        its options, optionally updating the stored options. Useful for refreshing defaults
        or when engine options may have changed.
        
        Args:
            engine_path: Path to engine executable.
            debug_callback: Optional callback for debug messages.
            save_to_file: Whether to save the refreshed options to engine_parameters.json.
                         If False, only returns the parsed options without saving.
            
        Returns:
            Tuple of (success: bool, options: List[Dict[str, Any]]).
            If successful, returns (True, options_list). Otherwise (False, []).
        """
        # Check if file exists
        if not engine_path.exists() or not engine_path.is_file():
            return (False, [])
        
        try:
            # Create UCI communication service instance
            uci = UCICommunicationService(
                engine_path,
                debug_callback=debug_callback,
                identifier="RefreshOptions"
            )
            
            # Spawn engine process
            if not uci.spawn_process():
                return (False, [])
            
            # Initialize UCI and collect lines
            success, lines = uci.initialize_uci(timeout=EngineValidationService.VALIDATION_TIMEOUT, collect_lines=True)
            if not success:
                uci.cleanup()
                return (False, [])
            
            # Parse collected lines for options
            options: List[Dict[str, Any]] = []
            for line in lines:
                if line.startswith(EngineValidationService.OPTION_PREFIX):
                    option = EngineValidationService._parse_option_line(line)
                    if option:
                        options.append(option)
            
            # Cleanup
            uci.cleanup()
            
            # Store options if parsing was successful and save_to_file is True
            if options and save_to_file:
                EngineValidationService._store_engine_options(engine_path, options)
            
            return (True, options)
            
        except Exception as e:
            print(f"Warning: Failed to refresh engine options: {e}", file=sys.stderr)
            return (False, [])
    
    @staticmethod
    def _store_engine_options(engine_path: Path, options: List[Dict[str, Any]]) -> None:
        """Store engine options in engine_parameters.json.
        
        Args:
            engine_path: Path to engine executable.
            options: List of parsed option dictionaries.
        """
        try:
            service = EngineParametersService.get_instance()
            service.load()
            
            # Convert Path to string for JSON storage
            engine_path_str = str(engine_path)
            
            # Store options
            service.set_engine_options(engine_path_str, options)
        except Exception as e:
            # Don't fail validation if storing options fails
            print(f"Warning: Failed to store engine options: {e}", file=sys.stderr)


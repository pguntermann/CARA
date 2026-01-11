"""Service for checking if a newer version of the application is available."""

import re
import requests
from typing import Tuple, Optional, List


class VersionCheckService:
    """Service for checking if a newer version is available from a remote source."""
    
    DEFAULT_TIMEOUT = 10  # seconds
    
    @staticmethod
    def check_for_updates(current_version: str, url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Optional[bool], Optional[str], Optional[str]]:
        """Check if a newer version is available.
        
        Args:
            current_version: Current application version (e.g., "2.5.3").
            url: URL to fetch the remote version information from.
            timeout: Request timeout in seconds (default: 10).
            
        Returns:
            Tuple of (success, is_newer, remote_version, error_message):
            - success: True if the check completed (regardless of result), False if an error occurred
            - is_newer: True if remote version is newer, False if same or older, None if check failed
            - remote_version: Remote version string if found, None otherwise
            - error_message: Error message if check failed, None otherwise
        """
        try:
            # Fetch the remote page
            headers = {
                "User-Agent": f"CARA/{current_version}",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # Parse HTML to find version
            html_content = response.text
            
            # Look for version in <p class="version">Version X.X.X</p> pattern
            version_pattern = r'<p\s+class=["\']version["\']>Version\s+([\d.]+)</p>'
            match = re.search(version_pattern, html_content, re.IGNORECASE)
            
            if not match:
                # Try alternative pattern: just "Version X.X.X" anywhere
                version_pattern_alt = r'Version\s+([\d.]+)'
                match = re.search(version_pattern_alt, html_content, re.IGNORECASE)
            
            if not match:
                return (False, None, None, "Could not find version information on remote page")
            
            remote_version_str = match.group(1).strip()
            
            # Compare versions (semantic versioning: major.minor.patch)
            try:
                is_newer = VersionCheckService._compare_versions(current_version, remote_version_str)
                return (True, is_newer, remote_version_str, None)
            except Exception as e:
                return (False, None, remote_version_str, f"Error comparing versions: {str(e)}")
                
        except requests.exceptions.RequestException as e:
            return (False, None, None, f"Network error: {str(e)}")
        except Exception as e:
            return (False, None, None, f"Unexpected error: {str(e)}")
    
    @staticmethod
    def _compare_versions(current: str, remote: str) -> bool:
        """Compare two version strings (semantic versioning: major.minor.patch).
        
        Args:
            current: Current version string (e.g., "2.5.3").
            remote: Remote version string (e.g., "2.5.4").
            
        Returns:
            True if remote version is newer than current version, False otherwise.
        """
        def version_tuple(v: str) -> Tuple[int, int, int]:
            """Convert version string to tuple of integers for comparison."""
            parts = v.split('.')
            # Pad with zeros if needed (e.g., "2.5" -> (2, 5, 0))
            while len(parts) < 3:
                parts.append('0')
            try:
                return tuple(int(part) for part in parts[:3])
            except ValueError:
                # If parsing fails, return (0, 0, 0) as fallback
                return (0, 0, 0)
        
        current_tuple = version_tuple(current)
        remote_tuple = version_tuple(remote)
        
        return remote_tuple > current_tuple


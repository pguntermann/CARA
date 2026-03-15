"""Shared compression and encoding helpers for PGN custom tags (CARAAnnotations, CARAAnalysisData, CARANotes).

Used by storage services to avoid duplicating gzip+base64+checksum logic.
"""

import gzip
import zlib
import base64
import hashlib
from typing import Tuple


def decode_and_decompress(encoded: str) -> bytes:
    """Decode base64 and decompress gzip payload.

    Args:
        encoded: Base64-encoded gzip payload (ascii string).

    Returns:
        Decompressed bytes (e.g. UTF-8 text).

    Raises:
        ValueError: If decoding or decompression fails.
    """
    try:
        compressed = base64.b64decode(encoded.encode("ascii"))
    except Exception as e:
        raise ValueError(f"Base64 decode failed: {e}") from e
    try:
        return gzip.decompress(compressed)
    except (gzip.BadGzipFile, OSError, zlib.error) as e:
        raise ValueError(f"Decompression failed: {e}") from e


def compress_and_encode(data: bytes, compresslevel: int = 9) -> str:
    """Compress with gzip and encode as base64.

    Args:
        data: Raw bytes to compress (e.g. UTF-8 text).
        compresslevel: gzip compression level 1–9 (default 9).

    Returns:
        Base64-encoded gzip payload (ascii string).
    """
    compressed = gzip.compress(data, compresslevel=compresslevel)
    return base64.b64encode(compressed).decode("ascii")


def compute_checksum(data: bytes) -> str:
    """Compute SHA256 hex digest of data.

    Args:
        data: Bytes to hash (e.g. UTF-8 text).

    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(data).hexdigest()


def decode_and_decompress_to_str(encoded: str, encoding: str = "utf-8") -> str:
    """Decode, decompress, and decode bytes to string.

    Args:
        encoded: Base64-encoded gzip payload.
        encoding: Text encoding (default utf-8).

    Returns:
        Decompressed text string.

    Raises:
        ValueError: If decoding or decompression fails.
    """
    return decode_and_decompress(encoded).decode(encoding)


def compress_and_encode_from_str(text: str, encoding: str = "utf-8", compresslevel: int = 9) -> str:
    """Encode string to bytes, compress, and base64-encode.

    Args:
        text: Text to store.
        encoding: Text encoding (default utf-8).
        compresslevel: gzip compression level 1–9.

    Returns:
        Base64-encoded gzip payload.
    """
    return compress_and_encode(text.encode(encoding), compresslevel=compresslevel)

"""Service for storing and loading Chess Log moments in PGN tags."""

import hashlib
import json
import uuid
from typing import Dict, List, Optional, Any
from io import StringIO
from datetime import datetime, timezone

import chess.pgn

from app.models.database_model import GameData
from app.services.pgn_service import PgnService
from app.services.logging_service import LoggingService
from app.utils.pgn_tag_compression import (
    decode_and_decompress_to_str,
    compress_and_encode_from_str,
    compute_checksum,
)
from app.utils.pgn_variation_path import decode_path, node_at_path


class ChessLogStorageService:
    """Service for storing and loading Chess Log moments in PGN tags.

    Uses [CARAChessLog "..."] with gzip+base64 encoding,
    [CARAChessLogInfo "..."] for metadata, and [CARAChessLogChecksum "..."]
    for integrity verification — same pattern as CARAAnnotations / CARANotes.

    Storage schema (before compression):
        {"_v": 1, "paths": {path_key: [entry, ...]}, "nag_shown": true,
         "_check_run": {"model": "...", "date": "2026-10-30T..."}}

    "nag_shown" is omitted when False (backward-compatible; readers default to False
    via .get()).  It records that the user has already been shown the "more than three
    moments?" nag for this game so it is suppressed on future saves/sessions.

    "_check_run" is omitted when absent; written/preserved by store_tags.  Records the
    AI model label and UTC ISO-8601 timestamp of the most recent Check Logs run that
    touched this game.  Entries carry "check_hash" (first 16 hex chars of
    sha256(why.strip())) when they have been classified by Check Logs.

    One path key = one moment. A path's list may hold multiple entries so that
    a CCT tag with two letters (both apply to the same moment) costs one moment
    against the 3-moment cap, not two.  count_tags() counts paths, not entries.

    For 3x3 moments, cat is one of "Why1", "Why2", "Why3", "Why4" and why holds
    the answer text.  A single 3x3 moment stores up to four entries (one per Why
    answered), all sharing the same path key.  Insertion order is preserved by
    json.dumps/loads and Python dicts (3.7+), so Why1 always precedes Why2,
    Why3, and Why4 when loaded back.  preset="3x3" on all four entries.
    """

    TAG_NAME = "CARAChessLog"
    TAG_INFO = "CARAChessLogInfo"
    TAG_CHECKSUM = "CARAChessLogChecksum"

    @staticmethod
    def has_chess_log_tags(game: GameData) -> bool:
        """Return True if game has a CARAChessLog tag."""
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
            return chess_game is not None and ChessLogStorageService.TAG_NAME in chess_game.headers
        except Exception:
            return False

    @staticmethod
    def has_moments(pgn_or_headers) -> bool:
        """Return True only when the game holds at least one valid Chess Log moment.

        Accepts either:
        - A PGN string (str): full text of one game, parsed with chess.pgn.read_game.
        - A dict-like headers object (chess.pgn.Headers or dict): used directly,
          avoiding a second parse when the caller already has the game in memory.

        Returns False for no tag, empty payload, corrupt tag (checksum mismatch or
        bad payload), or any error.  Never modifies any game object or PGN text.
        Called from pgn_service._extract_game_data to set has_chess_log_tags at
        database open time.
        """
        try:
            if isinstance(pgn_or_headers, str):
                if ChessLogStorageService.TAG_NAME not in pgn_or_headers:
                    return False
                chess_game = chess.pgn.read_game(StringIO(pgn_or_headers))
                if chess_game is None:
                    return False
                headers = chess_game.headers
            else:
                headers = pgn_or_headers
            if ChessLogStorageService.TAG_NAME not in headers:
                return False
            encoded = headers[ChessLogStorageService.TAG_NAME]
            json_text = decode_and_decompress_to_str(encoded)
            if ChessLogStorageService.TAG_CHECKSUM in headers:
                stored = headers[ChessLogStorageService.TAG_CHECKSUM]
                if compute_checksum(json_text.encode("utf-8")) != stored:
                    return False
            payload = json.loads(json_text)
            paths_data = payload.get("paths", {})
            return ChessLogStorageService.count_tags(paths_data) > 0
        except Exception:
            return False

    @staticmethod
    def load_tags(game: GameData) -> Dict[str, List[Dict[str, Any]]]:
        """Load Chess Log moments from game PGN.

        Returns {path_key: [entry, ...]}. Returns {} on missing tag, checksum
        mismatch, or any error.  On a corrupt tag, logs a warning and returns {}
        without modifying game.pgn — the corrupt tag stays until the game is next
        saved (store_tags overwrites it; clear_tags removes it).
        Does NOT modify game.has_chess_log_tags or game.pgn — this is a pure read.
        """
        if game is None:
            return {}
        if not hasattr(game, "pgn") or game.pgn is None:
            return {}
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
            if not chess_game or ChessLogStorageService.TAG_NAME not in chess_game.headers:
                return {}
            encoded = chess_game.headers[ChessLogStorageService.TAG_NAME]
            json_text = decode_and_decompress_to_str(encoded)
            if ChessLogStorageService.TAG_CHECKSUM in chess_game.headers:
                stored = chess_game.headers[ChessLogStorageService.TAG_CHECKSUM]
                if compute_checksum(json_text.encode("utf-8")) != stored:
                    LoggingService.get_instance().warning(
                        "Chess Log checksum mismatch — corrupt tag left in PGN; "
                        "will be replaced on next save."
                    )
                    return {}
            payload = json.loads(json_text)
            paths_data: Dict[str, List[Dict[str, Any]]] = payload.get("paths", {})
            return paths_data
        except ValueError:
            LoggingService.get_instance().warning(
                "Chess Log payload decode error — corrupt tag left in PGN; "
                "will be replaced on next save."
            )
            return {}
        except Exception:
            return {}

    @staticmethod
    def load_resolved_paths(game: GameData) -> Dict[str, List[Dict[str, Any]]]:
        """Load Chess Log moments, hiding path_keys that don't resolve in game's move tree.

        Returns only the path_keys whose decoded paths exist as nodes in the parsed
        chess_game.  Orphans are logged at WARNING and excluded from the returned dict,
        but they remain in the on-disk PGN (use load_tags for the byte-for-byte full
        dict).  This is the view consumed by all feature code; load_tags is the view
        used for save-time round-trip preservation.
        """
        full = ChessLogStorageService.load_tags(game)
        if not full:
            return full
        if not hasattr(game, "pgn") or not game.pgn:
            return full
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
        except Exception:
            return full
        if not chess_game:
            return full
        resolved: Dict[str, List[Dict[str, Any]]] = {}
        for path_key, entries in full.items():
            path = decode_path(path_key)
            if path is None or node_at_path(chess_game, path) is None:
                preset_set = sorted({e.get("preset", "") for e in (entries or [])})
                LoggingService.get_instance().warning(
                    f"Chess Log orphan path_key skipped on load: "
                    f"game#{getattr(game, 'game_number', '?')}, "
                    f"path_key={path_key!r}, presets={preset_set}, "
                    f"entries={len(entries or [])}"
                )
            else:
                resolved[path_key] = entries
        return resolved

    @staticmethod
    def compute_check_hash(why_text: str) -> str:
        """Return the first 16 hex chars of sha256(why_text.strip()).

        Used for both writing ``check_hash`` entries and verifying them.
        Always call this helper; never inline the hash computation.
        """
        return hashlib.sha256(why_text.strip().encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def is_entry_checked(entry: Dict[str, Any]) -> bool:
        """Return True when this entry counts as 'checked' for the unchecked warning.

        Checked when any of these hold:
        - ``check_hash`` present and sha256(why.strip())[:16] matches it.
        - ``is_shallow`` or ``is_vague`` present (legacy: flag proves classification).
        - ``ignore_shallow`` is honoured (a classified-then-ignored entry; Correction 4).
        """
        why = (entry.get("why") or "").strip()
        stored_hash = entry.get("check_hash")
        if stored_hash:
            return ChessLogStorageService.compute_check_hash(why) == stored_hash
        if entry.get("is_shallow") or entry.get("is_vague"):
            return True
        return ChessLogStorageService.is_entry_ignore_honoured(entry)

    @staticmethod
    def entry_has_flag(entry: Dict[str, Any]) -> bool:
        """Return True if this entry carries a Shallow or Vague flag (Ignored counts).

        This is the shared predicate used by both compute_narrative_counts (stats
        service) and get_shallow_vague_keys (chess_log_controller) — they must agree.
        check_hash is not consulted; only is_shallow/is_vague matter here.
        """
        return bool(entry.get("is_shallow")) or bool(entry.get("is_vague"))

    @staticmethod
    def load_nag_shown(game: GameData) -> bool:
        """Read the nag_shown flag from the CARAChessLog payload.

        Returns False on missing tag, missing key, or any error.  Does not
        re-verify the checksum — callers should call load_tags first if data
        integrity matters; a corrupt tag means load_tags already stripped it.
        """
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
            if not chess_game or ChessLogStorageService.TAG_NAME not in chess_game.headers:
                return False
            encoded = chess_game.headers[ChessLogStorageService.TAG_NAME]
            json_text = decode_and_decompress_to_str(encoded)
            payload = json.loads(json_text)
            return bool(payload.get("nag_shown", False))
        except Exception:
            return False

    @staticmethod
    def load_check_run(game: GameData) -> Optional[Dict[str, Any]]:
        """Read the _check_run dict from the CARAChessLog payload.

        Returns None on missing tag, missing key, or any error.
        """
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return None
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
            if not chess_game or ChessLogStorageService.TAG_NAME not in chess_game.headers:
                return None
            encoded = chess_game.headers[ChessLogStorageService.TAG_NAME]
            json_text = decode_and_decompress_to_str(encoded)
            payload = json.loads(json_text)
            return payload.get("_check_run") or None
        except Exception:
            return None

    @staticmethod
    def store_tags(
        game: GameData,
        paths_data: Dict[str, List[Dict[str, Any]]],
        config: Optional[Dict[str, Any]] = None,
        nag_shown: bool = False,
        original_paths: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        check_run: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store Chess Log moments into game PGN (in-memory). Returns True on success.

        If ``original_paths`` is provided, any path_key that is (a) new — not present
        in ``original_paths`` — AND (b) does not resolve to a node in the game's current
        move tree is refused and logged at ERROR.  Pre-existing orphan keys (present in
        ``original_paths`` even if they no longer resolve) pass through untouched so that
        historical data is never silently destroyed.  When ``original_paths`` is None the
        guard is not applied (backward-compatible behaviour).

        ``check_run`` is an optional dict ``{"model": ..., "date": ...}`` written as
        ``_check_run`` in the payload.  When None, any existing ``_check_run`` in the
        game's current PGN tag is preserved automatically so non-Check-Logs saves do not
        erase run history.
        """
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
            if not chess_game:
                return False
            # Preserve existing _check_run when no new one is supplied.
            if check_run is None and ChessLogStorageService.TAG_NAME in chess_game.headers:
                try:
                    _existing = json.loads(
                        decode_and_decompress_to_str(
                            chess_game.headers[ChessLogStorageService.TAG_NAME]
                        )
                    )
                    check_run = _existing.get("_check_run") or None
                except Exception:
                    pass
            if original_paths is not None:
                filtered: Dict[str, List[Dict[str, Any]]] = {}
                for pk, entries in paths_data.items():
                    if pk in original_paths:
                        filtered[pk] = entries  # pre-existing: always passthrough
                    else:
                        path = decode_path(pk)
                        if path is not None and node_at_path(chess_game, path) is not None:
                            filtered[pk] = entries
                        else:
                            preset_set = sorted({e.get("preset", "") for e in (entries or [])})
                            LoggingService.get_instance().error(
                                f"Chess Log refusing new orphan path_key on save: "
                                f"game#{getattr(game, 'game_number', '?')}, "
                                f"path_key={pk!r}, presets={preset_set}"
                            )
                paths_data = filtered
            payload: Dict[str, Any] = {"_v": 1, "paths": paths_data}
            if nag_shown:
                payload["nag_shown"] = True
            if check_run:
                payload["_check_run"] = check_run
            json_text = json.dumps(payload, ensure_ascii=False)
            data_bytes = json_text.encode("utf-8")
            checksum = compute_checksum(data_bytes)
            encoded = compress_and_encode_from_str(json_text, compresslevel=9)
            app_version = (config or {}).get("version", "1.0")
            info_str = (
                f"App Version: {app_version}, "
                f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            chess_game.headers[ChessLogStorageService.TAG_NAME] = encoded
            chess_game.headers[ChessLogStorageService.TAG_INFO] = info_str
            chess_game.headers[ChessLogStorageService.TAG_CHECKSUM] = checksum
            has_tags = ChessLogStorageService.count_tags(paths_data) > 0
            game.pgn = PgnService.export_game_to_pgn(chess_game)
            game.has_chess_log_tags = has_tags
            return True
        except Exception as e:
            LoggingService.get_instance().error(
                f"Error storing Chess Log tags: {e}", exc_info=e
            )
            return False

    @staticmethod
    def clear_tags(game: GameData) -> bool:
        """Remove CARAChessLog* tags from game PGN (in-memory)."""
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        ChessLogStorageService._remove_chess_log_tags(game)  # also removes chip from header
        game.has_chess_log_tags = False
        return True

    @staticmethod
    def count_tags(paths_data: Dict[str, List[Dict[str, Any]]]) -> int:
        """Count distinct moments (non-empty path keys) — NOT total entries.

        One path = one moment, even if it carries multiple entries
        (e.g. CCT with two letters selected on the same moment).
        """
        return sum(1 for entries in paths_data.values() if entries)

    @staticmethod
    def make_entry(
        preset: str,
        cat: str,
        why: str = "",
        ignore_shallow: bool = False,
        is_shallow: bool = False,
        is_vague: bool = False,
        ignore_text_hash: Optional[str] = None,
        check_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a single moment entry dict with a new UUID and UTC timestamp."""
        entry: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "preset": preset,
            "cat": cat,
            "why": why,
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if ignore_shallow:
            entry["ignore_shallow"] = True
        if is_shallow:
            entry["is_shallow"] = True
        if is_vague:
            entry["is_vague"] = True
        if ignore_text_hash:
            entry["ignore_text_hash"] = ignore_text_hash
        if check_hash:
            entry["check_hash"] = check_hash
        return entry

    @staticmethod
    def is_entry_ignore_honoured(entry: Dict[str, Any]) -> bool:
        """Return True when this entry's ignore_shallow flag is in effect.

        Honoured when ignore_shallow=True AND either:
        - no ignore_text_hash stored (legacy: honour unconditionally), OR
        - sha256(why) == ignore_text_hash (text unchanged since Ignore was set).
        """
        if not entry.get("ignore_shallow", False):
            return False
        h = entry.get("ignore_text_hash")
        if not h:
            return True
        why = (entry.get("why") or "").strip()
        if not why:
            return False
        return hashlib.sha256(why.encode("utf-8")).hexdigest() == h

    @staticmethod
    def clear_verdict_if_text_changed(
        entry: Dict[str, Any], original_why: str
    ) -> Dict[str, Any]:
        """Return entry with chip/Ignore fields cleared when why text changed.

        Compares entry["why"].strip() to original_why.strip(). When they
        differ, returns a copy with is_shallow, is_vague, ignore_shallow, and
        ignore_text_hash removed. Returns the same dict unchanged when the
        text is identical (including whitespace-only differences after strip).
        """
        new_why = (entry.get("why") or "").strip()
        if new_why == (original_why or "").strip():
            return entry
        return {k: v for k, v in entry.items()
                if k not in ("is_shallow", "is_vague", "ignore_shallow", "ignore_text_hash")}

    @staticmethod
    def _remove_chess_log_tags(game: GameData) -> None:
        """Remove CARAChessLog* tags from game PGN (in-memory, best-effort)."""
        try:
            chess_game = chess.pgn.read_game(StringIO(game.pgn))
            if not chess_game:
                return
            for key in (
                ChessLogStorageService.TAG_NAME,
                ChessLogStorageService.TAG_INFO,
                ChessLogStorageService.TAG_CHECKSUM,
            ):
                if key in chess_game.headers:
                    del chess_game.headers[key]
            game.pgn = PgnService.export_game_to_pgn(chess_game)
            # Sync Python-side attributes for immediate in-session UI consistency.
            from app.utils.game_tags_utils import parse_game_tags, tags_display_text
            new_raw = chess_game.headers.get("CARAGameTags", "")
            game.game_tags_raw = new_raw
            game.game_tags = tags_display_text(parse_game_tags(new_raw))
        except Exception as e:
            LoggingService.get_instance().warning(f"Chess Log tag cleanup failed: {e}")

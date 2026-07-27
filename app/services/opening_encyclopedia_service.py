"""Read-only lookup against the shipped Opening Encyclopedia product DB."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.utils.path_resolver import get_app_root

_SPELLING = {
    "defence": "defense",
    "centre": "center",
}

_APOSTROPHE = re.compile(r"[’‘`]")

# German umlaut / Eszett → digraph forms so "grünfeld" matches "gruenfeld".
_UMLAUT_FOLD = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
)


def normalize_opening_name(name: str) -> str:
    """Lowercase, collapse whitespace, British→American spelling, trim punctuation.

    Must match the encyclopedia build pipeline normalizer.
    """
    s = (name or "").strip().lower()
    s = _APOSTROPHE.sub("'", s)
    s = re.sub(r"\s+", " ", s)
    for brit, amer in _SPELLING.items():
        s = re.sub(rf"\b{brit}\b", amer, s)
    return s.strip(" .,;:")


def _fold_search_text(text: str) -> str:
    """Lowercase and expand German umlauts for tolerant search matching."""
    return (text or "").lower().translate(_UMLAUT_FOLD)


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class EncyclopediaImage:
    """One image slot (BLOB loaded separately via ``slot``)."""

    slot: int  # 1 or 2
    mime: Optional[str]
    caption: Optional[str]
    lifespan: Optional[str]
    origin: Optional[str]
    source: Optional[str]
    license: Optional[str]
    attribution: Optional[str]


@dataclass(frozen=True)
class EncyclopediaEntry:
    """Resolved encyclopedia prose for an opening (BLOBs loaded separately)."""

    opening_id: str
    display_name: str
    family_id: Optional[str]
    tier: Optional[str]
    eco_codes: Optional[str]
    summary: str
    key_ideas: Optional[str]
    name_origin: Optional[str]
    history: Optional[str]
    images: Tuple[EncyclopediaImage, ...]

    @property
    def has_image(self) -> bool:
        return bool(self.images)


@dataclass(frozen=True)
class EncyclopediaSearchResult:
    """Lightweight result row for search (no prose / images)."""

    opening_id: str
    display_name: str
    tier: Optional[str]
    eco_codes: Optional[str]
    family_id: Optional[str]


class OpeningEncyclopediaService:
    """Lookup encyclopedia entries by explorer ``(display_name, eco)``."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._conn: Optional[sqlite3.Connection] = None
        self._by_name_eco: Dict[Tuple[str, str], str] = {}
        self._by_name: Dict[str, str] = {}
        self._openings: Dict[str, Dict[str, Any]] = {}
        self._image_cache: Dict[Tuple[str, int], Optional[bytes]] = {}
        self._available = False
        self._load()

    @property
    def available(self) -> bool:
        return self._available

    def _db_path(self) -> Path:
        rel = (
            self._config.get("resources", {}).get(
                "encyclopedia_db_path",
                "app/resources/encyclopedia/openings.db",
            )
        )
        path = Path(str(rel))
        if not path.is_absolute():
            path = get_app_root() / path
        return path

    @staticmethod
    def _images_from_row(row: sqlite3.Row) -> Tuple[EncyclopediaImage, ...]:
        images: List[EncyclopediaImage] = []
        if row["has_image"]:
            images.append(
                EncyclopediaImage(
                    slot=1,
                    mime=_opt_str(row["image_mime"]),
                    caption=_opt_str(row["image_caption"]),
                    lifespan=_opt_str(row["image_lifespan"]),
                    origin=_opt_str(row["image_origin"]),
                    source=_opt_str(row["image_source"]),
                    license=_opt_str(row["image_license"]),
                    attribution=_opt_str(row["image_attribution"]),
                )
            )
        if row["has_image_2"]:
            images.append(
                EncyclopediaImage(
                    slot=2,
                    mime=_opt_str(row["image_2_mime"]),
                    caption=_opt_str(row["image_2_caption"]),
                    lifespan=_opt_str(row["image_2_lifespan"]),
                    origin=_opt_str(row["image_2_origin"]),
                    source=_opt_str(row["image_2_source"]),
                    license=_opt_str(row["image_2_license"]),
                    attribution=_opt_str(row["image_2_attribution"]),
                )
            )
        return tuple(images)

    def _load(self) -> None:
        path = self._db_path()
        if not path.is_file():
            try:
                from app.services.logging_service import LoggingService

                LoggingService.get_instance(self._config).warning(
                    f"Opening encyclopedia DB not found: {path}"
                )
            except Exception:
                pass
            return

        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            self._conn = conn

            for row in conn.execute(
                "SELECT name_key, eco, opening_id FROM name_resolution"
            ):
                key = str(row["name_key"])
                eco = str(row["eco"] or "")
                oid = str(row["opening_id"])
                self._by_name_eco[(key, eco)] = oid
                if key not in self._by_name:
                    self._by_name[key] = oid

            for row in conn.execute(
                """
                SELECT o.opening_id, o.display_name, o.family_id,
                       o.tier, o.eco_codes,
                       o.summary, o.key_ideas, o.name_origin, o.history,
                       i1.mime AS image_mime, o.image_caption, o.image_lifespan,
                       o.image_origin, o.image_source, o.image_license,
                       o.image_attribution,
                       CASE WHEN o.image_id IS NOT NULL THEN 1 ELSE 0 END AS has_image,
                       i2.mime AS image_2_mime, o.image_2_caption, o.image_2_lifespan,
                       o.image_2_origin, o.image_2_source, o.image_2_license,
                       o.image_2_attribution,
                       CASE WHEN o.image_2_id IS NOT NULL THEN 1 ELSE 0 END AS has_image_2
                FROM opening o
                LEFT JOIN image i1 ON i1.sha256 = o.image_id
                LEFT JOIN image i2 ON i2.sha256 = o.image_2_id
                """
            ):
                oid = str(row["opening_id"])
                self._openings[oid] = {
                    "opening_id": oid,
                    "display_name": str(row["display_name"] or ""),
                    "family_id": row["family_id"],
                    "tier": _opt_str(row["tier"]),
                    "eco_codes": _opt_str(row["eco_codes"]),
                    "summary": row["summary"],
                    "key_ideas": row["key_ideas"],
                    "name_origin": row["name_origin"],
                    "history": row["history"],
                    "images": self._images_from_row(row),
                }

            self._available = True
            try:
                from app.services.logging_service import LoggingService

                LoggingService.get_instance(self._config).info(
                    f"Opening encyclopedia loaded: path={path}, "
                    f"openings={len(self._openings)}, "
                    f"name_keys={len(self._by_name)}"
                )
            except Exception:
                pass
        except Exception as exc:
            self._conn = None
            self._available = False
            try:
                from app.services.logging_service import LoggingService

                LoggingService.get_instance(self._config).error(
                    f"Failed to load opening encyclopedia: {exc}"
                )
            except Exception:
                pass

    def _resolve_opening_id(self, display_name: str, eco: Optional[str]) -> Optional[str]:
        if not self._available:
            return None
        key = normalize_opening_name(display_name)
        if not key:
            return None
        eco_s = eco or ""
        oid = self._by_name_eco.get((key, eco_s))
        if oid is None:
            oid = self._by_name.get(key)
        return oid

    def lookup(
        self, display_name: str, eco: Optional[str] = None
    ) -> Optional[EncyclopediaEntry]:
        """Resolve name → node, then walk family_id until a row has summary prose."""
        node = self._resolve_opening_id(display_name, eco)
        while node:
            raw = self._openings.get(node)
            if raw is None:
                break
            summary = (raw.get("summary") or "").strip()
            if summary:
                family_id = raw.get("family_id")
                return EncyclopediaEntry(
                    opening_id=str(raw["opening_id"]),
                    display_name=str(raw["display_name"] or display_name),
                    family_id=str(family_id) if family_id else None,
                    tier=_opt_str(raw.get("tier")),
                    eco_codes=_opt_str(raw.get("eco_codes")),
                    summary=summary,
                    key_ideas=_opt_str(raw.get("key_ideas")),
                    name_origin=_opt_str(raw.get("name_origin")),
                    history=_opt_str(raw.get("history")),
                    images=tuple(raw.get("images") or ()),
                )
            family = raw.get("family_id")
            node = str(family) if family else None
        return None

    def has_entry(self, display_name: str, eco: Optional[str] = None) -> bool:
        return self.lookup(display_name, eco) is not None

    def search(self, query: str, limit: int = 20) -> List[EncyclopediaSearchResult]:
        """Free-text search over display_name, opening_id, eco_codes, family_id.

        Matching is case-insensitive and umlaut-tolerant: ``grünfeld`` /
        ``gruenfeld`` / ``grunfeld``-style digraph forms all match each other
        (``ä``↔``ae``, ``ö``↔``oe``, ``ü``↔``ue``, ``ß``↔``ss``).
        """
        if not self._available or not query or not query.strip():
            return []
        q = _fold_search_text(query.strip())
        if not q:
            return []
        results: List[EncyclopediaSearchResult] = []
        for raw in self._openings.values():
            name = _fold_search_text(raw.get("display_name") or "")
            oid = _fold_search_text(raw.get("opening_id") or "")
            eco = _fold_search_text(raw.get("eco_codes") or "")
            fid = _fold_search_text(raw.get("family_id") or "")
            if q in name or q in oid or q in eco or q in fid:
                results.append(
                    EncyclopediaSearchResult(
                        opening_id=str(raw["opening_id"]),
                        display_name=str(raw.get("display_name") or ""),
                        tier=_opt_str(raw.get("tier")),
                        eco_codes=_opt_str(raw.get("eco_codes")),
                        family_id=_opt_str(raw.get("family_id")),
                    )
                )
        results.sort(key=lambda r: r.display_name.lower())
        return results[: max(1, int(limit))]

    def get_entry_by_id(self, opening_id: str) -> Optional[EncyclopediaEntry]:
        """Look up an entry directly by opening_id."""
        raw = self._openings.get(opening_id)
        if raw is None:
            return None
        summary = (raw.get("summary") or "").strip()
        if not summary:
            return None
        family_id = raw.get("family_id")
        return EncyclopediaEntry(
            opening_id=str(raw["opening_id"]),
            display_name=str(raw["display_name"] or ""),
            family_id=str(family_id) if family_id else None,
            tier=_opt_str(raw.get("tier")),
            eco_codes=_opt_str(raw.get("eco_codes")),
            summary=summary,
            key_ideas=_opt_str(raw.get("key_ideas")),
            name_origin=_opt_str(raw.get("name_origin")),
            history=_opt_str(raw.get("history")),
            images=tuple(raw.get("images") or ()),
        )

    def get_image_bytes(self, opening_id: str, slot: int = 1) -> Optional[bytes]:
        """Lazy-load image BLOB for ``opening_id`` slot 1 or 2 (cached)."""
        if not self._available or not self._conn or not opening_id:
            return None
        if slot not in (1, 2):
            return None
        cache_key = (opening_id, slot)
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]
        try:
            fk = "image_id" if slot == 1 else "image_2_id"
            row = self._conn.execute(
                f"""
                SELECT i.bytes AS blob
                FROM opening o
                JOIN image i ON i.sha256 = o.{fk}
                WHERE o.opening_id=? AND o.{fk} IS NOT NULL
                """,
                (opening_id,),
            ).fetchone()
        except Exception:
            self._image_cache[cache_key] = None
            return None
        if row is None or row["blob"] is None:
            self._image_cache[cache_key] = None
            return None
        data = row["blob"]
        blob = bytes(data) if not isinstance(data, bytes) else data
        self._image_cache[cache_key] = blob
        return blob

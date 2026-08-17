"""Read-only lookup against the shipped Opening Encyclopedia product DB."""

from __future__ import annotations

import re
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.utils.path_resolver import get_app_resource_path

_SPELLING = {
    "defence": "defense",
    "centre": "center",
}

_APOSTROPHE = re.compile(r"[’‘`]")

# Punctuation that should not block substring search (e.g. "kings" ↔ "king's").
_SEARCH_PUNCT = re.compile(r"['’‘`ʼ\-–—_/.,:;!?()\[\]{}]+")

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


def prefer_rows_matching_display_name(
    rows: List[Any],
    display_name: str,
) -> List[Any]:
    """Prefer book rows whose name matches ``display_name``; else keep ``rows``.

    Encyclopedia family ids often absorb differently labeled ECO names (e.g.
    ``Reti: KIA`` → ``kings-indian-attack``). Using every mapped name for the
    tabiya can collapse the diagram to an almost-empty opening position.
    Title-matched rows keep the miniature aligned with the article the user opened.
    """
    if not rows:
        return []
    key = normalize_opening_name(display_name)
    if not key:
        return list(rows)
    matched = [row for row in rows if normalize_opening_name(getattr(row, "name", "")) == key]
    return matched if matched else list(rows)


def _fold_search_text(text: str) -> str:
    """Lowercase, expand umlauts, and strip punctuation for tolerant search matching.

    Apostrophes/hyphens are removed so ``kings indian`` matches ``King's Indian``.
    """
    s = (text or "").lower().translate(_UMLAUT_FOLD)
    s = _SEARCH_PUNCT.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


# Lower rank = better. display_name beats id/eco; alias-only matches rank last.
_SEARCH_RANK_NAME_PREFIX = 0
_SEARCH_RANK_NAME_SUBSTRING = 1
_SEARCH_RANK_ID_OR_FAMILY = 2
_SEARCH_RANK_ECO = 3
_SEARCH_RANK_ALIAS = 4

# Title vs explorer suffix: lower rank = better match for specificity lookup.
_SUFFIX_RANK_EXACT = 0
_SUFFIX_RANK_FULL = 1
_SUFFIX_RANK_PREFIX = 2
_SUFFIX_RANK_NONE = 99

_GENERIC_SUFFIX_WORDS = (
    " variation",
)


def _strip_generic_suffix_words(text: str) -> str:
    out = normalize_opening_name(text)
    changed = True
    while changed and out:
        changed = False
        for suffix in _GENERIC_SUFFIX_WORDS:
            if out.endswith(suffix):
                out = out[: -len(suffix)].strip(" ,;:")
                changed = True
    return out


def _extract_suffix_candidates(display_name: str) -> List[Tuple[str, int]]:
    """Explorer label fragments to match against ready article titles.

    Returns ``(candidate, clause_rank)`` where lower ``clause_rank`` is more
    specific. Later comma clauses after ``:`` outrank earlier ones so
    ``Parent: Broad, Specific Variation`` can deepen to the child article.
    """
    name = (display_name or "").strip()
    if not name:
        return []
    out: List[Tuple[str, int]] = []
    seen: set[Tuple[str, int]] = set()

    def add(part: str, clause_rank: int) -> None:
        part = part.strip()
        item = (part, clause_rank)
        if part and item not in seen:
            seen.add(item)
            out.append(item)

    add(name, 50)
    if ":" in name:
        after = name.split(":", 1)[1].strip()
        add(after, 40)
        if "," in after:
            clauses = [part.strip() for part in after.split(",") if part.strip()]
            for idx, clause in enumerate(clauses):
                clause_rank = max(0, len(clauses) - idx - 1)
                add(clause, clause_rank)
    return out


def _eco_codes_list(eco_codes: Optional[str]) -> List[str]:
    if not eco_codes:
        return []
    text = str(eco_codes).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(c).strip().upper() for c in parsed if str(c).strip()]
        except Exception:
            pass
    return [text.upper()] if text else []


def _eco_overlaps(eco: Optional[str], eco_codes: Optional[str]) -> bool:
    if not eco or not str(eco).strip():
        return True
    eco_key = str(eco).strip().upper()
    return eco_key in _eco_codes_list(eco_codes)


def _title_match_rank(title_keys: List[str], suffix_key: str, full_key: str) -> int:
    best = _SUFFIX_RANK_NONE
    for title_key in title_keys:
        if suffix_key and title_key == suffix_key:
            best = min(best, _SUFFIX_RANK_EXACT)
        if full_key and title_key == full_key:
            best = min(best, _SUFFIX_RANK_FULL)
        if suffix_key and title_key.startswith(suffix_key + " "):
            best = min(best, _SUFFIX_RANK_PREFIX)
    return best


def _title_match_keys(title: str) -> List[str]:
    """Comparable title fragments for suffix specificity checks."""
    out: List[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        key = _strip_generic_suffix_words(text)
        if key and key not in seen:
            seen.add(key)
            out.append(key)

    add(title)
    if ":" in title:
        add(title.split(":", 1)[1].strip())
    return out


def _is_ancestor_opening(ancestor_id: Optional[str], opening_id: Optional[str]) -> bool:
    if not ancestor_id or not opening_id or ancestor_id == opening_id:
        return False
    prefix = ancestor_id + "/"
    return str(opening_id).startswith(prefix)


def _specificity_rank(
    match_rank: int, clause_rank: int, opening_id: str, eco_codes: Optional[str]
) -> Tuple[int, int, int, int]:
    depth = opening_id.count("/")
    eco_count = len(_eco_codes_list(eco_codes))
    # Lower is better. Strong exact-style matches may deepen to a child, but broad
    # prefix matches should stay conservative and avoid drifting into descendants.
    depth_rank = -depth if match_rank <= _SUFFIX_RANK_FULL else depth
    return (match_rank, clause_rank, depth_rank, eco_count)


def _best_ready_preference(
    specific_id: Optional[str], nr_id: Optional[str], openings: Dict[str, Dict[str, Any]]
) -> Optional[str]:
    """Prefer a ready NR target over a runtime-picked ready ancestor."""
    if not nr_id:
        return specific_id
    nr_raw = openings.get(nr_id)
    if not nr_raw:
        return specific_id or nr_id
    nr_ready = (
        (nr_raw.get("content_state") or "") == "ready"
        and bool(str(nr_raw.get("summary") or "").strip())
    )
    if not nr_ready:
        return specific_id or nr_id
    if specific_id and _is_ancestor_opening(specific_id, nr_id):
        return nr_id
    return specific_id or nr_id


def _search_match_rank(
    query: str,
    *,
    display_name: str,
    opening_id: str,
    family_id: str,
    eco_codes: str,
    aliases: Tuple[str, ...],
) -> Optional[int]:
    """Return best (lowest) match rank for ``query``, or None if no match."""
    if not query:
        return None
    best: Optional[int] = None

    def consider(rank: int) -> None:
        nonlocal best
        if best is None or rank < best:
            best = rank

    if display_name:
        if display_name.startswith(query):
            consider(_SEARCH_RANK_NAME_PREFIX)
        elif query in display_name:
            consider(_SEARCH_RANK_NAME_SUBSTRING)
    if query in opening_id or (family_id and query in family_id):
        consider(_SEARCH_RANK_ID_OR_FAMILY)
    if eco_codes and query in eco_codes:
        consider(_SEARCH_RANK_ECO)
    for alias in aliases:
        if query in alias:
            consider(_SEARCH_RANK_ALIAS)
            break
    return best


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
    # When name_resolution hit a stub and prose came from an ancestor:
    matched_opening_id: Optional[str] = None
    matched_display_name: Optional[str] = None
    matched_content_state: Optional[str] = None  # pending | skipped | ready
    # Explorer / lookup request label (for Nearest chip when it differs from title).
    explorer_display_name: Optional[str] = None

    @property
    def has_image(self) -> bool:
        return bool(self.images)

    @property
    def used_fallback(self) -> bool:
        """True when displayed prose belongs to a less-specific ancestor."""
        matched = self.matched_opening_id
        return bool(matched and matched != self.opening_id)

    @property
    def used_nearest(self) -> bool:
        """True when the article title differs from the explorer request label.

        Covers compound ECO names (``Parent: Child`` → ``Child`` article) and
        NR remaps. Mutually exclusive with :attr:`used_fallback`.
        """
        if self.used_fallback:
            return False
        explorer = (self.explorer_display_name or "").strip()
        if not explorer:
            return False
        return normalize_opening_name(explorer) != normalize_opening_name(
            self.display_name or ""
        )

@dataclass(frozen=True)
class EncyclopediaSearchResult:
    """Lightweight result row for search (no prose / images)."""

    opening_id: str
    display_name: str
    tier: Optional[str]
    eco_codes: Optional[str]
    family_id: Optional[str]


@dataclass(frozen=True)
class EncyclopediaSearchPage:
    """Truncated search hit list plus the untruncated match count."""

    results: List[EncyclopediaSearchResult]
    total: int


@dataclass(frozen=True)
class _SearchAbbrev:
    """Cached ``search_abbrev`` row for free-text query rewrite."""

    abbrev: str
    expansion: str
    family_id: Optional[str]


def _rewrite_search_query(
    raw_query: str,
    abbrevs: Dict[str, _SearchAbbrev],
) -> Tuple[str, Optional[str]]:
    """Expand a leading ``search_abbrev`` token, then fold like any other query.

    Abbreviation detection runs on the normalized (but not yet fold-stripped)
    string so separators such as ``:`` remain visible. After expansion, the
    same ``_fold_search_text`` path used for unabbreviated queries strips
    punctuation — so ``kid b3`` and ``kid: b3`` match like
    ``King's Indian defense b3`` / ``King's Indian defense: b3``.
    """
    normalized = normalize_opening_name(raw_query)
    if not normalized:
        return "", None

    # Longest abbrev first so ``semi-slav …`` wins over ``slav …``.
    for abbrev, hit in sorted(abbrevs.items(), key=lambda item: -len(item[0])):
        if normalized == abbrev:
            return _fold_search_text(hit.expansion), hit.family_id
        if not normalized.startswith(abbrev):
            continue
        if len(normalized) == len(abbrev):
            continue
        # Require a separator after the abbrev (space or fold-stripped punct).
        boundary = normalized[len(abbrev)]
        if not (boundary.isspace() or _SEARCH_PUNCT.match(boundary)):
            continue
        rest = _SEARCH_PUNCT.sub(" ", normalized[len(abbrev) :])
        rest = re.sub(r"\s+", " ", rest).strip()
        rewritten = hit.expansion if not rest else f"{hit.expansion} {rest}"
        return _fold_search_text(rewritten), hit.family_id

    return _fold_search_text(normalized), None


def _opening_in_family_scope(
    *,
    opening_id: str,
    family_id: Optional[str],
    scope_family_id: str,
) -> bool:
    """True if this opening belongs to the abbrev's family tree."""
    if not scope_family_id:
        return True
    oid = opening_id or ""
    if oid == scope_family_id:
        return True
    if oid.startswith(scope_family_id + "/") or oid.startswith(scope_family_id + "-"):
        return True
    if family_id and str(family_id) == scope_family_id:
        return True
    return False


class OpeningEncyclopediaService:
    """Lookup encyclopedia entries by explorer ``(display_name, eco)``.

    The SQLite catalog is loaded lazily on first use. Prefer
    :meth:`get_instance` so UI surfaces share one in-memory catalog.
    """

    _instance: Optional["OpeningEncyclopediaService"] = None

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._conn: Optional[sqlite3.Connection] = None
        self._by_name_eco: Dict[Tuple[str, str], str] = {}
        self._by_name: Dict[str, str] = {}
        self._openings: Dict[str, Dict[str, Any]] = {}
        # Folded name_resolution keys per opening_id (for free-text alias search).
        self._aliases_by_oid: Dict[str, Tuple[str, ...]] = {}
        # Loaded once from search_abbrev (never re-queried per search).
        self._search_abbrevs: Dict[str, _SearchAbbrev] = {}
        self._image_cache: Dict[Tuple[str, int], Optional[bytes]] = {}
        self._available = False
        self._load_attempted = False
        self._opening_service: Optional[Any] = None
        self._rows_by_oid: Optional[Dict[str, List[Any]]] = None
        self._tabiya_fen_by_oid: Dict[str, Optional[str]] = {}
        self._last_lookup_log: Optional[str] = None

    @classmethod
    def get_instance(cls, config: Dict[str, Any]) -> "OpeningEncyclopediaService":
        """Return the process-wide shared encyclopedia service (lazy-loads DB)."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def _ensure_loaded(self) -> None:
        """Load the catalog once, on first access."""
        if self._load_attempted:
            return
        self._load_attempted = True
        self._load()

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    def _db_path(self) -> Path:
        rel = (
            self._config.get("resources", {}).get(
                "encyclopedia_db_path",
                "app/resources/encyclopedia/openings.db",
            )
        )
        path = Path(str(rel))
        if path.is_absolute():
            return path
        return get_app_resource_path(str(path))

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
            # Plain path open (not URI): drive letters and Parallels UNC shares
            # (\\Mac\...) both work. query_only keeps the shipped DB read-only.
            conn = sqlite3.connect(str(path.resolve()))
            conn.execute("PRAGMA query_only=ON")
            conn.row_factory = sqlite3.Row
            self._conn = conn
            alias_buckets: Dict[str, List[str]] = {}

            for row in conn.execute(
                "SELECT name_key, eco, opening_id FROM name_resolution"
            ):
                key = str(row["name_key"])
                eco = str(row["eco"] or "")
                oid = str(row["opening_id"])
                self._by_name_eco[(key, eco)] = oid
                if key not in self._by_name:
                    self._by_name[key] = oid
                folded = _fold_search_text(key)
                if folded:
                    bucket = alias_buckets.setdefault(oid, [])
                    if folded not in bucket:
                        bucket.append(folded)

            self._aliases_by_oid = {
                oid: tuple(aliases) for oid, aliases in alias_buckets.items()
            }

            # Optional in older product DBs; cache in memory for search rewrites.
            self._search_abbrevs = {}
            try:
                for row in conn.execute(
                    "SELECT abbrev, expansion, family_id FROM search_abbrev"
                ):
                    abbrev = normalize_opening_name(str(row["abbrev"] or ""))
                    expansion = normalize_opening_name(str(row["expansion"] or ""))
                    if not abbrev or not expansion:
                        continue
                    family_raw = row["family_id"]
                    family_id = str(family_raw).strip() if family_raw else None
                    self._search_abbrevs[abbrev] = _SearchAbbrev(
                        abbrev=abbrev,
                        expansion=expansion,
                        family_id=family_id or None,
                    )
            except sqlite3.OperationalError:
                self._search_abbrevs = {}

            # Prefer content_state when present; older DBs fall back to summary.
            has_content_state = False
            try:
                cols = {
                    str(r[1])
                    for r in conn.execute("PRAGMA table_info(opening)").fetchall()
                }
                has_content_state = "content_state" in cols
            except Exception:
                has_content_state = False

            state_select = (
                "o.content_state"
                if has_content_state
                else "NULL AS content_state"
            )
            for row in conn.execute(
                f"""
                SELECT o.opening_id, o.display_name, o.family_id,
                       o.tier, o.eco_codes,
                       o.summary, o.key_ideas, o.name_origin, o.history,
                       {state_select},
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
                summary = row["summary"]
                raw_state = row["content_state"] if has_content_state else None
                if raw_state in ("ready", "pending", "skipped"):
                    content_state = str(raw_state)
                elif summary and str(summary).strip():
                    content_state = "ready"
                else:
                    content_state = "pending"
                self._openings[oid] = {
                    "opening_id": oid,
                    "display_name": str(row["display_name"] or ""),
                    "family_id": row["family_id"],
                    "tier": _opt_str(row["tier"]),
                    "eco_codes": _opt_str(row["eco_codes"]),
                    "summary": summary,
                    "key_ideas": row["key_ideas"],
                    "name_origin": row["name_origin"],
                    "history": row["history"],
                    "content_state": content_state,
                    "images": self._images_from_row(row),
                }

            self._available = True
            try:
                from app.services.logging_service import LoggingService

                LoggingService.get_instance(self._config).info(
                    f"Opening encyclopedia loaded: path={path}, "
                    f"openings={len(self._openings)}, "
                    f"name_keys={len(self._by_name)}, "
                    f"search_abbrevs={len(self._search_abbrevs)}"
                )
            except Exception:
                pass
        except Exception as exc:
            self._conn = None
            self._available = False
            self._search_abbrevs = {}
            try:
                from app.services.logging_service import LoggingService

                LoggingService.get_instance(self._config).error(
                    f"Failed to load opening encyclopedia: {exc}"
                )
            except Exception:
                pass

    def _resolve_opening_id(self, display_name: str, eco: Optional[str]) -> Optional[str]:
        self._ensure_loaded()
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

    def _resolve_most_specific_ready(
        self, display_name: str, eco: Optional[str]
    ) -> Optional[str]:
        """Pick the best ready article for an explorer label (suffix + ECO overlap)."""
        self._ensure_loaded()
        if not self._available:
            return None
        full_key = normalize_opening_name(display_name)
        if not full_key:
            return None

        best_oid: Optional[str] = None
        best_rank: Tuple[int, int, int, int] = (_SUFFIX_RANK_NONE, 99, 0, 99)

        for suffix_raw, clause_rank in _extract_suffix_candidates(display_name):
            suffix_key = _strip_generic_suffix_words(suffix_raw)
            if not suffix_key:
                continue
            for oid, raw in self._openings.items():
                if not self._is_ready(raw):
                    continue
                if not _eco_overlaps(eco, raw.get("eco_codes")):
                    continue
                title_keys = _title_match_keys(str(raw.get("display_name") or ""))
                if not title_keys:
                    continue
                match_rank = _title_match_rank(title_keys, suffix_key, full_key)
                if match_rank >= _SUFFIX_RANK_NONE:
                    continue
                rank = _specificity_rank(
                    match_rank, clause_rank, oid, raw.get("eco_codes")
                )
                if rank < best_rank:
                    best_rank = rank
                    best_oid = oid
        return best_oid

    def _debug(self, message: str) -> None:
        try:
            from app.services.logging_service import LoggingService

            LoggingService.get_instance(self._config).debug(message)
        except Exception:
            pass

    def _log_lookup(
        self,
        display_name: str,
        eco: Optional[str],
        entry: Optional[EncyclopediaEntry],
        specific: Optional[str],
        nr: Optional[str],
    ) -> None:
        """One compact debug line per distinct lookup result (skips UI probe spam)."""
        eco_s = eco or "-"
        if entry is None:
            detail = f"no article (specific={specific or '-'} nr={nr or '-'})"
        else:
            if entry.used_fallback:
                chip = "fallback"
            elif entry.used_nearest:
                chip = "nearest"
            else:
                chip = "direct"
            chosen = entry.matched_opening_id or entry.opening_id
            if specific and nr and specific != nr:
                via = "nr" if chosen == nr else "specific"
                extra = f" specific={specific} nr={nr}"
            elif specific:
                via = "specific"
                extra = ""
            else:
                via = "nr"
                extra = ""
            detail = f"{entry.opening_id} {chip} via={via}{extra}"
            if entry.used_fallback and entry.matched_opening_id:
                detail += f" from={entry.matched_opening_id}"
        msg = f'Encyclopedia lookup: "{display_name}" {eco_s} -> {detail}'
        if msg == self._last_lookup_log:
            return
        self._last_lookup_log = msg
        self._debug(msg)

    def _resolve_opening_node(
        self, display_name: str, eco: Optional[str]
    ) -> Optional[str]:
        """Resolve with runtime specificity, but keep a ready NR child over an ancestor."""
        specific = self._resolve_most_specific_ready(display_name, eco)
        nr = self._resolve_opening_id(display_name, eco)
        return _best_ready_preference(specific, nr, self._openings)

    def _entry_from_ready(
        self,
        raw: Dict[str, Any],
        *,
        matched_opening_id: Optional[str] = None,
        matched_display_name: Optional[str] = None,
        matched_content_state: Optional[str] = None,
        fallback_display_name: Optional[str] = None,
        explorer_display_name: Optional[str] = None,
    ) -> EncyclopediaEntry:
        """Build an ``EncyclopediaEntry`` from a ready in-memory opening row."""
        family_id = raw.get("family_id")
        display = str(raw.get("display_name") or fallback_display_name or "")
        explorer = (explorer_display_name or fallback_display_name or "").strip() or None
        return EncyclopediaEntry(
            opening_id=str(raw["opening_id"]),
            display_name=display,
            family_id=str(family_id) if family_id else None,
            tier=_opt_str(raw.get("tier")),
            eco_codes=_opt_str(raw.get("eco_codes")),
            summary=str(raw.get("summary") or "").strip(),
            key_ideas=_opt_str(raw.get("key_ideas")),
            name_origin=_opt_str(raw.get("name_origin")),
            history=_opt_str(raw.get("history")),
            images=tuple(raw.get("images") or ()),
            matched_opening_id=matched_opening_id,
            matched_display_name=matched_display_name,
            matched_content_state=matched_content_state,
            explorer_display_name=explorer,
        )

    @staticmethod
    def _is_ready(raw: Dict[str, Any]) -> bool:
        state = raw.get("content_state") or ""
        summary = (raw.get("summary") or "").strip()
        if state == "ready" and summary:
            return True
        # Legacy DBs without content_state: non-empty summary is enough.
        if not state and summary:
            return True
        return False

    def _walk_to_ready(
        self,
        start_id: str,
        *,
        explorer_display_name: Optional[str] = None,
    ) -> Optional[EncyclopediaEntry]:
        """Walk ``family_id`` from ``start_id`` until a ready prose row."""
        matched_raw = self._openings.get(start_id)
        matched_name = (
            str(matched_raw.get("display_name") or "")
            if matched_raw
            else (explorer_display_name or "")
        )
        matched_state = (
            str(matched_raw.get("content_state") or "pending")
            if matched_raw
            else "pending"
        )
        node: Optional[str] = start_id
        seen: set[str] = set()
        while node and node not in seen:
            seen.add(node)
            raw = self._openings.get(node)
            if raw is None:
                break
            if self._is_ready(raw):
                used_fallback = node != start_id
                return self._entry_from_ready(
                    raw,
                    matched_opening_id=start_id if used_fallback else None,
                    matched_display_name=matched_name if used_fallback else None,
                    matched_content_state=matched_state if used_fallback else None,
                    explorer_display_name=explorer_display_name,
                )
            family = raw.get("family_id")
            node = str(family) if family else None
        return None

    def lookup(
        self, display_name: str, eco: Optional[str] = None
    ) -> Optional[EncyclopediaEntry]:
        """Resolve name → node, then walk family_id until a ready prose row.

        Resolution prefers the most specific ready article matching the explorer
        suffix and ECO; ``name_resolution`` is used when no such candidate exists.
        Pending / skipped stubs still inherit via ``family_id`` (Fallback chip).
        """
        specific = self._resolve_most_specific_ready(display_name, eco)
        nr = self._resolve_opening_id(display_name, eco)
        node = _best_ready_preference(specific, nr, self._openings)
        entry = (
            self._walk_to_ready(node, explorer_display_name=display_name)
            if node
            else None
        )
        self._log_lookup(display_name, eco, entry, specific, nr)
        return entry

    def has_entry(self, display_name: str, eco: Optional[str] = None) -> bool:
        node = self._resolve_opening_node(display_name, eco)
        if not node:
            return False
        return self._walk_to_ready(node, explorer_display_name=display_name) is not None

    def search(self, query: str, limit: int = 20) -> EncyclopediaSearchPage:
        """Free-text search over display_name, opening_id, eco_codes, family_id,
        and ``name_resolution`` aliases for each opening.

        Matching is case-insensitive, punctuation-tolerant (``kings``↔``king's``),
        and umlaut-tolerant: ``grünfeld`` / ``gruenfeld`` / ``grunfeld``-style
        digraph forms all match each other (``ä``↔``ae``, ``ö``↔``oe``,
        ``ü``↔``ue``, ``ß``↔``ss``).

        Queries may start with a curated ``search_abbrev`` token (cached at
        load). That token is expanded to its full ``expansion`` text, then the
        query is folded with the same punctuation/umlaut rules as any other
        search — so ``kid b3`` and ``kid: b3`` behave like
        ``King's Indian defense b3`` / ``…: b3``. Hits are scoped to the
        abbrev's ``family_id`` tree when set.

        Ranking (best first): display_name prefix, display_name substring,
        opening_id/family_id, eco_codes, then alias-only hits. Ties break on
        display_name A–Z.

        Only ``content_state=ready`` openings are searchable (stubs stay out of
        the hit list; explorer lookup still resolves them via inheritance).

        Returns a page of at most ``limit`` hits plus ``total`` untruncated count
        so the UI can show an overflow hint when results are truncated.
        """
        self._ensure_loaded()
        if not self._available or not query or not query.strip():
            return EncyclopediaSearchPage(results=[], total=0)
        q, family_scope = _rewrite_search_query(query.strip(), self._search_abbrevs)
        if not q:
            return EncyclopediaSearchPage(results=[], total=0)
        scored: List[Tuple[int, str, EncyclopediaSearchResult]] = []
        for raw in self._openings.values():
            if not self._is_ready(raw):
                continue
            oid = str(raw["opening_id"])
            row_family = raw.get("family_id")
            if family_scope and not _opening_in_family_scope(
                opening_id=oid,
                family_id=str(row_family) if row_family else None,
                scope_family_id=family_scope,
            ):
                continue
            name = _fold_search_text(raw.get("display_name") or "")
            oid_fold = _fold_search_text(oid)
            eco = _fold_search_text(raw.get("eco_codes") or "")
            fid = _fold_search_text(raw.get("family_id") or "")
            aliases = self._aliases_by_oid.get(oid, ())
            rank = _search_match_rank(
                q,
                display_name=name,
                opening_id=oid_fold,
                family_id=fid,
                eco_codes=eco,
                aliases=aliases,
            )
            if rank is None:
                continue
            display = str(raw.get("display_name") or "")
            scored.append(
                (
                    rank,
                    display.lower(),
                    EncyclopediaSearchResult(
                        opening_id=oid,
                        display_name=display,
                        tier=_opt_str(raw.get("tier")),
                        eco_codes=_opt_str(raw.get("eco_codes")),
                        family_id=_opt_str(raw.get("family_id")),
                    ),
                )
            )
        scored.sort(key=lambda item: (item[0], item[1]))
        results = [item[2] for item in scored]
        capped = max(1, int(limit))
        return EncyclopediaSearchPage(results=results[:capped], total=len(results))

    def get_entry_by_id(self, opening_id: str) -> Optional[EncyclopediaEntry]:
        """Look up an entry by opening_id, walking to a ready ancestor if needed."""
        self._ensure_loaded()
        if not opening_id:
            return None
        return self._walk_to_ready(opening_id)

    def get_image_bytes(self, opening_id: str, slot: int = 1) -> Optional[bytes]:
        """Lazy-load image BLOB for ``opening_id`` slot 1 or 2 (cached)."""
        self._ensure_loaded()
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

    def _get_opening_service(self):
        """Lazy OpeningService for ECO book rows (same config as this encyclopedia)."""
        if self._opening_service is None:
            from app.services.opening_service import OpeningService

            self._opening_service = OpeningService.get_instance(self._config)
        return self._opening_service

    def _ensure_rows_by_oid(self) -> Dict[str, List[Any]]:
        """Index ECO book rows by exact ``opening_id`` (from name_resolution)."""
        if self._rows_by_oid is not None:
            return self._rows_by_oid
        self._ensure_loaded()
        buckets: Dict[str, List[Any]] = {}
        if self._available:
            for row in self._get_opening_service().iter_book_rows():
                oid = self._resolve_opening_id(row.name, row.eco)
                if not oid:
                    continue
                buckets.setdefault(oid, []).append(row)
        self._rows_by_oid = buckets
        return buckets

    def _is_under_opening(self, oid: str, ancestor: str) -> bool:
        """True if ``oid`` is ``ancestor`` or a descendant (slash id or family_id)."""
        if not oid or not ancestor:
            return False
        if oid == ancestor or oid.startswith(ancestor + "/"):
            return True
        seen: set[str] = set()
        node: Optional[str] = oid
        while node and node not in seen:
            if node == ancestor:
                return True
            seen.add(node)
            raw = self._openings.get(node)
            if raw is None:
                break
            family = raw.get("family_id")
            node = str(family).strip() if family else None
            if not node:
                break
        return False

    def _rows_for_tabiya(self, opening_id: str) -> List[Any]:
        """Book rows for this opening and its descendant encyclopedia ids."""
        collected: List[Any] = []
        for oid, rows in self._ensure_rows_by_oid().items():
            if self._is_under_opening(oid, opening_id):
                collected.extend(rows)
        return collected

    def tabiya_fen(self, opening_id: str) -> Optional[str]:
        """Return the named-tabiya FEN for ``opening_id``, or ``None``.

        If ECO names resolve to this id, prefer rows whose book name matches
        this opening's encyclopedia display name, then take the shallowest
        unique named position (sibling pop only at min depth). That keeps
        alias labels mapped onto the same id (e.g. ``Reti: KIA`` under
        King's Indian Attack) from collapsing the diagram to ``1. Nf3``,
        and still avoids transpositional move orders collapsing to ``1. e4``.

        If this id has no book name of its own, include descendant ids and
        take the common SAN prefix so a parent still gets a defining diagram.
        Cached per opening_id.
        """
        oid = (opening_id or "").strip()
        if not oid:
            return None
        if oid in self._tabiya_fen_by_oid:
            return self._tabiya_fen_by_oid[oid]
        from app.services.opening_service import compute_tabiya_fen

        exact = self._ensure_rows_by_oid().get(oid, [])
        if exact:
            self._ensure_loaded()
            display = str((self._openings.get(oid) or {}).get("display_name") or "")
            fen = compute_tabiya_fen(
                prefer_rows_matching_display_name(exact, display),
                family=False,
            )
        else:
            fen = compute_tabiya_fen(self._rows_for_tabiya(oid), family=True)
        self._tabiya_fen_by_oid[oid] = fen
        return fen

"""Theme discovery and config loading for runtime style switching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.config.config_loader import ConfigLoader
from app.utils.path_resolver import get_app_resource_path, resolve_data_file_path


@dataclass(frozen=True)
class ThemeOption:
    """A discoverable style config option."""

    label: str
    style_ref: str  # Stored as a path relative to repo root (POSIX-ish) when possible
    absolute_path: Path


def _to_posix_relpath(path: Path, *, base: Path) -> Optional[str]:
    try:
        rel = path.resolve().relative_to(base.resolve())
    except Exception:
        return None
    return rel.as_posix()


def discover_style_configs(*, config_path: Path) -> List[ThemeOption]:
    """Find all ``style_*.config.json`` files next to config.json.

    The label is derived from the filename (without extension).
    """
    config_path = config_path.resolve()
    config_dir = config_path.parent
    repo_root = config_path.parents[2] if len(config_path.parents) >= 3 else config_dir

    opts: List[ThemeOption] = []
    for p in sorted(config_dir.glob("style_*.config.json")):
        if not p.is_file():
            continue
        # Display name in menus: strip "style_" prefix and extension.
        # Examples:
        # - style_default.config.json -> Default
        # - style_light.config.json -> Light
        base = p.name
        if base.endswith(".config.json"):
            base = base[: -len(".config.json")]
        elif base.lower().endswith(".json"):
            base = base[: -len(".json")]
        if base.startswith("style_"):
            base = base[len("style_") :]
        base = base.replace("_", " ").strip()
        label = base[:1].upper() + base[1:] if base else p.name.replace(".config.json", "")
        style_ref = _to_posix_relpath(p, base=repo_root) or str(p)
        opts.append(ThemeOption(label=label, style_ref=style_ref, absolute_path=p.resolve()))

    return opts


def load_config_for_style(*, config_path: Path, style_ref: str) -> dict:
    """Load merged+expanded config for a given style reference."""
    loader = ConfigLoader(config_path=config_path)
    return loader.load_with_style_override(style_ref)


def load_saved_theme_style_ref() -> Optional[str]:
    """Read the persisted theme selection from user settings (best-effort).

    This is intentionally lightweight so it can run before ConfigLoader / Qt UI
    initialization, enabling a no-flash theme on startup.
    """
    # Determine user settings filename from app/config/config.json (same logic as UserSettingsService).
    settings_filename = "user_settings.json"
    try:
        cfg_path = get_app_resource_path("app/config/config.json")
        if cfg_path.exists():
            base = json.loads(cfg_path.read_text(encoding="utf-8"))
            us_cfg = base.get("user_settings", {}) if isinstance(base, dict) else {}
            if isinstance(us_cfg, dict):
                settings_filename = str(us_cfg.get("filename", settings_filename) or settings_filename)
    except Exception:
        settings_filename = "user_settings.json"

    try:
        settings_path, _ = resolve_data_file_path(settings_filename)
    except Exception:
        return None

    if not settings_path or not settings_path.exists():
        return None

    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    ui = raw.get("ui", {}) if isinstance(raw, dict) else {}
    theme = ui.get("theme", {}) if isinstance(ui, dict) else {}
    ref = theme.get("default_style_config") if isinstance(theme, dict) else None
    if isinstance(ref, str) and ref.strip():
        return ref.strip()
    return None


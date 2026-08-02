# -*- mode: python ; coding: utf-8 -*-
"""macOS PyInstaller spec for CARA.

Unsigned by default (day-to-day builds). For release signing, set:

  export CARA_CODESIGN_IDENTITY="Developer ID Application: … (TEAMID)"

and run scripts/build_macos_signed.sh (preferred), or PyInstaller directly.

Secrets (Apple ID password, app-specific password, .p12 keys) must NEVER be
placed in this file — use Keychain / notarytool keychain profiles instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

config_json_datas = [
    (str(path), "app/config")
    for path in sorted(Path("app/config").glob("*.json"))
]

_version = "0.0.0"
try:
    with Path("app/config/config.json").open(encoding="utf-8") as fh:
        _version = str(json.load(fh).get("version") or _version)
except Exception:
    pass

# Public bundle id (not a secret). Override with CARA_BUNDLE_IDENTIFIER if needed.
_bundle_id = os.environ.get("CARA_BUNDLE_IDENTIFIER", "com.pguntermann.cara").strip()

# Signing is opt-in via environment. Identity string is not secret; the private
# key lives only in the local Keychain and is never read from this repo.
_codesign_identity = os.environ.get("CARA_CODESIGN_IDENTITY", "").strip() or None
_entitlements_default = Path("packaging/macos/entitlements.plist")
_entitlements_path = Path(
    os.environ.get("CARA_ENTITLEMENTS", str(_entitlements_default))
)
_entitlements_file = None
if _codesign_identity:
    if not _entitlements_path.is_file():
        raise SystemExit(f"Entitlements file not found: {_entitlements_path}")
    _entitlements_file = str(_entitlements_path.resolve())

# UPX-compressed binaries often fail Apple notarization; disable when signing.
_use_upx = _codesign_identity is None

a = Analysis(
    ["cara.py"],
    pathex=[],
    binaries=[],
    datas=[
        *config_json_datas,
        ("app/resources", "app/resources"),
        ("appicon.svg", "."),
        ("manual.html", "."),
        ("LICENSE", "."),
        ("README.md", "."),
        ("RELEASE_NOTES.md", "."),
        ("THIRD_PARTY_LICENSES.md", "."),
        ("engine_parameters.json", "."),
        ("user_settings.json", "."),
        ("user_settings.json.template", "."),
    ],
    hiddenimports=["_charset_normalizer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CARA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=_use_upx,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=_codesign_identity,
    entitlements_file=_entitlements_file,
    icon=["app/resources/icons/AppIcon.icns"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=_use_upx,
    upx_exclude=[],
    name="CARA",
)
app = BUNDLE(
    coll,
    name="CARA.app",
    icon="app/resources/icons/AppIcon.icns",
    bundle_identifier=_bundle_id,
    info_plist={
        "CFBundleShortVersionString": _version,
        "CFBundleVersion": _version,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)

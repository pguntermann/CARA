# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Linux (onedir). Based on CARA_windows.spec.
# Build from repo root, e.g.: pyinstaller CARA_linux.spec
# For a desktop icon, ship a .desktop file pointing at dist/CARA/CARA and a PNG.

import os
import shutil
import sys
from pathlib import Path

config_json_datas = [(str(path), 'app/config') for path in sorted(Path('app/config').glob('*.json'))]

# Multiarch prefixes used on Debian/Ubuntu CI runners.
_LINUX_LIB_PREFIXES = (
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib/aarch64-linux-gnu",
    "/usr/lib64",
    "/usr/lib",
)

# Qt xcb helpers: beside libQt6XcbQpa ($ORIGIN / $ORIGIN/../../lib).
_XCB_HELPER_SONAMES = (
    "libxcb-render-util.so.0",
    "libxcb-image.so.0",
    "libxcb-icccm.so.4",
    "libxcb-keysyms.so.1",
    "libxcb-shape.so.0",
    "libxcb-xkb.so.1",
    "libxcb-cursor.so.0",
)

# libxkbcommon* must NOT sit on XcbQpa's RUNPATH: rolling distros (CachyOS/Arch)
# must keep using their system libs + Compose data. Ship a private fallback tree
# for hosts that lack libxkbcommon-x11 (e.g. minimal Fedora); cara.py preloads
# it only when the system library is missing, and sets matching XLOCALEDIR.
_XKB_FALLBACK_DIR = "cara_xkb_fallback"
_XKB_FALLBACK_SONAMES = (
    "libxkbcommon.so.0",
    "libxkbcommon-x11.so.0",
)
_X11_LOCALE_SRC = "/usr/share/X11/locale"


def _ensure_soname_path(path: str, soname: str) -> str:
    """Return a filesystem path whose basename equals ``soname`` (not .so.N.N.N)."""
    if os.path.basename(path) == soname:
        return path
    sibling = os.path.join(os.path.dirname(path), soname)
    if os.path.isfile(sibling):
        return sibling
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="cara_xcb_")
    dest = os.path.join(tmp_dir, soname)
    shutil.copy2(path, dest)
    return dest


def _resolve_soname(soname: str, short_name: str) -> str:
    """Resolve ``soname`` on the build host (prefer the SONAME link path)."""
    import ctypes.util

    candidates = [os.path.join(prefix, soname) for prefix in _LINUX_LIB_PREFIXES]
    found = ctypes.util.find_library(short_name)
    if found:
        candidates.append(found)

    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isabs(path) and os.path.isfile(path):
            return _ensure_soname_path(path, soname)
        if not os.path.isabs(path):
            for prefix in _LINUX_LIB_PREFIXES:
                for name in (path, soname):
                    full = os.path.join(prefix, name)
                    if os.path.isfile(full):
                        return _ensure_soname_path(full, soname)

    raise SystemExit(
        f"{soname} not found on the build host. "
        "Install libxcb-cursor0 libxcb-render-util0 libxcb-icccm4 "
        "libxcb-keysyms1 libxcb-shape0 libxcb-image0 libxcb-xkb1 "
        "libxkbcommon0 libxkbcommon-x11-0 (Debian/Ubuntu)."
    )


def _linux_xcb_helper_binaries():
    """Ship XCB helpers beside XcbQpa; ship xkbcommon only in the private fallback dir."""
    entries = []
    for soname in _XCB_HELPER_SONAMES:
        short = soname[3:].split(".so")[0]  # libxcb-cursor.so.0 -> xcb-cursor
        path = _resolve_soname(soname, short)
        print(f"CARA_linux.spec: bundling {path} (XcbQpa $ORIGIN)", file=sys.stderr)
        entries.append((path, "PyQt6/Qt6/lib"))
        entries.append((path, "."))
    for soname in _XKB_FALLBACK_SONAMES:
        short = soname[3:].split(".so")[0]  # libxkbcommon-x11.so.0 -> xkbcommon-x11
        path = _resolve_soname(soname, short)
        print(f"CARA_linux.spec: bundling {path} -> {_XKB_FALLBACK_DIR}", file=sys.stderr)
        entries.append((path, _XKB_FALLBACK_DIR))
    return entries


def _linux_xkb_fallback_datas():
    """Ship build-host X11 locale data for the private libxkbcommon fallback."""
    if not os.path.isdir(_X11_LOCALE_SRC):
        raise SystemExit(
            f"{_X11_LOCALE_SRC} not found. Install libx11-data (Debian/Ubuntu)."
        )
    print(
        f"CARA_linux.spec: bundling {_X11_LOCALE_SRC} -> {_XKB_FALLBACK_DIR}/X11/locale",
        file=sys.stderr,
    )
    return [(_X11_LOCALE_SRC, f"{_XKB_FALLBACK_DIR}/X11/locale")]


a = Analysis(
    ['cara.py'],
    pathex=[],
    binaries=_linux_xcb_helper_binaries(),
    datas=[
        *config_json_datas,
        *_linux_xkb_fallback_datas(),
        ('app/resources', 'app/resources'),
        ('appicon.svg', '.'),
        ('manual.html', '.'),
        ('LICENSE', '.'),
        ('README.md', '.'),
        ('RELEASE_NOTES.md', '.'),
        ('THIRD_PARTY_LICENSES.md', '.'),
        ('engine_parameters.json', '.'),
        ('user_settings.json', '.'),
        ('user_settings.json.template', '.'),
    ],
    hiddenimports=['_charset_normalizer'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Keep libxkbcommon* only under cara_xkb_fallback (never on XcbQpa $ORIGIN).
def _linux_filter_xkb_libs(binaries_toc):
    out = []
    for entry in binaries_toc:
        dest = entry[0]
        base = os.path.basename(dest).lower()
        if base.startswith("libxkbregistry.so"):
            continue
        if base.startswith(("libxkbcommon.so", "libxkbcommon-x11.so")):
            norm = dest.replace("\\", "/")
            if f"/{_XKB_FALLBACK_DIR}/" not in f"/{norm}" and not norm.startswith(
                f"{_XKB_FALLBACK_DIR}/"
            ):
                continue
        out.append(entry)
    return out


a.binaries = _linux_filter_xkb_libs(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CARA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CARA',
)

# Fail the build if helpers / fallback did not land correctly.
_internal = Path("dist") / "CARA" / "_internal"
_qt_lib = _internal / "PyQt6" / "Qt6" / "lib"
_fallback = _internal / _XKB_FALLBACK_DIR
for _soname in _XCB_HELPER_SONAMES:
    for _dir in (_qt_lib, _internal):
        _path = _dir / _soname
        if not _path.is_file():
            raise SystemExit(f"CARA_linux.spec: missing {_path} after COLLECT")
        print(f"CARA_linux.spec: OK {_path}", file=sys.stderr)
for _soname in _XKB_FALLBACK_SONAMES:
    _path = _fallback / _soname
    if not _path.is_file():
        raise SystemExit(f"CARA_linux.spec: missing {_path} after COLLECT")
    # Must not also sit beside XcbQpa (would override system libs on rolling distros).
    for _dir in (_qt_lib, _internal):
        _bad = _dir / _soname
        if _bad.is_file():
            raise SystemExit(
                f"CARA_linux.spec: {_soname} must not be in {_dir} (only {_fallback})"
            )
    print(f"CARA_linux.spec: OK {_path}", file=sys.stderr)
_locale = _fallback / "X11" / "locale"
if not _locale.is_dir():
    raise SystemExit(f"CARA_linux.spec: missing {_locale} after COLLECT")
print(f"CARA_linux.spec: OK {_locale}", file=sys.stderr)

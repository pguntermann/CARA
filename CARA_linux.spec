# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Linux (onedir). Based on CARA_windows.spec.
# Build from repo root, e.g.: pyinstaller CARA_linux.spec
# For a desktop icon, ship a .desktop file pointing at dist/CARA/CARA and a PNG.

import os
from pathlib import Path

config_json_datas = [(str(path), 'app/config') for path in sorted(Path('app/config').glob('*.json'))]

a = Analysis(
    ['cara.py'],
    pathex=[],
    binaries=[],
    datas=[
        *config_json_datas,
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

# Do not ship libxkbcommon*: Qt/xcb loads the distro's libxcb-xkb and libxkbcommon-x11.
# A PyInstaller-bundled libxkbcommon often mismatches them (SIGSEGV in
# xkb_state_key_get_layout), seen e.g. on openSUSE Tumbleweed.
def _linux_skip_bundled_xkb_libs(binaries_toc):
    out = []
    for entry in binaries_toc:
        dest = entry[0]
        base = os.path.basename(dest).lower()
        if base.startswith(("libxkbcommon.so", "libxkbcommon-x11.so", "libxkbregistry.so")):
            continue
        out.append(entry)
    return out


a.binaries = _linux_skip_bundled_xkb_libs(a.binaries)

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

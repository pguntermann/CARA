# -*- mode: python ; coding: utf-8 -*-

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
    icon=['app\\resources\\icons\\AppIcon.ico'],
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

# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cara.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/config/config.json', 'app/config'),
        ('app/resources', 'app/resources'),
        ('appicon.svg', '.'),
        ('manual.html', '.'),
        ('LICENSE', '.'),
        ('README.md', '.'),
        ('RELEASE_NOTES.md', '.'),
        ('THIRD_PARTY_LICENSES.md', '.'),
        ('engine_parameters.json', '.'),
        ('user_settings.json', '.'),
    ],
    hiddenimports=[],
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
    icon=['app/resources/icons/AppIcon.icns'],
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
app = BUNDLE(
    coll,
    name='CARA.app',
    icon='app/resources/icons/AppIcon.icns',
    bundle_identifier=None,
)

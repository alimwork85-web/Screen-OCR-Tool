# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['ocr_tool.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/app_icon.ico', 'assets'), ('assets/app_icon_64.png', 'assets'), ('assets/fonts/Tajawal-Regular.ttf', 'assets/fonts'), ('assets/fonts/Tajawal-Bold.ttf', 'assets/fonts')],
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
    a.binaries,
    a.datas,
    [],
    name='ocr_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
    version='version_info.txt',
)

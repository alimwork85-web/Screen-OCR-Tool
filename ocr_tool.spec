# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import sys

# DLLs تأخذ مسار binaries كي لا تُنسخ مرتين (PyInstaller يعامل أي .dll في datas كملف ثنائي أيضًا)
TESSERACT_DLLS = [(path, 'tesseract') for path in glob.glob(os.path.join('vendor/tesseract', '*.dll'))]
# Tcl يحتاج zlib1.dll في جذر الحزمة، ونسخة vendor تُحذف أدناه كتكرار، فنضيف نسخة Python صراحةً
PYTHON_ZLIB = os.path.join(sys.base_prefix, 'DLLs', 'zlib1.dll')
if os.path.exists(PYTHON_ZLIB):
    TESSERACT_DLLS.append((PYTHON_ZLIB, '.'))

a = Analysis(
    ['ocr_tool.py'],
    pathex=[],
    binaries=TESSERACT_DLLS,
    datas=[('assets/app_icon.ico', 'assets'), ('assets/app_icon_64.png', 'assets'), ('assets/app_icon_256.png', 'assets'), ('assets/fonts/Tajawal-Regular.ttf', 'assets/fonts'), ('assets/fonts/Tajawal-Bold.ttf', 'assets/fonts'), ('vendor/tesseract/tesseract.exe', 'tesseract'), ('vendor/tesseract/tessdata', 'tesseract/tessdata'), ('THIRD_PARTY_LICENSES.txt', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# bindepend يضيف تبعيات DLLs إلى جذر الحزمة، وهي موجودة أصلًا مع tesseract.exe في مجلده؛
# نحذف المنسوخ من vendor فقط، لا نسخًا أخرى تحمل الاسم نفسه يحتاجها البرنامج (مثل zlib1.dll لـ tkinter)
VENDOR_DIR = os.path.abspath(os.path.join('vendor', 'tesseract')).lower() + os.sep
a.binaries = [entry for entry in a.binaries
              if not (os.path.abspath(entry[1]).lower().startswith(VENDOR_DIR) and os.sep not in entry[0])]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ocr_tool',
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
    icon='assets/app_icon.ico',
    version='version_info.txt',
)
# بناء بمجلد بدل ملف واحد: لا يُفك البرنامج في Temp عند كل تشغيل فلا تتراكم مجلدات _MEI
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ocr_tool',
)

# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
if sys.platform == 'win32':
    hiddenimports += collect_submodules('plyer')       # Windows pop-up notifications
hiddenimports += collect_submodules('qrcode')       # Google Authenticator QR code (loads its image classes by name)


a = Analysis(
    ['login_app.py'],
    pathex=[],
    binaries=[],
    datas=[('chat.key', '.'), ('server.crt', '.'), ('icon.png', '.'), ('icon.ico', '.')],
    hiddenimports=hiddenimports,
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
    name='ChatClient',
    icon='icon.ico',
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
    name='ChatClient',
)

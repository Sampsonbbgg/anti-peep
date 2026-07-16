# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('config/default.yml', 'config'),
    ('assets/moyu.ico', 'assets'),
    ('assets/moyu.png', 'assets'),
]
datas += collect_data_files('mediapipe')

# 添加所有模块目录
hiddenimports = [
    'moyu',
    'moyu.core',
    'moyu.core.constants',
    'moyu.core.config_loader',
    'moyu.core.config_store',
    'moyu.core.deps',
    'moyu.core.detector',
    'moyu.core.paths',
    'moyu.platforms.windows_session',
    'moyu.runners.headless',
    'moyu.services',
    'moyu.services.lock_screen_capture',
    'moyu.services.snapshot',
    'moyu.services.work_app',
    'moyu.ui',
    'moyu.ui.tray',
    'moyu.ui.ui_app',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    a.binaries,
    a.datas,
    [],
    name='moyu',
    icon='assets/moyu.ico',
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
)

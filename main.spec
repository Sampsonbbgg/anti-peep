# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('config/default.yml', 'config'),
    ('assets/anti-peep.ico', 'assets'),
    ('assets/anti-peep.png', 'assets'),
]
datas += collect_data_files('mediapipe')

# 人脸模型目录（如已下载则一并打包，否则首次运行时自动下载）
if os.path.isdir('models'):
    datas += [('models', 'models')]

# 添加所有模块目录
hiddenimports = [
    'anti_peep',
    'anti_peep.core',
    'anti_peep.core.constants',
    'anti_peep.core.config_loader',
    'anti_peep.core.config_store',
    'anti_peep.core.deps',
    'anti_peep.core.detector',
    'anti_peep.core.face_engine',
    'anti_peep.core.owner_store',
    'anti_peep.core.analysis_worker',
    'anti_peep.core.paths',
    'anti_peep.platforms.windows_session',
    'anti_peep.runners.headless',
    'anti_peep.services',
    'anti_peep.services.lock_screen_capture',
    'anti_peep.services.snapshot',
    'anti_peep.services.work_app',
    'anti_peep.services.privacy_guard',
    'anti_peep.services.screen_shield',
    'anti_peep.services.monitors',
    'anti_peep.services.hotkey',
    'anti_peep.ui',
    'anti_peep.ui.tray',
    'anti_peep.ui.ui_app',
    'anti_peep.ui.enroll_dialog',
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
    name='anti-peep',
    icon='assets/anti-peep.ico',
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

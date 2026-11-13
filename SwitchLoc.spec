# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('build_assets/splash.png', 'build_assets'), ('build_assets/logo.png', 'build_assets'), ('build_assets/icon.png', 'build_assets'), ('build_assets/fonts', 'build_assets/fonts'), ('build_assets/help', 'build_assets/help'), ('data/geography/ardabil_places.sqlite', 'data/geography')]
binaries = []
hiddenimports = ['shapefile', 'PySide6.QtSvg', 'matplotlib.backends.backend_qtagg', 'switchloc.ui.osm_tiles', 'switchloc.ui.qt.splash', 'switchloc.ui.qt.settings_dialog', 'switchloc.ui.qt.chrome', 'switchloc.ui.qt.theme', 'switchloc.ui.qt.icons', 'switchloc.ui.qt.i18n', 'switchloc.ui.qt.worker']
tmp_ret = collect_all('arabic_reshaper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('bidi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['build_tools/entry_gui.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'switchloc.cli'],
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
    name='SwitchLoc',
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
    icon=['build_assets/icon.ico'],
)

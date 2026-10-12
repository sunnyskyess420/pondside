# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for Pondside.

Bundles ``assets/`` - the glade, Peepers' poses, the bundled fonts - read-only
inside the EXE. Build windowed, because Pondside is a companion that lives in
the corner of the screen, not something that should ever open a black console.

Your data is deliberately *not* in here. PyInstaller unpacks a onefile build
into a temp folder that Windows deletes on exit, so paths.py resolves the
database, config, log and exports next to the EXE instead. See paths.py.

Build with:
    py -3.14 -m PyInstaller --noconfirm --clean Pondside.spec
or just run build_pondside_exe.bat.
"""

APP_NAME = "Pondside"
ENTRY = "pondside.py"

a = Analysis(
    [ENTRY],
    pathex=[],
    binaries=[],
    # ('source', 'destination inside the bundle')
    datas=[
        ("assets", "assets"),
        ("config.template.json", "."),
    ],
    # pystray chooses its backend at runtime, so PyInstaller cannot see this.
    hiddenimports=["pystray._win32"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # None of these are used by the app itself - only by tools/build_peepers.py,
    # which never ships. Dropping them keeps the EXE small.
    excludes=[
        "numpy", "cv2", "scipy", "matplotlib", "pandas",
        "pytest", "unittest", "pydoc", "doctest",
    ],
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/pondside.ico",
)

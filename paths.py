"""Where Pondside keeps its art, and where it keeps your data.

These are deliberately two different places, because once the app is packaged
they stop being the same folder.

When PyInstaller freezes Pondside (--onefile), ``__file__`` points into a temp
extraction directory that Windows deletes when the app exits. Anything written
there is gone next launch, so it must never hold your data. The split is:

  * **read-only art and fonts** ship inside the bundle  -> ``ASSETS``
  * **your database, config, log and exports** live next to the EXE -> data

Pondside is installed per-user (``{userpf}``, no admin required), so the folder
next to the EXE is writable and your data stays beside the app where you can
see it, copy it and back it up. Nothing is hidden in a system folder.

Run it straight from source - which is how it runs on this machine - and both
resolve to the project folder, so nothing moves and there is nothing to
migrate.
"""

import sys
from pathlib import Path

# PyInstaller sets sys.frozen and unpacks the bundle into sys._MEIPASS.
FROZEN = bool(getattr(sys, "frozen", False))
SOURCE_DIR = Path(__file__).resolve().parent


def bundle_dir():
    """Read-only art, bundled into the EXE once packaged."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
    return SOURCE_DIR


def data_dir():
    """Writable home for the database, config, log and exports."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return SOURCE_DIR


BUNDLE_DIR = bundle_dir()
DATA_DIR = data_dir()

# ── read-only ─────────────────────────────────────────────────────────────
ASSETS = BUNDLE_DIR / "assets"

# ── yours ─────────────────────────────────────────────────────────────────
DB_PATH = DATA_DIR / "pondside.db"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "pondside.log"
EXPORTS_DIR = DATA_DIR / "exports"

#!/usr/bin/env python
"""Pondside M0 - headless checks.

Run from the project root:
    py -3.14 tests\\check_m0.py

Proves (no window, no network):
  1. pondside.py and data.py compile.
  2. The scene, icon and all four font files are present and loadable.
  3. Check-ins and breaths round-trip through the database (temp file).
  4. A database written before the breaths table had a pattern column is
     upgraded in place, losing nothing, and upgrading twice is harmless.
  5. config.template.json is valid and shaped the way the app expects.

Exits non-zero if anything fails.
"""

import json
import sqlite3
import sys
import tempfile
import time
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = "\x1b[32m[PASS]\x1b[0m"
FAIL = "\x1b[31m[FAIL]\x1b[0m"

passes = 0
failures = 0


def check(name, condition, detail=""):
    global passes, failures
    if condition:
        passes += 1
        print(f"{PASS} {name}")
    else:
        failures += 1
        print(f"{FAIL} {name} -> {detail}")


def main():
    print("Pondside M0 checks")
    print("=" * 40)

    # 1. compile
    for fname in ("pondside.py", "data.py"):
        try:
            py_compile.compile(str(ROOT / fname), doraise=True)
            check(f"{fname} compiles", True)
        except Exception as e:
            check(f"{fname} compiles", False, str(e))

    # 2. assets
    for asset in ("assets/scene.png", "assets/icon.png"):
        p = ROOT / asset
        check(f"{asset} exists", p.exists() and p.stat().st_size > 1000,
              f"{p} missing or too small")

    try:
        from PIL import ImageFont, Image
        for f in sorted((ROOT / "assets" / "fonts").rglob("*.ttf")):
            try:
                fit = ImageFont.truetype(str(f), 24)
                family, style = fit.getname()
                check(f"font loads: {f.name}", bool(family), f"{family}/{style}")
            except Exception as e:
                check(f"font loads: {f.name}", False, str(e))
        try:
            Image.open(ROOT / "assets" / "scene.png").verify()
            check("scene.png is a valid image", True)
        except Exception as e:
            check("scene.png is a valid image", False, str(e))
    except ImportError:
        check("PIL available", False, "install pillow (py -3.14 -m pip install pillow)")

    # 3. data round-trip (temp db, never touches the real one)
    import data as pdata
    tmp = Path(tempfile.mkdtemp()) / "check.db"
    try:
        pdata.init_db(tmp)
        n1 = pdata.add_checkin("Okayish", path=tmp)
        n2 = pdata.add_checkin("Good", path=tmp)
        check("check-ins save and count", (n1, n2) == (1, 2), f"got {(n1, n2)}")
        pdata.add_breath(60, True, path=tmp)
        pdata.add_breath(20, False, path=tmp)
        st = pdata.stats(tmp)
        check("breaths save and count", st["breaths"] == 2, str(st))
        check("stats totals", st["checkins"] == 2 and st["breaths"] == 2, str(st))
    except Exception as e:
        check("data round-trip", False, str(e))

    # 4. the breaths table remembers which pattern a breath was done in, and a
    # database from before that column existed is upgraded in place without
    # losing a single row of anyone's history.
    old = Path(tempfile.mkdtemp()) / "old.db"
    try:
        with sqlite3.connect(str(old)) as c:
            c.execute("CREATE TABLE breaths("
                      "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,"
                      " seconds INTEGER NOT NULL, completed INTEGER NOT NULL)")
            c.execute("INSERT INTO breaths(ts, seconds, completed) VALUES(?,?,?)",
                      (time.time() - 120, 60, 1))
        cols_before = [r[1] for r in
                       sqlite3.connect(str(old)).execute("PRAGMA table_info(breaths)")]
        check("an old database has no pattern column yet",
              "pattern" not in cols_before, str(cols_before))

        pdata.init_db(old)
        cols_after = [r[1] for r in
                      sqlite3.connect(str(old)).execute("PRAGMA table_info(breaths)")]
        check("upgrading adds the pattern column",
              "pattern" in cols_after, str(cols_after))
        with sqlite3.connect(str(old)) as c:
            rows = c.execute(
                "SELECT seconds, completed, pattern FROM breaths").fetchall()
        check("upgrading loses none of your history",
              rows == [(60, 1, None)], str(rows))

        pdata.init_db(old)
        cols_again = [r[1] for r in
                      sqlite3.connect(str(old)).execute("PRAGMA table_info(breaths)")]
        check("upgrading an already-upgraded database is harmless",
              cols_again == cols_after, str(cols_again))

        pdata.add_breath(64, True, pattern="box", path=old)
        with sqlite3.connect(str(old)) as c:
            stored = c.execute("SELECT pattern FROM breaths ORDER BY id").fetchall()
        check("a new breath records its pattern",
              stored == [(None,), ("box",)], str(stored))
        check("a breath from before is left alone, not guessed at",
              pdata.week_patterns(0, path=old) == [("box", 1)],
              str(pdata.week_patterns(0, path=old)))

        # The backup must carry the new column, or a restore would quietly
        # lose which patterns someone was breathing.
        dumped = pdata.dump_all(path=old)["breaths"]
        check("a backup carries the pattern with each breath",
              dumped and "pattern" in dumped[0],
              str(dumped[:1]))
    except Exception as e:
        check("breath pattern upgrade", False, str(e))

    # 4. config template
    try:
        cfg = json.loads((ROOT / "config.template.json").read_text(encoding="utf-8"))
        check("config.template.json valid", isinstance(cfg, dict), "")
        check("config has a font key", "font" in cfg, str(cfg))
    except Exception as e:
        check("config.template.json valid", False, str(e))

    # 5. paths: read-only art must ship inside the bundle, but your data must
    # never be written into it. When frozen, __file__ sits in a temp folder
    # that Windows deletes on exit, so data has to resolve next to the EXE.
    # Running from source both point at the project, so nothing is migrated.
    import importlib
    import paths as pathsmod

    check("from source: data stays in the project folder",
          pathsmod.DATA_DIR == ROOT and pathsmod.BUNDLE_DIR == ROOT,
          f"bundle={pathsmod.BUNDLE_DIR} data={pathsmod.DATA_DIR}")
    check("from source: assets resolve inside the project",
          pathsmod.ASSETS == ROOT / "assets", str(pathsmod.ASSETS))
    check("from source: database sits beside the app",
          pathsmod.DB_PATH == ROOT / "pondside.db", str(pathsmod.DB_PATH))

    real_exe = sys.executable
    had_frozen = hasattr(sys, "frozen")
    try:
        fake_bundle = Path(tempfile.mkdtemp()) / "_MEI12345"
        fake_bundle.mkdir(parents=True, exist_ok=True)
        fake_app = Path(tempfile.mkdtemp())
        sys.frozen = True
        sys._MEIPASS = str(fake_bundle)
        sys.executable = str(fake_app / "Pondside.exe")
        pathsmod = importlib.reload(pathsmod)

        check("frozen: art is read from the unpacked bundle",
              pathsmod.BUNDLE_DIR == fake_bundle, str(pathsmod.BUNDLE_DIR))
        check("frozen: assets come from the bundle",
              pathsmod.ASSETS == fake_bundle / "assets", str(pathsmod.ASSETS))
        check("frozen: data goes next to the EXE, not the temp dir",
              pathsmod.DATA_DIR == fake_app, str(pathsmod.DATA_DIR))
        check("frozen: the database is never written into the bundle",
              pathsmod.DB_PATH.parent != pathsmod.BUNDLE_DIR
              and "_MEI" not in str(pathsmod.DB_PATH),
              str(pathsmod.DB_PATH))
        check("frozen: config and log follow the same rule",
              pathsmod.CONFIG_PATH.parent == fake_app
              and pathsmod.LOG_PATH.parent == fake_app, "")
    except Exception as e:
        check("frozen path resolution", False, str(e))
    finally:
        if not had_frozen:
            try:
                del sys.frozen
            except AttributeError:
                pass
        try:
            del sys._MEIPASS
        except AttributeError:
            pass
        sys.executable = real_exe
        importlib.reload(pathsmod)

    check("paths restored after the frozen simulation",
          pathsmod.DATA_DIR == ROOT and pathsmod.BUNDLE_DIR == ROOT,
          f"bundle={pathsmod.BUNDLE_DIR} data={pathsmod.DATA_DIR}")

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

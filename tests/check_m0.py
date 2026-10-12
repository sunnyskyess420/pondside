#!/usr/bin/env python
"""Pondside M0 - headless checks.

Run from the project root:
    py -3.14 tests\\check_m0.py

Proves (no window, no network):
  1. pondside.py and data.py compile.
  2. The scene, icon and all four font files are present and loadable.
  3. Check-ins and breaths round-trip through the database (temp file).
  4. config.template.json is valid and shaped the way the app expects.

Exits non-zero if anything fails.
"""

import json
import sys
import tempfile
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

    # 4. config template
    try:
        cfg = json.loads((ROOT / "config.template.json").read_text(encoding="utf-8"))
        check("config.template.json valid", isinstance(cfg, dict), "")
        check("config has a font key", "font" in cfg, str(cfg))
    except Exception as e:
        check("config.template.json valid", False, str(e))

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

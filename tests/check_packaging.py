#!/usr/bin/env python
"""Pondside M4 - headless checks for the packaging recipe.

Run from the project root:
    py -3.14 tests\\check_packaging.py

These do not build anything - building takes a minute and needs PyInstaller
and Inno Setup. They check the recipes themselves, so the things that only
break when somebody actually ships drift out of sync:

  1. The PyInstaller spec exists, is windowed, bundles the art, and points at
     the icon.
  2. A multi-size .ico exists, because Windows installers and shortcuts need
     more sizes than the app ever draws.
  3. The installer script installs per-user without admin, and its version
     matches the app's own APP_VERSION - the classic thing to forget to bump.
  4. The installer never deletes the user's data on uninstall.
  5. Build outputs are gitignored, so a 32 MB EXE never lands in the repo.

Exits non-zero if anything fails.
"""

import re
import sys
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
    print("Pondside M4 checks")
    print("=" * 40)

    import pondside as ps

    spec_path = ROOT / "Pondside.spec"
    iss_path = ROOT / "pondside.iss"
    ico_path = ROOT / "assets" / "pondside.ico"

    # ── the PyInstaller recipe ────────────────────────────────────────────
    check("Pondside.spec exists", spec_path.exists(), str(spec_path))
    spec = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""

    if spec:
        check("spec builds pondside.py", 'ENTRY = "pondside.py"' in spec
              or "pondside.py" in spec, "entry point missing")
        check("spec bundles the art read-only", '("assets", "assets")' in spec,
              "assets would not ship inside the EXE")
        check("spec bundles the Windows tray backend",
              "pystray._win32" in spec,
              "pystray picks its backend at runtime and would be missed")
        check("spec builds windowed, not with a console",
              re.search(r"console\s*=\s*False", spec) is not None,
              "a companion app should never open a black console")
        check("spec sets the application icon",
              "assets/pondside.ico" in spec, "icon not referenced")

    # ── the icon ──────────────────────────────────────────────────────────
    check("a .ico exists for Windows", ico_path.exists(), str(ico_path))
    if ico_path.exists():
        try:
            from PIL import Image

            sizes = sorted(Image.open(ico_path).info.get("sizes", []))
            check("icon carries several sizes", len(sizes) >= 3, str(sizes))
            check("icon includes a small 16px size",
                  (16, 16) in sizes or any(s[0] == 16 for s in sizes), str(sizes))
            check("icon includes a large 256px size",
                  any(s[0] == 256 for s in sizes), str(sizes))
        except Exception as e:
            check("icon is a readable image", False, str(e))

    # ── the installer recipe ──────────────────────────────────────────────
    check("pondside.iss exists", iss_path.exists(), str(iss_path))
    iss = iss_path.read_text(encoding="utf-8") if iss_path.exists() else ""

    if iss:
        check("installer needs no administrator",
              "PrivilegesRequired=lowest" in iss,
              "an admin prompt would be a bad first impression")
        check("installer installs per-user",
              "DefaultDirName={userpf}" in iss,
              "data must live in a writable folder beside the EXE")
        check("installer sets up its own icon and uninstaller icon",
              "SetupIconFile=" in iss and "UninstallDisplayIcon=" in iss, "")
        check("installer seeds config without overwriting an existing one",
              "onlyifdoesntexist" in iss, "")

        # THE important one: uninstalling must never destroy the record of how
        # someone has been. Inno only deletes what it installed, so the only
        # way to get this wrong is an [UninstallDelete] aimed at their data.
        delete_block = re.search(r"\[UninstallDelete\](.*?)(\n\[|\Z)",
                                 iss, re.S)
        offenders = []
        if delete_block:
            for line in delete_block.group(1).splitlines():
                low = line.lower()
                if low.strip().startswith((";", "type:", "name:")) and any(
                        token in low for token in
                        ("pondside.db", "exports", "config.json")):
                    offenders.append(line.strip())
        check("uninstall never deletes your data", not offenders,
              f"would delete: {offenders}")

        # Version drift: the app and the installer must agree.
        m = re.search(r'#define\s+AppVersion\s+"([^"]+)"', iss)
        check("installer declares a version", m is not None, "no AppVersion")
        if m:
            check("installer version matches the app",
                  m.group(1) == ps.APP_VERSION,
                  f"installer {m.group(1)} vs app {ps.APP_VERSION}")

        check("installer has a stable AppId",
              re.search(r"AppId=\{\{[0-9a-fA-F-]{36}\}", iss) is not None,
              "Windows uses this to recognise upgrades")

    # ── build scripts ─────────────────────────────────────────────────────
    for script in ("build_pondside_exe.bat", "build_installer.bat"):
        p = ROOT / script
        check(f"{script} exists", p.exists(), str(p))

    # ── nothing built should ever be committed ─────────────────────────────
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for artifact in ("build/", "dist/", "installer_output/"):
        check(f"git ignores {artifact}", artifact in ignore,
              "a 32 MB EXE would land in the repo")

    # ── the app can report on itself ───────────────────────────────────────
    check("the app exposes a version", bool(ps.APP_VERSION), "")
    check("the app can describe where its files live",
          callable(getattr(ps, "selftest", None)),
          "a packaged app needs this; it has no console to print to")

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

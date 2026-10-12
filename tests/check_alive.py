#!/usr/bin/env python
"""Pondside M3.5 - headless checks for "Peepers alive".

Run from the project root:
    py -3.14 tests\\check_alive.py

Proves (no window, no network):
  1. pondside.py and the asset builder compile.
  2. The three actor poses exist, are transparent PNGs, and are sane.
  3. The anti-pop invariant: every pose is the *same shape* as the hero pose,
     so a blink can never resize or shift him.
  4. The fallback is all-or-nothing: with the backdrop or any one pose
     missing, the feature switches off and the baked scene is used instead.
  5. The blink/breathe timings are gentle.

Exits non-zero if anything fails.
"""

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
    print("Pondside M3.5 checks")
    print("=" * 40)

    for fname in ("pondside.py", "tools/build_peepers.py"):
        try:
            py_compile.compile(str(ROOT / fname), doraise=True)
            check(f"{fname} compiles", True)
        except Exception as e:
            check(f"{fname} compiles", False, str(e))

    import pondside as ps

    from PIL import Image, ImageChops

    # ── the poses ─────────────────────────────────────────────────────────
    poses = {}
    for name in ps.POSES:
        path = ps.PEEPERS_DIR / f"peepers_{name}.png"
        check(f"pose exists: peepers_{name}.png", path.exists(), str(path))
        if not path.exists():
            continue
        im = Image.open(path)
        poses[name] = im
        check(f"pose is transparent: peepers_{name}.png", im.mode == "RGBA",
              im.mode)
        if im.mode != "RGBA":
            continue
        alpha = im.getchannel("A")
        lo, hi = alpha.getextrema()
        check(f"pose has real transparency: peepers_{name}.png",
              lo == 0 and hi == 255, f"alpha range {lo}..{hi}")
        check(f"pose is a sensible size: peepers_{name}.png",
              im.height >= 64 and im.width >= 64, str(im.size))

    check("all three poses loaded", len(poses) == len(ps.POSES), str(sorted(poses)))

    # ── the anti-pop invariant ────────────────────────────────────────────
    # Every pose must be the same picture shape. This is the check that
    # keeps a blink from looking like a jump.
    sizes = {n: im.size for n, im in poses.items()}
    check("every pose shares one canvas size",
          len(set(sizes.values())) == 1, str(sizes))

    if len(poses) == len(ps.POSES) and len(set(sizes.values())) == 1:
        def silhouette(im):
            return im.getchannel("A").point(lambda v: 255 if v > 128 else 0)

        hero = silhouette(poses["awake"])
        for name in ps.POSES:
            if name == "awake":
                continue
            delta = ImageChops.difference(hero, silhouette(poses[name]))
            check(f"pose silhouette matches the hero: {name}",
                  delta.getbbox() is None,
                  "silhouettes differ - a blink would visibly jump")

    # ── the backdrop ──────────────────────────────────────────────────────
    check("frog-free backdrop installed", ps.SCENE_BASE_PATH.exists(),
          str(ps.SCENE_BASE_PATH))
    if ps.SCENE_BASE_PATH.exists() and (ROOT / "assets" / "scene.png").exists():
        check("backdrop matches the baked scene's size",
              Image.open(ps.SCENE_BASE_PATH).size
              == Image.open(ROOT / "assets" / "scene.png").size,
              "a size mismatch would shift the whole crop")

    # ── the fallback is all-or-nothing ────────────────────────────────────
    tmp = Path(tempfile.mkdtemp())
    folder = tmp / "peepers"
    folder.mkdir()
    base = tmp / "scene_base.png"
    check("fallback: no art at all -> off",
          ps.peepers_assets_ready(base, folder) is False)
    base.write_bytes(b"x")
    check("fallback: backdrop but no poses -> off",
          ps.peepers_assets_ready(base, folder) is False)
    for name in ps.POSES:
        (folder / f"peepers_{name}.png").write_bytes(b"x")
    check("fallback: complete art -> on",
          ps.peepers_assets_ready(base, folder) is True)
    (folder / "peepers_sleep.png").unlink()
    check("fallback: one pose missing -> off again",
          ps.peepers_assets_ready(base, folder) is False)

    # ── gentle timings ────────────────────────────────────────────────────
    gap_lo, gap_hi = ps.BLINK_GAP
    bl_lo, bl_hi = ps.BLINK_LEN
    check("blink is brief", 0.05 <= bl_lo and bl_hi <= 0.4,
          f"{ps.BLINK_LEN}")
    check("blink is much shorter than the gap", bl_hi < gap_lo,
          f"blink {bl_hi}s vs gap {gap_lo}s")
    check("breathing is subtle", 0 <= ps.BREATHE_PX <= 4, str(ps.BREATHE_PX))
    check("breathing is slow", ps.BREATHE_SECONDS >= 3.0,
          str(ps.BREATHE_SECONDS))
    check("breath is pre-rendered in steps", ps.BREATHE_FRAMES >= 2,
          str(ps.BREATHE_FRAMES))

    # He must breathe from a planted base. The draw code places him at
    # TOP + H - frame_height, so the bottom edge is the same for every frame
    # no matter how tall it is. Recompute that here: if someone reintroduces
    # a vertical offset, the whole frog slides and this fails.
    feet = ps.PEEPERS_TOP + ps.PEEPERS_H
    heights, bottoms = set(), set()
    for step in range(ps.BREATHE_FRAMES):
        h = ps.PEEPERS_H + round(
            ps.BREATHE_PX * step / max(1, ps.BREATHE_FRAMES - 1))
        heights.add(h)
        bottoms.add(ps.PEEPERS_TOP + ps.PEEPERS_H - h + h)
    check("breath always lands on the same feet", bottoms == {feet},
          f"feet drifted: {sorted(bottoms)}")
    # Guard the trap where a small rise rounds every frame back to the same
    # height: breathing would silently stop while still looking configured.
    if ps.BREATHE_PX > 0:
        check("the breath really changes his size", len(heights) > 1,
              f"all {ps.BREATHE_FRAMES} frames are {sorted(heights)} tall")
    else:
        check("breathing off means one still frame", len(heights) == 1,
              str(sorted(heights)))

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Build Peepers' animation poses (M3.5).

Why this exists
---------------
The three raw art passes in ``assets/_alive_pass/`` were separate AI
generations, and they do not match each other geometrically: the ``awake``
frog carries ~65% more area than the ``blink`` frog, so swapping between them
would visibly resize him mid-blink. A blink has to be a 150 ms event, which
makes that pop impossible to hide.

So we keep ``awake`` - the pose the handoff calls the strongest match to the
original Peepers - as the hero, and derive the other two from it by closing his
eyes. The silhouette, scale and registration are then identical by
construction, and there is no way for him to jump.

Run from the project root:
    py -3.14 tools\\build_peepers.py

Writes ``assets/peepers/peepers_blink.png`` and ``peepers_sleep.png``.
``peepers_awake.png`` is an input (cut from the raw art) and is never rewritten.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PEEPERS = ROOT / "assets" / "peepers"
AWAKE = PEEPERS / "peepers_awake.png"

EYE_MIN_AREA = 2000     # ignore nostrils, mouth lines and stray speckle
EYE_LID_GROW = 1.18     # the lid reaches a little past the dark pupil
LID_DARKEN = 0.72       # lid crease tone, as a fraction of the skin colour
CREASE_W = 0.055        # crease thickness, as a fraction of the eye width
FEATHER = 0.035         # soft edge, as a fraction of the eye width


def find_eyes(rgba):
    """Return [(cx, cy, half_w, half_h), ...] for the two eyes, left to right."""
    alpha = rgba[..., 3]
    rgb = rgba[..., :3].astype(np.int16)
    h, w = alpha.shape
    dark = ((alpha > 128) & (rgb.max(axis=2) < 100)).astype(np.uint8)
    top = dark.copy()
    top[int(h * 0.40):, :] = 0          # eyes sit in the upper part of the head
    top = cv2.erode(top, np.ones((5, 5), np.uint8))

    n, _lab, stats, cent = cv2.connectedComponentsWithStats(top, 8)
    eyes = []
    for i in range(1, n):
        area = stats[i, 4]
        if area >= EYE_MIN_AREA:
            x, y, bw, bh, _ = stats[i]
            eyes.append((float(cent[i][0]), float(cent[i][1]),
                         float(bw) / 2.0, float(bh) / 2.0))
    if len(eyes) < 2:
        raise SystemExit(
            f"expected two eyes in {AWAKE.name}, found {len(eyes)} - not touching it")
    eyes.sort(key=lambda e: e[0])
    return eyes


def skin_colour(rgba, cx, cy, rx, ry):
    """Median skin tone just outside an eye, so the lid always matches."""
    alpha = rgba[..., 3]
    rgb = rgba[..., :3].astype(np.int16)
    h, w = alpha.shape
    ys, xs = np.mgrid[0:h, 0:w]
    d = ((xs - cx) / (rx * 1.85)) ** 2 + ((ys - cy) / (ry * 2.35)) ** 2
    ring = (d > 1.0) & (d < 2.4) & (alpha > 200) & (rgb.max(axis=2) > 100)
    if ring.sum() < 50:                     # fall back to any nearby skin
        ring = (d < 3.0) & (alpha > 200) & (rgb.max(axis=2) > 100)
    if ring.sum() < 10:
        return (150, 175, 110)
    px = rgb[ring]
    return tuple(int(v) for v in np.median(px, axis=0))


def close_eyes(rgba, eyes, deepen=0.0):
    """Return a copy of *rgba* with both eyes shut.

    *deepen* pushes the lid a touch darker, which reads as the heavier sleep
    of the nap view without changing his shape at all.
    """
    h, w = rgba.shape[:2]
    out = Image.fromarray(rgba.copy())
    for (cx, cy, rx, ry) in eyes:
        cx, cy = float(cx), float(cy)
        lid_w = float(rx) * EYE_LID_GROW
        lid_h = float(ry) * EYE_LID_GROW
        base = skin_colour(rgba, cx, cy, rx, ry)
        tone = tuple(max(0, min(255, int(c * (LID_DARKEN - deepen))))
                     for c in base)

        # soft mask for the lid, feathered so there is no visible seam
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((cx - lid_w, cy - lid_h, cx + lid_w, cy + lid_h), fill=255)
        blur = float(max(1.0, lid_w * FEATHER))
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
        out = Image.composite(Image.new("RGBA", (w, h), tone + (255,)),
                              out, mask)

        # the crease: a shallow arc across the lower half of the lid
        crease = Image.new("L", (w, h), 0)
        cd = ImageDraw.Draw(crease)
        steps = 40
        pts = []
        for k in range(steps + 1):
            t = k / steps
            ang = np.pi * (0.12 + 0.76 * t)          # a gentle downward bow
            pts.append((cx - lid_w * np.cos(ang) * 0.94,
                        cy + lid_h * np.sin(ang) * 0.72))
        cd.line(pts, fill=255, width=int(max(2, lid_w * 2 * CREASE_W)),
                joint="curve")
        crease = crease.filter(
            ImageFilter.GaussianBlur(float(max(1.0, lid_w * 0.05))))
        crease_tone = tuple(max(0, min(255, int(c * 0.42))) for c in base)
        out = Image.composite(Image.new("RGBA", (w, h), crease_tone + (255,)),
                              out, crease)
    return np.asarray(out)


def main():
    if not AWAKE.exists():
        raise SystemExit(f"missing {AWAKE} - run the background cut first")
    awake = np.asarray(Image.open(AWAKE).convert("RGBA"))
    eyes = find_eyes(awake)
    print(f"{AWAKE.name}: {awake.shape[1]}x{awake.shape[0]}")
    for i, (cx, cy, rx, ry) in enumerate(eyes, 1):
        print(f"  eye {i}: centre=({cx:.0f},{cy:.0f}) radius=({rx:.0f},{ry:.0f})")

    for name, deepen in (("blink", 0.0), ("sleep", 0.06)):
        out = PEEPERS / f"peepers_{name}.png"
        Image.fromarray(close_eyes(awake, eyes, deepen)).save(out)
        print(f"  wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

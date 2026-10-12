# -*- coding: utf-8 -*-
"""Pondside - M1 prototype: Peepers gets timers, a journal and a week.

What M1 adds on top of M0:
  * Timers - start / finish, the duration is computed for you, then a gentle
    "did it help?" (or skip). Nothing counts against you.
  * Journal - short notes, saved locally.
  * Week - a gentle look back: what helped first, then soft numbers.

M0 remains: the glade, one-tap check-ins, the breath, the font pick, the
tray, quiet mode.

Run:
  py -3.14 pondside.py            (or run_pondside.bat for no console window)
  py -3.14 pondside.py --smoke    (opens, proves itself, closes after ~3s)

Rulebook (v1): no water is ever shown; nothing here should make a hard day
harder. Your data stays on this machine.
"""

import json
import math
import random
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from traceback import format_exc

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:  # pragma: no cover
    Image = None

from collections import namedtuple

import data as pdata

# Art ships inside the bundle; your data sits beside the app. See paths.py.
from paths import (ASSETS, BUNDLE_DIR, CONFIG_PATH, DATA_DIR, LOG_PATH)

APP_VERSION = "1.2.0"

# ── palette ───────────────────────────────────────────────────────────────
BG     = "#241F2E"
PANEL  = "#2E2739"
CTL    = "#362E44"
CTLBRD = "#544A66"
TEXT   = "#F2E9DC"
MUTED  = "#A99BC2"
SOFT   = "#7E7394"
GOLD   = "#E8C36A"
GOLDT  = "#3A2E17"
GREEN  = "#9CCB84"
GREENT = "#22301C"
HOVER  = "#4A4159"

WIN_W, WIN_H = 760, 940
SCENE_W, SCENE_H = 712, 400
SCENE_X, SCENE_Y = 24, 94

# ── M3.5 "Peepers alive" ─────────────────────────────────────────────────
# Peepers is drawn as a separate actor on top of a frog-free backdrop, so he
# can blink and breathe. If the backdrop or any pose is missing, every one of
# these paths is skipped and the app behaves exactly as it did before.
PEEPERS_DIR = ASSETS / "peepers"
SCENE_BASE_PATH = ASSETS / "scene_base.png"
POSES = ("awake", "blink", "sleep")
BLINK_GAP = (4.0, 7.0)     # seconds of looking around between blinks
BLINK_LEN = (0.13, 0.18)   # how long his eyes stay shut
BREATHE_SECONDS = 9.0      # one slow breath, barely perceptible
BREATHE_PX = 1             # how far his head rises (his feet never move)
BREATHE_FRAMES = 2         # pre-rendered breath steps; set BREATHE_PX=0 to still him
PEEPERS_TICK_MS = 60
# Where he sits, in scene-region coordinates (SCENE_X/SCENE_Y get added).
# These are the only numbers to nudge if he looks off - nothing else moves.
PEEPERS_CX = 284
PEEPERS_TOP = 78
PEEPERS_H = 167            # his height once drawn, in pixels

# ── breathing patterns ───────────────────────────────────────────────────
# A pattern is a shape you walk, one side at a time. Each side says what it
# is, how many seconds it lasts, and what the circle does while you are on
# it: "grow" widens it, "shrink" narrows it, "hold" keeps it at its widest
# and "rest" keeps it at its smallest. Rounds is how many times round.
#
# Sessions are always whole rounds of whatever you picked - never a side left
# half-breathed - so the totals differ between patterns and that is fine.
BreathPattern = namedtuple("BreathPattern", "key name blurb sides rounds")

PATTERNS = (
    BreathPattern(
        "box", "Box", "steady, for a hard moment",
        (("in…", 4.0, "grow"), ("hold…", 4.0, "hold"),
         ("out…", 4.0, "shrink"), ("hold…", 4.0, "rest")), 4),
    BreathPattern(
        "exhale", "Long exhale", "the one for stress",
        (("in…", 4.0, "grow"), ("out…", 6.0, "shrink")), 6),
    BreathPattern(
        "sleep", "Winding down", "in four, hold seven, out eight",
        (("in…", 4.0, "grow"), ("hold…", 7.0, "hold"),
         ("out…", 8.0, "shrink")), 3),
    BreathPattern(
        "even", "Even", "in five, out five, nothing to count",
        (("in…", 5.0, "grow"), ("out…", 5.0, "shrink")), 6),
)
DEFAULT_PATTERN = "box"

# What each stored key is called on screen. Derived, never typed twice, so the
# database and the Week view cannot disagree.
PATTERN_NAMES = {p.key: p.name for p in PATTERNS}

# On screen the circle travels the sides, between these two sizes.
BREATH_R_MIN = 70
BREATH_R_MAX = 150

_BREATH_WORDS = ("zero", "one", "two", "three", "four", "five", "six",
                 "seven", "eight", "nine", "ten", "eleven", "twelve")


def breath_word(n):
    n = int(round(n))
    return _BREATH_WORDS[n] if 0 <= n < len(_BREATH_WORDS) else str(n)


def pattern_by_key(key):
    """The pattern for a saved key, falling back to the default.

    An unknown or missing key (a fresh install, or a config from some other
    version) must land somewhere sensible rather than raising.
    """
    for p in PATTERNS:
        if p.key == key:
            return p
    for p in PATTERNS:
        if p.key == DEFAULT_PATTERN:
            return p
    return PATTERNS[0]


def pattern_cycle(pattern):
    """Seconds for one time round the shape."""
    return sum(secs for _label, secs, _move in pattern.sides)


def pattern_total(pattern):
    """Seconds for the whole session."""
    return pattern_cycle(pattern) * pattern.rounds


def pattern_words(pattern):
    """The 'four in  ·  four hold  ·  ...' line, built from the sides."""
    return "  ·  ".join(f"{breath_word(secs)} {label.rstrip('…')}"
                        for label, secs, _move in pattern.sides)


def breath_phase(elapsed, pattern):
    """Which side of the pattern we are on, and how far along it.

    Returns ``(index, label, progress)`` with progress 0..1 along that side.
    Pure, so the shape of any pattern can be checked without a window.
    """
    pos = elapsed % pattern_cycle(pattern)
    for index, (label, secs, _move) in enumerate(pattern.sides):
        if pos < secs:
            return index, label, pos / secs
        pos -= secs
    last = len(pattern.sides) - 1
    return last, pattern.sides[last][0], 1.0


def breath_radius(index, progress, pattern):
    """How wide the circle should be while you are on that side."""
    _label, _secs, move = pattern.sides[index]
    progress = max(0.0, min(1.0, progress))
    ease = 0.5 - 0.5 * math.cos(math.pi * progress)
    span = BREATH_R_MAX - BREATH_R_MIN
    if move == "grow":
        return BREATH_R_MIN + span * ease
    if move == "shrink":
        return BREATH_R_MAX - span * ease
    if move == "hold":
        return BREATH_R_MAX
    return BREATH_R_MIN     # "rest"


def peepers_assets_ready(scene_base=None, peepers_dir=None, poses=POSES):
    """Is the M3.5 art fully installed? Pure and headless, so it can be
    tested without a window. All-or-nothing: a half-copied art pass must not
    half-render, so one missing pose keeps the whole feature off."""
    base = Path(scene_base) if scene_base else SCENE_BASE_PATH
    folder = Path(peepers_dir) if peepers_dir else PEEPERS_DIR
    if not base.exists():
        return False
    return all((folder / f"peepers_{name}.png").exists() for name in poses)


def selftest():
    """Report where a running copy thinks its art and its data live.

    A packaged Pondside is built windowed, so there is no console to print to
    and a silent failure would look identical to success. This writes the
    same report to a file as well, which is how a frozen build gets verified.
    Returns 0 only when everything the app needs is actually present.
    """
    lines = [f"Pondside {APP_VERSION}"]
    lines.append(f"frozen        : {bool(getattr(sys, 'frozen', False))}")
    lines.append(f"bundle_dir    : {BUNDLE_DIR}")
    lines.append(f"data_dir      : {DATA_DIR}")

    ok = True

    def need(label, path):
        nonlocal ok
        exists = Path(path).exists()
        ok = ok and exists
        lines.append(f"{label:<14}: {path}  exists={exists}")

    need("assets", ASSETS)
    need("scene.png", ASSETS / "scene.png")
    need("icon.png", ASSETS / "icon.png")

    # The M3.5 art is optional by design: without it the app falls back to
    # the painted scene, so a missing pose is reported but never fatal.
    alive = peepers_assets_ready()
    lines.append(f"animated      : {alive}")
    lines.append(f"backdrop      : {SCENE_BASE_PATH}  exists={SCENE_BASE_PATH.exists()}")
    for name in POSES:
        p = PEEPERS_DIR / f"peepers_{name}.png"
        lines.append(f"pose {name:<8} : exists={p.exists()}")

    fonts = sorted(ASSETS.glob("fonts/**/*.ttf"))
    lines.append(f"bundled fonts : {len(fonts)}")
    ok = ok and len(fonts) >= 1

    # Anything imported lazily can be missed by the packager and then fail
    # only when someone tries that one thing, which is the worst way to find
    # out. Prove the Windows tray backend and the PDF writer are really here.
    for mod in ("PIL", "pystray", "pystray._win32",
                "reportlab.pdfgen.canvas"):
        try:
            __import__(mod)
            lines.append(f"import {mod:<20} : ok")
        except Exception as exc:
            ok = False
            lines.append(f"import {mod:<20} : FAILED {exc!r}")

    lines.append(f"template      : {(BUNDLE_DIR / 'config.template.json')}"
                 f"  exists={(BUNDLE_DIR / 'config.template.json').exists()}")

    # Prove the data side is genuinely writable, not just present.
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pdata.init_db()
        lines.append(f"database      : {pdata.DB_PATH}  writable=True")
    except Exception as exc:
        ok = False
        lines.append(f"database      : FAILED {exc!r}")

    lines.append(f"exports       : {DATA_DIR / 'exports'}")
    lines.append(f"RESULT        : {'OK' if ok else 'PROBLEMS FOUND'}")
    report = "\n".join(lines)

    try:
        print(report)
    except Exception:
        pass
    try:
        (DATA_DIR / "selftest.txt").write_text(report, encoding="utf-8")
    except Exception:
        ok = False
    return 0 if ok else 1


def log_error():
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(format_exc() + "\n")
    except Exception:
        pass


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        log_error()


def register_fonts():
    if sys.platform != "win32":
        return
    import ctypes
    FR_PRIVATE = 0x10
    for p in sorted(ASSETS.glob("fonts/**/*.ttf")):
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(p), FR_PRIVATE, 0)
        except Exception:
            log_error()


def fmt_dur(seconds):
    """Human, kind durations: '45 sec', '12 min', '1 h 5 min'."""
    s = int(seconds)
    if s < 60:
        return f"{s} sec"
    m = s // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"


def fmt_clock(seconds):
    s = int(seconds)
    if s >= 3600:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}"
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"


def rrect_points(x1, y1, x2, y2, r, steps=8):
    pts = []
    corners = [
        (x2 - r, y1 + r, -90, 0),
        (x2 - r, y2 - r, 0, 90),
        (x1 + r, y2 - r, 90, 180),
        (x1 + r, y1 + r, 180, 270),
    ]
    for cx, cy, a0, a1 in corners:
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
    return pts


def rrect(canvas, x1, y1, x2, y2, r, **kw):
    return canvas.create_polygon(rrect_points(x1, y1, x2, y2, r), **kw)


class CanvasButton:
    """A friendly rounded button drawn on the canvas."""

    def __init__(self, canvas, x1, y1, x2, y2, radius, text, font, command,
                 fill=CTL, hover=HOVER, text_fill=TEXT, outline=CTLBRD,
                 guard=None):
        self.canvas = canvas
        self.command = command
        self.guard = guard
        self.fill = fill
        self.hover = hover
        self.tag = f"btn{id(self)}"
        pts = rrect_points(x1, y1, x2, y2, radius)
        self.poly = canvas.create_polygon(
            pts, fill=fill, outline=outline, width=1, tags=(self.tag,))
        self.label = canvas.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2, text=text, font=font,
            fill=text_fill, tags=(self.tag,))
        canvas.tag_bind(self.tag, "<Enter>", self._enter)
        canvas.tag_bind(self.tag, "<Leave>", self._leave)
        canvas.tag_bind(self.tag, "<Button-1>", self._click)

    def _blocked(self):
        return self.guard is not None and getattr(self.guard, "modal", False)

    def _enter(self, _e):
        if not self._blocked():
            self.canvas.itemconfigure(self.poly, fill=self.hover)

    def _leave(self, _e):
        self.canvas.itemconfigure(self.poly, fill=self.fill)

    def _click(self, _e):
        if not self._blocked() and self.command:
            self.command()

    def set_style(self, fill=None, text_fill=None):
        if fill:
            self.fill = fill
            self.canvas.itemconfigure(self.poly, fill=fill)
        if text_fill:
            self.canvas.itemconfigure(self.label, fill=text_fill)


class Fonts:
    def __init__(self, root):
        fams = {f.lower(): f for f in tkfont.families(root)}

        def find(sub):
            for low, real in fams.items():
                if sub in low:
                    return real
            return None

        self.families = {"Quicksand": find("quicksand"), "Nunito": find("nunito")}
        self.choice = "Quicksand" if self.families["Quicksand"] else (
            "Nunito" if self.families["Nunito"] else "Segoe UI")

    def family_for(self, name):
        return self.families.get(name) or "Segoe UI"

    def f(self, name, size, bold=False):
        return (self.family_for(name), -abs(size), "bold" if bold else "normal")


class PondsideApp:
    def __init__(self, root, smoke=False):
        self.root = root
        self.smoke = smoke
        self.cfg = load_config()
        self.modal = False
        self.tray = None
        self.fireflies = []
        self.sprites = []
        self.scene_photo = None
        self._drag_origin = None
        self._anim_job = None
        self._breathe_job = None
        self._timer_job = None
        self._toast_job = None
        self._focus_job = None
        self._nav_job = None
        self._breath_start = 0.0
        self._breath_stopped = False
        self._widgets = []
        self._running = None  # {"id":..., "activity":..., "t0":..., "elapsed_id":...}
        self._pending = None  # a finished, un-saved session awaiting "did it help?"
        self.napping = False
        self.scene_dim = None
        self.alive = False          # True only when the M3.5 assets are present
        self.peepers_photos = {}
        self.peepers_id = None
        self._peepers_job = None
        self._blink_until = 0.0
        self._next_blink = 0.0
        # Timer displays. A running session outlives the view it was started
        # from, so these are cleared with the canvas but the timer is not.
        self.elapsed_id = None
        self.timer_line_id = None
        self.timer_nap_id = None
        self._timeline_job = None

        root.overrideredirect(True)
        root.configure(bg=BG)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(16, sw - WIN_W - 48)
        y = max(16, sh - WIN_H - 60)
        root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        self.canvas = tk.Canvas(root, width=WIN_W, height=WIN_H, bg=BG,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        pdata.init_db()
        pdata.close_stale_sessions()
        register_fonts()
        self.fonts = Fonts(root)
        saved = self.cfg.get("font")
        if saved in ("Quicksand", "Nunito") and self.fonts.families.get(saved):
            self.fonts.choice = saved

        # the breathing pattern you chose last; box is the one we start on
        self.breath_key = pattern_by_key(self.cfg.get("breath")).key

        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        root.bind("<Escape>", self._escape)

        self.show_main()

        if not smoke:
            if not self.cfg.get("first_run_done"):
                self.root.after(700, self.open_font_picker)
            self.root.after(300, self.start_tray)
        else:
            root.after(2600, self.quit)

    # ── plumbing ──────────────────────────────────────────────────────────
    def _press(self, event):
        if getattr(self, "_quiet_tap_guard", False):
            self._quiet_tap_guard = False
            return
        if self.napping:
            self.wake()
            return
        if event.y <= 84:
            self._drag_origin = (event.x_root - self.root.winfo_x(),
                                 event.y_root - self.root.winfo_y())
        else:
            self._drag_origin = None

    def _drag(self, event):
        if self._drag_origin:
            self.root.geometry(
                f"+{event.x_root - self._drag_origin[0]}"
                f"+{event.y_root - self._drag_origin[1]}")

    def _escape(self, _e):
        if self.modal:
            self.close_picker()

    def _after_job(self, attr, ms, fn):
        old = getattr(self, attr, None)
        if old:
            try:
                self.root.after_cancel(old)
            except Exception:
                pass

        def run():
            try:
                fn()
            except tk.TclError:
                pass
        setattr(self, attr, self.root.after(ms, run))

    def _focus_later(self, widget):
        """Focus an entry a moment after it appears - if it still exists.

        Walking straight into ``after(60, widget.focus_set)`` throws into the
        console when you have already moved on: by then the widget is gone.
        """

        def run():
            try:
                if widget.winfo_exists():
                    widget.focus_set()
            except tk.TclError:
                pass

        self._after_job("_focus_job", 60, run)

    def _cancel_jobs(self):
        for attr in ("_anim_job", "_breathe_job", "_timer_job", "_toast_job",
                     "_peepers_job", "_focus_job", "_nav_job"):
            job = getattr(self, attr)
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)

    def clear(self):
        self._cancel_jobs()
        for w in self._widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._widgets = []
        self.canvas.delete("all")
        self.fireflies = []
        self.peepers_id = None
        self.elapsed_id = None
        self.timer_line_id = None
        self.timer_nap_id = None

    def titlebar(self, title="Pondside", back=None):
        f = self.fonts
        if back:
            CanvasButton(self.canvas, 30, 18, 150, 56, 19, "‹  back",
                         f.f(f.choice, 18, True), back,
                         fill=CTL, hover=HOVER, text_fill=MUTED)
            self.canvas.create_text(174, 36, text=title, anchor="w",
                                    font=f.f(f.choice, 22, True), fill=TEXT)
        else:
            self.canvas.create_text(30, 36, text=title, anchor="w",
                                    font=f.f(f.choice, 24, True), fill=TEXT)
        CanvasButton(self.canvas, WIN_W - 74, 18, WIN_W - 36, 56, 19,
                     "×", f.f(f.choice, 20, True), self.quit,
                     fill=CTL, hover="#5A3A44", text_fill=MUTED)
        CanvasButton(self.canvas, WIN_W - 122, 18, WIN_W - 84, 56, 19,
                     "Aa", f.f(f.choice, 16, True), self.open_font_picker,
                     fill=CTL, hover=HOVER, text_fill=MUTED)
        self.canvas.create_line(16, 76, WIN_W - 16, 76, fill=CTLBRD)

    def back_button_ok(self):
        return True

    # ── main view ─────────────────────────────────────────────────────────
    def show_main(self):
        self.clear()
        self.modal = False
        self.napping = False
        f = self.fonts
        self.titlebar()

        self.place_scene()
        self.spawn_fireflies()

        self.canvas.create_text(32, 516, anchor="nw", text="Hi. I'm Peepers.",
                                font=f.f(f.choice, 31, True), fill=TEXT)
        self.canvas.create_text(32, 562, anchor="nw", text="How's the glade today?",
                                font=f.f(f.choice, 23), fill=MUTED)

        self.chip_ids = {}
        chips = [("Rough", 132), ("Okayish", 152), ("Good", 118)]
        cx = 32
        for label, width in chips:
            b = CanvasButton(self.canvas, cx, 622, cx + width, 676, 27,
                             label, f.f(f.choice, 21, True),
                             lambda m=label: self.set_mood(m))
            self.chip_ids[label] = b
            cx += width + 14

        breath = pattern_by_key(self.breath_key)
        CanvasButton(self.canvas, 32, 706, WIN_W - 32, 772, 22,
                     f"Breathe with me  ·  {breath.name}  ·  "
                     f"{int(pattern_total(breath))} sec",
                     f.f(f.choice, 24, True),
                     self.show_breathe, fill=GOLD, hover="#F2D284",
                     text_fill=GOLDT, outline=GOLD)

        # footer: the four little doors
        row_y1, row_y2 = 794, 848
        for (label, x1, x2, cmd) in (
            ("Timer",     50, 206, self.show_timer),
            ("Journal",  218, 374, self.show_journal),
            ("Week",     386, 542, self.show_week),
            ("Worry jar", 554, 710, self.show_worry),
        ):
            CanvasButton(self.canvas, x1, row_y1, x2, row_y2, 25,
                         label, f.f(f.choice, 19, True), cmd,
                         fill=CTL, hover=HOVER, text_fill=TEXT)

        self.quiet_id = self.canvas.create_text(
            WIN_W / 2, 878, text="quiet mode is always on — tap to let me nap",
            font=f.f(f.choice, 17), fill=SOFT, tags=("quietline",))
        self.canvas.tag_bind("quietline", "<Button-1>", self._quiet_tap)

        self.place_timer_pill()

        self._anim_job = self.root.after(70, self.animate)
        if self.alive:
            self._blink_until = 0.0
            self._next_blink = time.monotonic() + random.uniform(*BLINK_GAP)
            self._peepers_job = self.root.after(
                PEEPERS_TICK_MS, self.peepers_animate)

    def load_peepers(self):
        """Load the actor poses. Returns {} (and sets the fallback) if the
        backdrop or any single pose is missing - a half-installed art pass
        must never half-render."""
        if Image is None or not peepers_assets_ready():
            return {}
        out = {}
        try:
            for name in POSES:
                path = PEEPERS_DIR / f"peepers_{name}.png"
                if not path.exists():
                    return {}
                src = Image.open(path).convert("RGBA")
                frames = []
                for step in range(max(1, BREATHE_FRAMES)):
                    h = PEEPERS_H + round(
                        BREATHE_PX * step / max(1, BREATHE_FRAMES - 1))
                    w = max(1, round(src.width * (h / src.height)))
                    frames.append(ImageTk.PhotoImage(
                        src.resize((w, h), Image.LANCZOS)))
                out[name] = frames
        except Exception:
            log_error()
            return {}
        return out

    def draw_peepers(self, pose, level=0):
        """Put the actor on the canvas, or swap which pose and breath he's on.

        His feet are the anchor: a taller breath frame grows upward instead of
        sliding him, so he never appears to lift off the log.
        """
        frames = self.peepers_photos.get(pose)
        if not frames:
            return
        photo = frames[min(max(level, 0), len(frames) - 1)]
        x = SCENE_X + PEEPERS_CX - photo.width() / 2
        y = SCENE_Y + PEEPERS_TOP + PEEPERS_H - photo.height()
        if self.peepers_id is None or self.peepers_id not in self.canvas.find_all():
            self.peepers_id = self.canvas.create_image(
                x, y, image=photo, anchor="nw")
        else:
            self.canvas.itemconfigure(self.peepers_id, image=photo)
            self.canvas.coords(self.peepers_id, x, y)

    def place_scene(self):
        self.peepers_photos = self.load_peepers()
        self.alive = bool(self.peepers_photos)
        # the frog-free backdrop only takes over once the actor can stand on
        # it; otherwise we keep the original baked scene, untouched.
        base = SCENE_BASE_PATH if self.alive else ASSETS / "scene.png"
        self.peepers_id = None
        if Image is None:
            self.canvas.create_rectangle(SCENE_X, SCENE_Y, SCENE_X + SCENE_W,
                                         SCENE_Y + SCENE_H, fill=PANEL,
                                         outline=CTLBRD)
            return
        im = Image.open(base).convert("RGB")
        tr = SCENE_W / SCENE_H
        sr = im.width / im.height
        if sr > tr:
            nw = int(im.height * tr)
            x0 = (im.width - nw) // 2
            im = im.crop((x0, 0, x0 + nw, im.height))
        else:
            nh = int(im.width / tr)
            y0 = (im.height - nh) // 2
            im = im.crop((0, y0, im.width, y0 + nh))
        im = im.resize((SCENE_W, SCENE_H), Image.LANCZOS)
        mask = Image.new("L", (SCENE_W, SCENE_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, SCENE_W - 1, SCENE_H - 1), radius=20, fill=255)
        out = Image.new("RGBA", (SCENE_W, SCENE_H), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        self.scene_photo = ImageTk.PhotoImage(out)
        self.canvas.create_image(SCENE_X, SCENE_Y, image=self.scene_photo,
                                 anchor="nw")
        # a dimmed twin for napping
        dim = Image.blend(im, Image.new("RGB", im.size, (20, 16, 28)), 0.62)
        out_dim = Image.new("RGBA", (SCENE_W, SCENE_H), (0, 0, 0, 0))
        out_dim.paste(dim, (0, 0), mask)
        self.scene_dim = ImageTk.PhotoImage(out_dim)
        if self.alive:
            self.draw_peepers("awake")

    def peepers_animate(self):
        """One slow breath, and a blink every few seconds.

        A single tick drives both so there is never a second timer to stack
        or cancel, and every step is swallowed if the window is going away.
        """
        if not self.alive:
            return
        try:
            now = time.monotonic()
            if self._blink_until and now >= self._blink_until:
                self._blink_until = 0.0
                self._next_blink = now + random.uniform(*BLINK_GAP)
            elif not self._blink_until and now >= self._next_blink:
                self._blink_until = now + random.uniform(*BLINK_LEN)
            pose = "blink" if self._blink_until else "awake"
            # 0 .. BREATHE_FRAMES-1, easing in and out across one slow breath
            breath = 0.5 - 0.5 * math.cos(
                now * 2 * math.pi / BREATHE_SECONDS)
            level = round(breath * (len(self.peepers_photos.get(pose, [0])) - 1))
            self.draw_peepers(pose, level)
            self._peepers_job = self.root.after(
                PEEPERS_TICK_MS, self.peepers_animate)
        except tk.TclError:
            pass

    def _glow(self, size, color=(255, 218, 130)):
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = size / 2
        for r in range(size // 2, 0, -1):
            a = int(210 * (1 - r / (size / 2)) ** 2)
            d.ellipse((c - r, c - r, c + r, c + r), fill=(*color, a))
        return ImageTk.PhotoImage(im)

    def spawn_fireflies(self):
        if Image is None:
            return
        self.sprites = [self._glow(54), self._glow(36, (255, 236, 170))]
        for _ in range(10):
            self.fireflies.append({
                "x": random.uniform(SCENE_X + 30, SCENE_X + SCENE_W - 30),
                "y": random.uniform(SCENE_Y + 30, SCENE_Y + SCENE_H - 30),
                "vx": random.uniform(-0.35, 0.35),
                "vy": random.uniform(-0.22, 0.22),
                "phase": random.uniform(0, 6.28),
                "sprite": random.choice(self.sprites),
                "id": None,
            })
        for ff in self.fireflies:
            ff["id"] = self.canvas.create_image(ff["x"], ff["y"],
                                                image=ff["sprite"])

    def animate(self):
        try:
            t = time.monotonic()
            for ff in self.fireflies:
                ff["x"] += ff["vx"] + math.sin(t * 0.9 + ff["phase"]) * 0.18
                ff["y"] += ff["vy"] + math.cos(t * 0.7 + ff["phase"]) * 0.12
                if ff["x"] < SCENE_X + 16 or ff["x"] > SCENE_X + SCENE_W - 16:
                    ff["vx"] *= -1
                if ff["y"] < SCENE_Y + 16 or ff["y"] > SCENE_Y + SCENE_H - 16:
                    ff["vy"] *= -1
                self.canvas.coords(ff["id"], ff["x"], ff["y"])
            self._anim_job = self.root.after(70, self.animate)
        except tk.TclError:
            pass

    # ── check-in ──────────────────────────────────────────────────────────
    def set_mood(self, mood):
        if self.modal:
            return
        try:
            n = pdata.add_checkin(mood)
        except Exception:
            log_error()
            return
        for label, btn in self.chip_ids.items():
            if label == mood:
                btn.set_style(fill=GREEN, text_fill=GREENT)
            else:
                btn.set_style(fill=CTL, text_fill=TEXT)
        self.canvas.itemconfigure(
            self.quiet_id,
            text=f"Saved — that's {n} visit{'s' if n != 1 else ''} here now.")
        self._after_job("_toast_job", 5200, lambda: self.canvas.itemconfigure(
            self.quiet_id,
            text="quiet mode is always on — tap to let me nap"))

    # ── breathe ───────────────────────────────────────────────────────────
    def show_breathe(self):
        if self.modal:
            return
        self.clear()
        f = self.fonts
        self._breath_start = time.monotonic()
        self._breath_stopped = False

        pat = pattern_by_key(self.breath_key)

        self.canvas.create_text(WIN_W / 2, 144, text="Breathe with me",
                                font=f.f(f.choice, 27, True), fill=TEXT)
        self.canvas.create_text(WIN_W / 2, 184, text=pattern_words(pat),
                                font=f.f(f.choice, 18), fill=MUTED)
        self.canvas.create_text(
            WIN_W / 2, 212,
            text=f"{pat.blurb}  —  {breath_word(pat.rounds)} rounds, "
                 f"{int(pattern_total(pat))} sec",
            font=f.f(f.choice, 15), fill=SOFT)

        # the patterns, one tap apart. The one you are breathing is the gold one.
        gap = 8
        width = (WIN_W - 64 - gap * (len(PATTERNS) - 1)) / len(PATTERNS)
        x = 32
        for option in PATTERNS:
            chosen = option.key == pat.key
            CanvasButton(self.canvas, x, 242, x + width, 292, 20,
                         option.name, f.f(f.choice, 16, True),
                         lambda k=option.key: self.choose_breath(k),
                         fill=(GOLD if chosen else CTL),
                         hover=("#F2D284" if chosen else HOVER),
                         text_fill=(GOLDT if chosen else MUTED),
                         outline=(GOLD if chosen else CTLBRD))
            x += width + gap

        self.circle = self.canvas.create_oval(0, 0, 0, 0, fill=GREEN,
                                              outline="")
        self.cue = self.canvas.create_text(WIN_W / 2, WIN_H / 2 + 20,
                                           text="in…",
                                           font=f.f(f.choice, 30, True),
                                           fill=GREENT)
        CanvasButton(self.canvas, WIN_W / 2 - 90, WIN_H - 120,
                     WIN_W / 2 + 90, WIN_H - 66, 26, "stop for now",
                     f.f(f.choice, 20, True), self.stop_breathe,
                     fill=CTL, hover=HOVER, text_fill=MUTED)
        self._breathe_tick()

    def choose_breath(self, key):
        """Swap to another pattern, and remember it for next time.

        Leaving one pattern for another is a stop, so the attempt you walk
        away from is logged exactly the way "stop for now" logs it.
        """
        if key == self.breath_key:
            return
        try:
            pdata.add_breath(time.monotonic() - self._breath_start, False,
                             pattern=self.breath_key)
        except Exception:
            log_error()
        self.breath_key = pattern_by_key(key).key
        self.cfg["breath"] = self.breath_key
        save_config(self.cfg)
        self.show_breathe()

    def _breathe_tick(self):
        try:
            pat = pattern_by_key(self.breath_key)
            elapsed = time.monotonic() - self._breath_start
            if elapsed >= pattern_total(pat):
                self.finish_breathe()
                return
            index, label, progress = breath_phase(elapsed, pat)
            radius = breath_radius(index, progress, pat)
            cx, cy = WIN_W / 2, WIN_H / 2 + 20
            self.canvas.coords(self.circle, cx - radius, cy - radius,
                               cx + radius, cy + radius)
            self.canvas.coords(self.cue, cx, cy)
            self.canvas.itemconfigure(self.cue, text=label)
            self._breathe_job = self.root.after(50, self._breathe_tick)
        except tk.TclError:
            pass

    def stop_breathe(self):
        if self._breath_stopped:
            return
        self._breath_stopped = True
        try:
            pdata.add_breath(time.monotonic() - self._breath_start, False,
                             pattern=self.breath_key)
        except Exception:
            log_error()
        self.show_main()

    def finish_breathe(self):
        if self._breath_stopped:
            return
        self._breath_stopped = True
        try:
            pdata.add_breath(pattern_total(pattern_by_key(self.breath_key)), True,
                             pattern=self.breath_key)
        except Exception:
            log_error()
        self.canvas.coords(self.circle, WIN_W / 2 - 80, WIN_H / 2 - 60,
                           WIN_W / 2 + 80, WIN_H / 2 + 100)
        self.canvas.itemconfigure(self.cue, text="there you are.",
                                  font=self.fonts.f(self.fonts.choice, 26, True))
        # A scheduled return, not a fixed one: if you wander off in the next
        # moment, that is where you meant to be, and clear() cancels this.
        self._after_job("_nav_job", 1800, self.show_main)

    # ── timer ─────────────────────────────────────────────────────────────
    def show_timer(self):
        self.clear()
        # A timer you started is never thrown away by leaving this view. Coming
        # back just shows it again, still counting from your real start.
        if self._running:
            self.timer_running(self._running["id"], self._running["activity"],
                               t0=self._running["t0"])
            return
        f = self.fonts
        self.titlebar("A timer", back=self.show_main)

        self.canvas.create_text(32, 120, anchor="nw", text="What are you up to?",
                                font=f.f(f.choice, 27, True), fill=TEXT)
        self.canvas.create_text(32, 164, anchor="nw",
                                text="a shower  ·  a walk  ·  tidying  ·  "
                                "resting  ·  a call  ·  anything",
                                font=f.f(f.choice, 18), fill=MUTED)

        rrect(self.canvas, 32, 204, WIN_W - 32, 268, 18,
              fill=CTL, outline=CTLBRD)
        entry = tk.Entry(self.root, bg=CTL, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=f.f(f.choice, 19),
                         selectbackground=GREEN, selectforeground=GREENT)
        self.canvas.create_window(WIN_W / 2, 236, window=entry,
                                  width=WIN_W - 96, height=36)
        self._widgets.append(entry)
        self.entry = entry

        CanvasButton(self.canvas, 32, 300, WIN_W - 32, 366, 22,
                     "Start the timer", f.f(f.choice, 23, True),
                     self.timer_start, fill=GOLD, hover="#F2D284",
                     text_fill=GOLDT, outline=GOLD)

        self.canvas.create_text(WIN_W / 2, 404,
                                text="no math here — start it, live your life, "
                                "come back and stop it",
                                font=f.f(f.choice, 17), fill=SOFT)

        recent = pdata.recent_sessions(3)
        if recent:
            self.canvas.create_text(32, 470, anchor="nw", text="lately:",
                                    font=f.f(f.choice, 18, True), fill=MUTED)
            y = 502
            for (_sid, s0, s1, activity, helped) in recent:
                line = f"{activity}  ·  {fmt_dur(s1 - s0)}"
                if helped:
                    line += f"  ·  {helped}"
                self.canvas.create_text(44, y, anchor="nw", text=line,
                                        font=f.f(f.choice, 18), fill=SOFT)
                y += 30

        self._focus_later(entry)

    def timer_start(self):
        activity = (self.entry.get() or "").strip()
        if not activity:
            activity = "being here"
        try:
            sid = pdata.start_session(activity)
        except Exception:
            log_error()
            return
        self.timer_running(sid, activity)

    def timer_running(self, sid, activity, t0=None):
        self.clear()
        f = self.fonts
        self.titlebar("A timer", back=self.show_main)
        self._running = {"id": sid, "activity": activity,
                         "t0": time.time() if t0 is None else t0}

        self.canvas.create_text(WIN_W / 2, 190, text=activity,
                                font=f.f(f.choice, 30, True), fill=TEXT)
        self.elapsed_id = self.canvas.create_text(
            WIN_W / 2, 320, text="0:00", font=f.f(f.choice, 64, True), fill=GOLD)
        self.canvas.create_text(WIN_W / 2, 386, text="no rush. I'll wait.",
                                font=f.f(f.choice, 18), fill=SOFT)
        self.canvas.create_text(
            WIN_W / 2, 418,
            text="leave whenever you like — I'll keep counting, and wait for "
                 "you on the way back.",
            font=f.f(f.choice, 16), fill=SOFT)

        CanvasButton(self.canvas, 32, 470, WIN_W - 32, 536, 22, "finish",
                     f.f(f.choice, 23, True), self.timer_finish_prompt,
                     fill=GOLD, hover="#F2D284", text_fill=GOLDT, outline=GOLD)
        CanvasButton(self.canvas, WIN_W / 2 - 130, 566, WIN_W / 2 + 130, 618, 24,
                     "let it go (don't log)", f.f(f.choice, 18), self.timer_drop,
                     fill=CTL, hover=HOVER, text_fill=MUTED)
        self._timer_tick()

    def _timer_tick(self):
        try:
            if not self._running or self.elapsed_id is None:
                return
            self.canvas.itemconfigure(
                self.elapsed_id,
                text=fmt_clock(time.time() - self._running["t0"]))
            self._timer_job = self.root.after(1000, self._timer_tick)
        except tk.TclError:
            pass

    def timer_drop(self):
        if self._running:
            try:
                pdata.drop_session(self._running["id"])
            except Exception:
                log_error()
        self._running = None
        self.show_main()

    def timer_finish_prompt(self):
        if not self._running:
            return
        run = self._running
        secs = time.time() - run["t0"]
        self._running = None
        self.clear()
        f = self.fonts
        self.titlebar("A timer")
        self._pending = {"id": run["id"], "seconds": secs,
                         "activity": run["activity"]}

        self.canvas.create_text(WIN_W / 2, 200,
                                text=f"{run['activity']}  ·  {fmt_dur(secs)}",
                                font=f.f(f.choice, 26, True), fill=TEXT)
        self.canvas.create_text(WIN_W / 2, 250, text="did it help?",
                                font=f.f(f.choice, 24), fill=MUTED)

        answers = [("yes", 32, 250), ("a bit", 272, 490), ("no", 512, 728)]
        for label, x1, x2 in answers:
            CanvasButton(self.canvas, x1, 320, x2, 386, 22, label,
                         f.f(f.choice, 22, True),
                         lambda a=label: self.timer_save(a),
                         fill=CTL, hover=HOVER, text_fill=TEXT)

        CanvasButton(self.canvas, WIN_W / 2 - 130, 430, WIN_W / 2 + 130, 482, 24,
                     "skip — just log it", f.f(f.choice, 18),
                     lambda: self.timer_save(None),
                     fill=CTL, hover=HOVER, text_fill=MUTED)
        self.canvas.create_text(WIN_W / 2, 540,
                                text="no wrong answers here.",
                                font=f.f(f.choice, 17), fill=SOFT)

    def timer_save(self, helped):
        if not self._pending:
            return
        try:
            pdata.finish_session(self._pending["id"], helped)
        except Exception:
            log_error()
        activity = self._pending["activity"]
        secs = self._pending["seconds"]
        self._pending = None
        self.clear()
        f = self.fonts
        self.titlebar("A timer")
        self.canvas.create_text(WIN_W / 2, WIN_H / 2 - 40, text="logged.",
                                font=f.f(f.choice, 34, True), fill=GREEN)
        self.canvas.create_text(WIN_W / 2, WIN_H / 2 + 20,
                                text=f"{activity}  ·  {fmt_dur(secs)}",
                                font=f.f(f.choice, 22), fill=MUTED)
        self._after_job("_toast_job", 2200, self.show_main)

    # ── journal ───────────────────────────────────────────────────────────
    def show_journal(self):
        self.clear()
        f = self.fonts
        self.titlebar("Journal", back=self.show_main)

        self.canvas.create_text(32, 120, anchor="nw",
                                text="A page of your own.",
                                font=f.f(f.choice, 27, True), fill=TEXT)
        self.canvas.create_text(32, 164, anchor="nw",
                                text="one line counts. so does a paragraph.",
                                font=f.f(f.choice, 18), fill=MUTED)

        rrect(self.canvas, 32, 204, WIN_W - 32, 380, 18,
              fill=CTL, outline=CTLBRD)
        text = tk.Text(self.root, bg=CTL, fg=TEXT, insertbackground=TEXT,
                       relief="flat", font=f.f(f.choice, 18), wrap="word",
                       padx=12, pady=10, selectbackground=GREEN,
                       selectforeground=GREENT, height=6)
        self.canvas.create_window(WIN_W / 2, 292, window=text,
                                  width=WIN_W - 96, height=156)
        self._widgets.append(text)
        self.note_box = text

        CanvasButton(self.canvas, 32, 400, WIN_W - 32, 462, 22, "save it",
                     f.f(f.choice, 22, True), self.journal_save,
                     fill=GOLD, hover="#F2D284", text_fill=GOLDT, outline=GOLD)

        self.journal_note_id = self.canvas.create_text(
            WIN_W / 2, 486, text="", font=f.f(f.choice, 17), fill=GREEN)

        self.canvas.create_text(32, 524, anchor="nw", text="lately:",
                                font=f.f(f.choice, 18, True), fill=MUTED)
        self.draw_notes(550)
        self._focus_later(text)

    def draw_notes(self, y):
        f = self.fonts
        for (ts, note) in pdata.recent_notes(5):
            when = time.strftime("%b %d", time.localtime(ts))
            snippet = note.strip().replace("\n", " ")
            if len(snippet) > 88:
                snippet = snippet[:85] + "…"
            self.canvas.create_text(44, y, anchor="nw",
                                    text=f"{when} — {snippet}",
                                    font=f.f(f.choice, 17), fill=SOFT,
                                    tags=("notes",))
            y += 42

    def journal_save(self):
        text = self.note_box.get("1.0", "end").strip()
        if not text:
            self.canvas.itemconfigure(self.journal_note_id,
                                      text="nothing to save yet — that's okay too.")
            self._after_job("_toast_job", 2600, lambda: self.canvas.itemconfigure(
                self.journal_note_id, text=""))
            return
        try:
            pdata.add_note(text)
        except Exception:
            log_error()
            return
        self.note_box.delete("1.0", "end")
        self.canvas.itemconfigure(self.journal_note_id,
                                  text="saved. thanks for writing it down.")
        self._after_job("_toast_job", 2600, lambda: self.canvas.itemconfigure(
            self.journal_note_id, text=""))
        self.canvas.delete("notes")
        self.draw_notes(550)

    # ── week ──────────────────────────────────────────────────────────────
    def show_week(self):
        self.clear()
        f = self.fonts
        self.titlebar("Your week", back=self.show_main)

        self.canvas.create_text(32, 116, anchor="nw",
                                text="Your week, gently.",
                                font=f.f(f.choice, 27, True), fill=TEXT)
        self.canvas.create_text(32, 158, anchor="nw",
                                text="what helped first — the numbers can wait.",
                                font=f.f(f.choice, 18), fill=MUTED)

        st = pdata.week_stats()

        self.canvas.create_text(32, 212, anchor="nw", text="what helped",
                                font=f.f(f.choice, 20, True), fill=GOLD)
        y = 248
        if st["helped"]:
            for activity, secs in st["helped"][:4]:
                self.canvas.create_text(44, y, anchor="nw",
                                        text=f"{activity} — {fmt_dur(secs)}",
                                        font=f.f(f.choice, 19), fill=TEXT)
                y += 32
        else:
            self.canvas.create_text(44, y, anchor="nw",
                                    text="nothing logged as helping yet. the week "
                                    "is still yours.",
                                    font=f.f(f.choice, 18), fill=SOFT)
            y += 32

        y += 18
        self.canvas.create_text(32, y, anchor="nw", text="and quietly",
                                font=f.f(f.choice, 20, True), fill=GOLD)
        y += 36

        lines = [
            f"you checked in {st['checkins']} time{'s' if st['checkins'] != 1 else ''}",
            f"you breathed {st['breaths']} time{'s' if st['breaths'] != 1 else ''}",
            f"you tracked {fmt_dur(st['total_seconds'])} across "
            f"{st['sessions']} session{'s' if st['sessions'] != 1 else ''}",
        ]
        # Which breathing you actually reached for. Only worth saying once it
        # is a habit rather than a one-off - one breath is not a pattern.
        if st.get("patterns") and st["patterns"][0][1] >= 2:
            lines.insert(2, "mostly "
                         + pattern_by_key(st["patterns"][0][0]).name.lower())
        if st["notes"]:
            lines.append(f"you wrote {st['notes']} note{'s' if st['notes'] != 1 else ''}")
        if st["top"]:
            top_name, top_secs = st["top"][0]
            lines.append(f"most time went to: {top_name} ({fmt_dur(top_secs)})")
        for line in lines:
            self.canvas.create_text(44, y, anchor="nw", text=line,
                                    font=f.f(f.choice, 18), fill=MUTED)
            y += 30

        y += 24
        self.canvas.create_text(WIN_W / 2, y, text="showing up is the whole trick.",
                                font=f.f(f.choice, 19, True), fill=GREEN)

        # take it with you
        CanvasButton(self.canvas, 50, 660, 370, 716, 22,
                     "save this week (PDF)", f.f(f.choice, 18, True),
                     self.week_save_pdf, fill=CTL, hover=HOVER, text_fill=TEXT)
        CanvasButton(self.canvas, 390, 660, 710, 716, 22,
                     "backup everything", f.f(f.choice, 18, True),
                     self.week_backup, fill=CTL, hover=HOVER, text_fill=TEXT)
        self.export_note_id = self.canvas.create_text(
            WIN_W / 2, 750, text="", font=f.f(f.choice, 17), fill=GREEN)

    def week_save_pdf(self):
        try:
            import exports as pexports
            out = pexports.week_pdf(pattern_names=PATTERN_NAMES)
        except Exception:
            log_error()
            self.canvas.itemconfigure(
                self.export_note_id,
                text="couldn't write it just now — the log has the details.")
            return
        self.canvas.itemconfigure(self.export_note_id,
                                  text=f"saved:   exports\\{out.name}")

    def week_backup(self):
        try:
            import exports as pexports
            out = pexports.backup_zip()
        except Exception:
            log_error()
            self.canvas.itemconfigure(
                self.export_note_id,
                text="couldn't write it just now — the log has the details.")
            return
        self.canvas.itemconfigure(self.export_note_id,
                                  text=f"saved:   exports\\{out.name}")

    def _quiet_tap(self, _e):
        """The quiet line toggles the nap - and keeps the tap to itself."""
        self._quiet_tap_guard = True
        self.toggle_nap()
        return "break"

    # ── nap (quiet mode, made visible) ────────────────────────────────────
    def toggle_nap(self):
        if self.modal:
            return
        if self.napping:
            self.wake()
        else:
            self.nap()

    def nap(self):
        self.napping = True
        self.clear()
        f = self.fonts
        if self.scene_dim is not None:
            self.canvas.create_image(SCENE_X, SCENE_Y, image=self.scene_dim,
                                     anchor="nw")
        else:
            self.canvas.create_rectangle(SCENE_X, SCENE_Y, SCENE_X + SCENE_W,
                                         SCENE_Y + SCENE_H, fill=PANEL,
                                         outline=CTLBRD)
        if self.alive:
            self.draw_peepers("sleep")
        self.canvas.create_text(WIN_W / 2, 560, text="z    z    z",
                                font=f.f(f.choice, 30, True), fill=MUTED)
        self.canvas.create_text(WIN_W / 2, 646, text="napping.",
                                font=f.f(f.choice, 26, True), fill=TEXT)
        self.canvas.create_text(WIN_W / 2, 692,
                                text="tap anywhere when you need me.",
                                font=f.f(f.choice, 18), fill=SOFT)
        if self._running:
            self.timer_nap_id = self.canvas.create_text(
                WIN_W / 2, 736, text=self._timer_pill_text(),
                font=f.f(f.choice, 17), fill=GOLD)
            self._start_timeline()

    def wake(self):
        self.napping = False
        self.show_main()

    # ── a running timer, visible from wherever you are ────────────────────
    def _timer_pill_text(self):
        if not self._running:
            return ""
        name = self._running["activity"]
        if len(name) > 16:
            name = name[:15].rstrip() + "…"
        return f"{name}  ·  {fmt_clock(time.time() - self._running['t0'])}"

    def place_timer_pill(self):
        """Quietly show, on the main view, that a timer is still going."""
        if not self._running:
            return
        f = self.fonts
        rrect(self.canvas, 392, 514, WIN_W - 32, 564, 22,
              fill=CTL, outline=CTLBRD, tags=("timerpill",))
        self.timer_line_id = self.canvas.create_text(
            (392 + WIN_W - 32) / 2, 539, text=self._timer_pill_text(),
            font=f.f(f.choice, 18, True), fill=GOLD, tags=("timerpill",))
        self.canvas.tag_bind("timerpill", "<Button-1>", self._timer_pill_tap)
        self._start_timeline()

    def _timer_pill_tap(self, _e):
        self.show_timer()
        return "break"

    def _start_timeline(self):
        if self._timeline_job is None and self._running:
            self._timeline_job = self.root.after(1000, self._timeline_tick)

    def _timeline_tick(self):
        """Keep the 'still counting' labels current.

        This deliberately outlives clear(): the whole point is that a timer
        keeps counting while you are somewhere else in the app.
        """
        try:
            self._timeline_job = None
            if not self._running:
                return
            text = self._timer_pill_text()
            for attr in ("timer_line_id", "timer_nap_id"):
                canvas_id = getattr(self, attr)
                if canvas_id is not None:
                    self.canvas.itemconfigure(canvas_id, text=text)
            self._timeline_job = self.root.after(1000, self._timeline_tick)
        except tk.TclError:
            pass

    # ── the worry jar ─────────────────────────────────────────────────────
    def show_worry(self):
        self.clear()
        f = self.fonts
        self.titlebar("The worry jar", back=self.show_main)

        self.canvas.create_text(32, 120, anchor="nw",
                                text="Give me what's heavy.",
                                font=f.f(f.choice, 27, True), fill=TEXT)
        self.canvas.create_text(32, 164, anchor="nw",
                                text="I'll hold it. It waits for you — "
                                "not the other way around.",
                                font=f.f(f.choice, 18), fill=MUTED)

        rrect(self.canvas, 32, 210, WIN_W - 32, 274, 18,
              fill=CTL, outline=CTLBRD)
        entry = tk.Entry(self.root, bg=CTL, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=f.f(f.choice, 19),
                         selectbackground=GREEN, selectforeground=GREENT)
        self.canvas.create_window(WIN_W / 2, 242, window=entry,
                                  width=WIN_W - 96, height=36)
        self._widgets.append(entry)
        self.worry_entry = entry

        CanvasButton(self.canvas, 32, 296, 420, 358, 22, "into the jar",
                     f.f(f.choice, 21, True),
                     lambda: self.worry_park(with_text=True),
                     fill=GOLD, hover="#F2D284", text_fill=GOLDT, outline=GOLD)
        CanvasButton(self.canvas, 436, 296, WIN_W - 32, 358, 22,
                     "it's heavy (no words)", f.f(f.choice, 19),
                     lambda: self.worry_park(with_text=False),
                     fill=CTL, hover=HOVER, text_fill=MUTED)

        n = pdata.worry_count()
        if n == 0:
            jar_text = "the jar is empty. nothing to carry right now."
        elif n == 1:
            jar_text = "the jar holds 1 worry."
        else:
            jar_text = f"the jar holds {n} worries."
        self.canvas.create_text(WIN_W / 2, 424, text=jar_text,
                                font=f.f(f.choice, 21, True), fill=TEXT)
        if n:
            CanvasButton(self.canvas, WIN_W / 2 - 150, 464,
                         WIN_W / 2 + 150, 520, 24, "visit the jar",
                         f.f(f.choice, 20, True), self.show_jar_list,
                         fill=CTL, hover=HOVER, text_fill=TEXT)

        released = pdata.released_count()
        if released:
            self.canvas.create_text(
                WIN_W / 2, 560,
                text=f"and you've set down {released} so far.",
                font=f.f(f.choice, 17), fill=SOFT)

        self.worry_note_id = self.canvas.create_text(
            WIN_W / 2, 630, text="", font=f.f(f.choice, 18), fill=GREEN)
        self._focus_later(entry)

    def worry_park(self, with_text=True):
        value = None
        if with_text:
            value = (self.worry_entry.get() or "").strip()
            if not value:
                self.canvas.itemconfigure(
                    self.worry_note_id,
                    text="write it, or tap \"it's heavy\" — either is okay.")
                self._after_job("_toast_job", 2600,
                                lambda: self.canvas.itemconfigure(
                                    self.worry_note_id, text=""))
                return
        try:
            pdata.add_worry(value)
        except Exception:
            log_error()
            return
        self.worry_entry.delete(0, "end")
        self.canvas.itemconfigure(
            self.worry_note_id,
            text="it's in the jar. you don't have to hold it right now.")
        self._after_job("_toast_job", 2800, self.show_worry)

    def show_jar_list(self):
        self.clear()
        f = self.fonts
        self.titlebar("Inside the jar", back=self.show_worry)
        rows = pdata.open_worries(6)
        if not rows:
            self.canvas.create_text(WIN_W / 2, 300, text="the jar is quiet now.",
                                    font=f.f(f.choice, 24, True), fill=GREEN)
            self.canvas.create_text(WIN_W / 2, 350,
                                    text="nothing is waiting in here.",
                                    font=f.f(f.choice, 18), fill=SOFT)
            return
        self.canvas.create_text(32, 116, anchor="nw",
                                text="no rush. nothing here expires.",
                                font=f.f(f.choice, 18), fill=MUTED)
        y = 164
        for (wid, ts, text) in rows:
            when = time.strftime("%b %d", time.localtime(ts))
            body = text or "(no words — just heavy)"
            self.canvas.create_text(44, y, anchor="nw",
                                    text=f"{when} — {body}",
                                    font=f.f(f.choice, 18), fill=TEXT,
                                    width=540)
            CanvasButton(self.canvas, 604, y - 8, 716, y + 32, 18,
                         "let it go", f.f(f.choice, 16, True),
                         lambda w=wid: self.release(w),
                         fill=CTL, hover="#4A4159", text_fill=GOLD)
            y += 76
        self.canvas.create_text(32, WIN_H - 130, anchor="nw",
                                text="anything you set down stays set down.",
                                font=f.f(f.choice, 17), fill=SOFT)

    def release(self, worry_id):
        try:
            pdata.release_worry(worry_id)
        except Exception:
            log_error()
        self.show_jar_list()

    # ── font picker ───────────────────────────────────────────────────────
    def open_font_picker(self):
        if self.modal:
            return
        self.modal = True
        f = self.fonts
        self.canvas.create_rectangle(0, 0, WIN_W, WIN_H, fill=BG, outline="")
        self.canvas.create_text(WIN_W / 2, 130,
                                text="Hi! Which writing feels like me?",
                                font=f.f(f.choice, 26, True), fill=TEXT)
        self.canvas.create_text(WIN_W / 2, 172,
                                text="tap the one you like — you can change it "
                                "anytime with the Aa button",
                                font=f.f(f.choice, 17), fill=MUTED)

        y = 240
        for name in ("Quicksand", "Nunito"):
            fam_ok = bool(self.fonts.families.get(name))
            label = name if fam_ok else f"{name} (not found — using default)"
            CanvasButton(self.canvas, 90, y, WIN_W - 90, y + 200, 24,
                         "", f.f(name, 24), lambda n=name: self.choose_font(n),
                         fill=PANEL, hover="#3A3147", text_fill=TEXT,
                         outline=CTLBRD)
            self.canvas.create_text(WIN_W / 2, y + 58, text="Hi. I'm Peepers.",
                                    font=f.f(name, 30, True), fill=TEXT)
            self.canvas.create_text(WIN_W / 2, y + 112,
                                    text="How's the glade today?",
                                    font=f.f(name, 22), fill=MUTED)
            self.canvas.create_text(WIN_W / 2, y + 162,
                                    text=f"{label} — tap me",
                                    font=f.f(f.choice, 16, True), fill=GOLD)
            y += 230

        CanvasButton(self.canvas, WIN_W / 2 - 120, WIN_H - 110,
                     WIN_W / 2 + 120, WIN_H - 58, 24, "I'll decide later",
                     f.f(f.choice, 18), self.close_picker,
                     fill=CTL, hover=HOVER, text_fill=MUTED)

    def choose_font(self, name):
        if self.fonts.families.get(name):
            self.fonts.choice = name
        self.cfg["font"] = self.fonts.choice
        self.cfg["first_run_done"] = True
        save_config(self.cfg)
        self.modal = False
        self.show_main()

    def close_picker(self):
        self.cfg["first_run_done"] = True
        save_config(self.cfg)
        self.modal = False
        self.show_main()

    # ── tray ──────────────────────────────────────────────────────────────
    def start_tray(self):
        try:
            import pystray
            img = Image.open(ASSETS / "icon.png")

            def _show(icon, item):
                self.root.after(0, lambda: (self.root.lift(),
                                            self.root.focus_force()))

            def _breathe(icon, item):
                self.root.after(0, self.show_breathe)

            def _quit(icon, item):
                icon.stop()
                self.root.after(0, self.quit)

            def _nap(icon, item):
                self.root.after(0, self.toggle_nap)

            menu = pystray.Menu(
                pystray.MenuItem("Show Peepers", _show, default=True),
                pystray.MenuItem("Begin a breath", _breathe),
                pystray.MenuItem("Let Peepers nap", _nap),
                pystray.MenuItem("Quit", _quit),
            )
            self.tray = pystray.Icon("pondside", img,
                                     f"Pondside {APP_VERSION} — Peepers says hi",
                                     menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception:
            log_error()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def quit(self):
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    if "--selftest" in sys.argv:
        return selftest()
    smoke = "--smoke" in sys.argv
    root = tk.Tk()
    root.title("Pondside")
    app = PondsideApp(root, smoke=smoke)
    try:
        root.mainloop()
        if smoke:
            print("SMOKE OK")
    except Exception:
        log_error()
        raise


if __name__ == "__main__":
    sys.exit(main())

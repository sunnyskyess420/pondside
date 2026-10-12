"""Live probe: a running timer that survives leaving the view, and the breath.

The checked-in suites under tests/ are headless on purpose (no window), so the
two behaviours here - a timer that keeps counting while you are somewhere else
in the app, and the 4-in / 8-out breathing screen - can only be proven against
a real Tk canvas. That is what this script is for.

It opens a window for a couple of seconds, works entirely inside a throwaway
temp folder, and never touches your pondside.db.

    py -3.14 tools/probe_timer.py
"""

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point every writable path at a temp folder BEFORE importing our own modules:
# both data.py and pondside.py do ``from paths import ...``, which binds the
# value at import time.
TMP = Path(tempfile.mkdtemp(prefix="pondside-probe-"))
import paths  # noqa: E402

paths.DB_PATH = TMP / "probe.db"
paths.CONFIG_PATH = TMP / "config.json"
paths.LOG_PATH = TMP / "probe.log"
paths.EXPORTS_DIR = TMP / "exports"
paths.DATA_DIR = TMP

import tkinter as tk  # noqa: E402

import pondside  # noqa: E402

passes = 0
fails = []


def check(name, ok, detail=""):
    global passes
    if ok:
        passes += 1
        print(f"  ok    {name}")
    else:
        fails.append(name)
        print(f"  FAIL  {name}   {detail}")


def texts_on_screen(app):
    c = app.canvas
    return [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]


def main():
    root = tk.Tk()
    root.title("Pondside probe")
    root.withdraw()
    app = pondside.PondsideApp(root)
    root.update()

    # ── the breath pattern ────────────────────────────────────────────────
    print("breath pattern")
    check("the exhale is twice the inhale",
          pondside.BREATH_OUT == 2 * pondside.BREATH_IN,
          f"in={pondside.BREATH_IN} out={pondside.BREATH_OUT}")
    cycle = pondside.BREATH_IN + pondside.BREATH_OUT
    breaths = pondside.BREATH_TOTAL / cycle
    check("the minute divides into whole breaths",
          abs(breaths - round(breaths)) < 1e-9, f"{breaths} breaths")
    check("at least five slow breaths fit", breaths >= 5, f"{breaths}")

    app.show_breathe()
    root.update_idletasks()
    shown = texts_on_screen(app)
    check("the screen states four in / eight out",
          any("four in" in t and "eight out" in t for t in shown), str(shown))
    check("and counts the breaths it will take",
          any("five slow breaths" in t for t in shown), str(shown))

    # Drive the animation itself, so this is not just arithmetic on constants.
    def cue_at(t):
        app._breath_start = time.monotonic() - t
        app._breathe_tick()
        x0, _y0, x1, _y1 = app.canvas.coords(app.circle)
        return app.canvas.itemcget(app.cue, "text"), (x1 - x0) / 2

    labels = {t: cue_at(t)[0] for t in (0.5, 3.9, 4.1, 11.9, 12.1)}
    check("the cue says 'in' for the first four seconds",
          labels[0.5] == "in…" and labels[3.9] == "in…", str(labels))
    check("the cue says 'out' for the next eight",
          labels[4.1] == "out…" and labels[11.9] == "out…", str(labels))
    check("and then the cycle starts over", labels[12.1] == "in…",
          str(labels))
    wide, narrow = cue_at(4.0)[1], cue_at(12.0)[1]
    check("the circle swells on the inhale, settles on the exhale",
          wide > narrow and abs(narrow - 70) < 1 and abs(wide - 150) < 1,
          f"{narrow} -> {wide}")

    app._breath_start = time.monotonic() - pondside.BREATH_TOTAL
    app._breathe_tick()
    with sqlite3.connect(str(TMP / "probe.db")) as c:
        secs = [r[0] for r in c.execute("SELECT seconds FROM breaths")]
    check("a completed breath logs the whole minute",
          secs == [int(pondside.BREATH_TOTAL)], str(secs))

    # ── starting a timer ──────────────────────────────────────────────────
    print("a timer you can walk away from")
    app.show_timer()
    app.entry.delete(0, "end")
    app.entry.insert(0, "probe")
    app.timer_start()
    root.update()
    run = app._running
    check("starting a timer marks it running",
          bool(run) and run["activity"] == "probe", str(run))
    t0 = run["t0"] if run else None
    check("the timer view has a back button to leave by",
          app.elapsed_id is not None)

    # ── leaving and coming back ───────────────────────────────────────────
    for view in (app.show_journal, app.show_week, app.show_worry, app.show_main):
        view()
        root.update()
        check(f"a running timer survives {view.__name__}",
              bool(app._running) and app._running["t0"] == t0,
              str(app._running))

    pill = app.canvas.find_withtag("timerpill")
    check("the main view carries a running-timer pill",
          len(pill) >= 2 and app.timer_line_id is not None, str(pill))
    check("the pill names the activity and the elapsed time",
          "probe" in app.canvas.itemcget(app.timer_line_id, "text"),
          app.canvas.itemcget(app.timer_line_id, "text"))

    pill_before = app.canvas.itemcget(app.timer_line_id, "text")
    time.sleep(1.3)
    root.update()
    pill_text = app.canvas.itemcget(app.timer_line_id, "text")
    check("the pill clock keeps moving", pill_text != pill_before,
          f"{pill_before!r} -> {pill_text!r}")

    app.show_timer()
    root.update()
    check("coming back re-opens the timer, still running",
          app.elapsed_id is not None and app._running["t0"] == t0)
    clock = app.canvas.itemcget(app.elapsed_id, "text")
    check("and it did not restart from zero", clock != "0:00", repr(clock))

    # ── napping is allowed now ────────────────────────────────────────────
    app.nap()
    root.update()
    check("you can let me nap with a timer running",
          app.napping and bool(app._running), f"nap={app.napping}")
    check("the nap view admits the timer is still going",
          app.timer_nap_id is not None)
    app.wake()
    root.update()
    check("waking comes back with the timer intact",
          bool(app._running) and app._running["t0"] == t0)

    # ── letting it go leaves nothing behind ───────────────────────────────
    app.show_timer()
    app.timer_drop()
    root.update()
    check("letting it go clears the running timer", app._running is None)
    check("no phantom pill is left on the main view",
          not app.canvas.find_withtag("timerpill"))
    left = pondside.pdata.recent_sessions(5, path=TMP / "probe.db")
    check("and the dropped session was not logged", not left, str(left))

    try:
        root.destroy()
    except Exception:
        pass

    print()
    print(f"{passes} passed, {len(fails)} failed")
    for f in fails:
        print(f"  - {f}")
    print(f"(used {TMP})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

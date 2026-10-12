"""Live probe: a running timer that survives leaving the view, and the breath.

The checked-in suites under tests/ are headless on purpose (no window), so the
two behaviours here - a timer that keeps counting while you are somewhere else
in the app, and the box-breathing screen - can only be proven against a real
Tk canvas. That is what this script is for.

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

    # ── the shape of the box ──────────────────────────────────────────────
    print("box breathing")
    sides = (pondside.BREATH_IN, pondside.BREATH_HOLD,
             pondside.BREATH_OUT, pondside.BREATH_HOLD)
    check("all four sides of the box are the same length",
          len(set(sides)) == 1, str(sides))
    check("a cycle is exactly those four sides",
          abs(pondside.BREATH_CYCLE - sum(sides)) < 1e-9,
          f"{pondside.BREATH_CYCLE} vs {sum(sides)}")
    rounds = pondside.BREATH_TOTAL / pondside.BREATH_CYCLE
    check("the session is whole rounds, not part of one",
          abs(rounds - round(rounds)) < 1e-9, f"{rounds} rounds")
    check("and it is four of them",
          int(round(rounds)) == pondside.BREATH_ROUNDS, f"{rounds}")

    walked = [pondside.breath_phase(t)[0] for t in
              (0.5, 3.5, 4.5, 7.5, 8.5, 11.5, 12.5, 15.5, 16.5)]
    check("the box is walked in order, then round again",
          walked == [0, 0, 1, 1, 2, 2, 3, 3, 0], str(walked))

    def shape(t):
        index, _label, progress = pondside.breath_phase(t)
        return pondside.breath_radius(index, progress)

    low, high = pondside.BREATH_R_MIN, pondside.BREATH_R_MAX
    check("the circle widens on the way in", low < shape(2.0) < high,
          f"{shape(2.0)}")
    check("it sits at its widest right through the hold",
          shape(4.0) == shape(5.0) == shape(6.0) == high,
          f"{shape(4.0)} {shape(5.0)} {shape(6.0)}")
    check("it narrows on the way out", low < shape(10.0) < high,
          f"{shape(10.0)}")
    check("and rests at its smallest through the last side",
          shape(12.0) == shape(13.0) == shape(14.0) == low,
          f"{shape(12.0)} {shape(13.0)} {shape(14.0)}")

    # ── the same thing, driven through the real canvas ────────────────────
    app.show_breathe()
    root.update_idletasks()
    shown = texts_on_screen(app)
    check("the screen names the exercise and all four sides",
          any("box breathing" in t and "four hold" in t for t in shown),
          str(shown))

    def cue_at(t):
        app._breath_start = time.monotonic() - t
        app._breathe_tick()
        x0, _y0, x1, _y1 = app.canvas.coords(app.circle)
        return app.canvas.itemcget(app.cue, "text"), (x1 - x0) / 2

    cues = {t: cue_at(t)[0] for t in (0.5, 5.0, 9.0, 13.0, 16.5)}
    check("the cue walks in, hold, out, hold",
          [cues[t] for t in (0.5, 5.0, 9.0, 13.0)]
          == ["in…", "hold…", "out…", "hold…"], str(cues))
    check("and the next round begins again", cues[16.5] == "in…", str(cues))
    held_wide, held_empty = cue_at(5.0)[1], cue_at(13.0)[1]
    check("the circle is held at its widest, then at its smallest",
          abs(held_wide - high) < 1 and abs(held_empty - low) < 1,
          f"{held_empty} -> {held_wide}")

    # Drop the animation jobs we have been driving by hand, so no stray tick
    # fires later and logs a breath behind the checks below.
    app._cancel_jobs()

    app.show_main()
    root.update()
    on_main = " ".join(texts_on_screen(app))
    check("the main button states the real length of a breath",
          f"{int(pondside.BREATH_TOTAL)} sec" in on_main, on_main[:160])

    app.show_breathe()
    app._breath_start = time.monotonic() - pondside.BREATH_TOTAL
    app._breathe_tick()
    with sqlite3.connect(str(TMP / "probe.db")) as c:
        secs = [r[0] for r in c.execute("SELECT seconds FROM breaths")]
    check("a completed breath logs the whole session",
          secs == [int(pondside.BREATH_TOTAL)], str(secs))

    # A finished breath lingers on "there you are." and then returns to the
    # main view. That return must not drag you off a view you move to in the
    # meantime - it used to, because it was scheduled outside clear().
    app.show_breathe()
    app._breath_start = time.monotonic() - pondside.BREATH_TOTAL
    app._breathe_tick()               # finishes, schedules the way back
    app.show_week()
    time.sleep(2.0)                   # longer than the linger
    root.update()
    check("a finished breath doesn't drag you off the view you left for",
          not app.canvas.find_withtag("quietline"),
          f"stole the view: {app.canvas.find_withtag('quietline')}")
    app._cancel_jobs()

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

"""Live probe: a running timer that survives leaving the view, and the breath.

The checked-in suites under tests/ are headless on purpose (no window), so the
two behaviours here - a timer that keeps counting while you are somewhere else
in the app, and the breathing screen - can only be proven against a real Tk
canvas. That is what this script is for.

It opens a window for a couple of seconds, works entirely inside a throwaway
temp folder, and never touches your pondside.db.

    py -3.14 tools/probe_timer.py
"""

import json
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

    # ── every pattern has to add up ───────────────────────────────────────
    print("breathing patterns")
    low, high = pondside.BREATH_R_MIN, pondside.BREATH_R_MAX
    keys = [p.key for p in pondside.PATTERNS]
    check("there are a few of them, all named and explained",
          len(pondside.PATTERNS) >= 3
          and all(p.key and p.name and p.blurb for p in pondside.PATTERNS),
          str(keys))
    check("no two share a key", len(set(keys)) == len(keys), str(keys))
    check("a missing or unknown setting lands on the default",
          pondside.pattern_by_key(None).key == pondside.DEFAULT_PATTERN
          and pondside.pattern_by_key("nonsense").key
          == pondside.DEFAULT_PATTERN, pondside.DEFAULT_PATTERN)

    stress = pondside.pattern_by_key("exhale")
    ins = [s for _l, s, m in stress.sides if m == "grow"]
    outs = [s for _l, s, m in stress.sides if m == "shrink"]
    check("the stress pattern breathes out for longer than it breathes in",
          max(ins) < min(outs), f"in={ins} out={outs}")

    def shape_at(t, pat):
        index, label, progress = pondside.breath_phase(t, pat)
        return label, pondside.breath_radius(index, progress, pat)

    for pat in pondside.PATTERNS:
        total = pondside.pattern_total(pat)
        cycle = pondside.pattern_cycle(pat)
        problems = []
        at, starts = 0.0, []
        for _l, secs, _m in pat.sides:
            starts.append(at)
            at += secs
            if secs <= 0:
                problems.append(f"a side lasts {secs}s")
        if abs(cycle - at) > 1e-9:
            problems.append(f"cycle {cycle} but sides add to {at}")
        if abs(total - cycle * pat.rounds) > 1e-9:
            problems.append(f"total {total} is not {pat.rounds} x {cycle}")
        for (label, secs, move), start in zip(pat.sides, starts):
            for frac in (0.0, 0.5, 0.999):
                got, radius = shape_at(start + secs * frac, pat)
                if got != label:
                    problems.append(f"'{label}' at {frac} read as '{got}'")
                if move == "hold" and abs(radius - high) > 1:
                    problems.append(f"held full at {frac} was {radius:.1f}")
                if move == "rest" and abs(radius - low) > 1:
                    problems.append(f"at rest at {frac} was {radius:.1f}")
            end = shape_at(start + secs * 0.999, pat)[1]
            if move == "grow" and abs(end - high) > 1:
                problems.append(f"'{label}' only reached {end:.1f}")
            if move == "shrink" and abs(end - low) > 1:
                problems.append(f"'{label}' only came down to {end:.1f}")
        check(f"{pat.name}: the circle moves the way each side says",
              not problems, "; ".join(problems))

        walked, at = [], 0.0
        for _round in range(pat.rounds):
            for label, secs, _move in pat.sides:
                walked.append(shape_at(at + secs / 2, pat)[0])
                at += secs
        expected = [label for _r in range(pat.rounds)
                    for label, _s, _m in pat.sides]
        check(f"{pat.name}: {pat.rounds} whole rounds, sides in order",
              walked == expected, str(walked))
        check(f"{pat.name}: it ends on its last side, not part way through",
              shape_at(total - 1e-6, pat)[0] == pat.sides[-1][0],
              f"{shape_at(total - 1e-6, pat)[0]!r}")
        check(f"{pat.name}: a session, not a whole afternoon",
              20 <= total <= 90, f"{total} sec")

    # ── the same patterns, driven through the real canvas ─────────────────
    app.show_breathe()
    root.update_idletasks()

    def cue_at(t):
        app._breath_start = time.monotonic() - t
        app._breathe_tick()
        x0, _y0, x1, _y1 = app.canvas.coords(app.circle)
        return app.canvas.itemcget(app.cue, "text"), (x1 - x0) / 2

    for pat in pondside.PATTERNS:
        app.choose_breath(pat.key)
        root.update()

        shown = " ".join(texts_on_screen(app))
        missing = [f"{pondside.breath_word(s)} {l.rstrip('…')}"
                   for l, s, _m in pat.sides
                   if f"{pondside.breath_word(s)} {l.rstrip('…')}" not in shown]
        check(f"{pat.name}: the screen spells out this pattern's sides",
              not missing and pat.blurb in shown, f"{missing} | {shown[:170]}")

        gold = [i for i in app.canvas.find_all()
                if app.canvas.type(i) == "polygon"
                and app.canvas.itemcget(i, "fill") == pondside.GOLD]
        check(f"{pat.name}: exactly one chip is the chosen one",
              len(gold) == 1, f"{len(gold)} highlighted")

        second = pat.sides[1]
        got = cue_at(pat.sides[0][1] + second[1] / 2)[0]
        check(f"{pat.name}: the screen cues its own second side",
              got == second[0], f"{got} != {second[0]}")
        last = cue_at(pondside.pattern_total(pat) - 0.5)[0]
        check(f"{pat.name}: still on its last side at the very end",
              last == pat.sides[-1][0], f"{last} != {pat.sides[-1][0]}")

        with sqlite3.connect(str(TMP / "probe.db")) as c:
            before = [r[0] for r in c.execute("SELECT seconds FROM breaths")]
        app._breath_start = time.monotonic() - pondside.pattern_total(pat)
        app._breathe_tick()
        with sqlite3.connect(str(TMP / "probe.db")) as c:
            after = [r[0] for r in c.execute("SELECT seconds FROM breaths")]
        check(f"{pat.name}: a finished session logs this pattern's length",
              after == before + [int(pondside.pattern_total(pat))],
              f"{before} -> {after}")

    # Drop the animation jobs we have been driving by hand, so no stray tick
    # fires later and logs a breath behind the checks below.
    app._cancel_jobs()

    app.show_main()
    root.update()
    on_main = " ".join(texts_on_screen(app))
    chosen = pondside.pattern_by_key(app.breath_key)
    check("the main button names the pattern you last chose, and its length",
          chosen.name in on_main
          and f"{int(pondside.pattern_total(chosen))} sec" in on_main,
          on_main[:170])

    cfg = json.loads((TMP / "config.json").read_text(encoding="utf-8"))
    check("and that choice is written down for next time",
          cfg.get("breath") == chosen.key, str(cfg))

    # A finished breath lingers on "there you are." and then returns to the
    # main view. That return must not drag you off a view you move to in the
    # meantime - it used to, because it was scheduled outside clear().
    app.show_breathe()
    app._breath_start = time.monotonic() - pondside.pattern_total(
        pondside.pattern_by_key(app.breath_key))
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

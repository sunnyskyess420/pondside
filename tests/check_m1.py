#!/usr/bin/env python
"""Pondside M1 - headless checks for timers, journal and the week view.

Run from the project root:
    py -3.14 tests\\check_m1.py

Proves (no window, no network):
  1. pondside.py and data.py compile.
  2. Sessions round-trip: start -> finish -> helped; drop; stale cleanup.
  3. Notes round-trip.
  4. week_stats() counts and windows (7 days) are correct, including
     "what helped" aggregation and duration totals.
  5. format helpers behave (durations and clocks).

Exits non-zero if anything fails.
"""

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
    print("Pondside M1 checks")
    print("=" * 40)

    for fname in ("pondside.py", "data.py"):
        try:
            py_compile.compile(str(ROOT / fname), doraise=True)
            check(f"{fname} compiles", True)
        except Exception as e:
            check(f"{fname} compiles", False, str(e))

    import data as pdata

    # fresh temp db
    tmp = Path(tempfile.mkdtemp()) / "m1.db"
    pdata.init_db(tmp)

    # 2. sessions round-trip
    sid = pdata.start_session("a walk", path=tmp)
    time.sleep(0.05)
    pdata.finish_session(sid, "yes", path=tmp)
    rows = pdata.recent_sessions(5, path=tmp)
    check("session saved and listed", len(rows) == 1 and rows[0][3] == "a walk",
          str(rows))
    check("session has a duration", rows[0][2] > rows[0][1], str(rows))

    sid2 = pdata.start_session("tidying", path=tmp)
    pdata.drop_session(sid2, path=tmp)
    check("dropped session disappears", len(pdata.recent_sessions(5, path=tmp)) == 1)

    sid3 = pdata.start_session("stale one", path=tmp)  # never finished
    pdata.close_stale_sessions(path=tmp)
    check("stale sessions are cleaned at startup",
          all(r[3] != "stale one" for r in pdata.recent_sessions(5, path=tmp)))

    # 3. notes round-trip
    pdata.add_note("first note", path=tmp)
    pdata.add_note("second note", path=tmp)
    notes = pdata.recent_notes(5, path=tmp)
    check("notes save and list newest first",
          len(notes) == 2 and notes[0][1] == "second note", str(notes))

    # 4. week stats - seed with hand-written timestamps
    tmp2 = Path(tempfile.mkdtemp()) / "week.db"
    pdata.init_db(tmp2)
    now = time.time()
    with sqlite3.connect(str(tmp2)) as c:
        c.execute("INSERT INTO sessions(ts_start, ts_end, activity, helped) "
                  "VALUES(?,?,?,?)", (now - 300, now - 120, "walk", "yes"))   # 180s, recent
        c.execute("INSERT INTO sessions(ts_start, ts_end, activity, helped) "
                  "VALUES(?,?,?,?)", (now - 400, now - 180, "tea", "yes"))    # 220s, recent
        c.execute("INSERT INTO sessions(ts_start, ts_end, activity, helped) "
                  "VALUES(?,?,?,?)", (now - 500, now - 300, "scrolling", "no"))  # 200s, recent
        c.execute("INSERT INTO sessions(ts_start, ts_end, activity, helped) "
                  "VALUES(?,?,?,?)", (now - 900000, now - 899700, "old walk", "yes"))  # >10 days: out
        c.execute("INSERT INTO sessions(ts_start, activity) VALUES(?,?)",
                  (now - 100, "still open"))  # unfinished: out of totals
        c.execute("INSERT INTO checkins(ts, mood) VALUES(?,?)", (now - 60, "Good"))
        c.execute("INSERT INTO checkins(ts, mood) VALUES(?,?)", (now - 900000, "Rough"))
        c.execute("INSERT INTO breaths(ts, seconds, completed) VALUES(?,?,?)",
                  (now - 90, 60, 1))
        c.execute("INSERT INTO notes(ts, text) VALUES(?,?)", (now - 80, "a note"))

    st = pdata.week_stats(days=7, path=tmp2)
    check("week: check-in window", st["checkins"] == 1, str(st["checkins"]))
    check("week: breaths window", st["breaths"] == 1, str(st["breaths"]))
    check("week: notes window", st["notes"] == 1, str(st["notes"]))
    check("week: finished sessions only", st["sessions"] == 3, str(st["sessions"]))
    check("week: duration total", st["total_seconds"] == 600,
          str(st["total_seconds"]))
    check("week: what helped (yes only, sorted)",
          st["helped"] == [("tea", 220.0), ("walk", 180.0)], str(st["helped"]))
    check("week: top by time includes non-helpers",
          st["top"][0] == ("tea", 220.0), str(st["top"]))

    # 5. formatting helpers (import the app module textually - it is a GUI
    # module, so we only borrow the pure functions by exec of their source)
    src = (ROOT / "pondside.py").read_text(encoding="utf-8")
    ns = {}
    for name in ("fmt_dur", "fmt_clock"):
        start = src.index(f"def {name}")
        end = src.index("\ndef ", start + 1)
        exec(src[start:end], ns)
    check("fmt_dur 45 -> '45 sec'", ns["fmt_dur"](45) == "45 sec")
    check("fmt_dur 720 -> '12 min'", ns["fmt_dur"](720) == "12 min")
    check("fmt_dur 3900 -> '1 h 5 min'", ns["fmt_dur"](3900) == "1 h 5 min")
    check("fmt_clock 65 -> '1:05'", ns["fmt_clock"](65) == "1:05")
    check("fmt_clock 3725 -> '1:02:05'", ns["fmt_clock"](3725) == "1:02:05")

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

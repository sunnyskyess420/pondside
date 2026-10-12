#!/usr/bin/env python
"""Pondside M3 - headless checks for exports (weekly PDF + backup zip).

Run from the project root:
    py -3.14 tests\\check_m3.py

Proves (no window, no network):
  1. pondside.py, data.py and exports.py compile.
  2. week_pdf() writes a real PDF (%PDF header) from seeded data.
  3. backup_zip() contains everything.json + one CSV per table, and the
     contents match the seeded rows.
  4. Empty databases still export (empty states must not crash).

Exits non-zero if anything fails.
"""

import csv
import io
import json
import sqlite3
import sys
import tempfile
import time
import zipfile
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


def seed(db):
    now = time.time()
    with sqlite3.connect(str(db)) as c:
        c.execute("INSERT INTO checkins(ts, mood) VALUES(?,?)", (now - 100, "Okayish"))
        c.execute("INSERT INTO checkins(ts, mood) VALUES(?,?)", (now - 2000, "Good"))
        c.execute("INSERT INTO breaths(ts, seconds, completed) VALUES(?,?,?)",
                  (now - 300, 60, 1))
        c.execute("INSERT INTO sessions(ts_start, ts_end, activity, helped) "
                  "VALUES(?,?,?,?)", (now - 900, now - 300, "a walk", "yes"))
        c.execute("INSERT INTO sessions(ts_start, ts_end, activity, helped) "
                  "VALUES(?,?,?,?)", (now - 500, now - 250, "tea", "no"))
        c.execute("INSERT INTO notes(ts, text) VALUES(?,?)", (now - 400, "slept okay"))
        c.execute("INSERT INTO worries(ts_created, text) VALUES(?,?)",
                  (now - 350, "the phone call"))


def main():
    print("Pondside M3 checks")
    print("=" * 40)

    for fname in ("pondside.py", "data.py", "exports.py"):
        try:
            py_compile.compile(str(ROOT / fname), doraise=True)
            check(f"{fname} compiles", True)
        except Exception as e:
            check(f"{fname} compiles", False, str(e))

    import data as pdata
    import exports as pexports

    work = Path(tempfile.mkdtemp())
    db = work / "m3.db"
    out = work / "exports"
    pdata.init_db(db)
    seed(db)

    # weekly PDF
    try:
        pdf = pexports.week_pdf(path=db, out_dir=out)
        head = pdf.read_bytes()[:5]
        check("weekly PDF is written", pdf.exists() and pdf.stat().st_size > 1200,
              f"{pdf} size={pdf.stat().st_size if pdf.exists() else 0}")
        check("weekly PDF looks like a PDF", head == b"%PDF-", str(head))
    except Exception as e:
        check("weekly PDF is written", False, str(e))

    # backup zip
    try:
        zpath = pexports.backup_zip(path=db, out_dir=out)
        with zipfile.ZipFile(zpath) as z:
            names = set(z.namelist())
            check("backup has every.json + all CSVs",
                  {"everything.json", "checkins.csv", "breaths.csv",
                   "sessions.csv", "notes.csv", "worries.csv"} <= names,
                  str(sorted(names)))
            dump = json.loads(z.read("everything.json").decode("utf-8"))
            check("json holds all tables",
                  all(k in dump for k in ("checkins", "breaths", "sessions",
                                          "notes", "worries")))
            sessions = list(csv.DictReader(
                io.StringIO(z.read("sessions.csv").decode("utf-8"))))
            check("sessions.csv row count matches", len(sessions) == 2,
                  str(len(sessions)))
            check("sessions.csv keeps helped",
                  [s["helped"] for s in sessions] == ["yes", "no"],
                  str([s["helped"] for s in sessions]))
            notes = z.read("README.txt").decode("utf-8")
            check("backup carries its little README", "Peepers" in notes)
    except Exception as e:
        check("backup zip is written", False, str(e))

    # empty database still exports
    empty = work / "empty.db"
    pdata.init_db(empty)
    try:
        pdf2 = pexports.week_pdf(path=empty, out_dir=out)
        check("empty week still makes a PDF",
              pdf2.exists() and pdf2.read_bytes()[:5] == b"%PDF-")
        z2 = pexports.backup_zip(path=empty, out_dir=out)
        with zipfile.ZipFile(z2) as z:
            row = z.read("checkins.csv").decode("utf-8")
            check("empty backup notes its emptiness", "nothing here yet" in row)
    except Exception as e:
        check("empty exports", False, str(e))

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

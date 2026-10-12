#!/usr/bin/env python
"""Pondside M2 - headless checks for the worry jar.

Run from the project root:
    py -3.14 tests\\check_m2.py

Proves (no window, no network):
  1. pondside.py and data.py compile.
  2. Worries round-trip: park (with words), park (no words), count, list.
  3. Releasing works: released worries leave the open list, still counted.
  4. Ordering: newest first.

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
    print("Pondside M2 checks")
    print("=" * 40)

    for fname in ("pondside.py", "data.py"):
        try:
            py_compile.compile(str(ROOT / fname), doraise=True)
            check(f"{fname} compiles", True)
        except Exception as e:
            check(f"{fname} compiles", False, str(e))

    import data as pdata

    tmp = Path(tempfile.mkdtemp()) / "m2.db"
    pdata.init_db(tmp)

    check("empty jar starts at zero", pdata.worry_count(path=tmp) == 0)

    w1 = pdata.add_worry("the phone call on Friday", path=tmp)
    w2 = pdata.add_worry(None, path=tmp)  # no words, just heavy
    w3 = pdata.add_worry("   ", path=tmp)  # whitespace only -> no words
    check("parked three worries", pdata.worry_count(path=tmp) == 3,
          str(pdata.worry_count(path=tmp)))

    rows = pdata.open_worries(10, path=tmp)
    check("list is newest-first", [r[0] for r in rows] == [w3, w2, w1],
          str([r[0] for r in rows]))
    check("no-words worries stay textless", rows[0][2] is None and rows[1][2] is None)
    check("words are kept as written", rows[2][2] == "the phone call on Friday")

    pdata.release_worry(w2, path=tmp)
    check("released leaves the open list",
          [r[0] for r in pdata.open_worries(10, path=tmp)] == [w3, w1])
    check("released is still remembered", pdata.released_count(path=tmp) == 1)
    check("open count drops", pdata.worry_count(path=tmp) == 2)

    print()
    print(f"{passes} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

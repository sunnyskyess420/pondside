"""Pondside data layer.

M1 grows the M0 schema with sessions (timers) and notes (journal). Still
stdlib sqlite3, one database file next to the app. Everything stays local.

Tone rule for anything derived from this data: report gently. Numbers inform,
they never scold.
"""

import sqlite3
import time
from pathlib import Path

from paths import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkins(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    mood TEXT NOT NULL,
    energy TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS breaths(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    seconds INTEGER NOT NULL,
    completed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_start REAL NOT NULL,
    ts_end REAL,
    activity TEXT NOT NULL,
    helped TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS notes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS worries(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_created REAL NOT NULL,
    text TEXT,
    visited_at REAL,
    released_at REAL
);
"""


def _db(path=None):
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(path=None):
    with _db(path) as c:
        c.executescript(_SCHEMA)


# ── check-ins ─────────────────────────────────────────────────────────────
def add_checkin(mood, energy=None, note=None, path=None):
    """Save one check-in. Returns the total number of check-ins."""
    with _db(path) as c:
        c.execute(
            "INSERT INTO checkins(ts, mood, energy, note) VALUES(?,?,?,?)",
            (time.time(), mood, energy, note),
        )
        return c.execute("SELECT COUNT(*) FROM checkins").fetchone()[0]


# ── breaths ───────────────────────────────────────────────────────────────
def add_breath(seconds, completed, path=None):
    with _db(path) as c:
        c.execute(
            "INSERT INTO breaths(ts, seconds, completed) VALUES(?,?,?)",
            (time.time(), int(seconds), 1 if completed else 0),
        )


# ── sessions (timers) ─────────────────────────────────────────────────────
def start_session(activity, path=None):
    with _db(path) as c:
        cur = c.execute(
            "INSERT INTO sessions(ts_start, activity) VALUES(?,?)",
            (time.time(), activity),
        )
        return cur.lastrowid


def finish_session(session_id, helped=None, path=None):
    with _db(path) as c:
        c.execute(
            "UPDATE sessions SET ts_end=?, helped=? WHERE id=?",
            (time.time(), helped, session_id),
        )


def drop_session(session_id, path=None):
    with _db(path) as c:
        c.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def close_stale_sessions(path=None):
    """Sessions left open by a crash/quit simply go away - no guilt."""
    with _db(path) as c:
        c.execute("DELETE FROM sessions WHERE ts_end IS NULL")


def recent_sessions(limit=10, path=None):
    with _db(path) as c:
        rows = c.execute(
            "SELECT id, ts_start, ts_end, activity, helped FROM sessions "
            "WHERE ts_end IS NOT NULL ORDER BY ts_start DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return rows


# ── notes (journal) ───────────────────────────────────────────────────────
def add_note(text, path=None):
    with _db(path) as c:
        c.execute("INSERT INTO notes(ts, text) VALUES(?,?)", (time.time(), text))


def recent_notes(limit=6, path=None):
    with _db(path) as c:
        rows = c.execute(
            "SELECT ts, text FROM notes ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows


# ── worries (the jar) ─────────────────────────────────────────────────────
def add_worry(text=None, path=None):
    """Park a worry. Text may be empty - sometimes it's just heavy."""
    value = (text or "").strip() or None
    with _db(path) as c:
        cur = c.execute(
            "INSERT INTO worries(ts_created, text) VALUES(?,?)",
            (time.time(), value),
        )
        return cur.lastrowid


def open_worries(limit=20, path=None):
    with _db(path) as c:
        return c.execute(
            "SELECT id, ts_created, text FROM worries "
            "WHERE released_at IS NULL ORDER BY ts_created DESC LIMIT ?",
            (limit,),
        ).fetchall()


def worry_count(path=None):
    with _db(path) as c:
        return c.execute(
            "SELECT COUNT(*) FROM worries WHERE released_at IS NULL"
        ).fetchone()[0]


def release_worry(worry_id, path=None):
    with _db(path) as c:
        c.execute("UPDATE worries SET released_at=? WHERE id=?",
                  (time.time(), worry_id))


def released_count(path=None):
    with _db(path) as c:
        return c.execute(
            "SELECT COUNT(*) FROM worries WHERE released_at IS NOT NULL"
        ).fetchone()[0]


# ── week (gentle review) ──────────────────────────────────────────────────
def week_stats(days=7, path=None):
    since = time.time() - days * 86400
    with _db(path) as c:
        checkins = c.execute(
            "SELECT COUNT(*) FROM checkins WHERE ts>=?", (since,)).fetchone()[0]
        breaths = c.execute(
            "SELECT COUNT(*) FROM breaths WHERE ts>=?", (since,)).fetchone()[0]
        notes = c.execute(
            "SELECT COUNT(*) FROM notes WHERE ts>=?", (since,)).fetchone()[0]
        sess = c.execute(
            "SELECT activity, ts_start, ts_end, helped FROM sessions "
            "WHERE ts_start>=? AND ts_end IS NOT NULL", (since,)).fetchall()

    total = 0.0
    helped = {}
    top = {}
    for activity, s0, s1, h in sess:
        dur = max(0.0, (s1 or s0) - s0)
        total += dur
        top[activity] = top.get(activity, 0.0) + dur
        if h in ("yes", "a bit"):
            helped[activity] = helped.get(activity, 0.0) + dur

    return {
        "checkins": checkins,
        "breaths": breaths,
        "notes": notes,
        "sessions": len(sess),
        "total_seconds": int(total),
        "helped": sorted(helped.items(), key=lambda kv: -kv[1]),
        "top": sorted(top.items(), key=lambda kv: -kv[1]),
    }


# ── week detail (for exports) ─────────────────────────────────────────────
def week_detail(days=7, path=None):
    since = time.time() - days * 86400
    with _db(path) as c:
        checkins = c.execute(
            "SELECT ts, mood FROM checkins WHERE ts>=? ORDER BY ts",
            (since,)).fetchall()
        sessions = c.execute(
            "SELECT ts_start, ts_end, activity, helped FROM sessions "
            "WHERE ts_start>=? AND ts_end IS NOT NULL ORDER BY ts_start",
            (since,)).fetchall()
        breaths = c.execute(
            "SELECT COUNT(*) FROM breaths WHERE ts>=?", (since,)).fetchone()[0]
        notes = c.execute(
            "SELECT ts, text FROM notes WHERE ts>=? ORDER BY ts",
            (since,)).fetchall()
        parked = c.execute(
            "SELECT COUNT(*) FROM worries WHERE ts_created>=?",
            (since,)).fetchone()[0]
        released = c.execute(
            "SELECT COUNT(*) FROM worries WHERE released_at>=?",
            (since,)).fetchone()[0]
    return {
        "since": since,
        "checkins": checkins,
        "sessions": sessions,
        "breaths": breaths,
        "notes": notes,
        "worries_parked": parked,
        "worries_released": released,
    }


# ── full dump (for backups) ───────────────────────────────────────────────
def dump_all(path=None):
    with _db(path) as c:
        def rows(sql):
            cur = c.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        return {
            "exported_at": time.time(),
            "checkins": rows("SELECT id, ts, mood, energy, note FROM checkins ORDER BY id"),
            "breaths": rows("SELECT id, ts, seconds, completed FROM breaths ORDER BY id"),
            "sessions": rows("SELECT id, ts_start, ts_end, activity, helped, note FROM sessions ORDER BY id"),
            "notes": rows("SELECT id, ts, text FROM notes ORDER BY id"),
            "worries": rows("SELECT id, ts_created, text, visited_at, released_at FROM worries ORDER BY id"),
        }


# ── totals ────────────────────────────────────────────────────────────────
def stats(path=None):
    with _db(path) as c:
        checkins = c.execute("SELECT COUNT(*) FROM checkins").fetchone()[0]
        breaths = c.execute("SELECT COUNT(*) FROM breaths").fetchone()[0]
    return {"checkins": checkins, "breaths": breaths}

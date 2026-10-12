# Pondside 🐸

A cozy desktop companion for hard days: Peepers himself, one-tap check-ins, a
working breath, timers that do the math, a jar that holds what's heavy, a
gentle week's look back, and exports you own.

> **Rulebook (v1):** no water is ever shown. Nothing here may make a hard day
> harder. No streaks, no guilt, no numbers that scold. Everything stays on
> this machine.

## Run it

```
py -3.14 pondside.py            # or double-click run_pondside.bat (no console)
py -3.14 pondside.py --smoke    # self-test: opens and closes after ~3s
py -3.14 tests\check_m0.py      # headless checks (no window)
py -3.14 tools\probe_timer.py   # live probe: needs a window, uses a temp db
```

Requires: Python 3.11+, `pillow`, `pystray`, `reportlab`
(`py -3.14 -m pip install -r requirements.txt`).
Both are already on this machine from FrogPaper.

## What's in it (M0 – M3.5)

- **Peepers window** — the glade, drifting fireflies, "Hi. I'm Peepers."
- **Check-ins** — Rough / Okayish / Good. One tap. Saved locally.
- **Breathe with me** — four patterns, one tap apart on the screen, and
  Peepers remembers the one you chose:
  **Box** (in, hold, out, hold), **Long exhale** (in four, out six — the one
  for stress), **Winding down** (in four, hold seven, out eight) and
  **Even** (in five, out five). The circle travels whatever shape you pick,
  and a session always finishes the round you are in rather than stopping
  mid-breath. Ends with *"there you are."*
- **Timers (M1)** — start something, live your life, stop it: the duration
  is computed for you, then a gentle *"did it help?"*. No math, ever. A
  running timer is never trapped in its own screen: leave whenever you like,
  the app keeps counting, and a small pill on the main view shows the
  activity and the time so you can tap straight back to it.
- **Journal (M1)** — short notes, saved locally. One line counts.
- **Week (M1)** — a gentle look back: *what helped* first, soft numbers after.
- **The worry jar (M2)** — give Peepers what's heavy (or just tap *"it's
  heavy"* when words won't come). The jar holds a count, not a pile.
  Visit it whenever you choose — *nothing here expires* — and set things
  down with *"let it go"* when you're ready.
- **Nap / quiet mode (M2)** — tap *"quiet mode is always on — tap to let me
  nap"* (or use the tray) and Peepers closes his eyes; the glade dims,
  the world stays quiet. Tap anywhere to wake him.
- **Peepers alive (M3.5)** — he breathes slowly and blinks every few seconds,
  and sleeps with his eyes shut while napping. The art swaps only happen if
  the whole set is installed; if any piece is missing he falls back to the
  painted scene and nothing else changes.
- **Exports (M3)** — in the Week view: *save this week (PDF)* for therapy or
  your own shelf, and *backup everything* (JSON + CSVs in one zip). Files
  land in `exports/` next to the app. Your data, in your hands.
- **First-run font pick** — Quicksand or Nunito; change anytime with **Aa**.
- **Tray icon** — Show Peepers / Begin a breath / Let Peepers nap / Quit.
- **Quiet mode is always on** — no notifications, ever.

## Files

| File | What it is |
|---|---|
| `pondside.py` | the app (window, views, fireflies, tray) |
| `data.py` | tiny SQLite layer (`checkins`, `breaths`) |
| `assets/scene.png` | Peepers' glade, with him painted in (the fallback) |
| `assets/scene_base.png` | the same glade with him lifted out (M3.5) |
| `assets/peepers/` | his three poses: awake, blink, sleep |
| `tools/build_peepers.py` | derives blink + sleep from the awake pose |
| `tools/shot.ps1` | grabs the borderless window for looking at |
| `tools/probe_timer.py` | live probe (opens a window) for the timer + the breath |
| `assets/icon.png` | tray icon (a small Peepers) |
| `assets/fonts/` | Quicksand + Nunito (SIL OFL, bundled) |
| `tests/check_m0.py` | headless checks (M0: assets, db, config) |
| `tests/check_m1.py` | headless checks (M1: sessions, notes, week, formats) |
| `tests/check_m2.py` | headless checks (M2: the worry jar) |
| `tests/check_m3.py` | headless checks (M3: weekly PDF + backup zip) |
| `tests/check_alive.py` | headless checks (M3.5: poses, no-pop, fallback) |
| `exports.py` | weekly PDF + backup bundle (writes to `exports/`) |
| `pondside.db` | your data (created on first run, gitignored) |
| `config.json` | your choices (created on first run, gitignored) |

## Next (from the v1 plan)

M4: installer + v1.0. Peepers' animation (M3.5) is in — if he ever looks
misplaced, `PEEPERS_CX` / `PEEPERS_TOP` / `PEEPERS_H` near the top of
`pondside.py` are the only numbers to nudge.

*Built with love. The pond is behind the log — you'll never need to look.*

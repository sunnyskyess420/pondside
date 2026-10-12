# Pondside v1.1.0

*Monday 12 October 2026*

A cozy, local-first Windows companion for hard days, starring **Peepers** — a
small watercolour frog who holds your worries, times your walks, breathes with
you, and keeps a gentle weekly review.

This release is mostly about getting out of your way.

---

## What's new

- **Breathe four ways.** One pattern was never going to fit every day, so
  Peepers now offers four, one tap apart, and remembers the one you chose:
  - **Box** — in, hold, out, hold, four seconds a side, four times round.
    Steady, for a moment you have to get through.
  - **Long exhale** — in four, out six. The one for stress: the out-breath
    runs longer than the in, which is the part that settles you.
  - **Winding down** — in four, hold seven, out eight. For the end of the
    night.
  - **Even** — in five, out five. Nothing to count, nothing to hold.
- **A timer you can walk away from.** Starting a timer used to lock you into
  its own screen until you finished or gave up. Now you can leave whenever you
  like: the counting continues, a small pill on the main view shows the
  activity and the time, and one tap takes you back to it. You can let Peepers
  nap with a timer running, and he will still be counting when you wake him.

## Fixed

- **"Let it go" left a ghost.** Dropping a timer without logging it kept the
  session marked as running behind the scenes.
- **A finished breath stole your screen.** After *"there you are."* the view
  was queued to return to Peepers' face, and nothing could cancel it — so if
  you moved to the journal in those couple of seconds, you were yanked back.
  Whichever view you choose now wins.
- **Changing views too quickly wrote to the error log.** A half-second race
  when leaving a screen with a text box in it.

## Everything from v1.0.0 is still here

Peepers blinking and breathing, one-tap check-ins, timers that do the math for
you, the worry jar, the journal, the gentle week view, the weekly PDF and full
backup, the tray, and quiet mode.

## Install

Download **Pondside-Setup-1.1.0.exe** below and run it. It installs just for
you, under `%LOCALAPPDATA%\Programs\Pondside` — **no administrator prompt**.
Open him from the Start Menu; uninstall any time from there too.

**Already have v1.0?** Run this straight over the top. Your data is not touched.

## Your data

Everything lives in one SQLite file beside the app, on your machine. No
account, no cloud, no telemetry, no analytics. Exports happen only when you
ask for them.

Uninstalling **never deletes your data** — your check-ins, notes, worries,
config and exports are left exactly where they are.

## The promises

- **No water is ever shown.** The pond is behind the log; you never have to
  look at it.
- **No streaks, no scores, no red numbers, no "you should".**
- **Nothing that could feel like surveillance.** If it would make a hard day
  harder, it isn't in here.

## Notes

- Windows only for now, 64-bit. Built and tested on Windows 11.
- The installer is not code-signed, so Windows SmartScreen may warn on first
  run. `SHA256SUMS.txt` is attached if you would like to check what you got.
- Breathing patterns are deliberately short — a minute or so each. Longer is
  not better here; finishing one is.

## What's next

Seasons. An autumn glade first, then a small witch hat for October. 🎃

---

*Built with love.* 🐸

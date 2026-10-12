# Pondside v1.2.0

*Monday 12 October 2026*

A cozy, local-first Windows companion for hard days, starring **Peepers** — a
small watercolour frog who holds your worries, times your walks, breathes with
you, and keeps a gentle weekly review.

## What's new

- **Peepers remembers which breathing you did.** Four patterns went in last
  release — Box, Long exhale, Winding down, Even — and now each session is
  saved with the one you were actually using. A week of *"you breathed nine
  times"* was never the interesting part; knowing it was **mostly the long
  exhale on the days that were hard** is.
  - The **Week view** says it, right under the count: *"mostly long exhale"*.
  - The **weekly PDF** breaks the number down for you and anyone you share it
    with: *"Breaths taken: 5 (Long exhale x3, Box x1)."*
- **Upgrading takes care of itself.** Your database gains one new column the
  first time you run this. Nothing to click, nothing to export first, and not
  a single row of your history is touched. Breaths from before this release
  are still counted — they simply are not labelled, because guessing would be
  worse than not knowing.

## Everything from before

Four breathing patterns, a timer you can walk away from, Peepers blinking and
breathing, one-tap check-ins, the worry jar, the journal, the gentle week view,
the weekly PDF and full backup, the tray, and quiet mode.

## Install

Download **Pondside-Setup-1.2.0.exe** below and run it. It installs just for
you, under `%LOCALAPPDATA%\Programs\Pondside` — **no administrator prompt**.
Open him from the Start Menu; uninstall any time from there too.

**Already have an older version?** Run this straight over the top. Your data is
not touched, as always.

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

## What's next

Seasons. An autumn glade first, then a small witch hat for October. 🎃

---

*Built with love.* 🐸

# Word Count Tracker — Technical Specification

## Overview

A small macOS menu bar application that tracks progress toward a daily word-count goal in a single markdown file. The app watches the file for saves and keeps a live word counter visible in the menu bar. When the number of words written during the current session crosses the configured threshold, the display changes once to acknowledge the milestone and then continues counting without further visual change.

Scope is intentionally narrow: personal use on a single Mac, no distribution, no code signing, no cross-platform concerns.

---

## User Flow

1. User launches the app from the terminal (`python word_tracker.py`).
2. A configuration window appears with two fields, pre-filled with the last-used values (or empty on first run):
   - **File path** (markdown file to track)
   - **Daily word goal** (positive integer)
3. User confirms or edits the values and clicks **Start**.
4. The configuration window closes. The app reads the file once, records the current word count as the session **baseline**, and places the menu bar item.
5. The user writes in Typora (or any other editor). Each time the file is saved, the app reads it, recomputes the word count, and updates the menu bar title and dropdown.
6. When `current_words - baseline >= threshold`, the menu bar title and dropdown switch to the **goal-reached** state. This transition happens exactly once per app run. Counting continues; further saves update numbers but not visual state.
7. The user quits the app via the `Quit` menu item. The last-used file path and threshold are saved for the next launch.

---

## UI

### Configuration window

- Two text fields: **File path** and **Daily word goal**.
- A **Browse...** button next to the file path, opening the standard macOS file picker (`NSOpenPanel`), filtered to `.md` and `.markdown`.
- A **Start** button.
- On first launch, both fields are empty; **Start** remains disabled until the file exists and the threshold parses as a positive integer.
- On subsequent launches, fields are pre-filled with the last-used values; the user can edit or simply click **Start**.
- Invalid input (file does not exist, threshold is not a positive integer) produces an inline validation message; the window does not close.

### Menu bar title

Four states:

| State | Title |
|---|---|
| Idle, before any file-save event is seen | `📝 0/<threshold>` |
| Active, below threshold | `📝 <written>/<threshold>`, e.g. `📝 427/1000` |
| Goal reached | `📝 <current_words> 🎉`, e.g. `📝 8058 🎉` |
| Error (file missing/unreadable) | `📝 ⚠️` |

Note the difference between the "below threshold" and "goal reached" titles: before the goal, the left number is the **session delta**; after the goal, it is the **total word count** of the document.

### Dropdown menu

Opened by clicking the menu bar title. All informational lines are rendered as disabled menu items (non-interactive). Only **Quit** is clickable.

Normal state, before threshold:

```
<file_name>
Total words: <current> (last checked at HH:MM)
Written this session: <delta>
Remaining: <threshold - delta>
────────────────
Quit
```

After threshold is reached:

```
<file_name>
Total words: <current> (last checked at HH:MM)
Written this session: <delta>
🎉🎉🎉
────────────────
Quit
```

Error state (file missing):

```
<file_name>
⚠️ File not accessible
────────────────
Quit
```

If the file becomes accessible again (e.g., it reappeared after an atomic save), the app recovers automatically and resumes normal display on the next successful read.

---

## Behavior

### Word counting

- Read the file as UTF-8.
- Use Python's `str.split()` with no arguments (splits on any whitespace, collapses consecutive whitespace).
- Word count = length of the resulting list.
- No markdown preprocessing. Headings, emphasis markers, link syntax, etc., are counted as-is.

### Baseline

- Recorded once, right before the menu bar item appears.
- Fixed for the lifetime of the app run.
- To reset the session, the user quits and relaunches.

### File watching

- Use `watchdog` to watch the **directory containing the tracked file**, not the file itself.
- **Rationale:** Typora and many macOS editors save atomically — they write a temporary file and rename it over the original. File-level watchers that bind to an inode miss these events. Directory-level watching sees the creation/rename and works reliably.
- Events of interest: `on_modified`, `on_created`, `on_moved` (destination path). For each event, check whether the affected path matches the tracked file; if so, recompute.
- On every successful recount: update the menu bar title, the dropdown, and the last-checked timestamp.
- No polling fallback. No artificial debouncing — Typora's save rate is well within normal bounds.

### Threshold crossing

- The transition to the goal-reached display happens exactly once, at the first recount where `delta >= threshold`.
- After that, the display remains in the goal-reached state for the rest of the app run, even if the user deletes text and `delta` drops back below the threshold.

### Timestamp format

- `HH:MM`, 24-hour, local time, no seconds (e.g., `14:07`).

---

## Persistence

- Config stored as JSON at `~/Library/Application Support/word-tracker/config.json`.
- Fields:
  ```json
  {
    "file_path": "/absolute/path/to/file.md",
    "threshold": 1000
  }
  ```
- Written on clean shutdown (when the user clicks **Quit**).
- If the file is missing or malformed on startup, fall back to empty values and treat it as a first run.

---

## Technical Stack

- **Python 3.11+**
- **`rumps`** — menu bar app framework.
- **`watchdog`** — filesystem monitoring.
- Standard library for everything else.
- **No** PyObjC, Qt, or Xcode.

### Thread safety note

`watchdog` callbacks run on a background thread. UI updates (`self.title = ...`, rebuilding the dropdown menu) must happen on the main thread. Use `rumps.Timer` or `rumps`'s threading utilities to marshal updates safely; a simple thread-safe queue that the main thread drains on a short timer is also acceptable.

---

## Running

- Entry point: `word_tracker.py`.
- Launch from terminal: `python word_tracker.py`.
- No `.app` bundle required at this stage. If a double-clickable icon becomes desirable later, `py2app` is the standard tool — noted as a future consideration, not a requirement.

---

## Non-goals

- macOS notifications.
- Multiple files or project-wide tracking.
- Streaks or cross-day history.
- In-app session reset (quit + relaunch instead).
- Markdown-aware word counting (headings, inline code, etc., are just words).
- Signed `.app` bundle, Dock icon, LaunchAgent.
- Cross-platform support.

---

## Edge Cases

- **Empty file:** word count = 0, baseline = 0, display `📝 0/<threshold>`. Normal behavior.
- **File containing only whitespace or pure markdown syntax:** counted as whitespace-separated tokens; acceptable.
- **External edits to the config file while running:** unsupported; next launch will pick up the changes.
- **External edits to the tracked file (git pull, another editor):** treated as a normal change, counted the same way.
- **Very large files:** not a concern at novel scale — even a million-word file reads in well under 100ms, no optimization required.
- **File briefly missing during an atomic save:** ignored; next event from `watchdog` will restore state.

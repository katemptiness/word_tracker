# Word Count Tracker

A tiny macOS menu bar app that tracks your progress toward a daily word-count goal in a single markdown file. Point it at a file, set a goal, and it watches for saves and keeps a live counter in your menu bar.

## What it shows

| State | Menu bar title |
|---|---|
| Before any save | `📝 0/<goal>` |
| Writing, below goal | `📝 <written-this-session>/<goal>` |
| Goal reached | `📝 <total-words> 🎉` |
| File missing/unreadable | `📝 ⚠️` |

Click the title for a dropdown with total words, session delta, and the last-checked timestamp.

## Install (macOS)

Requires Python 3.11+.

```bash
git clone <this repo>
cd word_tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python word_tracker.py
```

On launch, pick the markdown file to track and enter a daily word goal. The app remembers these between runs. Quit via the menu bar dropdown; relaunching starts a fresh session (the "written this session" counter resets).

## Notes

- macOS only — depends on `rumps`, which needs AppKit.
- Saves from Typora and other atomic-save editors are handled correctly (the app watches the containing directory, not the file inode).
- Config is stored at `~/Library/Application Support/word-tracker/config.json`.

## Spec and design

See [`word_tracker_spec.md`](word_tracker_spec.md) for the full behavior spec.

## Tests

Pure logic has unit tests that run on any platform:

```bash
python3 -m unittest test_word_tracker_core -v
```

The rumps/watchdog glue can only be verified on a Mac.

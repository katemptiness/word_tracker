# Handoff — Word Tracker

This document is written for the next Claude (or the user + Claude) who picks up this project. Read this **instead of** re-reading the full conversation.

## State of the project

**Written on Ubuntu, never run.** The app is for macOS (uses `rumps`, which requires AppKit). All pure logic has been unit-tested on Linux. The rumps/watchdog glue has been syntax-checked (`py_compile`) but not executed.

### Files

| File | Status | Notes |
|---|---|---|
| `word_tracker_spec.md` | authoritative spec | Unchanged from what the user + prior Claude agreed on. |
| `word_tracker_core.py` | **done, 38 tests passing on Linux** | Pure logic: `count_words`, `format_hhmm`, `validate_inputs`, `load_config`, `save_config`, `SessionState`. Zero platform-specific imports. |
| `test_word_tracker_core.py` | **done, passing** | `python3 -m unittest test_word_tracker_core -v` |
| `word_tracker.py` | written, syntax-checked, **not runtime-tested** | rumps `App`, watchdog `Observer`, config flow, `osascript` file picker. |
| `requirements.txt` | done | `rumps>=0.4.0`, `watchdog>=3.0.0`. |
| `.gitignore` | done | Python standard stuff. |
| `README.md` | done | User-facing. |
| `HANDOFF.md` | this file | |

### What's verified on Linux

- All behavior encoded in `word_tracker_core.py`: word counting semantics (whitespace split, unicode, markdown counted naively), threshold-crossing state machine including the "goal is sticky even if delta drops" rule, error state transitions, config load/save roundtrip including malformed/wrong-type/negative/bool edge cases, input validation (empty, nonexistent path, zero/negative/non-integer/float thresholds, surrounding whitespace).
- `word_tracker.py` parses cleanly under `python3 -m py_compile`.

### What's NOT verified (needs a Mac)

Everything in `word_tracker.py` at runtime:

1. rumps app actually appears in the menu bar with the right title.
2. The two-stage config window flow works end-to-end (file prompt → threshold prompt → validation loop on error).
3. The `osascript` Browse button returns a usable path and the `of type {"md","markdown"}` filter behaves on the user's macOS version.
4. `watchdog.Observer` on the parent directory actually fires `on_modified`/`on_created`/`on_moved` for Typora's atomic save.
5. The queue → `rumps.Timer` (200ms) drain pattern stays on the main thread and doesn't deadlock or drop events.
6. The `rumps.MenuItem` info lines are rendered as non-clickable (`set_callback(None)`) — this is the documented way but worth eyeballing.
7. Quit button persists `{file_path, threshold}` to `~/Library/Application Support/word-tracker/config.json` before `rumps.quit_application()`.

## Design decisions worth knowing

### Two-stage config prompt (deviation from spec)
Spec says "a configuration window with two fields" and "**Start** remains disabled until… valid" with inline validation messages. `rumps.Window` is a single-text-field modal with OK/Cancel — it cannot render two fields side-by-side, cannot live-enable a button as the user types, and cannot show inline validation without closing. Implementing that UX would require direct AppKit/PyObjC, which the spec explicitly forbids ("No PyObjC, Qt, or Xcode").

**Chosen compromise:** two sequential `rumps.Window` prompts (file path → threshold), with a loop that re-prompts showing the error message if validation fails. Cancel on the threshold prompt acts as "Back" to the file prompt. Cancel on the file prompt exits the app. Functionally equivalent; the user never gets past invalid input.

User approved live validation in the abstract but was not yet aware of this rumps limitation when they approved it. Flag it for them.

### `osascript` for the Browse button (not PyObjC)
Spec asks for a Browse button backed by `NSOpenPanel`. Calling `NSOpenPanel` requires PyObjC. To honor "No PyObjC" while still getting a native file picker, `pick_file_via_osascript()` shells out to `osascript -e 'choose file ... of type {"md","markdown"}'`. Zero Python dependencies beyond stdlib.

### Thread marshaling: queue + `rumps.Timer`
Watchdog callbacks run on a background thread. They push sentinel strings onto `queue.Queue`. A `rumps.Timer` (200ms interval, on main thread) drains the queue — multiple events coalesce into a single recount. Simpler than calling AppKit's main-thread dispatch primitives, and the spec explicitly permits this pattern.

### Error state preserves `goal_reached`
If a read fails after the goal was reached, the title switches to `📝 ⚠️`, but `goal_reached=True` is preserved. On successful recovery, the display returns to `📝 <total> 🎉`, not to `📝 <delta>/<threshold>`. Covered by `test_error_after_goal_preserves_goal_on_recovery`.

### Validation rejects bools and floats
`json.load` can return `True`/`False` where an int is expected; Python treats `bool` as a subclass of `int`, so `isinstance(True, int)` is `True`. `load_config` guards against this explicitly. `validate_inputs` uses `int(s)` which rejects `"1.5"` cleanly.

## Known risks in the untested code

1. **`rumps.Window.add_button` index semantics.** Code assumes: `resp.clicked == 0` is Cancel, `1` is the default OK, `2` is the first added button (Browse). This is the documented behavior but worth confirming on first run.
2. **`rumps.separator`.** Used directly as a menu entry. If the installed rumps version uses a different token, swap for `None` or whatever that version expects.
3. **`MenuItem.set_callback(None)` disabling info lines.** The idiomatic pattern, but some rumps versions may render them as greyed but clickable; acceptable either way.
4. **Observer thread during quit.** `_stop_observer` joins with a 2-second timeout. If watchdog hangs on stop (rare but seen on some macOS versions), quit will be slightly delayed but won't deadlock.
5. **Path resolution during atomic save.** `FileChangeHandler._matches` uses `Path.resolve(strict=False)` on both the target and event paths. For Typora's temp-file-rename pattern this should match on the `on_moved` dest_path. If events don't fire for the target file, first thing to check is whether `resolve()` is returning unexpected paths (symlinks, `/private/var` vs `/var`, etc.).

## Exact next steps for the Mac session

1. Copy the repo to the Mac.
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. `python word_tracker.py`
4. Smoke test:
   - Config window appears; pick a markdown file via Browse; enter a small threshold (e.g. 10 words for quick testing).
   - Menu bar title shows `📝 0/10`.
   - Open the file in Typora, add some words, save. Title updates to `📝 N/10`.
   - Keep adding words until you cross 10. Title switches to `📝 <total> 🎉` and stays.
   - Delete words until delta drops back below 10. Title should still show `🎉`.
   - Click the menu bar item. Verify dropdown lines are disabled and the file name, total, delta, and "last checked at HH:MM" look right.
   - Quit via the dropdown. Check `~/Library/Application Support/word-tracker/config.json` has the right path and threshold.
   - Relaunch. Config window pre-fills with last-used values. Click through.
5. Error-path smoke: rename the tracked file while the app is running. Title should switch to `📝 ⚠️`. Rename it back; title should recover on the next save event.

## Open items / user should weigh in

- Is the two-stage config prompt acceptable, or do they want the real two-field window (which means accepting a bit of PyObjC)?
- If the Typora atomic-save pattern produces no watchdog events, we may need to add a fallback (e.g. periodic polling). Not implemented yet — spec says "no polling fallback," so defer unless it breaks in practice.

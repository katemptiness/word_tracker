"""Word Count Tracker — macOS menu bar app.

Entry point. Uses rumps for the menu bar and config windows, watchdog for file
monitoring. Pure logic lives in word_tracker_core (unit-tested).

This file CANNOT run on Linux — rumps requires AppKit. It is syntax-checked
with py_compile during development; real verification happens on macOS.
"""

from __future__ import annotations

import queue
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def _activate_app_for_modals() -> None:
    """Register this process as a regular GUI app so modal windows get keyboard focus.

    Without this, rumps.Window pops up but doesn't receive keystrokes because
    the Python process has no activation policy set before the first window opens.
    """
    ns_app = NSApplication.sharedApplication()
    ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    ns_app.activateIgnoringOtherApps_(True)

from word_tracker_core import (
    DEFAULT_CONFIG_PATH,
    SessionState,
    count_words,
    format_hhmm,
    load_config,
    save_config,
    validate_inputs,
)


# ---------------------------------------------------------------------------
# File picker — osascript avoids a direct PyObjC dependency for the Browse
# button while still giving the native macOS open panel.
# ---------------------------------------------------------------------------

_OSASCRIPT_PICK = '''
try
    set f to choose file with prompt "Pick a markdown file" of type {"md","markdown"}
    return POSIX path of f
on error number -128
    return ""
end try
'''


def pick_file_via_osascript() -> Optional[str]:
    try:
        result = subprocess.run(
            ["osascript", "-e", _OSASCRIPT_PICK],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    path = result.stdout.strip()
    return path or None


# ---------------------------------------------------------------------------
# Config flow — rumps.Window is a single-text-field modal, so the spec's
# "one window with two fields" becomes a two-step prompt. Functionally
# equivalent from the user's side; see HANDOFF.md for the tradeoff.
# ---------------------------------------------------------------------------


def _run_file_prompt(default_text: str, error: str = "") -> tuple[str, bool]:
    """Return (path, cancelled). Handles the Browse button internally."""
    current = default_text
    while True:
        message = "Markdown file to track."
        if error:
            message += f"\n\n⚠️ {error}"
            error = ""
        w = rumps.Window(
            message=message,
            title="Word Tracker — file",
            default_text=current,
            ok="Next",
            cancel="Cancel",
            dimensions=(360, 24),
        )
        w.add_button("Browse…")
        resp = w.run()
        if resp.clicked == 0:
            return "", True
        if resp.clicked == 2:
            picked = pick_file_via_osascript()
            if picked:
                current = picked
            else:
                current = resp.text
            continue
        return resp.text.strip(), False


def _run_threshold_prompt(default_text: str, error: str = "") -> tuple[str, bool]:
    """Return (threshold_text, went_back). Cancel here means 'back to file prompt'."""
    message = "Daily word goal (positive integer)."
    if error:
        message += f"\n\n⚠️ {error}"
    w = rumps.Window(
        message=message,
        title="Word Tracker — daily goal",
        default_text=default_text,
        ok="Start",
        cancel="Back",
        dimensions=(160, 24),
    )
    resp = w.run()
    if resp.clicked == 0:
        return "", True
    return resp.text.strip(), False


def run_config_flow(
    initial_file: str, initial_threshold: Optional[int]
) -> Optional[tuple[str, int]]:
    """Drive the two-step config prompt until valid input or user cancels."""
    file_path = initial_file or ""
    threshold_str = str(initial_threshold) if initial_threshold else ""
    error = ""
    while True:
        file_path, cancelled = _run_file_prompt(file_path, error=error)
        error = ""
        if cancelled:
            return None
        threshold_str, went_back = _run_threshold_prompt(threshold_str, error="")
        if went_back:
            continue
        ok, err = validate_inputs(file_path, threshold_str)
        if ok:
            return file_path, int(threshold_str)
        error = err or "Invalid input."


# ---------------------------------------------------------------------------
# Watchdog handler — marshals events onto a queue that the main thread drains.
# ---------------------------------------------------------------------------


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, target: Path, event_queue: "queue.Queue[str]"):
        self.target = str(target.resolve(strict=False))
        self.queue = event_queue

    def _matches(self, event) -> bool:
        for attr in ("src_path", "dest_path"):
            p = getattr(event, attr, None)
            if not p:
                continue
            try:
                if str(Path(p).resolve(strict=False)) == self.target:
                    return True
            except OSError:
                continue
        return False

    def on_modified(self, event):
        if not event.is_directory and self._matches(event):
            self.queue.put("change")

    def on_created(self, event):
        if not event.is_directory and self._matches(event):
            self.queue.put("change")

    def on_moved(self, event):
        if not getattr(event, "is_directory", False) and self._matches(event):
            self.queue.put("change")


# ---------------------------------------------------------------------------
# The rumps App itself.
# ---------------------------------------------------------------------------


class WordTrackerApp(rumps.App):
    DRAIN_INTERVAL_SECONDS = 0.2

    def __init__(self, file_path: str, threshold: int):
        super().__init__(name="WordTracker", title="📝 …", quit_button=None)
        self.file_path = Path(file_path)
        self.filename = self.file_path.name
        self.event_queue: queue.Queue[str] = queue.Queue()
        self.observer: Optional[Observer] = None

        baseline = self._read_count()
        now = format_hhmm(datetime.now())
        self.state = SessionState(
            baseline=baseline if baseline is not None else 0,
            threshold=threshold,
            now_hhmm=now,
        )
        if baseline is None:
            self.state.mark_error()

        self._refresh_display()
        self._start_observer()

        self.drain_timer = rumps.Timer(self._drain_queue, self.DRAIN_INTERVAL_SECONDS)
        self.drain_timer.start()

    def _read_count(self) -> Optional[int]:
        try:
            text = self.file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError, UnicodeDecodeError):
            return None
        return count_words(text)

    def _refresh_display(self) -> None:
        self.title = self.state.title()
        info_lines = self.state.dropdown_lines(self.filename)

        items: list = []
        for line in info_lines:
            mi = rumps.MenuItem(line)
            mi.set_callback(None)
            items.append(mi)
        items.append(rumps.separator)
        items.append(rumps.MenuItem("Quit", callback=self._on_quit))

        self.menu.clear()
        self.menu.update(items)

    def _drain_queue(self, _timer) -> None:
        saw_event = False
        try:
            while True:
                self.event_queue.get_nowait()
                saw_event = True
        except queue.Empty:
            pass
        if saw_event:
            self._recount()

    def _recount(self) -> None:
        count = self._read_count()
        now = format_hhmm(datetime.now())
        if count is None:
            self.state.mark_error()
        else:
            self.state.update(count, now)
        self._refresh_display()

    def _start_observer(self) -> None:
        parent = self.file_path.parent
        handler = FileChangeHandler(self.file_path, self.event_queue)
        self.observer = Observer()
        self.observer.schedule(handler, str(parent), recursive=False)
        self.observer.start()

    def _stop_observer(self) -> None:
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=2.0)
            except Exception:
                pass
            self.observer = None

    def _on_quit(self, _sender) -> None:
        try:
            save_config(DEFAULT_CONFIG_PATH, str(self.file_path), self.state.threshold)
        except OSError:
            pass
        self._stop_observer()
        rumps.quit_application()


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def main() -> None:
    _activate_app_for_modals()

    cfg = load_config(DEFAULT_CONFIG_PATH)
    initial_file = cfg.get("file_path") or ""
    initial_threshold = cfg.get("threshold")

    result = run_config_flow(initial_file, initial_threshold)
    if result is None:
        return

    file_path, threshold = result
    WordTrackerApp(file_path=file_path, threshold=threshold).run()


if __name__ == "__main__":
    main()

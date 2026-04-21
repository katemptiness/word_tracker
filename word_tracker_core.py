"""Pure logic for the word tracker: word counting, session state, config, validation.

Nothing here imports rumps or watchdog, so it can be unit-tested on any platform.
The macOS-only glue lives in word_tracker.py.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "word-tracker" / "config.json"
)


def count_words(text: str) -> int:
    """Whitespace-split word count, per spec."""
    return len(text.split())


def format_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def validate_inputs(file_path: str, threshold_str: str) -> tuple[bool, Optional[str]]:
    """Return (ok, error_message). Used by the config window to gate the Start button."""
    file_path = (file_path or "").strip()
    threshold_str = (threshold_str or "").strip()

    if not file_path:
        return False, "Please choose a file."
    if not Path(file_path).expanduser().is_file():
        return False, "File does not exist."

    try:
        n = int(threshold_str)
    except (ValueError, TypeError):
        return False, "Threshold must be an integer."
    if n <= 0:
        return False, "Threshold must be a positive integer."

    return True, None


def _empty_config() -> dict:
    return {"file_path": "", "threshold": None}


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Return {'file_path': str, 'threshold': int | None}. Missing/malformed → empty."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _empty_config()

    if not isinstance(data, dict):
        return _empty_config()

    fp = data.get("file_path", "")
    if not isinstance(fp, str):
        fp = ""

    th = data.get("threshold")
    if not isinstance(th, int) or isinstance(th, bool) or th <= 0:
        th = None

    return {"file_path": fp, "threshold": th}


def save_config(path: Path, file_path: str, threshold: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"file_path": file_path, "threshold": threshold}, f, indent=2)


class SessionState:
    """Tracks a single run of the app. Goal-reached is sticky for the run's lifetime."""

    def __init__(self, baseline: int, threshold: int, now_hhmm: str):
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        self.baseline = baseline
        self.threshold = threshold
        self.current = baseline
        self.goal_reached = False
        self.last_checked_hhmm = now_hhmm
        self.error = False

    @property
    def delta(self) -> int:
        return self.current - self.baseline

    def update(self, current: int, now_hhmm: str) -> None:
        self.current = current
        self.last_checked_hhmm = now_hhmm
        self.error = False
        if self.delta >= self.threshold:
            self.goal_reached = True

    def mark_error(self) -> None:
        self.error = True

    def title(self) -> str:
        if self.error:
            return "📝 ⚠️"
        if self.goal_reached:
            return f"📝 {self.current} 🎉"
        return f"📝 {self.delta}/{self.threshold}"

    def dropdown_lines(self, filename: str) -> list[str]:
        if self.error:
            return [filename, "⚠️ File not accessible"]
        ts = (
            f" (last checked at {self.last_checked_hhmm})"
            if self.last_checked_hhmm
            else ""
        )
        lines = [
            filename,
            f"Total words: {self.current}{ts}",
            f"Written this session: {self.delta}",
        ]
        if self.goal_reached:
            lines.append("🎉🎉🎉")
        else:
            lines.append(f"Remaining: {self.threshold - self.delta}")
        return lines

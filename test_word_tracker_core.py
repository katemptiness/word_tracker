"""Unit tests for word_tracker_core. Runnable on any platform — no rumps/watchdog."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from word_tracker_core import (
    SessionState,
    count_words,
    format_hhmm,
    load_config,
    save_config,
    validate_inputs,
)


class TestCountWords(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(count_words(""), 0)

    def test_whitespace_only(self):
        self.assertEqual(count_words("   \n\t  \n"), 0)

    def test_simple(self):
        self.assertEqual(count_words("hello world"), 2)

    def test_collapses_whitespace(self):
        self.assertEqual(count_words("  hello   world  \n\nfoo "), 3)

    def test_unicode(self):
        self.assertEqual(count_words("привет мир 你好"), 3)

    def test_markdown_counted_naively(self):
        # "# Hello **world**" → three whitespace-separated tokens
        self.assertEqual(count_words("# Hello **world**"), 3)

    def test_newlines_only(self):
        self.assertEqual(count_words("\n\n\n"), 0)


class TestFormatHHMM(unittest.TestCase):
    def test_zero_padded(self):
        self.assertEqual(format_hhmm(datetime(2026, 4, 21, 9, 7)), "09:07")

    def test_afternoon(self):
        self.assertEqual(format_hhmm(datetime(2026, 4, 21, 14, 7)), "14:07")


class TestValidateInputs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
        self._tmp.write(b"hi")
        self._tmp.close()
        self.good_path = self._tmp.name

    def tearDown(self):
        Path(self.good_path).unlink(missing_ok=True)

    def test_empty_path(self):
        ok, err = validate_inputs("", "1000")
        self.assertFalse(ok)
        self.assertIn("choose a file", err.lower())

    def test_whitespace_path(self):
        ok, err = validate_inputs("   ", "1000")
        self.assertFalse(ok)

    def test_nonexistent_path(self):
        ok, err = validate_inputs("/definitely/not/here.md", "1000")
        self.assertFalse(ok)
        self.assertIn("does not exist", err.lower())

    def test_zero_threshold(self):
        ok, err = validate_inputs(self.good_path, "0")
        self.assertFalse(ok)
        self.assertIn("positive", err.lower())

    def test_negative_threshold(self):
        ok, err = validate_inputs(self.good_path, "-5")
        self.assertFalse(ok)

    def test_non_integer_threshold(self):
        ok, err = validate_inputs(self.good_path, "abc")
        self.assertFalse(ok)
        self.assertIn("integer", err.lower())

    def test_float_threshold_rejected(self):
        ok, err = validate_inputs(self.good_path, "1.5")
        self.assertFalse(ok)

    def test_empty_threshold(self):
        ok, err = validate_inputs(self.good_path, "")
        self.assertFalse(ok)

    def test_valid(self):
        ok, err = validate_inputs(self.good_path, "1000")
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_valid_with_surrounding_whitespace(self):
        ok, err = validate_inputs(f"  {self.good_path}  ", " 1000 ")
        self.assertTrue(ok)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "nested" / "config.json"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_load_missing_returns_empty(self):
        cfg = load_config(self.path)
        self.assertEqual(cfg, {"file_path": "", "threshold": None})

    def test_roundtrip(self):
        save_config(self.path, "/foo/bar.md", 1500)
        cfg = load_config(self.path)
        self.assertEqual(cfg, {"file_path": "/foo/bar.md", "threshold": 1500})

    def test_save_creates_parent_dir(self):
        self.assertFalse(self.path.parent.exists())
        save_config(self.path, "/x.md", 10)
        self.assertTrue(self.path.exists())

    def test_malformed_json_returns_empty(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(load_config(self.path), {"file_path": "", "threshold": None})

    def test_non_dict_json_returns_empty(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(load_config(self.path), {"file_path": "", "threshold": None})

    def test_wrong_types_coerced_to_empty(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"file_path": 123, "threshold": "abc"}), encoding="utf-8"
        )
        cfg = load_config(self.path)
        self.assertEqual(cfg, {"file_path": "", "threshold": None})

    def test_negative_threshold_coerced_to_none(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"file_path": "/x.md", "threshold": -10}), encoding="utf-8"
        )
        cfg = load_config(self.path)
        self.assertEqual(cfg["threshold"], None)

    def test_bool_threshold_rejected(self):
        # json.dumps(True) is "true"; bool is subclass of int in Python, guard against it
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"file_path": "/x.md", "threshold": True}), encoding="utf-8"
        )
        self.assertIsNone(load_config(self.path)["threshold"])


class TestSessionState(unittest.TestCase):
    def test_rejects_nonpositive_threshold(self):
        with self.assertRaises(ValueError):
            SessionState(baseline=0, threshold=0, now_hhmm="10:00")
        with self.assertRaises(ValueError):
            SessionState(baseline=0, threshold=-1, now_hhmm="10:00")

    def test_idle_state_shows_zero_over_threshold(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        self.assertEqual(s.delta, 0)
        self.assertEqual(s.title(), "📝 0/500")

    def test_idle_dropdown(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        lines = s.dropdown_lines("novel.md")
        self.assertEqual(lines[0], "novel.md")
        self.assertIn("Total words: 100", lines[1])
        self.assertIn("last checked at 10:00", lines[1])
        self.assertEqual(lines[2], "Written this session: 0")
        self.assertEqual(lines[3], "Remaining: 500")

    def test_update_below_threshold(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.update(current=300, now_hhmm="10:15")
        self.assertEqual(s.delta, 200)
        self.assertEqual(s.title(), "📝 200/500")
        self.assertFalse(s.goal_reached)

    def test_threshold_crossing_exact(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.update(current=600, now_hhmm="11:00")
        self.assertTrue(s.goal_reached)
        self.assertEqual(s.title(), "📝 500 🎉")

    def test_threshold_crossing_dropdown(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.update(current=700, now_hhmm="11:00")
        lines = s.dropdown_lines("novel.md")
        self.assertEqual(lines[0], "novel.md")
        self.assertIn("Total words: 700", lines[1])
        self.assertEqual(lines[2], "Written this session: 600")
        self.assertEqual(lines[3], "🎉🎉🎉")

    def test_goal_reached_is_sticky_when_delta_drops(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.update(current=650, now_hhmm="11:00")
        self.assertTrue(s.goal_reached)
        s.update(current=400, now_hhmm="12:00")  # delta back down to 300
        self.assertTrue(s.goal_reached)
        self.assertEqual(s.title(), "📝 300 🎉")

    def test_error_state(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.mark_error()
        self.assertEqual(s.title(), "📝 ⚠️")
        self.assertEqual(s.dropdown_lines("novel.md"), ["novel.md", "⚠️ File not accessible"])

    def test_recovery_from_error(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.mark_error()
        s.update(current=200, now_hhmm="10:30")
        self.assertFalse(s.error)
        self.assertEqual(s.title(), "📝 100/500")

    def test_error_after_goal_preserves_goal_on_recovery(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.update(current=700, now_hhmm="11:00")
        self.assertTrue(s.goal_reached)
        s.mark_error()
        self.assertEqual(s.title(), "📝 ⚠️")
        s.update(current=720, now_hhmm="11:05")
        self.assertTrue(s.goal_reached)
        self.assertEqual(s.title(), "📝 620 🎉")

    def test_timestamp_updates_on_each_recount(self):
        s = SessionState(baseline=100, threshold=500, now_hhmm="10:00")
        s.update(current=200, now_hhmm="10:30")
        self.assertEqual(s.last_checked_hhmm, "10:30")
        s.update(current=250, now_hhmm="11:45")
        self.assertEqual(s.last_checked_hhmm, "11:45")


if __name__ == "__main__":
    unittest.main()

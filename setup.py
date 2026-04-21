"""py2app build script.

Usage:
    python setup.py py2app          # release build (standalone .app in dist/)
    python setup.py py2app -A       # alias build (fast, but not portable)

LSUIElement=True keeps the app menu-bar-only (no Dock icon, no menu bar file menu).

libffi is bundled explicitly because py2app with Anaconda/Homebrew Python does
not always pick it up via the usual dylib walk — _ctypes.so depends on it, and
without it the app crashes at startup with "Library not loaded: libffi.8.dylib".
"""

import sys
from pathlib import Path

from setuptools import setup

APP = ["word_tracker.py"]

# base_prefix, not prefix: in a venv, libffi lives with the parent Python install.
_candidates = [
    Path(sys.base_prefix) / "lib" / "libffi.8.dylib",
    Path(sys.prefix) / "lib" / "libffi.8.dylib",
]
FRAMEWORKS = [str(p) for p in _candidates if p.exists()][:1]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "WordTracker",
        "CFBundleDisplayName": "Word Tracker",
        "CFBundleIdentifier": "com.katemptiness.wordtracker",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,
    },
    "packages": ["rumps", "watchdog"],
    "frameworks": FRAMEWORKS,
}

setup(
    app=APP,
    name="WordTracker",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

"""Runtime introspection helpers — distinguish dev mode from a built app.

PyInstaller sets ``sys.frozen = True`` and ``sys._MEIPASS`` to the bundle
data dir. Nuitka doesn't set either: the binary lives at
``…/StemGen.app/Contents/MacOS/StemGenApp`` (or ``…/StemGenApp.dist/`` on
Windows) and bundled data is co-located in that directory. We detect either
packaging via a single ``is_frozen()`` and expose a uniform
``bundle_data_dir()`` so call sites don't have to re-implement the heuristic.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

# GPAC ships per platform under the repo root; the same folder is copied
# verbatim into the bundle by scripts/_build_app.{sh,ps1}.
_GPAC_FOLDER = {"Windows": "GPAC_win", "Darwin": "GPAC_mac"}
_MP4BOX_EXE = {"Windows": "mp4box.exe", "Darwin": "mp4box"}

# GUI apps launched from Finder inherit launchd's PATH, not the shell's, so
# Homebrew/MacPorts tools (ffmpeg, sox) are invisible unless added here.
_MACOS_EXTRA_PATH = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")


def is_frozen() -> bool:
    """True if running from a PyInstaller or Nuitka bundle."""
    if getattr(sys, "frozen", False):
        return True
    # Nuitka sets ``__compiled__`` on every compiled module; the entry
    # script ends up as the running module's ``__main__``.
    main_mod = sys.modules.get("__main__")
    if main_mod is not None and hasattr(main_mod, "__compiled__"):
        return True
    # Fallback: executable lives inside a .app bundle (covers Nuitka in
    # ``--mode=app`` even if ``__compiled__`` ever stops being injected).
    exe = Path(sys.executable).resolve()
    return ".app/Contents/MacOS/" in exe.as_posix()


def bundle_data_dir() -> Path:
    """Directory holding bundled (read-only, ships-with-the-app) data files.

    * PyInstaller: ``sys._MEIPASS`` (PyInstaller extracts data files here).
    * Nuitka ``--mode=app`` / ``standalone``: the directory of
      ``sys.executable``.
    * Dev: the project root (one level above ``src/``).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # Dev: <repo>/src/runtime.py → <repo>/
    return Path(__file__).resolve().parent.parent


def mp4box_path(system: str | None = None, data_dir: Path | None = None) -> Path:
    """Absolute path of the bundled GPAC ``mp4box`` for this platform.

    ``system`` / ``data_dir`` are injectable for tests; they default to
    :func:`platform.system` and :func:`bundle_data_dir`.
    """
    system = system or platform.system()
    data_dir = data_dir or bundle_data_dir()
    folder = _GPAC_FOLDER.get(system, "GPAC_linux")
    exe = _MP4BOX_EXE.get(system, "MP4Box")
    return data_dir / folder / exe


def augmented_path(env_path: str | None = None, system: str | None = None) -> str:
    """``PATH`` with the usual macOS package-manager bin dirs appended.

    Returns a new string — the caller decides whether to write it back to
    ``os.environ``. Entries already present are not duplicated; other
    platforms get their ``PATH`` back untouched.
    """
    env_path = os.environ.get("PATH", "") if env_path is None else env_path
    system = system or platform.system()
    if system != "Darwin":
        return env_path
    # ":" is macOS's separator regardless of the host running this code
    # (the unit tests exercise the Darwin branch from Windows too).
    present = env_path.split(":") if env_path else []
    missing = [p for p in _MACOS_EXTRA_PATH if p not in present]
    return ":".join(present + missing)

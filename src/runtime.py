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
import subprocess
import sys
from pathlib import Path

# GPAC ships per platform under the repo root; the same folder is copied
# verbatim into the bundle by scripts/_build_app.{sh,ps1}.
_GPAC_FOLDER = {"Windows": "GPAC_win", "Darwin": "GPAC_mac"}
_MP4BOX_EXE = {"Windows": "mp4box.exe", "Darwin": "mp4box"}

# Static ffmpeg / ffprobe / sox built by scripts/build_audio_tools.sh, copied
# verbatim into the bundle next to the GPAC folder. No Linux build: from
# source on Linux the system tools are used.
_AUDIO_FOLDER = {"Windows": "AUDIO_win", "Darwin": "AUDIO_mac"}

# Fallback for running from source on macOS without the bundled tools: GUI
# apps launched from Finder inherit launchd's PATH, not the shell's, so
# Homebrew/MacPorts tools are invisible unless added here.
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


def audio_tools_dir(system: str | None = None, data_dir: Path | None = None) -> Path | None:
    """Folder holding the bundled ffmpeg / ffprobe / sox, or ``None`` (Linux)."""
    system = system or platform.system()
    folder = _AUDIO_FOLDER.get(system)
    if folder is None:
        return None
    return (data_dir or bundle_data_dir()) / folder


def augmented_path(
    env_path: str | None = None,
    system: str | None = None,
    data_dir: Path | None = None,
) -> str:
    """``PATH`` with the bundled audio tools first (and Homebrew dirs last on macOS).

    The bundled folder goes first so our known-good ffmpeg / sox win over
    whatever the user has installed — demucs calls ``ffmpeg`` by bare name,
    so ``PATH`` is the only way to point it at ours. Returns a new string —
    the caller decides whether to write it back to ``os.environ``. Entries
    already present are not duplicated; Linux gets its ``PATH`` back untouched.
    """
    env_path = os.environ.get("PATH", "") if env_path is None else env_path
    system = system or platform.system()
    # The target's separator, not the host's (the unit tests exercise both
    # branches from either OS).
    sep = ";" if system == "Windows" else ":"
    present = env_path.split(sep) if env_path else []
    tools = audio_tools_dir(system=system, data_dir=data_dir)
    first = [str(tools)] if tools is not None and str(tools) not in present else []
    extra = _MACOS_EXTRA_PATH if system == "Darwin" else ()
    last = [p for p in extra if p not in present]
    return sep.join(first + present + last)


# Win32 process-creation flag: start a console program without giving it a
# console window. Spelled out because subprocess only defines it on Windows.
CREATE_NO_WINDOW = 0x08000000


def hide_console_windows(system: str | None = None, module=subprocess) -> bool:
    """Make every child process start without a console window (Windows only).

    The app is a GUI binary, so on Windows each console program it runs —
    sox, ffprobe, ffmpeg, mp4box, from our code and from demucs's — would
    otherwise flash a console window. Rather than threading a flag through
    every call site (demucs's included), this swaps ``module.Popen`` for a
    subclass that ORs ``CREATE_NO_WINDOW`` into ``creationflags``;
    ``subprocess.run`` / ``check_output`` / ``call`` all construct ``Popen``
    through the module attribute, so they pick it up. Call it once at
    startup, before anything spawns a process.

    Returns True if the patch is (now) in place. A no-op elsewhere, where
    ``creationflags`` is not supported. ``module`` is injectable for tests.
    """
    system = system or platform.system()
    if system != "Windows":
        return False
    base = module.Popen
    if getattr(base, "_stemgen_no_window", False):
        return True

    class _NoWindowPopen(base):
        _stemgen_no_window = True

        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    module.Popen = _NoWindowPopen
    return True

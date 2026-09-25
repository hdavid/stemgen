"""Headless tests for src/runtime.py — no Qt, no GPAC, no ffmpeg needed."""

from pathlib import Path

import pytest

import runtime

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Darwin", Path("GPAC_mac") / "mp4box"),
        ("Windows", Path("GPAC_win") / "mp4box.exe"),
        ("Linux", Path("GPAC_linux") / "MP4Box"),
    ],
)
def test_mp4box_path_per_platform(system, expected):
    base = Path("/bundle")
    assert runtime.mp4box_path(system=system, data_dir=base) == base / expected


def test_mp4box_path_dev_mode_points_into_repo():
    # Running from source: the GPAC folder is the one checked into the repo.
    assert not runtime.is_frozen()
    assert runtime.bundle_data_dir() == REPO_ROOT
    assert runtime.mp4box_path(system="Darwin").is_file()


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Darwin", Path("AUDIO_mac")),
        ("Windows", Path("AUDIO_win")),
    ],
)
def test_audio_tools_dir_per_platform(system, expected):
    base = Path("/bundle")
    assert runtime.audio_tools_dir(system=system, data_dir=base) == base / expected


def test_audio_tools_dir_none_on_linux():
    # No bundled build for Linux: the system ffmpeg / sox are used from source.
    assert runtime.audio_tools_dir(system="Linux", data_dir=Path("/bundle")) is None


@pytest.mark.parametrize("tool", ["ffmpeg", "ffprobe", "sox"])
def test_audio_tools_checked_into_repo_for_macos(tool):
    assert (runtime.audio_tools_dir(system="Darwin") / tool).is_file()


def test_augmented_path_puts_bundled_tools_first_on_macos():
    result = runtime.augmented_path("/usr/bin:/bin", system="Darwin", data_dir=Path("/b"))
    parts = result.split(":")  # macOS separator, whatever the host
    # Bundled tools win over a Homebrew ffmpeg/sox the user may have.
    assert parts[:3] == [str(Path("/b") / "AUDIO_mac"), "/usr/bin", "/bin"]
    assert "/opt/homebrew/bin" in parts
    assert "/usr/local/bin" in parts


def test_augmented_path_puts_bundled_tools_first_on_windows():
    result = runtime.augmented_path("C:\\Windows", system="Windows", data_dir=Path("/b"))
    parts = result.split(";")  # Windows separator, whatever the host
    assert parts == [str(Path("/b") / "AUDIO_win"), "C:\\Windows"]


def test_augmented_path_handles_empty_path():
    result = runtime.augmented_path("", system="Windows", data_dir=Path("/b"))
    assert result == str(Path("/b") / "AUDIO_win")


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
def test_augmented_path_is_idempotent(system):
    once = runtime.augmented_path("/usr/bin", system=system, data_dir=Path("/b"))
    assert runtime.augmented_path(once, system=system, data_dir=Path("/b")) == once


def test_augmented_path_untouched_on_linux():
    assert runtime.augmented_path("/usr/bin", system="Linux") == "/usr/bin"


class _FakeSubprocess:
    """Stands in for the subprocess module: its Popen records the kwargs it gets."""

    def __init__(self):
        self.calls = []
        calls = self.calls

        class Popen:
            def __init__(self, *args, **kwargs):
                calls.append(kwargs)

        self.Popen = Popen


def test_hide_console_windows_sets_create_no_window_on_windows():
    # A GUI app on Windows flashes a console window for every console child
    # (sox, ffprobe, ffmpeg, mp4box — ours and demucs's) unless each gets
    # CREATE_NO_WINDOW. subprocess.run/check_output all go through Popen.
    fake = _FakeSubprocess()
    assert runtime.hide_console_windows(system="Windows", module=fake) is True
    fake.Popen(["sox"])
    fake.Popen(["ffmpeg"], creationflags=0x00000200)  # caller's own flags survive
    assert fake.calls[0]["creationflags"] == runtime.CREATE_NO_WINDOW
    assert fake.calls[1]["creationflags"] == 0x00000200 | runtime.CREATE_NO_WINDOW


def test_hide_console_windows_is_idempotent():
    fake = _FakeSubprocess()
    runtime.hide_console_windows(system="Windows", module=fake)
    runtime.hide_console_windows(system="Windows", module=fake)
    fake.Popen(["sox"])
    assert fake.calls[0]["creationflags"] == runtime.CREATE_NO_WINDOW


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_hide_console_windows_noop_elsewhere(system):
    # creationflags is Windows-only; POSIX Popen raises if it is set.
    fake = _FakeSubprocess()
    original = fake.Popen
    assert runtime.hide_console_windows(system=system, module=fake) is False
    assert fake.Popen is original

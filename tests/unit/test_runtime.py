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

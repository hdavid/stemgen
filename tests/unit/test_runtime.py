"""Headless tests for src/runtime.py — no Qt, no GPAC, no ffmpeg needed."""

import os
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


def test_augmented_path_appends_missing_macos_dirs():
    result = runtime.augmented_path("/usr/bin:/bin", system="Darwin")
    parts = result.split(os.pathsep)
    assert parts[:2] == ["/usr/bin", "/bin"]
    assert "/opt/homebrew/bin" in parts
    assert "/usr/local/bin" in parts


def test_augmented_path_is_idempotent():
    once = runtime.augmented_path("/usr/bin", system="Darwin")
    assert runtime.augmented_path(once, system="Darwin") == once


def test_augmented_path_untouched_off_macos():
    assert runtime.augmented_path("/usr/bin", system="Linux") == "/usr/bin"
    assert runtime.augmented_path("C:\\Windows", system="Windows") == "C:\\Windows"

"""Guard the Nuitka flags a running bundle depends on but can't be seen statically.

Nuitka only follows imports it can see. These modules/folders are reached by
name at runtime, so dropping one from a build script produces a bundle that
builds fine and then fails on every track.
"""

from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
BUILDS = {
    "mac": SCRIPTS / "_build_app.sh",
    "win": SCRIPTS / "_build_app.ps1",
}

# Globals the htdemucs checkpoint pickle references; torch.load imports them
# by name while unpickling. numpy.core is a numpy-2 compatibility shim nothing
# imports statically — without it every track fails with
# "No module named 'numpy.core.multiarray'".
CHECKPOINT_MODULES = ["numpy.core.multiarray", "fractions"]


@pytest.mark.parametrize("target", BUILDS)
@pytest.mark.parametrize("module", CHECKPOINT_MODULES)
def test_checkpoint_pickle_modules_are_included(target, module):
    assert f"--include-module={module}" in BUILDS[target].read_text()


@pytest.mark.parametrize(
    ("target", "flag"),
    [
        ("mac", "--include-data-dir=AUDIO_mac=AUDIO_mac"),
        # raw dir: Nuitka silently drops .exe/.dll from a data dir.
        ("win", "--include-raw-dir=AUDIO_win=AUDIO_win"),
    ],
)
def test_bundled_audio_tools_are_shipped(target, flag):
    assert flag in BUILDS[target].read_text()

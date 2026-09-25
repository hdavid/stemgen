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


# CUDA-torch DLLs a GPU split never needs. Each was removed from a real
# cu130 torch on an RTX 3080 and htdemucs still split 60 s of audio to
# bit-identical output at the same speed. Nothing loads them at import time.
UNNEEDED_CUDA_DLLS = [
    "cudnn_adv64_9.dll",
    "cusolverMg64_12.dll",
    "nvrtc64_130_0.alt.dll",
    "curand64_10.dll",
    "nvperf_host.dll",
]
# Removing any of these broke the split (sub-library loading failures, or
# "unable to find an engine") — they must never be excluded.
REQUIRED_CUDA_DLLS = [
    "cudnn_engines_runtime_compiled64_9.dll",
    "cudnn_heuristic64_9.dll",
    "cudnn_engines_precompiled64_9.dll",
    "cudnn_ops64_9.dll",
]


@pytest.mark.parametrize("dll", UNNEEDED_CUDA_DLLS)
def test_unneeded_cuda_dlls_are_excluded_on_windows(dll):
    # Nuitka matches the path inside the bundle, not the bare filename.
    assert f"--noinclude-dlls=torch/lib/{dll}" in BUILDS["win"].read_text()


@pytest.mark.parametrize("dll", REQUIRED_CUDA_DLLS)
def test_required_cuda_dlls_are_never_excluded(dll):
    text = BUILDS["win"].read_text()
    assert f"--noinclude-dlls=torch/lib/{dll}" not in text
    assert "--noinclude-dlls=torch/lib/cudnn_*" not in text

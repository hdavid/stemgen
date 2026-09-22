"""Regression tests for StemGen.convert() path handling.

sox is replaced by a stub that records its arguments, so these run without
sox/ffmpeg installed and without touching real audio.
"""

import os
import subprocess

import pytest

import stemgen


@pytest.fixture
def fake_sox(monkeypatch):
    """Record every subprocess.run call; create the sox output file."""
    calls = []

    def run(args, **kwargs):
        calls.append(list(args))
        if args[0] == "sox":
            # sox's output path is the first non-option argument after the
            # input (and after `-b 24` when present).
            out = args[6] if args[3] == "-b" else args[4]
            with open(out, "wb") as fh:
                fh.write(b"RIFF")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(stemgen.subprocess, "run", run)
    return calls


def _make_track(tmp_path, name="track"):
    directory = str(tmp_path) + os.sep  # StemGen.run() adds a trailing separator
    (tmp_path / name).mkdir()
    copied = tmp_path / name / f"{name}.wav"
    copied.write_bytes(b"ORIGINAL")
    return directory, str(copied)


def test_in_place_resample_never_runs_sox_with_input_equal_output(tmp_path, fake_sox):
    directory, copied = _make_track(tmp_path)
    # The historical bug: a doubled separator made this path compare unequal
    # to convert()'s own output path, so sox was run with input == output.
    doubled = copied.replace(os.sep + "track" + os.sep, os.sep + os.sep + "track" + os.sep, 1)
    assert doubled != copied and os.path.normpath(doubled) == copied

    stemgen.StemGen().convert(doubled, directory, "track.wav", ".wav", "track", 24, 48000)

    sox_calls = [c for c in fake_sox if c[0] == "sox"]
    assert len(sox_calls) == 1
    in_path, out_path = sox_calls[0][1], sox_calls[0][4]
    assert os.path.normpath(in_path) != os.path.normpath(out_path)
    # The temp output was renamed over the original.
    assert os.path.isfile(copied)
    assert not os.path.exists(os.path.join(str(tmp_path), "track", "track.44100Hz.wav"))


def test_44100_wav_is_left_untouched(tmp_path, fake_sox):
    directory, copied = _make_track(tmp_path)
    stemgen.StemGen().convert(copied, directory, "track.wav", ".wav", "track", 24, 44100)
    assert fake_sox == []
    assert open(copied, "rb").read() == b"ORIGINAL"


def test_emit_error_stores_strings():
    sg = stemgen.StemGen()
    sg.emit_error(RuntimeError("boom"))
    assert sg.errors == ["boom"]
    # print_report joins errors into the details text — must not TypeError.
    sg.failed_tracks.append("x")
    sg.print_report()

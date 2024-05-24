#!/usr/bin/env python3

import argparse
import os
import shutil
import sys
import subprocess
from pathlib import Path
import unicodedata
import torch
import demucs.separate
from metadata import get_cover, get_metadata
from tkinter import filedialog


SUPPORTED_FILES = [".wave", ".wav", ".aiff", ".aif", ".flac", ".mp3"]
REQUIRED_PACKAGES = ["ffmpeg", "sox"]
USAGE = f"""
Stemgen is a Stem file generator. Convert any track into a stem and have fun with Traktor.

Usage: python3 stemgen.py -i [INPUT_PATH] -o [OUTPUT_PATH]

Supported input file format: {SUPPORTED_FILES}
"""
VERSION = "6.0.0"
INSTALL_DIR = Path(__file__).parent.absolute()
PROCESS_DIR = os.getcwd()

parser = argparse.ArgumentParser(
    description=USAGE, formatter_class=argparse.RawTextHelpFormatter
)
parser.add_argument(
    dest="POSITIONAL_INPUT_PATH", nargs="?", help="the path to the input file"
)
parser.add_argument(
    "-i", "--input", dest="INPUT_PATH", help="the path to the input file"
)
parser.add_argument(
    "-o",
    "--output",
    dest="OUTPUT_PATH",
    default="output"
    if str(INSTALL_DIR) == PROCESS_DIR or INSTALL_DIR.as_posix() == PROCESS_DIR
    else ".",
    help="the path to the output folder",
)
parser.add_argument("-f", "--format", dest="FORMAT", default="alac", help="aac or alac")
parser.add_argument("-w", default=False, action="store_true", help="Overwrite existing file")
parser.add_argument("-d", "--device", dest="DEVICE", help="cpu or cuda or mps")
parser.add_argument("-v", "--version", action="version", version=VERSION)
parser.add_argument('-n', "--model_name", dest="MODEL_NAME", help="name of the model to use")
parser.add_argument('-s', "--model_shifts", dest="MODEL_SHIFTS", help="number of shifts for demucs to use")
args = parser.parse_args()

INPUT_PATH = args.POSITIONAL_INPUT_PATH or args.INPUT_PATH
if INPUT_PATH is None:
    LOOP=True
else:
    LOOP=False

OUTPUT_PATH = (
    args.OUTPUT_PATH
    if os.path.isabs(args.OUTPUT_PATH)
    else os.path.join(PROCESS_DIR, args.OUTPUT_PATH)
)   

FORMAT = args.FORMAT

OVERWRITE_EXISTING = args.w

DEVICE = (
    args.DEVICE
    if args.DEVICE is not None
    else ("cuda" if torch.cuda.is_available() else (
	"mps" if torch.backends.mps.is_available() else "cpu"))
)

PYTHON_EXEC = sys.executable if not None else "python3"

MODEL_NAME = (
    args.MODEL_NAME
    if args.MODEL_NAME is not None
    else "htdemucs"
)

MODEL_SHIFTS = (
    args.MODEL_SHIFTS
    if args.MODEL_SHIFTS is not None
    else "1"
)


# CONVERSION AND GENERATION


def convert():
    print("Converting to wav 44.1kHz.")

    # We downsample to 44.1kHz to avoid problems with the separation software
    # because the models are trained on 44.1kHz audio files

    # QUALITY            WIDTH  REJ dB   TYPICAL USE
    # -v  very high      95%     175     24-bit mastering

    # -M/-I/-L     Phase response = minimum/intermediate/linear(default)
    # -s           Steep filter (band-width = 99%)
    # -a           Allow aliasing above the pass-band

    global BIT_DEPTH
    global SAMPLE_RATE

    converted_file_path = os.path.join(OUTPUT_PATH, FILE_NAME, FILE_NAME + ".wav")

    if BIT_DEPTH == 32:
        # Downconvert to 24-bit
        if FILE_PATH == converted_file_path:
            subprocess.run(
                [
                    "sox",
                    FILE_PATH,
                    "--show-progress",
                    "-b",
                    "24",
                    os.path.join(OUTPUT_PATH, FILE_NAME, FILE_NAME + ".24bit.wav"),
                    "rate",
                    "-v",
                    "-a",
                    "-I",
                    "-s",
                    "44100",
                ],
                check=True,
    			stdout = subprocess.DEVNULL,
    			stderr = subprocess.DEVNULL,
            )
            os.remove(converted_file_path)
            os.rename(
                os.path.join(OUTPUT_PATH, FILE_NAME, FILE_NAME + ".24bit.wav"),
                converted_file_path,
            )
        else:
            subprocess.run(
                [
                    "sox",
                    FILE_PATH,
                    "--show-progress",
                    "-b",
                    "24",
                    converted_file_path,
                    "rate",
                    "-v",
                    "-a",
                    "-I",
                    "-s",
                    "44100",
                ],
                check=True,
    			stdout = subprocess.DEVNULL,
    			stderr = subprocess.DEVNULL,
            )
        BIT_DEPTH = 24
    else:
        if (
            FILE_EXTENSION == ".wav" or FILE_EXTENSION == ".wave"
        ) and SAMPLE_RATE == 44100:
            print("No conversion needed.")
        else:
            if FILE_PATH == converted_file_path:
                subprocess.run(
                    [
                        "sox",
                        FILE_PATH,
                        "--show-progress",
                        "--no-dither",
                        os.path.join(
                            OUTPUT_PATH, FILE_NAME, FILE_NAME + ".44100Hz.wav"
                        ),
                        "rate",
                        "-v",
                        "-a",
                        "-I",
                        "-s",
                        "44100",
                    ],
                    check=True,
        			stdout = subprocess.DEVNULL,
        			stderr = subprocess.DEVNULL,
                )
                os.remove(converted_file_path)
                os.rename(
                    os.path.join(OUTPUT_PATH, FILE_NAME, FILE_NAME + ".44100Hz.wav"),
                    converted_file_path,
                )
            else:
                subprocess.run(
                    [
                        "sox",
                        FILE_PATH,
                        "--show-progress",
                        "--no-dither",
                        converted_file_path,
                        "rate",
                        "-v",
                        "-a",
                        "-I",
                        "-s",
                        "44100",
                    ],
                    check=True,
        			stdout = subprocess.DEVNULL,
        			stderr = subprocess.DEVNULL,
                )


def split_stems():
    print("spliting using " + MODEL_NAME + " on " + DEVICE)
    if BIT_DEPTH == 24:
        demucs.separate.main([
                            "--int24",
                            "-n",
                            MODEL_NAME,
                            "--shifts",
                            MODEL_SHIFTS,
                            "-d",
                            DEVICE,
                            FILE_PATH,
                            "-o",
                            f"{OUTPUT_PATH}/{FILE_NAME}"
            ])
    else:
        demucs.separate.main([ "-n",
                MODEL_NAME,
                "--shifts",
                MODEL_SHIFTS,
                "-d",
                DEVICE,
                FILE_PATH,
                "-o",
                f"{OUTPUT_PATH}/{FILE_NAME}"])


def create_stem():
    print("Creating stem file " + FILE_NAME)
    import ni_stem
    stems = [
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/drums.wav",
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/bass.wav",
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/other.wav",
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/vocals.wav",
    ]
    mixdown = f"{OUTPUT_PATH}/{FILE_NAME}/{FILE_NAME}.wav"
    tags =  f"{OUTPUT_PATH}/{FILE_NAME}/tags.json"
    metadata = "metadata.json"
    creator = ni_stem.StemCreator(mixdown, stems, FORMAT, metadata, tags)
    creator.save()

def create_stem_old():
    print("Creating stem file " + FILE_NAME)
    os.chdir(INSTALL_DIR)

    stem_args = [PYTHON_EXEC, "ni-stem/ni-stem", "create", "-s"]
    stem_args += [
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/drums.wav",
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/bass.wav",
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/other.wav",
        f"{OUTPUT_PATH}/{FILE_NAME}/{MODEL_NAME}/{FILE_NAME}/vocals.wav",
    ]
    stem_args += [
        "-x",
        f"{OUTPUT_PATH}/{FILE_NAME}/{FILE_NAME}.wav",
        "-t",
        f"{OUTPUT_PATH}/{FILE_NAME}/tags.json",
        "-m",
        "metadata.json",
        "-f",
        FORMAT,
    ]

    subprocess.run(stem_args,
			stdout = subprocess.DEVNULL,
			stderr = subprocess.DEVNULL,)


# SETUP


def setup():
    for package in REQUIRED_PACKAGES:
        if not shutil.which(package):
            print(f"Please install {package} before running Stemgen.")
            sys.exit(2)

    if (
        subprocess.run(
            [PYTHON_EXEC, "-m", "demucs", "-h"], capture_output=True, text=True
        ).stdout.strip()
        == ""
    ):
        print("Please install demucs before running Stemgen.")
        sys.exit(2)

    if not os.path.exists(OUTPUT_PATH):
        os.mkdir(OUTPUT_PATH)

    global BASE_PATH, FILE_EXTENSION
    BASE_PATH = os.path.basename(INPUT_PATH)
    FILE_EXTENSION = os.path.splitext(BASE_PATH)[1]

    if FILE_EXTENSION not in SUPPORTED_FILES:
        print("Invalid input file format. File should be one of:", SUPPORTED_FILES)
        sys.exit(1)

    setup_file()
    get_bit_depth()
    get_sample_rate()
    get_cover(FILE_EXTENSION, FILE_PATH, OUTPUT_PATH, FILE_NAME)
    get_metadata(FILE_PATH, OUTPUT_PATH, FILE_NAME)
    convert()



def get_bit_depth():
  
    global BIT_DEPTH

    if FILE_EXTENSION == ".flac":
        BIT_DEPTH = int(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a",
                    "-show_entries",
                    "stream=bits_per_raw_sample",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    FILE_PATH,
                ]
            )
        )
    else:
        BIT_DEPTH = int(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a",
                    "-show_entries",
                    "stream=bits_per_sample",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    FILE_PATH,
                ]
            )
        )



def get_sample_rate():

    global SAMPLE_RATE

    SAMPLE_RATE = int(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=sample_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                FILE_PATH,
            ]
        )
    )


def strip_accents(text):
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore")
    text = text.decode("utf-8")
    return str(text)


def setup_file():
    global FILE_NAME, INPUT_DIR, FILE_PATH
    FILE_NAME = strip_accents(BASE_PATH.removesuffix(FILE_EXTENSION))
    INPUT_DIR = os.path.join(PROCESS_DIR, os.path.dirname(INPUT_PATH))

    if not os.path.exists(f"{OUTPUT_PATH}/{FILE_NAME}"):
        os.mkdir(f"{OUTPUT_PATH}/{FILE_NAME}")

    shutil.copy(INPUT_PATH, f"{OUTPUT_PATH}/{FILE_NAME}/{FILE_NAME}{FILE_EXTENSION}")
    FILE_PATH = f"{OUTPUT_PATH}/{FILE_NAME}/{FILE_NAME}{FILE_EXTENSION}"


def clean_dir():
    print("Cleaning...")

    os.chdir(OUTPUT_PATH)

    if os.path.isfile(os.path.join(OUTPUT_PATH, f"{FILE_NAME}.stem.m4a")):
        os.remove(os.path.join(OUTPUT_PATH, f"{FILE_NAME}.stem.m4a"))

    if os.path.isfile(os.path.join(OUTPUT_PATH, FILE_NAME, f"{FILE_NAME}.stem.m4a")):
        os.rename(
            os.path.join(OUTPUT_PATH, FILE_NAME, f"{FILE_NAME}.stem.m4a"),
            os.path.join(OUTPUT_PATH, f"{FILE_NAME}.stem.m4a"),
        )

    try:
        shutil.rmtree(os.path.join(OUTPUT_PATH, FILE_NAME))
    except PermissionError:
        print(
            f"Permission error encountered. Directory {os.path.join(OUTPUT_PATH, FILE_NAME)} might still be in use."
        )

    print("Done.")


if __name__ == "__main__":
    if LOOP:
        INPUT_PATHS = filedialog.askopenfilenames(title='.mp3')        
        while INPUT_PATHS is not None and len(INPUT_PATHS)>0:
            for INPUT_PATH in INPUT_PATHS:
                print(os.path.basename(INPUT_PATH))
                
                OUTPUT_PATH = os.path.dirname(INPUT_PATH) + "/"
                BASE_PATH = os.path.basename(INPUT_PATH)
                FILE_EXTENSION = os.path.splitext(BASE_PATH)[1]
                FILE_NAME = strip_accents(BASE_PATH.removesuffix(FILE_EXTENSION))
                
                
                if INPUT_PATH.endswith(".stem.m4a"):
                    print("skipping! already a stem.")
                    print("")
                elif os.path.isfile(os.path.join(OUTPUT_PATH, f"{FILE_NAME}.stem.m4a")) and not OVERWRITE_EXISTING:
                    print("skipping! a stem exist for this file")
                    print("")
                else:
                    os.chdir(PROCESS_DIR)    
                    setup()
                    split_stems()
                    create_stem()
                    clean_dir()
                    print("")
                
            INPUT_PATHS = filedialog.askopenfilenames(title='.mp3')
    else:
        os.chdir(PROCESS_DIR)
        setup()
        split_stems()
        create_stem()
        clean_dir()

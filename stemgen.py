import argparse
import os
import shutil
import sys
import subprocess
from pathlib import Path
import unicodedata
import traceback
import torch
import demucs.separate
from metadata import get_cover, get_metadata
from tkinter import filedialog

from nistem import StemCreator

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


DEVICE = (
    ("cuda" if torch.cuda.is_available() else (
    "mps" if torch.backends.mps.is_available() else "cpu"))
)

class StemGen(QObject):
    song_processing = pyqtSignal(str)
    counts = pyqtSignal(str, int, int, int, int)
    details_update = pyqtSignal(str)
    
    def __init__(self):
        super(StemGen, self).__init__()
        
        self.supported_files = [".wave", ".wav", ".aiff", ".aif", ".flac", ".mp3"]
        self.required_packages = ["ffmpeg", "sox"]
        
        self.model_name = "htdemucs"
        self.model_shifts = "1"
        self.overwrite_existing = False
        
        self.tracks = []
        self.processed_tracks = []
        self.skipped_tracks = []
        self.failed_tracks = []
        self.errors = []
        
        
    @property
    def track_count(self):
        return len(self.tracks)
        
        
    @property
    def processed_track_count(self):
        return len(self.processed_tracks)
    
    
    @property
    def skipped_track_count(self):
        return len(self.skipped_tracks)
    
    
    @property
    def failed_track_count(self):
        return len(self.failed_tracks)
       
 
    def run(self, tracks):
        try:
            self.setup()
        except Exception as exc:
            print(traceback.format_exc())
            self.emit_error(exc)
            return
            
        self.tracks = tracks
        if self.tracks is not None and len(tracks)>0:
            for track in self.tracks:
                directory = os.path.dirname(track) + "/"
                filename = os.path.basename(track)
                filename_extension = os.path.splitext(filename)[1]
                filename_without_extension = filename.removesuffix(filename_extension)
                self.song_processing.emit(filename_without_extension)
                self.update_track_counts_ui("processing")
                if track.endswith(".stem.m4a"):
                    self.skipped_tracks.append(filename_without_extension)
                    self.update_track_counts_ui("processing - skipping (already a stem)")
                    
                elif os.path.isfile(os.path.join(directory, f"{filename_without_extension}.stem.m4a")) and not self.overwrite_existing:
                    self.skipped_tracks.append(filename_without_extension)
                    self.update_track_counts_ui("processing - skipping (already stemmed)")
                    
                else:
                    try:
                        self.update_track_counts_ui("Processing - preparing")
                        copied_track, bit_depth = self.prepare(track, directory, filename, filename_extension, filename_without_extension)
                        self.update_track_counts_ui("Processing - splitting using " + DEVICE)
                        self.split_stems(copied_track, directory, filename, filename_extension, filename_without_extension, bit_depth)
                        self.update_track_counts_ui("Processing - saving")
                        self.create_stem(directory, filename, filename_extension, filename_without_extension)
                        self.update_track_counts_ui("Processing - cleaning")
                        self.clean_dir(directory, filename_without_extension)
                        self.processed_tracks.append(filename_without_extension)
                        self.update_track_counts_ui("Processing - done")
                    except Exception as exc:
                        print(traceback.format_exc())
                        self.emit_error(exc)
                        self.failed_tracks.append(filename_without_extension)
                        self.update_track_counts_ui("Processing - error")
            self.print_report()
                
    
    def print_report(self):
        self.update_track_counts_ui("Done !")
        self.song_processing.emit("")
        details = ""
        
        if self.failed_track_count>0:
            details += "Processed Tracks:"
            for track in self.failed_tracks:
                details += "\n\t" + track
            details +="\n"
            
        if len(self.errors)>0:
            details += "Errors:"
            for error in self.errors:
                details += "\n\t" + error
            details +="\n"
                
        if self.processed_track_count>0:
            details += "Processed Tracks:"        
            for track in self.processed_tracks:
                details += "\n\t" + track
            details +="\n"
        self.details_update.emit(details)
            
        
    def emit_error(self, error:str):
        self.errors.append(error)
        self.details_update.emit(', '.join(str(x) for x in self.errors)  )
    
    
    def update_track_counts_ui(self, message):
        print(message)
        self.counts.emit(message, self.track_count, self.processed_track_count, self.skipped_track_count, self.failed_track_count)  
    

    def convert(self, copied_track, directory, filename, filename_extension, filename_without_extension, bit_depth, sample_rate):
        # We downsample to 44.1kHz to avoid problems with the separation software
        # because the models are trained on 44.1kHz audio files

        # QUALITY            WIDTH  REJ dB   TYPICAL USE
        # -v  very high      95%     175     24-bit mastering

        # -M/-I/-L     Phase response = minimum/intermediate/linear(default)
        # -s           Steep filter (band-width = 99%)
        # -a           Allow aliasing above the pass-band


        converted_file_path = os.path.join(directory, filename_without_extension, filename_without_extension + ".wav")

        if bit_depth == 32:
            # Downconvert to 24-bit
            if copied_track == converted_file_path:
                subprocess.run(
                    [
                        "sox",
                        copied_track,
                        "--show-progress",
                        "-b",
                        "24",
                        os.path.join(directory, filename_without_extension, filename_without_extension + ".24bit.wav"),
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
                    os.path.join(directory, filename_without_extension, filename_without_extension + ".24bit.wav"),
                    converted_file_path,
                )
            else:
                subprocess.run(
                    [
                        "sox",
                        copied_track,
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
                filename_extension == ".wav" or filename_extension == ".wave"
            ) and sample_rate == 44100:
                pass
                # No conversion needed.
            else:
                if copied_track == converted_file_path:
                    subprocess.run(
                        [
                            "sox",
                            copied_track,
                            "--show-progress",
                            "--no-dither",
                            os.path.join(
                                directory, filename_without_extension, filename_without_extension + ".44100Hz.wav"
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
                        os.path.join(directory, filename_without_extension, filename_without_extension + ".44100Hz.wav"),
                        converted_file_path,
                    )
                else:
                    subprocess.run(
                        [
                            "sox",
                            copied_track,
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


    def split_stems(self, copied_track, directory, filename, filename_extension, filename_without_extension, bit_depth):
        if bit_depth == 24:
            demucs.separate.main([
                                "--int24",
                                "-n",
                                self.model_name,
                                "--shifts",
                                self.model_shifts,
                                "-d",
                                DEVICE,
                                copied_track,
                                "-o",
                                f"{directory}/{filename_without_extension}"
                ])
        else:
            demucs.separate.main([ "-n",
                    self.model_name,
                    "--shifts",
                    self.model_shifts,
                    "-d",
                    DEVICE,
                    copied_track,
                    "-o",
                    f"{directory}/{filename_without_extension}"])


    def create_stem(self, directory, filename, filename_extension, filename_without_extension):
        stems = [
            f"{directory}/{filename_without_extension}/{self.model_name}/{filename_without_extension}/drums.wav",
            f"{directory}/{filename_without_extension}/{self.model_name}/{filename_without_extension}/bass.wav",
            f"{directory}/{filename_without_extension}/{self.model_name}/{filename_without_extension}/other.wav",
            f"{directory}/{filename_without_extension}/{self.model_name}/{filename_without_extension}/vocals.wav",
        ]
        mixdown = f"{directory}/{filename_without_extension}/{filename_without_extension}.wav"
        tags =  f"{directory}/{filename_without_extension}/tags.json"
        metadata = {
          "mastering_dsp": {
            "compressor": {
              "enabled": False,
              "ratio": 3,
              "output_gain": 0.5,
              "release": 0.300000011920929,
              "attack": 0.003000000026077032,
              "input_gain": 0.5,
              "threshold": 0,
              "hp_cutoff": 300,
              "dry_wet": 50
            },
            "limiter": {
              "enabled": False,
              "release": 0.05000000074505806,
              "threshold": 0,
              "ceiling": -0.3499999940395355
            }
          },
          "version": 1,
          "stems": [
            {"color": "#009E73", "name": "Drums"},
            {"color": "#D55E00", "name": "Bass"},
            {"color": "#CC79A7", "name": "Other"},
            {"color": "#56B4E9", "name": "Vox"}
          ]
        }
        creator = StemCreator(mixdown, stems, "alac", metadata, tags)
        creator.save()


    def setup(self):
        for package in self.required_packages:
            if not shutil.which(package):
                error = f"Please install {package} before running Stemgen."
                if not (getattr(sys, 'frozen', False)):# and hasattr(sys, '_MEIPASS')):
                    # only report if not in pyinstaller
                    raise Exception(error)


    def prepare(self, track:str, directory:str, filename:str, filename_extension:str, filename_without_extension:str):
        if not os.path.exists(directory):
            os.mkdir(directory)
     
        if filename_extension not in self.supported_files:
            raise Exception("Invalid input file format. File should be one of:", self.supported_files)
            
        if not os.path.exists(f"{directory}/{filename_without_extension}"):
            os.mkdir(f"{directory}/{filename_without_extension}")

        copied_track = f"{directory}/{filename_without_extension}/{filename}"
        shutil.copy(track, copied_track)

        bit_depth = self.get_bit_depth(copied_track, filename_extension)
        sample_rate = self.get_sample_rate(copied_track)
        get_cover(filename_extension, track, directory, filename_without_extension)
        get_metadata(track, directory, filename_without_extension)
        self.convert(copied_track, directory, filename, filename_extension, filename_without_extension, bit_depth, sample_rate)
        return copied_track, bit_depth


    def get_bit_depth(self, file_path, filename_extension):
        if filename_extension == ".flac":
            return int(
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
                        file_path,
                    ]
                )
            )
        else:
            return int(
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
                        file_path,
                    ]
                )
            )



    def get_sample_rate(self, filepath):
        return int(
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
                    filepath,
                ]
            )
        )


    def clean_dir(self, directory, filename_without_extension):

        #os.chdir(directory)

        if os.path.isfile(os.path.join(directory, f"{filename_without_extension}.stem.m4a")):
            os.remove(os.path.join(directory, f"{filename_without_extension}.stem.m4a"))

        if os.path.isfile(os.path.join(directory, filename_without_extension, f"{filename_without_extension}.stem.m4a")):
            os.rename(
                os.path.join(directory, filename_without_extension, f"{filename_without_extension}.stem.m4a"),
                os.path.join(directory, f"{filename_without_extension}.stem.m4a"),
            )

        try:
            shutil.rmtree(os.path.join(directory, filename_without_extension))
        except PermissionError:
            raise Exception(
                f"Permission error encountered. Directory {os.path.join(directory, filename_without_extension)} might still be in use."
            )








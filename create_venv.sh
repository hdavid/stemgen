#!/bin/bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -U demucs
python3 -m pip install mutagen


#!/bin/zsh

# create venv if does not exist
if [ ! -d "venv" ]; then
  ./create_venv.sh
fi

source venv/bin/activate
rm -rf dist
rm -rf build
rm -f StemGenApp.spec

# 
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    add_data="--add-data=GPAC_linux/*:."
elif [[ "$OSTYPE" == "darwin"* ]]; then
    add_data="--add-data=GPAC_mac/*:."
else
   add_data="--add-data=GPAC_win/*:."
fi

pyinstaller --noconfirm --clean  -i icons/StemGen.icns ${add_data} --add-data="venv/lib/python3.12/site-packages/demucs/remote/*:demucs/remote/" --windowed StemGenApp.py

deactivate
#!/bin/bash

DIR="$(dirname "$(readlink "$0")")"
cd $DIR

source venv/bin/activate
python3 StemGenApp.py

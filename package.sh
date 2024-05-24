rm -rf dist
rm -rf build

./venv/bin/pyinstaller --noconfirm --clean --paths ./venv/lib/python3.12/site-packages  -i icons/stemgen.icns --windowed stemgen.py

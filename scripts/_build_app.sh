#!/usr/bin/env bash
# Single-source-of-truth Nuitka build for StemGen on macOS.
#
# This is the only build path. PyInstaller (package.sh) and cx_Freeze
# (setup.py) were dropped when the project moved to the Track Kommander
# build convention — see git log if you need them back.
#
# Holds an exclusive lock for the entire build via an atomic ``mkdir`` mutex
# so two concurrent invocations (e.g. a backgrounded build + a manual
# `make build` from a terminal) can never race on the dist tree.
#
# Args (all optional, forwarded to nuitka):
#   $@   extra flags
#
# Required env (set by the Makefile):
#   APP_NAME       e.g. "StemGen"
#   ENTRY          e.g. src/StemGenApp.py
#   VENV_PY        e.g. .venv/bin/python
#   DIST           e.g. dist
#
set -euo pipefail

# ── Inputs ──────────────────────────────────────────────────────────────────
APP_NAME="${APP_NAME:?APP_NAME is required}"
ENTRY="${ENTRY:?ENTRY is required}"
VENV_PY="${VENV_PY:?VENV_PY is required}"
DIST="${DIST:?DIST is required}"

BUNDLE="$DIST/$APP_NAME.app"
LOCK="$DIST.lock"
# Must match BUNDLE_ID in the Makefile / Info.plist consumers.
BUNDLE_ID="com.stemgen.app"

# ── Sign-mode banner ────────────────────────────────────────────────────────
# Print the chosen signing path up-front so a long Nuitka run doesn't end
# in a surprise. Wiring: Makefile auto-includes .env.local when present and
# exports its keys → DEVELOPER_ID_APP becomes visible here.
if [ -n "${DEVELOPER_ID_APP:-}" ]; then
    if [ -n "${NOTARY_APPLE_ID:-}" ] && [ -n "${NOTARY_TEAM_ID:-}" ] \
        && [ -n "${NOTARY_PASSWORD:-}" ]; then
        echo "▶ sign mode: Developer ID + notarize"
    else
        echo "▶ sign mode: Developer ID (notarization skipped — NOTARY_* incomplete)"
    fi
else
    echo "▶ sign mode: ad-hoc  (drop a .env.local with DEVELOPER_ID_APP=… to enable Developer ID)"
fi

# ── Build mutex ─────────────────────────────────────────────────────────────
# ``mkdir`` is atomic on POSIX filesystems — either we create the lockdir
# or someone else already has. Far more reliable than a flag-file check
# because there's no read-modify-write window.
mkdir -p "$(dirname "$DIST")"
if ! mkdir "$LOCK" 2>/dev/null; then
    other_pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -z "$other_pid" ]; then
        # No pid recorded: either another instance is in the tiny window
        # between mkdir and its pid write, or a lock was left corrupt. Never
        # steal it — a stolen live lock lets two builds run concurrently, and
        # each starts with `rm -rf $DIST`, destroying the other's output.
        echo "✗ a build lock exists but records no pid (another build may be starting)" >&2
        echo "  if you are SURE no build is running:  rm -rf '$LOCK'" >&2
        exit 1
    fi
    if kill -0 "$other_pid" 2>/dev/null; then
        echo "✗ another Nuitka build is in progress (pid $other_pid)" >&2
        echo "  wait for it to finish, or:  kill $other_pid && rm -rf '$LOCK'" >&2
        exit 1
    fi
    echo "  removing stale lock from dead pid $other_pid"
    rm -rf "$LOCK"
    if ! mkdir "$LOCK" 2>/dev/null; then
        echo "✗ lost the lock race to another build starting at the same time" >&2
        exit 1
    fi
fi
echo "$$" > "$LOCK/pid"

# Remove the lock on exit ONLY if we still own it. An unconditional rm would
# let an instance that took over a (wrongly presumed stale) lock delete it
# when it exits, leaving the still-running original build unprotected.
_cleanup_lock() {
    if [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ]; then
        rm -rf "$LOCK"
    fi
}
trap _cleanup_lock EXIT INT TERM

# ── Wipe stale outputs ──────────────────────────────────────────────────────
# Now that we hold the lock, no other build can be writing into $DIST.
rm -rf "$DIST"
mkdir -p "$DIST"

# ── Nuitka flags ────────────────────────────────────────────────────────────
# Notable points:
#   - demucs resolves model classes by name (demucs.htdemucs.HTDemucs is
#     looked up from the checkpoint's pickled `klass`), so the whole package
#     is force-included; --include-package-data=demucs ships remote/files.txt
#     + the model .yaml files that demucs.pretrained reads at runtime. The
#     model weights themselves are downloaded to ~/.cache/torch on first run,
#     exactly as when running from source.
#   - torch is compiled in as a normal dependency (Nuitka's package config
#     handles its dylibs). torch/include is header payload nobody needs at
#     runtime — dropping it saves ~50 MB.
#   - Optional accelerators (xformers, triton) and the ML zoo that torch /
#     demucs / dora reference in optional code paths are excluded explicitly
#     because Nuitka's transitive analysis would otherwise pull them in.
#   - All Qt subsystems we don't touch (WebEngine, Multimedia, Bluetooth, …)
#     are excluded so the bundle stays small.
#   - GPAC ships as a data dir with its layout intact: mp4box links
#     @executable_path/lib/libgpac.dylib, so GPAC_mac/lib must stay next to
#     it. runtime.mp4box_path() resolves it relative to the launcher.
NUITKA_FLAGS=(
    --mode=app
    --macos-app-name="$APP_NAME"
    --macos-app-icon=assets/icons/StemGen.icns
    --macos-signed-app-name="$BUNDLE_ID"
    --enable-plugin=pyqt5
    --include-package=demucs
    --include-package-data=demucs
    --include-package=julius
    --include-package=einops
    --include-package=lameenc
    --include-package=mutagen
    # demucs never calls torch.jit; make Nuitka's standalone default explicit
    # so the options-nanny plugin stops asking.
    --module-parameter=torch-disable-jit=yes
    --nofollow-import-to=einops.tests
    # torch only reaches sympy / jinja2 / _dynamo / _inductor through
    # torch.compile, which demucs never uses — verified by running the
    # pipeline with those imports blocked. Compiling them costs ~1000
    # C files and ~60 MB of bundle for nothing.
    --nofollow-import-to=sympy
    --nofollow-import-to=jinja2
    --nofollow-import-to=torch._dynamo
    --nofollow-import-to=torch._inductor
    --nofollow-import-to=xformers
    --nofollow-import-to=triton
    --nofollow-import-to=pandas
    --nofollow-import-to=matplotlib
    --nofollow-import-to=IPython
    --nofollow-import-to=jupyter
    --nofollow-import-to=PIL
    --nofollow-import-to=tkinter
    --nofollow-import-to=tensorflow
    --nofollow-import-to=jax
    --nofollow-import-to=flax
    --nofollow-import-to=sklearn
    --nofollow-import-to=transformers
    --nofollow-import-to=huggingface_hub
    --nofollow-import-to=onnx
    --nofollow-import-to=onnxruntime
    --nofollow-import-to=PyQt5.QtSql
    --nofollow-import-to=PyQt5.QtNetwork
    --nofollow-import-to=PyQt5.QtWebEngineCore
    --nofollow-import-to=PyQt5.QtWebEngineWidgets
    --nofollow-import-to=PyQt5.QtWebEngine
    --nofollow-import-to=PyQt5.QtMultimedia
    --nofollow-import-to=PyQt5.QtMultimediaWidgets
    --nofollow-import-to=PyQt5.QtBluetooth
    --nofollow-import-to=PyQt5.QtSensors
    --nofollow-import-to=PyQt5.QtPositioning
    --nofollow-import-to=PyQt5.QtLocation
    --nofollow-import-to=PyQt5.QtRemoteObjects
    --nofollow-import-to=PyQt5.QtDesigner
    --nofollow-import-to=PyQt5.QtQml
    --nofollow-import-to=PyQt5.QtQuick
    --nofollow-import-to=PyQt5.QtQuickWidgets
    --nofollow-import-to=PyQt5.QtWebSockets
    --nofollow-import-to=PyQt5.QtWebChannel
    --nofollow-import-to=PyQt5.QtSerialPort
    --nofollow-import-to=PyQt5.QtNfc
    --nofollow-import-to=PyQt5.QtXml
    --nofollow-import-to=PyQt5.QtXmlPatterns
    --nofollow-import-to=PyQt5.QtTest
    --nofollow-import-to=PyQt5.QtHelp
    --nofollow-import-to=PyQt5.QtOpenGL
    --nofollow-import-to=PyQt5.QtPrintSupport
    --nofollow-import-to=PyQt5.QtSvg
    --nofollow-import-to=PyQt5.QtDBus
    --no-deployment-flag=excluded-module-usage
    # torch/include is C++ header payload (~50 MB) nobody needs at runtime.
    # torch/bin must stay: torch.__init__ refuses to import without
    # bin/torch_shm_manager.
    --noinclude-data-files=torch/include/*
    # Nuitka drops .DS_Store from data dirs on every platform except macOS
    # (IncludedDataFiles.py: `if not isMacOS()`), so Finder droppings in
    # GPAC_mac/ and assets/ would otherwise ship inside the bundle.
    '--noinclude-data-files=*.DS_Store'
    --include-data-dir=GPAC_mac=GPAC_mac
    --include-data-files=LICENSE=LICENSE
    --output-dir="$DIST"
    --remove-output
    --assume-yes-for-downloads
)

# ── Compile ─────────────────────────────────────────────────────────────────
echo "▶ Nuitka build → $BUNDLE"
"$VENV_PY" -m nuitka "${NUITKA_FLAGS[@]}" "$ENTRY" "$@"

# ── Rename bundle ────────────────────────────────────────────────────────────
# Nuitka derives the .app name from the entry stem (StemGenApp.app);
# rename to the product name.
ENTRY_STEM="$(basename "$ENTRY" .py)"
if [ -d "$DIST/$ENTRY_STEM.app" ]; then
    rm -rf "$BUNDLE"
    mv "$DIST/$ENTRY_STEM.app" "$BUNDLE"
fi
[ -d "$BUNDLE" ] || { echo "✗ Nuitka did not produce a .app bundle in $DIST" >&2; exit 1; }

# ── Strip ───────────────────────────────────────────────────────────────────
echo "▶ stripping debug symbols"
/usr/bin/strip -S -x "$BUNDLE/Contents/MacOS/$ENTRY_STEM" 2>/dev/null || true
/usr/bin/find "$BUNDLE/Contents/MacOS" \
    \( -name '*.so' -o -name '*.dylib' \) \
    -exec /usr/bin/strip -S -x {} \; 2>/dev/null || true

# GPAC's mp4box must stay executable after the data-dir copy, or the stem
# muxing step fails silently (ni_stem swallows the subprocess output).
/bin/chmod +x "$BUNDLE/Contents/MacOS/GPAC_mac/mp4box"

# ── Codesign ────────────────────────────────────────────────────────────────
# If DEVELOPER_ID_APP is set we do a real Developer-ID sign with the hardened
# runtime + a secure timestamp + entitlements (notarizable). Otherwise we
# fall back to ad-hoc so the bundle still launches locally.
#
# Required env for Developer ID signing:
#   DEVELOPER_ID_APP     e.g. "Developer ID Application: ACME Inc (ABCDE12345)"
# Optional env for notarization (all three needed to actually notarize):
#   NOTARY_APPLE_ID      Apple ID email
#   NOTARY_TEAM_ID       10-char Team ID
#   NOTARY_PASSWORD      app-specific password from appleid.apple.com
ENTITLEMENTS="scripts/entitlements.plist"

if [ -n "${DEVELOPER_ID_APP:-}" ]; then
    echo "▶ codesigning with Developer ID: $DEVELOPER_ID_APP"
    # Nuitka bundles Qt framework binaries into Contents/MacOS/ with no
    # extension, and GPAC's mp4box is a bare executable — an extension-based
    # find misses them and they stay ad-hoc-signed → notarization rejects
    # the bundle. Detect every Mach-O regardless of name via `file -b`.
    echo "  • signing nested Mach-O binaries"
    /usr/bin/find "$BUNDLE/Contents" -type f ! -path '*/.??*/*' -print0 \
        | while IFS= read -r -d '' f; do
              if /usr/bin/file -b "$f" 2>/dev/null \
                    | /usr/bin/grep -q 'Mach-O'; then
                  /usr/bin/codesign --force --timestamp --options runtime \
                      --sign "$DEVELOPER_ID_APP" "$f" >/dev/null
              fi
          done

    echo "  • signing outer bundle (with entitlements)"
    /usr/bin/codesign --force --timestamp --options runtime \
        --entitlements "$ENTITLEMENTS" \
        --sign "$DEVELOPER_ID_APP" "$BUNDLE"

    echo "▶ verifying signature"
    /usr/bin/codesign --verify --deep --strict --verbose=2 "$BUNDLE"

    # ── Notarize ────────────────────────────────────────────────────────────
    if [ -n "${NOTARY_APPLE_ID:-}" ] \
        && [ -n "${NOTARY_TEAM_ID:-}" ] \
        && [ -n "${NOTARY_PASSWORD:-}" ]; then
        ZIP_FOR_NOTARY="$DIST/${APP_NAME}.notary.zip"
        echo "▶ zipping for notarization → $ZIP_FOR_NOTARY"
        /usr/bin/ditto -c -k --keepParent "$BUNDLE" "$ZIP_FOR_NOTARY"

        echo "▶ submitting to notarytool (this can take 1–5 min)"
        /usr/bin/xcrun notarytool submit "$ZIP_FOR_NOTARY" \
            --apple-id   "$NOTARY_APPLE_ID" \
            --team-id    "$NOTARY_TEAM_ID" \
            --password   "$NOTARY_PASSWORD" \
            --wait

        echo "▶ stapling notarization ticket"
        /usr/bin/xcrun stapler staple "$BUNDLE"
        rm -f "$ZIP_FOR_NOTARY"
    else
        echo "  ℹ notarization skipped — set NOTARY_APPLE_ID / NOTARY_TEAM_ID / NOTARY_PASSWORD"
    fi
else
    echo "▶ ad-hoc codesigning (DEVELOPER_ID_APP unset)"
    /usr/bin/codesign --force --deep --sign - "$BUNDLE" 2>&1 \
        | /usr/bin/grep -v "replacing existing signature" || true
fi

SIZE="$(/usr/bin/du -sh "$BUNDLE" | /usr/bin/awk '{print $1}')"
echo "✓ $BUNDLE  ($SIZE)"

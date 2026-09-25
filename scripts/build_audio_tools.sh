#!/usr/bin/env bash
# Build the ffmpeg / ffprobe / sox binaries StemGen ships inside the app.
#
#   scripts/build_audio_tools.sh mac   # → AUDIO_mac/  (arm64, macOS 11+)
#   scripts/build_audio_tools.sh win   # → AUDIO_win/  (x86_64, cross-built with mingw-w64)
#
# Everything is static — no Homebrew dylibs, no DLLs next to the .exe files —
# so the output folders drop straight into the bundle the same way GPAC_mac /
# GPAC_win do. Sources are pinned by sha256 and built in a scratch dir
# ($WORK, default: a mktemp dir), never in the repo.
#
# Only what StemGen actually asks of the tools is compiled in:
#   ffmpeg   decode wav/aiff/flac/mp3 → f32le (demucs.audio.AudioFile),
#            encode ALAC into .m4a (ni_stem), stream-copy the cover → .jpg
#            (metadata.get_cover)
#   ffprobe  bits_per_sample / sample_rate / stream info on those inputs
#   sox      read wav/aiff/flac/mp3, resample to 44.1 kHz (stemgen.convert)
#
# arm64 only on macOS: torch ships no x86_64 macOS wheels, so the app itself
# cannot run on Intel Macs.
#
# Licensing: this ffmpeg is LGPL (no --enable-gpl). sox + libmad are GPL-2.0;
# they ship as separate executables, with their licences and the exact source
# URLs in AUDIO_*/LICENSES/.
#
# Host requirements: Xcode CLT, cmake, and for `win` Homebrew's mingw-w64.
set -euo pipefail

TARGET="${1:?usage: $0 mac|win}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORK:-$(mktemp -d -t stemgen-audio-tools)}"
JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 8)"

FFMPEG_URL="https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz"
FFMPEG_SHA="8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e"
FLAC_URL="https://downloads.xiph.org/releases/flac/flac-1.5.0.tar.xz"
FLAC_SHA="f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920"
MAD_URL="https://codeberg.org/tenacityteam/libmad/releases/download/0.16.4/libmad-0.16.4.tar.gz"
MAD_SHA="0f6bfb36c554075494b5fc2c646d08de7364819540f23bab30ae73fa1b5cfe65"
# Backport for CMake 4 (same patch Homebrew's `mad` formula applies).
MAD_PATCH_URL="https://codeberg.org/tenacityteam/libmad/commit/326363f04e583b563f63941db3cf7f50e76aceb2.diff"
MAD_PATCH_SHA="8de5b7e7495ee789ecee07bacc93e2d2ce4be07c83e19c1181778d86fc7185ce"
SOX_URL="https://downloads.sourceforge.net/project/sox/sox/14.4.2/sox-14.4.2.tar.gz"
SOX_SHA="b45f598643ffbd8e363ff24d61166ccec4836fea6d3888881b8df53e3bb55f6c"

case "$TARGET" in
    mac)
        OUT="$REPO/AUDIO_mac"; EXE=""
        HOST_ARGS=()
        CMAKE_ARGS=(-DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0)
        export CC="clang -arch arm64 -mmacosx-version-min=11.0"
        export CFLAGS="-O2 -Wno-incompatible-function-pointer-types -Wno-implicit-function-declaration -Wno-int-conversion"
        export LDFLAGS="-arch arm64 -mmacosx-version-min=11.0"
        FFMPEG_PLATFORM=(--arch=arm64 --cc="$CC" --extra-ldflags="$LDFLAGS")
        ;;
    win)
        OUT="$REPO/AUDIO_win"; EXE=".exe"
        TRIPLE="x86_64-w64-mingw32"
        HOST_ARGS=(--host="$TRIPLE")
        CMAKE_ARGS=(-DCMAKE_SYSTEM_NAME=Windows -DCMAKE_C_COMPILER="$TRIPLE-gcc"
                    -DCMAKE_RC_COMPILER="$TRIPLE-windres"
                    -DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER)
        export CC="$TRIPLE-gcc"
        # FLAC__NO_DLL: link libFLAC's static symbols, not __declspec(dllimport).
        export CFLAGS="-O2 -DFLAC__NO_DLL"
        # Fully static: no libgcc / libwinpthread DLLs next to the .exe.
        export LDFLAGS="-static -static-libgcc"
        FFMPEG_PLATFORM=(--target-os=mingw32 --arch=x86_64 --enable-cross-compile
                         --cross-prefix="$TRIPLE-" --extra-ldflags="$LDFLAGS"
                         --disable-x86asm)
        ;;
    *) echo "usage: $0 mac|win" >&2; exit 2 ;;
esac

PREFIX="$WORK/$TARGET/prefix"
mkdir -p "$WORK/dl" "$WORK/$TARGET" "$PREFIX"
echo "▶ building $TARGET audio tools in $WORK/$TARGET → $OUT"

fetch() {  # fetch URL SHA → prints local path
    local url="$1" sha="$2" f="$WORK/dl/$(basename "$1")"
    [ -f "$f" ] || curl -fsSL --retry 3 -o "$f" "$url"
    echo "$sha  $f" | shasum -a 256 -c - >/dev/null \
        || { echo "✗ sha256 mismatch for $url" >&2; rm -f "$f"; exit 1; }
    echo "$f"
}

unpack() {  # unpack TARBALL → prints the extracted dir (fresh every run)
    # Read the top-level dir from the archive: libmad's tarball unpacks to
    # "libmad/", not "libmad-0.16.4/".
    local top; top="$(tar -tf "$1" | head -1 | cut -d/ -f1)"
    local dir="$WORK/$TARGET/$top"
    rm -rf "$dir"; tar -xf "$1" -C "$WORK/$TARGET"
    echo "$dir"
}

# ── libFLAC (static, no Ogg, no programs) ──────────────────────────────────
build_flac() {
    local src; src="$(unpack "$(fetch "$FLAC_URL" "$FLAC_SHA")")"
    cmake -S "$src" -B "$src/build" "${CMAKE_ARGS[@]}" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DBUILD_SHARED_LIBS=OFF -DWITH_OGG=OFF -DBUILD_CXXLIBS=OFF \
        -DBUILD_PROGRAMS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF \
        -DBUILD_DOCS=OFF -DINSTALL_MANPAGES=OFF >"$src/cmake.log" 2>&1
    cmake --build "$src/build" -j "$JOBS" >"$src/build.log" 2>&1
    cmake --install "$src/build" >>"$src/build.log" 2>&1
}

# ── libmad (static; sox's MP3 decoder) ─────────────────────────────────────
build_mad() {
    local src; src="$(unpack "$(fetch "$MAD_URL" "$MAD_SHA")")"
    patch -d "$src" -p1 <"$(fetch "$MAD_PATCH_URL" "$MAD_PATCH_SHA")" >/dev/null
    cmake -S "$src" -B "$src/build" "${CMAKE_ARGS[@]}" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DBUILD_SHARED_LIBS=OFF -DEXAMPLE=OFF >"$src/cmake.log" 2>&1
    cmake --build "$src/build" -j "$JOBS" >"$src/build.log" 2>&1
    cmake --install "$src/build" >>"$src/build.log" 2>&1
}

# ── sox (static, FLAC + MP3 via libmad, everything else off) ───────────────
build_sox() {
    local src; src="$(unpack "$(fetch "$SOX_URL" "$SOX_SHA")")"
    (
        cd "$src"
        if [ "$TARGET" = win ]; then
            # mingw-w64's UCRT makes FILE opaque, so rewind_pipe()'s _ptr/_base
            # poke no longer compiles. It only serves type detection on piped
            # input (`cat x.wav | sox - …`); StemGen always passes file paths.
            # Take sox's own "live without it" branch on UCRT.
            perl -0pi -e 's/(#elif defined _MSC_VER \|\| defined _WIN32)/#elif defined _UCRT\n  #define NO_REWIND_PIPE\n  (void)fp;\n$1/' src/formats.c
            grep -q '#elif defined _UCRT' src/formats.c \
                || { echo "✗ sox: UCRT rewind_pipe patch did not apply" >&2; exit 1; }
        fi
        # sox 14.4.2 is 2015 C: GCC 14+ turned these long-standing warnings
        # into errors (e.g. sox_sample_test.h calls fabs() without <math.h>).
        # Scoped to the unmodified sox sources only — the clang flags in the
        # mac CFLAGS above are the same thing for Apple's compiler.
        local sox_cflags="$CFLAGS"
        local sox_extra=()
        if [ "$TARGET" = win ]; then
            sox_cflags="$CFLAGS -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=int-conversion -fstack-protector-strong"
            # sox's own SSP probe adds -lssp, whose symbols clash with the
            # __stack_chk_* mingw-w64 already ships in libmingwex. Keep the
            # protection via the flag above, drop the probe.
            sox_extra=(--disable-stack-protector)
        fi
        CFLAGS="$sox_cflags" CPPFLAGS="-I$PREFIX/include" LDFLAGS="$LDFLAGS -L$PREFIX/lib" LIBS="-lm" \
        ./configure ${HOST_ARGS[@]+"${HOST_ARGS[@]}"} --prefix="$PREFIX" \
            ${sox_extra[@]+"${sox_extra[@]}"} \
            --disable-shared --enable-static --disable-openmp \
            --with-flac --with-mad --without-id3tag --without-lame \
            --without-twolame --without-oggvorbis --without-opus \
            --without-sndfile --without-amrwb --without-amrnb --without-wavpack \
            --without-png --without-ladspa --without-magic --without-ao \
            --without-pulseaudio --without-coreaudio --without-alsa --without-oss \
            --without-sunaudio --without-waveaudio --without-sndio \
            >configure.log 2>&1
        # Refuse to ship a sox that silently lost a format StemGen feeds it.
        grep -Eq '^flac\.+yes' configure.log || { echo "✗ sox: FLAC support not detected (see $src/configure.log)" >&2; exit 1; }
        grep -Eq '^ mad\.+yes'  configure.log || { echo "✗ sox: MP3 support not detected (see $src/configure.log)" >&2; exit 1; }
        # libtool drops a plain -static when linking the sox program, which
        # left sox.exe needing libssp-0.dll + libwinpthread-1.dll. libtool's
        # own -all-static fixes that; gcc rejects it, so it can only go in at
        # make time, not through configure.
        local make_ldflags="$LDFLAGS -L$PREFIX/lib"
        [ "$TARGET" = win ] && make_ldflags="$make_ldflags -all-static"
        make -j "$JOBS" LDFLAGS="$make_ldflags" >make.log 2>&1
        make install LDFLAGS="$make_ldflags" >>make.log 2>&1
    )
}

# ── ffmpeg / ffprobe (LGPL, audio + cover-copy only) ───────────────────────
build_ffmpeg() {
    local src; src="$(unpack "$(fetch "$FFMPEG_URL" "$FFMPEG_SHA")")"
    (
        cd "$src"
        ./configure --prefix="$PREFIX" "${FFMPEG_PLATFORM[@]}" \
            --disable-everything --disable-autodetect --disable-network \
            --disable-doc --disable-debug --disable-ffplay --disable-avdevice \
            --disable-swscale --enable-static --disable-shared \
            --enable-ffmpeg --enable-ffprobe --enable-avfilter --enable-swresample \
            --enable-protocol=file,pipe \
            --enable-demuxer=wav,w64,aiff,flac,mp3,mov,image2 \
            --enable-muxer=pcm_f32le,wav,ipod,mp4,mov,image2,mjpeg \
            --enable-decoder=pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,pcm_s16be,pcm_s24be,pcm_s32be,pcm_f32be,pcm_f64be,pcm_u8,flac,mp3,mp3float,alac,aac,mjpeg,png \
            --enable-encoder=alac,aac,pcm_f32le,pcm_s16le,pcm_s24le,pcm_s32le \
            --enable-parser=flac,mpegaudio,aac,mjpeg,png \
            --enable-filter=aresample,aformat,anull,atrim,null,format,abuffer,abuffersink,buffer,buffersink \
            >configure.log 2>&1
        make -j "$JOBS" >make.log 2>&1
        make install >>make.log 2>&1
    )
}

build_flac
build_mad
build_sox
build_ffmpeg

# ── Collect ────────────────────────────────────────────────────────────────
rm -rf "$OUT"; mkdir -p "$OUT/LICENSES"
for tool in ffmpeg ffprobe sox; do
    cp "$PREFIX/bin/$tool$EXE" "$OUT/"
done
if [ "$TARGET" = mac ]; then
    /usr/bin/strip -S -x "$OUT/ffmpeg" "$OUT/ffprobe" "$OUT/sox"
else
    "$TRIPLE-strip" "$OUT"/*.exe
fi
T="$WORK/$TARGET"
cp "$T/ffmpeg-9.0.2/COPYING.LGPLv2.1" "$OUT/LICENSES/ffmpeg-LGPL-2.1.txt"
cp "$T/sox-14.4.2/COPYING"            "$OUT/LICENSES/sox-GPL-2.0.txt"
cp "$T/libmad/COPYING"        "$OUT/LICENSES/libmad-GPL-2.0.txt"
cp "$T/flac-1.5.0/COPYING.Xiph"       "$OUT/LICENSES/libFLAC-BSD.txt"
cat >"$OUT/LICENSES/SOURCES.txt" <<EOF
Built by scripts/build_audio_tools.sh ($TARGET) from these unmodified sources
(libmad additionally gets the CMake 4 backport listed below):

ffmpeg 9.0.2   $FFMPEG_URL
               sha256 $FFMPEG_SHA   (LGPL-2.1; configured without --enable-gpl)
sox 14.4.2     $SOX_URL
               sha256 $SOX_SHA   (GPL-2.0)
libmad 0.16.4  $MAD_URL
               sha256 $MAD_SHA   (GPL-2.0)
               patch $MAD_PATCH_URL
libFLAC 1.5.0  $FLAC_URL
               sha256 $FLAC_SHA   (BSD-3-Clause)
EOF

echo "✓ $OUT"
ls -la "$OUT"

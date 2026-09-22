#!/usr/bin/env bash
# Build a static MP4Box for one arch from a GPAC checkout in ./src, e.g.
#   git clone --depth 1 --branch v26.07.0 https://github.com/gpac/gpac.git src
#   ./build_mp4box_macos.sh arm64 && ./build_mp4box_macos.sh x86_64
#   lipo -create build-arm64/bin/gcc/MP4Box build-x86_64/bin/gcc/MP4Box -output GPAC_mac/mp4box
# Run it from a scratch directory, not from the repo root.
set -euo pipefail
ARCH="$1"; S="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$S/build-$ARCH"; cp -R "$S/src" "$S/build-$ARCH"; cd "$S/build-$ARCH"
# Static MP4Box, no external libs beyond the macOS SDK (zlib comes from the SDK).
./configure --static-bin --isomedia-only --use-zlib=system --use-ssl=no --use-curl=no --use-ffmpeg=no --use-sdl=no --use-freetype=no --use-png=no --use-jpeg=no --use-nghttp2=no --use-lzma=no --use-ogg=no --use-vorbis=no --use-theora=no --use-a52=no --use-mad=no --use-faad=no --use-xvid=no --use-openjpeg=no --use-vtb=no --use-caption=no --use-libcaca=no --use-mpeghdec=no --use-hid=no --use-jack=no --use-ngtcp2=no --use-nghttp3=no \
    --extra-cflags="-arch $ARCH -mmacosx-version-min=11.0" >configure.log 2>&1
# configure drops --extra-ldflags on the floor for the final MP4Box link, so
# force the arch onto the linker here.
make -j16 LDFLAGS="-arch $ARCH -mmacosx-version-min=11.0" >make.log 2>&1
ls -la bin/gcc/MP4Box && file bin/gcc/MP4Box

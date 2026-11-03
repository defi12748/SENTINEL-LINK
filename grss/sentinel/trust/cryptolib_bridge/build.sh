#!/usr/bin/env bash
# Build NASA CryptoLib (libgcrypt backend) and the SENTINEL-LINK bridge.
#   CRYPTOLIB_SRC: CryptoLib checkout (default: NOS3's components/cryptolib or
#                  a fresh clone of github.com/nasa/CryptoLib)
# Output: $HOME/.sentinel/cryptolib_bridge
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HOME/.sentinel"
mkdir -p "$OUT"
SRC="${CRYPTOLIB_SRC:-$OUT/CryptoLib}"
if [ ! -f "$SRC/include/crypto.h" ]; then
  git init "$SRC"
  git -C "$SRC" remote add origin https://github.com/nasa/CryptoLib.git
  git -C "$SRC" fetch --depth 1 origin d4f91523b7f2f247b89bbde9e156cd8420e2cb86
  git -C "$SRC" checkout --detach FETCH_HEAD
fi
command -v cmake >/dev/null || sudo apt-get install -y cmake build-essential libgcrypt20-dev
mkdir -p "$SRC/build"
cd "$SRC/build"
# GCC >= 13 promotes a maybe-uninitialized warning in CryptoLib to an error.
cmake .. -DCRYPTO_LIBGCRYPT=ON -DKEY_INTERNAL=ON -DMC_INTERNAL=ON -DSA_INTERNAL=ON \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="-Wno-error=maybe-uninitialized" >/dev/null
make -j"$(nproc)" crypto >/dev/null
LIBDIR="$(dirname "$(find . -name 'libcryptolib.so' | head -1)")"
gcc -O2 -o "$OUT/cryptolib_bridge" "$HERE/bridge.c" -I"$SRC/include" \
    -L"$SRC/build/$LIBDIR" -lcryptolib -lgcrypt -Wl,-rpath,"$SRC/build/$LIBDIR"
echo "$OUT/cryptolib_bridge"

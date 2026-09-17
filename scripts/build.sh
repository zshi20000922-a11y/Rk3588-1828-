#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT/frontend"
npm ci
npm run build
cmake -S "$ROOT/native" -B "$ROOT/build/native" -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/build/native" -j


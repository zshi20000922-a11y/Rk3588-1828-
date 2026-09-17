#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET=/userdata/rk-edge-ai
adb shell "mkdir -p $TARGET $TARGET/bin $TARGET/data/uploads $TARGET/data/kv"
adb push "$ROOT/backend" "$TARGET/"
adb push "$ROOT/config" "$TARGET/"
adb push "$ROOT/frontend/dist" "$TARGET/frontend/"
adb push "$ROOT/scripts/board-start.sh" "$TARGET/"
adb push "$ROOT/pyproject.toml" "$TARGET/"
if [ -d "$ROOT/build/wheelhouse-aarch64" ]; then adb push "$ROOT/build/wheelhouse-aarch64" "$TARGET/"; fi
if [ -x "$ROOT/build/native-aarch64-gcc10/rk_inference_daemon" ]; then adb push "$ROOT/build/native-aarch64-gcc10/rk_inference_daemon" "$TARGET/bin/"; fi
adb shell "chmod +x $TARGET/board-start.sh $TARGET/bin/rk_inference_daemon 2>/dev/null || true"
echo "Deployed to $TARGET. Install the offline wheelhouse and start the service as documented."

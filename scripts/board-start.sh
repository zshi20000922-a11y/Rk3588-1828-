#!/bin/sh
set -eu
ROOT=/userdata/rk-edge-ai
export RK_PLATFORM_CONFIG="$ROOT/config/platform.board.yaml"
export PYTHONPATH="$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn rk_platform.app:app --host 0.0.0.0 --port 8080


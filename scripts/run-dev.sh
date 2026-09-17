#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT/backend"
exec python3 -m uvicorn rk_platform.app:app --host 0.0.0.0 --port 8080


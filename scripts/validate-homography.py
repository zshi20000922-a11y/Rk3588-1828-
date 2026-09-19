#!/usr/bin/env python3
"""Create the hardware-ROI safety gate from nine measured camera correspondences."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path, help="CSV with predicted_x,predicted_y,actual_x,actual_y")
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=float, default=160.0)
    args = parser.parse_args()
    with args.samples.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    errors = [math.hypot(float(row["predicted_x"]) - float(row["actual_x"]),
                         float(row["predicted_y"]) - float(row["actual_y"])) for row in rows]
    if len(errors) < 9:
        raise SystemExit("at least nine correspondence samples are required")
    ordered = sorted(errors)
    p95 = ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)]
    result = {
        "samples": len(errors),
        "p95_error_px": round(p95, 3),
        "mean_error_px": round(sum(errors) / len(errors), 3),
        "max_error_px": round(max(errors), 3),
        "limit_px": args.limit,
        "passed": p95 <= args.limit,
        "calibration_sha256": hashlib.sha256(args.calibration.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

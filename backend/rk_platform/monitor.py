from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


def _read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, PermissionError):
        return default


class SystemMonitor:
    def __init__(self) -> None:
        self._last_cpu: tuple[int, int] | None = None
        self._started = time.monotonic()

    def _cpu(self) -> float:
        values = [int(value) for value in _read("/proc/stat", "cpu 0 0 0 0").splitlines()[0].split()[1:]]
        total, idle = sum(values), values[3] + (values[4] if len(values) > 4 else 0)
        previous, self._last_cpu = self._last_cpu, (total, idle)
        if not previous or total == previous[0]:
            return 0.0
        return round(100 * (1 - (idle - previous[1]) / (total - previous[0])), 1)

    def snapshot(self) -> dict[str, Any]:
        mem = {}
        for line in _read("/proc/meminfo").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                mem[key] = int(value.strip().split()[0])
        total, available = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
        thermal = {}
        for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
            name = _read(str(zone / "type"))
            value = _read(str(zone / "temp"))
            if name and value.lstrip("-").isdigit():
                thermal[name] = round(int(value) / 1000, 1)
        npu_load = _read("/sys/kernel/debug/rknpu/load") or _read("/sys/devices/platform/fdab0000.npu/devfreq/fdab0000.npu/load")
        npu_freq = _read("/sys/devices/platform/fdab0000.npu/devfreq/fdab0000.npu/cur_freq")
        rk1828_online = Path("/dev/pcie-rkep-0000:01:00.0").exists() or any(Path("/dev").glob("pcie-rkep-*"))
        return {
            "timestamp": time.time(),
            "rk3588": {
                "cpu_percent": self._cpu(),
                "memory_total_mb": round(total / 1024, 1),
                "memory_used_mb": round((total - available) / 1024, 1),
                "load_average": list(os.getloadavg()),
                "temperatures_c": thermal,
                "npu": {"load_raw": npu_load or None, "frequency_hz": int(npu_freq) if npu_freq.isdigit() else None},
            },
            "rk1828": {
                "online": bool(rk1828_online),
                "utilization_kind": "inference_duty_cycle",
                "utilization_percent": None,
                "note": "No public hardware utilization counter; runtime duty cycle is reported by inference daemon.",
            },
            "uptime_seconds": round(time.monotonic() - self._started, 1),
        }


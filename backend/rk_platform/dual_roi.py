from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any


class DualRoiController:
    """Safe control-plane adapter for the exclusive dual-camera ROI demo."""

    def __init__(self, settings: dict[str, Any] | None):
        settings = settings or {}
        self.enabled = bool(settings.get("enabled", False))
        self.socket_path = str(settings.get("control_socket", "/run/rknn-dual-detector/control.sock"))
        self.detector_service = str(settings.get("detector_service", "/etc/init.d/S95rknn-dual-detector"))
        self.vision_service = str(settings.get("vision_service", "/etc/init.d/S96rk-vision-service"))
        self.timeout = float(settings.get("start_timeout_seconds", 15))
        self.validation_path = Path(str(settings.get(
            "validation_path", "/userdata/rknn-dual-detector/config/homography_validation.json")))
        self.mapping_p95_limit = float(settings.get("mapping_p95_limit_px", 160))
        self.require_validation = bool(settings.get("require_validation", True))
        self.expected_devices = settings.get("expected_devices", {
            "/dev/video44": "rkisp_mainpath",
            "/dev/video62": "rkisp_mainpath",
            "/dev/v4l-subdev2": "imx415",
            "/dev/v4l-subdev3": "rkisp-isp-subdev",
            "/dev/v4l-subdev4": "rkcif-mipi-lvds",
        })

    @staticmethod
    def _process_running(fragment: str) -> bool:
        result = subprocess.run(["pgrep", "-f", fragment], capture_output=True, timeout=2)
        return result.returncode == 0

    def _service(self, script: str, operation: str, timeout: float = 15) -> None:
        result = subprocess.run(["/bin/sh", script, operation], capture_output=True,
                                text=True, timeout=timeout)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(detail or f"{Path(script).name} {operation} failed")

    def _command(self, command: str) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(self.socket_path)
            client.sendall((command + "\n").encode())
            data = bytearray()
            while b"\n" not in data:
                chunk = client.recv(65536)
                if not chunk:
                    break
                data.extend(chunk)
        return json.loads(bytes(data).splitlines()[0])

    def preflight(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        for device, expected in self.expected_devices.items():
            path = Path(device)
            sys_name = Path("/sys/class/video4linux") / path.name / "name"
            try:
                actual = sys_name.read_text(encoding="utf-8").strip()
            except OSError:
                actual = ""
            ok = path.exists() and expected in actual
            checks.append({"device": device, "expected": expected, "actual": actual, "ok": ok})
        calibration = Path("/userdata/rknn-dual-detector/config/stereo_calibration.yaml")
        checks.append({"device": str(calibration), "expected": "calibration file",
                       "actual": "present" if calibration.is_file() else "missing",
                       "ok": calibration.is_file()})
        if self.require_validation:
            validation: dict[str, Any] = {}
            try:
                validation = json.loads(self.validation_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            samples = int(validation.get("samples", 0))
            p95 = float(validation.get("p95_error_px", float("inf")))
            valid = samples >= 9 and p95 <= self.mapping_p95_limit
            checks.append({"device": str(self.validation_path),
                           "expected": f">=9 samples and P95 <= {self.mapping_p95_limit:g} px",
                           "actual": f"samples={samples}, p95={p95:g}", "ok": valid})
        return {"ok": all(item["ok"] for item in checks), "checks": checks}

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"available": False, "active": False, "reason": "dual ROI demo is disabled"}
        preflight = self.preflight()
        active = Path(self.socket_path).exists() and self._process_running("rknn_dual_camera_detector")
        runtime: dict[str, Any] = {}
        error = ""
        if active:
            try:
                runtime = self._command("status")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                error = str(exc)
        stereo = runtime.get("stereo", {})
        return {
            "available": True,
            "active": active,
            "ready": bool(active and stereo.get("enabled") and not error),
            "preflight": preflight,
            "mode": stereo.get("mode", "INACTIVE"),
            "global_camera": stereo.get("global_camera", "cam0"),
            "roi_camera": stereo.get("roi_camera", "cam1"),
            "track_id": stereo.get("global_track_id", 0),
            "roi": stereo.get("roi", [0, 0, 640, 640]),
            "target_visible": bool(stereo.get("target_visible", False)),
            "mapping_error_px": stereo.get("mapping_error_px"),
            "frame_delta_ms": stereo.get("frame_delta_ms"),
            "match_confidence": stereo.get("match_confidence"),
            "projected_fallback": bool(stereo.get("projected_fallback_enabled", False)),
            "switch_ms": runtime.get("stereo_switch_ms", 0),
            "switches": runtime.get("stereo_switches", 0),
            "switch_failures": runtime.get("stereo_switch_failures", 0),
            "cameras": runtime.get("cameras", []),
            "pipeline_errors": runtime.get("pipeline_errors", 0),
            "error": error or stereo.get("last_error", ""),
            "runtime": runtime,
            "timestamp": time.time(),
        }

    def start(self) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("dual ROI demo is disabled")
        preflight = self.preflight()
        if not preflight["ok"]:
            raise RuntimeError("camera/media topology preflight failed")
        if self.status()["active"]:
            return self.status()
        self._service(self.vision_service, "stop")
        try:
            self._service(self.detector_service, "start")
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if Path(self.socket_path).exists():
                    status = self.status()
                    if status["ready"]:
                        return status
                time.sleep(0.1)
            raise RuntimeError("dual ROI detector did not become ready")
        except Exception:
            try:
                self._service(self.detector_service, "stop")
            finally:
                self._service(self.vision_service, "start")
            raise

    def stop(self) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("dual ROI demo is disabled")
        self._service(self.detector_service, "stop")
        self._service(self.vision_service, "start")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self._process_running("rk_vision_service"):
                break
            time.sleep(0.1)
        return self.status()

    def command(self, command: str) -> dict[str, Any]:
        if command not in {"unlock", "projected fallback on", "projected fallback off"}:
            raise ValueError("unsupported dual ROI command")
        if not self.status()["active"]:
            raise RuntimeError("dual ROI demo is not active")
        self._command(command)
        return self.status()

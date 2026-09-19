from __future__ import annotations

import json
import os
import re
import socket
import tempfile
from pathlib import Path
from typing import Any

import yaml


class VisionController:
    """Validated control-plane adapter for rk_vision_service."""

    def __init__(self, settings: dict[str, Any] | None):
        settings = settings or {}
        self.enabled = bool(settings.get("enabled", False))
        self.socket_path = str(settings.get("control_socket", "/run/rk-vision-service/control.sock"))
        self.config_path = Path(str(settings.get("config_path", "/userdata/rk-vision-service/config.yaml")))

    def _command(self, command: dict[str, Any]) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(self.socket_path)
            client.sendall((json.dumps(command) + "\n").encode())
            data = bytearray()
            while b"\n" not in data:
                chunk = client.recv(65536)
                if not chunk:
                    break
                data.extend(chunk)
        return json.loads(bytes(data).splitlines()[0])

    def _load(self) -> dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def _save_text(self, value: str) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".vision-", suffix=".yaml", dir=self.config_path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.config_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _replace_scalar(text: str, section: str, key: str, value: Any) -> str:
        """Replace one scalar without reformatting the service's restricted YAML."""
        rendered = "true" if value is True else "false" if value is False else str(value)
        lines = text.splitlines(keepends=True)
        in_section = False
        for index, line in enumerate(lines):
            if line and not line[0].isspace() and re.match(r"^[A-Za-z_][\w-]*:\s*", line):
                in_section = line.split(":", 1)[0] == section
                continue
            if in_section and re.match(rf"^\s+(?:-\s+)?{re.escape(key)}\s*:", line):
                ending = "\n" if line.endswith("\n") else ""
                prefix = line[:line.index(key)]
                lines[index] = f"{prefix}{key}: {rendered}{ending}"
                return "".join(lines)
        raise ValueError(f"missing {section}.{key} in vision config")

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"available": False, "reason": "vision control is disabled"}
        original_text = self.config_path.read_text(encoding="utf-8")
        config = yaml.safe_load(original_text)
        runtime = self._command({"command": "status"})
        motion, tracker = config.get("motion", {}), config.get("tracker", {})
        source = (config.get("sources") or [{}])[0]
        return {
            "available": True,
            "media_idle": bool(runtime.get("media_idle", False)),
            "media_state": "idle" if runtime.get("media_idle", False) else "active",
            "detection_enabled": not bool(runtime.get("paused", False)),
            "motion_enabled": bool(motion.get("enabled", False)),
            "motion_gate": bool(motion.get("gate_detection", False)),
            "tracking_enabled": bool(tracker.get("enabled", False)),
            "active_detect_fps": int(source.get("detect_fps", 1)),
            "idle_detect_fps": int(motion.get("idle_detect_fps", 1)),
            "runtime": runtime,
        }

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("vision control is disabled")
        allowed = {"detection_enabled", "motion_enabled", "motion_gate", "tracking_enabled",
                   "active_detect_fps", "idle_detect_fps"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported vision fields: {', '.join(sorted(unknown))}")
        original_text = self.config_path.read_text(encoding="utf-8")
        config = yaml.safe_load(original_text)
        motion, tracker = config.setdefault("motion", {}), config.setdefault("tracker", {})
        sources = config.setdefault("sources", [])
        if not sources:
            raise ValueError("vision config has no source")
        if "motion_enabled" in changes:
            motion["enabled"] = bool(changes["motion_enabled"])
            original_text = self._replace_scalar(original_text, "motion", "enabled", motion["enabled"])
        if "motion_gate" in changes:
            motion["gate_detection"] = bool(changes["motion_gate"])
            original_text = self._replace_scalar(original_text, "motion", "gate_detection", motion["gate_detection"])
        if "tracking_enabled" in changes:
            tracker["enabled"] = bool(changes["tracking_enabled"])
            original_text = self._replace_scalar(original_text, "tracker", "enabled", tracker["enabled"])
        if "active_detect_fps" in changes:
            value = int(changes["active_detect_fps"])
            if not 1 <= value <= 60:
                raise ValueError("active_detect_fps must be 1..60")
            sources[0]["detect_fps"] = value
            original_text = self._replace_scalar(original_text, "sources", "detect_fps", value)
        if "idle_detect_fps" in changes:
            value = int(changes["idle_detect_fps"])
            if not 1 <= value <= 15:
                raise ValueError("idle_detect_fps must be 1..15")
            motion["idle_detect_fps"] = value
            original_text = self._replace_scalar(original_text, "motion", "idle_detect_fps", value)
        soft_changed = any(key != "detection_enabled" for key in changes)
        if soft_changed:
            previous_text = self.config_path.read_text(encoding="utf-8")
            self._save_text(original_text)
            try:
                response = self._command({"command": "reload_soft_config"})
                if not response.get("ok"):
                    raise RuntimeError(response.get("error", "vision config reload failed"))
            except Exception:
                self._save_text(previous_text)
                try:
                    self._command({"command": "reload_soft_config"})
                except Exception:
                    pass
                raise
        if "detection_enabled" in changes:
            command = "resume_detection" if changes["detection_enabled"] else "pause_detection"
            response = self._command({"command": command})
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "vision detection control failed"))
        return self.status()

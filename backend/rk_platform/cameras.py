from __future__ import annotations

import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class CameraProvider(ABC):
    def __init__(self, camera_id: str, name: str, source: str):
        self.id, self.name, self.source = camera_id, name, source

    @abstractmethod
    def status(self) -> dict[str, Any]: ...

    @abstractmethod
    def snapshot(self, target: Path) -> Path: ...


class ImageCamera(CameraProvider):
    def status(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "provider": "image", "online": Path(self.source).is_file()}

    def snapshot(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.source, target)
        return target


class VideoCamera(CameraProvider):
    def status(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "provider": "video", "online": Path(self.source).is_file()}

    def snapshot(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-ss", "0", "-i", self.source, "-frames:v", "1", str(target)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return target


class RtspCamera(CameraProvider):
    def status(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "provider": "rtsp", "online": True,
                "stream_url": self.source, "note": "Browser playback requires the configured HLS/WebRTC gateway."}

    def snapshot(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-rtsp_transport", "tcp", "-i", self.source,
                        "-frames:v", "1", str(target)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return target


class CameraRegistry:
    def __init__(self, configs: list[dict[str, Any]]):
        providers = {"image": ImageCamera, "video": VideoCamera, "rtsp": RtspCamera}
        self.items: dict[str, CameraProvider] = {}
        for item in configs:
            cls = providers[item["provider"]]
            self.items[item["id"]] = cls(item["id"], item["name"], item["source"])

    def list(self) -> list[dict[str, Any]]:
        return [provider.status() for provider in self.items.values()]

    def capture(self, camera_id: str, directory: Path) -> Path:
        if camera_id not in self.items:
            raise KeyError(camera_id)
        return self.items[camera_id].snapshot(directory / f"{camera_id}-{int(time.time() * 1000)}.jpg")


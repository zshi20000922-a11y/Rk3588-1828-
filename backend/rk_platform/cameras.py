from __future__ import annotations

import shutil
import socket
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def build_preview_command(source: str, settings: dict[str, Any] | None = None) -> list[str]:
    settings = settings or {}
    backend = settings.get("backend", "ffmpeg")
    width = int(settings.get("width", 960))
    height = int(settings.get("height", 540))
    fps = int(settings.get("fps", 8))
    quality = int(settings.get("quality", 70))
    if backend == "gstreamer_mpp":
        return [
            "gst-launch-1.0", "-q", "rtspsrc", f"location={source}",
            f"latency={int(settings.get('latency_ms', 50))}", "protocols=tcp", "!",
            "rtph264depay", "!", "h264parse", "!", "mppvideodec",
            f"width={width}", f"height={height}", "!", "videorate", "!",
            f"video/x-raw,framerate={fps}/1", "!", "mppjpegenc", f"q-factor={quality}", "!",
            "fdsink", "fd=1", "sync=false",
        ]
    if backend != "ffmpeg":
        raise ValueError(f"unsupported camera preview backend: {backend}")
    ffmpeg_quality = max(2, min(31, round((100 - quality) * 0.29 + 2)))
    return [
        "ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", source,
        "-vf", f"fps={fps},scale={width}:{height}", "-q:v", str(ffmpeg_quality),
        "-f", "image2pipe", "-vcodec", "mjpeg", "-",
    ]


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
    def __init__(self, camera_id: str, name: str, source: str):
        super().__init__(camera_id, name, source)
        self._last_probe_at = 0.0
        self._last_probe_online = False

    def _probe(self) -> bool:
        """Probe the configured RTSP path, not only the shared server port."""
        now = time.monotonic()
        if now - self._last_probe_at < 2.0:
            return self._last_probe_online
        parsed = urlparse(self.source)
        online = False
        try:
            # A live GStreamer mount can wait for the next keyframe before it
            # answers DESCRIBE; the board uses a 25-frame GOP at 25 FPS.
            with socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 554), timeout=2.0) as client:
                client.settimeout(2.0)
                request = (f"DESCRIBE {self.source} RTSP/1.0\r\nCSeq: 1\r\n"
                           "Accept: application/sdp\r\nUser-Agent: rk-edge-ai-platform\r\n\r\n")
                client.sendall(request.encode("ascii"))
                status_line = client.recv(512).split(b"\r\n", 1)[0]
                online = status_line.startswith(b"RTSP/1.0 200")
        except (OSError, UnicodeError):
            pass
        self._last_probe_at, self._last_probe_online = now, online
        return online

    def status(self) -> dict[str, Any]:
        online = self._probe()
        return {"id": self.id, "name": self.name, "provider": "rtsp", "online": online,
                "stream_url": self.source, "note": "Browser preview is provided by the built-in MJPEG gateway."}

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

    def get(self, camera_id: str) -> CameraProvider:
        if camera_id not in self.items:
            raise KeyError(camera_id)
        return self.items[camera_id]

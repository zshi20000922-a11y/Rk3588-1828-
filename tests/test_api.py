import os
import socketserver
import threading
from pathlib import Path

os.environ.setdefault("RK_PLATFORM_CONFIG", str(Path(__file__).parents[1] / "config/platform.test.yaml"))

from fastapi.testclient import TestClient
from rk_platform.app import app
from rk_platform.cameras import RtspCamera, build_preview_command
from rk_platform.preview import extract_jpeg_frames
from rk_platform.vision import VisionController

TOKEN = {"Authorization": "Bearer test-token"}


def test_health_and_auth():
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/conversations").status_code == 401
        assert client.get("/api/v1/conversations", headers=TOKEN).status_code == 200


def test_conversation_lifecycle():
    with TestClient(app) as client:
        row = client.post("/api/v1/conversations", headers=TOKEN, json={"title": "test"}).json()
        conversation_id = row["id"]
        result = client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=TOKEN,
                             json={"text": "hello", "attachments": []})
        assert result.status_code == 200
        assert client.post(f"/api/v1/conversations/{conversation_id}/kv/swap", headers=TOKEN,
                           json={"direction": "out"}).status_code == 200
        assert client.delete(f"/api/v1/conversations/{conversation_id}", headers=TOKEN).status_code == 200


def test_tool_allowlist():
    with TestClient(app) as client:
        denied = client.post("/api/v1/tools/run_shell/execute", headers=TOKEN, json={"arguments": {}}).json()
        assert denied["error"] == "tool_not_allowed"
        status = client.post("/api/v1/tools/get_system_status/execute", headers=TOKEN, json={"arguments": {}}).json()
        assert status["ok"] is True


def test_vision_control_disabled_by_default():
    with TestClient(app) as client:
        status = client.get("/api/v1/vision/pipeline", headers=TOKEN)
        assert status.status_code == 200
        assert status.json()["available"] is False
        update = client.patch("/api/v1/vision/pipeline", headers=TOKEN,
                              json={"detection_enabled": False})
        assert update.status_code == 503


def test_shared_preview_status_is_observable():
    with TestClient(app) as client:
        status = client.get("/api/v1/cameras/preview/status", headers=TOKEN)
        assert status.status_code == 200
        assert status.json()["shared"] is True
        assert status.json()["backend"] == "ffmpeg"
        snapshot = client.get("/api/v1/system/snapshot", headers=TOKEN)
        assert snapshot.json()["camera_preview"]["shared"] is True


def test_vision_scalar_update_preserves_restricted_yaml_layout():
    source = "tracker:\n  enabled: true\nsources:\n  - id: cam0\n    detect_fps: 15\n"
    changed = VisionController._replace_scalar(source, "tracker", "enabled", False)
    changed = VisionController._replace_scalar(changed, "sources", "detect_fps", 10)
    assert changed == "tracker:\n  enabled: false\nsources:\n  - id: cam0\n    detect_fps: 10\n"


def test_preview_commands_are_explicit_and_hardware_backend_uses_mpp():
    source = "rtsp://127.0.0.1:8554/mosaic"
    software = build_preview_command(source, {"backend": "ffmpeg", "width": 640, "height": 360, "fps": 5})
    hardware = build_preview_command(source, {"backend": "gstreamer_mpp", "width": 960, "height": 540,
                                                       "fps": 8, "quality": 70, "latency_ms": 50})
    assert software[0] == "ffmpeg"
    assert "fps=5,scale=640:360" in software
    assert hardware[0] == "gst-launch-1.0"
    assert "mppvideodec" in hardware
    assert "mppjpegenc" in hardware
    assert "video/x-raw,framerate=8/1" in hardware


def test_jpeg_stream_parser_handles_noise_and_partial_frames():
    buffer = bytearray(b"noise\xff\xd8first\xff\xd9\xff\xd8partial")
    assert extract_jpeg_frames(buffer) == [b"\xff\xd8first\xff\xd9"]
    assert buffer == bytearray(b"\xff\xd8partial")
    buffer.extend(b"-rest\xff\xd9trailing")
    assert extract_jpeg_frames(buffer) == [b"\xff\xd8partial-rest\xff\xd9"]
    assert buffer == bytearray(b"g")


def test_camera_snapshot_requires_token_and_serves_only_camera_images():
    snapshot = Path("/tmp/rk-edge-ai-test/uploads/camera/test-frame.jpg")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b"\xff\xd8test\xff\xd9")
    with TestClient(app) as client:
        assert client.get("/api/v1/camera-snapshots/test-frame.jpg").status_code == 422
        response = client.get("/api/v1/camera-snapshots/test-frame.jpg?token=test-token")
        assert response.status_code == 200
        assert response.content == b"\xff\xd8test\xff\xd9"
        assert client.get("/api/v1/camera-snapshots/test-frame.txt?token=test-token").status_code == 404


def test_rtsp_status_checks_the_path_instead_of_only_the_port():
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            request = self.request.recv(1024)
            status = b"200 OK" if b"/camera-1 " in request else b"404 Not Found"
            self.request.sendall(b"RTSP/1.0 " + status + b"\r\nCSeq: 1\r\n\r\n")

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        assert RtspCamera("one", "one", f"rtsp://127.0.0.1:{port}/camera-1").status()["online"] is True
        assert RtspCamera("two", "two", f"rtsp://127.0.0.1:{port}/camera-2").status()["online"] is False

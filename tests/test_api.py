import os
from pathlib import Path

os.environ.setdefault("RK_PLATFORM_CONFIG", str(Path(__file__).parents[1] / "config/platform.test.yaml"))

from fastapi.testclient import TestClient
from rk_platform.app import app

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


from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .cameras import CameraRegistry, RtspCamera
from .config import load_config, resolve_path
from .database import Database, now_iso
from .dual_roi import DualRoiController
from .events import EventBus
from .experiments import ExperimentManager
from .inference import create_backend
from .monitor import SystemMonitor
from .preview import SharedMjpegGateway
from .tools import ToolRegistry
from .vision import VisionController


class ConversationCreate(BaseModel):
    title: str = "新对话"


class MessageCreate(BaseModel):
    text: str = ""
    attachments: list[str] = Field(default_factory=list)


class SwapRequest(BaseModel):
    direction: str


class ToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    confirmed: bool = False


class ExperimentCreate(BaseModel):
    name: str
    variables: dict[str, Any] = Field(default_factory=dict)


class VisionPipelinePatch(BaseModel):
    detection_enabled: bool | None = None
    motion_enabled: bool | None = None
    motion_gate: bool | None = None
    tracking_enabled: bool | None = None
    active_detect_fps: int | None = None
    idle_detect_fps: int | None = None
    roi_modes: dict[str, str] | None = None


class ProjectedFallbackRequest(BaseModel):
    enabled: bool = False


config = load_config()
db = Database(resolve_path(config, config["server"]["database"]))
events = EventBus()
monitor = SystemMonitor()
backend = create_backend(config)
cameras = CameraRegistry(config.get("cameras", []))
camera_preview = config.get("camera_preview", {})
preview_gateway = SharedMjpegGateway(camera_preview)
experiments = ExperimentManager(Path(config["_root"]), db, config)
tools = ToolRegistry(db)
vision = VisionController(config.get("vision_service"))
dual_roi = DualRoiController(config.get("dual_roi_demo"))
active_requests: dict[str, str] = {}
rk1828_requests: set[str] = set()


def platform_snapshot() -> dict[str, Any]:
    value = monitor.snapshot()
    value["rk1828"]["utilization_percent"] = 100.0 if rk1828_requests else 0.0
    value["rk1828"]["phase"] = "inference" if rk1828_requests else "idle"
    value["rk1828"]["active_requests"] = len(rk1828_requests)
    value["camera_preview"] = preview_gateway.status()
    value["dual_roi"] = dual_roi.status()
    return value


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = config["server"]["admin_token"]
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(401, "invalid admin token")


async def _system_tool(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": platform_snapshot()}


async def _model_tool(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "active": config["models"]["active"], "models": config["models"]["registry"]}


async def _camera_tool(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "cameras": cameras.list()}


async def _clear_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    conversation_id = arguments["conversation_id"]
    return await backend.control({"action": "clear", "conversation_id": conversation_id, "keep_system_prompt": True})


tools.register("get_system_status", _system_tool)
tools.register("get_model_context", _model_tool)
tools.register("get_camera_status", _camera_tool)
tools.register("clear_conversation", _clear_tool, confirmation=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    resolve_path(config, config["server"]["upload_dir"]).mkdir(parents=True, exist_ok=True)
    resolve_path(config, config["server"]["kv_dir"]).mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        await preview_gateway.close()


app = FastAPI(title="RK Heterogeneous Edge AI Platform", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    inference_ready = config["inference"]["backend"] != "rknn3" or Path(config["inference"]["socket_path"]).exists()
    return {"ok": inference_ready, "web_ok": True, "inference_ready": inference_ready,
            "version": "0.1.0", "backend": config["inference"]["backend"]}


@app.post("/api/v1/conversations", dependencies=[Depends(require_token)])
async def create_conversation(body: ConversationCreate) -> dict[str, Any]:
    conversation_id, timestamp = str(uuid.uuid4()), now_iso()
    db.execute("INSERT INTO conversations(id,title,model_id,created_at,updated_at) VALUES (?,?,?,?,?)",
               (conversation_id, body.title, config["models"]["active"], timestamp, timestamp))
    return db.rows("SELECT * FROM conversations WHERE id=?", (conversation_id,))[0]


@app.get("/api/v1/conversations", dependencies=[Depends(require_token)])
async def list_conversations() -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM conversations ORDER BY updated_at DESC")


@app.delete("/api/v1/conversations/{conversation_id}", dependencies=[Depends(require_token)])
async def delete_conversation(conversation_id: str) -> dict[str, bool]:
    await backend.control({"action": "clear", "conversation_id": conversation_id})
    db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return {"ok": True}


@app.get("/api/v1/conversations/{conversation_id}/messages", dependencies=[Depends(require_token)])
async def list_messages(conversation_id: str) -> list[dict[str, Any]]:
    rows = db.rows("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,))
    for row in rows:
        try:
            attachments = json.loads(row.get("attachments") or "[]")
        except json.JSONDecodeError:
            attachments = []
        row["attachments"] = attachments
        row["attachment_urls"] = [
            f"/api/v1/camera-snapshots/{Path(item['path']).name}"
            for item in attachments
            if item.get("path") and Path(item["path"]).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ]
    return rows


async def _run_inference(conversation_id: str, request_id: str, body: MessageCreate) -> None:
    answer, metrics = [], {}
    await events.publish(conversation_id, {"type": "accepted", "request_id": request_id, "conversation_id": conversation_id, "timestamp": now_iso()})
    try:
        tool_name = None
        if any(term in body.text for term in ("系统状态", "设备状态", "CPU占用", "CPU 占用", "NPU占用", "NPU 占用", "内存占用")):
            tool_name = "get_system_status"
        elif any(term in body.text for term in ("当前模型", "模型信息", "上下文信息", "上下文长度")):
            tool_name = "get_model_context"
        elif any(term in body.text for term in ("摄像头状态", "有哪些摄像头")):
            tool_name = "get_camera_status"
        if tool_name:
            outcome = await tools.execute(tool_name, {}, request_id, conversation_id, True)
            rendered = json.dumps(outcome, ensure_ascii=False, indent=2)
            metrics = {"backend": "tool", "tool": tool_name, "input_tokens": 0, "output_tokens": 0, "reused_tokens": 0}
            await events.publish(conversation_id, {"type": "tool", "tool": tool_name, "request_id": request_id,
                                                   "conversation_id": conversation_id, "timestamp": now_iso()})
            await events.publish(conversation_id, {"type": "token", "text": rendered, "request_id": request_id,
                                                   "conversation_id": conversation_id, "model_version": config["models"]["active"],
                                                   "device": "rk3588", "timestamp": now_iso()})
            await events.publish(conversation_id, {"type": "done", "metrics": metrics, "request_id": request_id,
                                                   "conversation_id": conversation_id, "timestamp": now_iso()})
            answer.append(rendered)
            db.add_message(str(uuid.uuid4()), conversation_id, request_id, "assistant", rendered, metrics=metrics)
            db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), conversation_id))
            return
        rk1828_requests.add(request_id)
        async for event in backend.generate({"conversation_id": conversation_id, "request_id": request_id,
                                             "prompt": body.text, "attachments": body.attachments,
                                             "model_id": config["models"]["active"]}):
            event.update({"conversation_id": conversation_id, "model_version": config["models"]["active"],
                          "device": "rk1828", "timestamp": now_iso()})
            if event.get("type") == "token":
                answer.append(event.get("text", ""))
            if event.get("type") == "done":
                metrics = event.get("metrics", {})
            await events.publish(conversation_id, event)
        db.add_message(str(uuid.uuid4()), conversation_id, request_id, "assistant", "".join(answer), metrics=metrics)
        # RKNN reports reused history separately from newly prefetched input.
        # Store the current resident context size instead of a lifetime sum.
        current_tokens = (metrics.get("reused_tokens", 0) + metrics.get("input_tokens", 0)
                          + metrics.get("output_tokens", 0))
        db.execute("UPDATE conversations SET token_count=?, reused_tokens=?, status='resident', updated_at=? WHERE id=?",
                   (current_tokens, metrics.get("reused_tokens", 0), now_iso(), conversation_id))
    except Exception as exc:
        await events.publish(conversation_id, {"type": "error", "request_id": request_id,
                                               "conversation_id": conversation_id, "error": str(exc), "timestamp": now_iso()})
    finally:
        rk1828_requests.discard(request_id)
        active_requests.pop(conversation_id, None)


@app.post("/api/v1/conversations/{conversation_id}/messages", dependencies=[Depends(require_token)])
async def create_message(conversation_id: str, body: MessageCreate) -> dict[str, str]:
    if not db.rows("SELECT id FROM conversations WHERE id=?", (conversation_id,)):
        raise HTTPException(404, "conversation not found")
    if conversation_id in active_requests:
        raise HTTPException(409, "conversation is already generating")
    request_id = str(uuid.uuid4())
    db.add_message(str(uuid.uuid4()), conversation_id, request_id, "user", body.text,
                   [{"path": item} for item in body.attachments])
    active_requests[conversation_id] = request_id
    asyncio.create_task(_run_inference(conversation_id, request_id, body))
    return {"request_id": request_id, "conversation_id": conversation_id}


@app.get("/api/v1/conversations/{conversation_id}/events")
async def stream_events(conversation_id: str, token: str) -> StreamingResponse:
    if token != config["server"]["admin_token"]:
        raise HTTPException(401, "invalid admin token")

    async def generate():
        async for event in events.subscribe(conversation_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/v1/conversations/{conversation_id}/stop", dependencies=[Depends(require_token)])
async def stop(conversation_id: str) -> dict[str, Any]:
    request_id = active_requests.get(conversation_id)
    if not request_id:
        return {"ok": True, "already_stopped": True}
    return await backend.control({"action": "stop", "conversation_id": conversation_id, "request_id": request_id})


@app.post("/api/v1/conversations/{conversation_id}/kv/swap", dependencies=[Depends(require_token)])
async def swap(conversation_id: str, body: SwapRequest) -> dict[str, Any]:
    if body.direction not in {"in", "out"}:
        raise HTTPException(422, "direction must be in or out")
    result = await backend.control({"action": f"swap_{body.direction}", "conversation_id": conversation_id,
                                    "path": str(resolve_path(config, config["server"]["kv_dir"]) / f"{conversation_id}.kv")})
    db.execute("UPDATE conversations SET status=?, updated_at=? WHERE id=?",
               ("resident" if body.direction == "in" else "swapped", now_iso(), conversation_id))
    return result


@app.post("/api/v1/uploads", dependencies=[Depends(require_token)])
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".wav", ".mp3", ".m4a", ".webm"}:
        raise HTTPException(415, "unsupported media type")
    target = resolve_path(config, config["server"]["upload_dir"]) / f"{uuid.uuid4()}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 50 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413, "file too large")
            handle.write(chunk)
    if suffix in {".mp3", ".m4a", ".webm"}:
        wav_target = target.with_suffix(".wav")
        try:
            subprocess.run(["ffmpeg", "-y", "-i", str(target), "-ac", "1", "-ar", "16000", str(wav_target)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (subprocess.SubprocessError, FileNotFoundError):
            target.unlink(missing_ok=True)
            raise HTTPException(422, "audio conversion failed")
        target.unlink(missing_ok=True)
        target = wav_target
    return {"id": target.name, "path": str(target), "size": size, "content_type": file.content_type}


@app.get("/api/v1/models", dependencies=[Depends(require_token)])
async def models() -> dict[str, Any]:
    return {"active": config["models"]["active"], "models": config["models"]["registry"], "plugins": config.get("plugins", [])}


@app.get("/api/v1/system/snapshot", dependencies=[Depends(require_token)])
async def snapshot() -> dict[str, Any]:
    return platform_snapshot()


@app.websocket("/api/v1/system/stream")
async def system_stream(websocket: WebSocket) -> None:
    if websocket.query_params.get("token") != config["server"]["admin_token"]:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(platform_snapshot())
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass


@app.get("/api/v1/cameras", dependencies=[Depends(require_token)])
async def list_cameras() -> list[dict[str, Any]]:
    return cameras.list()


@app.get("/api/v1/cameras/preview/status", dependencies=[Depends(require_token)])
async def camera_preview_status() -> dict[str, Any]:
    return preview_gateway.status()


@app.get("/api/v1/vision/pipeline", dependencies=[Depends(require_token)])
async def vision_pipeline() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(vision.status)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"vision service unavailable: {exc}")


@app.patch("/api/v1/vision/pipeline", dependencies=[Depends(require_token)])
async def update_vision_pipeline(body: VisionPipelinePatch) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "at least one vision setting is required")
    try:
        result = await asyncio.to_thread(vision.update, changes)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, f"vision service unavailable: {exc}")
    db.execute("INSERT INTO audit_log(request_id,conversation_id,tool,arguments,outcome,created_at) VALUES (?,?,?,?,?,?)",
               (str(uuid.uuid4()), None, "update_vision_pipeline", json.dumps(changes),
                json.dumps({"ok": True}), now_iso()))
    return result


def _audit_dual_roi(action: str, outcome: dict[str, Any]) -> None:
    db.execute("INSERT INTO audit_log(request_id,conversation_id,tool,arguments,outcome,created_at) VALUES (?,?,?,?,?,?)",
               (str(uuid.uuid4()), None, f"dual_roi_{action}", "{}",
                json.dumps(outcome, ensure_ascii=False), now_iso()))


@app.get("/api/v1/demo/dual-roi", dependencies=[Depends(require_token)])
async def dual_roi_status() -> dict[str, Any]:
    return await asyncio.to_thread(dual_roi.status)


@app.post("/api/v1/demo/dual-roi/start", dependencies=[Depends(require_token)])
async def dual_roi_start() -> dict[str, Any]:
    await preview_gateway.close()
    try:
        result = await asyncio.to_thread(dual_roi.start)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(503, f"dual ROI start failed: {exc}")
    _audit_dual_roi("start", {"ok": True, "mode": result.get("mode")})
    return result


@app.post("/api/v1/demo/dual-roi/stop", dependencies=[Depends(require_token)])
async def dual_roi_stop() -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(dual_roi.stop)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(503, f"dual ROI stop failed: {exc}")
    _audit_dual_roi("stop", {"ok": True})
    return result


@app.post("/api/v1/demo/dual-roi/unlock", dependencies=[Depends(require_token)])
@app.post("/api/v1/demo/dual-roi/full-frame", dependencies=[Depends(require_token)])
async def dual_roi_unlock() -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(dual_roi.command, "unlock")
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"dual ROI unlock failed: {exc}")
    _audit_dual_roi("unlock", {"ok": True, "mode": result.get("mode")})
    return result


@app.post("/api/v1/demo/dual-roi/projected-fallback", dependencies=[Depends(require_token)])
async def dual_roi_projected_fallback(body: ProjectedFallbackRequest) -> dict[str, Any]:
    command = f"projected fallback {'on' if body.enabled else 'off'}"
    try:
        result = await asyncio.to_thread(dual_roi.command, command)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"dual ROI fallback update failed: {exc}")
    _audit_dual_roi("projected_fallback", {"ok": True, "enabled": body.enabled})
    return result


@app.get("/api/v1/demo/dual-roi/events")
async def dual_roi_events(token: str) -> StreamingResponse:
    if token != config["server"]["admin_token"]:
        raise HTTPException(401, "invalid admin token")

    async def stream():
        previous = ""
        while True:
            status = await asyncio.to_thread(dual_roi.status)
            payload = json.dumps(status, ensure_ascii=False, separators=(",", ":"))
            if payload != previous:
                yield f"data: {payload}\n\n"
                previous = payload
            await asyncio.sleep(0.25 if status.get("active") else 1.0)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/v1/cameras/{camera_id}/stream")
async def camera_stream(camera_id: str, token: str, request: Request):
    if token != config["server"]["admin_token"]:
        raise HTTPException(401, "invalid admin token")
    try:
        provider = cameras.get(camera_id)
    except KeyError:
        raise HTTPException(404, "camera not found")
    if isinstance(provider, RtspCamera):
        return StreamingResponse(preview_gateway.stream(camera_id, provider.source, request),
                                 media_type="multipart/x-mixed-replace; boundary=frame")
    path = cameras.capture(camera_id, resolve_path(config, config["server"]["upload_dir"]) / "camera")
    return FileResponse(path)


@app.post("/api/v1/cameras/{camera_id}/analyze", dependencies=[Depends(require_token)])
async def analyze_camera(camera_id: str, conversation_id: str) -> dict[str, str]:
    try:
        path = cameras.capture(camera_id, resolve_path(config, config["server"]["upload_dir"]) / "camera")
    except KeyError:
        raise HTTPException(404, "camera not found")
    result = await create_message(conversation_id, MessageCreate(
        text=f"<image>请分析摄像头 {camera_id} 的当前画面。",
        attachments=[str(path)],
    ))
    result["snapshot_url"] = f"/api/v1/camera-snapshots/{path.name}"
    result["camera_id"] = camera_id
    return result


@app.get("/api/v1/camera-snapshots/{filename}")
async def camera_snapshot(filename: str, token: str) -> FileResponse:
    if token != config["server"]["admin_token"]:
        raise HTTPException(401, "invalid admin token")
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(404, "snapshot not found")
    target = resolve_path(config, config["server"]["upload_dir"]) / "camera" / safe_name
    if not target.is_file():
        raise HTTPException(404, "snapshot not found")
    return FileResponse(target, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@app.get("/api/v1/tools", dependencies=[Depends(require_token)])
async def list_tools() -> list[dict[str, Any]]:
    return tools.describe()


@app.post("/api/v1/tools/{name}/execute", dependencies=[Depends(require_token)])
async def execute_tool(name: str, body: ToolRequest) -> dict[str, Any]:
    return await tools.execute(name, body.arguments, str(uuid.uuid4()), body.conversation_id, body.confirmed)


@app.post("/api/v1/experiments", dependencies=[Depends(require_token)])
async def create_experiment(body: ExperimentCreate) -> dict[str, Any]:
    return experiments.create(body.name, body.variables)


@app.get("/api/v1/experiments/{experiment_id}", dependencies=[Depends(require_token)])
async def get_experiment(experiment_id: str) -> dict[str, Any]:
    result = experiments.get(experiment_id)
    if not result:
        raise HTTPException(404, "experiment not found")
    return result


frontend = Path(config["_root"]) / "frontend/dist"
if not frontend.is_dir():
    frontend = Path(config["_root"]) / "frontend"
if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

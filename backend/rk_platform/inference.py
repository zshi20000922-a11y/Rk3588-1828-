from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator


class InferenceBackend(ABC):
    @abstractmethod
    async def generate(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]: ...

    @abstractmethod
    async def control(self, command: dict[str, Any]) -> dict[str, Any]: ...


class MockBackend(InferenceBackend):
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, int | str]] = {}
        self.cancelled: set[str] = set()

    async def generate(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        conversation_id = request["conversation_id"]
        request_id = request["request_id"]
        prompt = request.get("prompt", "")
        session = self.sessions.setdefault(conversation_id, {"tokens": 0, "reused": 0, "status": "resident"})
        session["reused"] = int(session["tokens"])
        words = list(f"模拟回复：已收到“{prompt}”。RKNN3 板端后端启用后，此处将返回 RK1828 的真实流式结果。")
        started = time.perf_counter()
        yield {"type": "phase", "phase": "prefill", "request_id": request_id}
        for token in words:
            if request_id in self.cancelled:
                yield {"type": "stopped", "request_id": request_id}
                self.cancelled.discard(request_id)
                return
            await asyncio.sleep(0.006)
            yield {"type": "token", "text": token, "request_id": request_id}
        input_tokens = max(1, len(prompt) // 2)
        output_tokens = len(words)
        session["tokens"] = int(session["tokens"]) + input_tokens + output_tokens
        elapsed = time.perf_counter() - started
        yield {"type": "done", "request_id": request_id, "metrics": {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "reused_tokens": session["reused"], "ttft_ms": 10.0,
            "decode_tps": round(output_tokens / max(elapsed, 0.001), 2),
            "backend": "mock"
        }}

    async def control(self, command: dict[str, Any]) -> dict[str, Any]:
        action = command["action"]
        conversation_id = command.get("conversation_id", "")
        if action == "stop":
            self.cancelled.add(command["request_id"])
        elif action == "clear":
            self.sessions.pop(conversation_id, None)
        elif action == "swap_out" and conversation_id in self.sessions:
            self.sessions[conversation_id]["status"] = "swapped"
        elif action == "swap_in" and conversation_id in self.sessions:
            self.sessions[conversation_id]["status"] = "resident"
        return {"ok": True, "action": action}


class UnixSocketBackend(InferenceBackend):
    """JSON-lines client for the native RKNN3 daemon."""

    def __init__(self, socket_path: str):
        self.socket_path = socket_path

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_unix_connection(self.socket_path)

    async def generate(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        reader, writer = await self._connect()
        try:
            writer.write((json.dumps({"action": "generate", **request}, ensure_ascii=False) + "\n").encode())
            await writer.drain()
            while line := await reader.readline():
                event = json.loads(line)
                yield event
                if event.get("type") in {"done", "error", "stopped"}:
                    break
        finally:
            writer.close()
            await writer.wait_closed()

    async def control(self, command: dict[str, Any]) -> dict[str, Any]:
        reader, writer = await self._connect()
        try:
            writer.write((json.dumps(command, ensure_ascii=False) + "\n").encode())
            await writer.drain()
            return json.loads(await reader.readline())
        finally:
            writer.close()
            await writer.wait_closed()


def create_backend(config: dict[str, Any]) -> InferenceBackend:
    inference = config["inference"]
    if inference["backend"] == "rknn3":
        return UnixSocketBackend(inference["socket_path"])
    return MockBackend()


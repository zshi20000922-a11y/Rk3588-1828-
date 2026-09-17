from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, AsyncIterator

from fastapi import Request

from .cameras import build_preview_command


def extract_jpeg_frames(buffer: bytearray) -> list[bytes]:
    frames: list[bytes] = []
    while True:
        start = buffer.find(b"\xff\xd8")
        if start < 0:
            if len(buffer) > 1:
                del buffer[:-1]
            break
        end = buffer.find(b"\xff\xd9", start + 2)
        if end < 0:
            if start:
                del buffer[:start]
            break
        frames.append(bytes(buffer[start:end + 2]))
        del buffer[:end + 2]
    return frames


class MjpegHub:
    def __init__(self, source: str, settings: dict[str, Any]):
        self.source = source
        self.settings = settings
        self.subscribers: set[asyncio.Queue[bytes]] = set()
        self.task: asyncio.Task[None] | None = None
        self.idle_task: asyncio.Task[None] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.frames = 0
        self.dropped = 0
        self.restarts = 0
        self.last_error = ""

    async def subscribe(self) -> asyncio.Queue[bytes]:
        if self.idle_task:
            self.idle_task.cancel()
            self.idle_task = None
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[bytes]) -> None:
        self.subscribers.discard(queue)
        if not self.subscribers and not self.idle_task:
            self.idle_task = asyncio.create_task(self._stop_after_idle())

    async def _stop_after_idle(self) -> None:
        try:
            await asyncio.sleep(float(self.settings.get("idle_seconds", 2)))
            if not self.subscribers:
                await self.stop()
        except asyncio.CancelledError:
            pass
        finally:
            self.idle_task = None

    async def _terminate_process(self) -> None:
        process, self.process = self.process, None
        if process is None or process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()

    async def _run(self) -> None:
        try:
            while self.subscribers:
                try:
                    self.process = await asyncio.create_subprocess_exec(
                        *build_preview_command(self.source, self.settings),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    buffer = bytearray()
                    while self.subscribers:
                        assert self.process.stdout is not None
                        chunk = await self.process.stdout.read(65536)
                        if not chunk:
                            raise RuntimeError(f"preview process exited with {self.process.returncode}")
                        buffer.extend(chunk)
                        for frame in extract_jpeg_frames(buffer):
                            self.frames += 1
                            for queue in tuple(self.subscribers):
                                if queue.full():
                                    with suppress(asyncio.QueueEmpty):
                                        queue.get_nowait()
                                    self.dropped += 1
                                queue.put_nowait(frame)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = str(exc)
                    self.restarts += 1
                finally:
                    await self._terminate_process()
                if self.subscribers:
                    await asyncio.sleep(1)
        finally:
            self.task = None

    async def stop(self) -> None:
        task = self.task
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self._terminate_process()

    def status(self) -> dict[str, Any]:
        return {
            "clients": len(self.subscribers),
            "running": self.process is not None and self.process.returncode is None,
            "pid": self.process.pid if self.process and self.process.returncode is None else None,
            "frames": self.frames,
            "dropped_for_slow_clients": self.dropped,
            "restarts": self.restarts,
            "last_error": self.last_error,
        }


class SharedMjpegGateway:
    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}
        self.hubs: dict[str, MjpegHub] = {}

    async def stream(self, camera_id: str, source: str, request: Request) -> AsyncIterator[bytes]:
        hub = self.hubs.setdefault(camera_id, MjpegHub(source, self.settings))
        queue = await hub.subscribe()
        try:
            while not await request.is_disconnected():
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
        finally:
            await hub.unsubscribe(queue)

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.settings.get("backend", "ffmpeg"),
            "shared": True,
            "streams": {camera_id: hub.status() for camera_id, hub in self.hubs.items()},
        }

    async def close(self) -> None:
        await asyncio.gather(*(hub.stop() for hub in self.hubs.values()), return_exceptions=True)

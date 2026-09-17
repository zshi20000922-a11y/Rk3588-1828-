#!/usr/bin/env python3
"""Collect detailed image-to-first-token and decode metrics from the RKNN3 daemon."""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any


def rpc(socket_path: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        stream = client.makefile("r", encoding="utf-8")
        for line in stream:
            event = json.loads(line)
            events.append(event)
            if event.get("type") in {"done", "error", "stopped"} or "ok" in event:
                break
    return events, round((time.perf_counter() - started) * 1000, 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/rk-edge-ai/inference.sock")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--prompt", default="<image>请用一句话描述图像中的主要内容。")
    parser.add_argument("images", nargs="+")
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for image_path in args.images:
        for repeat in range(1, args.repeats + 1):
            conversation_id = f"visionbench-{Path(image_path).stem}-r{repeat}"
            request_id = str(uuid.uuid4())
            events, wall_ms = rpc(args.socket, {
                "action": "generate", "conversation_id": conversation_id,
                "request_id": request_id, "prompt": args.prompt,
                "attachments": [image_path],
            })
            terminal = events[-1] if events else {"type": "error", "error": "no events"}
            rows.append({
                "image_path": image_path, "repeat": repeat, "prompt": args.prompt,
                "conversation_id": conversation_id, "request_id": request_id,
                "answer": "".join(e.get("text", "") for e in events if e.get("type") == "token"),
                "metrics": terminal.get("metrics", {}), "terminal_type": terminal.get("type"),
                "error": terminal.get("error", ""), "wall_ms": wall_ms,
            })
            control, clear_ms = rpc(args.socket, {
                "action": "clear", "conversation_id": conversation_id, "keep_system_prompt": False,
            })
            rows[-1]["clear_ok"] = bool(control and control[-1].get("ok"))
            rows[-1]["clear_ms"] = clear_ms
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

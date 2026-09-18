#!/usr/bin/env python3
"""Run reproducible long-prompt requests against the resident RKNN3 daemon."""

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
    parser.add_argument("--context", type=int, required=True)
    parser.add_argument("--repeat-units", type=int, default=600)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    # Stable ASCII units make the same logical prompt reusable across tokenizer builds.
    prompt = "Context benchmark data: " + "item " * args.repeat_units + "\n只回答：好。"
    rows: list[dict[str, Any]] = []
    for repeat in range(1, args.repeats + 1):
        conversation_id = f"context-{args.context}-r{repeat}"
        request_id = str(uuid.uuid4())
        events, wall_ms = rpc(args.socket, {
            "action": "generate", "conversation_id": conversation_id,
            "request_id": request_id, "prompt": prompt, "attachments": [],
        })
        terminal = events[-1] if events else {"type": "error", "error": "no events"}
        clear, clear_ms = rpc(args.socket, {
            "action": "clear", "conversation_id": conversation_id,
            "keep_system_prompt": False,
        })
        rows.append({
            "configured_context": args.context,
            "repeat_units": args.repeat_units,
            "prompt_bytes": len(prompt.encode()),
            "repeat": repeat,
            "request_id": request_id,
            "answer": "".join(e.get("text", "") for e in events if e.get("type") == "token"),
            "metrics": terminal.get("metrics", {}),
            "terminal_type": terminal.get("type"),
            "error": terminal.get("error", ""),
            "wall_ms": wall_ms,
            "clear_ok": bool(clear and clear[-1].get("ok")),
            "clear_ms": clear_ms,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the RKNN3 multi-session KV isolation baseline against the daemon socket."""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any


def rpc(socket_path: str, request: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
        stream = client.makefile("r", encoding="utf-8")
        for line in stream:
            event = json.loads(line)
            events.append(event)
            if event.get("type") in {"done", "error", "stopped"} or "ok" in event:
                break
    return events, (time.perf_counter() - started) * 1000


def generate(socket_path: str, conversation_id: str, prompt: str) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    events, wall_ms = rpc(socket_path, {
        "action": "generate", "conversation_id": conversation_id,
        "request_id": request_id, "prompt": prompt, "attachments": [],
    })
    terminal = events[-1] if events else {"type": "error", "error": "no events"}
    return {
        "conversation_id": conversation_id,
        "request_id": request_id,
        "prompt": prompt,
        "answer": "".join(event.get("text", "") for event in events if event.get("type") == "token"),
        "metrics": terminal.get("metrics", {}),
        "terminal_type": terminal.get("type", "control"),
        "error": terminal.get("error", ""),
        "wall_ms": round(wall_ms, 3),
    }


def control(socket_path: str, action: str, conversation_id: str) -> dict[str, Any]:
    events, wall_ms = rpc(socket_path, {
        "action": action, "conversation_id": conversation_id, "keep_system_prompt": False,
    })
    return {"action": action, "conversation_id": conversation_id,
            "response": events[-1] if events else {}, "wall_ms": round(wall_ms, 3)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/rk-edge-ai/inference.sock")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    base_facts = {
        "a": "JADE-17", "b": "EMBER-29",
        "c": "COBALT-43", "d": "LOTUS-61",
    }
    rows: list[dict[str, Any]] = []
    all_conversations: list[str] = []
    try:
        for repeat in range(1, args.repeats + 1):
            facts = {f"kvexp-r{repeat}-{suffix}": code for suffix, code in base_facts.items()}
            all_conversations.extend(facts)
            for conversation_id, code in facts.items():
                row = generate(args.socket, conversation_id,
                               f"请记住本会话的唯一代号是 {code}。只回答：已记住。")
                row.update({"phase": "prime", "repeat": repeat, "expected_code": code})
                rows.append(row)
            for conversation_id, code in facts.items():
                row = generate(args.socket, conversation_id, "本会话的唯一代号是什么？只回答代号。")
                row.update({"phase": "recall", "repeat": repeat, "expected_code": code,
                            "correct": code in row["answer"],
                            "cross_talk": any(other in row["answer"] for other in facts.values() if other != code)})
                rows.append(row)
            cleared_id = f"kvexp-r{repeat}-a"
            rows.append(control(args.socket, "clear", cleared_id) | {"phase": "clear", "repeat": repeat})
            row = generate(args.socket, cleared_id, "本会话的唯一代号是什么？如果不知道，只回答不知道。")
            row.update({"phase": "after_clear", "repeat": repeat, "expected_code": facts[cleared_id],
                        "forgotten": facts[cleared_id] not in row["answer"]})
            rows.append(row)
            for conversation_id in facts:
                rows.append(control(args.socket, "clear", conversation_id)
                            | {"phase": "round_cleanup", "repeat": repeat})
    finally:
        for conversation_id in all_conversations:
            rows.append(control(args.socket, "clear", conversation_id) | {"phase": "cleanup"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

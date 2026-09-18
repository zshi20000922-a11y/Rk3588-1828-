#!/usr/bin/env python3
"""Validate resident KV reuse, explicit swap, and five-session LRU restore."""

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
        for line in client.makefile("r", encoding="utf-8"):
            event = json.loads(line)
            events.append(event)
            if event.get("type") in {"done", "error", "stopped"} or "ok" in event:
                break
    return events, round((time.perf_counter() - started) * 1000, 3)


def generate(socket_path: str, conversation_id: str, prompt: str, phase: str) -> dict[str, Any]:
    events, wall_ms = rpc(socket_path, {
        "action": "generate", "conversation_id": conversation_id,
        "request_id": str(uuid.uuid4()), "prompt": prompt, "attachments": [],
    })
    terminal = events[-1] if events else {"type": "error", "error": "no events"}
    return {
        "phase": phase, "conversation_id": conversation_id,
        "answer": "".join(e.get("text", "") for e in events if e.get("type") == "token"),
        "metrics": terminal.get("metrics", {}), "terminal_type": terminal.get("type"),
        "error": terminal.get("error", ""), "wall_ms": wall_ms,
    }


def control(socket_path: str, action: str, conversation_id: str, phase: str) -> dict[str, Any]:
    events, wall_ms = rpc(socket_path, {"action": action, "conversation_id": conversation_id})
    return {"phase": phase, "action": action, "conversation_id": conversation_id,
            "response": events[-1] if events else {}, "wall_ms": wall_ms}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/rk-edge-ai/inference.sock")
    parser.add_argument("--kv-dir", type=Path, default=Path("/userdata/rk-edge-ai/data/kv"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-units", type=int, default=600)
    args = parser.parse_args()
    codes = ["JADE-17", "EMBER-29", "COBALT-43", "LOTUS-61", "ONYX-83"]
    ids = [f"kv4096-{i}" for i in range(1, 6)]
    filler = "item " * args.history_units
    rows: list[dict[str, Any]] = []
    try:
        # Explicit swap uses one session and verifies restore before LRU work.
        explicit = "kv4096-explicit"
        rows.append(generate(args.socket, explicit,
                             f"Background: {filler}\n记住代号 JADE-17，只回答：已记住。", "explicit_prime"))
        rows.append(generate(args.socket, explicit, "代号是什么？只回答代号。", "explicit_resident_recall"))
        rows.append(control(args.socket, "swap_out", explicit, "explicit_swap_out"))
        kv_path = args.kv_dir / f"{explicit}.kv"
        rows.append({"phase": "explicit_swap_file", "path": str(kv_path),
                     "exists": kv_path.exists(), "size_bytes": kv_path.stat().st_size if kv_path.exists() else 0})
        rows.append(control(args.socket, "swap_in", explicit, "explicit_swap_in"))
        rows.append(generate(args.socket, explicit, "代号是什么？只回答代号。", "explicit_restored_recall"))
        rows.append(control(args.socket, "clear", explicit, "explicit_cleanup"))

        # Five histories exceed the four-session resident pool and trigger LRU.
        for cid, code in zip(ids, codes):
            row = generate(args.socket, cid,
                           f"Background: {filler}\n记住代号 {code}，只回答：已记住。", "lru_prime")
            row["expected_code"] = code
            rows.append(row)
        first_kv = args.kv_dir / f"{ids[0]}.kv"
        rows.append({"phase": "lru_eviction_file", "conversation_id": ids[0],
                     "path": str(first_kv), "exists": first_kv.exists(),
                     "size_bytes": first_kv.stat().st_size if first_kv.exists() else 0})
        row = generate(args.socket, ids[0], "代号是什么？只回答代号。", "lru_restored_recall")
        row.update({"expected_code": codes[0], "correct": codes[0] in row["answer"],
                    "cross_talk": any(code in row["answer"] for code in codes[1:])})
        rows.append(row)
    finally:
        for cid in ["kv4096-explicit", *ids]:
            try:
                rows.append(control(args.socket, "clear", cid, "cleanup"))
            except OSError as exc:
                rows.append({"phase": "cleanup", "conversation_id": cid, "error": str(exc)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

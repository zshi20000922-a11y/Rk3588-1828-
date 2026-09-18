#!/usr/bin/env python3
"""Stress one RKNN3 session through repeated explicit KV swap-out/in cycles."""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any


def rpc(socket_path: str, payload: dict[str, Any], timeout: float) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter(); events: list[dict[str, Any]] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout); client.connect(socket_path)
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        for line in client.makefile("r", encoding="utf-8"):
            event = json.loads(line); events.append(event)
            if event.get("type") in {"done", "error", "stopped"} or "ok" in event: break
    return events, round((time.perf_counter() - started) * 1000, 3)


def append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()


def generate(sock: str, cid: str, prompt: str, timeout: float) -> dict[str, Any]:
    events, wall_ms = rpc(sock, {"action":"generate","conversation_id":cid,
        "request_id":str(uuid.uuid4()),"prompt":prompt,"attachments":[]}, timeout)
    terminal = events[-1] if events else {"type":"error","error":"no events"}
    return {"answer":"".join(e.get("text","") for e in events if e.get("type")=="token"),
        "metrics":terminal.get("metrics",{}),"terminal_type":terminal.get("type"),
        "error":terminal.get("error",""),"wall_ms":wall_ms}


def control(sock: str, action: str, cid: str, timeout: float) -> dict[str, Any]:
    events, wall_ms = rpc(sock, {"action":action,"conversation_id":cid}, timeout)
    return {"response":events[-1] if events else {},"wall_ms":wall_ms}


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--socket",default="/run/rk-edge-ai/inference.sock")
    ap.add_argument("--kv-dir",type=Path,default=Path("/userdata/rk-edge-ai/data/kv"))
    ap.add_argument("--output",type=Path,required=True); ap.add_argument("--cycles",type=int,default=20)
    ap.add_argument("--timeout",type=float,default=30); args=ap.parse_args()
    cid="explicit-swap-stress"; code="JADE-17"; kv_path=args.kv_dir/f"{cid}.kv"
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.unlink(missing_ok=True)
    try:
        row=generate(args.socket,cid,f"记住本会话代号是{code}。只回答：已记住。",args.timeout)
        append(args.output,{"phase":"prime",**row})
        for cycle in range(1,args.cycles+1):
            try:
                out=control(args.socket,"swap_out",cid,args.timeout)
                append(args.output,{"phase":"swap_out","cycle":cycle,"kv_exists":kv_path.exists(),
                    "kv_size_bytes":kv_path.stat().st_size if kv_path.exists() else 0,**out})
                inside=control(args.socket,"swap_in",cid,args.timeout)
                append(args.output,{"phase":"swap_in","cycle":cycle,**inside})
                recall=generate(args.socket,cid,"本会话代号是什么？只回答代号。",args.timeout)
                append(args.output,{"phase":"recall","cycle":cycle,"expected":code,
                    "correct":code in recall["answer"],**recall})
            except (OSError,TimeoutError) as exc:
                append(args.output,{"phase":"cycle_error","cycle":cycle,"error":repr(exc)})
                break
    finally:
        try: append(args.output,{"phase":"cleanup",**control(args.socket,"clear",cid,args.timeout)})
        except (OSError,TimeoutError) as exc: append(args.output,{"phase":"cleanup_error","error":repr(exc)})


if __name__=="__main__": main()

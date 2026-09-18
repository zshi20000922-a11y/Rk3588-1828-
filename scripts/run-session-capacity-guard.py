#!/usr/bin/env python3
"""Verify that a fifth resident session is rejected without harming four active sessions."""

import argparse
import json
import socket
import time
import uuid
from pathlib import Path


def call(sock: str, payload: dict) -> tuple[list[dict], float]:
    start = time.perf_counter()
    events = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(sock)
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        for line in client.makefile("r", encoding="utf-8"):
            event = json.loads(line); events.append(event)
            if event.get("type") in {"done", "error"} or "ok" in event: break
    return events, round((time.perf_counter() - start) * 1000, 3)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--socket", default="/run/rk-edge-ai/inference.sock")
    ap.add_argument("--output", type=Path, required=True); args = ap.parse_args()
    codes = ["JADE-17", "EMBER-29", "COBALT-43", "LOTUS-61"]
    ids = [f"capacity-guard-{i}" for i in range(1, 6)]; rows = []
    try:
        for cid, code in zip(ids[:4], codes):
            events, ms = call(args.socket, {"action":"generate","conversation_id":cid,"request_id":str(uuid.uuid4()),"prompt":f"记住代号{code}，只回答已记住。","attachments":[]})
            rows.append({"phase":"prime","conversation_id":cid,"events":events,"wall_ms":ms})
        events, ms = call(args.socket, {"action":"generate","conversation_id":ids[4],"request_id":str(uuid.uuid4()),"prompt":"你好","attachments":[]})
        rows.append({"phase":"fifth_rejected","conversation_id":ids[4],"events":events,"wall_ms":ms})
        events, ms = call(args.socket, {"action":"generate","conversation_id":ids[0],"request_id":str(uuid.uuid4()),"prompt":"代号是什么？只回答代号。","attachments":[]})
        answer = "".join(e.get("text","") for e in events if e.get("type")=="token")
        rows.append({"phase":"first_survives","conversation_id":ids[0],"events":events,"answer":answer,"correct":codes[0] in answer,"wall_ms":ms})
    finally:
        for cid in ids:
            try:
                events, ms = call(args.socket, {"action":"clear","conversation_id":cid,"keep_system_prompt":False})
                rows.append({"phase":"cleanup","conversation_id":cid,"events":events,"wall_ms":ms})
            except OSError as exc: rows.append({"phase":"cleanup","conversation_id":cid,"error":str(exc)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__ == "__main__": main()

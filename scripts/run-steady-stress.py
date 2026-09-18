#!/usr/bin/env python3
"""Run a fixed-rate, bounded-context steady-state RKNN3 stress test."""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any


def rpc(sock: str, payload: dict[str, Any], timeout: float = 15) -> tuple[list[dict[str, Any]], float]:
    started=time.perf_counter();events=[]
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(timeout);client.connect(sock)
        client.sendall((json.dumps(payload,ensure_ascii=False)+"\n").encode())
        for line in client.makefile("r",encoding="utf-8"):
            event=json.loads(line);events.append(event)
            if event.get("type") in {"done","error","stopped"} or "ok" in event:break
    return events,round((time.perf_counter()-started)*1000,3)


def append(path:Path,row:dict[str,Any])->None:
    with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False)+"\n");f.flush()


def generate(sock:str,cid:str,prompt:str,code:str,index:int,phase:str)->dict[str,Any]:
    started_at=time.time()
    try:
        events,wall=rpc(sock,{"action":"generate","conversation_id":cid,
            "request_id":str(uuid.uuid4()),"prompt":prompt,"attachments":[]})
        terminal=events[-1] if events else {"type":"error","error":"no events"}
        answer="".join(e.get("text","") for e in events if e.get("type")=="token")
        return {"timestamp":started_at,"index":index,"phase":phase,"conversation_id":cid,
            "expected_code":code,"answer":answer,"correct":phase=="prime" or code in answer,
            "terminal_type":terminal.get("type"),"error":terminal.get("error",""),
            "metrics":terminal.get("metrics",{}),"wall_ms":wall}
    except (OSError,TimeoutError) as exc:
        return {"timestamp":started_at,"index":index,"phase":phase,"conversation_id":cid,
            "expected_code":code,"correct":False,"terminal_type":"exception","error":repr(exc),"metrics":{}}


def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--socket",default="/run/rk-edge-ai/inference.sock")
    ap.add_argument("--output",type=Path,required=True);ap.add_argument("--duration",type=int,default=1800)
    ap.add_argument("--interval",type=float,default=5);ap.add_argument("--refresh-turns",type=int,default=16)
    args=ap.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.unlink(missing_ok=True)
    codes=["JADE-17","EMBER-29","COBALT-43","LOTUS-61"];ids=[f"steady-{i}" for i in range(4)]
    deadline=time.monotonic()+args.duration;next_at=time.monotonic();index=0;turns=[0]*4;primed=[False]*4
    while time.monotonic()<deadline:
        slot=index%4;cid=ids[slot];code=codes[slot]
        if not primed[slot] or turns[slot]>=args.refresh_turns:
            if primed[slot]:
                try:
                    events,wall=rpc(args.socket,{"action":"clear","conversation_id":cid,"keep_system_prompt":False})
                    append(args.output,{"timestamp":time.time(),"phase":"refresh_clear","conversation_id":cid,
                        "ok":bool(events and events[-1].get("ok")),"wall_ms":wall})
                except (OSError,TimeoutError) as exc:append(args.output,{"timestamp":time.time(),"phase":"refresh_clear","conversation_id":cid,"ok":False,"error":repr(exc)})
            index+=1;append(args.output,generate(args.socket,cid,
                f"记住本会话代号是{code}。只回答：已记住。",code,index,"prime"));primed[slot]=True;turns[slot]=0
        else:
            index+=1;append(args.output,generate(args.socket,cid,"本会话代号是什么？只回答代号。",code,index,"recall"));turns[slot]+=1
        next_at+=args.interval;time.sleep(max(0,next_at-time.monotonic()))
    for cid in ids:
        try:
            events,wall=rpc(args.socket,{"action":"clear","conversation_id":cid,"keep_system_prompt":False})
            append(args.output,{"timestamp":time.time(),"phase":"cleanup","conversation_id":cid,"ok":bool(events and events[-1].get("ok")),"wall_ms":wall})
        except (OSError,TimeoutError) as exc:append(args.output,{"timestamp":time.time(),"phase":"cleanup","conversation_id":cid,"ok":False,"error":repr(exc)})


if __name__=="__main__":main()

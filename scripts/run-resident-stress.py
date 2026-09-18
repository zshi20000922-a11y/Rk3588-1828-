#!/usr/bin/env python3
"""Run 100 bounded requests over four resident RKNN3 sessions."""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any


def rpc(sock: str, payload: dict[str, Any], timeout: float = 15) -> tuple[list[dict[str, Any]], float]:
    started=time.perf_counter(); events=[]
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(timeout); client.connect(sock)
        client.sendall((json.dumps(payload,ensure_ascii=False)+"\n").encode())
        for line in client.makefile("r",encoding="utf-8"):
            event=json.loads(line); events.append(event)
            if event.get("type") in {"done","error","stopped"} or "ok" in event: break
    return events,round((time.perf_counter()-started)*1000,3)


def write(stream,row:dict[str,Any])->None:
    stream.write(json.dumps(row,ensure_ascii=False)+"\n");stream.flush()


def generate(sock:str,cid:str,prompt:str,phase:str,round_id:int,index:int,code:str)->dict[str,Any]:
    try:
        events,wall=rpc(sock,{"action":"generate","conversation_id":cid,
            "request_id":str(uuid.uuid4()),"prompt":prompt,"attachments":[]})
        terminal=events[-1] if events else {"type":"error","error":"no events"}
        answer="".join(e.get("text","") for e in events if e.get("type")=="token")
        return {"index":index,"round":round_id,"phase":phase,"conversation_id":cid,
            "expected_code":code,"answer":answer,"correct":phase=="prime" or code in answer,
            "cross_talk":False,"terminal_type":terminal.get("type"),"error":terminal.get("error",""),
            "metrics":terminal.get("metrics",{}),"wall_ms":wall}
    except (OSError,TimeoutError) as exc:
        return {"index":index,"round":round_id,"phase":phase,"conversation_id":cid,
            "expected_code":code,"correct":False,"cross_talk":False,"terminal_type":"exception",
            "error":repr(exc),"metrics":{}}


def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--socket",default="/run/rk-edge-ai/inference.sock")
    ap.add_argument("--output",type=Path,required=True);ap.add_argument("--rounds",type=int,default=5)
    args=ap.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.unlink(missing_ok=True)
    codes=["JADE-17","EMBER-29","COBALT-43","LOTUS-61"];index=0
    with args.output.open("a",encoding="utf-8") as stream:
        for round_id in range(1,args.rounds+1):
            ids=[f"stress-r{round_id}-{i}" for i in range(4)]
            for cid,code in zip(ids,codes):
                index+=1;write(stream,generate(args.socket,cid,
                    f"记住本会话代号是{code}。只回答：已记住。","prime",round_id,index,code))
            for turn in range(4):
                for cid,code in zip(ids,codes):
                    index+=1;row=generate(args.socket,cid,"本会话代号是什么？只回答代号。",
                        "recall",round_id,index,code)
                    row["cross_talk"]=any(other in row.get("answer","") for other in codes if other!=code)
                    write(stream,row)
            for cid in ids:
                try:
                    events,wall=rpc(args.socket,{"action":"clear","conversation_id":cid,"keep_system_prompt":False})
                    write(stream,{"round":round_id,"phase":"cleanup","conversation_id":cid,
                        "ok":bool(events and events[-1].get("ok")),"wall_ms":wall})
                except (OSError,TimeoutError) as exc:
                    write(stream,{"round":round_id,"phase":"cleanup","conversation_id":cid,
                        "ok":False,"error":repr(exc)})
    print(json.dumps({"requests":index,"rounds":args.rounds},ensure_ascii=False))


if __name__=="__main__":main()

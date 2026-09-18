#!/usr/bin/env python3
"""Sample process, memory, temperature, and vision-service state during stress tests."""

import argparse,csv,json,os,socket,time
from pathlib import Path

def proc(pid:int):
    try:
        stat=Path(f"/proc/{pid}/stat").read_text().split();status=Path(f"/proc/{pid}/status").read_text().splitlines()
        values={line.split(':',1)[0]:line.split()[1] for line in status if ':' in line and len(line.split())>1}
        return int(stat[13])+int(stat[14]),int(values.get('VmRSS',0)),int(values.get('VmHWM',0))
    except (OSError,ValueError):return 0,0,0

def vision(path:str):
    try:
        s=socket.socket(socket.AF_UNIX);s.settimeout(1);s.connect(path);s.sendall(b'{"command":"status"}\n');data=s.recv(262144);s.close();return json.loads(data)
    except Exception as exc:return {"ok":False,"error":repr(exc)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--csv',type=Path,required=True);ap.add_argument('--vision-jsonl',type=Path,required=True)
    ap.add_argument('--stop-file',type=Path,required=True);ap.add_argument('--interval',type=float,default=1);args=ap.parse_args()
    names={'inference':'rk_inference_daemon','vision':'rk_vision_service','web':'uvicorn','mediamtx':'mediamtx'}
    pids={}
    for label,name in names.items():
        for p in Path('/proc').glob('[0-9]*'):
            try:
                if name in (p/'cmdline').read_bytes().decode(errors='ignore'):pids[label]=int(p.name);break
            except OSError:pass
    args.csv.parent.mkdir(parents=True,exist_ok=True);last={};last_t=time.monotonic();clk=os.sysconf('SC_CLK_TCK')
    fields=['timestamp','mem_available_kb','temp_mC']+[f'{n}_{x}' for n in names for x in ('cpu_pct','rss_kb','hwm_kb')]
    with args.csv.open('w',newline='') as f,args.vision_jsonl.open('w') as vf:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        while not args.stop_file.exists():
            now=time.monotonic();row={'timestamp':time.time()}
            try:row['mem_available_kb']=next(int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
            except Exception:row['mem_available_kb']=0
            temps=[]
            for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
                try:temps.append(int(p.read_text()))
                except (OSError,ValueError):pass
            row['temp_mC']=max(temps,default=0)
            for label in names:
                ticks,rss,hwm=proc(pids.get(label,0));prev=last.get(label)
                row[f'{label}_cpu_pct']=(ticks-prev)*100/clk/(now-last_t) if prev is not None and now>last_t else 0
                row[f'{label}_rss_kb']=rss;row[f'{label}_hwm_kb']=hwm;last[label]=ticks
            w.writerow(row);f.flush();vf.write(json.dumps({'timestamp':time.time(),'status':vision('/run/rk-vision-service/control.sock')},ensure_ascii=False)+'\n');vf.flush()
            last_t=now;time.sleep(args.interval)

if __name__=='__main__':main()

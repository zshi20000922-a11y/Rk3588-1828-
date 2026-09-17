import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, Camera, Cpu, Image, MemoryStick, Mic, Plus, Send, Square, Thermometer, Trash2} from 'lucide-react';
import './style.css';

type Conversation = {id:string,title:string,status:string,token_count:number,reused_tokens:number,updated_at:string};
type Message = {id?:string,role:string,content:string};
type Snapshot = {rk3588:{cpu_percent:number,memory_total_mb:number,memory_used_mb:number,temperatures_c:Record<string,number>,npu:{load_raw:string|null,frequency_hz:number|null}},rk1828:{online:boolean,utilization_percent:number|null,phase?:string,note:string}};
const API='/api/v1';

function App(){
  const [token,setToken]=useState(localStorage.getItem('rk-token')||'SET_A_UNIQUE_TOKEN_BEFORE_START');
  const [conversations,setConversations]=useState<Conversation[]>([]);
  const [current,setCurrent]=useState<string>('');
  const [messages,setMessages]=useState<Message[]>([]);
  const [input,setInput]=useState(''); const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [models,setModels]=useState<any>(null); const [cameras,setCameras]=useState<any[]>([]);
  const [streaming,setStreaming]=useState(false); const [attachment,setAttachment]=useState('');
  const [recording,setRecording]=useState(false); const recorder=useRef<MediaRecorder|null>(null); const chunks=useRef<Blob[]>([]);
  const auth={'Authorization':`Bearer ${token}`};
  const request=async(path:string,init:RequestInit={})=>{const response=await fetch(API+path,{...init,headers:{...auth,...(init.headers||{})}});if(!response.ok)throw new Error(await response.text());return response.json()};
  const refresh=async()=>{try{const rows=await request('/conversations');setConversations(rows);if(!current&&rows[0])setCurrent(rows[0].id)}catch{}};
  useEffect(()=>{localStorage.setItem('rk-token',token);refresh();request('/models').then(setModels).catch(()=>{});request('/cameras').then(setCameras).catch(()=>{})},[token]);
  useEffect(()=>{if(!current)return;request(`/conversations/${current}/messages`).then((rows:any[])=>setMessages(rows.map(x=>({...x})))).catch(()=>{});const es=new EventSource(`${API}/conversations/${current}/events?token=${encodeURIComponent(token)}`);es.onmessage=e=>{const ev=JSON.parse(e.data);if(ev.type==='token'){setStreaming(true);setMessages(old=>{const copy=[...old];const last=copy[copy.length-1];if(last?.role==='assistant'&&last.id==='stream')last.content+=ev.text;else copy.push({id:'stream',role:'assistant',content:ev.text});return copy})}if(['done','error','stopped'].includes(ev.type)){setStreaming(false);refresh()}};return()=>es.close()},[current,token]);
  useEffect(()=>{const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}${API}/system/stream?token=${encodeURIComponent(token)}`);ws.onmessage=e=>setSnapshot(JSON.parse(e.data));return()=>ws.close()},[token]);
  const create=async()=>{const row=await request('/conversations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'新对话'})});await refresh();setCurrent(row.id);setMessages([])};
  const remove=async(id:string)=>{await request(`/conversations/${id}`,{method:'DELETE'});if(current===id){setCurrent('');setMessages([])};refresh()};
  const upload=async(file:File)=>{const form=new FormData();form.append('file',file);const row=await request('/uploads',{method:'POST',body:form});setAttachment(row.path)};
  const send=async()=>{if(!current||(!input.trim()&&!attachment))return;const text=input;setMessages(old=>[...old,{role:'user',content:text+(attachment?' [附件]':'')}]);setInput('');const files=attachment?[attachment]:[];setAttachment('');await request(`/conversations/${current}/messages`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,attachments:files})})};
  const stop=()=>request(`/conversations/${current}/stop`,{method:'POST'});
  const toggleRecord=async()=>{if(recording){recorder.current?.stop();setRecording(false);return}const media=await navigator.mediaDevices.getUserMedia({audio:true});const mr=new MediaRecorder(media);chunks.current=[];mr.ondataavailable=e=>chunks.current.push(e.data);mr.onstop=async()=>{const file=new File(chunks.current,'voice.webm',{type:'audio/webm'});await upload(file);setInput('<audio>请理解并回答这段语音。');media.getTracks().forEach(t=>t.stop())};mr.start();recorder.current=mr;setRecording(true)};
  const analyze=async(id:string)=>{if(current)await request(`/cameras/${id}/analyze?conversation_id=${current}`,{method:'POST'})};
  const temp=snapshot?Object.values(snapshot.rk3588.temperatures_c)[0]:undefined;
  return <div className="shell">
    <aside><div className="brand"><span>RK</span><div>Edge AI<small>异构推理平台</small></div></div><button className="new" onClick={create}><Plus size={17}/> 新建会话</button><div className="sessions">{conversations.map(c=><div className={'session '+(c.id===current?'active':'')} onClick={()=>setCurrent(c.id)} key={c.id}><div><b>{c.title}</b><small>{c.token_count} tokens · {c.status}</small></div><Trash2 size={15} onClick={e=>{e.stopPropagation();remove(c.id)}}/></div>)}</div><div className="auth"><label>管理令牌</label><input value={token} onChange={e=>setToken(e.target.value)} type="password"/></div></aside>
    <main><header><div><h1>多模态控制台</h1><p>{models?.active||'正在读取模型…'}</p></div><div className={'status '+(snapshot?.rk1828.online?'ok':'')}><i/>{snapshot?.rk1828.online?'RK1828 在线':'RK1828 离线'}</div></header>
      <section className="chat"><div className="messages">{messages.length===0&&<div className="empty"><Activity size={34}/><h2>从一条指令开始</h2><p>输入文字、上传图片，或按住说话。设备操作只通过白名单工具执行。</p></div>}{messages.map((m,i)=><div key={m.id||i} className={'bubble '+m.role}>{m.content}</div>)}</div><div className="composer">{attachment&&<div className="chip">已添加媒体文件 ×</div>}<textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}} placeholder="向 Qwen2.5-Omni 发布指令…"/><div className="actions"><label><Image size={19}/><input hidden type="file" accept="image/*,audio/*" onChange={e=>e.target.files?.[0]&&upload(e.target.files[0])}/></label><button className={recording?'recording':''} onClick={toggleRecord}><Mic size={19}/></button>{streaming?<button onClick={stop}><Square size={18}/></button>:<button className="send" onClick={send}><Send size={18}/></button>}</div></div></section>
    </main>
    <aside className="right"><h3>实时资源</h3><div className="metric-grid"><Metric icon={<Cpu/>} label="CPU" value={`${snapshot?.rk3588.cpu_percent??0}%`}/><Metric icon={<MemoryStick/>} label="内存" value={`${snapshot?.rk3588.memory_used_mb??0} MB`}/><Metric icon={<Activity/>} label="RK3588 NPU" value={snapshot?.rk3588.npu.load_raw||'空闲'}/><Metric icon={<Activity/>} label="RK1828 占空比" value={`${snapshot?.rk1828.utilization_percent??0}%`}/><Metric icon={<Thermometer/>} label="温度" value={temp?`${temp}°C`:'—'}/><Metric icon={<Activity/>} label="RK1828 阶段" value={snapshot?.rk1828.phase||'idle'}/></div><div className="panel"><h3>当前上下文</h3>{conversations.filter(c=>c.id===current).map(c=><div key={c.id}><Progress value={Math.min(100,c.token_count/10.24)}/><dl><dt>已用 Token</dt><dd>{c.token_count} / 1024</dd><dt>KV 复用</dt><dd>{c.reused_tokens}</dd><dt>KV 状态</dt><dd>{c.status}</dd></dl></div>)}</div><div className="panel"><h3><Camera size={17}/> 摄像头</h3>{cameras.map(c=><div className="camera" key={c.id}><img src={`${API}/cameras/${c.id}/stream?token=${encodeURIComponent(token)}&t=${Date.now()}`}/><div><span>{c.name}</span><button onClick={()=>analyze(c.id)}>分析当前帧</button></div></div>)}</div><div className="panel"><h3>模型配置</h3><dl><dt>设备</dt><dd>RK1828</dd><dt>量化</dt><dd>W4A16 / KV FP16</dd><dt>Core Mask</dt><dd>0xff</dd><dt>上下文</dt><dd>1024（当前 KV 组）</dd></dl></div></aside>
  </div>
}
function Metric({icon,label,value}:{icon:React.ReactNode,label:string,value:string}){return <div className="metric">{icon}<small>{label}</small><b>{value}</b></div>}
function Progress({value}:{value:number}){return <div className="progress"><i style={{width:`${value}%`}}/></div>}
createRoot(document.getElementById('root')!).render(<App/>);

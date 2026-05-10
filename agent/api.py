"""
FastAPI Agent API 서버
- POST /chat       : agent 호출
- GET  /health     : 서버/세션 상태
- GET  /sessions   : 세션 목록
- DELETE /sessions/{id} : 세션 종료
"""

import time
import asyncio
import sys
sys.path.insert(0, "/app")

import os
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from session_manager import SessionManager
from runtime import manager as _shared_manager, next_color_id, COLOR_PALETTE

app = FastAPI(title="Agent Sandbox API")
manager = _shared_manager


@app.get("/", include_in_schema=False)
def _root():
    return RedirectResponse(url="/monitor")


@app.get("/chat", include_in_schema=False)
def _chat_redirect():
    return RedirectResponse(url="/chat/")


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    llm_id: str | None = None   # None 이면 config default 사용


class ChatResponse(BaseModel):
    session_id: str
    response: str
    elapsed_ms: int


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id 필요")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 필요")

    t0 = time.time()

    def _invoke():
        session = manager.get_or_create(req.session_id.strip(), req.llm_id)
        session.begin_request(req.message)
        try:
            result = session.graph.invoke(
                {"messages": [{"role": "user", "content": req.message}]},
                config={"configurable": {"thread_id": req.session_id}},
            )
        finally:
            session.end_request()
        return result["messages"][-1].content

    try:
        response = await asyncio.to_thread(_invoke)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])

    elapsed_ms = int((time.time() - t0) * 1000)
    return ChatResponse(session_id=req.session_id, response=response, elapsed_ms=elapsed_ms)


@app.get("/health")
def health():
    stats = manager.stats()
    return {
        "status": "ok",
        "active_sessions": stats["active_sessions"],
        "max_sessions": stats["max_sessions"],
        "total_requests": stats["total_requests"],
        "total_workdir_kb": stats["total_workdir_kb"],
    }


@app.get("/sessions")
def sessions():
    out = []
    for info in manager.list_sessions():
        s = manager.get(info.session_id)
        current_message = s.current_message if s else None
        processing = bool(s and s.processing)
        # 현재(또는 마지막) tool — sandbox.activity 마지막 항목
        last_action = None
        if s is not None:
            acts = getattr(s.sandbox, "activity", [])
            if acts:
                a = acts[-1]
                last_action = {"action": a.get("action"), "target": a.get("target"), "status": a.get("status")}
        out.append({
            "session_id": info.session_id,
            "request_count": info.request_count,
            "idle_seconds": round(info.idle_seconds, 1),
            "age_seconds": round(info.age_seconds, 1),
            "workdir": info.workdir,
            "workdir_size_kb": info.workdir_size_kb,
            "current_message": current_message,
            "processing": processing,
            "last_action": last_action,
        })
    return out


@app.get("/sessions/{session_id}/activity")
def session_activity(session_id: str):
    s = manager.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    activity = getattr(s.sandbox, "activity", [])
    return {"session_id": session_id, "activity": activity}


# ── 시연용 데모 테스트셋 ────────────────────────────────────────────────────────

_DEMO_SCRIPT_A = [
    "alice.txt 파일에 'A-hello' 라고 써줘",
    "calc.py 파일에 1부터 10까지의 합을 출력하는 코드를 만들고 실행해줘",
    "result.txt 에 calc.py 출력 결과를 저장해줘",
    "현재 디렉토리 파일 목록을 보여줘",
    "count.txt 파일을 만들어서 1초마다 1부터 100까지 한 줄씩 써줘",
]

_DEMO_SCRIPT_B = [
    "bob.txt 파일에 'B-hi' 라고 써줘",
    "fib.py 파일에 피보나치 수열 첫 8개를 출력하는 코드를 만들고 실행해줘",
    "data.json 파일에 {\"x\": 10, \"y\": 20} 를 저장해줘",
    "data.json 내용을 읽어줘",
    "현재 디렉토리 파일 목록을 보여줘",
]

_demo_lock = threading.Lock()
_demo_state = {"running": False, "started_at": None, "sessions": []}


def _run_one_message(session_id: str, message: str) -> None:
    try:
        session = manager.get_or_create(session_id)
        session.begin_request(message)
        try:
            session.graph.invoke(
                {"messages": [{"role": "user", "content": message}]},
                config={"configurable": {"thread_id": session_id}},
            )
        finally:
            session.end_request()
    except Exception as e:
        # 데모용 — 실패해도 다음 메시지로 진행
        print(f"[demo] {session_id} error: {e}")


def _run_session_script(session_id: str, messages: list[str]) -> None:
    for i, msg in enumerate(messages, 1):
        _run_one_message(session_id, msg)
        _time.sleep(0.5)  # 시연 간격


def _run_demo() -> None:
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            ex.submit(_run_session_script, "red", _DEMO_SCRIPT_A)
            ex.submit(_run_session_script, "blue", _DEMO_SCRIPT_B)
            ex.shutdown(wait=True)
    finally:
        with _demo_lock:
            _demo_state["running"] = False


@app.post("/demo/start")
def demo_start():
    with _demo_lock:
        if _demo_state["running"]:
            return {"status": "already_running", "started_at": _demo_state["started_at"]}
        _demo_state["running"] = True
        _demo_state["started_at"] = _time.time()
        _demo_state["sessions"] = ["red", "blue"]
    threading.Thread(target=_run_demo, daemon=True).start()
    return {"status": "started", "sessions": ["red", "blue"], "messages_each": len(_DEMO_SCRIPT_A)}


@app.get("/demo/status")
def demo_status():
    with _demo_lock:
        return dict(_demo_state)


@app.get("/sandbox/next_id")
def sandbox_next_id():
    """다음 사용 가능한 색-이름 session_id."""
    return {"session_id": next_color_id(), "palette": COLOR_PALETTE}


@app.delete("/sessions/{session_id}")
def close_session(session_id: str):
    manager.close(session_id)
    return {"closed": session_id}


@app.get("/sandbox/tree")
def sandbox_tree():
    """sandbox WORKSPACE 최상위 디렉토리 리스트 + 활성 세션 매핑"""
    from process_sandbox import WORKSPACE
    if not os.path.exists(WORKSPACE):
        return {"workspace": WORKSPACE, "dirs": []}
    active = {info.session_id for info in manager.list_sessions()}
    dirs = []
    for name in sorted(os.listdir(WORKSPACE)):
        full = os.path.join(WORKSPACE, name)
        if not os.path.isdir(full):
            continue
        try:
            stat = os.stat(full)
        except OSError:
            continue
        total = 0
        file_count = 0
        for root, _, files in os.walk(full):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                    file_count += 1
                except OSError:
                    pass
        dirs.append({
            "name": name,
            "path": full,
            "size_bytes": total,
            "file_count": file_count,
            "active": name in active,
            "mtime": stat.st_mtime,
        })
    return {"workspace": WORKSPACE, "dirs": dirs}


@app.get("/sessions/{session_id}/files")
def list_session_files(session_id: str):
    """세션 workdir 안 파일 트리"""
    sessions = {s.session_id: s for s in manager.list_sessions()}
    info = sessions.get(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    files = []
    for root, _dirs, fs in os.walk(info.workdir):
        for f in fs:
            full = os.path.join(root, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            rel = os.path.relpath(full, info.workdir)
            files.append({"path": rel, "size": size})
    return {"session_id": session_id, "workdir": info.workdir, "files": files}


_MONITOR_HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>Agent Sandbox — Monitor</title>
<style>
 body{font-family:ui-monospace,Menlo,Consolas,monospace;background:#0e1117;color:#e6edf3;margin:0;padding:20px;}
 h1{margin:0 0 12px;font-size:18px;color:#7ee787;}
 .lead{color:#8b949e;font-size:12px;margin-bottom:14px;}
 .stats{padding:12px;background:#161b22;border-radius:6px;margin-bottom:16px;}
 .stats span{margin-right:24px;}
 .sbroot{padding:10px 14px;background:#161b22;border-radius:6px;margin-bottom:14px;font-size:12px;}
 .sbroot .title{color:#7ee787;font-weight:bold;margin-bottom:6px;}
 .sbroot .path{color:#6e7681;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;margin-bottom:8px;}
 .sbroot .dirs{display:flex;flex-wrap:wrap;gap:8px;}
 .sbroot .dir{padding:4px 10px;border-radius:5px;background:#21262d;border:1px solid #30363d;display:flex;gap:6px;align-items:center;font-size:12px;}
 .sbroot .dir.active{border-color:#238636;}
 .sbroot .dir.orphan{opacity:0.55;}
 .sbroot .dot{font-size:10px;}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px;}
 .session{background:#161b22;border-radius:6px;padding:12px 16px;border-left:3px solid #58a6ff;}
 .session h2{margin:0 0 4px;font-size:18px;color:#58a6ff;text-transform:capitalize;}
 .session h2 .dot{font-size:22px;vertical-align:middle;margin-right:4px;}
 .session .sid{font-size:11px;color:#6e7681;font-family:ui-monospace,Menlo,Consolas,monospace;margin-bottom:6px;word-break:break-all;}
 .workdir{font-size:11px;color:#6e7681;margin-bottom:6px;word-break:break-all;}
 .current{background:#0d1117;border:1px solid #30363d;border-radius:5px;padding:8px 10px;margin:8px 0;font-size:12px;}
 .current .lbl{color:#6e7681;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px;}
 .current .msg{color:#e6edf3;}
 .current .running{color:#f1c40f;font-weight:bold;}
 .current .done{color:#7ee787;}
 .current .tool-now{margin-top:6px;color:#79c0ff;font-family:ui-monospace,Menlo,Consolas,monospace;}
 .meta{color:#8b949e;font-size:12px;margin-bottom:8px;}
 .pill{display:inline-block;padding:2px 8px;border-radius:10px;background:#21262d;color:#7ee787;font-size:11px;margin-right:6px;}
 .section{font-size:11px;color:#6e7681;margin:8px 0 4px;text-transform:uppercase;letter-spacing:0.5px;}
 ul.tree{list-style:none;padding-left:8px;margin:0;font-size:12px;max-height:120px;overflow-y:auto;}
 ul.tree li{padding:1px 0;color:#c9d1d9;}
 ul.activity{list-style:none;padding-left:0;margin:0;font-size:12px;max-height:200px;overflow-y:auto;}
 ul.activity li{padding:2px 0;color:#c9d1d9;border-bottom:1px solid #21262d;display:flex;gap:6px;}
 .ts{color:#6e7681;flex-shrink:0;width:60px;}
 .act{flex-shrink:0;width:60px;font-weight:bold;}
 .act-execute{color:#79c0ff;}
 .act-write{color:#7ee787;}
 .act-read{color:#d2a8ff;}
 .act-edit{color:#ffa657;}
 .act-ls{color:#a5d6ff;}
 .act-glob,.act-grep{color:#a5d6ff;}
 .target{color:#c9d1d9;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
 .status-blocked,.status-error,.status-timeout{color:#ff7b72;}
 .empty{color:#6e7681;font-style:italic;font-size:12px;}
 .updated{color:#6e7681;font-size:11px;text-align:right;margin-top:14px;}
 .controls{margin-bottom:8px;}
 .controls button{background:#238636;color:white;border:none;padding:8px 14px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;}
 .controls button:disabled{background:#393f47;cursor:not-allowed;}
 .controls button:hover:not(:disabled){background:#2ea043;}
 .manual{margin-bottom:14px;}
 .manual form{display:flex;gap:6px;}
 .manual input,.manual select{background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:6px 10px;border-radius:6px;font-family:inherit;font-size:13px;}
 .manual select{width:240px;}
 .manual input{flex:1;}
 .manual button{background:#1f6feb;color:white;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;}
 .manual button:hover{background:#388bfd;}
 .status{color:#7ee787;font-size:12px;margin-left:10px;}
 .status.err{color:#ff7b72;}
</style></head><body>
<h1>📊 Agent Sandbox — 실시간 모니터링</h1>
<div class="lead">
 sandbox 경계 = workdir 경로  ·  tool 호출 흐름 = 활동 로그  ·  세션 정리 = 카드 사라짐  ·  격리 = 세션 카드 분리
</div>
<div class="controls">
  <button id="demo-btn" onclick="startDemo()">🚀 데모 테스트셋 시작 (demo-A · demo-B 동시 진행, 각 10 메시지)</button>
  <span id="demo-status" class="status"></span>
</div>
<div class="manual">
  <form onsubmit="sendChat(event)">
    <select id="manual-sid-select" title="대상 세션">
      <option value="__new__">+ 새 세션 (자동 ID)</option>
    </select>
    <input id="manual-msg" placeholder="발화문 (예: 'todo.txt에 할일을 써줘')" required>
    <button type="submit">전송</button>
  </form>
  <span id="chat-status" class="status"></span>
</div>
<div class="stats" id="stats">로딩...</div>
<div class="sbroot" id="sbroot">로딩...</div>
<div class="grid" id="sessions"></div>
<div class="updated" id="updated"></div>
<script>
function fmtTs(ts){
  const d = new Date(ts*1000);
  return d.toTimeString().slice(0,8);
}


// session_id 자체가 색 이름 (red, blue, yellow, ...)
const _COLORS = {
  red:    '#f85149',
  blue:   '#58a6ff',
  yellow: '#f1c40f',
  pink:   '#ff80bf',
  purple: '#bc8cff',
  orange: '#ffa657',
  cyan:   '#39d0d8',
  green:  '#7ee787',
};

function colorFor(sid){
  // sid가 "red" 또는 "red-2" 형태일 수 있음
  const base = (sid || '').split('-')[0];
  return _COLORS[base] || '#8b949e';
}

function colorNameFor(sid){
  const base = (sid || '').split('-')[0];
  return base in _COLORS ? sid : '';
}

function assignColors(_activeIds){ /* no-op — sid 자체가 색이라 매핑 불필요 */ }

async function startDemo(){
  const btn = document.getElementById('demo-btn');
  const st = document.getElementById('demo-status');
  btn.disabled = true;
  st.textContent = '시작 요청...';
  st.className = 'status';
  try {
    const r = await fetch('/demo/start', {method:'POST'}).then(r => r.json());
    if (r.status === 'started') {
      st.textContent = `▶ 진행 중 — 세션: ${r.sessions.join(', ')}, 각 ${r.messages_each} 메시지`;
    } else if (r.status === 'already_running') {
      st.textContent = '⚠ 이미 진행 중입니다';
    } else {
      st.textContent = JSON.stringify(r);
    }
  } catch(e){ st.textContent = '에러: ' + e; st.className = 'status err'; }
  // 데모 진행 중인 동안 버튼 잠금, /demo/status 폴링하여 끝나면 풀기
  const poll = setInterval(async () => {
    const s = await fetch('/demo/status').then(r => r.json()).catch(()=>null);
    if (s && !s.running) {
      btn.disabled = false;
      st.textContent = '✓ 데모 완료';
      clearInterval(poll);
    }
  }, 2000);
}

async function nextColorSid(){
  const r = await fetch('/sandbox/next_id').then(r => r.json());
  return r.session_id;
}

async function sendChat(ev){
  ev.preventDefault();
  const sel = document.getElementById('manual-sid-select');
  const msg = document.getElementById('manual-msg').value.trim();
  const st = document.getElementById('chat-status');
  if (!msg) return;
  let sid = sel.value;
  let isNew = false;
  if (sid === '__new__') {
    sid = await nextColorSid();
    isNew = true;
  }
  st.textContent = `→ ${sid}${isNew ? ' (신규)' : ' (이어가기)'} 처리 중...`;
  st.className = 'status';
  document.getElementById('manual-msg').value = '';
  try {
    const r = await fetch('/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({session_id: sid, message: msg}),
    }).then(r => r.json());
    st.textContent = `✓ ${sid}: ${r.elapsed_ms}ms`;
  } catch(e){
    st.textContent = '에러: ' + e; st.className = 'status err';
  }
}

function refreshSidSelect(activeIds){
  const sel = document.getElementById('manual-sid-select');
  const cur = sel.value;
  const opts = ['<option value="__new__">+ 새 세션 (자동 ID)</option>'];
  for (const sid of activeIds){
    const cname = colorNameFor(sid) || '—';
    const shortSid = sid.length > 16 ? sid.slice(0, 8) + '…' : sid;
    opts.push(`<option value="${sid}" data-color="${colorFor(sid)}">● ${cname.toUpperCase()} — ${shortSid}</option>`);
  }
  sel.innerHTML = opts.join('');
  for (const opt of sel.options){
    const c = opt.getAttribute('data-color');
    if (c) opt.style.color = c;
  }
  if (cur && (cur === '__new__' || activeIds.includes(cur))) {
    sel.value = cur;
  }
}

async function fetchAll() {
  const [health, sessions, sbtree] = await Promise.all([
    fetch('/health').then(r => r.json()),
    fetch('/sessions').then(r => r.json()),
    fetch('/sandbox/tree').then(r => r.json()).catch(() => ({dirs:[], workspace:''})),
  ]);
  const sids = sessions.map(s => s.session_id);
  assignColors(sids);
  const [filesArr, actArr] = await Promise.all([
    Promise.all(sids.map(sid => fetch('/sessions/' + encodeURIComponent(sid) + '/files').then(r => r.json()).catch(() => ({files:[]})))),
    Promise.all(sids.map(sid => fetch('/sessions/' + encodeURIComponent(sid) + '/activity').then(r => r.json()).catch(() => ({activity:[]})))),
  ]);

  document.getElementById('stats').innerHTML =
    `<span>활성 세션: <b>${health.active_sessions}</b> / ${health.max_sessions}</span>` +
    `<span>총 요청: <b>${health.total_requests}</b></span>` +
    `<span>디스크: <b>${health.total_workdir_kb} KB</b></span>`;

  // sandbox 최상위 트리 — 색을 1차 식별자
  const dirsHtml = sbtree.dirs.length === 0
    ? '<span class="empty">(디렉토리 없음)</span>'
    : sbtree.dirs.map(d => {
        const cls = d.active ? 'active' : 'orphan';
        const c = d.active ? colorFor(d.name) : '#8b949e';
        const cname = d.active ? colorNameFor(d.name) : 'orphan';
        const shortName = d.name.length > 16 ? d.name.slice(0, 8) + '…' : d.name;
        return `<div class="dir ${cls}" style="border-left:3px solid ${c};">
          <span class="dot" style="color:${c};font-size:14px;">●</span>
          <b style="color:${c};text-transform:capitalize;">${cname}</b>
          <span style="color:#6e7681;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;" title="${d.name}">${shortName}</span>
          <span style="color:#6e7681;">(${d.file_count}f, ${(d.size_bytes/1024).toFixed(1)} KB)</span>
        </div>`;
      }).join('');
  document.getElementById('sbroot').innerHTML =
    `<div class="title">📁 Sandbox 최상위 디렉토리</div>` +
    `<div class="path">${sbtree.workspace || '/tmp/sandbox_workspace'}</div>` +
    `<div class="dirs">${dirsHtml}</div>`;

  const html = sessions.map((s, i) => {
    const files = filesArr[i].files || [];
    const acts = (actArr[i].activity || []).slice().reverse();
    const tree = files.length === 0
      ? `<span class="empty">(파일 없음)</span>`
      : `<ul class="tree">${files.map(f => `<li>📄 ${f.path}  <span style="color:#6e7681;">(${f.size}B)</span></li>`).join('')}</ul>`;
    const activity = acts.length === 0
      ? `<span class="empty">(활동 없음)</span>`
      : `<ul class="activity">${acts.slice(0,15).map(a => {
          const cls = `act-${a.action}`;
          const stcls = a.status !== 'ok' ? `status-${a.status.split('=')[0].replace(/[^a-z]/g,'')}` : '';
          return `<li><span class="ts">${fmtTs(a.ts)}</span><span class="act ${cls}">${a.action}</span><span class="target ${stcls}">${a.target}${a.detail ? ' — ' + a.detail : ''}${a.status !== 'ok' ? ' [' + a.status + ']' : ''}</span></li>`;
        }).join('')}</ul>`;
    const c = colorFor(s.session_id);
    const cname = colorNameFor(s.session_id) || '—';
    // session_id 표시 — 긴 UUID는 8자만
    const shortSid = s.session_id.length > 16 ? s.session_id.slice(0, 8) + '…' : s.session_id;
    // 현재(또는 마지막) 발화문 + 진행 중 tool
    let currentBlock = '';
    if (s.current_message) {
      const stCls = s.processing ? 'running' : 'done';
      const stTxt = s.processing ? '▶ 진행 중' : '✓ 완료';
      let toolNow = '';
      if (s.last_action) {
        const la = s.last_action;
        const pre = s.processing ? '🔧 진행 tool' : '🔧 마지막 tool';
        toolNow = `<div class="tool-now">${pre}: <b>${la.action}</b> ${la.target}${la.status !== 'ok' ? ' [' + la.status + ']' : ''}</div>`;
      }
      currentBlock = `<div class="current">
        <div class="lbl"><span class="${stCls}">${stTxt}</span> · 발화문</div>
        <div class="msg">"${(s.current_message || '').replace(/</g,'&lt;')}"</div>
        ${toolNow}
      </div>`;
    }
    return `<div class="session" style="border-left-color:${c};">
      <h2 style="color:${c};"><span class="dot">●</span>${cname}</h2>
      <div class="sid" title="${s.session_id}">${shortSid}</div>
      <div class="workdir">${s.workdir}</div>
      <div class="meta">
        <span class="pill">요청 ${s.request_count}</span>
        <span class="pill">생성 ${s.age_seconds.toFixed(0)}s 전</span>
        <span class="pill">유휴 ${s.idle_seconds.toFixed(0)}s</span>
        <span class="pill">${s.workdir_size_kb} KB</span>
      </div>
      ${currentBlock}
      <div class="section">📂 파일</div>
      ${tree}
      <div class="section">⚡ 활동 (최근 → 과거)</div>
      ${activity}
    </div>`;
  }).join('');
  document.getElementById('sessions').innerHTML = html ||
    '<div class="session"><span class="empty">활성 세션 없음. 위 버튼이나 폼으로 시작하세요.</span></div>';
  refreshSidSelect(sids);
  document.getElementById('updated').textContent = '갱신: ' + new Date().toLocaleTimeString() + '  (3초 자동 갱신)';
}
fetchAll();
setInterval(fetchAll, 3000);
</script></body></html>"""


@app.get("/monitor", response_class=HTMLResponse)
def monitor_page():
    return _MONITOR_HTML


if __name__ == "__main__":
    import uvicorn
    # Chainlit 채팅을 같은 프로세스에 mount → SessionManager 공유
    try:
        from chainlit.utils import mount_chainlit
        mount_chainlit(app=app, target=os.path.join(os.path.dirname(__file__), "chat.py"), path="/chat")
        print("[api] Chainlit mounted at /chat", flush=True)
    except Exception as e:
        print(f"[api] Chainlit mount 실패: {e}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)

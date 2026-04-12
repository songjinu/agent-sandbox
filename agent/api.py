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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from session_manager import SessionManager

app = FastAPI(title="Agent Sandbox API")
manager = SessionManager()


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
        result = session.graph.invoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config={"configurable": {"thread_id": req.session_id}},
        )
        session.touch()
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
    return [
        {
            "session_id": info.session_id,
            "request_count": info.request_count,
            "idle_seconds": round(info.idle_seconds, 1),
            "workdir_size_kb": info.workdir_size_kb,
        }
        for info in manager.list_sessions()
    ]


@app.delete("/sessions/{session_id}")
def close_session(session_id: str):
    manager.close(session_id)
    return {"closed": session_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

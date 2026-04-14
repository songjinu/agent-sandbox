"""
세션 기반 Agent/Sandbox 관리
- 세션 ID가 같으면 Agent/Sandbox 재사용
- 세션 타임아웃 시 자동 정리
- 최대 세션 수 제한
- 세션 목록 조회
- 세션별 리소스 사용량 모니터링
- 스레드 안전
"""

import os
import time
import threading
from dataclasses import dataclass, field

from llm_config import build_llm

SESSION_TIMEOUT = 300   # 5분 비활동 시 세션 소멸
MAX_SESSIONS = 50       # 최대 동시 세션 수
SKILLS_PATH = os.environ.get("SKILLS_PATH", "/app/skills/")


@dataclass
class SessionInfo:
    """세션 상태 및 리소스 정보"""
    session_id: str
    created_at: float
    last_active: float
    request_count: int
    workdir: str

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def workdir_size_kb(self) -> float:
        """sandbox 디렉토리 사용량 (KB)"""
        try:
            total = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, files in os.walk(self.workdir)
                for f in files
            )
            return round(total / 1024, 1)
        except Exception:
            return 0.0


@dataclass
class Session:
    session_id: str
    graph: object
    sandbox: object
    llm_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    request_count: int = 0

    def touch(self):
        self.last_active = time.time()
        self.request_count += 1

    def switch_llm(self, llm_id: str | None):
        """LLM 교체 — sandbox/파일은 유지, graph만 재생성"""
        self.graph = _create_graph(build_llm(llm_id), self.sandbox)
        self.llm_id = llm_id

    def is_expired(self) -> bool:
        return time.time() - self.last_active > SESSION_TIMEOUT

    def info(self) -> SessionInfo:
        return SessionInfo(
            session_id=self.session_id,
            created_at=self.created_at,
            last_active=self.last_active,
            request_count=self.request_count,
            workdir=self.sandbox.workdir,
        )


def _create_graph(llm, sandbox):
    from deepagents.graph import create_deep_agent
    return create_deep_agent(model=llm, backend=sandbox, skills=[SKILLS_PATH])


class SessionManager:
    def __init__(self, max_sessions: int = MAX_SESSIONS, session_timeout: int = SESSION_TIMEOUT):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def get_or_create(self, session_id: str, llm_id: str | None = None) -> Session:
        with self._lock:
            # 기존 세션 재사용
            if session_id in self._sessions:
                session = self._sessions[session_id]
                if llm_id is not None and llm_id != session.llm_id:
                    session.switch_llm(llm_id)
                session.touch()
                return session

            # 최대 세션 수 초과 확인
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError(
                    f"최대 세션 수 초과 ({self.max_sessions}). 나중에 다시 시도하세요."
                )

            # 새 세션 생성
            from deepagents.graph import create_deep_agent
            from process_sandbox import ProcessSandboxBackend

            sandbox = ProcessSandboxBackend(session_id)
            llm = build_llm(llm_id)
            graph = _create_graph(llm, sandbox)

            session = Session(session_id=session_id, graph=graph, sandbox=sandbox, llm_id=llm_id)
            session.touch()
            self._sessions[session_id] = session
            return session

    def close(self, session_id: str):
        """세션 명시적 종료"""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].sandbox.cleanup()
                del self._sessions[session_id]

    def list_sessions(self) -> list[SessionInfo]:
        """전체 세션 목록 및 상태 반환"""
        with self._lock:
            return [s.info() for s in self._sessions.values()]

    def stats(self) -> dict:
        """전체 리소스 사용 요약"""
        with self._lock:
            sessions = list(self._sessions.values())
        infos = [s.info() for s in sessions]
        return {
            "active_sessions": len(sessions),
            "max_sessions": self.max_sessions,
            "total_requests": sum(i.request_count for i in infos),
            "total_workdir_kb": sum(i.workdir_size_kb for i in infos),
        }

    def _cleanup_loop(self):
        while True:
            time.sleep(60)
            with self._lock:
                expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
                for sid in expired:
                    self._sessions[sid].sandbox.cleanup()
                    del self._sessions[sid]

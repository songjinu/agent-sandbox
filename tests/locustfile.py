"""
locust 성능 테스트
- 실행: locust -f tests/locustfile.py --host http://localhost:8000
- 웹 UI: http://localhost:8089

시나리오:
  1. 세션 생성 후 파일 작성 → 읽기 → python 실행 (tool 3회 호출)
  2. 세션 재사용 반복
  3. 세션 종료
"""

import uuid
from locust import HttpUser, task, between, events


class AgentUser(HttpUser):
    wait_time = between(1, 3)   # 요청 사이 대기 (초)

    def on_start(self):
        """세션 ID 발급 — 유저별 고유 세션"""
        self.session_id = f"perf-{uuid.uuid4().hex[:8]}"

    def on_stop(self):
        """세션 종료"""
        self.client.delete(f"/sessions/{self.session_id}")

    @task(3)
    def tool_multi_step(self):
        """파일 생성 → 읽기 → python 실행 (tool 3회)"""
        steps = [
            "result.txt 파일에 'hello from agent' 라고 써줘",
            "result.txt 파일 내용을 읽어줘",
            "python3 -c \"print(2**10)\" 를 실행해줘",
        ]
        for msg in steps:
            with self.client.post(
                "/chat",
                json={"session_id": self.session_id, "message": msg},
                catch_response=True,
                name="/chat [multi-step]",
            ) as resp:
                if resp.status_code == 200:
                    elapsed = resp.json().get("elapsed_ms", 0)
                    resp.success()
                elif resp.status_code == 503:
                    resp.failure(f"세션 한계 초과: {resp.text}")
                else:
                    resp.failure(f"오류 {resp.status_code}: {resp.text[:100]}")

    @task(1)
    def health_check(self):
        """서버 상태 확인"""
        self.client.get("/health", name="/health")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n[locust] 성능 테스트 시작")
    print("  시나리오: 세션별 파일 생성/읽기/python 실행 반복")
    print("  목표: 동시 세션 10 → 한계까지 단계적 증가\n")

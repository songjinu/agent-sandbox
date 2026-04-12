# 성능 테스트 가이드

## 구조

- **API 서버** (`agent/api.py`) — FastAPI, 포트 8000
- **로컬 부하 테스트** — locust
- **공식 부하 테스트** — JMeter (JMX 별도 제작)

---

## 사전 준비

### API 서버 실행

```bash
# 로컬 (Ollama)
PYTHONPATH=agent python agent/api.py

# 또는 Docker
./run.sh
```

서버 확인:
```bash
curl http://localhost:8000/health
```

### LLM 설정

`llm_config.json` 파일을 미리 작성하거나 UI(`http://localhost:7860`) 설정 탭에서 등록.

```json
{
  "default": "ollama-local",
  "llms": {
    "ollama-local": {
      "base_url": "http://172.19.16.1:11434/v1",
      "model": "glm-5:cloud",
      "api_key": "ollama"
    },
    "vllm-server": {
      "base_url": "http://vllm-server:8000/v1",
      "model": "your-model",
      "api_key": "your-key"
    }
  }
}
```

---

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/chat` | agent 호출 |
| GET | `/health` | 서버/세션 상태 |
| GET | `/sessions` | 세션 목록 |
| DELETE | `/sessions/{id}` | 세션 강제 종료 |

### POST /chat

```json
// Request
{
  "session_id": "user-001",
  "message": "hello.txt 파일에 hi 라고 써줘",
  "llm_id": "ollama-local"   // 생략 시 default 사용
}

// Response
{
  "session_id": "user-001",
  "response": "hello.txt 파일에 'hi'라고 작성했습니다.",
  "elapsed_ms": 12059
}
```

---

## locust 부하 테스트

### 설치

```bash
pip install locust
```

### 실행

```bash
# 웹 UI 모드 (http://localhost:8089)
locust -f tests/locustfile.py --host http://localhost:8000

# Headless 모드
locust -f tests/locustfile.py \
  --host http://localhost:8000 \
  --headless \
  --users 10 \
  --spawn-rate 2 \
  --run-time 60s \
  --only-summary
```

### 시나리오

세션별로 아래 3단계 tool 호출을 반복:

1. `result.txt` 파일 생성
2. `result.txt` 파일 읽기
3. `python3 -c "print(2**10)"` 실행

### 단계적 부하 증가 (한계 측정)

```bash
# 10 → 20 → 50 순으로 단계 테스트
for USERS in 10 20 50; do
  echo "=== users: $USERS ==="
  locust -f tests/locustfile.py \
    --host http://localhost:8000 \
    --headless \
    --users $USERS \
    --spawn-rate 5 \
    --run-time 60s \
    --only-summary
done
```

---

## JMeter 설정 참고

| 항목 | 값 |
|------|-----|
| Protocol | HTTP |
| Host | `localhost` (또는 서버 IP) |
| Port | `8000` |
| Method | POST |
| Path | `/chat` |
| Content-Type | `application/json` |
| Body | `{"session_id": "${SESSION_ID}", "message": "${MESSAGE}"}` |

`SESSION_ID`는 Thread Group별 고유값 사용 권장 (UUID 함수 등).

---

## 측정 지표

| 지표 | 확인 방법 |
|------|----------|
| 응답 레이턴시 | locust/JMeter 리포트, 또는 응답의 `elapsed_ms` |
| 동시 세션 한계 | `max_sessions` 초과 시 503 에러율 증가 |
| Sandbox 자원 | `GET /sessions` → `workdir_size_kb` |
| Pod 자원 | `docker stats` 또는 K8s metrics-server |

---

## 알려진 제약

- **로컬 Ollama**: 단일 CPU/GPU 처리 → 동시 요청이 순차 처리됨. 레이턴시 측정보다 에러율/한계 측정에 집중.
- **vLLM 멀티 GPU**: 실제 동시 처리 가능. 의미 있는 처리량 측정 가능.
- **세션 LLM 교체**: 기존 세션에 다른 `llm_id` 전달 시 graph 재생성 (sandbox 파일 유지).

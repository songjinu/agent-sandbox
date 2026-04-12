# Agent Sandbox

LangGraph 기반 Agent 서비스를 위한 프로세스 샌드박스 구현 및 테스트 환경입니다.

## 구조

```
agent-sandbox/
├── Dockerfile
├── requirements.txt
├── build.sh                    # 이미지 빌드
├── run.sh                      # 컨테이너 실행
├── agent/                      # 앱 소스
│   ├── process_sandbox.py      # 프로세스 기반 샌드박스 (자체 구현)
│   ├── session_manager.py      # 세션 관리 (생성/재사용/타임아웃)
│   ├── llm_config.py           # LLM 설정 관리 (다중 ID)
│   ├── api.py                  # FastAPI HTTP API 서버
│   └── ui.py                   # Gradio UI
├── tests/                      # 테스트
│   ├── sandbox_direct_test.py          # 샌드박스 기능 직접 테스트 (LLM 없이)
│   ├── sandbox_test.py                 # 프로세스 샌드박스 기본 테스트
│   ├── session_test.py                 # 세션 관리 테스트
│   ├── llm_config_test.py              # LLM 설정 테스트
│   ├── locustfile.py                   # locust 성능 테스트 시나리오
│   └── deepagents_process_sandbox_test.py  # deepagents + LLM 통합 테스트
└── docs/                       # 문서
    └── performance_test.md     # 성능 테스트 가이드
```

## 아키텍처

### 샌드박스

deepagents의 Sandbox 인터페이스를 자체 구현한 **프로세스 기반 샌드박스**입니다.
외부 샌드박스 서비스(Daytona, E2B 등) 없이 Agent Pod 내에서 직접 동작합니다.

- **격리**: 세션별 독립 디렉토리 (`/tmp/sandbox_workspace/{session_id}/`)
- **리소스 제한**: CPU 시간 30초, 메모리 256MB
- **기능**: 명령 실행, 파일 생성/읽기, 타임아웃 처리
- **세션 재사용**: 동일 세션 ID면 Agent/Sandbox 유지, 비활동 5분 후 자동 소멸
- **스케일 아웃**: 단일 Pod 내 다수 세션 처리, K8s HPA로 Pod 증설

### LLM 연동

`llm_config.json` 으로 다중 LLM을 ID별로 관리합니다.
Ollama, vLLM, OpenRouter 등 OpenAI 호환 API를 동일하게 지원합니다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `LLM_BASE_URL` | LLM 서버 주소 | `http://172.19.16.1:11434/v1` |
| `LLM_MODEL` | 모델명 | `glm-5:cloud` |
| `LLM_API_KEY` | API 키 | `ollama` |

## 빠른 시작

### 빌드

```bash
./build.sh
```

### 실행

```bash
# Ollama (로컬 테스트)
./run.sh

# vLLM (테스트 서버)
LLM_PROVIDER=vllm \
LLM_BASE_URL=http://vllm-server:8000/v1 \
LLM_MODEL=your-model \
LLM_API_KEY=your-key \
./run.sh
```

브라우저에서 `http://localhost:7861` 접속

### UI 구성

- **채팅**: 세션 ID + LLM 선택 후 Agent에게 요청
- **모니터링**: 활성 세션 목록, 요청수, 유휴시간, 디스크 사용량
- **설정**: 세션 타임아웃/최대 수 조정, LLM 설정 CRUD

## 테스트

```bash
# LLM 없이 샌드박스 기능 테스트 (파일 생성, Python 실행, 커맨드, 타임아웃, 격리)
~/.local/share/uv/tools/deepagents-cli/bin/python3 tests/sandbox_direct_test.py

# 세션 관리 테스트
~/.local/share/uv/tools/deepagents-cli/bin/python3 tests/session_test.py
```

## 성능 테스트 (실험적)

FastAPI 기반 HTTP API 서버와 locust/JMeter를 이용한 부하 테스트를 지원합니다.

> [성능 테스트 가이드](docs/performance_test.md)

## 요구사항

- Docker
- Python 3.13+
- Ollama 또는 vLLM 서버

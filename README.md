# Agent Sandbox

LangGraph 기반 Agent 서비스를 위한 프로세스 샌드박스 구현 및 테스트 환경입니다.

## 구조

```
agent-sandbox/
├── Dockerfile
├── requirements.txt
├── build.sh            # 이미지 빌드
├── run.sh              # 컨테이너 실행
├── agent/              # 앱 소스
│   ├── process_sandbox.py   # 프로세스 기반 샌드박스 백엔드
│   ├── session_manager.py   # 세션 관리 (생성/재사용/타임아웃)
│   └── ui.py                # Gradio UI
├── tests/              # 테스트
│   ├── sandbox_direct_test.py       # 샌드박스 기능 직접 테스트 (LLM 없이)
│   ├── sandbox_test.py              # 프로세스 샌드박스 기본 테스트
│   ├── session_test.py              # 세션 관리 테스트
│   └── deepagents_process_sandbox_test.py  # deepagents + LLM 통합 테스트
└── docs/               # 문서
```

## 아키텍처

### 샌드박스 설계

- **격리 방식**: 요청별 프로세스 + 디렉토리 분리 (`/tmp/sandbox_workspace/{session_id}/`)
- **리소스 제한**: CPU 시간 30초, 메모리 256MB (Linux `resource` 모듈)
- **세션 관리**: 동일 세션 ID면 Agent/Sandbox 재사용, 비활동 5분 후 자동 소멸
- **동시 처리**: 단일 Pod 내 다수 세션 처리, K8s HPA로 Pod 스케일 아웃

### LLM 연동

환경변수로 LLM 프로바이더 전환 가능:

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `LLM_PROVIDER` | `ollama` 또는 `vllm` | `ollama` |
| `LLM_BASE_URL` | LLM 서버 주소 | `http://172.19.16.1:11434` |
| `LLM_MODEL` | 모델명 | `glm-5:cloud` |
| `LLM_API_KEY` | API 키 | `dummy` |

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

- **채팅**: 세션 ID 입력 후 Agent에게 요청
- **모니터링**: 활성 세션 목록, 요청수, 유휴시간, 디스크 사용량
- **설정**: 최대 세션 수, 타임아웃 조정

## 테스트

```bash
# LLM 없이 샌드박스 기능 테스트 (파일 생성, Python 실행, 커맨드, 타임아웃, 격리)
~/.local/share/uv/tools/deepagents-cli/bin/python3 tests/sandbox_direct_test.py

# 세션 관리 테스트
~/.local/share/uv/tools/deepagents-cli/bin/python3 tests/session_test.py
```

## 요구사항

- Docker
- Python 3.13+
- Ollama 또는 vLLM 서버

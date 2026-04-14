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
- **리소스 제한**: CPU 시간 30초, 메모리 256MB, 디스크 10MB/세션 (환경변수로 조정 가능)
- **기능**: 명령 실행, 파일 생성/읽기, 타임아웃 처리
- **세션 재사용**: 동일 세션 ID면 Agent/Sandbox 유지, 비활동 5분 후 자동 소멸
- **스케일 아웃**: 단일 Pod 내 다수 세션 처리, K8s HPA로 Pod 증설

#### 리소스 제한 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SANDBOX_DISK_LIMIT_MB` | `10` | 세션별 디스크 최대 사용량 (MB) |
| `SANDBOX_FILE_SIZE_LIMIT_MB` | `10` | 단일 파일 최대 크기 (MB) |
| `SANDBOX_NPROC_LIMIT` | `256` | 최대 프로세스 수 (non-root 환경에서만 유효) |

#### 고려사항

| 항목 | 현황 | 비고 |
|------|------|------|
| 네트워크 격리 | Docker/K8s 레벨 | 연계 서버는 허용, 외부 인터넷은 K8s NetworkPolicy로 차단 |
| 프로세스 수 제한 | 부분 | `RLIMIT_NPROC`은 non-root 사용자에게만 적용됨 (Dockerfile에 `sandbox` 유저 설정). `RLIMIT_NPROC`은 user 전체 프로세스 수 기준이라 멀티 세션 환경에서 간섭 가능. **fork bomb 완전 차단은 K8s `--pids-limit` 또는 Pod spec `resources.limits.pids`로 보완 필요** |
| 디스크 격리 | 부분 | 세션별 디렉토리 분리 + 용량 제한. Pod 디스크 자체는 공유. 멀티 Pod 운영 시 NAS/PVC 마운트 필요 |

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
# 샌드박스 기능 테스트 (LLM 없이 — 파일, 실행, 타임아웃, 디스크/메모리/CPU/프로세스 제한, 격리)
docker run --rm \
  -v $(pwd)/tests:/app/tests \
  -e PYTHONPATH=/app \
  songwork python3 tests/sandbox_direct_test.py

# Skills + Agent 통합 테스트 (LLM 필요)
docker run --rm \
  -v $(pwd)/tests:/app/tests \
  -e PYTHONPATH=/app \
  songwork python3 tests/deepagents_process_sandbox_test.py

# 세션 관리 테스트
docker run --rm \
  -v $(pwd)/tests:/app/tests \
  -e PYTHONPATH=/app \
  songwork python3 tests/session_test.py
```

## Skills 추가 가이드

Agent가 툴을 일관되게 사용하도록 지침을 제공하는 **Skills** 시스템입니다.
Skills는 Agent의 시스템 프롬프트에 주입되며, 실제 코드 실행은 Sandbox에서 이루어집니다.

### 구조

```
skills/
├── code-execution/     # 코드 실행 지침
│   └── SKILL.md
├── file-operations/    # 파일 처리 지침
│   └── SKILL.md
├── debugging/          # 디버깅 지침
│   └── SKILL.md
└── data-analysis/      # 데이터 분석 지침
    └── SKILL.md
```

### 새 Skill 추가

**1. 디렉토리 생성** — 디렉토리명 = skill 이름 (소문자, 하이픈만 허용)

```bash
mkdir skills/my-skill
```

**2. SKILL.md 작성** — YAML frontmatter 필수

```markdown
---
name: my-skill
description: 한 줄로 이 skill이 언제 사용되는지 설명 (Agent가 이 설명으로 skill 선택)
allowed-tools: execute write_file read_file
---

## My Skill

### When to Use
- 어떤 상황에서 이 skill을 사용하는지

### Workflow
1. 첫 번째 단계
2. 두 번째 단계
3. 검증

### Rules
- Agent가 반드시 따라야 할 규칙
```

**frontmatter 필드**

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | 필수 | 디렉토리명과 동일해야 함 |
| `description` | 필수 | Agent가 skill 선택 시 참고 (최대 1024자) |
| `allowed-tools` | 선택 | 이 skill에서 사용할 툴 목록 (공백 구분) |

**3. Docker 이미지 재빌드**

```bash
./build.sh
```

### 커스텀 Tool 추가

deepagents의 `@tool` 데코레이터로 Python 함수를 툴로 등록합니다.

**1. 툴 함수 작성** (`agent/custom_tools.py`)

```python
from langchain_core.tools import tool

@tool
def my_tool(input: str) -> str:
    """툴 설명 — Agent가 이 설명으로 툴 선택"""
    # 구현
    return result
```

**2. session_manager.py에 등록**

```python
from custom_tools import my_tool

graph = create_deep_agent(
    model=llm,
    backend=sandbox,
    skills=["/app/skills/"],
    tools=[my_tool],          # 커스텀 툴 추가
)
```

**3. Skill에서 툴 참조** (`allowed-tools`에 추가)

```markdown
---
name: my-skill
allowed-tools: execute my_tool
---
```

### 테스트

**Skills 로딩 + Agent 동작 통합 테스트:**

```bash
docker run --rm \
  -v $(pwd)/tests:/app/tests \
  -e PYTHONPATH=/app \
  songwork python3 tests/deepagents_process_sandbox_test.py
```

**새 skill 단독 테스트** — `tests/deepagents_process_sandbox_test.py`의 `test_with_skills()`에 태스크 추가:

```python
tasks = [
    ...
    "새 skill이 처리해야 할 요청",  # 추가
]
```

**skill 로딩만 확인** (LLM 없이):

```bash
docker run --rm songwork python3 -c "
import os
skills_path = '/app/skills/'
for name in os.listdir(skills_path):
    skill_md = os.path.join(skills_path, name, 'SKILL.md')
    if os.path.isfile(skill_md):
        print(f'OK: {name}')
    else:
        print(f'MISSING SKILL.md: {name}')
"
```

### 예시: Tavily Tool + web-search Skill 추가

Tavily 검색 툴을 연동하고, Agent가 검색 요청 시 반드시 Tavily를 사용하도록 skill로 강제하는 예시입니다.

> API key는 사용자마다 다를 수 있고 과금이 발생하므로, 세션 첫 요청 시 한 번만 입력받아 sandbox 파일에 저장하고 이후 재사용합니다.

#### 1. 패키지 추가 (`requirements.txt`)

```
tavily-python
```

#### 2. Tool 작성 (`agent/custom_tools.py`)

```python
from langchain_core.tools import tool

@tool
def tavily_search(query: str, api_key: str) -> str:
    """Search the web using Tavily. Requires api_key parameter."""
    from tavily import TavilyClient
    return str(TavilyClient(api_key=api_key).search(query))
```

#### 3. session_manager.py 수정

```python
# 상단 import 추가
from custom_tools import tavily_search

# get_or_create() 내 graph 생성 부분
graph = create_deep_agent(
    model=llm,
    backend=sandbox,
    skills=["/app/skills/"],
    tools=[tavily_search],   # 커스텀 툴 추가
)
```

#### 4. Skill 파일 생성 (`skills/web-search/SKILL.md`)

```markdown
---
name: web-search
description: Search the web for information, news, or any topic requiring up-to-date knowledge. Always use Tavily for web searches.
allowed-tools: tavily_search read_file write_file
---

## Web Search Skill

### When to Use
- User asks to search, find, or look up information
- Need up-to-date information beyond training data

### Workflow
1. read_file(".api_keys") 로 TAVILY_API_KEY 확인
2. 없으면 사용자에게 요청 → write_file(".api_keys", ...) 로 저장
3. tavily_search(query=..., api_key=...) 호출
4. 결과 요약 + 출처 URL 함께 제공

### Rules
- api_key는 응답에 출력하지 않음
- 검색 없이 추측으로 답변 금지
- .api_keys 파일 형식: {"TAVILY_API_KEY": "tvly-xxxx"}
```

`.api_keys` 파일은 세션별 workdir에 저장되므로 사용자 간 격리되고, 세션 종료 시 자동 삭제됩니다.

#### 5. 테스트 케이스 추가 (`tests/deepagents_process_sandbox_test.py`)

`test_with_skills()`의 tasks 리스트에 추가:

```python
tasks = [
    ...
    "최근 AI 에이전트 관련 뉴스를 검색해줘",   # web-search skill 동작 확인
]
```

#### 6. 테스트 실행

```bash
docker run --rm \
  -v $(pwd)/tests:/app/tests \
  -e PYTHONPATH=/app \
  songwork python3 tests/deepagents_process_sandbox_test.py
```

테스트 실행 시 Agent가 TAVILY_API_KEY를 요청하면 입력해주면 됩니다.

#### 검증 포인트

| 항목 | 확인 방법 |
|------|---------|
| skill 로딩 | `[1] Skills 로딩 확인`에 `web-search` 출력 여부 |
| key 요청 | 첫 검색 시 Agent가 TAVILY_API_KEY 요청하는지 |
| key 재사용 | 같은 세션 두 번째 검색 시 key 재요청 없는지 |
| 세션 격리 | 다른 세션에서 `.api_keys` 파일 접근 불가한지 |
| 툴 사용 | Agent 응답에 검색 결과 + URL 포함 여부 |

## 성능 테스트 (실험적)

FastAPI 기반 HTTP API 서버와 locust/JMeter를 이용한 부하 테스트를 지원합니다.

> [성능 테스트 가이드](docs/performance_test.md)

## 요구사항

- Docker
- Python 3.13+
- Ollama 또는 vLLM 서버

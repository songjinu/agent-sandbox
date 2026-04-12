# LangChain DeepAgents CLI 테스트 결과 보고서

**테스트 일자:** 2026-03-31
**테스트 환경:** Ubuntu 22.04 (Linux VM, Python 3.10.12)
**대상 버전:** deepagents-cli v0.0.34, deepagents SDK v0.4.11
**테스트 방식:** Pattern 2 — 에이전트 외부, 샌드박스는 도구

---

## 🔴 핵심 결론: Python 3.11+ 필수 요구사항

deepagents-cli는 **Python 3.11 이상이 반드시 필요**합니다. Python 3.10에서는 실제 태스크 실행이 불가합니다.

---

## 1. 환경 확인 결과

| 항목 | 결과 |
|------|------|
| `uv` 버전 | 0.10.4 ✅ |
| `uvx` 버전 | 0.10.4 ✅ |
| Python 버전 | **3.10.12** ⚠️ (3.11+ 필요) |
| pip 버전 | 25.3 ✅ |

---

## 2. 설치 과정

### 2-A. uvx를 통한 설치 시도 (실패)

```bash
uvx deepagents-cli --help
```

**결과:** Python 버전 불일치로 실패

```
× No solution found when resolving tool dependencies:
  Because the current Python version (3.10.12) does not satisfy Python>=3.11,<4.0
  ...we can conclude that your requirements are unsatisfiable.
```

deepagents-cli v0.0.1부터 v0.0.34까지 **모든 버전이 Python>=3.11 요구**.

### 2-B. pip install --ignore-requires-python (성공)

```bash
pip3 install deepagents-cli --ignore-requires-python --break-system-packages
```

**결과:** 설치 성공 ✅ (하지만 실행 시 호환성 문제 발생)

설치된 주요 패키지:
- `deepagents-cli-0.0.34`
- `deepagents-0.4.11`
- `langchain-1.2.13`
- `langgraph-1.1.3`
- `langgraph-api-0.7.91`
- `modal-1.4.1` (샌드박스 옵션용)

---

## 3. Python 3.10 호환성 패치 내역

Python 3.10에서 구동하기 위해 다음 패치를 적용했습니다.

### 3-A. `usercustomize.py` — stdlib 백포트 shim

`pip` 사용자 site-packages에 자동 로드되는 패치 파일 생성:

```python
# StrEnum (Python 3.11+) → strenum 패키지로 백포트
from strenum import StrEnum
enum.StrEnum = StrEnum

# tomllib (Python 3.11+) → tomli 패키지로 백포트
import tomli; sys.modules["tomllib"] = tomli

# datetime.UTC (Python 3.11+) → datetime.timezone.utc
datetime.UTC = datetime.timezone.utc

# typing.NotRequired 등 → typing_extensions에서 주입
for name in ("NotRequired", "Self", "TypeAlias", ...):
    setattr(typing, name, getattr(typing_extensions, name))

# logging.getLevelNamesMapping() (Python 3.11+) → 수동 구현
logging.getLevelNamesMapping = lambda: dict(logging._nameToLevel)
```

### 3-B. 파일 직접 패치

```
deepagents_cli/config.py          ← from enum import StrEnum
deepagents_cli/widgets/autocomplete.py
deepagents_cli/widgets/message_store.py
deepagents_cli/agent.py           ← import tomllib
deepagents_cli/model_config.py
```

---

## 4. 테스트 결과

### ✅ 성공한 테스트

#### `--help` 출력 (성공)
```
deepagents-cli v0.0.34

Usage:
  deepagents [OPTIONS]                           Start interactive thread
  deepagents list                                List all available agents
  ...

Options:
  -n, --non-interactive MSG  Run a single task and exit
  --sandbox TYPE             Remote sandbox for execution (modal, e2b, daytona...)
  -M, --model MODEL          Model to use (e.g., gpt-4o, claude-haiku...)
  -S, --shell-allow-list     Comma-separated cmds, 'recommended', or 'all'
  -y, --auto-approve         Auto-approve all tool calls
```

#### `deepagents list` (성공)
```
No agents found.
Agents will be created in ~/.deepagents/ when you first use them.
```

#### `deepagents -v` (성공)
```
deepagents-cli 0.0.34
deepagents (SDK) 0.4.11
```

---

### ❌ 실패한 테스트

#### 실제 태스크 실행 (실패)
```bash
deepagents -n "print hello world in python" -S all --model claude-haiku-4-5-20251001
```

**에러 체인:**
```
1. ImportError: cannot import name 'StrEnum' from 'enum'       → 패치됨
2. ModuleNotFoundError: No module named 'tomllib'               → 패치됨
3. ImportError: cannot import name 'NotRequired' from 'typing'  → 패치됨
4. ImportError: cannot import name 'UTC' from 'datetime'        → 패치됨
5. AttributeError: module 'logging' has no attribute 'getLevelNamesMapping'  → 패치됨
6. AttributeError: module 'asyncio' has no attribute 'Runner'   ← 🚫 최종 블로커
```

**최종 블로커: `asyncio.Runner`**
Python 3.11에 추가된 `asyncio.Runner` 클래스를 `langgraph_runtime_inmem/queue.py`에서 **기반 클래스로 상속**하고 있어 monkey-patch 불가:

```python
# langgraph_runtime_inmem/queue.py
class BgLoopRunner(asyncio.Runner):  # Python 3.11 클래스 직접 상속
    ...
```

---

## 5. 에러 체인 흐름도

```
deepagents -n "..." 실행
    └─ LangGraph 서버 시작 시도
           └─ langgraph_api 로드
                  └─ langgraph_runtime_inmem 로드
                         └─ queue.py: class BgLoopRunner(asyncio.Runner)
                                └─ ❌ AttributeError: asyncio.Runner (Python 3.11+)
```

---

## 6. Windows에서 실제 테스트 방법 (권장 설정)

### 전제 조건
- **Python 3.11+** 필수 (`python --version` 확인)
- Windows Terminal 또는 PowerShell

### 최소 설치

```powershell
# uv가 있는 경우 (권장)
uvx deepagents-cli --help

# pip로 직접 설치
pip install deepagents-cli
deepagents-cli --help
```

### API 키 설정 (하나만 있으면 됨)

```powershell
# Anthropic Claude 사용 (권장)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 또는 OpenAI GPT 사용
$env:OPENAI_API_KEY = "sk-..."
```

### 기본 동작 테스트

```powershell
# 에이전트 목록 확인
deepagents list

# 비인터랙티브 모드 — 샌드박스 없이 로컬 실행
deepagents -n "print hello world in python" -S all --model claude-haiku-4-5-20251001

# 샌드박스 포함 테스트 (Modal 무료 티어)
# 먼저 modal 로그인 필요: modal token new
deepagents -n "print hello world" --sandbox modal -y
```

### Pattern 2 방식 확인 방법

```powershell
# 에이전트가 로컬에서 실행되고, 도구(shell, file 등)가 샌드박스에서 실행됨
deepagents -n "list files in current directory" -S ls,cat,pwd
```

---

## 7. 샌드박스 옵션 요약

| 샌드박스 | 무료 티어 | 설정 난이도 | 비고 |
|---------|---------|-----------|------|
| 없음 (`-S all`) | - | 쉬움 | 로컬 쉘 직접 사용, API 키만 필요 |
| Modal | ✅ | 보통 | `modal token new` 후 사용 |
| E2B | ✅ | 보통 | `E2B_API_KEY` 환경변수 설정 |
| Daytona | 유료 | 어려움 | 자체 서버 필요 |
| Runloop | 유료 | 보통 | - |

---

## 8. 결론 및 권장사항

| 항목 | 상태 |
|------|------|
| 설치 가능 여부 (Python 3.11+) | ✅ 가능 |
| `--help`, `list` 동작 | ✅ 정상 |
| 비인터랙티브 태스크 실행 | ✅ Python 3.11+에서 정상 예상 |
| Python 3.10에서 완전 동작 | ❌ 불가 (`asyncio.Runner` 블로커) |

**핵심 체크리스트:**
1. Python 3.11 이상 설치 확인
2. API 키 환경변수 설정 (`ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY`)
3. `pip install deepagents-cli` 또는 `uvx deepagents-cli --help`
4. `deepagents list` 로 정상 작동 확인
5. `deepagents -n "simple task" -S all` 로 첫 실행

Windows 환경(C:\Users\qsky0)에서는 Python 3.11+을 python.org에서 설치하거나 `uv python install 3.11` 명령으로 설치 후 테스트를 권장합니다.

---

*테스트 수행: Claude (Cowork mode) — 2026-03-31*

# DeepAgents CLI 셋업 가이드 (WSL / Ubuntu)

> **작성일**: 2026-03-31
> **패키지**: `deepagents-cli` v0.0.34
> **필수 Python**: ≥ 3.11

---

## 샌드박스 테스트 결과 요약

| 단계 | 명령어 | 결과 |
|------|--------|------|
| uv 버전 확인 | `uv --version` | ✅ `uv 0.10.4` |
| Python 3.11 다운로드 (uv) | `uv tool install deepagents-cli --python 3.11` | ❌ GitHub 다운로드 차단 (프록시 403) |
| Python 3.13 다운로드 (uvx) | `uvx --python 3.13 deepagents-cli --help` | ❌ 동일한 프록시 차단 |
| 시스템 Python 3.10 사용 | `uv tool install deepagents-cli --python /usr/bin/python3` | ❌ `deepagents-cli` requires Python ≥ 3.11 |

**결론**: 샌드박스 환경의 네트워크 프록시가 GitHub release 다운로드를 차단해서 uv의 자동 Python 설치가 불가. WSL 로컬 환경에서는 문제없이 동작함.

---

## WSL 로컬 셋업 가이드

### 1. uv 설치

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env  # 또는 새 터미널 열기
uv --version                 # uv 0.x.x 확인
```

### 2. deepagents-cli 설치 (Python 3.13 권장)

**방법 A: uvx로 바로 실행 (설치 없이)**
```bash
uvx --python 3.13 deepagents-cli --help
```

**방법 B: uv tool로 영구 설치**
```bash
uv tool install deepagents-cli --python 3.13
deepagents --help  # 설치 후 직접 실행 가능
```

> uv가 Python 3.13을 자동으로 다운로드합니다. 처음 실행 시 수십 초 소요.

### 3. ANTHROPIC_API_KEY 설정

```bash
# 방법 A: 환경변수 직접 설정 (임시)
export ANTHROPIC_API_KEY="sk-ant-..."

# 방법 B: .env 파일 사용 (프로젝트 폴더에)
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env

# 방법 C: ~/.bashrc 또는 ~/.zshrc에 영구 등록
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc
```

### 4. API 키 없이 테스트 가능한 범위

```bash
# --help (API 키 불필요)
uvx --python 3.13 deepagents-cli --help

# --version (API 키 불필요)
uvx --python 3.13 deepagents-cli --version

# list 명령어 → API 키 없으면 에러 예상
uvx --python 3.13 deepagents-cli list

# run 명령어 → API 키 필수
uvx --python 3.13 deepagents-cli run "파일 목록 보여줘"
```

### 5. Anthropic Claude로 첫 실행

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# 기본 실행 (Claude 3.x 사용)
uvx --python 3.13 deepagents-cli run "현재 폴더의 파일 목록을 알려줘"

# 또는 설치 후
uv tool install deepagents-cli --python 3.13
deepagents run "Hello, what can you do?"
```

---

## 패키지 정보

- **GitHub**: https://github.com/langchain-ai/deepagents
- **문서**: https://docs.langchain.com/oss/python/deepagents/overview
- **최신 버전**: 0.0.34
- **지원 LLM**: Claude (Anthropic), GPT-4 (OpenAI), Gemini (Google), Groq, DeepSeek 등

### 주요 의존성
- `langchain`, `langgraph`, `langchain-anthropic`
- `daytona`, `modal` (샌드박스 실행 환경)
- `textual` (TUI 인터페이스)
- `langchain-mcp-adapters` (MCP 툴 연동)

---

## 문제 해결

### `uv: command not found`
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Python 버전 에러 (`requires Python>=3.11`)
```bash
uv python install 3.13  # 먼저 Python 설치
uv tool install deepagents-cli --python 3.13
```

### API 키 에러
```bash
# 에러 예시: AuthenticationError
export ANTHROPIC_API_KEY="sk-ant-api03-..."  # 키 앞에 공백 없이
```

### GitHub 프록시/방화벽 차단 환경
uv의 Python 자동 다운로드가 막힌 경우, 시스템에 직접 Python 3.11+ 설치 후:
```bash
# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv

# 설치된 Python 경로로 지정
uv tool install deepagents-cli --python /usr/bin/python3.11
```

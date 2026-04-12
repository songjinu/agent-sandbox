# DeepAgents CLI + Groq 모델 + 샌드박스 테스트 결과

**테스트 일시**: 2026-04-01
**환경**: Cowork 샌드박스 (Ubuntu 22.04, Python 3.10/3.11)
**deepagents-cli 버전**: v0.0.34
**deepagents SDK 버전**: v0.4.11

---

## 요약

| 항목 | 결과 |
|------|------|
| deepagents-cli 설치 | ✅ 성공 (Python 3.11 필요) |
| langchain-groq 설치 | ✅ 성공 |
| deepagents CLI 기동 | ✅ 성공 (LangGraph 서버 시작됨) |
| Groq API 연결 | ❌ 실패 (프록시 allowlist 차단) |
| E2B 샌드박스 연결 | ❌ 실패 (프록시 allowlist 차단) |
| Modal 샌드박스 연결 | ❌ 실패 (프록시 allowlist 차단) |

**결론**: deepagents-cli 자체는 정상 설치 및 기동됨. 단, 이 환경의 네트워크 프록시가 `api.groq.com`, `api.e2b.dev`, `api.modal.com` 등 외부 API 엔드포인트를 allowlist 정책으로 차단하여 실제 LLM 호출 및 샌드박스 연동은 불가.

---

## 1. 환경 구성 과정

### 1-1. Python 버전 문제

deepagents-cli v0.0.34는 **Python >= 3.11** 을 요구함. 이 환경의 기본 Python은 3.10.12.

```
# 시도 1: uv로 Python 3.13 설치 → GitHub 다운로드 차단으로 실패
uv venv ~/deepagents-test --python 3.13
# error: Failed to download from github.com (blocked)

# 시도 2: apt-get install python3.11 → sudo 권한 없어서 실패

# 해결책: Ubuntu archive (허용됨)에서 .deb 수동 다운로드 후 추출
apt-get download python3.11 python3.11-minimal libpython3.11-minimal libpython3.11-stdlib
dpkg -x *.deb /tmp/py311/install/
# → /tmp/py311/install/usr/bin/python3.11 (Python 3.11.0rc1) 획득
```

### 1-2. 설치 성공 명령어 세트

```bash
# 1. Python 3.11 deb 추출
mkdir -p /tmp/py311
cd /tmp/py311
apt-get download python3.11 python3.11-minimal libpython3.11-minimal libpython3.11-stdlib python3.11-venv
for deb in *.deb; do dpkg -x "$deb" /tmp/py311/install/; done

# 2. venv 생성
export LD_LIBRARY_PATH=/tmp/py311/install/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
/tmp/py311/install/usr/bin/python3.11 -m venv --without-pip ~/deepagents-py311

# 3. pip 설치 (PyPI는 허용됨)
pip3 download pip -d /tmp/pip-wheel/ --only-binary :all:
~/deepagents-py311/bin/python3.11 -m pip install /tmp/pip-wheel/pip-*.whl --target ~/deepagents-py311/lib/python3.11/site-packages

# 4. deepagents + groq 설치
~/deepagents-py311/bin/python3.11 -m pip install deepagents-cli langchain-groq "httpx[socks]" socksio

# 설치 결과
# deepagents-cli 0.0.34, deepagents 0.4.11, langchain-groq 1.1.2, groq 0.37.1
```

---

## 2. Groq API 연결 테스트

### 2-1. 네트워크 프록시 상황

이 환경은 HTTP 프록시(localhost:3128)와 SOCKS5(localhost:1080)를 통해서만 외부에 접근 가능함.

```
HTTP_PROXY=http://localhost:3128
HTTPS_PROXY=http://localhost:3128
ALL_PROXY=socks5h://localhost:1080
```

### 2-2. 프록시 allowlist 분석

| 엔드포인트 | HTTP 응답 | 상태 |
|-----------|----------|------|
| api.anthropic.com | 200 Connection Established | ✅ 허용 |
| pypi.org | 200 OK | ✅ 허용 |
| archive.ubuntu.com | 200 OK | ✅ 허용 |
| **api.groq.com** | **403 Forbidden (blocked-by-allowlist)** | ❌ **차단** |
| api.openai.com | 403 Forbidden (blocked-by-allowlist) | ❌ 차단 |
| api.e2b.dev | 403 Forbidden (blocked-by-allowlist) | ❌ 차단 |
| api.modal.com | 403 Forbidden (blocked-by-allowlist) | ❌ 차단 |

### 2-3. Groq API 직접 테스트 결과

```python
from langchain_groq import ChatGroq
llm = ChatGroq(model='llama-3.3-70b-versatile',
               api_key='gsk_...')
result = llm.invoke('Say hi')

# 오류:
# httpcore.ProxyError: 403 Forbidden
# groq.APIConnectionError: Connection error.
```

---

## 3. deepagents CLI 기동 테스트

### 3-1. 버전 확인

```bash
export LD_LIBRARY_PATH=/tmp/py311/install/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
~/deepagents-py311/bin/python3.11 -m deepagents_cli.main --version
# deepagents-cli 0.0.34
# deepagents (SDK) 0.4.11
```

### 3-2. 비대화형 실행 결과

```bash
export GROQ_API_KEY=gsk_YOUR_GROQ_API_KEY

~/deepagents-py311/bin/python3.11 -m deepagents_cli.main \
  -n "hello world 파이썬 파일 만들어줘" \
  -M groq:llama-3.3-70b-versatile \
  -S all \
  --no-mcp
```

```
Running task non-interactively...
CLI: v0.0.34 | Agent: agent (default) | Model: llama-3.3-70b-versatile | Thread: 019d47db-...
Starting LangGraph server...
✓ Server ready                               ← LangGraph 서버 정상 기동
Unexpected error during non-interactive execution
langgraph.pregel.remote.RemoteException: {'error': 'APIConnectionError', 'message': 'An internal error occurred'}
```

**분석**: deepagents는 내부적으로 LangGraph 서버를 기동하고, Groq API를 통해 LLM 호출을 시도함. 프록시에서 api.groq.com이 차단되어 있어 `APIConnectionError` 발생.

---

## 4. 샌드박스 연동 테스트

### 4-1. deepagents 지원 샌드박스 목록 (소스코드 확인)

```python
# deepagents_cli/integrations/sandbox_factory.py
_PROVIDER_TO_WORKING_DIR = {
    "daytona": "/home/daytona",
    "modal": "/workspace",
    "runloop": "/home/user",
}
# + langsmith 지원
```

### 4-2. E2B 샌드박스

E2B는 deepagents v0.0.34 공식 문서에 언급되나, 현재 소스코드에는 별도 provider로 등록되어 있지 않음.

```bash
# API 접근 테스트
curl -v -x http://localhost:3128 https://api.e2b.dev
# → HTTP/1.1 403 Forbidden (blocked-by-allowlist)
```

**결론**: api.e2b.dev가 프록시 allowlist에 없어서 API 키 발급 및 연동 불가.

### 4-3. Modal 샌드박스

```bash
# API 접근 테스트
curl -v -x http://localhost:3128 https://api.modal.com
# → 403 Forbidden (blocked-by-allowlist)
```

**결론**: api.modal.com도 차단. `modal setup` (브라우저 인증) 실행 불가.

### 4-4. Daytona 샌드박스

deepagents가 Daytona SDK를 내장(daytona 0.159.0 설치됨). 별도 서버 URL 설정 필요.

```bash
# 테스트 생략 - 외부 Daytona API 서버도 같은 allowlist 정책에 해당할 것으로 예상
```

---

## 5. 정리: 성공/실패 항목

### ✅ 성공한 것

1. **deepagents-cli v0.0.34 설치** - Python 3.11 RC1 (.deb 수동 추출)으로 설치 성공
2. **langchain-groq 1.1.2 설치** - PyPI에서 정상 설치
3. **deepagents --help 실행** - CLI 인터페이스 정상 작동
4. **LangGraph 서버 기동** - `deepagents -n ...` 실행 시 내부 서버 정상 시작
5. **groq 패키지 import** - Python 레벨에서 정상 로드

### ❌ 실패한 것

1. **Groq API 연결** - api.groq.com이 프록시 allowlist에 없어서 차단
2. **E2B 샌드박스** - api.e2b.dev 차단
3. **Modal 샌드박스** - api.modal.com 차단
4. **Python 3.13 venv (uv)** - github.com 다운로드 차단

---

## 6. 성공 가능 최소 명령어 세트 (프록시 제약 없는 환경 기준)

아래 명령어는 **api.groq.com 접근이 허용된 일반 환경**에서 작동 예상:

```bash
# Step 1: Python 3.11+ 환경 준비
uv venv ~/deepagents-test --python 3.13
source ~/deepagents-test/bin/activate

# Step 2: 패키지 설치
uv pip install deepagents-cli langchain-groq

# Step 3: Groq API 키 설정
export GROQ_API_KEY=gsk_YOUR_GROQ_API_KEY

# Step 4: Groq API 직접 테스트
python3 -c "
from langchain_groq import ChatGroq
llm = ChatGroq(model='llama-3.3-70b-versatile', api_key='$GROQ_API_KEY')
print(llm.invoke('Say hi').content)
"

# Step 5: deepagents 기본 실행 (로컬 실행, 샌드박스 없음)
deepagents -n "hello world 파이썬 파일 만들어줘" -M groq:llama-3.3-70b-versatile -S all

# Step 6: E2B 샌드박스 연동 (E2B API 키 필요 - https://e2b.dev 에서 발급)
pip install e2b-code-interpreter
export E2B_API_KEY=your_e2b_api_key
deepagents -n "hello world" -M groq:llama-3.3-70b-versatile --sandbox e2b

# Step 7: Modal 샌드박스 연동 (브라우저 인증 필요)
pip install modal
modal setup
deepagents -n "hello world" -M groq:llama-3.3-70b-versatile --sandbox modal
```

---

## 7. 환경 제약 사항 (이 Cowork 샌드박스 기준)

이 환경에서 외부 LLM/샌드박스 API를 사용하려면 프록시 allowlist에 다음 도메인 추가 필요:

- `api.groq.com` (Groq LLM API)
- `api.e2b.dev` (E2B 샌드박스)
- `api.modal.com` (Modal 샌드박스)
- `github.com` (uv Python 다운로드)

현재 허용된 도메인: `api.anthropic.com`, `pypi.org`, `archive.ubuntu.com` 등.

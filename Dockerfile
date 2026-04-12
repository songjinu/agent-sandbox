FROM python:3.13-slim

WORKDIR /app

# 시스템 패키지
RUN apt-get update -qq && apt-get install -y -qq curl && rm -rf /var/lib/apt/lists/*

# pip 업그레이드 및 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY agent/ .

# sandbox 작업 디렉토리
RUN mkdir -p /tmp/sandbox_workspace

# LLM 설정 기본값 (docker run -e 로 오버라이드)
# vllm (Gemini)
# ENV LLM_PROVIDER=vllm
# ENV LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# ENV LLM_MODEL=gemini-2.0-flash
# ENV LLM_API_KEY=dummy

# ollama (로컬 테스트)
ENV LLM_PROVIDER=ollama
ENV LLM_BASE_URL=http://172.19.16.1:11434
ENV LLM_MODEL=glm-5:cloud
ENV LLM_API_KEY=dummy

EXPOSE 7860
EXPOSE 8000

# UI: python ui.py
# API: python api.py
CMD ["python", "api.py"]

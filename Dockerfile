FROM python:3.13-slim

WORKDIR /app

# 시스템 패키지 — bubblewrap 추가 (sandbox 격리용)
RUN apt-get update -qq && apt-get install -y -qq curl tini bubblewrap && rm -rf /var/lib/apt/lists/*

# pip 패키지
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스
COPY agent/ ./agent/
ENV PYTHONPATH=/app/agent

# sandbox 작업 디렉토리
RUN mkdir -p /tmp/sandbox_workspace

# 디버그 편의 — docker exec -it agent-sandbox bash 시 사용
RUN { \
      echo "alias ll='ls -lah --color=auto'"; \
      echo "alias la='ls -A --color=auto'"; \
      echo "alias l='ls -CF --color=auto'"; \
      echo "alias ..='cd ..'"; \
      echo "alias sb='cd /tmp/sandbox_workspace'"; \
      echo "alias logs='docker logs -f agent-sandbox'"; \
      echo "PS1='\\[\\033[1;32m\\][container]\\[\\033[0m\\] \\w \\$ '"; \
    } >> /root/.bashrc

# LLM 설정 기본값 (run.sh / docker run -e 로 오버라이드 가능)
ENV LLM_BASE_URL=http://172.19.16.1:11434/v1 \
    LLM_MODEL=minimax-m2.5:cloud \
    LLM_API_KEY=ollama \
    LLM_CONFIG_FILE=/app/llm_config.json \
    SESSION_TIMEOUT=120 \
    CLEANUP_INTERVAL=10 \
    MAX_SESSIONS=10 \
    USE_BUBBLEWRAP=1

# 단일 프로세스: FastAPI + 그 안에 Chainlit mount → SessionManager 싱글톤 공유
EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "agent/api.py"]

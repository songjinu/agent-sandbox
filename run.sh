#!/bin/bash
# Agent Sandbox 컨테이너 실행
# 단일 프로세스: FastAPI :8000 (안에 Chainlit이 /chat 경로로 mount됨)
#   - http://localhost:8000/        → API (chat, sessions, health)
#   - http://localhost:8000/monitor → 실시간 모니터링
#   - http://localhost:8000/chat    → Chainlit 채팅 UI

set -e

CONTAINER_NAME=agent-sandbox
IMAGE_NAME=agent-sandbox
PORT=${PORT:-8000}

# Docker 자원 한도 — 한 세션이 폭주해도 컨테이너 전체가 죽지 않게 cap
MEMORY=${MEMORY:-3g}
CPUS=${CPUS:-2}

LLM_BASE_URL=${LLM_BASE_URL:-http://172.19.16.1:11434/v1}
LLM_MODEL=${LLM_MODEL:-minimax-m2.5:cloud}
LLM_API_KEY=${LLM_API_KEY:-ollama}

MOUNT_ARGS=""
if [ -n "$CONFIG" ]; then
  if [ ! -f "$CONFIG" ]; then
    echo "CONFIG not found: $CONFIG" >&2
    exit 1
  fi
  MOUNT_ARGS="-v $(realpath "$CONFIG"):/app/llm_config.json:ro"
fi

docker rm -f $CONTAINER_NAME 2>/dev/null || true

docker run -d \
  --name $CONTAINER_NAME \
  --cap-add SYS_ADMIN \
  --security-opt seccomp=unconfined \
  --memory="$MEMORY" \
  --memory-swap="$MEMORY" \
  --cpus="$CPUS" \
  -p $PORT:8000 \
  -e LLM_BASE_URL="$LLM_BASE_URL" \
  -e LLM_MODEL="$LLM_MODEL" \
  -e LLM_API_KEY="$LLM_API_KEY" \
  $MOUNT_ARGS \
  $IMAGE_NAME

echo "Started:"
echo "  채팅:    http://localhost:$PORT/chat"
echo "  모니터:  http://localhost:$PORT/monitor"
echo "  API:     http://localhost:$PORT (/health, /sessions, /chat[POST], ...)"
echo
echo "자원: --memory=$MEMORY --cpus=$CPUS  (변경: MEMORY=4g CPUS=4 ./run.sh)"
echo
echo "Logs:    docker logs -f $CONTAINER_NAME"
echo "Stop:    docker rm -f $CONTAINER_NAME"

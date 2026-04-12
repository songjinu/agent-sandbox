#!/bin/bash
# Agent Sandbox 컨테이너 실행
#
# [Ollama 로컬 테스트]
# ./run.sh
#
# [vLLM 테스트 서버]
# LLM_PROVIDER=vllm \
# LLM_BASE_URL=http://vllm-server:8000/v1 \
# LLM_MODEL=your-model-name \
# LLM_API_KEY=your-api-key \
# ./run.sh
#
# [Gemini API]
# LLM_PROVIDER=vllm \
# LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/ \
# LLM_MODEL=gemini-2.0-flash \
# LLM_API_KEY=your-gemini-key \
# ./run.sh

set -e

CONTAINER_NAME=agent-sandbox
IMAGE_NAME=agent-sandbox
HOST_PORT=${HOST_PORT:-7861}

# 기존 컨테이너 정리
docker rm -f $CONTAINER_NAME 2>/dev/null || true

docker run -d \
  --name $CONTAINER_NAME \
  -p $HOST_PORT:7860 \
  -e LLM_PROVIDER=${LLM_PROVIDER:-ollama} \
  -e LLM_BASE_URL=${LLM_BASE_URL:-http://172.19.16.1:11434} \
  -e LLM_MODEL=${LLM_MODEL:-glm-5:cloud} \
  -e LLM_API_KEY=${LLM_API_KEY:-dummy} \
  $IMAGE_NAME

echo "Started: http://localhost:$HOST_PORT"
echo ""
echo "Logs: docker logs -f $CONTAINER_NAME"

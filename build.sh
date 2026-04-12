#!/bin/bash
# Agent Sandbox 이미지 빌드
set -e

IMAGE_NAME=agent-sandbox
IMAGE_TAG=${1:-latest}

echo "Building $IMAGE_NAME:$IMAGE_TAG ..."
docker build -t $IMAGE_NAME:$IMAGE_TAG .
echo "Done: $IMAGE_NAME:$IMAGE_TAG"

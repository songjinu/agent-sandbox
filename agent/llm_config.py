"""
LLM 설정 파일 관리
- llm_config.json 파일로 다중 LLM 설정 저장/로드
- base_url / model / api_key 만으로 OpenAI 호환 API 전부 커버
  예) Ollama, vLLM, OpenRouter, Claude(via OpenRouter), Gemini 등
"""

import os
import json
from langchain_openai import ChatOpenAI

CONFIG_FILE = os.environ.get("LLM_CONFIG_FILE", "/app/llm_config.json")

_DEFAULT_CONFIG = {
    "default": "default",
    "llms": {
        "default": {
            "base_url": os.environ.get("LLM_BASE_URL", "http://172.19.16.1:11434/v1"),
            "model":    os.environ.get("LLM_MODEL",    "glm-5:cloud"),
            "api_key":  os.environ.get("LLM_API_KEY",  "ollama"),
        },
    },
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        config.setdefault("default", "default")
        config.setdefault("llms", {})
        return config
    return {
        "default": _DEFAULT_CONFIG["default"],
        "llms": {k: v.copy() for k, v in _DEFAULT_CONFIG["llms"].items()},
    }


def save_config(config: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_llm_entry(llm_id: str | None = None) -> dict:
    config = load_config()
    key = llm_id or config["default"]
    entry = config["llms"].get(key)
    if entry is None:
        raise KeyError(f"LLM ID '{key}' 가 설정에 없습니다.")
    return entry


def build_llm(llm_id: str | None = None) -> ChatOpenAI:
    entry = get_llm_entry(llm_id)
    return ChatOpenAI(
        model=entry["model"],
        base_url=entry["base_url"],
        api_key=entry["api_key"],
    )


def list_llm_ids() -> list[str]:
    return list(load_config()["llms"].keys())

"""
Chainlit 채팅 UI - Agent Sandbox 테스트/시연용
- chat profile로 LLM 선택
- 도구 호출 단계를 cl.Step 으로 자동 표시
- 모니터링은 별도 페이지 (FastAPI :8000/monitor)
"""

import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chainlit as cl
from llm_config import list_llm_ids, load_config
from runtime import manager, next_color_id


def _resolve_sid() -> str:
    """Chainlit 세션마다 색 이름을 session_id로 부여 (red, blue, yellow, ...)."""
    sid = cl.user_session.get("sandbox_session_id")
    if sid:
        return sid
    sid = next_color_id()
    cl.user_session.set("sandbox_session_id", sid)
    return sid


def _content_str(msg) -> str:
    c = getattr(msg, "content", "")
    if isinstance(c, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return str(c)


@cl.set_chat_profiles
async def chat_profiles(_user=None):
    cfg = load_config()
    default_id = cfg.get("default", "")
    profiles = []
    for llm_id, entry in cfg["llms"].items():
        profiles.append(
            cl.ChatProfile(
                name=llm_id,
                markdown_description=f"`{entry.get('model', '')}` @ `{entry.get('base_url', '')}`",
                default=(llm_id == default_id),
            )
        )
    return profiles


@cl.on_chat_start
async def on_start():
    sid = _resolve_sid()

    profile = cl.user_session.get("chat_profile") or load_config().get("default")
    cl.user_session.set("llm_id", profile)

    print(f"[chat.py:on_chat_start] sid={sid} llm={profile}", flush=True)

    await cl.Message(
        content=(
            f"🟢 **세션 시작**\n"
            f"- session_id: `{sid}`\n"
            f"- LLM: `{profile}`\n"
            f"- 모니터링: http://localhost:8000/monitor (별도 창)\n\n"
            "샘플 명령:\n"
            "1. `hello.txt 파일에 'hi' 라고 써줘`\n"
            "2. `fib.py에 피보나치 10개 출력 코드 만들고 실행해줘`\n"
            "3. `/etc/secret.txt에 'leak' 이라고 써줘` _(격리 검증)_\n"
            "4. `count.txt 파일을 만들어서 1초마다 1부터 100까지 한 줄씩 써줘` _(자원 한도 검증 — 30초 타임아웃)_\n"
        )
    ).send()


@cl.on_chat_end
async def on_end():
    """브라우저 닫힘/페이지 이탈 시 호출. 즉시 close하면 모니터에서 곧바로 사라져
    시연 가시성이 떨어지므로, SESSION_TIMEOUT 자동 cleanup에 맡김."""
    sid = cl.user_session.get("sandbox_session_id")
    print(f"[chat.py:on_chat_end] sid={sid} (SESSION_TIMEOUT 자동 정리 대기)", flush=True)


@cl.on_message
async def on_message(msg: cl.Message):
    sid = _resolve_sid()
    llm_id = cl.user_session.get("llm_id") or load_config().get("default")
    print(f"[chat.py:on_message] sid={sid} msg={msg.content[:60]!r}", flush=True)

    try:
        session = manager.get_or_create(sid, llm_id)
    except RuntimeError as e:
        await cl.Message(content=f"❌ {e}").send()
        return

    seen: set = set()
    pending_tool_steps: dict = {}  # tool_call_id → cl.Step
    final_text = ""

    session.begin_request(msg.content)
    try:
        async for state in session.graph.astream(
            {"messages": [{"role": "user", "content": msg.content}]},
            config={"configurable": {"thread_id": sid}},
            stream_mode="values",
        ):
            msgs = state.get("messages", []) if isinstance(state, dict) else []
            for m in msgs:
                mid = getattr(m, "id", None) or id(m)
                if mid in seen:
                    continue
                seen.add(mid)

                mtype = (getattr(m, "type", "") or type(m).__name__).lower()

                if "human" in mtype:
                    continue

                if "ai" in mtype:
                    tcs = getattr(m, "tool_calls", []) or []
                    for tc in tcs:
                        name = tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                        tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                        step = cl.Step(name=name, type="tool")
                        await step.__aenter__()
                        step.input = args
                        pending_tool_steps[tc_id] = step
                    text = _content_str(m)
                    if text and not tcs:
                        final_text = text

                elif "tool" in mtype:
                    tc_id = getattr(m, "tool_call_id", "")
                    out = _content_str(m)
                    step = pending_tool_steps.pop(tc_id, None)
                    if step is None:
                        step = cl.Step(name="결과", type="tool")
                        await step.__aenter__()
                    step.output = out[:2000]
                    await step.__aexit__(None, None, None)

        # 혹시 매칭 안 된 step 정리
        for step in pending_tool_steps.values():
            await step.__aexit__(None, None, None)

        session.end_request()

        if final_text:
            await cl.Message(content=final_text).send()
        else:
            await cl.Message(content="_(빈 응답)_").send()

    except Exception as e:
        # 매달린 step 정리
        for step in pending_tool_steps.values():
            try:
                await step.__aexit__(None, None, None)
            except Exception:
                pass
        try:
            session.end_request()
        except Exception:
            pass
        await cl.Message(content=f"❌ 오류: {str(e)[:300]}").send()

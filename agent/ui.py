"""
Gradio UI - Agent 테스트 및 세션 관리
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
from session_manager import SessionManager, SESSION_TIMEOUT, MAX_SESSIONS
from llm_config import list_llm_ids, load_config, save_config

manager = SessionManager()


def _msg_content_str(msg) -> str:
    c = getattr(msg, "content", "")
    if isinstance(c, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return str(c)


def chat(session_id: str, llm_id: str, message: str, history: list):
    if not session_id.strip():
        yield history + [{"role": "assistant", "content": "세션 ID를 입력하세요."}], ""
        return
    if not message.strip():
        yield history, ""
        return

    try:
        session = manager.get_or_create(session_id.strip(), llm_id or None)
    except Exception as e:
        yield history + [{"role": "assistant", "content": f"오류: {str(e)[:200]}"}], ""
        return

    history = history + [{"role": "user", "content": message}]
    yield history, ""

    seen: set = set()
    progress: list[str] = []

    def render():
        return history + [{"role": "assistant", "content": "\n\n".join(progress) or "..."}]

    try:
        for state in session.graph.stream(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": session_id.strip()}},
            stream_mode="values",
        ):
            msgs = state.get("messages", []) if isinstance(state, dict) else []
            for msg in msgs:
                mid = getattr(msg, "id", None) or id(msg)
                if mid in seen:
                    continue
                seen.add(mid)

                mtype = (getattr(msg, "type", None) or type(msg).__name__).lower()
                if "human" in mtype:
                    continue
                if "ai" in mtype:
                    tool_calls = getattr(msg, "tool_calls", []) or []
                    for tc in tool_calls:
                        name = tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                        args_str = str(args)
                        if len(args_str) > 200:
                            args_str = args_str[:200] + "…"
                        progress.append(f"🔧 **{name}**\n```\n{args_str}\n```")
                    text = _msg_content_str(msg)
                    if text:
                        progress.append(f"💬 {text}")
                elif "tool" in mtype:
                    out = _msg_content_str(msg)
                    if len(out) > 400:
                        out = out[:400] + "…"
                    progress.append(f"📤 결과:\n```\n{out}\n```")

            yield render(), ""

        session.touch()
    except RuntimeError as e:
        progress.append(f"❌ 오류: {e}")
        yield render(), ""
    except Exception as e:
        progress.append(f"❌ 오류: {str(e)[:300]}")
        yield render(), ""


def close_session(session_id: str) -> str:
    if not session_id.strip():
        return "세션 ID를 입력하세요."
    manager.close(session_id.strip())
    return f"세션 '{session_id}' 종료됨"


def _list_workdir_tree(workdir: str, max_files: int = 30) -> list[str]:
    """workdir 안 파일 목록을 indent된 문자열 리스트로 반환."""
    lines: list[str] = []
    count = 0
    for root, _dirs, files in sorted(os.walk(workdir)):
        rel = os.path.relpath(root, workdir)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if rel != ".":
            lines.append("    " + "  " * (depth - 1) + os.path.basename(root) + "/")
        for f in sorted(files):
            if count >= max_files:
                lines.append("    " + "  " * depth + f"… (+{count}개 이상 생략)")
                return lines
            try:
                size = os.path.getsize(os.path.join(root, f))
            except OSError:
                size = 0
            lines.append("    " + "  " * depth + f"{f}  ({size}B)")
            count += 1
    if not lines:
        lines.append("    (빈 디렉토리)")
    return lines


def get_status() -> str:
    stats = manager.stats()
    lines = [
        f"활성 세션: {stats['active_sessions']} / {stats['max_sessions']}",
        f"총 요청수: {stats['total_requests']}",
        f"디스크 사용: {stats['total_workdir_kb']} KB",
        "",
    ]
    sessions = manager.list_sessions()
    if not sessions:
        lines.append("(세션 없음)")
        return "\n".join(lines)

    for info in sessions:
        lines.append(
            f"[{info.session_id}]  요청:{info.request_count}  유휴:{info.idle_seconds:.0f}초  디스크:{info.workdir_size_kb}KB"
        )
        lines.append(f"  workdir: {info.workdir}")
        lines.extend(_list_workdir_tree(info.workdir))
        lines.append("")
    return "\n".join(lines)


def get_settings() -> tuple:
    return manager.max_sessions, manager.session_timeout


def apply_settings(max_sessions: int, timeout: int) -> str:
    manager.max_sessions = int(max_sessions)
    manager.session_timeout = int(timeout)
    return f"설정 적용됨: 최대 세션={max_sessions}, 타임아웃={timeout}초"


def get_llm_list() -> str:
    cfg = load_config()
    default_id = cfg.get("default", "")
    lines = [f"**현재 등록된 LLM** (기본값: `{default_id}`)", ""]
    for llm_id, entry in cfg["llms"].items():
        marker = " ⭐" if llm_id == default_id else ""
        lines.append(f"- **`{llm_id}`**{marker} — `{entry.get('model','')}` @ `{entry.get('base_url','')}`")
    if not cfg["llms"]:
        lines.append("_(등록된 LLM 없음)_")
    return "\n".join(lines)


def save_llm_entry(llm_id: str, base_url: str, model: str, api_key: str, set_default: bool) -> str:
    if not llm_id.strip():
        return "LLM ID를 입력하세요."
    cfg = load_config()
    cfg["llms"][llm_id.strip()] = {
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }
    if set_default:
        cfg["default"] = llm_id.strip()
    save_config(cfg)
    return f"저장됨: [{llm_id}] {model} @ {base_url}"


def delete_llm_entry(llm_id: str) -> str:
    if not llm_id.strip():
        return "LLM ID를 입력하세요."
    cfg = load_config()
    if llm_id.strip() not in cfg["llms"]:
        return f"'{llm_id}' 없음"
    del cfg["llms"][llm_id.strip()]
    save_config(cfg)
    return f"삭제됨: {llm_id}"


with gr.Blocks(title="Agent Sandbox UI") as app:
    gr.Markdown("# Agent Sandbox 테스트")
    gr.Markdown("💡 실시간 세션 모니터링: [http://localhost:8000/monitor](http://localhost:8000/monitor) (별도 창)")

    with gr.Tabs():
        # 채팅 탭
        with gr.Tab("채팅"):
            with gr.Row():
                session_input = gr.Textbox(label="세션 ID", placeholder="예: user-001", scale=2)
                llm_id_input = gr.Dropdown(
                    choices=list_llm_ids(), label="LLM", scale=1,
                    value=load_config().get("default"),
                )
            chatbot = gr.Chatbot(height=400)
            with gr.Row():
                msg_input = gr.Textbox(label="메시지", placeholder="Agent에게 요청하세요", scale=4)
                send_btn = gr.Button("전송", scale=1)
            close_btn = gr.Button("세션 종료", variant="stop")
            close_output = gr.Textbox(label="", interactive=False)

            send_btn.click(chat, [session_input, llm_id_input, msg_input, chatbot], [chatbot, msg_input])
            msg_input.submit(chat, [session_input, llm_id_input, msg_input, chatbot], [chatbot, msg_input])
            close_btn.click(close_session, session_input, close_output)

        # 설정 탭
        with gr.Tab("설정"):
            gr.Markdown("### 세션 설정")
            max_sessions_slider = gr.Slider(1, 100, value=MAX_SESSIONS, step=1, label="최대 세션 수")
            timeout_slider = gr.Slider(60, 3600, value=SESSION_TIMEOUT, step=60, label="세션 타임아웃 (초)")
            apply_btn = gr.Button("적용", variant="primary")
            settings_output = gr.Textbox(label="", interactive=False)
            apply_btn.click(apply_settings, [max_sessions_slider, timeout_slider], settings_output)
            app.load(lambda: get_settings(), outputs=[max_sessions_slider, timeout_slider])

            gr.Markdown("### LLM 설정")
            llm_summary = gr.Markdown(value=get_llm_list)
            llm_select = gr.Dropdown(choices=list_llm_ids(), label="등록된 LLM (선택하면 폼 자동 입력)", interactive=True)
            llm_id_field = gr.Textbox(label="LLM ID", placeholder="예: ollama-local")
            llm_base_url_field = gr.Textbox(label="Base URL", placeholder="http://172.19.16.1:11434/v1")
            llm_model_field = gr.Textbox(label="Model", placeholder="glm-5:cloud")
            llm_api_key_field = gr.Textbox(label="API Key", placeholder="dummy", type="password")
            llm_default_check = gr.Checkbox(label="기본값으로 설정")
            with gr.Row():
                llm_save_btn = gr.Button("저장", variant="primary")
                llm_delete_btn = gr.Button("삭제", variant="stop")
            llm_output = gr.Textbox(label="", interactive=False)

            def load_llm_entry(llm_id):
                if not llm_id:
                    return "", "", "", "", False
                cfg = load_config()
                entry = cfg["llms"].get(llm_id, {})
                is_default = cfg["default"] == llm_id
                return (
                    llm_id,
                    entry.get("base_url", ""),
                    entry.get("model", ""),
                    entry.get("api_key", ""),
                    is_default,
                )

            def refresh_llm_select():
                cfg = load_config()
                ids = list(cfg["llms"].keys())
                default_id = cfg.get("default") if cfg.get("default") in ids else (ids[0] if ids else None)
                return gr.Dropdown(choices=ids, value=default_id)

            llm_select.change(
                load_llm_entry, llm_select,
                [llm_id_field, llm_base_url_field, llm_model_field, llm_api_key_field, llm_default_check],
            )
            llm_save_btn.click(
                save_llm_entry,
                [llm_id_field, llm_base_url_field, llm_model_field, llm_api_key_field, llm_default_check],
                llm_output,
            ).then(refresh_llm_select, outputs=llm_select).then(get_llm_list, outputs=llm_summary)
            llm_delete_btn.click(
                delete_llm_entry, llm_id_field, llm_output,
            ).then(refresh_llm_select, outputs=llm_select).then(get_llm_list, outputs=llm_summary)
            app.load(refresh_llm_select, outputs=llm_select)
            app.load(get_llm_list, outputs=llm_summary)


if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)

"""
Gradio UI - Agent 테스트 및 세션 관리
"""

import sys
sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork")

import gradio as gr
from session_manager import SessionManager, SESSION_TIMEOUT, MAX_SESSIONS
from llm_config import list_llm_ids, load_config, save_config

manager = SessionManager()


def chat(session_id: str, llm_id: str, message: str, history: list) -> tuple:
    if not session_id.strip():
        history = history + [("", "세션 ID를 입력하세요.")]
        return history, ""
    if not message.strip():
        return history, ""

    try:
        session = manager.get_or_create(session_id.strip(), llm_id or None)
        result = session.graph.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": session_id}},
        )
        session.touch()
        response = result["messages"][-1].content
    except RuntimeError as e:
        response = f"오류: {e}"
    except Exception as e:
        response = f"오류: {str(e)[:200]}"

    history = history + [(message, response)]
    return history, ""


def close_session(session_id: str) -> str:
    if not session_id.strip():
        return "세션 ID를 입력하세요."
    manager.close(session_id.strip())
    return f"세션 '{session_id}' 종료됨"


def get_status() -> str:
    stats = manager.stats()
    lines = [
        f"활성 세션: {stats['active_sessions']} / {stats['max_sessions']}",
        f"총 요청수: {stats['total_requests']}",
        f"디스크 사용: {stats['total_workdir_kb']} KB",
        "",
        "세션 목록:",
    ]
    for info in manager.list_sessions():
        lines.append(
            f"  [{info.session_id}] 요청:{info.request_count} 유휴:{info.idle_seconds:.0f}초 디스크:{info.workdir_size_kb}KB"
        )
    return "\n".join(lines) if manager.list_sessions() else "\n".join(lines) + "\n  (없음)"


def get_settings() -> tuple:
    return manager.max_sessions, manager.session_timeout


def apply_settings(max_sessions: int, timeout: int) -> str:
    manager.max_sessions = int(max_sessions)
    manager.session_timeout = int(timeout)
    return f"설정 적용됨: 최대 세션={max_sessions}, 타임아웃={timeout}초"


def get_llm_list() -> str:
    cfg = load_config()
    lines = [f"default: {cfg['default']}", ""]
    for llm_id, entry in cfg["llms"].items():
        lines.append(f"[{llm_id}] {entry['model']} @ {entry['base_url']}")
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
    return f"저장됨: [{llm_id}] {provider} / {model}"


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

        # 모니터링 탭
        with gr.Tab("모니터링"):
            status_output = gr.Textbox(label="세션 현황", lines=15, interactive=False)
            refresh_btn = gr.Button("새로고침")
            refresh_btn.click(get_status, outputs=status_output)
            app.load(get_status, outputs=status_output)

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
            llm_list_output = gr.Textbox(label="등록된 LLM 목록", lines=6, interactive=False)
            llm_id_field = gr.Textbox(label="LLM ID", placeholder="예: ollama-local")
            llm_base_url_field = gr.Textbox(label="Base URL", placeholder="http://172.19.16.1:11434/v1")
            llm_model_field = gr.Textbox(label="Model", placeholder="glm-5:cloud")
            llm_api_key_field = gr.Textbox(label="API Key", placeholder="dummy", type="password")
            llm_default_check = gr.Checkbox(label="기본값으로 설정")
            with gr.Row():
                llm_save_btn = gr.Button("저장", variant="primary")
                llm_delete_btn = gr.Button("삭제", variant="stop")
            llm_output = gr.Textbox(label="", interactive=False)
            llm_save_btn.click(
                save_llm_entry,
                [llm_id_field, llm_base_url_field, llm_model_field, llm_api_key_field, llm_default_check],
                llm_output,
            ).then(get_llm_list, outputs=llm_list_output)
            llm_delete_btn.click(delete_llm_entry, llm_id_field, llm_output).then(get_llm_list, outputs=llm_list_output)
            app.load(get_llm_list, outputs=llm_list_output)


if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)

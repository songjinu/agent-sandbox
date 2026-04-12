"""
Gradio UI - Agent 테스트 및 세션 관리
"""

import sys
sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork")

import gradio as gr
from session_manager import SessionManager, SESSION_TIMEOUT, MAX_SESSIONS

manager = SessionManager()


def chat(session_id: str, message: str, history: list) -> tuple:
    if not session_id.strip():
        history = history + [("", "세션 ID를 입력하세요.")]
        return history, ""
    if not message.strip():
        return history, ""

    try:
        session = manager.get_or_create(session_id.strip())
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


with gr.Blocks(title="Agent Sandbox UI") as app:
    gr.Markdown("# Agent Sandbox 테스트")

    with gr.Tabs():
        # 채팅 탭
        with gr.Tab("채팅"):
            session_input = gr.Textbox(label="세션 ID", placeholder="예: user-001", scale=1)
            chatbot = gr.Chatbot(height=400)
            with gr.Row():
                msg_input = gr.Textbox(label="메시지", placeholder="Agent에게 요청하세요", scale=4)
                send_btn = gr.Button("전송", scale=1)
            close_btn = gr.Button("세션 종료", variant="stop")
            close_output = gr.Textbox(label="", interactive=False)

            send_btn.click(chat, [session_input, msg_input, chatbot], [chatbot, msg_input])
            msg_input.submit(chat, [session_input, msg_input, chatbot], [chatbot, msg_input])
            close_btn.click(close_session, session_input, close_output)

        # 모니터링 탭
        with gr.Tab("모니터링"):
            status_output = gr.Textbox(label="세션 현황", lines=15, interactive=False)
            refresh_btn = gr.Button("새로고침")
            refresh_btn.click(get_status, outputs=status_output)
            app.load(get_status, outputs=status_output)

        # 설정 탭
        with gr.Tab("설정"):
            max_sessions_slider = gr.Slider(1, 100, value=MAX_SESSIONS, step=1, label="최대 세션 수")
            timeout_slider = gr.Slider(60, 3600, value=SESSION_TIMEOUT, step=60, label="세션 타임아웃 (초)")
            apply_btn = gr.Button("적용", variant="primary")
            settings_output = gr.Textbox(label="", interactive=False)
            apply_btn.click(apply_settings, [max_sessions_slider, timeout_slider], settings_output)
            app.load(lambda: get_settings(), outputs=[max_sessions_slider, timeout_slider])


if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)

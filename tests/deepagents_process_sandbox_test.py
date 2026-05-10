"""
deepagents SDK + ProcessSandboxBackend + Ollama 연동 테스트
- 동시 3개 요청 제한
- 요청별 디렉토리 격리
"""

import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent"))

OLLAMA_HOST = "http://172.19.16.1:11434"
MODEL = "ollama:llama3.2:1b"
MAX_CONCURRENT = 3
TASK_TIMEOUT = 60  # 요청당 최대 60초


def run_agent_task(task: str) -> dict:
    """단일 요청을 격리된 sandbox에서 실행"""
    import os
    os.environ["OLLAMA_HOST"] = OLLAMA_HOST

    from deepagents.graph import create_deep_agent
    from langchain_ollama import ChatOllama
    from process_sandbox import ProcessSandboxBackend

    request_id = str(uuid.uuid4())[:8]
    sandbox = ProcessSandboxBackend(request_id)

    try:
        llm = ChatOllama(model="glm-5:cloud", base_url=OLLAMA_HOST)
        graph = create_deep_agent(model=llm, backend=sandbox)

        result = graph.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"thread_id": request_id}},
        )
        last_msg = result["messages"][-1].content
        return {"request_id": request_id, "task": task, "status": "ok", "result": last_msg[:200]}
    except Exception as e:
        return {"request_id": request_id, "task": task, "status": "error", "error": str(e)[:200]}
    finally:
        sandbox.cleanup()


def main():
    tasks = [
        "hello.txt 파일을 만들고 'Hello World!'를 써줘",
        "1부터 10까지 합계를 계산하는 파이썬 코드를 실행해줘",
        "현재 디렉토리의 파일 목록을 보여줘",
        "fibonacci.py 파일을 만들어줘. 피보나치 수열 10개를 출력하는 코드로.",
        "현재 날짜와 시간을 출력하는 파이썬 코드를 실행해줘",
    ]

    print(f"총 {len(tasks)}개 요청 / 동시 {MAX_CONCURRENT}개 제한\n")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(run_agent_task, task): task for task in tasks}
        for future in as_completed(futures, timeout=TASK_TIMEOUT * 2):
            try:
                result = future.result(timeout=TASK_TIMEOUT)
            except TimeoutError:
                task = futures[future]
                print(f"✗ [timeout] {task[:30]}... — {TASK_TIMEOUT}초 초과\n")
                continue
            rid = result["request_id"]
            task = result["task"]
            if result["status"] == "ok":
                print(f"✓ [{rid}] {task[:30]}...")
                print(f"  → {result['result']}\n")
            else:
                print(f"✗ [{rid}] {task[:30]}...")
                print(f"  오류: {result['error']}\n")


if __name__ == "__main__":
    main()

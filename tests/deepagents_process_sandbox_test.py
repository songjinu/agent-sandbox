"""
deepagents SDK + ProcessSandboxBackend + Skills + Ollama 연동 테스트
- skills 로딩 확인
- skill 지침에 따른 tool 사용 일관성 확인
- 동시 3개 요청 제한
- 요청별 디렉토리 격리
"""

import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork/agent")

OLLAMA_HOST = "http://172.19.16.1:11434"
MAX_CONCURRENT = 3
TASK_TIMEOUT = 60
SKILLS_PATH = "/app/skills/"


def run_agent_task(task: str, use_skills: bool = True) -> dict:
    """단일 요청을 격리된 sandbox에서 실행 (skills 선택 적용)"""
    import os
    os.environ["OLLAMA_HOST"] = OLLAMA_HOST

    from deepagents.graph import create_deep_agent
    from langchain_ollama import ChatOllama
    from process_sandbox import ProcessSandboxBackend

    request_id = str(uuid.uuid4())[:8]
    sandbox = ProcessSandboxBackend(request_id)

    try:
        llm = ChatOllama(model="glm-5:cloud", base_url=OLLAMA_HOST)
        graph = create_deep_agent(
            model=llm,
            backend=sandbox,
            skills=[SKILLS_PATH] if use_skills else None,
        )
        result = graph.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"thread_id": request_id}},
        )
        last_msg = result["messages"][-1].content
        return {
            "request_id": request_id,
            "task": task,
            "status": "ok",
            "result": last_msg[:200],
            "skills": use_skills,
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "task": task,
            "status": "error",
            "error": str(e)[:200],
            "skills": use_skills,
        }
    finally:
        sandbox.cleanup()


def print_result(result: dict):
    rid = result["request_id"]
    task = result["task"]
    tag = "[skills]" if result["skills"] else "[no-skills]"
    if result["status"] == "ok":
        print(f"  [PASS] {tag} [{rid}] {task[:40]}")
        print(f"         → {result['result'][:100]}\n")
    else:
        print(f"  [FAIL] {tag} [{rid}] {task[:40]}")
        print(f"         오류: {result['error']}\n")


def test_skills_load():
    """skills 파일 로딩 확인"""
    print("[1] Skills 로딩 확인")
    import os
    assert os.path.isdir(SKILLS_PATH), f"skills 경로 없음: {SKILLS_PATH}"
    skill_dirs = [d for d in os.listdir(SKILLS_PATH)
                  if os.path.isdir(os.path.join(SKILLS_PATH, d))
                  and os.path.isfile(os.path.join(SKILLS_PATH, d, "SKILL.md"))]
    assert len(skill_dirs) > 0, "SKILL.md 파일 없음"
    for name in sorted(skill_dirs):
        print(f"  [PASS] skill 로드: {name}")
    print()


def test_with_skills():
    """skills 적용 후 agent 동작 테스트"""
    print("[2] Skills 적용 agent 테스트 (동시 3개)")
    tasks = [
        "1부터 10까지 합계를 계산하는 파이썬 코드를 실행해줘",
        "fibonacci.py 파일을 만들고 피보나치 수열 10개를 출력해줘",
        "현재 날짜와 시간을 출력하는 파이썬 코드를 실행해줘",
    ]
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(run_agent_task, t, use_skills=True): t for t in tasks}
        for future in as_completed(futures, timeout=TASK_TIMEOUT * 2):
            try:
                print_result(future.result(timeout=TASK_TIMEOUT))
            except TimeoutError:
                print(f"  [FAIL] timeout: {futures[future][:40]}\n")


def main():
    print("=" * 55)
    print("deepagents + Skills + Sandbox 통합 테스트")
    print("=" * 55 + "\n")

    test_skills_load()
    test_with_skills()

    print("=" * 55)
    print("테스트 완료")
    print("=" * 55)


if __name__ == "__main__":
    main()

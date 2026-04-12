"""
세션 관리 테스트
- 세션 재사용 / 독립 sandbox
- 세션 목록 조회
- 리소스 모니터링
- 최대 세션 수 제한
"""

import sys
sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork/agent")

from session_manager import SessionManager


def run_task(manager: SessionManager, session_id: str, task: str) -> str:
    session = manager.get_or_create(session_id)
    result = session.graph.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"configurable": {"thread_id": session_id}},
    )
    session.touch()
    return result["messages"][-1].content[:150]


def print_status(manager: SessionManager):
    print("\n--- 세션 현황 ---")
    for info in manager.list_sessions():
        print(f"  [{info.session_id}] 요청수:{info.request_count} 유휴:{info.idle_seconds:.0f}초 디스크:{info.workdir_size_kb}KB")
    stats = manager.stats()
    print(f"  합계: {stats['active_sessions']}/{stats['max_sessions']} 세션 | "
          f"총요청:{stats['total_requests']} | 디스크:{stats['total_workdir_kb']}KB")
    print("-----------------")


def main():
    manager = SessionManager(max_sessions=3)  # 테스트용 최대 3개

    print("=" * 50)
    print("테스트 1: 세션 재사용 + 파일 유지")
    print("=" * 50)

    r1 = run_task(manager, "session-A", "data.txt 파일을 만들고 '첫번째 요청' 이라고 써줘")
    print(f"[A] 요청1: {r1[:80]}")

    r2 = run_task(manager, "session-A", "data.txt 파일 내용을 읽어줘")
    print(f"[A] 요청2: {r2[:80]}")

    print_status(manager)

    print("\n" + "=" * 50)
    print("테스트 2: 다른 세션 독립 sandbox")
    print("=" * 50)

    r3 = run_task(manager, "session-B", "data.txt 파일이 있으면 내용, 없으면 없다고 해줘")
    print(f"[B] 요청1: {r3[:80]}")

    print_status(manager)

    print("\n" + "=" * 50)
    print("테스트 3: 최대 세션 수 제한 (max=3)")
    print("=" * 50)

    run_task(manager, "session-C", "안녕이라고 말해줘")
    print(f"[C] 세션 생성 성공")

    try:
        run_task(manager, "session-D", "안녕이라고 말해줘")
        print(f"[D] 세션 생성 성공 (예상치 못한 결과)")
    except RuntimeError as e:
        print(f"[D] 세션 생성 차단: {e}")

    print_status(manager)

    # 정리
    for sid in ["session-A", "session-B", "session-C"]:
        manager.close(sid)
    print(f"\n모든 세션 종료. 활성 세션: {manager.stats()['active_sessions']}")


if __name__ == "__main__":
    main()

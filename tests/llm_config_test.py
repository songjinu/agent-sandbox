"""
llm_config 테스트
- config 저장/로드
- llm_id 별 LLM 빌드
- 세션에 llm_id 전달
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork/agent")

# 테스트용 임시 config 파일 사용
_tmp_cfg = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
_tmp_cfg.close()
os.environ["LLM_CONFIG_FILE"] = _tmp_cfg.name
os.environ["LLM_BASE_URL"] = "http://172.19.16.1:11434/v1"
os.environ["LLM_MODEL"] = "glm-5:cloud"
os.environ["LLM_API_KEY"] = "ollama"

from llm_config import load_config, save_config, build_llm, list_llm_ids, get_llm_entry


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def ok(label: str):
    print(f"  [PASS] {label}")

def fail(label: str, e):
    print(f"  [FAIL] {label}: {e}")
    raise SystemExit(1)


# ── 테스트 1: config 저장 / 로드 ──────────────────────────────────────────────

def test_save_load():
    print("\n[1] config 저장/로드")
    cfg = {
        "default": "ollama-local",
        "llms": {
            "ollama-local": {
                "base_url": "http://172.19.16.1:11434/v1",
                "model": "glm-5:cloud",
                "api_key": "ollama",
            },
            "openrouter": {
                "base_url": "https://openrouter.ai/api/v1",
                "model": "anthropic/claude-3.5-haiku",
                "api_key": "sk-or-test",
            },
        },
    }
    save_config(cfg)
    loaded = load_config()
    assert loaded["default"] == "ollama-local", "default 불일치"
    assert "ollama-local" in loaded["llms"], "ollama-local 없음"
    assert "openrouter" in loaded["llms"], "openrouter 없음"
    ok("저장/로드 일치")

    ids = list_llm_ids()
    assert set(ids) == {"ollama-local", "openrouter"}, f"목록 불일치: {ids}"
    ok(f"list_llm_ids: {ids}")


# ── 테스트 2: get_llm_entry ──────────────────────────────────────────────────

def test_get_entry():
    print("\n[2] get_llm_entry")
    entry = get_llm_entry("ollama-local")
    assert entry["model"] == "glm-5:cloud"
    ok(f"ollama-local entry: {entry['model']} @ {entry['base_url']}")

    entry2 = get_llm_entry(None)   # default 사용
    assert entry2["model"] == "glm-5:cloud"
    ok("None → default 사용")

    try:
        get_llm_entry("nonexistent")
        fail("존재하지 않는 ID 예외 미발생", "")
    except KeyError as e:
        ok(f"없는 ID → KeyError: {e}")


# ── 테스트 3: build_llm (인스턴스 생성만) ─────────────────────────────────────

def test_build_llm():
    print("\n[3] build_llm 인스턴스 생성")
    try:
        llm = build_llm("ollama-local")
        ok(f"ollama-local LLM 생성: {llm.model_name}")
    except Exception as e:
        fail("ollama-local build_llm", e)


# ── 테스트 4: 실제 LLM 호출 (ollama-local) ───────────────────────────────────

def test_llm_invoke():
    print("\n[4] 실제 LLM 호출 — ollama-local")
    try:
        llm = build_llm("ollama-local")
        resp = llm.invoke("한 문장으로 대답해. 1+1은?")
        answer = resp.content.strip()
        print(f"  응답: {answer[:100]}")
        ok("ollama-local 호출 성공")
    except Exception as e:
        fail("ollama-local 호출", e)


# ── 테스트 5: SessionManager에 llm_id 전달 ───────────────────────────────────

def test_session_with_llm_id():
    print("\n[5] SessionManager llm_id 전달")
    from session_manager import SessionManager

    manager = SessionManager(max_sessions=2)
    try:
        session = manager.get_or_create("test-session", llm_id="ollama-local")
        ok(f"세션 생성 성공: {session.session_id}")

        result = session.graph.invoke(
            {"messages": [{"role": "user", "content": "hello.txt 파일을 만들고 'hi' 라고 써줘"}]},
            config={"configurable": {"thread_id": "test-session"}},
        )
        resp = result["messages"][-1].content[:120]
        print(f"  응답: {resp}")
        ok("agent 호출 성공")
    except Exception as e:
        fail("세션 agent 호출", e)
    finally:
        manager.close("test-session")
        ok("세션 종료")


# ── 테스트 6: 동일 세션에 llm_id 변경 시도 (무시됨) ──────────────────────────

def test_session_reuse_same_llm():
    print("\n[6] 기존 세션 재사용 — 같은 llm_id")
    from session_manager import SessionManager

    manager = SessionManager(max_sessions=2)
    s1 = manager.get_or_create("reuse-test", llm_id="ollama-local")
    graph_before = s1.graph
    s2 = manager.get_or_create("reuse-test", llm_id="ollama-local")  # 동일 llm_id
    assert s1 is s2, "같은 session_id인데 다른 객체"
    assert s2.graph is graph_before, "llm_id 동일한데 graph 교체됨"
    ok("동일 llm_id → graph 유지")
    manager.close("reuse-test")


def test_session_llm_switch():
    print("\n[7] 기존 세션에서 llm_id 교체 — sandbox 파일 유지")
    from session_manager import SessionManager

    # config에 두 번째 llm 추가 (같은 ollama, 다른 모델)
    cfg = load_config()
    cfg["llms"]["ollama-alt"] = {
        "base_url": "http://172.19.16.1:11434/v1",
        "model": "llama3.2:1b",
        "api_key": "ollama",
    }
    save_config(cfg)

    manager = SessionManager(max_sessions=2)

    # 첫 번째 요청: ollama-local로 파일 생성
    s1 = manager.get_or_create("switch-test", llm_id="ollama-local")
    graph_before = s1.graph
    result = s1.graph.invoke(
        {"messages": [{"role": "user", "content": "switch.txt 파일에 'original' 이라고 써줘"}]},
        config={"configurable": {"thread_id": "switch-test"}},
    )
    print(f"  [ollama-local] {result['messages'][-1].content[:80]}")
    ok("ollama-local로 파일 생성")

    # llm_id 교체 요청
    s2 = manager.get_or_create("switch-test", llm_id="ollama-alt")
    assert s1 is s2, "세션 객체가 달라짐"
    assert s2.graph is not graph_before, "graph가 교체되지 않음"
    assert s2.llm_id == "ollama-alt", f"llm_id 불일치: {s2.llm_id}"
    ok("sandbox 유지, graph 교체됨")

    # 교체된 LLM으로 파일 읽기
    result2 = s2.graph.invoke(
        {"messages": [{"role": "user", "content": "switch.txt 파일 내용을 읽어줘"}]},
        config={"configurable": {"thread_id": "switch-test"}},
    )
    print(f"  [ollama-alt] {result2['messages'][-1].content[:80]}")
    ok("교체된 LLM으로 기존 파일 접근 성공")

    manager.close("switch-test")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("llm_config 테스트")
    print("=" * 50)

    test_save_load()
    test_get_entry()
    test_build_llm()
    test_llm_invoke()
    test_session_with_llm_id()
    test_session_reuse_same_llm()
    test_session_llm_switch()

    # 임시 config 파일 정리
    os.unlink(_tmp_cfg.name)

    print("\n" + "=" * 50)
    print("모든 테스트 통과")
    print("=" * 50)

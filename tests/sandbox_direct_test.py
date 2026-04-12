"""
ProcessSandboxBackend 직접 기능 테스트 (LLM 없이)
- 파일 생성/읽기
- Python 코드 실행
- 커맨드 실행
- 타임아웃
- 동시 3개 격리
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork/agent")
from process_sandbox import ProcessSandboxBackend


def test_file_creation(sandbox: ProcessSandboxBackend) -> dict:
    """파일 생성 테스트"""
    result = sandbox.execute("echo 'Hello World!' > hello.txt && cat hello.txt")
    return {"test": "파일 생성", "output": result.output.strip(), "exit_code": result.exit_code}


def test_python_execution(sandbox: ProcessSandboxBackend) -> dict:
    """Python 코드 실행 테스트"""
    result = sandbox.execute("python3 -c \"print(sum(range(1, 11)))\"")
    return {"test": "Python 실행", "output": result.output.strip(), "exit_code": result.exit_code}


def test_command_execution(sandbox: ProcessSandboxBackend) -> dict:
    """커맨드 실행 테스트"""
    result = sandbox.execute("ls -la && pwd")
    return {"test": "커맨드 실행", "output": result.output.strip()[:100], "exit_code": result.exit_code}


def test_python_file(sandbox: ProcessSandboxBackend) -> dict:
    """Python 파일 생성 후 실행"""
    sandbox.execute("cat > fib.py << 'EOF'\ndef fib(n):\n    a,b=0,1\n    for _ in range(n):\n        print(a,end=' ')\n        a,b=b,a+b\nfib(10)\nEOF")
    result = sandbox.execute("python3 fib.py")
    return {"test": "Python 파일 실행", "output": result.output.strip(), "exit_code": result.exit_code}


def test_timeout(sandbox: ProcessSandboxBackend) -> dict:
    """타임아웃 테스트 (5초 제한, 10초 sleep)"""
    result = sandbox.execute("sleep 10", timeout=5)
    return {"test": "타임아웃", "output": result.output.strip(), "exit_code": result.exit_code}


def test_isolation(sandbox: ProcessSandboxBackend, req_id: str) -> dict:
    """격리 테스트 - 각 sandbox가 독립 디렉토리 사용"""
    sandbox.execute(f"echo '{req_id}' > myfile.txt")
    result = sandbox.execute("cat myfile.txt && ls")
    return {"test": f"격리[{req_id}]", "output": result.output.strip(), "exit_code": result.exit_code}


def run_all_tests(req_id: str) -> list:
    sandbox = ProcessSandboxBackend(req_id)
    results = []
    try:
        results.append(test_file_creation(sandbox))
        results.append(test_python_execution(sandbox))
        results.append(test_command_execution(sandbox))
        results.append(test_python_file(sandbox))
        results.append(test_timeout(sandbox))
        results.append(test_isolation(sandbox, req_id))
    finally:
        sandbox.cleanup()
    return results


def main():
    req_ids = ["req-A", "req-B", "req-C"]
    print(f"동시 {len(req_ids)}개 요청 테스트\n" + "="*50)

    start = time.time()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(run_all_tests, rid): rid for rid in req_ids}
        for future in as_completed(futures):
            rid = futures[future]
            results = future.result()
            print(f"\n[{rid}]")
            for r in results:
                status = "✓" if r["exit_code"] == 0 or r["test"] == "타임아웃" else "✗"
                print(f"  {status} {r['test']}: {r['output'][:80]}")

    print(f"\n총 소요시간: {time.time()-start:.1f}초")


if __name__ == "__main__":
    main()

"""
ProcessSandboxBackend 직접 기능 테스트 (LLM 없이)
- 파일 생성/읽기
- Python 코드 실행
- 커맨드 실행
- 타임아웃
- 디스크 용량 제한
- 동시 3개 격리
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/mnt/c/Users/qsky0/Documents/Claude/Projects/songwork/agent")


def ok(label: str, detail: str = ""):
    suffix = f": {detail}" if detail else ""
    print(f"  [PASS] {label}{suffix}")


def fail(label: str, detail: str = ""):
    suffix = f": {detail}" if detail else ""
    print(f"  [FAIL] {label}{suffix}")
    raise SystemExit(1)


# ── 기능 테스트 ────────────────────────────────────────────────────────────────

def test_file_creation():
    print("\n[1] 파일 생성/읽기")
    from process_sandbox import ProcessSandboxBackend
    sb = ProcessSandboxBackend("t-file")
    try:
        r = sb.execute("echo 'Hello World!' > hello.txt && cat hello.txt")
        assert r.exit_code == 0 and "Hello World!" in r.output
        ok("파일 생성/읽기", r.output.strip())
    finally:
        sb.cleanup()


def test_python_execution():
    print("\n[2] Python 실행")
    from process_sandbox import ProcessSandboxBackend
    sb = ProcessSandboxBackend("t-py")
    try:
        r = sb.execute("python3 -c \"print(sum(range(1, 11)))\"")
        assert r.exit_code == 0 and "55" in r.output
        ok("Python 실행", r.output.strip())
    finally:
        sb.cleanup()


def test_command_execution():
    print("\n[3] 커맨드 실행")
    from process_sandbox import ProcessSandboxBackend
    sb = ProcessSandboxBackend("t-cmd")
    try:
        r = sb.execute("ls -la && pwd")
        assert r.exit_code == 0
        ok("커맨드 실행", r.output.strip()[:60])
    finally:
        sb.cleanup()


def test_python_file():
    print("\n[4] Python 파일 생성 후 실행")
    from process_sandbox import ProcessSandboxBackend
    sb = ProcessSandboxBackend("t-pyfile")
    try:
        sb.execute("cat > fib.py << 'EOF'\ndef fib(n):\n    a,b=0,1\n    for _ in range(n):\n        print(a,end=' ')\n        a,b=b,a+b\nfib(10)\nEOF")
        r = sb.execute("python3 fib.py")
        assert r.exit_code == 0 and "0" in r.output
        ok("Python 파일 실행", r.output.strip())
    finally:
        sb.cleanup()


def test_timeout():
    print("\n[5] 타임아웃")
    from process_sandbox import ProcessSandboxBackend
    sb = ProcessSandboxBackend("t-timeout")
    try:
        r = sb.execute("sleep 10", timeout=3)
        assert r.exit_code == 124
        ok("타임아웃 차단 (3초 제한, sleep 10)")
    finally:
        sb.cleanup()


def test_disk_quota():
    print("\n[6] 디스크 용량 제한")
    from process_sandbox import ProcessSandboxBackend, DISK_LIMIT

    # 정상: 작은 파일
    sb = ProcessSandboxBackend("t-disk-ok")
    try:
        r = sb.execute("echo 'small' > small.txt")
        assert r.exit_code == 0
        ok(f"정상 범위 내 파일 생성 (한도: {DISK_LIMIT // (1024*1024)}MB)")
    finally:
        sb.cleanup()

    # 초과: 한도 이상으로 mock
    import unittest.mock as mock
    sb2 = ProcessSandboxBackend("t-disk-over")
    try:
        with mock.patch.object(sb2, '_workdir_size', return_value=DISK_LIMIT + 1):
            try:
                sb2.execute("echo hi")
                fail("디스크 초과 시 예외 미발생")
            except RuntimeError as e:
                ok("디스크 초과 차단", str(e))

        # upload_files 도 차단 확인
        with mock.patch.object(sb2, '_workdir_size', return_value=DISK_LIMIT + 1):
            try:
                sb2.upload_files([("test.txt", b"data")])
                fail("upload 디스크 초과 시 예외 미발생")
            except RuntimeError as e:
                ok("upload 디스크 초과 차단", str(e))
    finally:
        sb2.cleanup()

    # 환경변수로 한도 변경 확인
    os.environ["SANDBOX_DISK_LIMIT_MB"] = "1"
    import importlib, process_sandbox
    importlib.reload(process_sandbox)
    from process_sandbox import ProcessSandboxBackend as PSB2, DISK_LIMIT as DL2
    assert DL2 == 1 * 1024 * 1024, f"한도 재설정 실패: {DL2}"
    ok("환경변수로 한도 변경 확인 (1MB)")
    # 원복
    os.environ["SANDBOX_DISK_LIMIT_MB"] = "10"
    importlib.reload(process_sandbox)


def test_isolation():
    print("\n[7] 동시 3개 세션 격리")
    from process_sandbox import ProcessSandboxBackend

    def run(req_id):
        sb = ProcessSandboxBackend(req_id)
        try:
            sb.execute(f"echo '{req_id}' > myfile.txt")
            r = sb.execute("cat myfile.txt")
            assert req_id in r.output, f"격리 실패: {r.output}"
            return req_id, True
        finally:
            sb.cleanup()

    start = time.time()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run, f"iso-{c}") for c in ["A", "B", "C"]]
        for f in as_completed(futures):
            rid, success = f.result()
            if success:
                ok(f"세션 [{rid}] 독립 격리")
    ok(f"동시 3개 완료 ({time.time()-start:.1f}초)")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Sandbox 기능 테스트")
    print("=" * 50)

    test_file_creation()
    test_python_execution()
    test_command_execution()
    test_python_file()
    test_timeout()
    test_disk_quota()
    test_isolation()

    print("\n" + "=" * 50)
    print("모든 테스트 통과")
    print("=" * 50)

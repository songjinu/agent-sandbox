"""
Agent Pod 내 프로세스 기반 샌드박스 테스트
- 동시 요청 3개 제한
- 요청별 디렉토리 격리
- CPU/메모리 제한 (resource 모듈)
"""

import os
import time
import uuid
import shutil
import resource
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

WORKSPACE = "/tmp/sandbox_workspace"
MAX_CONCURRENT = 3
MEM_LIMIT = 256 * 1024 * 1024  # 256MB
CPU_TIME_LIMIT = 30  # 30초


def sandbox_runner(request_id: str, code: str) -> dict:
    """격리된 프로세스에서 코드 실행"""
    workdir = f"{WORKSPACE}/{request_id}"
    os.makedirs(workdir, exist_ok=True)
    os.chdir(workdir)

    # CPU 시간 제한
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_TIME_LIMIT, CPU_TIME_LIMIT))
    # 메모리 제한
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))

    start = time.time()
    try:
        exec_globals = {"__builtins__": __builtins__}
        exec(code, exec_globals)
        elapsed = time.time() - start
        # 결과 파일 목록
        files = os.listdir(workdir)
        return {"request_id": request_id, "status": "ok", "elapsed": f"{elapsed:.2f}s", "files": files}
    except Exception as e:
        return {"request_id": request_id, "status": "error", "error": str(e)}
    finally:
        # 디렉토리 정리
        shutil.rmtree(workdir, ignore_errors=True)


def run_requests():
    os.makedirs(WORKSPACE, exist_ok=True)

    # 테스트 요청 5개 (동시 3개 제한)
    requests = [
        ("hello world 파일 생성", """
with open('hello.txt', 'w') as f:
    f.write('Hello World!')
print('hello.txt 생성 완료')
"""),
        ("간단한 계산", """
result = sum(range(1000))
print(f'합계: {result}')
"""),
        ("파이썬 파일 생성", """
with open('script.py', 'w') as f:
    f.write("print('generated script')")
print('script.py 생성 완료')
"""),
        ("리스트 처리", """
data = [i**2 for i in range(100)]
print(f'최대값: {max(data)}')
"""),
        ("문자열 처리", """
text = 'sandbox test ' * 100
print(f'길이: {len(text)}')
"""),
    ]

    jobs = [(str(uuid.uuid4())[:8], code) for _, code in requests]
    names = {job[0]: name for job, (name, _) in zip(jobs, requests)}

    print(f"총 {len(jobs)}개 요청 / 동시 {MAX_CONCURRENT}개 제한\n")

    with ProcessPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(sandbox_runner, rid, code): rid for rid, code in jobs}
        for future in as_completed(futures):
            result = future.result()
            rid = result["request_id"]
            name = names[rid]
            if result["status"] == "ok":
                print(f"✓ [{rid}] {name} — {result['elapsed']} | 파일: {result.get('files', [])}")
            else:
                print(f"✗ [{rid}] {name} — 오류: {result['error']}")


if __name__ == "__main__":
    run_requests()

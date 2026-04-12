"""
프로세스 기반 커스텀 Sandbox Backend
- 요청별 디렉토리 격리
- CPU/메모리 제한 (resource 모듈)
- deepagents SandboxBackendProtocol 구현
"""

import os
import shlex
import shutil
import subprocess
import uuid

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

WORKSPACE = "/tmp/sandbox_workspace"
MEM_LIMIT = 256 * 1024 * 1024   # 256MB
CPU_TIME_LIMIT = 30              # 30초
DISK_LIMIT = 100 * 1024 * 1024  # 100MB (디렉토리 총 용량)
FILE_SIZE_LIMIT = 50 * 1024 * 1024  # 50MB (단일 파일)


def _set_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_TIME_LIMIT, CPU_TIME_LIMIT))
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_LIMIT, FILE_SIZE_LIMIT))


class ProcessSandboxBackend(BaseSandbox):
    """프로세스 + 디렉토리 기반 샌드박스 백엔드"""

    def __init__(self, request_id: str | None = None):
        self._id = request_id or str(uuid.uuid4())[:8]
        self._workdir = f"{WORKSPACE}/{self._id}"
        os.makedirs(self._workdir, exist_ok=True)

    @property
    def id(self) -> str:
        return self._id

    @property
    def workdir(self) -> str:
        return self._workdir

    def _workdir_size(self) -> int:
        """디렉토리 총 사용량 (bytes)"""
        total = 0
        for dp, _, files in os.walk(self._workdir):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        return total

    def _check_disk_quota(self):
        used = self._workdir_size()
        if used >= DISK_LIMIT:
            raise RuntimeError(
                f"디스크 용량 초과: {used // (1024*1024)}MB / {DISK_LIMIT // (1024*1024)}MB"
            )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        self._check_disk_quota()
        effective_timeout = timeout or CPU_TIME_LIMIT
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=self._workdir,
                preexec_fn=_set_limits,
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr if output else result.stderr
            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=False,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Error: 명령 실행 타임아웃 ({effective_timeout}초)",
                exit_code=124,
                truncated=False,
            )
        except Exception as e:
            return ExecuteResponse(output=f"Error: {e}", exit_code=1, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        self._check_disk_quota()
        responses = []
        for path, content in files:
            full_path = os.path.join(self._workdir, path.lstrip("/"))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(content)
            responses.append(FileUploadResponse(path=path, error=None))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            full_path = os.path.join(self._workdir, path.lstrip("/"))
            if not os.path.isfile(full_path):
                responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
            else:
                with open(full_path, "rb") as f:
                    responses.append(FileDownloadResponse(path=path, content=f.read(), error=None))
        return responses

    def cleanup(self):
        """작업 완료 후 디렉토리 정리"""
        shutil.rmtree(self._workdir, ignore_errors=True)

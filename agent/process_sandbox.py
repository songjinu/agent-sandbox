"""
프로세스 기반 커스텀 Sandbox Backend
- 요청별 디렉토리 격리
- CPU/메모리 제한 (resource 모듈)
- deepagents SandboxBackendProtocol 구현
- 파일 API(write/read/edit/ls/glob/grep) 경로를 sandbox 내부로 강제
"""

import os
import shlex
import shutil
import subprocess
import time
import uuid
from collections import deque

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    WriteResult,
    EditResult,
    FileInfo,
    GrepMatch,
)
from deepagents.backends.sandbox import BaseSandbox

WORKSPACE = "/tmp/sandbox_workspace"
MEM_LIMIT = 256 * 1024 * 1024  # 256MB
CPU_TIME_LIMIT = 30  # 30초
USE_BUBBLEWRAP = os.environ.get("USE_BUBBLEWRAP", "0") == "1"


def _set_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_TIME_LIMIT, CPU_TIME_LIMIT))
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))


def _bwrap_command(workdir: str, command: str) -> list[str]:
    """LLM 명령을 bubblewrap으로 감싸서 sandbox 외부 접근 차단.
    workdir만 read-write로 노출, 나머지 경로는 보이지 않음 (또는 읽기전용).
    workdir 경로는 bwrap 안에서도 동일 경로로 mount → _safe_path 결과 호환."""
    return [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", workdir, workdir,
        "--chdir", workdir,
        "--setenv", "PATH", "/usr/local/bin:/usr/bin",
        "--setenv", "HOME", workdir,
        "--unshare-all",
        "--share-net",
        "--die-with-parent",
        "bash", "-c", command,
    ]


class ProcessSandboxBackend(BaseSandbox):
    """프로세스 + 디렉토리 기반 샌드박스 백엔드"""

    def __init__(self, request_id: str | None = None):
        self._id = request_id or str(uuid.uuid4())[:8]
        self._workdir = f"{WORKSPACE}/{self._id}"
        os.makedirs(self._workdir, exist_ok=True)
        self._workdir_real = os.path.realpath(self._workdir)
        self._activity: deque = deque(maxlen=50)  # 최근 50개 활동

    @property
    def activity(self) -> list[dict]:
        return list(self._activity)

    def _log(self, action: str, target: str, status: str = "ok", detail: str = "") -> None:
        self._activity.append({
            "ts": time.time(),
            "action": action,
            "target": (target or "")[:200],
            "status": status,
            "detail": (detail or "")[:200],
        })

    @property
    def id(self) -> str:
        return self._id

    @property
    def workdir(self) -> str:
        return self._workdir

    def _safe_path(self, path: str) -> str:
        """LLM이 넘긴 경로를 sandbox 내부로 강제. 탈출 시 PermissionError.

        - 이미 workdir 안을 가리키는 절대경로는 그대로 (이중 nesting 방지)
        - 그 외 절대경로는 lstrip("/") 후 workdir 안으로 매핑
        """
        if not path:
            return self._workdir_real
        # 이미 workdir 내부를 가리키는 절대경로 (e.g. /tmp/sandbox_workspace/red/...)
        if path.startswith(self._workdir_real + os.sep) or path == self._workdir_real \
           or path.startswith(self._workdir + os.sep) or path == self._workdir:
            candidate = os.path.realpath(path)
        else:
            rel = path.lstrip("/")
            candidate = os.path.realpath(os.path.join(self._workdir_real, rel))
        if candidate != self._workdir_real and not candidate.startswith(self._workdir_real + os.sep):
            raise PermissionError(f"path escapes sandbox: {path!r}")
        return candidate

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = timeout or CPU_TIME_LIMIT
        cmd_summary = command.strip().split("\n")[0][:120]
        try:
            if USE_BUBBLEWRAP:
                argv = _bwrap_command(self._workdir, command)
                result = subprocess.run(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    preexec_fn=_set_limits,
                )
            else:
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
            self._log("execute", cmd_summary,
                      status="ok" if result.returncode == 0 else f"exit={result.returncode}",
                      detail=output.strip()[:120])
            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=False,
            )
        except subprocess.TimeoutExpired:
            self._log("execute", cmd_summary, status="timeout")
            return ExecuteResponse(
                output=f"Error: 명령 실행 타임아웃 ({effective_timeout}초)",
                exit_code=124,
                truncated=False,
            )
        except Exception as e:
            self._log("execute", cmd_summary, status="error", detail=str(e)[:120])
            return ExecuteResponse(output=f"Error: {e}", exit_code=1, truncated=False)

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            safe = self._safe_path(file_path)
        except PermissionError as e:
            self._log("write", file_path, status="blocked", detail=str(e))
            return WriteResult(error=str(e), path=file_path)
        self._log("write", file_path, detail=f"{len(content)}B")
        return super().write(safe, content)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        try:
            safe = self._safe_path(file_path)
        except PermissionError as e:
            self._log("read", file_path, status="blocked", detail=str(e))
            return f"Error: {e}"
        self._log("read", file_path)
        return super().read(safe, offset=offset, limit=limit)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        try:
            safe = self._safe_path(file_path)
        except PermissionError as e:
            self._log("edit", file_path, status="blocked", detail=str(e))
            return EditResult(error=str(e), path=file_path)
        self._log("edit", file_path, detail=f"replace_all={replace_all}")
        return super().edit(safe, old_string, new_string, replace_all=replace_all)

    def ls_info(self, path: str) -> list[FileInfo]:
        try:
            safe = self._safe_path(path)
        except PermissionError:
            self._log("ls", path, status="blocked")
            return []
        self._log("ls", path)
        return super().ls_info(safe)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        try:
            safe = self._safe_path(path)
        except PermissionError:
            self._log("glob", f"{pattern} in {path}", status="blocked")
            return []
        self._log("glob", f"{pattern} in {path}")
        return super().glob_info(pattern, safe)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[GrepMatch] | str:
        try:
            safe = self._safe_path(path) if path else self._workdir_real
        except PermissionError as e:
            self._log("grep", f"{pattern}", status="blocked", detail=str(e))
            return f"Error: {e}"
        self._log("grep", pattern, detail=f"path={path or '.'} glob={glob or ''}")
        return super().grep_raw(pattern, path=safe, glob=glob)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
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

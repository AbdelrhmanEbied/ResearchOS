import asyncio
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

TIMEOUT_SECONDS = 10
MEMORY_LIMIT_MB = 256
OUTPUT_LIMIT_CHARS = 50_000

RESTRICTED_IMPORTS = (
    "os",
    "subprocess",
    "socket",
    "shutil",
    "ctypes",
    "multiprocessing",
    "threading",
    "http",
    "urllib",
    "requests",
    "importlib",
)


@dataclass
class ExecutionResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    exit_code: int | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)


def _build_guard(code: str) -> str:
    blocked = ", ".join(f'"{m}"' for m in RESTRICTED_IMPORTS)
    return f"""
import sys

_BLOCKED = [{blocked}]

class _BlockedImport:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _BLOCKED:
            raise ImportError(f"Import of '{{name}}' is not allowed in the sandbox")
        return None

sys.meta_path.insert(0, _BlockedImport())

for _name in list(sys.modules):
    if _name.split(".")[0] in _BLOCKED:
        del sys.modules[_name]

import resource

resource.setrlimit(resource.RLIMIT_AS, ({MEMORY_LIMIT_MB} * 1024 * 1024, {MEMORY_LIMIT_MB} * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))

code = {code!r}
exec(compile(code, "<sandbox>", "exec"))
"""


async def execute_code(code: str, timeout: int = TIMEOUT_SECONDS) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix="agent_sandbox_") as tmp:
        script = Path(tmp) / "run.py"
        script.write_text(_build_guard(code))

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmp,
            limit=OUTPUT_LIMIT_CHARS * 2,
        )
        try:
            stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecutionResult(
                success=False,
                timed_out=True,
                error=f"Execution timed out after {timeout}s",
            )

    stdout = stdout_raw.decode(errors="replace")[:OUTPUT_LIMIT_CHARS]
    stderr = stderr_raw.decode(errors="replace")[:OUTPUT_LIMIT_CHARS]

    return ExecutionResult(
        success=proc.returncode == 0,
        stdout=stdout,
        stderr=stderr,
        exit_code=proc.returncode,
        error=None if proc.returncode == 0 else f"Exit code {proc.returncode}",
    )

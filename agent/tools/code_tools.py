from langchain_core.tools import tool

from agent.sandbox.executor import ExecutionResult, execute_code
from agent.state.schemas import Evidence


@tool
async def run_code(code: str, timeout: int = 10) -> dict:
    """Execute Python code in a sandbox. Returns success, stdout, stderr and the exit code."""
    result = await execute_code(code, timeout=timeout)
    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "error": result.error,
        "timed_out": result.timed_out,
    }


def build_code_evidence(result: ExecutionResult, code: str) -> list[Evidence]:
    from uuid import uuid4

    content = result.stdout.strip() or result.stderr.strip() or result.error or "(no output)"
    return [
        Evidence(
            id=uuid4().hex,
            content=content,
            source_type="code",
            score=1.0,
            metadata={"exit_code": result.exit_code, "code": code[:2000]},
        )
    ]

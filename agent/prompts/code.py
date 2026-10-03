from pydantic import BaseModel, Field

PLAN_CODE_SYSTEM_PROMPT = """\
You are a Python engineer. Write a single Python script that answers the
given task.

Rules:
- Standard library only (no pip installs).
- Script must print its final result to stdout.
- No network access, no file writes outside temp, no user input().
- Keep it under 80 lines.
- Defensive: handle missing/empty data gracefully.
"""

PLAN_CODE_HUMAN_PROMPT = """\
Task: {task}

Research question: {question}

Write the Python script."""

INTERPRET_SYSTEM_PROMPT = """\
You are a research analyst. Convert code execution output into a concise
finding for a research answer.

Rules:
- 1-3 sentences.
- State the concrete numbers/result.
- If the code failed, state what failed.
"""

INTERPRET_HUMAN_PROMPT = """\
Task: {task}

Code:
```python
{code}
```

Exit code: {exit_code}
Stdout: {stdout}
Stderr: {stderr}

Extract the finding."""


class CodeScript(BaseModel):
    code: str
    explanation: str = ""


class FindingOutput(BaseModel):
    findings: list[str] = Field(min_length=1, max_length=3)

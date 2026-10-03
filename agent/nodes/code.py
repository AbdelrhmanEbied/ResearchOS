from agent.llms import build_structured_llm
from agent.prompts.code import (
    INTERPRET_HUMAN_PROMPT,
    INTERPRET_SYSTEM_PROMPT,
    PLAN_CODE_HUMAN_PROMPT,
    PLAN_CODE_SYSTEM_PROMPT,
    CodeScript,
    FindingOutput,
)
from agent.sandbox.executor import ExecutionResult
from agent.state.schemas import AgentState, active_task
from agent.tools.code_tools import build_code_evidence, run_code

MAX_ATTEMPTS = 2


def _task_query(state: AgentState) -> str:
    task = active_task(state)
    if task:
        return task.query
    if state.get("plan"):
        return state["plan"].objective
    return state["query"]


async def plan_code(state: AgentState) -> dict:
    llm = build_structured_llm(CodeScript)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": PLAN_CODE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": PLAN_CODE_HUMAN_PROMPT.format(
                    task=_task_query(state), question=state["query"]
                ),
            },
        ]
    )
    return {"code_output": {"code": response.code, "explanation": response.explanation}}


async def execute(state: AgentState) -> dict:
    code = state["code_output"]["code"]
    try:
        out = await run_code.ainvoke({"code": code})
    except Exception as exc:
        out = {"success": False, "stdout": "", "stderr": "", "exit_code": None, "error": str(exc)}
    attempts = state.get("code_attempts", 0) + 1
    return {
        "code_output": {
            "code": code,
            "explanation": state["code_output"].get("explanation", ""),
            "success": out.get("success", False),
            "stdout": out.get("stdout", ""),
            "stderr": out.get("stderr", ""),
            "exit_code": out.get("exit_code"),
            "error": out.get("error"),
        },
        "code_attempts": attempts,
    }


async def interpret(state: AgentState) -> dict:
    out = state["code_output"]
    llm = build_structured_llm(FindingOutput)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": INTERPRET_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": INTERPRET_HUMAN_PROMPT.format(
                    task=_task_query(state),
                    code=out["code"],
                    exit_code=out.get("exit_code"),
                    stdout=out.get("stdout", "")[:3000],
                    stderr=out.get("stderr", "")[:2000],
                ),
            },
        ]
    )
    fake_result = ExecutionResult(
        success=out.get("success", False),
        stdout="\n".join(response.findings),
        exit_code=out.get("exit_code"),
    )
    evidence = build_code_evidence(fake_result, out["code"])
    return {"evidence": evidence, "code_evidence": evidence, "code_output": None}


async def accumulate(state: AgentState) -> dict:
    return {"status": "researching", "code_evidence": [], "code_output": None}


def route_execution(state: AgentState) -> str:
    out = state.get("code_output") or {}
    if out.get("success"):
        return "interpret"
    if state.get("code_attempts", 0) < MAX_ATTEMPTS:
        return "plan_code"
    return "accumulate"

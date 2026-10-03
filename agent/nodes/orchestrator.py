from uuid import uuid4

from agent.llms import build_structured_llm
from agent.prompts.orchestrator import (
    PLAN_HUMAN_PROMPT,
    PLAN_SYSTEM_PROMPT,
    REPLAN_HUMAN_PROMPT,
    REPLAN_SYSTEM_PROMPT,
    ResearchPlanDraft,
)
from agent.state.schemas import AgentState, Evidence, ResearchPlan, ResearchTask
from rag.rag_schemas import _domain_of, _snippet_of
from settings import get_settings_store

MAX_RESEARCH_ITERATIONS = 3


def max_research_iterations() -> int:
    return get_settings_store().get_agent()["max_research_iterations"]


def is_thinking(state: AgentState) -> bool:
    """Effort level. Instant skips analysis, verification and quality review."""
    return state.get("agent_mode") == "thinking"


def route_after_intent(state: AgentState) -> str:
    return "plan" if state.get("intent") == "research" else "draft"


def route_after_writing(state: AgentState) -> str:
    return "quality" if is_thinking(state) else "finalize"


def _recent_evidence(state: AgentState, limit: int = 10) -> str:
    ev = state.get("evidence", [])[-limit:]
    lines = []
    for e in ev:
        src = e.source_url or e.source_title or e.document_id or e.source_type
        lines.append(f"- ({src}) {e.content[:200]}")
    return "\n".join(lines) or "(none)"


def _chat_history(state: AgentState, limit: int = 12) -> str:
    history = state.get("history") or []
    lines = [f"{m.get('role')}: {m.get('content')}" for m in history[-limit:]]
    return "\n".join(lines) or "(none)"


def _plan_system(state: AgentState) -> str:
    """Base planner prompt plus this run's constraints (tools, effort)."""
    is_replan = state.get("iteration", 0) > 0
    system = REPLAN_SYSTEM_PROMPT if is_replan else PLAN_SYSTEM_PROMPT

    allowed = state.get("allowed_tools")
    extra = []
    if allowed and len(allowed) < 3:
        extra.append(
            "This run may ONLY use these graph types: "
            + ", ".join(f'"{t}"' for t in allowed)
            + ". Anything else would be wasted work."
        )
    if not is_thinking(state):
        extra.append(
            "Keep the plan minimal: at most 2 tasks, and only tasks that are strictly necessary."
        )
    if not extra:
        return system
    return system + "\n" + "\n".join(f"- {line}" for line in extra) + "\n"


async def plan(state: AgentState) -> dict:
    is_replan = state.get("iteration", 0) > 0
    allowed = state.get("allowed_tools")

    if is_replan:
        human = REPLAN_HUMAN_PROMPT.format(
            question=state["query"],
            gaps="\n".join(f"- {g}" for g in state.get("gaps", [])) or "(none)",
            evidence_count=len(state.get("evidence", [])),
            history="\n".join(
                f"- [{t.graph}] {t.query}"
                for t in (state["plan"].tasks if state.get("plan") else [])
            )
            or "(none)",
        )
    else:
        human = PLAN_HUMAN_PROMPT.format(
            question=state["query"],
            history=_chat_history(state),
            context=_recent_evidence(state),
            gaps="",
        )

    if not is_replan and allowed and len(allowed) == 1:
        objective = state["query"]
        tasks = [ResearchTask(id=uuid4().hex, graph=allowed[0], query=state["query"])]
    else:
        llm = build_structured_llm(ResearchPlanDraft)
        response = await llm.ainvoke(
            [
                {"role": "system", "content": _plan_system(state)},
                {"role": "user", "content": human},
            ]
        )
        objective = response.objective
        tasks = [
            ResearchTask(id=t.id, graph=t.graph, query=t.query, depends_on=t.depends_on)
            for t in response.tasks
            if allowed is None or t.graph in allowed
        ]
    new_plan = ResearchPlan(
        objective=objective,
        tasks=tasks,
        max_iterations=max_research_iterations(),
    )
    return {
        "plan": new_plan,
        "iteration": state.get("iteration", 0) + 1,
        "current_task_id": None,
        "completed_task_ids": [],
        "status": "planning",
        "should_replan": False,
    }


async def prepare_task(state: AgentState) -> dict:
    plan_obj = state.get("plan")
    if not plan_obj:
        return {"current_task_id": None}
    done = set(state.get("completed_task_ids", []))
    for task in plan_obj.tasks:
        if task.id in done:
            continue
        if all(dep in done for dep in task.depends_on):
            return {"current_task_id": task.id, "status": "researching"}
    return {"current_task_id": None}


def route_task(state: AgentState) -> str:
    task_id = state.get("current_task_id")
    if not task_id:
        return "analysis" if is_thinking(state) else "writing"
    plan_obj = state.get("plan")
    for task in plan_obj.tasks:
        if task.id == task_id:
            return f"task_{task.graph}"
    return "analysis" if is_thinking(state) else "writing"


async def mark_task_done(state: AgentState) -> dict:
    completed = list(state.get("completed_task_ids", []))
    task_id = state.get("current_task_id")
    if task_id and task_id not in completed:
        completed.append(task_id)
    return {"completed_task_ids": completed, "current_task_id": None}


def route_after_research(state: AgentState) -> str:
    if state.get("should_replan") and state.get("iteration", 0) < (
        state["plan"].max_iterations if state.get("plan") else 1
    ):
        return "replan"
    return "writing"


def _source_entry(evidence: Evidence) -> dict | None:
    if evidence.source_url:
        return {
            "source": "web",
            "label": evidence.source_title or evidence.source_url,
            "name": evidence.source_title,
            "title": evidence.source_title,
            "url": evidence.source_url,
            "domain": _domain_of(evidence.source_url),
            "snippet": _snippet_of(evidence.content),
        }
    if evidence.source_type == "document" and evidence.document_id:
        return {
            "source": "rag",
            "label": evidence.source_title or f"Document {evidence.document_id}",
            "document_id": evidence.document_id,
            "chunk_id": (evidence.metadata or {}).get("chunk_id"),
            "snippet": _snippet_of(evidence.content),
        }
    if evidence.source_type == "code":
        return {
            "source": "code",
            "label": "Code execution",
            "snippet": _snippet_of(evidence.content),
        }
    return None


def _source_key(entry: dict) -> str:
    if entry.get("url"):
        return entry["url"]
    if entry.get("document_id"):
        return f"doc:{entry['document_id']}:{entry.get('chunk_id')}"
    return entry.get("label") or entry.get("source") or "source"


async def finalize(state: AgentState) -> dict:
    sources: list[dict] = []
    seen: set[str] = set()
    for e in state.get("evidence", []):
        entry = _source_entry(e)
        if not entry:
            continue
        key = _source_key(entry)
        if key in seen:
            continue
        seen.add(key)
        sources.append(entry)
    return {
        "response": state.get("draft"),
        "sources": sources,
        "status": "done",
    }

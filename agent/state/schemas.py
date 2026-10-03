from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


def replace_history(_current: list[ChatMessage], new: list[ChatMessage]) -> list[ChatMessage]:
    return new


def merge_evidence(
    current: list[Evidence] | None,
    new: list[Evidence],
) -> list[Evidence]:
    if not current:
        return new

    seen = {e.id for e in current}
    merged = list(current)
    for item in new:
        if item.id not in seen:
            merged.append(item)
            seen.add(item.id)
    return merged


class Evidence(BaseModel):
    id: str
    content: str
    source_type: Literal["web", "document", "code"]
    source_url: str | None = None
    source_title: str | None = None
    document_id: str | None = None
    score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class Claim(BaseModel):
    id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["supported", "partially_supported", "contradicted", "unverified"] = "unverified"


class ResearchTask(BaseModel):
    id: str
    graph: Literal["web", "document", "code"]
    query: str
    depends_on: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    objective: str
    tasks: list[ResearchTask] = Field(default_factory=list)
    max_iterations: int = 3


class VerificationResult(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    sufficient: bool = False
    gaps: list[str] = Field(default_factory=list)


class Theme(BaseModel):
    id: str
    name: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


def active_task(state: dict) -> ResearchTask | None:
    plan_obj = state.get("plan")
    task_id = state.get("current_task_id")
    if not plan_obj or not task_id:
        return None
    for task in plan_obj.tasks:
        if task.id == task_id:
            return task
    return None


class AgentState(TypedDict):
    query: str
    conversation_id: str | None
    history: Annotated[list[ChatMessage], replace_history]
    llm_config: dict | None
    retrieval_config: dict | None
    agent_mode: str | None
    mode_override: str | None
    source_override: str | None

    intent: str | None
    allowed_tools: list[str] | None
    routing_reason: str | None

    plan: ResearchPlan | None
    iteration: int
    current_task_id: str | None
    completed_task_ids: list[str]

    evidence: Annotated[list[Evidence], merge_evidence]

    themes: list[Theme]
    claims: list[Claim]
    gaps: list[str]

    verification: VerificationResult | None

    draft: str | None
    outline: list[str]
    revision: int

    quality_pass: bool
    quality_feedback: list[str]

    response: str | None
    sources: list[dict]

    status: Literal[
        "idle",
        "planning",
        "researching",
        "analyzing",
        "verifying",
        "writing",
        "quality",
        "done",
        "failed",
    ]
    should_replan: bool

    messages: Annotated[list, lambda x, y: x + y]

    search_queries: list[str]
    search_retry: int
    web_results: list[dict]
    unique_results: list[dict]
    ranked_results: list[dict]
    web_pages: list[dict]
    web_evidence: list[Evidence]

    doc_retrieved: list[dict]
    doc_evidence: list[Evidence]

    code_attempts: int
    code_output: dict | None
    code_evidence: list[Evidence]


def initial_state(query: str, **overrides) -> AgentState:
    state: AgentState = {
        "query": query,
        "conversation_id": None,
        "history": [],
        "llm_config": None,
        "retrieval_config": None,
        "agent_mode": None,
        "mode_override": None,
        "source_override": None,
        "intent": None,
        "allowed_tools": None,
        "routing_reason": None,
        "plan": None,
        "iteration": 0,
        "current_task_id": None,
        "completed_task_ids": [],
        "evidence": [],
        "themes": [],
        "claims": [],
        "gaps": [],
        "verification": None,
        "draft": None,
        "outline": [],
        "revision": 0,
        "quality_pass": False,
        "quality_feedback": [],
        "response": None,
        "sources": [],
        "status": "idle",
        "should_replan": False,
        "messages": [],
        "search_queries": [],
        "search_retry": 0,
        "web_results": [],
        "unique_results": [],
        "ranked_results": [],
        "web_pages": [],
        "web_evidence": [],
        "doc_retrieved": [],
        "doc_evidence": [],
        "code_attempts": 0,
        "code_output": None,
        "code_evidence": [],
    }
    state.update(overrides)
    return state

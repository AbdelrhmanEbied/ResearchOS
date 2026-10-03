from agent.llms import (
    build_structured_llm,
    chunk_text_parts,
    get_llm,
    thinking_call_kwargs,
)
from agent.nodes.analysis import _format_evidence
from agent.prompts.writing import (
    DRAFT_HUMAN_PROMPT,
    DRAFT_SYSTEM_PROMPT,
    OUTLINE_HUMAN_PROMPT,
    OUTLINE_SYSTEM_PROMPT,
    QUICK_HUMAN_PROMPT,
    QUICK_SYSTEM_PROMPT,
    REVISE_HUMAN_PROMPT,
    REVISE_SYSTEM_PROMPT,
    OutlineOutput,
)
from agent.state.schemas import AgentState

MAX_REVISIONS = 3


def _history_text(state: AgentState, limit: int = 12) -> str:
    history = state.get("history") or []
    lines = [f"{m.get('role')}: {m.get('content')}" for m in history[-limit:]]
    return "\n".join(lines) or "(none)"


def _claims_text(state: AgentState) -> str:
    lines = []
    for c in state.get("claims", []):
        lines.append(f"[{c.status}] {c.text} (evidence: {', '.join(c.evidence_ids)})")
    return "\n".join(lines) or "(none)"


async def make_outline(state: AgentState) -> dict:
    llm = build_structured_llm(OutlineOutput)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": OUTLINE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": OUTLINE_HUMAN_PROMPT.format(
                    question=state["query"],
                    claims=_claims_text(state),
                    gaps=", ".join(state.get("gaps", [])) or "(none)",
                ),
            },
        ]
    )
    outline = [f"{s.heading}: {s.summary}" for s in response.sections]
    return {"outline": outline, "status": "writing"}


async def _stream_answer(llm, messages: list[dict], **kwargs) -> str:
    """Stream the draft so the first token reaches the client immediately."""
    parts: list[str] = []
    async for chunk in llm.astream(messages, **kwargs):
        parts.extend(chunk_text_parts(getattr(chunk, "content", None)))
    return "".join(parts)


async def draft(state: AgentState) -> dict:
    kwargs = thinking_call_kwargs(state.get("agent_mode"))

    if state.get("quality_feedback") and state.get("draft"):
        llm = get_llm()
        text = await _stream_answer(
            llm,
            [
                {"role": "system", "content": REVISE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": REVISE_HUMAN_PROMPT.format(
                        question=state["query"],
                        draft=state["draft"],
                        feedback="\n".join(f"- {f}" for f in state["quality_feedback"]),
                    ),
                },
            ],
            **kwargs,
        )
        return {
            "draft": text,
            "revision": state.get("revision", 0) + 1,
            "quality_feedback": [],
        }

    llm = get_llm()

    if state.get("intent") == "quick":
        text = await _stream_answer(
            llm,
            [
                {"role": "system", "content": QUICK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": QUICK_HUMAN_PROMPT.format(
                        question=state["query"],
                        history=_history_text(state),
                    ),
                },
            ],
            **kwargs,
        )
        return {"draft": text, "status": "writing"}

    outline_text = "\n".join(f"- {s}" for s in state.get("outline", [])) or "(no outline)"
    text = await _stream_answer(
        llm,
        [
            {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": DRAFT_HUMAN_PROMPT.format(
                    question=state["query"],
                    outline=outline_text,
                    claims=_claims_text(state),
                    evidence=_format_evidence(state),
                    gaps=", ".join(state.get("gaps", [])) or "(none)",
                ),
            },
        ],
        **kwargs,
    )
    return {"draft": text, "status": "writing"}

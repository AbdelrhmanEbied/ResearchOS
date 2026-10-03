from agent.llms import build_structured_llm
from agent.prompts.quality import QUALITY_HUMAN_PROMPT, QUALITY_SYSTEM_PROMPT, QualityOutput
from agent.state.schemas import AgentState


def _claims_text(state: AgentState) -> str:
    return "\n".join(f"[{c.status}] {c.text}" for c in state.get("claims", [])) or "(none)"


async def check(state: AgentState) -> dict:
    if not state.get("draft"):
        return {
            "quality_pass": False,
            "quality_feedback": ["No draft was produced."],
            "status": "quality",
        }

    llm = build_structured_llm(QualityOutput)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": QUALITY_HUMAN_PROMPT.format(
                    question=state["query"],
                    claims=_claims_text(state),
                    draft=state["draft"],
                ),
            },
        ]
    )
    return {
        "quality_pass": response.passed,
        "quality_feedback": response.feedback,
        "status": "quality",
    }


def route_quality(state: AgentState) -> str:
    if state.get("quality_pass"):
        return "done"
    if state.get("revision", 0) >= 3:
        return "done"
    return "revise"

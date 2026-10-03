from agent.llms import build_structured_llm
from agent.nodes.analysis import EVIDENCE_ITEM_CHARS, _format_evidence
from agent.prompts.verification import VERIFY_HUMAN_PROMPT, VERIFY_SYSTEM_PROMPT, VerifyOutput
from agent.state.schemas import AgentState, Claim, VerificationResult


def _format_claims(claims: list[Claim]) -> str:
    return "\n".join(f"{i}. {c.text}" for i, c in enumerate(claims)) or "(none)"


async def verify_claims(state: AgentState) -> dict:
    claims = state.get("claims", [])
    if not claims:
        gaps = state.get("gaps") or ["No claims were produced."]
        return {
            "claims": claims,
            "verification": VerificationResult(claims=[], sufficient=False, gaps=gaps),
            "gaps": gaps,
            "should_replan": True,
            "status": "verifying",
        }

    llm = build_structured_llm(VerifyOutput)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": VERIFY_HUMAN_PROMPT.format(
                    question=state["query"],
                    gaps=", ".join(state.get("gaps", [])) or "(none)",
                    claims=_format_claims(claims),
                    evidence=_format_evidence(state, EVIDENCE_ITEM_CHARS),
                ),
            },
        ]
    )

    status_by_index = {v.index: v.status for v in response.verdicts}
    verified = [
        c.model_copy(update={"status": status_by_index.get(i, "unverified")})
        for i, c in enumerate(claims)
    ]
    result = VerificationResult(
        claims=verified,
        sufficient=response.sufficient,
        gaps=response.gaps or state.get("gaps", []),
    )
    return {
        "claims": verified,
        "verification": result,
        "gaps": result.gaps,
        "should_replan": not response.sufficient,
        "status": "verifying",
    }

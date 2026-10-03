from uuid import uuid4

from agent.llms import build_structured_llm
from agent.prompts.analysis import (
    CLAIMS_HUMAN_PROMPT,
    CLAIMS_SYSTEM_PROMPT,
    CLUSTER_HUMAN_PROMPT,
    CLUSTER_SYSTEM_PROMPT,
    ClaimsOutput,
    ClusterOutput,
)
from agent.state.schemas import AgentState, Claim, Theme

EVIDENCE_ITEM_CHARS = 1500


def _format_evidence(state: AgentState, max_chars: int | None = None) -> str:
    lines = []
    for e in state.get("evidence", []):
        src = e.source_url or e.source_title or e.document_id or e.source_type
        content = e.content
        if max_chars is not None and len(content) > max_chars:
            content = content[:max_chars] + " ..."
        lines.append(f"[{e.id}] ({src}) {content}")
    return "\n".join(lines) or "(no evidence)"


async def cluster(state: AgentState) -> dict:
    llm = build_structured_llm(ClusterOutput)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": CLUSTER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": CLUSTER_HUMAN_PROMPT.format(
                    question=state["query"], evidence=_format_evidence(state, EVIDENCE_ITEM_CHARS)
                ),
            },
        ]
    )
    themes = [
        Theme(id=uuid4().hex, name=t.name, summary=t.summary, evidence_ids=t.evidence_ids) for t in response.themes
    ]
    return {"themes": themes, "status": "analyzing"}


async def extract_claims(state: AgentState) -> dict:
    llm = build_structured_llm(ClaimsOutput)
    themes_text = "\n".join(f"- {t.name}: {t.summary}" for t in state.get("themes", [])) or "(none)"
    response = await llm.ainvoke(
        [
            {"role": "system", "content": CLAIMS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": CLAIMS_HUMAN_PROMPT.format(
                    question=state["query"],
                    themes=themes_text,
                    evidence=_format_evidence(state, EVIDENCE_ITEM_CHARS),
                ),
            },
        ]
    )
    valid_ids = {e.id for e in state.get("evidence", [])}
    claims = [
        Claim(
            id=uuid4().hex,
            text=c.text,
            evidence_ids=[eid for eid in c.evidence_ids if eid in valid_ids],
        )
        for c in response.claims
    ]
    return {"claims": claims, "gaps": response.gaps}

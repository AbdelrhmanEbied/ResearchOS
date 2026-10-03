from pydantic import BaseModel, Field

CLUSTER_SYSTEM_PROMPT = """\
You are a research analyst. Group the given evidence items into coherent themes.

Rules:
- 1 to 6 themes.
- Each theme has a short name and a 1-2 sentence summary.
- Reference evidence by their exact ids.
- Every evidence item should be used at most once across all themes.
"""

CLUSTER_HUMAN_PROMPT = """\
Research question: {question}

Evidence items:
{evidence}

Group these into themes."""

CLAIMS_SYSTEM_PROMPT = """\
You are a research analyst. Extract factual claims that the evidence supports.

Rules:
- 1 to 10 claims.
- Each claim must be directly grounded in cited evidence ids (from the list provided).
- Claims must be specific and verifiable, not vague.
- If evidence is weak or missing, say so — do not invent.

Then identify what information is still MISSING to fully answer the research
question: the gaps between the claims and a complete answer. If nothing is
missing, return gaps = [].
"""

CLAIMS_HUMAN_PROMPT = """\
Research question: {question}

Themes:
{themes}

Evidence:
{evidence}

Extract claims with supporting evidence ids, then the gaps in coverage."""


class ThemeDraft(BaseModel):
    name: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class ClusterOutput(BaseModel):
    themes: list[ThemeDraft] = Field(min_length=1, max_length=6)


class ClaimDraft(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimsOutput(BaseModel):
    claims: list[ClaimDraft] = Field(min_length=1, max_length=10)
    gaps: list[str] = Field(default_factory=list, max_length=8)

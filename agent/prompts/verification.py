from pydantic import BaseModel, Field

VERIFY_SYSTEM_PROMPT = """\
You are a claim verification engine. For each claim, check whether the cited
evidence (and any other evidence) supports, partially supports, contradicts,
or does not support the claim.

Status meanings:
- "supported": evidence directly and fully backs the claim
- "partially_supported": evidence backs part of the claim or is weaker than needed
- "contradicted": evidence disagrees with the claim
- "unverified": not enough evidence either way

Rules:
- Judge ONLY by the evidence provided. No outside knowledge.
- Every claim must get exactly one status.

After verifying, decide whether the verified claims (supported or
partially_supported) are enough to answer the research question:
- if they are: sufficient = true, gaps = []
- if they are not: sufficient = false, and list the specific gaps that the
  remaining evidence must fill. Reuse and refine known gaps where relevant.
"""

VERIFY_HUMAN_PROMPT = """\
Research question: {question}

Known gaps so far: {gaps}

Claims:
{claims}

Evidence:
{evidence}

Verify each claim, then decide sufficiency."""


class ClaimVerdict(BaseModel):
    index: int
    status: str = Field(pattern="^(supported|partially_supported|contradicted|unverified)$")
    reasoning: str


class VerifyOutput(BaseModel):
    verdicts: list[ClaimVerdict] = Field(min_length=1)
    sufficient: bool = True
    gaps: list[str] = Field(default_factory=list, max_length=8)

from pydantic import BaseModel, Field

QUALITY_SYSTEM_PROMPT = """\
You are a research quality checker. Review the draft against the research
question, the claims, and the evidence.

Check for:
1. Does it actually answer the question?
2. Are claims grounded in cited evidence (citations [e1] etc. exist)?
3. Any unsupported or invented statements?
4. Are gaps acknowledged rather than papered over?
5. Structure, clarity, correctness.

Rules:
- passed=true ONLY if there are no substantive problems.
- feedback: specific, actionable items (empty list if passed).
"""

QUALITY_HUMAN_PROMPT = """\
Research question: {question}

Claims verified:
{claims}

Draft:
{draft}

Judge the draft."""


class QualityOutput(BaseModel):
    passed: bool
    feedback: list[str] = Field(default_factory=list, max_length=10)

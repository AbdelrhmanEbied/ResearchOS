from pydantic import BaseModel, Field

QUERY_SYSTEM_PROMPT = """\
You are a search-query generator for a research assistant.
Given a research task, produce diverse, high-recall web search queries.

Rules:
- 3 to 5 queries.
- Each query targets a different angle (statistics, mechanisms, critiques, recent developments, expert consensus).
- Use natural search phrasing, not questions.
- No quotes or operators unless essential.
"""

QUERY_HUMAN_PROMPT = """\
Research question: {question}

Task: {task}

{context}"""

REWRITE_SYSTEM_PROMPT = """\
You are a search-query rewriter for a research assistant.
Previous searches returned too few relevant results.
Generate NEW queries with different terminology, framing, or scope.

Rules:
- 2 to 3 queries.
- Avoid repeating wording that already failed.
- Broader or alternative terms are better than exact retries.
"""

REWRITE_HUMAN_PROMPT = """\
Research question: {question}

Task: {task}

Queries already tried:
{tried}

Top results so far:
{seen}

Generate replacement queries."""


class SearchQueries(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=5)

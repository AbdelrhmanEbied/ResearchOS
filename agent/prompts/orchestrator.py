from pydantic import BaseModel, Field

PLAN_SYSTEM_PROMPT = """\
You are a research orchestrator. Decompose a research question into concrete
tasks for specialized sub-graphs.

Available graph types:
- "web": needs fresh/external information → web search
- "document": needs information from the user's uploaded documents
- "code": needs computation, data analysis, or calculations

Rules:
- 1 to 6 tasks.
- Each task gets a self-contained query (the sub-graph will NOT see the full context).
- Use "document" tasks only if the question clearly needs the user's files.
- Use "code" tasks only if computation is needed.
- Set depends_on to task ids when one task's query needs another task's results.
- Task ids: t1, t2, ...
"""

PLAN_HUMAN_PROMPT = """\
Research question: {question}

Conversation so far:
{history}

Previous findings so far (if any):
{context}

{gaps}"""

REPLAN_SYSTEM_PROMPT = """\
You are a research orchestrator in a REPLANNING phase. Previous research was
insufficient. Create NEW tasks that target the gaps. Do not repeat failed tasks
unless you change the query meaningfully.

Include the original question's needs plus the gaps below."""

REPLAN_HUMAN_PROMPT = """\
Research question: {question}

Gaps identified by verification:
{gaps}

Evidence already collected: {evidence_count} items

Existing task history:
{history}"""


class PlannedTask(BaseModel):
    id: str
    graph: str = Field(pattern="^(web|document|code)$")
    query: str
    depends_on: list[str] = Field(default_factory=list)


class ResearchPlanDraft(BaseModel):
    objective: str
    tasks: list[PlannedTask] = Field(min_length=1, max_length=6)

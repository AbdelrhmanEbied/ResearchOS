from typing import Literal

from pydantic import BaseModel, Field

ROUTE_SYSTEM_PROMPT = """\
You decide whether a research agent needs its tools for a user message.

Tools available to the agent:
- "web": live web search and fetching pages (fresh facts, news, sources)
- "document": the user's uploaded documents
- "code": running code for computation, data work, plots

Return decision="quick" when the message can be answered directly with no tool
call: greetings, small talk, thanks, follow-ups that the conversation already
answers, and general knowledge you can state confidently (definitions,
explanations, maths, writing code, opinions, summarising the chat).

Return decision="research" when at least one tool is genuinely needed, and
list every tool the run may use:
- "search/find/latest/news/according to..." → web
- "my document/report/file/pdf/attached..." → document
- "calculate/run this/analyse the data/plot..." → code

Rules:
- When a claim would need freshness or a citation, prefer research.
- A question that is only answerable from the user's files → document.
- Keep tools minimal: list a tool only if it is actually useful.
- The conversation so far is context; short follow-ups are usually quick.
"""

ROUTE_HUMAN_PROMPT = """\
User message: {question}

Conversation so far:
{history}"""


class RouteDecision(BaseModel):
    decision: Literal["quick", "research"]
    tools: list[Literal["web", "document", "code"]] = Field(default_factory=list)
    reason: str = Field(default="", max_length=600)

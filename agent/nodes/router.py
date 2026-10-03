from agent.llms import build_structured_llm
from agent.prompts.router import ROUTE_HUMAN_PROMPT, ROUTE_SYSTEM_PROMPT, RouteDecision
from agent.state.schemas import AgentState

ALL_TOOLS = ("web", "document", "code")

SOURCE_TOOLS = {"web": ("web",), "documents": ("document",)}
MODE_TOOLS = {"summarize": ("document",), "compare": ("document",)}


def _chat_history(state: AgentState, limit: int = 8) -> str:
    history = state.get("history") or []
    lines = [f"{m.get('role')}: {m.get('content')}" for m in history[-limit:]]
    return "\n".join(lines) or "(none)"


def _override(state: AgentState) -> dict | None:
    source = state.get("source_override")
    mode = state.get("mode_override")

    if mode == "chat" or source == "chat":
        return {"decision": "quick", "tools": [], "reason": "chat-only override"}

    tools: list[str] = []
    if source in SOURCE_TOOLS:
        tools.extend(SOURCE_TOOLS[source])
    elif mode in MODE_TOOLS:
        tools.extend(MODE_TOOLS[mode])

    if tools:
        return {
            "decision": "research",
            "tools": tools,
            "reason": f"{source or mode} override",
        }
    return None


def _normalize(decision: RouteDecision) -> dict:
    tools = list(decision.tools)
    if decision.decision == "quick":
        return {"decision": "quick", "tools": [], "reason": decision.reason}
    if not tools:
        return {"decision": "research", "tools": list(ALL_TOOLS), "reason": decision.reason}
    return {"decision": "research", "tools": tools, "reason": decision.reason}


async def route_intent(state: AgentState) -> dict:
    """First node: decide quick answer vs research, and which tools may run."""
    decision = _override(state)
    if decision is None:
        llm = build_structured_llm(RouteDecision)
        response = await llm.ainvoke(
            [
                {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": ROUTE_HUMAN_PROMPT.format(
                        question=state["query"],
                        history=_chat_history(state),
                    ),
                },
            ]
        )
        decision = _normalize(response)

    return {
        "intent": decision["decision"],
        "allowed_tools": decision["tools"],
        "routing_reason": decision["reason"],
    }

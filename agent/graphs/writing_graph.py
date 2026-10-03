from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.orchestrator import is_thinking
from agent.nodes.writing import draft, make_outline
from agent.state.schemas import AgentState


def route_writing(state: AgentState) -> str:
    """Instant skips the outline call: it drafts straight from claims and evidence."""
    return "make_outline" if is_thinking(state) else "draft"


def build_writing_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("make_outline", make_outline)
    graph.add_node("draft", draft)

    graph.add_conditional_edges(
        START,
        route_writing,
        {"make_outline": "make_outline", "draft": "draft"},
    )
    graph.add_edge("make_outline", "draft")
    graph.add_edge("draft", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["writing"])


writing_graph = build_writing_graph()

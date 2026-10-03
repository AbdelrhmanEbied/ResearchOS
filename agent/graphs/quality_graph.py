from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.quality import check
from agent.state.schemas import AgentState


def build_quality_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("check", check)
    graph.add_edge(START, "check")
    graph.add_edge("check", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["quality"])


quality_graph = build_quality_graph()

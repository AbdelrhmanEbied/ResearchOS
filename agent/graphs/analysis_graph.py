from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.analysis import cluster, extract_claims
from agent.state.schemas import AgentState


def build_analysis_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("cluster", cluster)
    graph.add_node("extract_claims", extract_claims)

    graph.add_edge(START, "cluster")
    graph.add_edge("cluster", "extract_claims")
    graph.add_edge("extract_claims", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["analysis"])


analysis_graph = build_analysis_graph()

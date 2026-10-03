from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.document import accumulate, retrieve
from agent.state.schemas import AgentState


def build_document_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", retrieve)
    graph.add_node("accumulate", accumulate)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "accumulate")
    graph.add_edge("accumulate", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["task_document"])


document_graph = build_document_graph()

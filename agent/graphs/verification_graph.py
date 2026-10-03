from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.verification import verify_claims
from agent.state.schemas import AgentState


def build_verification_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("verify_claims", verify_claims)

    graph.add_edge(START, "verify_claims")
    graph.add_edge("verify_claims", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["verification"])


verification_graph = build_verification_graph()

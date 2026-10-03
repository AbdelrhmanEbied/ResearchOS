from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.code import accumulate, execute, interpret, plan_code, route_execution
from agent.state.schemas import AgentState


def build_code_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("plan_code", plan_code)
    graph.add_node("execute", execute)
    graph.add_node("interpret", interpret)
    graph.add_node("accumulate", accumulate)

    graph.add_edge(START, "plan_code")
    graph.add_edge("plan_code", "execute")
    graph.add_conditional_edges(
        "execute",
        route_execution,
        {"interpret": "interpret", "plan_code": "plan_code", "accumulate": "accumulate"},
    )
    graph.add_edge("interpret", "accumulate")
    graph.add_edge("accumulate", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["task_code"])


code_graph = build_code_graph()

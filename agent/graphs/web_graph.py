from langgraph.graph import END, START, StateGraph

from agent.graphs.labels import SUBGRAPH_LABELS
from agent.nodes.web import (
    accumulate_evidence,
    deduplicate_results,
    execute_search,
    extract_and_build_evidence,
    fetch_pages,
    generate_queries,
    rank_and_filter,
    rewrite_queries,
    route_sufficiency,
)
from agent.state.schemas import AgentState


def build_web_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("generate_queries", generate_queries)
    graph.add_node("execute_search", execute_search)
    graph.add_node("deduplicate_results", deduplicate_results)
    graph.add_node("rank_and_filter", rank_and_filter)
    graph.add_node("rewrite_queries", rewrite_queries)
    graph.add_node("fetch_pages", fetch_pages)
    graph.add_node("extract_and_build_evidence", extract_and_build_evidence)
    graph.add_node("accumulate_evidence", accumulate_evidence)

    graph.add_edge(START, "generate_queries")
    graph.add_edge("generate_queries", "execute_search")
    graph.add_edge("execute_search", "deduplicate_results")
    graph.add_edge("deduplicate_results", "rank_and_filter")

    graph.add_conditional_edges(
        "rank_and_filter",
        route_sufficiency,
        {"fetch": "fetch_pages", "rewrite": "rewrite_queries"},
    )
    graph.add_edge("rewrite_queries", "execute_search")

    graph.add_edge("fetch_pages", "extract_and_build_evidence")
    graph.add_edge("extract_and_build_evidence", "accumulate_evidence")
    graph.add_edge("accumulate_evidence", END)

    return graph.compile(checkpointer=checkpointer, name=SUBGRAPH_LABELS["task_web"])


web_graph = build_web_graph()

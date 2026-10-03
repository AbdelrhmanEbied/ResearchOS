from langgraph.graph import END, START, StateGraph

from agent.graphs.analysis_graph import analysis_graph
from agent.graphs.code_graph import code_graph
from agent.graphs.document_graph import document_graph
from agent.graphs.labels import ROOT_GRAPH_NAME
from agent.graphs.quality_graph import quality_graph
from agent.graphs.verification_graph import verification_graph
from agent.graphs.web_graph import web_graph
from agent.graphs.writing_graph import writing_graph
from agent.nodes.orchestrator import (
    finalize,
    mark_task_done,
    plan,
    prepare_task,
    route_after_intent,
    route_after_research,
    route_after_writing,
    route_task,
)
from agent.nodes.quality import route_quality
from agent.nodes.router import route_intent
from agent.nodes.writing import draft
from agent.state.schemas import AgentState


def build_orchestrator_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("route_intent", route_intent)
    graph.add_node("plan", plan)
    graph.add_node("prepare_task", prepare_task)

    graph.add_node("task_web", web_graph)
    graph.add_node("task_document", document_graph)
    graph.add_node("task_code", code_graph)
    graph.add_node("mark_task_done", mark_task_done)

    graph.add_node("analysis", analysis_graph)
    graph.add_node("verification", verification_graph)

    graph.add_node("writing", writing_graph)
    graph.add_node("quality", quality_graph)

    graph.add_node("draft", draft)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        route_after_intent,
        {"draft": "draft", "plan": "plan"},
    )
    graph.add_edge("draft", "finalize")

    graph.add_edge("plan", "prepare_task")

    graph.add_conditional_edges(
        "prepare_task",
        route_task,
        {
            "task_web": "task_web",
            "task_document": "task_document",
            "task_code": "task_code",
            "analysis": "analysis",
            "writing": "writing",
        },
    )

    graph.add_edge("task_web", "mark_task_done")
    graph.add_edge("task_document", "mark_task_done")
    graph.add_edge("task_code", "mark_task_done")
    graph.add_edge("mark_task_done", "prepare_task")

    graph.add_edge("analysis", "verification")

    graph.add_conditional_edges(
        "verification",
        route_after_research,
        {"replan": "plan", "writing": "writing"},
    )

    graph.add_conditional_edges(
        "writing",
        route_after_writing,
        {"quality": "quality", "finalize": "finalize"},
    )

    graph.add_conditional_edges(
        "quality",
        route_quality,
        {"done": "finalize", "revise": "writing"},
    )

    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer, name=ROOT_GRAPH_NAME)


orchestrator_graph = build_orchestrator_graph()

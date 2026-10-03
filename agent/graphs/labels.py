ROOT_GRAPH_NAME = "Research Agent"

SUBGRAPH_LABELS: dict[str, str] = {
    "task_web": "Web Search",
    "task_document": "Document Analysis",
    "task_code": "Code Execution",
    "analysis": "Analysis",
    "verification": "Verification",
    "writing": "Writing",
    "quality": "Quality Review",
}

SUBGRAPH_NODE_NAMES = frozenset(SUBGRAPH_LABELS)
SUBGRAPH_GRAPH_NAMES = frozenset(SUBGRAPH_LABELS.values())

NODE_LABELS: dict[str, str] = {
    "route_intent": "Deciding what's needed",
    "plan": "Planning",
    "prepare_task": "Selecting next task",
    "mark_task_done": "Task complete",
    "finalize": "Finalizing",
    "generate_queries": "Generating search queries",
    "execute_search": "Searching the web",
    "deduplicate_results": "Deduplicating results",
    "rank_and_filter": "Ranking results",
    "rewrite_queries": "Rewriting queries",
    "fetch_pages": "Fetching pages",
    "extract_and_build_evidence": "Extracting evidence",
    "accumulate_evidence": "Accumulating evidence",
    "retrieve": "Retrieving documents",
    "accumulate": "Accumulating evidence",
    "plan_code": "Planning code",
    "execute": "Running code",
    "interpret": "Interpreting results",
    "cluster": "Clustering evidence",
    "extract_claims": "Extracting claims",
    "verify_claims": "Verifying claims",
    "make_outline": "Building outline",
    "draft": "Drafting response",
    "check": "Quality check",
}


def node_label(node: str) -> str:
    return NODE_LABELS.get(node, node.replace("_", " ").strip().capitalize())


def subgraph_label(node: str) -> str:
    return SUBGRAPH_LABELS.get(node, node_label(node))

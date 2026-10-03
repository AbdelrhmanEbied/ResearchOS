import asyncio

from agent.llms import build_structured_llm
from agent.prompts.web import (
    QUERY_HUMAN_PROMPT,
    QUERY_SYSTEM_PROMPT,
    REWRITE_HUMAN_PROMPT,
    REWRITE_SYSTEM_PROMPT,
    SearchQueries,
)
from agent.state.schemas import AgentState, Evidence, active_task
from agent.tools.web_tools import (
    build_evidence,
    deduplicate,
    extract_passages,
    fetch_url,
    web_search,
)
from settings import get_settings_store

MIN_RESULTS = 3
MAX_SEARCH_RETRIES = 2
MAX_QUERIES = 5
MAX_PAGES = 5
RESULTS_TOP_K = 8


def _web_limits(cfg: dict) -> tuple[str, int, int]:
    """Settings are the source of truth; a request-level config wins."""
    stored = get_settings_store().get_web()
    depth = cfg.get("search_depth") or stored["search_depth"]
    per_query = cfg.get("results_per_query") or stored["results_per_query"]
    pages = cfg.get("pages_fetched") or stored["pages_fetched"]
    return depth, int(per_query), min(int(pages), MAX_PAGES * 2)


def _focus(state: AgentState) -> tuple[str, str]:
    task = active_task(state)
    if task:
        return state["query"], task.query
    return state["query"], (state["plan"].objective if state.get("plan") else state["query"])


async def generate_queries(state: AgentState) -> dict:
    question, task = _focus(state)
    llm = build_structured_llm(SearchQueries)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": QUERY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": QUERY_HUMAN_PROMPT.format(
                    question=question,
                    task=task,
                    context="",
                ),
            },
        ]
    )
    return {
        "search_queries": response.queries[:MAX_QUERIES],
        "search_retry": 0,
        "web_results": [],
    }


async def execute_search(state: AgentState) -> dict:
    queries = state.get("search_queries", [])
    cfg = state.get("retrieval_config") or {}
    depth, per_query, _pages = _web_limits(cfg)
    results = await asyncio.gather(
        *(
            web_search.ainvoke({"query": q, "max_results": per_query, "search_depth": depth})
            for q in queries
        )
    )
    merged = [r for batch in results for r in batch]
    existing = state.get("web_results", [])
    return {"web_results": existing + merged}


async def deduplicate_results(state: AgentState) -> dict:
    return {"unique_results": deduplicate(state.get("web_results", []))}


async def rank_and_filter(state: AgentState) -> dict:
    query_terms = {t for t in state["query"].lower().split() if len(t) > 2}
    ranked = []
    for r in state.get("unique_results", []):
        text = f"{r.get('title', '')} {r.get('content', '')}".lower()
        overlap = sum(1 for t in query_terms if t in text)
        combined = r.get("score", 0.0) + overlap * 0.1
        ranked.append((combined, r))
    ranked.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in ranked[:RESULTS_TOP_K]]
    top = [r for r in top if r.get("score", 0.0) >= 0.3 or top.index(r) < MIN_RESULTS]
    return {"ranked_results": top}


async def rewrite_queries(state: AgentState) -> dict:
    question, task = _focus(state)
    llm = build_structured_llm(SearchQueries)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": REWRITE_HUMAN_PROMPT.format(
                    question=question,
                    task=task,
                    tried="\n".join(f"- {q}" for q in state.get("search_queries", [])),
                    seen="\n".join(
                        f"- {r.get('title')}: {r.get('url')}"
                        for r in state.get("ranked_results", [])[:5]
                    )
                    or "(none)",
                ),
            },
        ]
    )
    return {
        "search_queries": response.queries,
        "search_retry": state.get("search_retry", 0) + 1,
    }


async def fetch_pages(state: AgentState) -> dict:
    cfg = state.get("retrieval_config") or {}
    _depth, _per_query, pages = _web_limits(cfg)
    results = state.get("ranked_results", [])[:pages]

    async def one(r: dict) -> dict | None:
        try:
            text = await fetch_url.ainvoke({"url": r["url"]})
        except Exception:
            return None
        return {"url": r.get("url"), "title": r.get("title"), "text": text}

    pages = await asyncio.gather(*(one(r) for r in results))
    return {"web_pages": [p for p in pages if p]}


async def extract_and_build_evidence(state: AgentState) -> dict:
    question, task = _focus(state)
    all_evidence: list[Evidence] = []
    for page in state.get("web_pages", []):
        passages = extract_passages(page["text"], task or question)
        all_evidence += build_evidence(
            passages,
            source_url=page["url"],
            source_title=page["title"],
        )
    return {"web_evidence": all_evidence}


async def accumulate_evidence(state: AgentState) -> dict:
    return {
        "evidence": state.get("web_evidence", []),
        "status": "researching",
        "web_pages": [],
        "web_evidence": [],
    }


def route_sufficiency(state: AgentState) -> str:
    if len(state.get("ranked_results", [])) >= MIN_RESULTS:
        return "fetch"
    if state.get("search_retry", 0) < MAX_SEARCH_RETRIES:
        return "rewrite"
    return "fetch"

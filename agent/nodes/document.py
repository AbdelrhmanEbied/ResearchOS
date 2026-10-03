from agent.state.schemas import AgentState, active_task
from agent.tools.document_tools import (
    build_document_evidence,
    documents_available,
    retrieve_documents,
)
from settings import get_settings_store

DOC_LIMIT = 8


def _focus_query(state: AgentState) -> str:
    task = active_task(state)
    return task.query if task else state["query"]


async def retrieve(state: AgentState) -> dict:
    if not documents_available():
        return {
            "gaps": state.get("gaps", []) + ["No documents are available for retrieval."],
            "doc_retrieved": [],
            "doc_evidence": [],
        }
    cfg = state.get("retrieval_config") or {}
    limit = cfg.get("limit") or get_settings_store().get_retrieval()["limit"] or DOC_LIMIT
    search_type = cfg.get("search_type")
    docs = await retrieve_documents.ainvoke(
        {"query": _focus_query(state), "limit": limit, "search_type": search_type}
    )
    return {"doc_retrieved": docs, "doc_evidence": build_document_evidence(docs)}


async def accumulate(state: AgentState) -> dict:
    return {
        "evidence": state.get("doc_evidence", []),
        "status": "researching",
        "doc_retrieved": [],
        "doc_evidence": [],
    }

from langchain_core.tools import tool

from agent.state.schemas import Evidence
from agent.tools.registry import registry
from settings import get_settings_store


def _default_search_type() -> str:
    try:
        stored = get_settings_store().get_retrieval().get("search_type")
    except Exception:
        stored = None
    return stored or "hybrid"


def _chunk_title(metadata: dict) -> str | None:
    name = metadata.get("name")
    if name:
        return name
    title = metadata.get("title")
    if title and title not in {"(anonymous)", "(unspecified)"}:
        return title
    return None


def _retrieve_documents(
    query: str, *, limit: int = 8, search_type: str | None = None
) -> list[dict]:
    rag = registry.get("rag")
    docs = rag.retrieve(
        query=query, limit=limit, search_type=search_type or _default_search_type()
    )
    out = []
    for d in docs:
        out.append(
            {
                "text": d.text,
                "score": d.score,
                "document_id": d.metadata.get("document_id"),
                "title": _chunk_title(d.metadata),
                "chunk_id": d.metadata.get("chunk_id"),
            }
        )
    return out


@tool
def retrieve_documents(query: str, limit: int = 8, search_type: str | None = None) -> list[dict]:
    """Retrieve the most relevant passages from the user's uploaded documents."""
    return _retrieve_documents(query, limit=limit, search_type=search_type)


def build_document_evidence(docs: list[dict]) -> list[Evidence]:
    from uuid import uuid4

    return [
        Evidence(
            id=uuid4().hex,
            content=d["text"],
            source_type="document",
            document_id=d.get("document_id"),
            source_title=d.get("title"),
            score=d.get("score", 0.0),
            metadata={"chunk_id": d.get("chunk_id")},
        )
        for d in docs
    ]


def documents_available() -> bool:
    try:
        rag = registry.get("rag")
        return rag is not None
    except KeyError:
        return False

import os

from dotenv import load_dotenv
from pydantic import BaseModel
from tavily import TavilyClient

from rag.rag_schemas import RetrievedDocuments
from rag.reranker import Reranker

load_dotenv()

SEARCH_DEPTHS = ("basic", "advanced")
DEFAULT_SEARCH_DEPTH = "basic"


class SearchResult(BaseModel):
    title: str | None = None
    url: str | None = None
    content: str = ""
    score: float = 0.0
    source: str = "web"


class WebSearchService:
    def __init__(self, tavily_client: TavilyClient, reranker: Reranker | None = None):
        self.client = tavily_client
        self.reranker = reranker

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = DEFAULT_SEARCH_DEPTH,
    ) -> list[SearchResult]:
        if search_depth not in SEARCH_DEPTHS:
            search_depth = DEFAULT_SEARCH_DEPTH

        response = self.client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=False,
            include_raw_content=search_depth == "advanced",
            include_images=False,
        )

        results = []
        for item in response.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title"),
                    url=item.get("url"),
                    content=item.get("content") or item.get("raw_content") or "",
                    score=item.get("score", 0.0),
                )
            )

        if self.reranker is not None and results:
            results = self._rerank(query, results)

        return results

    def _rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        docs = [
            RetrievedDocuments(
                text=r.content,
                score=r.score,
                metadata={"title": r.title, "url": r.url, "source": "web"},
            )
            for r in results
        ]
        reranked = self.reranker.rerank(documents=docs, query=query)

        url_map = {r.url: r for r in results}
        out = []
        for doc in reranked:
            url = doc.metadata.get("url")
            if url and url in url_map:
                original = url_map[url]
                out.append(original.model_copy(update={"score": doc.score}))
            else:
                out.append(SearchResult(content=doc.text, score=doc.score))
        return out


def create_web_search_service(reranker: Reranker | None = None) -> WebSearchService:
    api_key = os.getenv("TAVILY_API_KEY")
    client = TavilyClient(api_key=api_key)
    return WebSearchService(tavily_client=client, reranker=reranker)

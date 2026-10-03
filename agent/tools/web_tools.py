import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from agent.state.schemas import Evidence
from agent.tools.registry import registry
from agent.web_service import create_web_search_service


def _web_service():
    if registry.has("web_search"):
        return registry.get("web_search")
    return create_web_search_service()


def search(query: str, *, max_results: int = 5, depth: str = "basic") -> list[dict]:
    results = _web_service().search(query, max_results=max_results, search_depth=depth)
    return [
        {"title": r.title, "url": r.url, "content": r.content, "score": r.score} for r in results
    ]


def fetch_page(url: str, *, timeout: int = 15) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (research-assistant)"}
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    return text[:20000]


def extract_passages(
    content: str,
    question: str,
    *,
    max_passages: int = 5,
) -> list[str]:
    paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 50]
    if not paragraphs:
        return []

    query_terms = set(question.lower().split())
    scored = []
    for p in paragraphs:
        p_lower = p.lower()
        overlap = sum(1 for term in query_terms if term in p_lower)
        if overlap > 0:
            scored.append((overlap, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:max_passages]]


def build_evidence(
    passages: list[str],
    *,
    source_url: str | None = None,
    source_title: str | None = None,
) -> list[Evidence]:
    from uuid import uuid4

    return [
        Evidence(
            id=uuid4().hex,
            content=passage,
            source_type="web",
            source_url=source_url,
            source_title=source_title,
        )
        for passage in passages
    ]


def deduplicate(results: list[dict]) -> list[dict]:
    seen_urls = set()
    seen_titles = set()
    unique = []
    for r in results:
        url = r.get("url", "")
        title = (r.get("title") or "").lower().strip()
        if url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        unique.append(r)
    return unique


def results_are_sufficient(results: list[dict], *, min_results: int = 3) -> bool:
    return len(results) >= min_results


@tool
def web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> list[dict]:
    """Search the web for current information. Returns ranked results with titles, URLs and content."""
    return search(query, max_results=max_results, depth=search_depth or "basic")


@tool
def fetch_url(url: str) -> str:
    """Fetch a web page URL and return its extracted text content."""
    return fetch_page(url)

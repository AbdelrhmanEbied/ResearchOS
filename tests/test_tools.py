import pytest

from agent.sandbox.executor import ExecutionResult
from agent.tools.code_tools import build_code_evidence, run_code
from agent.tools.document_tools import (
    _retrieve_documents,
    build_document_evidence,
    documents_available,
    retrieve_documents,
)
from agent.tools.registry import registry
from agent.tools.web_tools import build_evidence, fetch_url, web_search
from settings import reset_settings_store


@pytest.fixture(autouse=True)
def _isolated_registry():
    registry.clear()
    reset_settings_store()
    yield
    registry.clear()
    reset_settings_store()


class FakeRag:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.calls = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        return self.docs


class FakeWebSearch:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.results


def _rag_doc(text="passage", **metadata):
    return type(
        "Doc",
        (),
        {"text": text, "score": 0.9, "metadata": metadata},
    )()


def _web_result(title="Title", url="https://example.com", content="body", score=0.5):
    return type(
        "Result",
        (),
        {"title": title, "url": url, "content": content, "score": score},
    )()


@pytest.mark.asyncio
async def test_retrieve_documents_maps_registry_results():
    registry.register(
        "rag", FakeRag([_rag_doc("alpha", document_id="1", title="a.pdf", chunk_id="c1")])
    )

    docs = await retrieve_documents.ainvoke({"query": "q", "limit": 4})

    assert docs == [
        {
            "text": "alpha",
            "score": 0.9,
            "document_id": "1",
            "title": "a.pdf",
            "chunk_id": "c1",
        }
    ]


@pytest.mark.asyncio
async def test_retrieve_documents_passes_limit_and_search_type():
    rag = FakeRag([])
    registry.register("rag", rag)

    await retrieve_documents.ainvoke({"query": "q", "limit": 7, "search_type": "sparse"})

    assert rag.calls == [{"query": "q", "limit": 7, "search_type": "sparse"}]


def test_retrieve_documents_defaults_search_type_from_settings():
    registry.register("rag", FakeRag([]))
    _retrieve_documents("q")
    assert registry.get("rag").calls[0]["search_type"] == "hybrid"


def test_documents_available_without_registration():
    assert documents_available() is False
    with pytest.raises(KeyError):
        _retrieve_documents("q")


def test_document_evidence_builder():
    docs = [{"text": "alpha", "score": 0.4, "document_id": "1", "title": "a.pdf", "chunk_id": "c1"}]
    evidence = build_document_evidence(docs)

    assert len(evidence) == 1
    assert evidence[0].source_type == "document"
    assert evidence[0].document_id == "1"
    assert evidence[0].source_title == "a.pdf"
    assert evidence[0].metadata == {"chunk_id": "c1"}


@pytest.mark.asyncio
async def test_web_search_passes_depth_and_max_results():
    service = FakeWebSearch([_web_result()])
    registry.register("web_search", service)

    results = await web_search.ainvoke(
        {"query": "news", "max_results": 3, "search_depth": "advanced"}
    )

    assert service.calls == [{"query": "news", "max_results": 3, "search_depth": "advanced"}]
    assert results == [
        {"title": "Title", "url": "https://example.com", "content": "body", "score": 0.5}
    ]


def test_web_search_tool_schema_exposes_expected_arguments():
    assert set(web_search.args) == {"query", "max_results", "search_depth"}
    assert set(fetch_url.args) == {"url"}
    assert set(retrieve_documents.args) == {"query", "limit", "search_type"}
    assert set(run_code.args) == {"code", "timeout"}


def test_fetch_url_strips_boilerplate(monkeypatch):
    html = """
    <html><head><script>alert(1)</script></head>
    <body><nav>menu</nav><article><p>Useful paragraph content.</p></article></body></html>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResponse()

    import agent.tools.web_tools as web_tools

    monkeypatch.setattr(web_tools.httpx, "Client", FakeClient)

    text = fetch_url.invoke({"url": "https://example.com/page"})

    assert "Useful paragraph content." in text
    assert "alert(1)" not in text
    assert "menu" not in text


def test_web_evidence_builder():
    evidence = build_evidence(
        ["passage one", "passage two"],
        source_url="https://example.com",
        source_title="Example",
    )

    assert [e.content for e in evidence] == ["passage one", "passage two"]
    assert {e.source_url for e in evidence} == {"https://example.com"}
    assert {e.source_type for e in evidence} == {"web"}


@pytest.mark.asyncio
async def test_run_code_returns_execution_dict(monkeypatch):
    async def fake_execute(code, timeout=10):
        return ExecutionResult(success=True, stdout="4\n", exit_code=0)

    monkeypatch.setattr("agent.tools.code_tools.execute_code", fake_execute)

    out = await run_code.ainvoke({"code": "print(2 + 2)"})

    assert out == {
        "success": True,
        "stdout": "4\n",
        "stderr": "",
        "exit_code": 0,
        "error": None,
        "timed_out": False,
    }


def test_code_evidence_builder():
    evidence = build_code_evidence(
        ExecutionResult(success=True, stdout="42", exit_code=0), "print(42)"
    )

    assert len(evidence) == 1
    assert evidence[0].source_type == "code"
    assert evidence[0].content == "42"
    assert evidence[0].metadata["exit_code"] == 0


@pytest.mark.asyncio
async def test_run_code_executes_real_python():
    out = await run_code.ainvoke({"code": "print(2 + 2)"})
    assert out["success"] is True
    assert out["stdout"].strip() == "4"


@pytest.mark.asyncio
async def test_run_code_surfaces_stderr():
    out = await run_code.ainvoke({"code": "1 / 0"})
    assert out["success"] is False
    assert "ZeroDivisionError" in out["stderr"]


@pytest.mark.asyncio
async def test_run_code_times_out():
    out = await run_code.ainvoke({"code": "import time; time.sleep(5)", "timeout": 1})
    assert out["timed_out"] is True or "timed out" in (out["stderr"] + (out["error"] or ""))


@pytest.mark.asyncio
async def test_run_code_rejects_restricted_imports():
    out = await run_code.ainvoke({"code": "import os; print(os.getcwd())"})
    assert out["success"] is False
    assert "not allowed" in (out["stderr"] + (out["error"] or ""))

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import ClientDisconnect

import app.backend.services.chat_service as cs
from agent.llms import get_request_api_key
from app.backend.database.base import Base
from app.backend.database.models import Conversation
from app.backend.database.repositories import MessageRepository
from app.backend.schemas.chat import AgentMode, ChatRequest, LLMConfig, RegenerateRequest
from app.backend.services.chat_service import (
    DETAILS_MARKER,
    ERROR_MARKER,
    EVENT_MARKER,
    GRAPH_RECURSION_LIMIT,
    SOURCES_MARKER,
    THINKING_MARKER,
    ChatService,
)


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda conn: conn.execute(Conversation.__table__.insert(), {"title": "existing"})
        )
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


def _chain_start(run_id, name, node, parents=()):
    event = {
        "event": "on_chain_start",
        "name": name,
        "run_id": run_id,
        "parent_ids": list(parents),
        "data": {},
    }
    event["metadata"] = {"langgraph_node": node} if node else {}
    return event


def _chain_end(run_id, name, node, parents=(), output=None):
    event = {
        "event": "on_chain_end",
        "name": name,
        "run_id": run_id,
        "parent_ids": list(parents),
        "data": {"output": output if output is not None else {}},
    }
    event["metadata"] = {"langgraph_node": node} if node else {}
    return event


def _tool(kind, run_id, name, node, parents, **data):
    return {
        "event": kind,
        "name": name,
        "run_id": run_id,
        "parent_ids": list(parents),
        "metadata": {"langgraph_node": node},
        "data": data,
    }


def _model(kind, node, run_id, **data):
    return {
        "event": kind,
        "name": "chat_model",
        "run_id": run_id,
        "parent_ids": [],
        "metadata": {"langgraph_node": node},
        "data": data,
    }


def parse_stream(chunks) -> tuple[list[dict], str]:
    """Split the raw stream into protocol events and plain answer text."""
    raw = "".join(chunks)
    events: list[dict] = []
    text_parts: list[str] = []
    cursor = 0
    while True:
        idx = raw.find(EVENT_MARKER, cursor)
        if idx < 0:
            text_parts.append(raw[cursor:])
            break
        text_parts.append(raw[cursor:idx])
        payload_start = idx + len(EVENT_MARKER)
        if payload_start < len(raw) and raw[payload_start] == "\n":
            payload_start += 1
        payload_end = raw.index("\n", payload_start)
        events.append(json.loads(raw[payload_start:payload_end]))
        cursor = payload_end + 1
    return events, "".join(text_parts)


def answer_text(chunks) -> str:
    """Plain answer text: event frames removed and terminal markers dropped."""
    _, text = parse_stream(chunks)
    for marker in (SOURCES_MARKER, DETAILS_MARKER, ERROR_MARKER, THINKING_MARKER):
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
    return text.rstrip()


class FakeGraph:
    """Emits a realistic `astream_events` (v2) sequence for the new graph."""

    def __init__(self, sources, answer="answer here"):
        self.sources = sources
        self.answer = answer
        self.received_state = None
        self.received_config = None

    async def astream_events(self, state, config=None, version="v2"):
        self.received_state = state
        self.received_config = config
        yield _chain_start("root", "Research Agent", None)
        yield _chain_start("route1", "route_intent", "route_intent", parents=["root"])
        yield _chain_end(
            "route1",
            "route_intent",
            "route_intent",
            parents=["root"],
            output={
                "intent": "research",
                "allowed_tools": ["web"],
                "routing_reason": "needs facts",
            },
        )
        yield _chain_start("sg1", "Web Search", "task_web", parents=["root"])
        yield _tool(
            "on_tool_start",
            "tool1",
            "web_search",
            "execute_search",
            ["root", "sg1"],
            input={"query": "q"},
        )
        yield _tool(
            "on_tool_end",
            "tool1",
            "web_search",
            "execute_search",
            ["root", "sg1"],
            output=[{"title": "Example", "url": "https://example.com", "content": "body"}],
        )
        yield _chain_end("sg1", "Web Search", "task_web", parents=["root"])
        yield _chain_start("plan1", "plan", "plan", parents=["root"])
        yield _chain_end("plan1", "plan", "plan", parents=["root"], output={"status": "planning"})
        yield _model(
            "on_chat_model_stream",
            "draft",
            "draft1",
            chunk=AIMessageChunk(content=[{"type": "text", "text": "answer "}]),
        )
        yield _model(
            "on_chat_model_stream",
            "draft",
            "draft1",
            chunk=AIMessageChunk(content=[{"type": "text", "text": "here"}]),
        )
        yield _model(
            "on_chat_model_end",
            "draft",
            "draft1",
            output=AIMessage(
                content=self.answer,
                usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            ),
        )
        yield _chain_end(
            "final1",
            "finalize",
            "finalize",
            parents=["root"],
            output={"sources": self.sources, "response": self.answer, "status": "done"},
        )
        yield _chain_end(
            "root",
            "Research Agent",
            None,
            output={"response": self.answer, "sources": self.sources, "status": "done"},
        )


class RaisingGraph(FakeGraph):
    def __init__(self, error):
        super().__init__([])
        self.error = error

    async def astream_events(self, state, config=None, version="v2"):
        yield _model(
            "on_chat_model_stream",
            "draft",
            "draft1",
            chunk=AIMessageChunk(content=[{"type": "text", "text": "partial"}]),
        )
        raise self.error


class FailingGraph(FakeGraph):
    async def astream_events(self, state, config=None, version="v2"):
        if False:  # pragma: no cover - makes this an async generator
            yield
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_stream_yields_answer_and_sources_marker(db, monkeypatch):
    sources = [
        {"source": "rag", "label": "a.pdf", "url": None, "document_id": "1"},
        {"source": "web", "label": "Some site", "url": "https://example.com", "document_id": None},
    ]
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph(sources)
    service = ChatService(graph=graph, db=db, rag=None)

    chunks = []
    async for chunk in service.stream(ChatRequest(query="q", conversation_id=1)):
        chunks.append(chunk)

    events, text = parse_stream(chunks)
    kinds = [e["type"] for e in events]

    assert kinds[0] == "agent_started"
    assert kinds[-1] == "agent_finished"
    assert "subgraph_started" in kinds and "subgraph_finished" in kinds
    assert "tool_started" in kinds and "tool_finished" in kinds
    assert "agent_status" in kinds

    tool_start = next(e for e in events if e["type"] == "tool_started")
    assert tool_start["name"] == "web_search"
    assert tool_start["input"] == {"query": "q"}
    assert tool_start["scope"] is not None

    tool_done = next(e for e in events if e["type"] == "tool_finished")
    assert tool_done["ok"] is True
    assert tool_done["summary"] == "1 results"
    assert tool_done["duration_ms"] is not None

    subgraph = next(e for e in events if e["type"] == "subgraph_started")
    assert subgraph["label"] == "Web Search"
    assert subgraph["scope"] is None

    statuses = [e for e in events if e["type"] == "agent_status"]
    assert {s["label"] for s in statuses} >= {"Planning", "Finalizing"}

    assert answer_text(chunks) == "answer here"
    assert EVENT_MARKER not in text.split(SOURCES_MARKER)[0]

    marker_idx = text.index(SOURCES_MARKER)
    details_idx = text.index(DETAILS_MARKER)
    payload = json.loads(text[marker_idx + len(SOURCES_MARKER) : details_idx].strip())
    assert payload == sources

    details = json.loads(text[details_idx + len(DETAILS_MARKER) :].strip())
    assert details["model"] == "fake"
    assert details["tokens"] == {
        "input_tokens": 7,
        "output_tokens": 3,
        "total_tokens": 10,
    }


@pytest.mark.asyncio
async def test_stream_passes_full_history_to_graph(db, session_factory, monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    async with session_factory() as seed_db:
        repo = MessageRepository(seed_db)
        await repo.add_message(1, "user", "hi")
        await repo.add_message(1, "assistant", "hello!")

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(ChatRequest(query="how are you", conversation_id=1)):
        pass

    state = graph.received_state
    assert state["query"] == "how are you"
    assert state["conversation_id"] == "1"
    assert state["history"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello!"},
    ]


@pytest.mark.asyncio
async def test_stream_keeps_api_key_out_of_graph_state(db, monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(
        ChatRequest(
            query="q",
            conversation_id=1,
            llm_config=LLMConfig(model="m", model_provider="openai", api_key="secret"),
        )
    ):
        pass

    assert graph.received_state["llm_config"] == {
        "model": "m",
        "model_provider": "openai",
    }
    assert "api_key" not in graph.received_state["llm_config"]
    assert get_request_api_key() is None


async def _get_messages(session_factory, conversation_id):
    async with session_factory() as db:
        messages = await MessageRepository(db).list_for_history(conversation_id)
        return [
            {"id": m.id, "role": m.role, "content": m.content, "extra": m.extra} for m in messages
        ]


@pytest.mark.asyncio
async def test_regenerate_reuses_last_user_message_without_duplicating(
    db, session_factory, monkeypatch
):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    async with session_factory() as seed_db:
        repo = MessageRepository(seed_db)
        await repo.add_message(1, "user", "q1")
        await repo.add_message(1, "assistant", "a1")
        await repo.add_message(1, "user", "q2")
        await repo.add_message(1, "assistant", "old answer")

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.regenerate(RegenerateRequest(conversation_id=1)):
        pass

    state = graph.received_state
    assert state["query"] == "q2"
    assert state["history"] == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]

    remaining = await _get_messages(session_factory, 1)
    roles = [m["role"] for m in remaining]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert remaining[-1]["content"] == "answer here"
    assert remaining[-2]["content"] == "q2"
    assert [m["content"] for m in remaining].count("q2") == 1


@pytest.mark.asyncio
async def test_regenerate_without_user_message_raises(db, session_factory, monkeypatch):
    async with session_factory() as seed_db:
        await MessageRepository(seed_db).add_message(1, "assistant", "only assistant")

    service = ChatService(graph=None, db=db, rag=None)

    async def _run():
        async for _ in service.regenerate(RegenerateRequest(conversation_id=1)):
            pass

    with pytest.raises(ValueError, match="No user message"):
        await _run()


@pytest.mark.asyncio
async def test_stream_on_client_disconnect_does_not_persist_partial_answer(
    db, session_factory, monkeypatch
):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = RaisingGraph(ClientDisconnect())
    service = ChatService(graph=graph, db=db, rag=None)

    chunks = []
    with pytest.raises(ClientDisconnect):
        async for chunk in service.stream(ChatRequest(query="q", conversation_id=1)):
            chunks.append(chunk)
    assert "".join(chunks) == "partial"

    remaining = await _get_messages(session_factory, 1)
    assert [m["role"] for m in remaining] == ["user"]
    assert get_request_api_key() is None


@pytest.mark.asyncio
async def test_export_markdown_and_json(db, session_factory, monkeypatch):
    async with session_factory() as seed_db:
        repo = MessageRepository(seed_db)
        await repo.add_message(1, "user", "q1")
        await repo.add_message(1, "assistant", "a1")

    service = ChatService(graph=None, db=db, rag=None)

    md = await service.export_conversation(1, "markdown")
    js = await service.export_conversation(1, "json")

    assert "# " in md
    assert "## User" in md
    assert "q1" in md
    assert "## Assistant" in md
    assert "a1" in md

    data = json.loads(js)
    assert data["title"] == "existing"
    assert data["messages"] == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]


@pytest.mark.asyncio
async def test_stream_persists_sources_and_details_on_message(db, session_factory, monkeypatch):
    sources = [
        {"source": "rag", "label": "a.pdf", "url": None, "document_id": "1"},
    ]
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph(sources)
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(ChatRequest(query="q", conversation_id=1)):
        pass

    remaining = await _get_messages(session_factory, 1)
    assistant = remaining[-1]
    assert assistant["content"] == "answer here"
    assert assistant["extra"]["sources"] == sources
    assert assistant["extra"]["details"]["model"] == "fake"


@pytest.mark.asyncio
async def test_stream_yields_error_marker_when_generation_fails(db, session_factory, monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FailingGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    chunks = []
    async for chunk in service.stream(ChatRequest(query="q", conversation_id=1)):
        chunks.append(chunk)

    events, text = parse_stream(chunks)
    errors = [e for e in events if e["type"] == "error"]
    assert errors and errors[0]["message"] == "boom"

    err_idx = text.index(ERROR_MARKER)
    payload = json.loads(text[err_idx + len(ERROR_MARKER) :].strip())
    assert payload["message"] == "boom"

    remaining = await _get_messages(session_factory, 1)
    assert [m["role"] for m in remaining] == ["user"]


def test_generate_title_rejects_placeholder_output(monkeypatch):
    def _fake_llm(output):
        return SimpleNamespace(model="fake", invoke=lambda prompt: SimpleNamespace(content=output))

    service = ChatService(graph=None, db=None, rag=None)

    async def _run(output):
        monkeypatch.setattr(
            cs,
            "get_llms",
            lambda **kwargs: (_fake_llm(output), SimpleNamespace()),
        )
        return await service.generate_title("hi")

    assert asyncio.run(_run("New Chat")) == "hi"
    assert asyncio.run(_run("new chat")) == "hi"

    assert asyncio.run(_run("Greeting")) == "Greeting"


class ThinkingBlockGraph(FakeGraph):
    """Draft model returns a thinking block plus the visible answer."""

    async def astream_events(self, state, config=None, version="v2"):
        self.received_state = state
        yield _chain_start("root", "Research Agent", None)
        yield _model(
            "on_chat_model_stream",
            "draft",
            "draft1",
            chunk=AIMessageChunk(content=[{"type": "thinking", "thinking": "internal reasoning"}]),
        )
        yield _model(
            "on_chat_model_stream",
            "draft",
            "draft1",
            chunk=AIMessageChunk(content=[{"type": "text", "text": "answer here"}]),
        )
        yield _model(
            "on_chat_model_end",
            "draft",
            "draft1",
            output=AIMessage(
                content=[
                    {"type": "thinking", "thinking": "internal reasoning"},
                    {"type": "text", "text": "answer here"},
                ]
            ),
        )
        yield _chain_end(
            "final1",
            "finalize",
            "finalize",
            parents=["root"],
            output={"sources": [], "response": "answer here", "status": "done"},
        )
        yield _chain_end("root", "Research Agent", None, output={"status": "done"})


@pytest.mark.asyncio
async def test_stream_never_exposes_thinking_blocks(db, session_factory, monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = ThinkingBlockGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    chunks = []
    async for chunk in service.stream(
        ChatRequest(query="q", conversation_id=1, agent_mode=AgentMode.THINKING)
    ):
        chunks.append(chunk)

    events, text = parse_stream(chunks)

    assert THINKING_MARKER not in text
    assert "internal reasoning" not in text
    assert answer_text(chunks) == "answer here"
    assert graph.received_state["agent_mode"] == "thinking"
    assert all(e.get("type") != "message_delta" or "internal" not in e["text"] for e in events)

    remaining = await _get_messages(session_factory, 1)
    assert remaining[-1]["content"] == "answer here"
    assert "thinking" not in remaining[-1]["extra"]


@pytest.mark.asyncio
async def test_stream_instant_mode_never_emits_thinking_marker(db, monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    chunks = []
    async for chunk in service.stream(ChatRequest(query="q", conversation_id=1)):
        chunks.append(chunk)

    text = "".join(chunks)
    assert THINKING_MARKER not in text
    assert answer_text(chunks) == "answer here"
    assert graph.received_state["agent_mode"] == "instant"


@pytest.mark.asyncio
async def test_stream_raises_the_graph_recursion_limit(db, monkeypatch):
    """A legitimate thinking run (plans + tasks + verification + quality loop)
    exceeds LangGraph's default of 25 super-steps and used to abort mid-run."""
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(ChatRequest(query="q", conversation_id=1)):
        pass

    assert graph.received_config["recursion_limit"] == GRAPH_RECURSION_LIMIT
    assert GRAPH_RECURSION_LIMIT > 25


@pytest.mark.asyncio
async def test_stream_reads_agent_settings(db, monkeypatch, tmp_path):
    from settings.store import SettingsStore

    store = SettingsStore(tmp_path / "settings.json")
    store.set_agent(recursion_limit=321, default_effort="thinking")
    monkeypatch.setattr(cs, "get_settings_store", lambda: store)
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(ChatRequest(query="q", conversation_id=1)):
        pass

    assert graph.received_config["recursion_limit"] == 321
    assert graph.received_state["agent_mode"] == "thinking"


@pytest.mark.asyncio
async def test_stream_records_agent_run_telemetry(db, monkeypatch, tmp_path):
    from telemetry.config import TelemetryConfig
    from telemetry.storage import TelemetryStore

    store = TelemetryStore(str(tmp_path / "telemetry.db"))
    real_start = cs.start_request_tracking
    monkeypatch.setattr(
        cs,
        "start_request_tracking",
        lambda **kwargs: real_start(**kwargs, store=store, config=TelemetryConfig(enabled=True)),
    )
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(ChatRequest(query="q", conversation_id=1)):
        pass

    events = store.list_events()
    assert len(events) == 1
    metrics = events[0]["metrics"]
    tags = events[0]["tags"]
    spans = events[0]["spans"]

    assert tags["effort"] == "instant"
    assert tags["intent"] == "research"
    assert tags["tools_allowed"] == "web"

    assert metrics["tool_calls"] == 1
    assert metrics["tool_calls_web_search"] == 1
    assert metrics["tool_failures"] == 0
    assert metrics["tool_ms_web_search"] >= 0
    assert metrics["stage_ms_web_search"] >= 0
    assert metrics["node_ms_route_intent"] >= 0
    assert metrics["node_ms_plan"] >= 0
    assert metrics["replans"] == 0
    assert metrics["input_tokens"] == 7
    assert metrics["total_tokens"] == 10
    assert metrics["answer_chars"] == len("answer here")

    names = {(span["name"], span["span_type"]) for span in spans}
    assert ("web_search", "TOOL") in names
    assert ("Web Search", "STAGE") in names
    assert ("Planning", "NODE") in names
    assert all(span["duration_ms"] >= 0 for span in spans)


@pytest.mark.asyncio
async def test_stream_passes_request_overrides_into_state(db, monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_llms",
        lambda **kwargs: (SimpleNamespace(model="fake"), SimpleNamespace()),
    )

    graph = FakeGraph([])
    service = ChatService(graph=graph, db=db, rag=None)

    async for _ in service.stream(
        ChatRequest(
            query="q",
            conversation_id=1,
            mode="summarize",
            source="web",
            retrieval={"search_type": "sparse", "limit": 4, "search_depth": "advanced"},
        )
    ):
        pass

    state = graph.received_state
    assert state["retrieval_config"] == {
        "search_type": "sparse",
        "limit": 4,
        "rerank": None,
        "search_depth": "advanced",
    }
    assert state["mode_override"] == "summarize"
    assert state["source_override"] == "web"

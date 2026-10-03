import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent.graphs import (
    ROOT_GRAPH_NAME,
    SUBGRAPH_LABELS,
    build_orchestrator_graph,
    code_graph,
    document_graph,
    web_graph,
    writing_graph,
)
from agent.prompts.analysis import ClaimDraft, ClaimsOutput, ClusterOutput, ThemeDraft
from agent.prompts.code import CodeScript, FindingOutput
from agent.prompts.orchestrator import PlannedTask, ResearchPlanDraft
from agent.prompts.quality import QualityOutput
from agent.prompts.router import RouteDecision
from agent.prompts.verification import ClaimVerdict, VerifyOutput
from agent.prompts.web import SearchQueries
from agent.prompts.writing import OutlineOutput, OutlineSection
from agent.state.schemas import initial_state
from agent.tools.registry import registry
from app.backend.services.agent_events import AgentEventAdapter
from app.backend.services.chat_service import GRAPH_RECURSION_LIMIT
from settings import reset_settings_store

STRUCTURED_MODULES = (
    "agent.nodes.analysis",
    "agent.nodes.router",
    "agent.nodes.code",
    "agent.nodes.orchestrator",
    "agent.nodes.quality",
    "agent.nodes.verification",
    "agent.nodes.web",
    "agent.nodes.writing",
)

PAGE_TEXT = (
    "This paragraph is deliberately long enough to survive passage extraction and it "
    "mentions alpha facts about the topic so overlapping terms can be detected."
)


class FakeRag:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.calls = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        return self.docs


class FakeWebSearch:
    def __init__(self, results=None):
        self.results = results if results is not None else self._defaults()
        self.calls = []

    @staticmethod
    def _defaults():
        return [
            type(
                "Result",
                (),
                {
                    "title": f"Result {i}",
                    "url": f"https://example.com/{i}",
                    "content": f"content {i}",
                    "score": 0.9,
                },
            )()
            for i in range(5)
        ]

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.results


class FakeStructured:
    def __init__(self, recorder, schema, response):
        self._recorder = recorder
        self._schema = schema
        self._response = response

    async def ainvoke(self, messages, **kwargs):
        self._recorder.append(
            {"schema": self._schema, "messages": messages, "kwargs": kwargs}
        )
        return self._response


class FakeDraftLLM:
    def __init__(self, recorder, text="the answer"):
        self._recorder = recorder
        self._text = text

    async def astream(self, messages, **kwargs):
        self._recorder.append({"messages": messages, "kwargs": kwargs})
        yield AIMessage(
            content=self._text,
            usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
        )


def _rag_doc(text, **metadata):
    return type("Doc", (), {"text": text, "score": 0.8, "metadata": metadata})()


def _default_responses(tasks):
    return {
        RouteDecision: RouteDecision(
            decision="research", tools=["web", "document", "code"], reason="test"
        ),
        ResearchPlanDraft: ResearchPlanDraft(
            objective="answer the question",
            tasks=tasks,
        ),
        SearchQueries: SearchQueries(
            queries=["alpha query", "beta query", "gamma query"]
        ),
        ClusterOutput: ClusterOutput(
            themes=[ThemeDraft(name="Theme", summary="summary", evidence_ids=[])]
        ),
        ClaimsOutput: ClaimsOutput(claims=[ClaimDraft(text="a claim", evidence_ids=[])]),
        VerifyOutput: VerifyOutput(
            verdicts=[ClaimVerdict(index=0, status="supported", reasoning="ok")]
        ),
        OutlineOutput: OutlineOutput(
            sections=[OutlineSection(heading="Intro", summary="s")] * 3
        ),
        QualityOutput: QualityOutput(passed=True, feedback=[]),
        CodeScript: CodeScript(code="print(1)", explanation="compute"),
        FindingOutput: FindingOutput(findings=["the result is 1"]),
    }


def _tasks(*specs):
    return [
        PlannedTask(id=f"t{i}", graph=graph, query=query)
        for i, (graph, query) in enumerate(specs, start=1)
    ]


@pytest.fixture(autouse=True)
def _isolated_state():
    registry.clear()
    reset_settings_store()
    yield
    registry.clear()
    reset_settings_store()


def setup(monkeypatch, *, tasks, responses=None, rag_docs=None, web_results=None):
    """Build the orchestrator graph with fake LLMs and fake tools/services."""
    structured_calls: list[dict] = []
    draft_calls: list[dict] = []
    merged = _default_responses(tasks)
    if responses:
        merged.update(responses)

    def fake_build_structured(schema, *args, **kwargs):
        assert schema in merged, f"no fake response configured for {schema.__name__}"
        return FakeStructured(structured_calls, schema, merged[schema])

    for module in STRUCTURED_MODULES:
        monkeypatch.setattr(f"{module}.build_structured_llm", fake_build_structured)

    monkeypatch.setattr(
        "agent.nodes.writing.get_llm",
        lambda *a, **k: FakeDraftLLM(draft_calls),
    )
    monkeypatch.setattr(
        "agent.tools.web_tools.fetch_page", lambda url, timeout=15: PAGE_TEXT
    )

    rag = FakeRag(rag_docs if rag_docs is not None else [])
    web = FakeWebSearch(web_results)
    registry.register("rag", rag)
    registry.register("web_search", web)

    graph = build_orchestrator_graph()
    return graph, structured_calls, draft_calls, rag, web


async def run(graph, state=None, thread_id="1"):
    return await graph.ainvoke(
        state if state is not None else initial_state("what happened?"),
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        },
    )


def test_graph_names_are_stable_display_labels():
    assert ROOT_GRAPH_NAME == "Research Agent"
    assert build_orchestrator_graph().name == ROOT_GRAPH_NAME
    assert web_graph.name == "Web Search"
    assert document_graph.name == "Document Analysis"
    assert code_graph.name == "Code Execution"
    assert writing_graph.name == "Writing"
    assert SUBGRAPH_LABELS["quality"] == "Quality Review"


async def test_graph_runs_full_pipeline(monkeypatch):
    docs = [_rag_doc("document passage", document_id="1", title="a.pdf", chunk_id="c1")]
    graph, structured, draft, rag, web = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts"), ("document", "read the report"), ("code", "compute it")),
        rag_docs=docs,
    )

    result = await run(graph, initial_state("what happened?", agent_mode="thinking"))

    assert result["response"] == "the answer"
    assert result["status"] == "done"
    assert len(rag.calls) == 1
    assert len(web.calls) == 3
    assert {c["schema"] for c in structured} >= {
        ResearchPlanDraft,
        SearchQueries,
        ClusterOutput,
        VerifyOutput,
        OutlineOutput,
        QualityOutput,
    }
    assert len(draft) == 1
    assert draft[0]["kwargs"] == {"thinking_level": "high", "include_thoughts": True}


async def test_graph_sources_cover_web_document_and_code(monkeypatch):
    docs = [_rag_doc("document passage", document_id="1", title="a.pdf", chunk_id="c1")]
    graph, *_ = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts"), ("document", "read the report"), ("code", "compute it")),
        rag_docs=docs,
    )

    result = await run(graph)

    by_kind = {s["source"] for s in result["sources"]}
    assert by_kind == {"web", "rag", "code"}

    web_source = next(s for s in result["sources"] if s["source"] == "web")
    assert web_source["url"].startswith("https://example.com/")
    assert web_source["domain"] == "example.com"

    doc_source = next(s for s in result["sources"] if s["source"] == "rag")
    assert doc_source["document_id"] == "1"
    assert doc_source["label"] == "a.pdf"

    assert next(s for s in result["sources"] if s["source"] == "code")["label"] == (
        "Code execution"
    )


async def test_plan_prompt_includes_chat_history(monkeypatch):
    graph, structured, *_ = setup(monkeypatch, tasks=_tasks(("document", "read it")))

    await run(
        graph,
        initial_state(
            "what happened?",
            history=[
                {"role": "user", "content": "earlier question"},
                {"role": "assistant", "content": "earlier answer"},
            ],
        ),
    )

    plan_call = next(c for c in structured if c["schema"] is ResearchPlanDraft)
    human = next(m["content"] for m in plan_call["messages"] if m["role"] == "user")
    assert "earlier question" in human
    assert "earlier answer" in human
    assert "what happened?" in human


async def test_retrieval_config_reaches_document_tool(monkeypatch):
    graph, _, _, rag, _ = setup(monkeypatch, tasks=_tasks(("document", "read it")))

    await run(
        graph,
        initial_state(
            "what happened?",
            retrieval_config={"search_type": "sparse", "limit": 4, "search_depth": "advanced"},
        ),
    )

    assert rag.calls == [{"query": "read it", "limit": 4, "search_type": "sparse"}]


async def test_search_depth_reaches_web_tool(monkeypatch):
    graph, _, _, _, web = setup(monkeypatch, tasks=_tasks(("web", "find facts")))

    await run(
        graph,
        initial_state("what happened?", retrieval_config={"search_depth": "advanced"}),
    )

    assert {c["search_depth"] for c in web.calls} == {"advanced"}
    assert len(web.calls) == 3


async def test_web_limits_come_from_settings(monkeypatch):
    from settings import get_settings_store

    get_settings_store().set_web(
        results_per_query=9, pages_fetched=2, search_depth="advanced"
    )
    graph, _, _, _, web = setup(monkeypatch, tasks=_tasks(("web", "find facts")))

    await run(graph, initial_state("what happened?"))

    assert {c["max_results"] for c in web.calls} == {9}
    assert {c["search_depth"] for c in web.calls} == {"advanced"}


async def test_request_retrieval_config_still_beats_settings(monkeypatch):
    from settings import get_settings_store

    get_settings_store().set_web(search_depth="advanced")
    graph, _, _, _, web = setup(monkeypatch, tasks=_tasks(("web", "find facts")))

    await run(
        graph,
        initial_state("what happened?", retrieval_config={"search_depth": "basic"}),
    )

    assert {c["search_depth"] for c in web.calls} == {"basic"}


async def test_plan_uses_settings_iterations(monkeypatch):
    from settings import get_settings_store

    get_settings_store().set_agent(max_research_iterations=1)
    graph, *_ = setup(monkeypatch, tasks=_tasks(("web", "find facts")))

    result = await run(graph, initial_state("what happened?", agent_mode="thinking"))

    assert result["plan"].max_iterations == 1


async def test_thinking_mode_passes_gemini_thinking_kwargs(monkeypatch):
    graph, _, draft, *_ = setup(monkeypatch, tasks=_tasks(("document", "read it")))

    await run(graph, initial_state("what happened?", agent_mode="thinking"))

    assert draft[0]["kwargs"] == {"thinking_level": "high", "include_thoughts": True}


async def test_instant_mode_never_requests_thoughts(monkeypatch):
    graph, _, draft, *_ = setup(monkeypatch, tasks=_tasks(("document", "read it")))

    await run(graph, initial_state("what happened?", agent_mode="instant"))

    assert draft[0]["kwargs"] == {"thinking_level": "minimal"}


async def test_quick_route_answers_without_any_tool(monkeypatch):
    graph, structured, draft, rag, web = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts")),
        responses={RouteDecision: RouteDecision(decision="quick", tools=[], reason="greeting")},
    )

    result = await run(
        graph,
        initial_state(
            "hi",
            history=[{"role": "user", "content": "earlier question"}],
        ),
    )

    assert result["intent"] == "quick"
    assert result["response"] == "the answer"
    assert result["status"] == "done"
    assert {c["schema"] for c in structured} == {RouteDecision}
    assert len(draft) == 1
    assert rag.calls == [] and web.calls == []
    assert result["sources"] == []

    system = next(m["content"] for m in draft[0]["messages"] if m["role"] == "system")
    assert "needed no tools" in system
    human = next(m["content"] for m in draft[0]["messages"] if m["role"] == "user")
    assert "earlier question" in human
    assert "Evidence:" not in human


async def test_chat_override_beats_the_router(monkeypatch):
    graph, structured, draft, web, *_ = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts")),
        responses={RouteDecision: RouteDecision(decision="research", tools=["web"], reason="model")},
    )

    result = await run(graph, initial_state("hello", mode_override="chat"))

    assert result["intent"] == "quick"
    assert result["routing_reason"] == "chat-only override"
    assert structured == []
    assert len(draft) == 1
    assert web.calls == []


async def test_source_override_forces_one_tool(monkeypatch):
    graph, structured, _, rag, web = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts"), ("document", "read it")),
        responses={RouteDecision: RouteDecision(decision="quick", tools=[], reason="model")},
    )

    result = await run(
        graph, initial_state("what does my file say?", source_override="documents")
    )

    assert result["intent"] == "research"
    assert result["allowed_tools"] == ["document"]
    assert result["routing_reason"] == "documents override"
    assert rag.calls and web.calls == []
    assert not any(c["schema"] is ResearchPlanDraft for c in structured)
    assert [t.graph for t in result["plan"].tasks] == ["document"]


async def test_plan_drops_tasks_outside_allowed_tools(monkeypatch):
    graph, structured, _, rag, web = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts"), ("document", "read it"), ("code", "compute it")),
        responses={
            RouteDecision: RouteDecision(
                decision="research", tools=["web", "document"], reason="model"
            )
        },
    )

    result = await run(graph, initial_state("search for it"))

    assert {t.graph for t in result["plan"].tasks} == {"web", "document"}
    assert web.calls and rag.calls
    assert not any(c["schema"] is CodeScript for c in structured)


async def test_single_tool_research_skips_the_planner(monkeypatch):
    graph, structured, _, rag, web = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts")),
        responses={RouteDecision: RouteDecision(decision="research", tools=["web"], reason="model")},
    )

    result = await run(graph, initial_state("search for it"))

    assert not any(c["schema"] is ResearchPlanDraft for c in structured)
    assert [t.graph for t in result["plan"].tasks] == ["web"]
    assert web.calls and rag.calls == []
    assert result["status"] == "done"


async def test_instant_skips_analysis_verification_and_quality(monkeypatch):
    graph, structured, *_ = setup(monkeypatch, tasks=_tasks(("web", "find facts")))

    result = await run(graph, initial_state("what happened?", agent_mode="instant"))

    schemas = {c["schema"] for c in structured}
    assert ResearchPlanDraft in schemas
    assert SearchQueries in schemas
    assert OutlineOutput not in schemas
    assert not schemas & {ClusterOutput, VerifyOutput, QualityOutput}
    assert result["response"] == "the answer"


async def test_plan_prompt_states_run_constraints(monkeypatch):
    graph, structured, *_ = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts"), ("document", "read it")),
        responses={
            RouteDecision: RouteDecision(
                decision="research", tools=["web", "document"], reason="model"
            )
        },
    )

    await run(graph, initial_state("search for it", agent_mode="instant"))

    plan_call = next(c for c in structured if c["schema"] is ResearchPlanDraft)
    system = next(m["content"] for m in plan_call["messages"] if m["role"] == "system")
    assert 'ONLY use these graph types: "web", "document"' in system
    assert "at most 2 tasks" in system


async def test_quality_rejection_triggers_revisions(monkeypatch):
    graph, structured, draft, *_ = setup(
        monkeypatch,
        tasks=_tasks(("document", "read it")),
        responses={QualityOutput: QualityOutput(passed=False, feedback=["needs work"])},
    )

    result = await run(graph, initial_state("what happened?", agent_mode="thinking"))

    checks = [c for c in structured if c["schema"] is QualityOutput]
    assert len(checks) == 4
    assert len(draft) == 4
    assert result["response"] == "the answer"


async def test_insufficient_research_triggers_replan(monkeypatch):
    graph, structured, *_ = setup(
        monkeypatch,
        tasks=_tasks(("document", "read it")),
        responses={
            VerifyOutput: VerifyOutput(
                verdicts=[ClaimVerdict(index=0, status="supported", reasoning="ok")],
                sufficient=False,
                gaps=["missing"],
            )
        },
    )

    result = await run(graph, initial_state("what happened?", agent_mode="thinking"))

    plans = [c for c in structured if c["schema"] is ResearchPlanDraft]
    assert len(plans) == 3
    assert result["status"] == "done"


@pytest.mark.asyncio
async def test_astream_events_maps_to_protocol_events(monkeypatch):
    docs = [_rag_doc("document passage", document_id="1", title="a.pdf", chunk_id="c1")]
    graph, *_ = setup(
        monkeypatch,
        tasks=_tasks(("web", "find facts"), ("document", "read the report")),
        rag_docs=docs,
    )
    monkeypatch.setattr(
        "agent.nodes.writing.get_llm",
        lambda *a, **k: GenericFakeChatModel(
            messages=iter(
                [
                    AIMessage(
                        content="the answer",
                        usage_metadata={
                            "input_tokens": 5,
                            "output_tokens": 2,
                            "total_tokens": 7,
                        },
                    )
                ]
            )
        ),
    )

    adapter = AgentEventAdapter()
    events = []
    async for event in adapter.stream(
        graph.astream_events(
            initial_state("what happened?", agent_mode="thinking"),
            config={"configurable": {"thread_id": "1"}},
            version="v2",
        )
    ):
        events.append(event)

    kinds = [e["type"] for e in events]
    assert kinds[0] == "agent_started"
    assert kinds[-1] == "agent_finished"
    assert not adapter.failed

    labels = {e["label"] for e in events if "label" in e}
    assert {"Web Search", "Document Analysis", "Analysis", "Writing", "Quality Review"} <= labels
    assert "Start" not in labels

    subgraph_done = [e for e in events if e["type"] == "subgraph_finished"]
    assert {e["label"] for e in subgraph_done} <= labels
    assert all(e["duration_ms"] is not None for e in subgraph_done)

    tool_names = {e["name"] for e in events if e["type"] == "tool_started"}
    assert {"web_search", "retrieve_documents"} <= tool_names

    statuses = {e["label"] for e in events if e["type"] == "agent_status"}
    assert "Planning" in statuses
    assert "Drafting response" in statuses

    assert adapter.answer == "the answer"
    assert any(s["source"] == "web" for s in adapter.sources)
    assert adapter.route_decision is not None
    assert adapter.route_decision["intent"] in {"quick", "research"}
    assert isinstance(adapter.route_decision["allowed_tools"], list)

    delta_events = [e for e in events if e["type"] == "message_delta"]
    assert len(delta_events) >= 2
    assert "".join(e["text"] for e in delta_events) == "the answer"

    tool_done = next(e for e in events if e["type"] == "tool_finished")
    assert tool_done["duration_ms"] is not None
    assert tool_done["ok"] is True


@pytest.mark.asyncio
async def test_astream_events_reports_failed_step(monkeypatch):
    graph, *_ = setup(monkeypatch, tasks=_tasks(("document", "read it")))

    def boom(*args, **kwargs):
        raise RuntimeError("llm exploded")

    monkeypatch.setattr("agent.nodes.writing.get_llm", lambda *a, **k: type(
        "Broken", (), {"astream": boom}
    )())

    adapter = AgentEventAdapter()
    events = []
    with pytest.raises(RuntimeError):
        async for event in adapter.stream(
            graph.astream_events(
                initial_state("what happened?"),
                config={"configurable": {"thread_id": "1"}},
                version="v2",
            )
        ):
            events.append(event)

    error = adapter.failure_event("llm exploded")
    assert error["type"] == "error"
    assert error["message"] == "llm exploded"
    assert error["node"] == "draft"
    assert error["label"] == "Drafting response"
    assert adapter.failed is True
    assert events and events[-1]["type"] != "error"

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime

import pytest

from telemetry import (
    NullTelemetryTracker,
    TelemetryConfig,
    TelemetryTracker,
    clear_request_tracking,
    get_current_tracker,
    start_request_tracking,
)
from telemetry.storage import TelemetryStore
from telemetry.tokens import estimate_token_counts


@pytest.fixture
def store(tmp_path) -> TelemetryStore:
    return TelemetryStore(db_path=str(tmp_path / "telemetry.db"))


@pytest.fixture
def file_config(tmp_path) -> TelemetryConfig:
    return TelemetryConfig(
        enabled=True,
        db_path=str(tmp_path / "telemetry.db"),
        environment="test",
        app_version="0.0.1-test",
    )


def test_disabled_tracker_is_a_noop(store, tmp_path):
    config = TelemetryConfig(
        enabled=False,
        db_path=str(tmp_path / "nope.db"),
    )
    tracker = TelemetryTracker(
        route="/chat/",
        config=config,
        store=store,
    )

    with tracker.timed("agent_latency_ms"):
        time.sleep(0.001)
    with tracker.span("generate_answer", span_type="LLM"):
        pass
    tracker.add_metric("input_tokens", 10)
    tracker.finish(success=True)

    assert tracker.enabled is False
    assert store.list_events() == []


def test_tracker_logs_metrics_and_tags(store, file_config):
    tracker = start_request_tracking(
        route="/chat/",
        request_id="req-test-1",
        conversation_id=7,
        model="gemini-test",
        embedding_model="bge-test",
        config=file_config,
        store=store,
    )
    try:
        with tracker.timed("retrieval_latency_ms"):
            time.sleep(0.005)
        tracker.add_metric("retrieved_documents", 4)
        tracker.add_metric("retrieved_documents", 1)
        tracker.add_metric("input_tokens", 100)
        tracker.add_metric("output_tokens", 50)
        tracker.add_metric("total_tokens", 150)
        tracker.add_tag("source", "rag")
    finally:
        tracker.finish(success=True)
        clear_request_tracking()

    events = store.list_events()
    assert len(events) == 1
    event = events[0]

    assert event["request_id"] == "req-test-1"
    assert event["route"] == "/chat/"
    assert event["conversation_id"] == "7"
    assert event["model"] == "gemini-test"
    assert event["embedding_model"] == "bge-test"
    assert event["success"] is True
    assert event["error_type"] is None
    assert event["environment"] == "test"
    assert event["app_version"] == "0.0.1-test"

    assert event["metrics"]["retrieved_documents"] == 5.0
    assert event["metrics"]["input_tokens"] == 100.0
    assert event["metrics"]["output_tokens"] == 50.0
    assert event["metrics"]["total_tokens"] == 150.0
    assert event["metrics"]["retrieval_latency_ms"] > 0.0

    tags = event["tags"]
    assert tags["request_id"] == "req-test-1"
    assert tags["conversation_id"] == "7"
    assert tags["route"] == "/chat/"
    assert tags["model"] == "gemini-test"
    assert tags["embedding_model"] == "bge-test"
    assert tags["success"] == "true"
    assert tags["source"] == "rag"
    assert "timestamp" in tags

    assert event["started_at"] is not None
    assert event["finished_at"] is not None
    assert event["duration_ms"] > 0.0

    assert isinstance(get_current_tracker(), NullTelemetryTracker)


def test_spans_are_recorded_with_latencies(store, file_config):
    tracker = TelemetryTracker(
        route="/chat/",
        request_id="req-spans",
        config=file_config,
        store=store,
    )
    try:
        with tracker.span(
            "chat_request", span_type="AGENT", latency_metric="agent_latency_ms"
        ) as root_span:
            assert root_span is not None
            assert root_span.name == "chat_request"
            assert root_span.span_type == "AGENT"
            with tracker.span("retrieve", span_type="RETRIEVER"):
                time.sleep(0.001)
    finally:
        tracker.finish(success=True)

    event = store.list_events()[0]
    assert event["metrics"]["agent_latency_ms"] > 0.0

    spans = event["spans"]
    assert [s["name"] for s in spans] == ["chat_request", "retrieve"]
    assert all(s["duration_ms"] > 0.0 for s in spans)


def test_persistence_failures_do_not_break_the_app(store, file_config, monkeypatch):
    def broken_insert(_event):
        raise RuntimeError("store is down")

    monkeypatch.setattr(store, "insert_event", broken_insert)

    tracker = TelemetryTracker(
        route="/chat/",
        request_id="req-fail",
        config=file_config,
        store=store,
    )
    assert tracker.enabled is True
    assert tracker._store is store

    with (
        pytest.raises(ValueError, match="app code error"),
        tracker.span("generate_answer", span_type="LLM", latency_metric="llm_latency_ms"),
    ):
        tracker.add_metric("input_tokens", 1)
        raise ValueError("app code error")

    tracker.finish(success=False, error_type="ValueError")
    with tracker.timed("agent_latency_ms"):
        time.sleep(0.001)


def test_request_scope_propagates_and_clears(store, file_config):
    async def _run() -> None:
        tracker = start_request_tracking(
            route="/chat/",
            conversation_id=3,
            config=file_config,
            store=store,
        )
        try:

            async def nested() -> bool:
                return get_current_tracker() is tracker

            assert await nested() is True
        finally:
            tracker.finish(success=True)
            clear_request_tracking()

        assert isinstance(get_current_tracker(), NullTelemetryTracker)

    asyncio.run(_run())


def test_request_id_defaults_to_uuid(store, file_config):
    tracker = TelemetryTracker(
        route="/documents/upload",
        config=file_config,
        store=store,
    )
    try:
        assert uuid.UUID(tracker.request_id).version == 4
    finally:
        tracker.finish(success=True)


def test_estimate_token_counts():
    counts = estimate_token_counts("hello world", "hi there")
    assert counts is not None
    assert counts[2] == counts[0] + counts[1]
    assert estimate_token_counts("", "") == (0, 0, 0)


def test_store_summary_aggregates(store):
    base = {
        "request_id": "req",
        "conversation_id": "1",
        "model": "m",
        "embedding_model": "e",
        "error_type": None,
        "environment": "test",
        "app_version": "0.0.1",
        "finished_at": None,
        "spans": [],
        "tags": {},
    }
    store.insert_event(
        {
            **base,
            "route": "/chat/",
            "success": True,
            "started_at": datetime.now(),
            "duration_ms": 120.0,
            "metrics": {"agent_latency_ms": 100.0, "retrieved_documents": 5},
        }
    )
    store.insert_event(
        {
            **base,
            "route": "/chat/",
            "success": True,
            "started_at": datetime.now(),
            "duration_ms": 80.0,
            "metrics": {"agent_latency_ms": 70.0, "retrieved_documents": 3},
        }
    )
    store.insert_event(
        {
            **base,
            "route": "/documents/upload",
            "success": False,
            "error_type": "ValueError",
            "started_at": datetime.now(),
            "duration_ms": 50.0,
            "metrics": {"index_latency_ms": 45.0},
        }
    )

    summary = store.summary()
    assert summary["total"] == 3
    assert summary["success"] == 2
    assert summary["failures"] == 1
    assert summary["success_rate"] == pytest.approx(66.67, abs=0.01)
    assert summary["avg_duration_ms"] == pytest.approx(83.33, abs=0.01)
    assert summary["metric_averages"]["agent_latency_ms"] == pytest.approx(85.0)
    assert summary["routes"]["/chat/"]["count"] == 2
    assert summary["routes"]["/chat/"]["success"] == 2
    assert summary["routes"]["/chat/"]["avg_duration_ms"] == pytest.approx(100.0)
    assert summary["routes"]["/documents/upload"]["count"] == 1
    assert len(summary["timeline"]) >= 1
    entry = summary["timeline"][0]
    assert set(entry) == {"hour", "count", "success", "failures", "avg_duration_ms"}


def test_store_list_get_clear(store):
    eid = store.insert_event(
        {
            "request_id": "req-1",
            "route": "/chat/",
            "conversation_id": None,
            "model": None,
            "embedding_model": None,
            "success": True,
            "error_type": None,
            "environment": "test",
            "app_version": "0.0.1",
            "started_at": datetime.now(),
            "finished_at": None,
            "duration_ms": 10.0,
            "metrics": {},
            "tags": {"request_id": "req-1"},
            "spans": [],
        }
    )

    assert store.get_event(eid)["route"] == "/chat/"
    assert store.get_event(9999) is None
    events = store.list_events()
    assert len(events) == 1
    assert events[0]["id"] == eid

    assert store.clear() == 1
    assert store.list_events() == []


def test_telemetry_endpoints(store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.backend.routers.telemetry_router import router

    app = FastAPI()
    app.include_router(router)
    app.state.telemetry_store = store

    with TestClient(app) as client:
        response = client.get("/telemetry/summary")
        assert response.status_code == 200
        assert response.json()["total"] == 0

        response = client.get("/telemetry/events")
        assert response.status_code == 200
        assert response.json()["events"] == []

        response = client.get("/telemetry/events/1")
        assert response.status_code == 404

        eid = store.insert_event(
            {
                "request_id": "req-2",
                "route": "/chat/",
                "conversation_id": None,
                "model": None,
                "embedding_model": None,
                "success": True,
                "error_type": None,
                "environment": "test",
                "app_version": "0.0.1",
                "started_at": datetime.now(),
                "finished_at": None,
                "duration_ms": 30.0,
                "metrics": {"agent_latency_ms": 25.0},
                "tags": {},
                "spans": [{"name": "chat_request", "span_type": "AGENT", "duration_ms": 25.0}],
            }
        )

        response = client.get(f"/telemetry/events/{eid}")
        assert response.status_code == 200
        assert response.json()["id"] == eid
        assert response.json()["spans"][0]["name"] == "chat_request"

        response = client.get("/telemetry/summary")
        assert response.json()["total"] == 1

        response = client.delete("/telemetry/events")
        assert response.status_code == 200
        assert response.json()["deleted"] == 1
        assert store.list_events() == []


def test_agent_run_recorder_flattens_stream_events(store, file_config):
    from app.backend.services.agent_telemetry import AgentRunRecorder

    tracker = TelemetryTracker(route="/chat/", config=file_config, store=store)
    recorder = AgentRunRecorder(tracker)

    recorder.handle({"type": "agent_started", "id": "root"})
    recorder.handle({"type": "tool_started", "id": "t1", "name": "web_search"})
    recorder.handle(
        {"type": "tool_finished", "id": "t1", "name": "web_search", "ok": True, "duration_ms": 120.5}
    )
    recorder.handle({"type": "tool_started", "id": "t2", "name": "retrieve_documents"})
    recorder.handle(
        {
            "type": "tool_finished",
            "id": "t2",
            "name": "retrieve_documents",
            "ok": False,
            "duration_ms": 30.0,
        }
    )
    recorder.handle(
        {"type": "subgraph_finished", "id": "s1", "label": "Web Search", "duration_ms": 500.0}
    )
    recorder.handle({"type": "subgraph_finished", "id": "s2", "label": "Quality Review", "duration_ms": 100.0})
    recorder.handle({"type": "subgraph_finished", "id": "s3", "label": "Quality Review", "duration_ms": 150.0})
    recorder.handle(
        {
            "type": "agent_status",
            "node": "route_intent",
            "status": "done",
            "label": "Deciding what's needed",
            "duration_ms": 40.0,
        }
    )
    recorder.handle(
        {"type": "agent_status", "node": "replan", "status": "done", "label": "Replan", "duration_ms": 10.0}
    )
    recorder.handle({"type": "error", "message": "boom"})
    recorder.handle({"type": "message_delta", "text": "ignored"})

    recorder.finish(
        intent="research",
        allowed_tools=["web", "document"],
        sources=[{"source": "web"}],
        answer="hello",
        usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    tracker.finish(success=True)

    [event] = store.list_events()
    metrics = event["metrics"]
    tags = event["tags"]
    spans = {(s["name"], s["span_type"]) for s in event["spans"]}

    assert metrics["tool_calls"] == 2
    assert metrics["tool_failures"] == 1
    assert metrics["tool_ms"] == pytest.approx(150.5)
    assert metrics["tool_calls_web_search"] == 1
    assert metrics["tool_calls_retrieve_documents"] == 1
    assert metrics["stage_runs"] == 3
    assert metrics["stage_ms_web_search"] == pytest.approx(500.0)
    assert metrics["stage_ms_quality_review"] == pytest.approx(250.0)
    assert metrics["node_ms_route_intent"] == pytest.approx(40.0)
    assert metrics["replans"] == 1
    assert metrics["quality_revisions"] == 1
    assert metrics["agent_errors"] == 1
    assert metrics["sources_count"] == 1
    assert metrics["answer_chars"] == 5
    assert metrics["input_tokens"] == 7
    assert metrics["total_tokens"] == 10

    assert tags["intent"] == "research"
    assert tags["tools_allowed"] == "web,document"

    assert ("web_search", "TOOL") in spans
    assert ("retrieve_documents", "TOOL") in spans
    assert ("Web Search", "STAGE") in spans
    assert ("Quality Review", "STAGE") in spans
    assert ("Deciding what's needed", "NODE") in spans


def test_summary_splits_tags_and_spans(store):
    base = {
        "request_id": "req",
        "conversation_id": "1",
        "model": "m",
        "embedding_model": None,
        "error_type": None,
        "environment": "test",
        "app_version": "0.0.1",
        "success": True,
        "finished_at": None,
        "started_at": datetime.now(),
        "duration_ms": 100.0,
        "metrics": {},
    }
    store.insert_event(
        {
            **base,
            "route": "/chat/",
            "tags": {"effort": "instant", "intent": "quick"},
            "spans": [{"name": "Planning", "span_type": "NODE", "duration_ms": 20.0}],
        }
    )
    store.insert_event(
        {
            **base,
            "route": "/chat/",
            "tags": {"effort": "thinking", "intent": "research"},
            "spans": [
                {"name": "web_search", "span_type": "TOOL", "duration_ms": 100.0},
                {"name": "web_search", "span_type": "TOOL", "duration_ms": 300.0},
                {"name": "Web Search", "span_type": "STAGE", "duration_ms": 400.0},
            ],
        }
    )

    summary = store.summary()

    assert summary["tags"]["effort"] == {"instant": 1, "thinking": 1}
    assert summary["tags"]["intent"] == {"quick": 1, "research": 1}
    assert summary["spans"]["TOOL"]["web_search"] == {"count": 2, "avg_ms": 200.0}
    assert summary["spans"]["STAGE"]["Web Search"] == {"count": 1, "avg_ms": 400.0}
    assert summary["spans"]["NODE"]["Planning"] == {"count": 1, "avg_ms": 20.0}

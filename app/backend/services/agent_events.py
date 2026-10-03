from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from agent.graphs.labels import (
    ROOT_GRAPH_NAME,
    SUBGRAPH_GRAPH_NAMES,
    SUBGRAPH_NODE_NAMES,
    node_label,
)
from agent.llms import chunk_text_parts, extract_usage_tokens

EVENT_MARKER = "@@RESEARCH_EVENT@@"

ANSWER_NODE = "draft"
ROUTE_NODE = "route_intent"

MAX_TOOL_INPUT_CHARS = 2000
MAX_TOOL_OUTPUT_CHARS = 4000
MAX_SUMMARY_CHARS = 90


def encode_event(event: dict) -> str:
    """Frame one protocol event for the text stream (single-line payload)."""
    return f"{EVENT_MARKER}\n{json.dumps(event, ensure_ascii=False, default=str)}\n"


def _sanitize(value: Any, *, max_str: int, max_items: int, depth: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= max_str:
            return value
        return value[:max_str] + f"… [+{len(value) - max_str} chars]"
    if depth <= 0:
        return str(value)[:max_str]
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        out = {str(k): _sanitize(v, max_str=max_str, max_items=max_items, depth=depth - 1) for k, v in items}
        if len(value) > max_items:
            out["…"] = f"+{len(value) - max_items} more keys"
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)[:max_items]
        out = [_sanitize(v, max_str=max_str, max_items=max_items, depth=depth - 1) for v in items]
        if len(value) > max_items:
            out.append(f"… +{len(value) - max_items} more")
        return out
    return str(value)[:max_str]


def _tool_input(raw: Any) -> Any:
    return _sanitize(raw, max_str=MAX_TOOL_INPUT_CHARS, max_items=20, depth=4)


def _tool_output(raw: Any) -> Any:
    return _sanitize(raw, max_str=MAX_TOOL_OUTPUT_CHARS, max_items=50, depth=4)


def _tool_summary(raw: Any) -> str | None:
    if isinstance(raw, list):
        return f"{len(raw)} results"
    if isinstance(raw, str):
        text = " ".join(raw.split())
        if not text:
            return None
        if len(text) > MAX_SUMMARY_CHARS:
            return f"{len(raw)} chars"
        return text
    if isinstance(raw, dict):
        if "success" in raw:
            return "ok" if raw.get("success") else "failed"
        if "exit_code" in raw and raw.get("exit_code") is not None:
            return f"exit {raw.get('exit_code')}"
        return None
    if raw is None:
        return None
    return str(raw)[:MAX_SUMMARY_CHARS]


class AgentEventAdapter:
    """Stateful: one adapter per run. Collects answers/sources alongside events."""

    def __init__(self, *, answer_node: str = ANSWER_NODE):
        self.answer_node = answer_node
        self.answer = ""
        self.sources: list[dict] = []
        self.usage: dict[str, float] = {}
        self.subgraphs: set[str] = set()
        self.failed = False
        self.route_decision: dict | None = None

        self._started_at: dict[str, float] = {}
        self._open_subgraphs: dict[str, str] = {}
        self._open_steps: dict[str, dict] = {}
        self._emitted_node_error = False

    async def stream(self, raw: AsyncIterator[dict]) -> AsyncIterator[dict]:
        async for event in raw:
            for out in self._handle(event):
                yield out

    def failure_event(self, message: str) -> dict:
        """Innermost step that started but never finished = the failing one.

        LangGraph propagates node exceptions out of `astream_events` instead of
        emitting `on_chain_error`, so the caller reports the failure through here.
        """
        self.failed = True
        for payload in reversed(list(self._open_steps.values())):
            out = {key: value for key, value in payload.items() if key != "parents"}
            out["type"] = "error"
            out["message"] = message
            return out
        return {
            "type": "error",
            "id": "request",
            "label": ROOT_GRAPH_NAME,
            "message": message,
            "scope": None,
        }

    def _open_step(self, run_id: str, payload: dict, parent_ids: list[str]) -> None:
        entry = dict(payload)
        entry["parents"] = list(parent_ids)
        self._open_steps[run_id] = entry

    def _close_step(self, run_id: str) -> None:
        self._open_steps.pop(run_id, None)
        descendants = [
            rid for rid, entry in self._open_steps.items() if run_id in entry.get("parents", [])
        ]
        for rid in descendants:
            self._open_steps.pop(rid, None)

    def _elapsed_ms(self, run_id: str) -> float | None:
        started = self._started_at.pop(run_id, None)
        if started is None:
            return None
        return round((time.monotonic() - started) * 1000, 1)

    def _scope(self, parent_ids: list[str]) -> str | None:
        for parent_id in reversed(parent_ids):
            if parent_id in self._open_subgraphs:
                return parent_id
        return None

    def _handle(self, event: dict) -> list[dict]:
        kind = event.get("event")
        meta = event.get("metadata") or {}
        node = meta.get("langgraph_node")
        name = event.get("name") or ""
        run_id = str(event.get("run_id") or "")
        parent_ids = [str(p) for p in (event.get("parent_ids") or [])]
        data = event.get("data") or {}

        if kind == "on_chain_start":
            return self._on_chain_start(node, name, run_id, parent_ids)
        if kind == "on_chain_end":
            return self._on_chain_end(node, name, run_id, parent_ids, data)
        if kind == "on_chain_error":
            return self._on_chain_error(node, name, run_id, parent_ids, data)
        if kind in ("on_tool_start", "on_tool_end", "on_tool_error"):
            return self._on_tool(kind, name, run_id, parent_ids, data)
        if kind == "on_chat_model_stream":
            return self._on_model_stream(node, data)
        if kind == "on_chat_model_end":
            return self._on_model_end(node, data)
        return []

    def _on_chain_start(self, node, name, run_id, parent_ids) -> list[dict]:
        if node is None:
            self._started_at[run_id] = time.monotonic()
            self._open_step(
                run_id, {"id": run_id, "label": ROOT_GRAPH_NAME, "scope": None}, parent_ids
            )
            return [{"type": "agent_started", "id": run_id, "name": ROOT_GRAPH_NAME}]

        if node == "__start__":
            return []

        if name in SUBGRAPH_GRAPH_NAMES:
            label = name
            self._started_at[run_id] = time.monotonic()
            self._open_subgraphs[run_id] = label
            self.subgraphs.add(label)
            self._open_step(
                run_id,
                {"id": run_id, "name": label, "label": label, "scope": self._scope(parent_ids)},
                parent_ids,
            )
            return [
                {
                    "type": "subgraph_started",
                    "id": run_id,
                    "name": label,
                    "label": label,
                    "scope": self._scope(parent_ids),
                }
            ]

        if name == node and node not in SUBGRAPH_NODE_NAMES:
            self._started_at[run_id] = time.monotonic()
            self._open_step(
                run_id,
                {
                    "id": run_id,
                    "node": node,
                    "label": node_label(node),
                    "scope": self._scope(parent_ids),
                },
                parent_ids,
            )
            return [
                {
                    "type": "agent_status",
                    "id": run_id,
                    "node": node,
                    "label": node_label(node),
                    "status": "running",
                    "scope": self._scope(parent_ids),
                }
            ]
        return []

    def _on_chain_end(self, node, name, run_id, parent_ids, data) -> list[dict]:
        out: list[dict] = []

        if node is None:
            self._close_step(run_id)
            self._open_steps.clear()
            out.append(
                {
                    "type": "agent_finished",
                    "id": run_id,
                    "name": ROOT_GRAPH_NAME,
                    "duration_ms": self._elapsed_ms(run_id),
                }
            )
            return out

        if node == "__start__":
            return out

        if name in SUBGRAPH_GRAPH_NAMES:
            self._close_step(run_id)
            label = self._open_subgraphs.pop(run_id, name)
            duration = self._elapsed_ms(run_id)
            out.append(
                {
                    "type": "subgraph_finished",
                    "id": run_id,
                    "name": label,
                    "label": label,
                    "scope": self._scope(parent_ids),
                    "duration_ms": duration,
                }
            )
            return out

        if name == node and node not in SUBGRAPH_NODE_NAMES:
            self._close_step(run_id)
            payload = {
                "type": "agent_status",
                "id": run_id,
                "node": node,
                "label": node_label(node),
                "status": "done",
                "scope": self._scope(parent_ids),
                "duration_ms": self._elapsed_ms(run_id),
            }
            output = data.get("output")
            if isinstance(output, dict) and isinstance(output.get("status"), str):
                payload["state"] = output["status"]
            out.append(payload)

            if node == ROUTE_NODE and isinstance(output, dict):
                self.route_decision = output

            if node == "finalize" and isinstance(output, dict):
                sources = output.get("sources")
                if isinstance(sources, list):
                    self.sources = sources
        return out

    def _on_chain_error(self, node, name, run_id, parent_ids, data) -> list[dict]:
        error = data.get("error")
        message = str(error) if error else "Step failed"
        if not message:
            message = type(error).__name__ if error else "Step failed"
        self._close_step(run_id)
        self.failed = True

        if node is None:
            if self._emitted_node_error:
                return []
            return [
                {
                    "type": "error",
                    "id": run_id,
                    "label": ROOT_GRAPH_NAME,
                    "message": message,
                    "scope": None,
                }
            ]

        if name == node and node not in SUBGRAPH_NODE_NAMES:
            self._emitted_node_error = True
            return [
                {
                    "type": "error",
                    "id": run_id,
                    "node": node,
                    "label": node_label(node),
                    "message": message,
                    "scope": self._scope(parent_ids),
                }
            ]
        return []

    def _on_tool(self, kind, name, run_id, parent_ids, data) -> list[dict]:
        scope = self._scope(parent_ids)

        if kind == "on_tool_start":
            self._started_at[run_id] = time.monotonic()
            self._open_step(
                run_id,
                {"id": run_id, "name": name, "label": name, "scope": scope},
                parent_ids,
            )
            return [
                {
                    "type": "tool_started",
                    "id": run_id,
                    "name": name,
                    "label": name,
                    "input": _tool_input(data.get("input")),
                    "scope": scope,
                }
            ]

        self._close_step(run_id)
        duration = self._elapsed_ms(run_id)

        if kind == "on_tool_end":
            output = data.get("output")
            return [
                {
                    "type": "tool_finished",
                    "id": run_id,
                    "name": name,
                    "label": name,
                    "ok": True,
                    "summary": _tool_summary(output),
                    "output": _tool_output(output),
                    "duration_ms": duration,
                    "scope": scope,
                }
            ]

        error = data.get("error")
        message = str(error) if error else "Tool failed"
        self._started_at.pop(run_id, None)
        return [
            {
                "type": "tool_finished",
                "id": run_id,
                "name": name,
                "label": name,
                "ok": False,
                "error": message,
                "duration_ms": duration,
                "scope": scope,
            }
        ]

    def _on_model_stream(self, node, data) -> list[dict]:
        if node != self.answer_node:
            return []
        chunk = data.get("chunk")
        text = "".join(chunk_text_parts(getattr(chunk, "content", None)))
        if not text:
            return []
        self.answer += text
        return [{"type": "message_delta", "text": text}]

    def _on_model_end(self, node, data) -> list[dict]:
        out: list[dict] = []
        output = data.get("output")

        usage = extract_usage_tokens(output)
        if usage:
            for key, value in usage.items():
                self.usage[key] = self.usage.get(key, 0) + value

        if node != self.answer_node or output is None:
            return out

        final = "".join(chunk_text_parts(getattr(output, "content", None)))
        if not final:
            return out
        if final.startswith(self.answer):
            extra = final[len(self.answer) :]
        elif self.answer:
            extra = ""
        else:
            extra = final
        if extra:
            self.answer += extra
            out.append({"type": "message_delta", "text": extra})
        return out

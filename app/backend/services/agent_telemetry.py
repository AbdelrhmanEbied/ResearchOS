from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "unknown"


def _ms(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


class AgentRunRecorder:
    """Turns the normalized agent event stream into telemetry for one request.

    Everything is derived from real events — no timers, no estimates:
    tool spans from tool_started/tool_finished, stage spans from
    subgraph_finished, node timings from agent_status, tokens from the
    accumulated model usage.
    """

    def __init__(self, tracker: Any) -> None:
        self._tracker = tracker
        self._open_tools: dict[str, str] = {}
        self._tool_calls: dict[str, int] = {}
        self._tool_ms: dict[str, float] = {}
        self._tool_failures = 0
        self._stage_runs: dict[str, int] = {}
        self._stage_ms: dict[str, float] = {}
        self._node_runs: dict[str, int] = {}
        self._node_ms: dict[str, float] = {}
        self._errors = 0

    @property
    def enabled(self) -> bool:
        return self._tracker is not None and bool(getattr(self._tracker, "enabled", False))

    def handle(self, event: dict) -> None:
        if not self.enabled or not isinstance(event, dict):
            return
        etype = event.get("type")

        if etype == "tool_started":
            self._open_tools[str(event.get("id"))] = str(event.get("name") or "tool")
            return

        if etype == "tool_finished":
            name = self._open_tools.pop(str(event.get("id")), None) or str(
                event.get("name") or "tool"
            )
            duration = _ms(event.get("duration_ms"))
            self._tool_calls[name] = self._tool_calls.get(name, 0) + 1
            self._tool_ms[name] = self._tool_ms.get(name, 0.0) + duration
            if not event.get("ok", True):
                self._tool_failures += 1
            self._tracker.record_span(name=name, span_type="TOOL", duration_ms=duration)
            return

        if etype == "subgraph_finished":
            label = str(event.get("label") or event.get("name") or "stage")
            duration = _ms(event.get("duration_ms"))
            self._stage_runs[label] = self._stage_runs.get(label, 0) + 1
            self._stage_ms[label] = self._stage_ms.get(label, 0.0) + duration
            self._tracker.record_span(name=label, span_type="STAGE", duration_ms=duration)
            return

        if etype == "agent_status" and event.get("status") == "done":
            node = str(event.get("node") or "").strip()
            if not node:
                return
            duration = _ms(event.get("duration_ms"))
            self._node_runs[node] = self._node_runs.get(node, 0) + 1
            self._node_ms[node] = self._node_ms.get(node, 0.0) + duration
            label = str(event.get("label") or node)
            self._tracker.record_span(name=label, span_type="NODE", duration_ms=duration)
            return

        if etype == "error":
            self._errors += 1

    def finish(
        self,
        *,
        intent: str | None = None,
        allowed_tools: Any = None,
        sources: list | None = None,
        answer: str = "",
        usage: dict | None = None,
    ) -> None:
        """Flush the accumulated run stats. Safe to call more than once."""
        if not self.enabled:
            return
        tracker = self._tracker

        total_tool_calls = sum(self._tool_calls.values())
        tracker.add_metric("tool_calls", total_tool_calls)
        tracker.add_metric("tool_failures", self._tool_failures)
        tracker.add_metric("tool_ms", round(sum(self._tool_ms.values()), 2))
        tracker.add_metric("stage_runs", sum(self._stage_runs.values()))
        tracker.add_metric("node_runs", sum(self._node_runs.values()))
        tracker.add_metric("replans", self._node_runs.get("replan", 0))
        tracker.add_metric("quality_revisions", max(0, self._stage_runs.get("Quality Review", 0) - 1))
        tracker.add_metric("agent_errors", self._errors)
        tracker.add_metric("sources_count", len(sources or []))
        tracker.add_metric("answer_chars", len(answer or ""))

        for name, count in self._tool_calls.items():
            tracker.add_metric(f"tool_calls_{_slug(name)}", count)
            tracker.add_metric(f"tool_ms_{_slug(name)}", round(self._tool_ms.get(name, 0.0), 2))
        for label, ms in self._stage_ms.items():
            tracker.add_metric(f"stage_ms_{_slug(label)}", round(ms, 2))
        for node, ms in self._node_ms.items():
            tracker.add_metric(f"node_ms_{_slug(node)}", round(ms, 2))

        for key, value in (usage or {}).items():
            if isinstance(value, (int, float)) and value:
                tracker.add_metric(str(key), float(value))

        if intent:
            tracker.add_tag("intent", str(intent))
        if isinstance(allowed_tools, (list, tuple)):
            tracker.add_tag("tools_allowed", ",".join(str(t) for t in allowed_tools) or "none")

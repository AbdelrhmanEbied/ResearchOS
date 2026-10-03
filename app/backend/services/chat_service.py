import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import ClientDisconnect

from agent.llms import (
    extract_llm_text,
    get_llms,
    get_request_api_key,
    set_request_api_key,
    set_request_conversation_id,
    set_request_llm_config,
)
from app.backend.database.repositories import (
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
)
from app.backend.schemas.chat import ChatRequest, RegenerateRequest
from app.backend.services.agent_events import EVENT_MARKER, AgentEventAdapter, encode_event
from app.backend.services.agent_telemetry import AgentRunRecorder
from settings import get_settings_store
from telemetry import clear_request_tracking, start_request_tracking

__all__ = [
    "DETAILS_MARKER",
    "ERROR_MARKER",
    "EVENT_MARKER",
    "GRAPH_RECURSION_LIMIT",
    "SOURCES_MARKER",
    "THINKING_MARKER",
    "ChatService",
]

logger = logging.getLogger(__name__)

SOURCES_MARKER = "@@RESEARCH_SOURCES@@"
DETAILS_MARKER = "@@RESEARCH_DETAILS@@"
ERROR_MARKER = "@@RESEARCH_ERROR@@"
THINKING_MARKER = "@@RESEARCH_THINKING@@"

GRAPH_RECURSION_LIMIT = 150


PROVIDER_LABELS = {
    "google_genai": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic Claude",
}


class ChatService:
    def __init__(self, graph, db: AsyncSession, rag=None):
        self.graph = graph
        self.db = db
        self.rag = rag

    def _embedding_model_name(self) -> str | None:
        try:
            return getattr(self.rag.embedder.dense_model, "model_name", None)
        except Exception:
            return None

    def _generation_model_name(self, llm_config: dict | None) -> str | None:
        if llm_config and llm_config.get("model"):
            return llm_config["model"]
        try:
            generation_llm = get_llms()[0]
            return getattr(generation_llm, "model_name", None) or getattr(
                generation_llm, "model", None
            )
        except Exception:
            return None

    def _generation_provider(self, llm_config: dict | None) -> str | None:
        if llm_config and llm_config.get("model_provider"):
            return llm_config["model_provider"]
        return get_settings_store().effective_llm()["model_provider"]

    @staticmethod
    def _fallback_title(query: str, max_length: int = 50) -> str:
        title = re.sub(r"\s+", " ", query.strip())
        title = title.rstrip(".,!?;:")

        if not title:
            return "New Chat"

        if len(title) <= max_length:
            return title

        truncated = title[:max_length]

        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]

        return truncated + "..."

    @staticmethod
    def _is_placeholder_title(title: str) -> bool:
        normalized = re.sub(r"[\W_]+", " ", title).strip().lower()
        return normalized in {
            "new chat",
            "new chat title",
            "a new chat",
            "chat title",
        }

    async def generate_title(
        self,
        query: str,
        llm_config: dict | None = None,
        max_length: int = 50,
    ) -> str:
        try:
            cfg = llm_config or {}
            llm = get_llms(
                model=cfg.get("model"),
                model_provider=cfg.get("model_provider"),
                api_key=get_request_api_key(),
            )[0]

            prompt = (
                "Generate a short, concise title (under 6 words) for a chat "
                "that starts with the user's message below. Reply with only "
                "the title, no quotes, no punctuation.\n\n"
                f'Message: "{query}"\n\nTitle:'
            )

            response = await run_in_threadpool(llm.invoke, prompt)
            title = extract_llm_text(response).strip().strip('"').strip()
            title = re.sub(r"\s+", " ", title)

            if title and not self._is_placeholder_title(title):
                if len(title) > max_length:
                    truncated = title[:max_length]
                    if " " in truncated:
                        truncated = truncated.rsplit(" ", 1)[0]
                    return truncated + "..."
                return title
        except Exception as exc:
            logger.warning("LLM title generation failed, using fallback: %s", exc)

        return self._fallback_title(query, max_length)

    async def _get_conversation(self, conversation_id: int) -> dict | None:
        conv = await ConversationRepository(self.db).get_by_id(conversation_id)
        return {"id": conv.id, "title": conv.title} if conv else None

    async def _get_message_history(self, conversation_id: int) -> list[dict]:
        messages = await self._get_messages(conversation_id)
        return [{"role": m["role"], "content": m["content"]} for m in messages]

    async def _get_messages(self, conversation_id: int) -> list[dict]:
        messages = await MessageRepository(self.db).list_for_history(conversation_id)
        return [{"id": m.id, "role": m.role, "content": m.content} for m in messages]

    async def _persist_message(self, conversation_id: int, role: str, content: str) -> int:
        message = await MessageRepository(self.db).add_message(conversation_id, role, content)
        return message.id

    async def _update_message_metadata(self, message_id: int, metadata: dict | None):
        return await MessageRepository(self.db).update_metadata(message_id, metadata)

    async def _delete_messages_after(self, conversation_id: int, after_id: int) -> int:
        return await MessageRepository(self.db).delete_after_id(conversation_id, after_id)

    async def _set_title(self, conversation_id: int, title: str):
        return await ConversationRepository(self.db).update_title(conversation_id, title)

    async def _attach_document_names(self, sources: list[dict]) -> list[dict]:
        doc_ids = {str(s.get("document_id")) for s in sources if s.get("document_id")}
        names: dict[str, str] = {}
        if doc_ids:
            all_docs = {str(doc.id): doc.name for doc in await DocumentRepository(self.db).list_all()}
            names = {key: value for key, value in all_docs.items() if key in doc_ids}

        enriched = []
        for source in sources:
            label = source.get("label")
            doc_id = source.get("document_id")
            db_name = names.get(str(doc_id)) if doc_id else None
            if db_name:
                label = db_name
            elif not label and doc_id:
                label = f"Document {doc_id}"
            enriched.append({**source, "label": label})
        return enriched

    @staticmethod
    def _sanitize_llm_config(request_llm_config) -> dict | None:
        if request_llm_config is None:
            return None
        return {
            "model": request_llm_config.model,
            "model_provider": request_llm_config.model_provider,
        }

    async def stream(self, request: ChatRequest) -> AsyncGenerator[str]:
        async for chunk in self._generate(
            conversation_id=request.conversation_id,
            query=request.query,
            llm_config=self._sanitize_llm_config(request.llm_config),
            request_api_key=request.llm_config.api_key if request.llm_config else None,
            mode=request.mode.value if request.mode else None,
            source=request.source.value if request.source else None,
            retrieval=request.retrieval.model_dump() if request.retrieval else None,
            agent_mode=request.agent_mode.value if request.agent_mode else None,
            history=None,
            persist_user=True,
            generate_title=True,
        ):
            yield chunk

    async def regenerate(self, request: RegenerateRequest) -> AsyncGenerator[str]:
        conversation = await self._get_conversation(request.conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {request.conversation_id} not found")

        messages = await self._get_messages(request.conversation_id)
        if not messages:
            raise ValueError("Conversation has no messages to regenerate")

        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                last_user_idx = i
                break

        if last_user_idx is None:
            raise ValueError("No user message to regenerate")

        last_user = messages[last_user_idx]

        trailing_ids = [m["id"] for m in messages[last_user_idx + 1 :] if m["id"] > last_user["id"]]
        if trailing_ids:
            await self._delete_messages_after(request.conversation_id, last_user["id"])

        history = [{"role": m["role"], "content": m["content"]} for m in messages[:last_user_idx]]

        async for chunk in self._generate(
            conversation_id=request.conversation_id,
            query=last_user["content"],
            llm_config=self._sanitize_llm_config(request.llm_config),
            request_api_key=request.llm_config.api_key if request.llm_config else None,
            mode=request.mode.value if request.mode else None,
            source=request.source.value if request.source else None,
            retrieval=request.retrieval.model_dump() if request.retrieval else None,
            agent_mode=request.agent_mode.value if request.agent_mode else None,
            history=history,
            persist_user=False,
            generate_title=False,
        ):
            yield chunk

    async def _generate(
        self,
        *,
        conversation_id: int,
        query: str,
        llm_config: dict | None,
        request_api_key: str | None,
        mode: str | None,
        source: str | None,
        retrieval: dict | None,
        agent_mode: str | None,
        history: list[dict] | None,
        persist_user: bool,
        generate_title: bool,
    ) -> AsyncGenerator[str]:
        set_request_api_key(request_api_key)
        set_request_llm_config(llm_config)
        set_request_conversation_id(str(conversation_id))

        tracker = None
        recorder: AgentRunRecorder | None = None
        title_task: asyncio.Task | None = None
        conversation = None
        details: dict | None = None
        assistant_buffer: list[str] = []
        sources: list[dict] = []
        assistant_message_id: int | None = None
        adapter = AgentEventAdapter()

        try:
            conversation = await self._get_conversation(conversation_id)
            if conversation is None:
                raise ValueError(f"Conversation {conversation_id} not found")
            if generate_title and not conversation["title"]:
                title_task = asyncio.create_task(
                    self.generate_title(query, llm_config)
                )

            if history is None:
                history = await self._get_message_history(conversation_id)

            if persist_user:
                await self._persist_message(conversation_id, "user", query)

            agent_settings = get_settings_store().get_agent()
            effort = agent_mode or agent_settings["default_effort"]
            recursion_limit = int(agent_settings["recursion_limit"]) or GRAPH_RECURSION_LIMIT

            tracker = start_request_tracking(
                route="/chat/",
                conversation_id=conversation_id,
                model=self._generation_model_name(llm_config),
                embedding_model=self._embedding_model_name(),
            )
            self._tag_request(
                tracker, mode=mode, source=source, retrieval=retrieval, effort=effort
            )
            recorder = AgentRunRecorder(tracker)

            state = {
                "query": query,
                "conversation_id": str(conversation_id),
                "history": history,
                "llm_config": llm_config,
                "retrieval_config": retrieval,
                "agent_mode": effort,
                "mode_override": mode,
                "source_override": source,
            }

            config = {
                "configurable": {
                    "thread_id": str(conversation_id),
                },
                "recursion_limit": recursion_limit,
            }

            async with tracker.span(
                "chat_request",
                span_type="AGENT",
                latency_metric="agent_latency_ms",
            ):
                async for event in adapter.stream(
                    self.graph.astream_events(state, config=config, version="v2")
                ):
                    recorder.handle(event)
                    if event.get("type") == "message_delta":
                        text = event.get("text") or ""
                        if text:
                            assistant_buffer.append(text)
                            yield text
                    else:
                        yield encode_event(event)

            sources = adapter.sources
            if title_task is not None:
                title = await title_task
                title_task = None
                if title:
                    await self._set_title(conversation["id"], title)
            details = self._build_details(
                tracker,
                llm_config,
                sources,
                model=self._generation_model_name(llm_config),
                provider=self._generation_provider(llm_config),
                agent_mode=agent_mode,
                usage=adapter.usage or None,
            )

            self._finish_tracking(recorder, adapter, tracker, sources, assistant_buffer)

        except ClientDisconnect:
            self._finish_tracking(
                recorder, adapter, tracker, sources, assistant_buffer, success=False,
                error_type="ClientDisconnect",
            )
            raise
        except asyncio.CancelledError:
            self._finish_tracking(
                recorder, adapter, tracker, sources, assistant_buffer, success=False,
                error_type="Cancelled",
            )
            raise
        except Exception as exc:
            self._finish_tracking(
                recorder, adapter, tracker, sources, assistant_buffer, success=False,
                error_type=type(exc).__name__,
            )
            logger.warning("Chat generation failed for conversation %s: %s", conversation_id, exc)
            message = str(exc) or type(exc).__name__
            error_payload = {"message": message}
            prefix = "\n\n" if assistant_buffer else ""
            yield encode_event(adapter.failure_event(message))
            yield f"{prefix}{ERROR_MARKER}\n{json.dumps(error_payload)}\n"
            return
        finally:
            if title_task is not None:
                title_task.cancel()
            if tracker is not None:
                clear_request_tracking()
            set_request_api_key(None)
            set_request_llm_config(None)
            set_request_conversation_id(None)

        full_answer = adapter.answer.strip() or "".join(assistant_buffer).strip()
        if full_answer:
            assistant_message_id = await self._persist_message(
                conversation_id, "assistant", full_answer
            )

        if assistant_message_id is not None and (sources or details):
            final_sources = await self._attach_document_names(sources)
            extra: dict = {}
            if final_sources:
                extra["sources"] = final_sources
            if details:
                extra["details"] = details
            await self._update_message_metadata(assistant_message_id, extra or None)

        if sources:
            final_sources = await self._attach_document_names(sources)
            if final_sources:
                yield f"\n\n{SOURCES_MARKER}\n{json.dumps(final_sources)}\n"

        if details:
            yield f"{DETAILS_MARKER}\n{json.dumps(details)}\n"

    @staticmethod
    def _finish_tracking(
        recorder: AgentRunRecorder,
        adapter: AgentEventAdapter,
        tracker,
        sources: list[dict],
        assistant_buffer: list[str],
        *,
        success: bool = True,
        error_type: str | None = None,
    ) -> None:
        """Flush run stats into telemetry, then persist the request event."""
        if tracker is None:
            return
        decision = adapter.route_decision or {}
        if recorder is not None:
            recorder.finish(
                intent=decision.get("intent"),
                allowed_tools=decision.get("allowed_tools"),
                sources=sources or adapter.sources,
                answer=adapter.answer or "".join(assistant_buffer),
                usage=adapter.usage or None,
            )
        tracker.finish(success=success, error_type=error_type)

    @staticmethod
    def _tag_request(
        tracker,
        *,
        mode: str | None,
        source: str | None,
        retrieval: dict | None,
        effort: str | None = None,
    ) -> None:
        if tracker is None:
            return
        if mode:
            tracker.add_tag("mode", mode)
        if source:
            tracker.add_tag("source", source)
        if effort:
            tracker.add_tag("effort", effort)
        if not retrieval:
            return
        if retrieval.get("search_type"):
            tracker.add_tag("search_type", retrieval["search_type"])
        if retrieval.get("limit"):
            tracker.add_tag("retrieval_limit", retrieval["limit"])
        if retrieval.get("rerank") is not None:
            tracker.add_tag("rerank", retrieval["rerank"])
        if retrieval.get("search_depth"):
            tracker.add_tag("search_depth", retrieval["search_depth"])

    @staticmethod
    def _build_details(
        tracker,
        llm_config: dict | None,
        sources: list[dict],
        *,
        model: str | None,
        provider: str | None,
        agent_mode: str | None = None,
        usage: dict | None = None,
    ) -> dict:
        metrics = tracker.metrics() if tracker is not None else {}
        tags = tracker.tags() if tracker is not None else {}

        if usage:
            tokens = {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }
        else:
            tokens = {
                "input_tokens": metrics.get("input_tokens"),
                "output_tokens": metrics.get("output_tokens"),
                "total_tokens": metrics.get("total_tokens"),
            }

        return {
            "model": model or (llm_config or {}).get("model"),
            "provider": PROVIDER_LABELS.get(provider, provider),
            "agent_mode": agent_mode,
            "source": tags.get("source"),
            "mode": tags.get("mode"),
            "search_type": tags.get("search_type"),
            "rerank": tags.get("rerank"),
            "retrieval_limit": tags.get("retrieval_limit"),
            "search_depth": tags.get("search_depth"),
            "retrieved_documents": metrics.get("retrieved_documents"),
            "reranked_documents": metrics.get("reranked_documents"),
            "source_count": len(sources),
            "latencies": {
                "agent_latency_ms": metrics.get("agent_latency_ms"),
                "rag_latency_ms": metrics.get("rag_latency_ms"),
                "web_search_latency_ms": metrics.get("web_search_latency_ms"),
                "retrieval_latency_ms": metrics.get("retrieval_latency_ms"),
                "reranker_latency_ms": metrics.get("reranker_latency_ms"),
                "generation_latency_ms": metrics.get("llm_latency_ms"),
            },
            "tokens": tokens,
        }

    async def export_conversation(self, conversation_id: int, fmt: str) -> str:
        conversation = await self._get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        messages = await self._get_messages(conversation_id)

        if fmt == "json":
            return json.dumps(
                {
                    "id": conversation["id"],
                    "title": conversation["title"],
                    "messages": [
                        {
                            "role": m["role"],
                            "content": m["content"],
                        }
                        for m in messages
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )

        if fmt == "markdown":
            title = conversation["title"] or "Conversation"
            lines = [f"# {title}", ""]
            for m in messages:
                lines.append(f"## {m['role'].capitalize()}")
                lines.append("")
                lines.append(m["content"])
                lines.append("")
            return "\n".join(lines)

        raise ValueError(f"Unsupported export format: {fmt}")

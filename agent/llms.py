import os
from contextvars import ContextVar
from functools import lru_cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from settings import get_settings_store
from settings.store import PROVIDERS

load_dotenv()

DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "google_genai")
DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY")

_request_api_key: ContextVar[str | None] = ContextVar("request_api_key", default=None)
_request_conversation_id: ContextVar[str | None] = ContextVar(
    "request_conversation_id", default=None
)
_request_llm_config: ContextVar[dict | None] = ContextVar("request_llm_config", default=None)


def set_request_api_key(api_key: str | None) -> None:
    _request_api_key.set(api_key)


def get_request_api_key() -> str | None:
    return _request_api_key.get()


def set_request_conversation_id(conversation_id: str | None) -> None:
    _request_conversation_id.set(conversation_id)


def get_request_conversation_id() -> str | None:
    return _request_conversation_id.get()


def set_request_llm_config(config: dict | None) -> None:
    _request_llm_config.set(config)


def get_request_llm_config() -> dict | None:
    return _request_llm_config.get()


def thinking_call_kwargs(
    agent_mode: str | None,
    model: str | None = None,
    model_provider: str | None = None,
) -> dict:
    """Gemini 3 thinking budget for one call. Empty for every other provider."""
    if model is None or model_provider is None:
        default_model, default_provider = _default_llm_config()
        model = model or default_model
        model_provider = model_provider or default_provider
    if model_provider != "google_genai":
        return {}
    if not (model or "").lower().startswith("gemini-3"):
        return {}
    if agent_mode == "thinking":
        return {"thinking_level": "high", "include_thoughts": True}
    return {"thinking_level": "minimal"}


def _default_llm_config() -> tuple[str, str]:
    request_cfg = _request_llm_config.get() or {}
    stored = get_settings_store().get_llm()
    model = request_cfg.get("model") or stored.get("model") or DEFAULT_MODEL
    provider = request_cfg.get("model_provider") or stored.get("model_provider") or DEFAULT_PROVIDER
    return model, provider


def _resolve_api_key(provider: str) -> str | None:
    request_key = _request_api_key.get()
    if request_key:
        return request_key
    store = get_settings_store()
    key = store.get_api_key(provider)
    if key:
        return key
    if provider == "google_genai":
        return DEFAULT_API_KEY
    env_key = os.getenv(PROVIDERS.get(provider, {}).get("env_key", ""))
    return env_key or None


def _build_llms(model: str, model_provider: str, api_key: str | None = None):
    kwargs = {"model": model, "model_provider": model_provider}
    if api_key:
        kwargs["api_key"] = api_key
    llm = init_chat_model(**kwargs)
    return llm, llm


@lru_cache(maxsize=32)
def _cached_llms(model: str, model_provider: str, api_key: str | None):
    return _build_llms(model, model_provider, api_key)


def get_llm(
    model: str | None = None,
    model_provider: str | None = None,
    api_key: str | None = None,
):
    if model is None or model_provider is None:
        default_model, default_provider = _default_llm_config()
        model = model or default_model
        model_provider = model_provider or default_provider
    if api_key is None:
        api_key = _resolve_api_key(model_provider)
    return _cached_llms(model, model_provider, api_key)[0]


def get_llms(
    model: str | None = None,
    model_provider: str | None = None,
    api_key: str | None = None,
) -> tuple:
    """Back-compat helper returning a (chat llm, llm) tuple."""
    if model is None or model_provider is None:
        default_model, default_provider = _default_llm_config()
        model = model or default_model
        model_provider = model_provider or default_provider
    if api_key is None:
        api_key = _resolve_api_key(model_provider)
    return _cached_llms(model, model_provider, api_key)


def build_structured_llm(
    schema,
    model: str | None = None,
    model_provider: str | None = None,
    api_key: str | None = None,
):
    if model is None or model_provider is None:
        default_model, default_provider = _default_llm_config()
        model = model or default_model
        model_provider = model_provider or default_provider
    if api_key is None:
        api_key = _resolve_api_key(model_provider)
    return _cached_structured_llm(model, model_provider, api_key, schema)


@lru_cache(maxsize=64)
def _cached_structured_llm(model: str, model_provider: str, api_key: str | None, schema):
    kwargs = {"model": model, "model_provider": model_provider}
    if api_key:
        kwargs["api_key"] = api_key
    return init_chat_model(**kwargs).with_structured_output(schema)


def _split_content_parts(content) -> tuple[list[str], list[str]]:
    """Split message content into answer text parts and thinking parts."""
    text_parts: list[str] = []
    thinking_parts: list[str] = []

    if isinstance(content, str):
        if content:
            text_parts.append(content)
        return text_parts, thinking_parts

    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                if block:
                    text_parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "thinking":
                    thought = block.get("thinking") or block.get("text")
                    if thought:
                        thinking_parts.append(thought)
                elif block_type == "text" or block_type in (None, "output_text", "content"):
                    text = block.get("text")
                    if text:
                        text_parts.append(text)

    return text_parts, thinking_parts


def chunk_text_parts(content) -> list[str]:
    text, _ = _split_content_parts(content)
    return text


def extract_llm_text(response) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(chunk_text_parts(content))
    return getattr(response, "text", "") or ""


def extract_usage_tokens(response) -> dict | None:
    usage = getattr(response, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return None

    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")

    if input_tokens is None or output_tokens is None:
        return None

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": usage.get("total_tokens") or input_tokens + output_tokens,
    }

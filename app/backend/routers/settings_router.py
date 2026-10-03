from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from settings import get_settings_store

router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
)


class LLMSettingsUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    model_provider: str = Field(min_length=1, max_length=100)


class ApiKeyUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    api_key: str | None = Field(default=None, max_length=500)


class RetrievalSettingsUpdate(BaseModel):
    search_type: str | None = Field(default=None, pattern="^(hybrid|dense|sparse)$")
    limit: int | None = Field(default=None, ge=1, le=50)
    rerank: bool | None = None
    rerank_top_k: int | None = Field(default=None, ge=1, le=50)


class WebSettingsUpdate(BaseModel):
    results_per_query: int | None = Field(default=None, ge=1, le=10)
    pages_fetched: int | None = Field(default=None, ge=1, le=10)
    search_depth: str | None = Field(default=None, pattern="^(basic|advanced)$")


class AgentSettingsUpdate(BaseModel):
    recursion_limit: int | None = Field(default=None, ge=25, le=500)
    max_research_iterations: int | None = Field(default=None, ge=1, le=6)
    default_effort: str | None = Field(default=None, pattern="^(instant|thinking)$")


@router.get("/")
def get_settings():
    return get_settings_store().public_dict()


@router.put("/llm")
def update_llm(body: LLMSettingsUpdate):
    get_settings_store().set_llm(body.model.strip(), body.model_provider.strip())
    return {"ok": True}


@router.put("/api-keys")
def update_api_key(body: ApiKeyUpdate):
    if body.api_key and not body.api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be blank.")
    get_settings_store().set_api_key(body.provider.strip(), body.api_key)
    return {"ok": True}


@router.put("/retrieval")
def update_retrieval(body: RetrievalSettingsUpdate):
    get_settings_store().set_retrieval(
        search_type=body.search_type,
        limit=body.limit,
        rerank=body.rerank,
        rerank_top_k=body.rerank_top_k,
    )
    return {"ok": True}


@router.put("/web")
def update_web(body: WebSettingsUpdate):
    get_settings_store().set_web(
        results_per_query=body.results_per_query,
        pages_fetched=body.pages_fetched,
        search_depth=body.search_depth,
    )
    return {"ok": True}


@router.put("/agent")
def update_agent(body: AgentSettingsUpdate):
    get_settings_store().set_agent(
        recursion_limit=body.recursion_limit,
        max_research_iterations=body.max_research_iterations,
        default_effort=body.default_effort,
    )
    return {"ok": True}

from __future__ import annotations

import pytest

from settings import get_settings_store, reset_settings_store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    reset_settings_store()
    yield tmp_path / "settings.json"
    reset_settings_store()


def test_store_persists_llm_defaults(isolated_store):
    store = get_settings_store(isolated_store)
    store.set_llm("gpt-4o", "openai")

    reloaded = get_settings_store(isolated_store)
    assert reloaded.get_llm() == {"model": "gpt-4o", "model_provider": "openai"}


def test_store_api_key_never_leaks_into_public_dict(isolated_store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    store = get_settings_store(isolated_store)
    store.set_api_key("openai", "sk-secret-value")

    public = store.public_dict()
    assert public["providers"]["openai"]["has_api_key"] is True
    dumped = str(public)
    assert "sk-secret-value" not in dumped

    assert store.get_api_key("openai") == "sk-secret-value"


def test_store_api_key_falls_back_to_env(isolated_store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-gemini-key")
    store = get_settings_store(isolated_store)
    assert store.has_api_key("google_genai") is True
    assert store.get_api_key("google_genai") is None
    store.set_api_key("google_genai", "stored-key")
    assert store.get_api_key("google_genai") == "stored-key"


def test_store_retrieval_defaults_and_overrides(isolated_store):
    store = get_settings_store(isolated_store)
    defaults = store.get_retrieval()
    assert defaults["search_type"] == "hybrid"
    assert defaults["rerank"] is True
    assert 1 <= defaults["limit"] <= 50

    store.set_retrieval(search_type="dense", limit=6, rerank=False)
    reloaded = get_settings_store(isolated_store)
    assert reloaded.get_retrieval()["search_type"] == "dense"
    assert reloaded.get_retrieval()["limit"] == 6
    assert reloaded.get_retrieval()["rerank"] is False


def test_settings_endpoints(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.backend.routers.settings_router import router
    from settings.store import SettingsStore

    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    store = SettingsStore(tmp_path / "settings.json")
    monkeypatch.setattr("app.backend.routers.settings_router.get_settings_store", lambda: store)

    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        res = client.get("/settings/").json()
        assert res["llm"]["default_provider"] == "google_genai"
        assert res["providers"]["google_genai"]["has_api_key"] is True
        assert "env-key" not in str(res)

        res = client.put("/settings/llm", json={"model": "gpt-4o", "model_provider": "openai"})
        assert res.status_code == 200
        assert client.get("/settings/").json()["llm"] == {
            "default_model": "gpt-4o",
            "default_provider": "openai",
        }

        res = client.put("/settings/api-keys", json={"provider": "openai", "api_key": "sk-x"})
        assert res.status_code == 200
        assert store.get_api_key("openai") == "sk-x"
        assert "sk-x" not in str(client.get("/settings/").json())

        res = client.put(
            "/settings/api-keys",
            json={"provider": "openai", "api_key": ""},
        )
        assert res.status_code == 200
        assert store.get_api_key("openai") is None

        res = client.put(
            "/settings/retrieval",
            json={"search_type": "sparse", "limit": 8, "rerank": False, "rerank_top_k": 3},
        )
        assert res.status_code == 200
        public = client.get("/settings/").json()
        assert public["retrieval"]["search_type"] == "sparse"
        assert public["retrieval"]["rerank_top_k"] == 3

        res = client.put(
            "/settings/web",
            json={"results_per_query": 7, "pages_fetched": 4, "search_depth": "advanced"},
        )
        assert res.status_code == 200
        assert client.get("/settings/").json()["web"] == {
            "results_per_query": 7,
            "pages_fetched": 4,
            "search_depth": "advanced",
        }

        res = client.put(
            "/settings/agent",
            json={
                "recursion_limit": 250,
                "max_research_iterations": 4,
                "default_effort": "thinking",
            },
        )
        assert res.status_code == 200
        assert client.get("/settings/").json()["agent"] == {
            "recursion_limit": 250,
            "max_research_iterations": 4,
            "default_effort": "thinking",
        }

        assert client.put("/settings/agent", json={"recursion_limit": 5}).status_code == 422
        assert client.put("/settings/web", json={"pages_fetched": 50}).status_code == 422
        assert (
            client.put("/settings/agent", json={"default_effort": "turbo"}).status_code == 422
        )


def test_store_web_and_agent_defaults_and_overrides(isolated_store):
    store = get_settings_store(isolated_store)
    assert store.get_web() == {
        "results_per_query": 5,
        "pages_fetched": 5,
        "search_depth": "basic",
    }
    assert store.get_agent() == {
        "recursion_limit": 150,
        "max_research_iterations": 3,
        "default_effort": "instant",
    }

    store.set_web(results_per_query=8, pages_fetched=3, search_depth="advanced")
    store.set_agent(recursion_limit=400, max_research_iterations=2, default_effort="thinking")

    reloaded = get_settings_store(isolated_store)
    assert reloaded.get_web() == {
        "results_per_query": 8,
        "pages_fetched": 3,
        "search_depth": "advanced",
    }
    assert reloaded.get_agent() == {
        "recursion_limit": 400,
        "max_research_iterations": 2,
        "default_effort": "thinking",
    }


def test_agent_and_web_settings_are_clamped(isolated_store):
    store = get_settings_store(isolated_store)
    store.set_web(results_per_query=99, pages_fetched=0, search_depth="silly")
    store.set_agent(recursion_limit=99999, max_research_iterations=0, default_effort="nope")

    web = store.get_web()
    assert web["results_per_query"] == 10
    assert web["pages_fetched"] == 1
    assert web["search_depth"] == "basic"

    agent = store.get_agent()
    assert agent["recursion_limit"] == 500
    assert agent["max_research_iterations"] == 1
    assert agent["default_effort"] == "instant"


def test_legacy_search_depth_still_applies(isolated_store):
    """search_depth used to live under retrieval; old files keep working."""
    store = get_settings_store(isolated_store)
    store.set("retrieval", {"search_type": "hybrid", "search_depth": "advanced"})
    assert store.get_web()["search_depth"] == "advanced"


def test_public_dict_exposes_web_and_agent(isolated_store):
    public = get_settings_store(isolated_store).public_dict()
    assert public["web"]["results_per_query"] == 5
    assert public["agent"]["recursion_limit"] == 150

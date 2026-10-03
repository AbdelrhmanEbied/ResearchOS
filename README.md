# Research-Assistant

A local-first AI research assistant with a clean web UI for chatting with LLMs, uploading documents, and searching your knowledge base with hybrid RAG. Your chats, documents, and settings live on your own machine. Models, retrieval options, and API keys are configurable from a Settings page — no code editing required.

[![CI/CD](https://github.com/AbdelrhmanEbied/research-assistant/actions/workflows/ci-cd.yaml/badge.svg)](https://github.com/AbdelrhmanEbied/research-assistant/actions/workflows/ci-cd.yaml)

## Demo

![Demo](assets/demo.gif)

> The demo GIF is from an early release — the current version adds Thinking mode, the live agent execution panel, token streaming, and much more (see the features below).

## What it does

Research-Assistant gives you a simple GUI where you can:

* chat with Google Gemini, OpenAI, or Anthropic Claude
* switch models / providers and set API keys from the Settings page
* upload documents into a local knowledge base and scope retrieval to them
* search the live web with Tavily
* **pick an effort level per request — Instant or Thinking** — both route the message first (a greeting is answered directly, "search the web for…" runs the web tool). Instant runs only the tools it needs; Thinking runs the full research pipeline and streams its chain of thought
* stream responses token-by-token with per-response details (model, retrieval options, latency, token usage) and citations that show the uploaded file name
* watch a live execution tree of what the agent is doing (planning, sub-graphs, tool calls with durations), collapsed by default until you click it
* regenerate an answer, export a conversation (markdown or JSON), rename chats, and search across them
* view an analytics dashboard of runs, router decisions, effort mix, tool usage, stage timing, and token usage
* keep chat history stored locally on your machine

Hybrid search is enabled by default, and dense-only and sparse-only retrieval are also available.

## Why I built it

This project was built to learn and practice:

* RAG systems
* AI agents
* FastAPI backend development
* LangChain and LangGraph orchestration
* local document search and retrieval
* frontend/backend communication for AI applications

## Architecture

```mermaid
flowchart LR
    subgraph FE["Frontend — app/frontend (vanilla JS, no bundler)"]
        UI["Chat · Settings<br/>Documents · Analytics"]
        RENDER["Render loop<br/>stream markers → execution panel,<br/>Thinking panel, answer, citations"]
    end

    subgraph BE["FastAPI — app/backend"]
        API["Routers<br/>/chat · /documents · /settings<br/>/telemetry · /health"]
        SVC["chat_service<br/>streaming · title task · persistence"]
        EVENTS["agent_events<br/>graph events → marker frames"]
    end

    subgraph AGENT["LangGraph agent — agent/"]
        ROUTE{"Router node<br/>quick or research?"}
        DRAFT["Draft<br/>token streaming"]
        PLAN["Plan<br/>skipped for single-tool runs"]
        subgraph TASKS["Tool sub-graphs"]
            WEB["web<br/>Tavily search + fetch"]
            DOC["document<br/>hybrid retrieval"]
            CODE["code<br/>sandboxed Python"]
        end
        PIPE["analysis → verification<br/>→ writing → quality<br/>Thinking only · replans on gaps"]
        FINAL["finalize"]
    end

    subgraph STORES["Local stores"]
        PG[("PostgreSQL<br/>chats · checkpointer")]
        QDRANT[("Qdrant<br/>FastEmbed + BM25")]
        SQLITE[("SQLite<br/>telemetry.db")]
        DISK[("uploads · settings.json")]
    end

    LLM["LLM providers<br/>Gemini · OpenAI · Claude"]

    UI -->|"POST /chat/stream"| API
    API --> SVC
    SVC --> AGENT
    AGENT -->|"events + token deltas"| EVENTS
    EVENTS --> RENDER
    ROUTE -->|"quick"| DRAFT
    ROUTE -->|"research"| PLAN
    PLAN --> TASKS
    TASKS --> PIPE
    PIPE --> FINAL
    DRAFT --> FINAL
    DOC --> QDRANT
    AGENT --> LLM
    SVC --> PG
    SVC --> SQLITE
    SVC --> DISK
```

### Request flow

1. The frontend sends the message (plus effort and any overrides) to `POST /chat/stream`.
2. The router node decides **quick answer vs. research** and which tools are allowed — greetings never touch the pipeline, and a single-tool run skips the planner entirely.
3. Research runs the tool sub-graphs it needs (web, documents, code), then — in **Thinking** effort — analysis, verification (with replanning when gaps remain), writing, and quality review. **Instant** effort stops after the tools and writes straight from the evidence.
4. The backend streams back a `text/plain` body: raw answer tokens plus marker frames (`@@RESEARCH_THINKING@@`, `@@RESEARCH_SOURCES@@`, `@@RESEARCH_DETAILS@@`, `@@RESEARCH_EVENT@@`, `@@RESEARCH_ERROR@@`) carrying thoughts, citations, and normalized agent events.
5. The frontend renders the live execution tree, the Thinking panel (both collapsed by default), and the answer bubble; every run is recorded in the local telemetry store.

Documents are chunked, embedded with FastEmbed (dense) and BM25 (sparse), and stored in Qdrant; chats live in PostgreSQL, telemetry in SQLite, and settings in a gitignored `settings.json`.

## Features

### Agent & chat

* Multi-provider LLM support (Gemini, OpenAI, Claude)
* **Dynamic routing** — a router node runs first and decides whether the message needs tools at all, and which ones. Explicit overrides (e.g. the documents *summarize* action) beat the model's decision
* **Instant / Thinking modes** — a collapsible menu next to the Send button:
  * **Instant** — routes the message, runs only the tools it needs, then drafts. Skips analysis, verification and quality review for low latency (Gemini 3 uses `thinking_level="minimal"`)
  * **Thinking** — the full pipeline: routing → plan → tools → analysis → verification → writing → quality review, with replanning when verification finds gaps (Gemini 3 uses `thinking_level="high"` + `include_thoughts=True`)
* **Token streaming** — the answer is streamed as it is generated (not emitted in one chunk), so the typewriter, syntax highlighting, and math typesetting all run on live text
* **Live execution panel** — a Claude Code style tree of the run: root agent, sub-graphs, steps, and tool calls with server-reported durations and a live badge. Collapsed by default; click the header to expand
* **Thinking panel** — the provider's actual thought content (Gemini `thinking` content blocks) streams progressively while generating, with live tool statuses such as *Running Python…* and *Reading documents…*. Collapsed by default; persisted with the message
* **Local-first agent tools** (no extra dependencies):
  * `web_search` / `fetch_url` — live web search and page fetching via Tavily
  * `retrieve_documents` — hybrid retrieval over the documents scoped to the current conversation
  * `run_code` — executes Python in an isolated subprocess (`python -I`) in a per-conversation workspace with a timeout
* Settings page for model defaults, web search, RAG, and agent limits (recursion limit, research iterations, default effort)
* Local chat UI with streaming responses, citations, and per-response details
* **Single send/stop button** — the composer button toggles between sending a message and stopping generation
* Chat history stored locally with PostgreSQL and async SQLAlchemy
* Conversation search, rename, export (markdown / JSON), and paginated history
* Regenerate answers

### Retrieval & documents

* Document upload and management, with one-click summarization
* Link documents to a conversation for scoped retrieval
* Hybrid RAG retrieval with Qdrant (dense, sparse, and hybrid search types)
* Live web search via Tavily (basic / advanced depth)
* FastEmbed embeddings and cross-encoder reranking
* Citations show the uploaded file name, page, and chunk

### Operations

* Telemetry: local SQLite analytics store and in-app dashboard (runs, router decisions, effort mix, tool usage, stage timings, token usage)
* Dockerized: multi-service stack (app, PostgreSQL, Qdrant) with pre-baked embedding models
* CI/CD pipeline: lint, format, tests, a retrieval-quality gate, and image publishing to GHCR

## Tech Stack

* FastAPI
* SQLAlchemy (async) + Alembic
* PostgreSQL
* LangChain / LangGraph
* Google Gemini / OpenAI / Anthropic Claude
* Qdrant + FastEmbed (dense + BM25)
* Tavily
* HTML, CSS, JavaScript (ES modules, no bundler)
* Docker

## Project structure

```bash
research-assistant/
├── agent/
│   ├── graphs/            # orchestrator + web/document/code/analysis/verification/writing/quality sub-graphs
│   ├── nodes/             # routing, planning, task, writing, quality nodes
│   ├── prompts/
│   ├── sandbox/           # isolated Python subprocess executor
│   ├── state/             # AgentState schemas
│   ├── tools/             # web_search, fetch_url, retrieve_documents, run_code
│   ├── llms.py            # model resolution, structured outputs, streaming helpers
│   └── web_service.py     # page fetch + parse for the web tool
├── alembic/               # migrations (alembic.ini at root)
├── app/
│   ├── backend/
│   │   ├── main.py        # FastAPI app, static files, cache revalidation middleware
│   │   ├── lifespan.py    # service bootstrap (RAG, telemetry, graph, checkpointer)
│   │   ├── database/      # models, repositories, async engine
│   │   ├── routers/       # chat, documents, settings, telemetry
│   │   ├── schemas/
│   │   └── services/      # chat, document, agent_events, agent_telemetry
│   └── frontend/
│       ├── index.html
│       ├── css/styles.css
│       └── js/            # ES modules: chat, render, agentstream, analytics, …
├── rag/                   # loader, chunker, embedder, retriever, reranker, qdrant manager
├── settings/              # settings.json store
├── telemetry/             # SQLite analytics store
├── evaluation/            # retrieval metrics + LLM-as-judge
├── tests/
├── scripts/evaluate_rag.py
├── .github/workflows/ci-cd.yaml
├── Dockerfile · docker-compose.yml · .env.example
├── paths.py · pyproject.toml · uv.lock
└── README.md
```

## Getting started

You can run Research-Assistant either **with Docker** (recommended) or **locally with uv**.

### Option A — Run with Docker (recommended)

Requires [Docker](https://docs.docker.com/engine/install/) with the Compose plugin.

```bash
git clone https://github.com/AbdelrhmanEbied/research-assistant.git
cd research-assistant

cp .env.example .env
# fill in your API keys (see "Environment variables" below)

docker compose up --build -d
```

Open `http://localhost:8000`.

What the compose setup does:

* starts three services: **app**, **postgres** (PostgreSQL 16), and **qdrant** (vector search)
* builds the app image with `BAKE_MODELS=true`, pre-downloading the FastEmbed embedding, sparse (BM25), and reranker models into the image so the first run starts fast
* maps port `8000` on your host to the app
* loads your keys from `.env`
* persists data in named volumes:
  * `pgdata` — PostgreSQL data
  * `qdrant_data` — Qdrant vector store
  * `research_data` — chats, documents, uploads (`/data`)
  * `fastembed_cache` — model downloads (`/home/appuser/.cache/fastembed`)

Useful commands:

```bash
docker compose logs -f            # follow the app logs
docker compose down               # stop the app (keeps your volumes)
docker compose down -v            # stop AND delete your data
docker compose pull               # pull a prebuilt image instead of building
```

> Building with `BAKE_MODELS=true` makes the image larger. Set it to `false` in `docker-compose.yml` to skip pre-downloading; models are then fetched on demand at runtime (the first retrieval will be slower).

### Option B — Run locally with uv

Requires Python 3.14+, [uv](https://docs.astral.sh/uv/), and running PostgreSQL and Qdrant instances.

```bash
git clone https://github.com/AbdelrhmanEbied/research-assistant.git
cd research-assistant

uv sync

cp .env.example .env
# fill in DATABASE_URL and your API keys

# start PostgreSQL and Qdrant (if not already running)
docker compose up -d postgres qdrant

uv run uvicorn app.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

> Prefer `uv` — the lockfile (`uv.lock`) pins exact versions. With pip you can install the project directly with `pip install .`.

Then open `http://127.0.0.1:8000` in your browser.

### Environment variables

Copy `.env.example` to `.env` and fill in your keys. None are strictly required to boot — set the keys for the providers you want to use:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant`) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `LLM_MODEL` | Default model (e.g. `gemini-3.5-flash-lite`) |
| `LLM_PROVIDER` | Default provider: `google_genai`, `openai`, or `anthropic` |
| `TAVILY_API_KEY` | Key for live web search |
| `TELEMETRY_ENABLED` | `true`/`false` to toggle the telemetry store |
| `TELEMETRY_DB_PATH` | Path to the telemetry SQLite file |
| `DATA_DIR` | Directory for runtime data (set to `/data` in Docker) |
| `ENVIRONMENT` | `development`, `staging`, `production`, … |
| `APP_VERSION` | Version tag recorded in telemetry |

Keys and defaults can also be changed at runtime from the **Settings** page — env vars only seed the defaults on first run.

## Configuration

Settings are managed from the **Settings** page in the UI and persisted to a local `settings.json` (gitignored because it may hold API keys). Environment variables only seed the defaults on first run.

* **Model** — default model and provider (Gemini, OpenAI, or Claude) and the matching API key
* **Web search** — results per query, pages fetched per task, and the Tavily search depth (basic, advanced)
* **RAG / retrieval** — search type (hybrid, dense, sparse), chunks per retrieval, reranking and rerank top-k
* **Agent** — recursion limit, max research iterations per plan, and the default response effort for new chats

### Using Thinking mode

1. Open the **Instant / Thinking** menu next to the Send button and pick **Thinking** (recommended for analysis, math, comparisons, and anything that benefits from step-by-step reasoning). Instant still uses the same tools — it only skips the analysis, verification and quality-review stages.
2. Send your message. The assistant streams its reasoning and tool activity live. The **Thinking** and execution panels start collapsed — click a header to expand it.
3. Thinking content is saved with the message and remains expandable when you reopen the conversation.

> Thinking mode works best with Gemini 3 models (which support `thinking_level` and `include_thoughts`). On other providers/models it degrades gracefully to a tool-enabled agent loop without a thought stream.

## Running tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests live in `tests/` and cover the agent graph (routing, plan skipping, streaming drafts, the `__start__` pseudo-node), RAG builders, retrieval and reranking, local tool execution, chat streaming (marker frames, event replay, error handling), routers, settings, evaluation, and telemetry.

## RAG evaluation

The `evaluation/` package scores the real retrieval and generation pipeline (`RAGService.prepare`) against labeled datasets. There are two layers:

* **Retrieval metrics** — offline, deterministic, no LLM calls: **hit rate@k, recall@k, precision@k, MRR, NDCG@k** against ground-truth chunk or document ids.
* **LLM-as-judge metrics** — **faithfulness** (is the answer grounded in the retrieved context?), **answer relevance**, and **context relevance**, scored by the app's own LLM providers via structured output. Requires configured API keys.

### Dataset format

A JSONL file with one `EvalItem` per line:

```json
{"query": "How does hybrid retrieval work?", "relevant_document_ids": ["hybrid_retrieval"]}
{"query": "What is attention?", "relevant_chunk_ids": ["c1", "c3"], "reference_answer": "..."}
```

Provide `relevant_chunk_ids`, `relevant_document_ids`, or both. `reference_answer` is optional and unused by the current judges. A runnable sample lives in `evaluation/sample_data/`.

### Running

```bash
# retrieval-only against a fresh corpus (indexed into a temp store)
uv run python scripts/evaluate_rag.py \
  --dataset evaluation/sample_data/example.jsonl \
  --corpus evaluation/sample_data/corpus \
  --search-types dense,sparse,hybrid --k 3

# against an existing indexed store
uv run python scripts/evaluate_rag.py --dataset my-data.jsonl --db-path ./qdrant_db

# add LLM-as-judge metrics (needs API keys; 1 generation + 3 judge calls per query)
uv run python scripts/evaluate_rag.py --dataset my-data.jsonl --corpus ./docs --judge \
  --judge-model gemini-3.5-flash-lite

# save the full JSON report
uv run python scripts/evaluate_rag.py --dataset data.jsonl --corpus ./docs --output report.json
```

Run `uv run python scripts/evaluate_rag.py --help` for all options.

### Baseline results

Run on `evaluation/sample_data/` (10 documents on overlapping topics, 20 queries with document- and chunk-level ground truth, top-k 3, no rerank). Chunk ids are deterministic (`uuid5` of `document_id:index`), so the chunk-level labels stay reproducible across runs. Full report: `evaluation/sample_data/REPORT.md` (+ raw JSON in `report.json`).

Document-level:

| search type | hit_rate | recall@3 | precision@3 | mrr | ndcg@3 |
|---|---|---|---|---|---|
| dense | 0.950 | 0.950 | 0.525 | 0.925 | 0.932 |
| sparse | 1.000 | 1.000 | 0.492 | 1.000 | 0.996 |
| hybrid | 1.000 | 1.000 | 0.525 | 0.950 | 0.959 |

Chunk-level:

| search type | hit_rate | recall@3 | precision@3 | mrr | ndcg@3 |
|---|---|---|---|---|---|
| dense | 0.950 | 0.950 | 0.367 | 0.900 | 0.909 |
| sparse | 1.000 | 0.975 | 0.367 | 1.000 | 0.936 |
| hybrid | 1.000 | 0.975 | 0.367 | 0.900 | 0.910 |

The numbers are high because the corpus is small and each query has at most two relevant documents, but they are no longer trivially perfect: the overlapping topics give the near-miss queries real discrimination. Sparse (BM25) is strong because the corpus uses distinctive technical terms that match verbatim. Dense misses one document-level query and has the lowest MRR, and hybrid recovers it — which is exactly why hybrid is the default. Chunk-level MRR/recall run slightly below document-level for every strategy: retrieval almost always finds the right document, but the exact chunk is pinpointed a little less often. `precision@3` stays low (~0.5 doc-level, ~0.37 chunk-level) because at most one or two of the three returned documents are relevant by construction; treat it as a capacity ceiling, not a regression.

## CI/CD

A GitHub Actions workflow (`.github/workflows/ci-cd.yaml`) runs on every push to `master`, `v*` tags, and all pull requests:

* **Lint & Test** — sets up Python 3.14 with `uv`, installs the locked dependencies, then runs `ruff check`, `ruff format --check`, and `pytest`.
* **RAG Evaluation** — after tests pass, runs the retrieval-only evaluation on the sample dataset/corpus and fails the build if `hit_rate` or `mrr` drop below 0.7.
* **Build & Push** — on pushes to `master` only (after lint/tests pass), builds the Docker image with BuildKit caching and `BAKE_MODELS=true` (so the embedding models ship inside the image) and pushes it to the GitHub Container Registry (`ghcr.io/<owner>/research-assistant`) tagged with the short commit SHA, `latest` on the default branch, and semver tags for `v*` releases.

## Credits

* Frontend by [geopero123](https://github.com/geopero123)
* Backend, agent, and RAG pipeline by [AbdelrhmanEbied](https://github.com/AbdelrhmanEbied)

## License

This project is licensed under the Apache License 2.0.

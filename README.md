# AI Migration Platform

> **Converts legacy Java monoliths into React + Spring Boot (Gradle) — automatically.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple.svg)](https://langchain-ai.github.io/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

The platform takes a Git repository URL for a legacy Java monolith and produces:

| Artifact | Technology | Build command |
|---------|-----------|--------------|
| React frontend | React 18 + TypeScript + Vite | `npm run build` |
| Spring Boot backend | Spring Boot 3.3 + Gradle | `./gradlew build` |
| Migration docs | Mermaid diagrams + BRD + plan PDF | — |

**What it handles automatically:**
- 4,400+ source files (Java, JSP, JS, XML, WSDL)
- Axis SOAP client detection → REST adapter or Spring WS replacement
- JDBC call detection → JPA entity + Repository generation
- JSP scriptlet extraction → Spring Boot `@Service` classes
- Dependency graph analysis → business module identification
- Multi-LLM validation (Claude + GPT-4o cross-check)

---

## Quick Start

### 1. Install

```bash
git clone <this-repo>
cd migration-platform
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and OPENAI_API_KEY
```

### 3. Start

```bash
./scripts/start.sh           # development (auto-reload)
./scripts/start.sh --prod    # production (4 workers)
```

The platform starts at `http://localhost:8000`. No Docker. No database servers. Zero additional processes.

### 4. Run tests

```bash
pytest tests/unit/ -v                    # unit tests (no API keys needed)
pytest tests/integration/ -v             # integration tests
pytest --cov=migration_platform          # with coverage
```

---

## Architecture Overview

```
User → UI (React) → FastAPI → LangGraph StateGraph
                                    │
              ┌─────────────────────┴──────────────────────┐
              │ Phase A — Analysis (no code written)        │
              │  1. RepoAgent      clone + scan             │
              │  2. ParserAgent    chunk + embed (×20)      │
              │  3. GraphAgent     NetworkX + Louvain       │
              │  4. IntegrationAgent  SOAP + JDBC detect    │
              │  5. ArchitectureAgent  bounded contexts     │
              │  6. PlannerAgent   roadmap + BRD            │
              └──────────────┬─────────────────────────────┘
                             │
                    ⛔ HUMAN APPROVAL GATE
                    (LangGraph interrupt_before)
                    Review diagrams → Download → Approve
                             │
              ┌──────────────┴──────────────────────────────┐
              │ Phase B — Code Generation (post-approval)    │
              │  7. ValidationAgent  Claude + GPT-4o check  │
              │  8. CodeGenAgent     React + Spring (×8)    │
              │  9. TestingAgent     gradlew + npm verify   │
              └─────────────────────────────────────────────┘
```

Full architecture details, Mermaid diagrams, and data flow documentation: [`docs/architecture.md`](docs/architecture.md)

Sequence diagrams for all flows: [`docs/sequence_diagram.md`](docs/sequence_diagram.md)

---

## In-Memory Data Layer (No Enterprise DB Needed)

| Role | Package | Replaces |
|------|---------|---------|
| Dependency graph | `networkx` + `python-louvain` | Neo4j |
| Vector store | `chromadb` EphemeralClient | Qdrant |
| State + metadata | `duckdb` `:memory:` | PostgreSQL |
| Cache | `diskcache` | Redis |

All stores persist to local files (`./data/`) for restart resilience. No server approvals required.

---

## API Reference

### Start a migration

```bash
curl -X POST http://localhost:8000/api/migrations \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/example/legacy-app"}'
# → {"migration_id": "abc-123", "status": "started"}
```

### Check status

```bash
curl http://localhost:8000/api/migrations/abc-123
# → {"status": "awaiting_approval", "progress_pct": 80.0, ...}
```

### Get artifacts for review (before approving)

```bash
curl http://localhost:8000/api/migrations/abc-123/artifacts
# → {"diagrams": [...], "migration_plan": {...}, "soap_report": {...}}
```

### Approve (triggers Phase B — code generation)

```bash
curl -X POST http://localhost:8000/api/migrations/abc-123/approve \
  -H "Content-Type: application/json" \
  -d '{"status": "approved", "comment": "LGTM"}'
```

### Reject (triggers plan regeneration)

```bash
curl -X POST http://localhost:8000/api/migrations/abc-123/approve \
  -H "Content-Type: application/json" \
  -d '{"status": "rejected", "comment": "SOAP options incomplete"}'
```

### Live progress (WebSocket)

```javascript
const ws = new WebSocket("ws://localhost:8000/api/migrations/abc-123/ws");
ws.onmessage = (e) => {
    const { phase, progress_pct } = JSON.parse(e.data);
    console.log(`Phase: ${phase} — ${progress_pct}%`);
};
```

---

## Project Structure

```
migration-platform/
├── pyproject.toml                  ← hatchling build, all deps pinned
├── .env.example                    ← copy to .env
├── scripts/start.sh                ← single-command startup
├── src/migration_platform/
│   ├── main.py                     ← FastAPI app factory
│   ├── config/settings.py          ← pydantic-settings (all env vars)
│   ├── core/
│   │   ├── exceptions.py           ← HTTP-aware exception hierarchy
│   │   └── logging.py              ← structlog (JSON in prod)
│   ├── domain/
│   │   ├── models/migration.py     ← FileType, ChunkType, CodeChunk
│   │   └── schemas/                ← Pydantic v2 request/response models
│   ├── agents/                     ← 9 specialized agents (BaseAgent)
│   ├── codegen/                    ← ContextBuilder, GradleScaffold, generators
│   ├── parsers/                    ← Java (javalang), JSP, JS, XML
│   ├── graph/graph_store.py        ← GraphStore: NetworkX + Louvain
│   ├── rag/
│   │   ├── embedder.py             ← OpenAI text-embedding-3-large
│   │   ├── vector_store.py         ← VectorStore: ChromaDB cosine HNSW
│   │   └── retriever.py            ← token-budget hybrid retrieval
│   ├── storage/
│   │   ├── state_store.py          ← StateStore: DuckDB
│   │   └── cache_store.py          ← CacheStore: diskcache
│   ├── workflows/
│   │   ├── state.py                ← MigrationState TypedDict
│   │   └── migration_graph.py      ← LangGraph StateGraph + MemorySaver
│   ├── api/routes/migration.py     ← REST endpoints + WebSocket
│   └── prompts/templates.py        ← all LLM system prompts
├── docs/
│   ├── architecture.md             ← full architecture + 8 Mermaid diagrams
│   └── sequence_diagram.md         ← 7 detailed sequence diagrams
└── tests/
    ├── conftest.py                 ← shared fixtures + env stubs
    ├── unit/                       ← GraphStore, StateStore, VectorStore, parsers
    └── integration/test_workflow.py ← graph compile + approval routing
```

---

## Enterprise Patterns Used

| Pattern | Where Applied |
|---------|--------------|
| **Strategy** | `BaseParser` + `ParserRegistry` — each file type has its own parser |
| **Template Method** | `BaseAgent._call_llm_json()` — all agents share LLM retry logic |
| **Factory** | `build_migration_graph()` — constructs the entire dependency graph in one place |
| **Repository** | `StateStore`, `VectorStore`, `GraphStore` — all data access behind interfaces |
| **Dependency Injection** | Agents receive store instances via constructor; no global singletons in agent code |
| **State Machine** | LangGraph `StateGraph` — explicit nodes, edges, and conditional routing |
| **Circuit Breaker** | `tenacity` retry with exponential backoff on all LLM calls |
| **Observer** | WebSocket push for live progress — UI never polls |

---

## Configuration Reference

All configuration is via environment variables (`.env` file). See `.env.example` for full list.

| Variable | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | **required** | Claude API key |
| `OPENAI_API_KEY` | **required** | GPT-4o + embeddings key |
| `PRIMARY_MODEL` | `claude-sonnet-4-5` | Primary LLM for code gen |
| `MAX_CONTEXT_TOKENS` | `6000` | Hard token limit per LLM call |
| `PARSER_MAX_WORKERS` | `20` | Parallel file embedding threads |
| `CODEGEN_MAX_WORKERS` | `8` | Parallel module code gen threads |
| `DUCKDB_PATH` | `./data/migration.duckdb` | State persistence (`:memory:` for tests) |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Vector store persistence |

---

## License

MIT — see [LICENSE](LICENSE)

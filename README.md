# Agent Query Engine

[![API Tests](https://github.com/Yukigeshiki/agent-query-engine-python/actions/workflows/api-tests.yml/badge.svg)](https://github.com/Yukigeshiki/agent-query-engine-python/actions/workflows/api-tests.yml)
[![API Build](https://github.com/Yukigeshiki/agent-query-engine-python/actions/workflows/api-build.yml/badge.svg)](https://github.com/Yukigeshiki/agent-query-engine-python/actions/workflows/api-build.yml)
[![UI Build](https://github.com/Yukigeshiki/agent-query-engine-python/actions/workflows/ui-build.yml/badge.svg)](https://github.com/Yukigeshiki/agent-query-engine-python/actions/workflows/ui-build.yml)

A document ingestion and query engine built with Python and FastAPI. Upload documents (PDF, DOCX, TXT), extract knowledge graph triplets and vector embeddings, then query across both using natural language. Documents are stored in GCS, processed asynchronously via Celery, and indexed into Neo4j (knowledge graph) and pgvector (vector embeddings). The UI provides document upload with interactive graph visualization and a query interface with retrieval mode selection.

## How It Works

1. **Upload** — a document is uploaded through the UI, streamed to GCS, and a Celery task is dispatched for async processing
2. **Ingestion** — the document is chunked via LlamaIndex's SentenceSplitter, embedded via OpenAI, and triplet-extracted into Neo4j; vector embeddings are stored in pgvector; all metadata is preserved in the docstore for display
3. **Query** — users ask natural language questions with three retrieval modes:
   - **Dual** (default) — merges knowledge graph traversal + vector similarity, deduplicates by node ID, and synthesizes a response from both sources
   - **KG Only** — graph traversal through Neo4j entity relationships
   - **Vector Only** — cosine similarity search over embeddings in pgvector
4. **Caching** — query results are semantically cached using pgvector similarity search + Redis payload storage; similar questions hit the cache instead of re-running the LLM

## Prerequisites

- Python 3.13+ and [Poetry](https://python-poetry.org/)
- Docker
- Node.js + pnpm
- `OPENAI_API_KEY` environment variable
- `GCS_CREDENTIALS_JSON` environment variable

Export these before running (add to `~/.zshrc` or equivalent):

```bash
export OPENAI_API_KEY='your-openai-api-key'
export GCS_CREDENTIALS_JSON='{"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}'
```

`OPENAI_API_KEY` is required for LlamaIndex embeddings and LLM calls. `GCS_CREDENTIALS_JSON` is the full GCS service account key JSON as a single line — required for document uploads. Without it, the API starts but upload is disabled.

## Getting Started

### Infrastructure + Worker

```bash
docker compose up -d
```

Starts Neo4j, PostgreSQL (with pgvector), Redis, the Celery worker, and the Celery beat scheduler.

### Backend

```bash
cd services/query-engine
cp .env.example .env       # configure GCS bucket, connection strings
poetry install
poetry run uvicorn app.main:create_app --factory --reload
```

### UI

```bash
cd ui
pnpm install
pnpm dev  # port 5173
```

The UI provides a query page for asking questions about your documents and an upload page with drag-and-drop file upload and interactive Cytoscape.js knowledge graph visualization per document.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────┐
│   Vue 3 UI  │────>│  FastAPI Backend  │────>│  Neo4j  │
└─────────────┘     └──────┬───────────┘     └─────────┘
                           │                  ┌──────────┐
                           ├─────────────────>│ pgvector │
                           │                  └──────────┘
                    ┌──────┴───────┐          ┌─────────┐
                    │ Celery Worker│────>─────>│   GCS   │
                    └──────┬───────┘          └─────────┘
                           │                  ┌─────────┐
                           └─────────────────>│  Redis  │
                                              └─────────┘
```

- **FastAPI** — API server with rate limiting, request tracing, Prometheus metrics
- **Celery Worker** — async document ingestion (chunking, embedding, triplet extraction)
- **Celery Beat** — scheduled cleanup of expired GCS uploads (24h TTL)
- **Neo4j** — knowledge graph storage (entity-relationship triplets)
- **PostgreSQL/pgvector** — vector embeddings, docstore, index store, semantic query cache
- **Redis** — Celery broker, rate limiting, cache payloads
- **GCS** — document upload storage

## Project Structure

```
services/query-engine/   Python, FastAPI, LlamaIndex, Celery, Poetry
ui/                      Vue 3, TypeScript, Vite, Tailwind CSS, Cytoscape.js
docker-compose.yml       Neo4j, PostgreSQL, Redis, Celery worker + beat
```

## API

All endpoints are under `/api/v1`. Swagger docs available at http://localhost:8000/docs (debug mode only).

### Query

```bash
curl -X POST http://localhost:8000/api/v1/kg/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "What does Alice do?", "retrievalMode": "dual"}'
```

### Upload

```bash
curl -X POST http://localhost:8000/api/v1/kg/ingest/upload \
  -F 'file=@document.pdf'
```

### Key Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/kg/query` | Query documents with natural language |
| POST | `/kg/ingest/upload` | Upload a file for async ingestion |
| GET | `/kg/documents` | List ingested documents (paginated) |
| GET | `/kg/documents/graph` | Get knowledge graph for a document |
| GET | `/kg/subgraph` | Get subgraph around an entity |
| GET | `/tasks/{taskId}` | Poll background task status |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |

## Build Commands

**Backend** (from `services/query-engine/`):

```bash
poetry install          # install dependencies
poetry run pytest       # run tests
poetry run uvicorn app.main:create_app --factory --reload  # run
```

**UI** (from `ui/`):

```bash
pnpm install    # install dependencies
pnpm dev        # dev server
pnpm build      # production build
```
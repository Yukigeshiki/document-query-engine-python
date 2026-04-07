# Document Query Engine

[![API Tests](https://github.com/Yukigeshiki/document-query-engine-python/actions/workflows/api-tests.yml/badge.svg)](https://github.com/Yukigeshiki/document-query-engine-python/actions/workflows/api-tests.yml)
[![API Build](https://github.com/Yukigeshiki/document-query-engine-python/actions/workflows/api-build.yml/badge.svg)](https://github.com/Yukigeshiki/document-query-engine-python/actions/workflows/api-build.yml)
[![UI Build](https://github.com/Yukigeshiki/document-query-engine-python/actions/workflows/ui-build.yml/badge.svg)](https://github.com/Yukigeshiki/document-query-engine-python/actions/workflows/ui-build.yml)

A document ingestion and query engine built with Python/FastAPI, LlamaIndex, Neo4j, and pgvector. Upload documents (PDF, DOCX, TXT), extract knowledge graph triplets and vector embeddings, then query across both using natural language. LlamaIndex orchestrates the full pipeline - chunking documents, extracting entity-relationship triplets via OpenAI into Neo4j, embedding chunks into pgvector, and synthesizing answers from dual retrieval (graph traversal + vector similarity). Documents are stored in GCS and processed asynchronously via Celery. The UI provides testing for document upload with interactive graph visualization, a query interface with retrieval mode selection, and document deletion.

## How It Works

1. **Upload** - a document is uploaded, streamed to GCS, and a Celery task is dispatched for async processing
2. **Ingestion** - the document is chunked via LlamaIndex's SentenceSplitter, embedded via OpenAI, and triplet-extracted into Neo4j with `source_node_ids` provenance tracking on each relationship; vector embeddings are stored in pgvector; all metadata is preserved in the docstore for display
3. **Query** - users ask natural language questions with three retrieval modes:
   - **Dual** (default) - merges knowledge graph traversal + vector similarity, deduplicates by node ID, and synthesizes a response from both sources
   - **KG Only** - graph traversal through Neo4j entity relationships
   - **Vector Only** - cosine similarity search over embeddings in pgvector
4. **Caching** - query results are semantically cached using pgvector similarity search + Redis payload storage; similar questions hit the cache instead of re-running the LLM

## Prerequisites

- Python 3.12+ and [Poetry](https://python-poetry.org/)
- Docker
- Node.js + pnpm
- `OPENAI_API_KEY` environment variable
- `GCS_CREDENTIALS_JSON` environment variable

Export these before running (add to `~/.zshrc` or equivalent):

```bash
export OPENAI_API_KEY='your-openai-api-key'
export GCS_CREDENTIALS_JSON='{"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}'
```

`OPENAI_API_KEY` is required for LlamaIndex embeddings and LLM calls. `GCS_CREDENTIALS_JSON` is the full GCS service account key JSON as a single line - required for document uploads. Without it, the API starts but upload is disabled.

## Getting Started

### Docker Compose (full stack)

```bash
# Start everything - databases, worker, API, and UI
docker compose --profile all up -d
```

This builds and runs all services:
- API at http://localhost:8000
- UI at http://localhost:5173
- Neo4j, PostgreSQL (pgvector), Redis, Celery worker + beat

To start only the databases, worker, and beat scheduler:

```bash
docker compose up -d
```

### Local development

#### Backend

```bash
cd services/query-engine
cp .env.example .env       # configure GCS bucket, connection strings
poetry install
poetry run uvicorn app.main:create_app --factory --reload
```

#### UI

```bash
cd ui
pnpm install
pnpm dev  # port 5173
```

The UI provides a query page for asking questions about your documents and an upload page with drag-and-drop file upload and interactive Cytoscape.js knowledge graph visualization per document.

## Architecture

- **FastAPI** - API server with rate limiting, request tracing, Prometheus metrics
- **Celery Worker** - async document ingestion (chunking, embedding, triplet extraction) and deletion (precise removal using `source_node_ids` provenance)
- **Celery Beat** - scheduled cleanup of expired GCS uploads (24h TTL)
- **Neo4j** - knowledge graph storage (entity-relationship triplets)
- **PostgreSQL/pgvector** - vector embeddings, docstore, index store, semantic query cache
- **Redis** - Celery broker, rate limiting, cache payloads
- **GCS** - document upload storage

### Scaling the worker

The Celery worker uses the prefork pool with process-level concurrency. Each worker process has its own KG service, Neo4j driver, postgres engine, and LlamaIndex indexes - process isolation gives crash isolation and avoids races in LlamaIndex internals.

- **Vertical** - tune the `CELERY_WORKER_CONCURRENCY` env var (default `4`) to change the number of worker processes per container. `WORKER_MAX_TASKS_PER_CHILD` (default `100`) recycles processes to bound memory leaks.
- **Horizontal** - run multiple worker containers behind the same Redis broker.

Tasks use `task_acks_late` + `task_reject_on_worker_lost`, so a task is redelivered to another worker if its worker crashes mid-execution.

## Project Structure

```
services/query-engine/   Python, FastAPI, LlamaIndex, Celery, Poetry
ui/                      Vue 3, TypeScript, Vite, Tailwind CSS, Cytoscape.js
docker-compose.yml       Neo4j, PostgreSQL, Redis, Celery worker + beat (local dev)
.github/workflows/       CI: API tests, API build, UI build
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
| POST | `/kg/ingest/upload` | Upload a file for async ingestion (max 5MB) |
| POST | `/kg/ingest/source` | Ingest from a source connector (async) |
| GET | `/kg/documents` | List ingested documents (paginated, newest first) |
| DELETE | `/kg/documents/{docId}` | Delete a document from all storage layers |
| GET | `/kg/documents/graph` | Get knowledge graph for a document |
| GET | `/kg/subgraph` | Get subgraph around an entity |
| GET | `/tasks/{taskId}` | Poll background task status |
| DELETE | `/tasks/{taskId}` | Cancel a background task |
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
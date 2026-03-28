# Agent Query Engine

A document ingestion and query engine. Upload documents (PDF, DOCX, TXT), extract knowledge graph triplets and vector embeddings, then query across both using natural language.

## How It Works

1. **Upload** a document through the UI or API
2. The document is **chunked**, **embedded** (pgvector), and **triplet-extracted** (Neo4j) via LlamaIndex + OpenAI
3. **Query** your documents using natural language with three retrieval modes:
   - **Dual** (default) — combines knowledge graph traversal + vector similarity
   - **KG Only** — graph traversal through Neo4j relationships
   - **Vector Only** — cosine similarity search over embeddings

## Stack

**Backend** — FastAPI, LlamaIndex, Celery, PostgreSQL/pgvector, Neo4j, Redis

**Frontend** — Vue 3, TypeScript, Tailwind CSS, Cytoscape.js

## Project Structure

```
services/query-engine/   # FastAPI backend + Celery worker
ui/                      # Vue 3 frontend
docker-compose.yml       # Neo4j, PostgreSQL, Redis
```

## Running Locally

### Infrastructure

```bash
docker compose up -d
```

Starts Neo4j, PostgreSQL (with pgvector), and Redis.

### Backend

```bash
cd services/query-engine
cp .env.example .env       # configure OpenAI key, connection strings
poetry install
poetry run uvicorn app.main:create_app --factory --reload
```

### Worker

```bash
cd services/query-engine
poetry run celery -A app.worker.celery_app worker --loglevel=info
```

### Frontend

```bash
cd ui
pnpm install
pnpm dev
```

Open http://localhost:5173

## API

All endpoints are under `/api/v1/kg/`. Key routes:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest/upload` | Upload a file for async ingestion |
| POST | `/query` | Query documents with natural language |
| GET | `/documents` | List ingested documents (paginated) |
| GET | `/documents/graph` | Get knowledge graph for a document |
| GET | `/subgraph` | Get subgraph around an entity |
| GET | `/tasks/{taskId}` | Poll background task status |

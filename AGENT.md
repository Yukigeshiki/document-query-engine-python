# Agent Query Engine - Agent Guidelines

## Project Overview

FastAPI backend service that exposes a LlamaIndex Knowledge Graph query engine over HTTPS. Called by a Kotlin LangGraph4j agent as a tool. Neo4j is the graph store.

## Tech Stack

- **Framework**: FastAPI + Uvicorn
- **Validation**: Pydantic + Pydantic-Settings
- **Logging**: Structlog (JSON in prod, console in debug)
- **KG Engine**: LlamaIndex (KnowledgeGraphIndex)
- **Graph Store**: Neo4j (via llama-index-graph-stores-neo4j)
- **Build**: Poetry 2.3+
- **Linting**: Ruff
- **Type Checking**: mypy (strict mode)
- **Testing**: pytest + pytest-asyncio + httpx

## Project Structure

```
app/
├── api/v1/          # API route handlers
├── connectors/      # Document source connectors (filesystem, GCS)
├── core/            # Config (Pydantic Settings), logging, errors, middleware
├── models/          # Pydantic request/response schemas (CamelModel base)
├── services/        # Business logic (KnowledgeGraphService, IngestionPipeline)
└── worker/          # Celery app, background tasks
tests/               # Pytest test suite
```

## Commands

```bash
# Install dependencies
poetry install

# Run development server
poetry run uvicorn app.main:app --reload

# Run tests
poetry run pytest

# Lint
poetry run ruff check .

# Format
poetry run ruff format .

# Type check
poetry run mypy .

# Run Celery worker
poetry run celery -A app.worker.celery_app:celery_app worker --loglevel=info
```

## Code Conventions

- **Line length**: 100 characters
- **Type hints**: Required on all functions (strict mypy)
- **Modern Python syntax**: Use `list[str]` not `List[str]`, etc.
- **Imports**: Always at the top of the file, sorted by isort (via ruff). No inline imports unless absolutely necessary.
- **API routes**: Use `APIRouter`, grouped under `api/v1/`
- **Models**: Inherit from `CamelModel` (in `app/models/__init__.py`), not `BaseModel` directly. JSON serialization is camelCase for the Kotlin agent; Python code stays snake_case. Use `by_alias=True` when calling `model_dump()` manually.
- **Config**: Environment variables loaded via Pydantic-Settings from `.env`
- **Logging**: Use structlog, not `print()` or stdlib `logging` directly
- **Docstrings**: PEP 257 — all public modules, classes, functions, and methods must have docstrings. Use triple double quotes. One-line for simple cases, multi-line with summary + blank line + description for complex ones.

## Testing

- Tests live in `tests/` mirroring the app structure
- Use `pytest-asyncio` with mode `auto`
- Use `httpx.AsyncClient` with `ASGITransport` for endpoint tests
- Fixtures defined in `tests/conftest.py`

## Docker

```bash
docker build -t agent-query-engine .
docker run -p 8000:8000 agent-query-engine
```

Multi-stage Dockerfile: base → builder (Poetry install) → runtime (minimal image).

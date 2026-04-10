"""Integration test fixtures with real backing stores via testcontainers.

Starts Neo4j, PostgreSQL (pgvector), and Redis containers once per session.
Uses LlamaIndex MockLLM/MockEmbedding to avoid OpenAI API costs.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from llama_index.core.embeddings.mock_embed_model import MockEmbedding
from llama_index.core.llms.mock import MockLLM
from testcontainers.neo4j import Neo4jContainer  # type: ignore[import-untyped]
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
from testcontainers.redis import RedisContainer  # type: ignore[import-untyped]

from app.core.config import Settings
from app.core.postgres import get_pg_engine
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.query_cache import create_query_cache

# Deterministic triplet response for the extractor.
# MockLLM echoes the formatted prompt, so we patch predict() to return this.
_TRIPLET_RESPONSE = (
    "(Alice, works at, Acme Corp)\n"
    "(Acme Corp, located in, New York)\n"
)

# Deterministic keyword response for the retriever.
_KEYWORD_RESPONSE = "KEYWORDS: Alice, Acme Corp"


class _TestLLM(MockLLM):
    """MockLLM that returns deterministic triplet/keyword responses."""

    def predict(self, prompt: Any, **kwargs: Any) -> str:
        """Return triplets or keywords based on the prompt content."""
        formatted = prompt.format(**kwargs) if hasattr(prompt, "format") else str(prompt)
        if "triplets" in formatted.lower():
            return _TRIPLET_RESPONSE
        if "keywords" in formatted.lower():
            return _KEYWORD_RESPONSE
        return formatted


@pytest.fixture(scope="session")
def neo4j_container() -> Iterator[Any]:
    """Start a Neo4j container for the test session."""
    with Neo4jContainer("neo4j:5.26").with_env(
        "NEO4J_PLUGINS", '["apoc"]'
    ).with_env(
        "NEO4J_dbms_security_procedures_unrestricted", "apoc.*"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    """Start a PostgreSQL + pgvector container for the test session."""
    with PostgresContainer(
        "pgvector/pgvector:pg16",
        dbname="test_query_engine",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Iterator[Any]:
    """Start a Redis container for the test session."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def integration_config(
    neo4j_container: Any,
    postgres_container: Any,
    redis_container: Any,
) -> Settings:
    """Build a Settings object pointing at the testcontainers."""
    neo4j_host = neo4j_container.get_container_host_ip()
    neo4j_port = neo4j_container.get_exposed_port(7687)

    pg_host = postgres_container.get_container_host_ip()
    pg_port = postgres_container.get_exposed_port(5432)

    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)

    return Settings(
        openai_api_key="fake-key",
        llm_model="gpt-4o-mini",
        llm_temperature=0,
        embedding_model="text-embedding-3-small",
        neo4j_uri=f"bolt://{neo4j_host}:{neo4j_port}",
        neo4j_username="neo4j",
        neo4j_password="password",
        neo4j_database="neo4j",
        postgres_uri=(
            f"postgresql://test:test@{pg_host}:{pg_port}/test_query_engine"
        ),
        postgres_enabled=True,
        embed_dim=1536,
        vector_top_k=10,
        max_triplets_per_chunk=10,
        chunk_size=1024,
        celery_broker_url=f"redis://{redis_host}:{redis_port}/0",
        cache_ttl_seconds=3600,
        cache_similarity_threshold=0.95,
    )


@pytest.fixture(scope="session")
def kg_service(
    integration_config: Settings,
) -> Iterator[KnowledgeGraphService]:
    """
    Build a real KnowledgeGraphService with mock LLM/embeddings.

    Overrides LlamaIndex global Settings with MockLLM and MockEmbedding
    before constructing the service, then restores them after the session.
    """
    test_llm = _TestLLM(max_tokens=256)
    test_embed = MockEmbedding(embed_dim=1536)

    # Patch the OpenAI/OpenAIEmbedding constructors so the service __init__
    # stores our mocks in Settings.llm / Settings.embed_model. The
    # VectorStoreIndex captures the embed model at creation time, so we
    # must intercept before the service is constructed.
    with (
        patch(
            "app.services.knowledge_graph.OpenAI",
            return_value=test_llm,
        ),
        patch(
            "app.services.knowledge_graph.OpenAIEmbedding",
            return_value=test_embed,
        ),
    ):
        pg_engine = get_pg_engine(integration_config.postgres_uri)
        cache = create_query_cache(integration_config, engine=pg_engine)

        service = KnowledgeGraphService(
            config=integration_config,
            cache=cache,
            engine=pg_engine,
        )

        yield service

        service.close()

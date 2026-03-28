"""Tests for the semantic query cache."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.knowledge_graph import ResponseMode, RetrievalMode, SourceNodeInfo, SourceNodeMetadata
from app.services.query_cache import QueryCache


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create a mock Redis client."""
    return MagicMock()


@pytest.fixture
def mock_pg_conn() -> MagicMock:
    """Create a mock PostgreSQL connection."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


@pytest.fixture
def cache(mock_redis: MagicMock, mock_pg_conn: MagicMock) -> QueryCache:
    """Create a QueryCache with mocked backends."""
    with (
        patch("app.services.query_cache.redis.Redis.from_url", return_value=mock_redis),
        patch(
            "app.services.query_cache.psycopg2.pool.ThreadedConnectionPool"
        ) as mock_pool_cls,
    ):
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_pg_conn
        mock_pool_cls.return_value = mock_pool

        c = QueryCache(
            redis_url="redis://fake:6379/0",
            postgres_uri="postgresql://fake:5432/db",
            ttl=3600,
            threshold=0.95,
            embed_dim=1536,
        )
        return c


class TestQueryCache:
    """Tests for QueryCache semantic lookup."""

    def test_cache_miss_returns_none(
        self, cache: QueryCache, mock_pg_conn: MagicMock
    ) -> None:
        """Verify None returned when no similar query exists."""
        cursor = mock_pg_conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        embedding = [0.1] * 1536
        result = cache.get("test query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL, embedding=embedding)
        assert result is None

    def test_cache_hit_returns_result(
        self,
        cache: QueryCache,
        mock_redis: MagicMock,
        mock_pg_conn: MagicMock,
    ) -> None:
        """Verify cached result returned when similar query found."""
        cursor = mock_pg_conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("abc123", 0.97)

        payload = json.dumps({
            "response_text": "Alice works at Acme.",
            "source_nodes": [{"text": "source", "score": 0.9, "metadata": {}}],
        })
        mock_redis.get.return_value = payload.encode()

        embedding = [0.1] * 1536
        result = cache.get("test query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL, embedding=embedding)

        assert result is not None
        response_text, source_nodes, returned_embedding = result
        assert response_text == "Alice works at Acme."
        assert len(source_nodes) == 1
        assert source_nodes[0].score == 0.9
        assert returned_embedding is embedding

    def test_cache_miss_below_threshold(
        self, cache: QueryCache, mock_pg_conn: MagicMock
    ) -> None:
        """Verify None returned when similarity is below threshold."""
        cursor = mock_pg_conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("abc123", 0.90)

        embedding = [0.1] * 1536
        result = cache.get("test query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL, embedding=embedding)
        assert result is None

    @patch("app.services.query_cache.QueryCache.embed_query")
    def test_cache_set_stores_embedding_and_payload(
        self,
        mock_embed: MagicMock,
        cache: QueryCache,
        mock_redis: MagicMock,
        mock_pg_conn: MagicMock,
    ) -> None:
        """Verify set stores embedding in PG and payload in Redis."""
        mock_embed.return_value = [0.1] * 1536

        source_nodes = [SourceNodeInfo(score=0.9, metadata=SourceNodeMetadata())]
        cache.set("test query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL, "response", source_nodes)

        cursor = mock_pg_conn.cursor.return_value.__enter__.return_value
        cursor.execute.assert_called()
        mock_redis.setex.assert_called_once()

    @patch("app.services.query_cache.QueryCache.embed_query")
    def test_cache_set_reuses_provided_embedding(
        self,
        mock_embed: MagicMock,
        cache: QueryCache,
        mock_redis: MagicMock,
        mock_pg_conn: MagicMock,
    ) -> None:
        """Verify set skips embedding API call when embedding is provided."""
        pre_computed = [0.2] * 1536
        source_nodes = [SourceNodeInfo(score=0.9, metadata=SourceNodeMetadata())]
        cache.set(
            "test query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL,
            "response", source_nodes, embedding=pre_computed,
        )

        mock_embed.assert_not_called()
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_invalidate_clears_both(
        self, cache: QueryCache, mock_redis: MagicMock, mock_pg_conn: MagicMock
    ) -> None:
        """Verify invalidate clears PG table and Redis keys."""
        mock_redis.scan_iter.return_value = [b"query_cache:abc", b"query_cache:def"]

        await cache.invalidate()

        cursor = mock_pg_conn.cursor.return_value.__enter__.return_value
        cursor.execute.assert_called()
        assert mock_redis.delete.call_count == 2

    def test_cache_graceful_on_failure(self, cache: QueryCache) -> None:
        """Verify None returned when embedding fails."""
        result = cache.get(
            "test query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL,
            embedding=None,  # will try to call embed_query which uses real Settings
        )
        # Should gracefully return None (Settings.embed_model not configured in tests)
        assert result is None

    def test_cache_key_varies_by_params(self) -> None:
        """Verify different params produce different cache keys."""
        key1 = QueryCache._make_cache_key("query", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL)
        key2 = QueryCache._make_cache_key("query", False, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL)
        key3 = QueryCache._make_cache_key("query", True, ResponseMode.COMPACT, RetrievalMode.DUAL)
        key4 = QueryCache._make_cache_key("different", True, ResponseMode.TREE_SUMMARIZE, RetrievalMode.DUAL)

        assert len({key1, key2, key3, key4}) == 4

    def test_cache_check_health(
        self, cache: QueryCache, mock_redis: MagicMock, mock_pg_conn: MagicMock
    ) -> None:
        """Verify health check returns ok when both backends respond."""
        mock_redis.ping.return_value = True
        result = cache.check_health()
        assert result["status"] == "ok"
        assert result["backend"] == "redis+pgvector"

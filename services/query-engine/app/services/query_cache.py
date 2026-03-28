"""Semantic query cache using pgvector for similarity search and Redis for payloads."""

import asyncio
import hashlib
import json
from collections.abc import Generator
from contextlib import contextmanager

import psycopg2  # type: ignore[import-untyped]
import psycopg2.pool  # type: ignore[import-untyped]
import redis
import structlog
from llama_index.core import Settings
from psycopg2 import Error as PgError
from psycopg2.extensions import connection as pg_connection  # type: ignore[import-untyped]

from app.core.config import Settings as AppSettings
from app.core.metrics import kg_cache_invalidations_total, kg_cache_similarity_score
from app.models.knowledge_graph import ResponseMode, RetrievalMode, SourceNodeInfo

logger = structlog.stdlib.get_logger(__name__)

CACHE_KEY_PREFIX = "query_cache:"
TABLE_NAME = "query_cache_embeddings"


class QueryCache:
    """
    Semantic cache for KG query results.

    Embeds query text and searches for similar cached queries by cosine
    similarity in pgvector, filtered by query parameters. Response
    payloads are stored in Redis with TTL. Uses connection pooling for
    PostgreSQL to avoid per-operation connection overhead.
    """

    def __init__(
        self,
        redis_url: str,
        postgres_uri: str,
        ttl: int,
        threshold: float,
        embed_dim: int,
    ) -> None:
        self._ttl = ttl
        self._threshold = threshold
        self._embed_dim = embed_dim
        self._redis = redis.Redis.from_url(redis_url)
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=5, dsn=postgres_uri
        )
        self._ensure_table()

    @contextmanager
    def _pg_conn(self) -> Generator[pg_connection, None, None]:
        """
        Get a pooled PG connection, replacing stale connections automatically.

        psycopg2 marks connections as closed when the server drops them
        (e.g. after a PostgreSQL restart). We check before yielding, so
        callers never see a dead connection and discard any that break
        mid-use so the pool replaces them on the next call.
        """
        conn = self._pool.getconn()
        if conn.closed:
            self._pool.putconn(conn, close=True)
            conn = self._pool.getconn()
        try:
            yield conn
        finally:
            if conn.closed:
                self._pool.putconn(conn, close=True)
            else:
                self._pool.putconn(conn)

    def _ensure_table(self) -> None:
        """Create the cache embeddings table and index if they don't exist."""
        try:
            with self._pg_conn() as conn:
                with conn.cursor() as cur:
                    # pgvector extension should be pre-installed in production.
                    # This handles dev/Docker where the app user has superuser rights.
                    try:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    except PgError:
                        conn.rollback()
                        logger.info(
                            "pgvector_extension_not_created_assuming_pre_installed"
                        )
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                            id SERIAL PRIMARY KEY,
                            cache_key TEXT UNIQUE NOT NULL,
                            include_text BOOLEAN NOT NULL,
                            response_mode TEXT NOT NULL,
                            retrieval_mode TEXT NOT NULL,
                            query_embedding vector({self._embed_dim})
                        )
                    """)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_embedding
                        ON {TABLE_NAME}
                        USING hnsw (query_embedding vector_cosine_ops)
                    """)
                conn.commit()
            logger.info("query_cache_table_ready")
        except Exception as exc:
            logger.warning("query_cache_table_setup_failed", error=str(exc))

    def _delete_embedding(self, cache_key: str) -> None:
        """Remove an orphaned embedding row whose Redis payload has expired."""
        try:
            with self._pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {TABLE_NAME} WHERE cache_key = %s",
                        (cache_key,),
                    )
                conn.commit()
            logger.info("query_cache_orphan_cleaned", cache_key=cache_key[:12])
        except Exception as exc:
            logger.warning("query_cache_orphan_cleanup_failed", error=str(exc))

    @staticmethod
    def _make_cache_key(
        query_text: str,
        include_text: bool,
        response_mode: ResponseMode,
        retrieval_mode: RetrievalMode,
    ) -> str:
        """Generate a deterministic cache key from query parameters."""
        raw = f"{query_text}:{include_text}:{response_mode}:{retrieval_mode}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def embed_query(query_text: str) -> list[float]:
        """Generate an embedding for query text."""
        return Settings.embed_model.get_query_embedding(query_text)

    @staticmethod
    def _embedding_to_str(embedding: list[float]) -> str:
        """Convert embedding list to pgvector string format."""
        return "[" + ",".join(str(v) for v in embedding) + "]"

    def get(
        self,
        query_text: str,
        include_text: bool,
        response_mode: ResponseMode,
        retrieval_mode: RetrievalMode,
        embedding: list[float] | None = None,
    ) -> tuple[str, list[SourceNodeInfo], list[float]] | None:
        """
        Look up a semantically similar cached query with matching parameters.

        Finds the nearest embedding in pgvector, then verifies that
        include_text, response_mode, and retrieval_mode also match.
        Pass a pre-computed embedding to avoid an API call.
        Returns (response_text, source_nodes, embedding) on hit, None on miss.
        """
        try:
            if embedding is None:
                embedding = self.embed_query(query_text)
            embedding_str = self._embedding_to_str(embedding)

            with self._pg_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    f"""
                        SELECT cache_key,
                               1 - (query_embedding <=> %s::vector) AS similarity
                        FROM {TABLE_NAME}
                        WHERE include_text = %s
                          AND response_mode = %s
                          AND retrieval_mode = %s
                        ORDER BY query_embedding <=> %s::vector
                        LIMIT 1
                        """,
                    (
                        embedding_str,
                        include_text,
                        response_mode,
                        retrieval_mode,
                        embedding_str,
                    ),
                )
                row = cur.fetchone()

            if row is None:
                return None

            cache_key, similarity = row
            if similarity < self._threshold:
                return None

            # Fetch payload from Redis
            redis_key = f"{CACHE_KEY_PREFIX}{cache_key}"
            payload = self._redis.get(redis_key)
            if payload is None:
                # Redis entry expired — clean up orphaned pgvector row
                self._delete_embedding(cache_key)
                return None

            payload_bytes: bytes = (
                payload if isinstance(payload, bytes) else str(payload).encode()
            )
            data = json.loads(payload_bytes)
            source_nodes = [
                SourceNodeInfo.model_validate(sn) for sn in data["source_nodes"]
            ]
            kg_cache_similarity_score.observe(similarity)
            logger.info(
                "query_cache_hit",
                similarity=round(similarity, 4),
                cache_key=cache_key[:12],
            )
            return data["response_text"], source_nodes, embedding

        except Exception as exc:
            logger.warning("query_cache_get_failed", error=str(exc))
            return None

    def set(
        self,
        query_text: str,
        include_text: bool,
        response_mode: ResponseMode,
        retrieval_mode: RetrievalMode,
        response_text: str,
        source_nodes: list[SourceNodeInfo],
        embedding: list[float] | None = None,
    ) -> None:
        """
        Store a query result in the cache.

        Pass the embedding from a prior get() call to avoid regenerating it.
        """
        try:
            cache_key = self._make_cache_key(
                query_text, include_text, response_mode, retrieval_mode
            )
            if embedding is None:
                embedding = self.embed_query(query_text)
            embedding_str = self._embedding_to_str(embedding)

            # Store embedding + params in pgvector
            with self._pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE_NAME}
                            (cache_key, include_text, response_mode, retrieval_mode,
                             query_embedding)
                        VALUES (%s, %s, %s, %s, %s::vector)
                        ON CONFLICT (cache_key) DO UPDATE SET
                            query_embedding = EXCLUDED.query_embedding
                        """,
                        (
                            cache_key,
                            include_text,
                            response_mode,
                            retrieval_mode,
                            embedding_str,
                        ),
                    )
                conn.commit()

            # Store payload in Redis with TTL
            payload = json.dumps({
                "response_text": response_text,
                "source_nodes": [
                    sn.model_dump(by_alias=True) for sn in source_nodes
                ],
            })
            self._redis.setex(
                f"{CACHE_KEY_PREFIX}{cache_key}",
                self._ttl,
                payload,
            )

            logger.info("query_cache_set", cache_key=cache_key[:12])

        except Exception as exc:
            logger.warning("query_cache_set_failed", error=str(exc))

    async def invalidate(self) -> None:
        """Clear all cached query results."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._invalidate_sync)

    def _invalidate_sync(self) -> None:
        """Synchronous cache invalidation."""
        try:
            with self._pg_conn() as conn, conn.cursor() as cur:
                cur.execute(f"DELETE FROM {TABLE_NAME}")
                conn.commit()

            for key in self._redis.scan_iter(f"{CACHE_KEY_PREFIX}*"):
                self._redis.delete(key)

            kg_cache_invalidations_total.inc()
            logger.info("query_cache_invalidated")

        except Exception as exc:
            logger.warning("query_cache_invalidate_failed", error=str(exc))

    def check_health(self) -> dict[str, str]:
        """Check cache backend connectivity."""
        try:
            with self._pg_conn() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
            self._redis.ping()
            return {"status": "ok", "backend": "redis+pgvector"}
        except Exception as exc:
            return {
                "status": "degraded",
                "backend": "redis+pgvector",
                "error": str(exc),
            }


def create_query_cache(config: AppSettings) -> QueryCache | None:
    """Create a QueryCache if Redis and PostgreSQL are configured. Returns None otherwise."""
    if not config.celery_broker_url or not config.postgres_uri:
        return None
    try:
        return QueryCache(
            redis_url=config.celery_broker_url,
            postgres_uri=config.postgres_uri,
            ttl=config.cache_ttl_seconds,
            threshold=config.cache_similarity_threshold,
            embed_dim=config.embed_dim,
        )
    except Exception as exc:
        logger.warning("query_cache_init_failed", error=str(exc))
        return None

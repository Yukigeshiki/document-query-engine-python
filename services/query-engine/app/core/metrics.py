"""Prometheus metric definitions for the knowledge graph service."""

from prometheus_client import Counter, Gauge, Histogram

# Query metrics
kg_query_duration_seconds = Histogram(
    "kg_query_duration_seconds",
    "Knowledge graph query duration",
    labelnames=["retrieval_mode"],
)
kg_query_total = Counter(
    "kg_query_total",
    "Total knowledge graph queries",
    labelnames=["retrieval_mode", "status"],
)
kg_query_cache_hits_total = Counter(
    "kg_query_cache_hits_total",
    "Query cache hits",
)
kg_query_cache_misses_total = Counter(
    "kg_query_cache_misses_total",
    "Query cache misses",
)

# Ingestion metrics
kg_ingest_duration_seconds = Histogram(
    "kg_ingest_duration_seconds",
    "Document ingestion duration",
)
kg_ingest_total = Counter(
    "kg_ingest_total",
    "Total documents ingested",
    labelnames=["status"],
)
kg_ingest_triplets_total = Counter(
    "kg_ingest_triplets_total",
    "Cumulative triplets extracted",
)

# Subgraph metrics
kg_subgraph_duration_seconds = Histogram(
    "kg_subgraph_duration_seconds",
    "Subgraph retrieval duration",
)
kg_subgraph_total = Counter(
    "kg_subgraph_total",
    "Total subgraph queries",
)

# Cache metrics
kg_cache_similarity_score = Histogram(
    "kg_cache_similarity_score",
    "Similarity scores on cache lookups",
    buckets=[0.8, 0.85, 0.9, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0],
)
kg_cache_invalidations_total = Counter(
    "kg_cache_invalidations_total",
    "Query cache invalidations",
)

# Health gauges
kg_graph_store_up = Gauge(
    "kg_graph_store_up",
    "Graph store health (1=ok, 0=degraded)",
)
kg_vector_store_up = Gauge(
    "kg_vector_store_up",
    "Vector store health (1=ok, 0=degraded)",
)
kg_cache_up = Gauge(
    "kg_cache_up",
    "Query cache health (1=ok, 0=degraded)",
)

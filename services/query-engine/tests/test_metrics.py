"""Tests for Prometheus metrics endpoint."""

import pytest
from httpx import AsyncClient
from prometheus_client import REGISTRY

from app.core import metrics as _metrics  # noqa: F401 — ensure metrics are registered


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200(client: AsyncClient) -> None:
    """Verify /metrics returns 200 with Prometheus text format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_request" in response.text


@pytest.mark.asyncio
async def test_custom_metrics_registered() -> None:
    """Verify custom KG metrics are registered in the Prometheus registry."""
    metric_names = [m.name for m in REGISTRY.collect()]

    expected = [
        "kg_query_duration_seconds",
        "kg_query",
        "kg_query_cache_hits",
        "kg_query_cache_misses",
        "kg_ingest_duration_seconds",
        "kg_ingest",
        "kg_ingest_triplets",
        "kg_subgraph_duration_seconds",
        "kg_subgraph",
        "kg_cache_similarity_score",
        "kg_cache_invalidations",
        "kg_graph_store_up",
        "kg_vector_store_up",
        "kg_cache_up",
    ]

    for name in expected:
        assert name in metric_names, f"Metric '{name}' not found in registry"

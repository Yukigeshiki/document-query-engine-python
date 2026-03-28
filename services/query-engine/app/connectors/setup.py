"""Register all built-in connectors at application startup."""

from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]

from app.connectors.gcs import GCSConnector
from app.connectors.registry import default_registry
from app.core.config import Settings
from app.models.knowledge_graph import SourceType


def register_default_connectors(config: Settings, gcs_client: gcs_storage.Client) -> None:
    """Register GCS connector with shared client."""
    default_registry.register(
        SourceType.GCS,
        GCSConnector(
            gcs_bucket=config.gcs_bucket,
            gcs_client=gcs_client,
        ),
    )

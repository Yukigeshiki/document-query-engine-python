"""Register all built-in connectors at application startup."""

from pathlib import Path

from app.connectors.filesystem import FilesystemConnector
from app.connectors.gcs import GCSConnector
from app.connectors.registry import default_registry
from app.core.config import Settings
from app.models.knowledge_graph import SourceType


def register_default_connectors(config: Settings) -> None:
    """Register filesystem and GCS connectors."""
    default_registry.register(
        SourceType.FILESYSTEM,
        FilesystemConnector(data_dir=Path(config.data_dir)),
    )
    default_registry.register(
        SourceType.GCS,
        GCSConnector(
            gcs_bucket=config.gcs_bucket,
            gcs_credentials_path=config.gcs_credentials_path,
        ),
    )

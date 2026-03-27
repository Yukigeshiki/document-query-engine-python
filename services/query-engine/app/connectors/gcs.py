"""Google Cloud Storage document connector."""

from collections.abc import Iterator
from typing import Any

import structlog
from llama_index.core import Document
from llama_index.readers.gcs import GCSReader

from app.connectors.base import BaseConnector
from app.core.errors import BadRequestError, ConnectorError

logger = structlog.stdlib.get_logger(__name__)


class GCSConnector(BaseConnector):
    """Load documents from a Google Cloud Storage bucket."""

    def __init__(self, gcs_bucket: str = "", gcs_credentials_path: str = "") -> None:
        """Initialize with optional default bucket and credentials."""
        self._gcs_bucket = gcs_bucket
        self._gcs_credentials_path = gcs_credentials_path

    def load_documents(self, config: dict[str, Any]) -> Iterator[Document]:
        """
        Yield documents from GCS.

        Config keys:
            bucket (str): GCS bucket name. Falls back to default from Settings.
            prefix (str): Object key prefix to filter by. Default "".
        """
        bucket = config.get("bucket") or self._gcs_bucket
        if not bucket:
            raise BadRequestError(
                detail="GCS connector requires 'bucket' in config or GCS_BUCKET env var"
            )

        prefix = str(config.get("prefix", ""))

        reader_kwargs: dict[str, Any] = {"bucket": bucket, "prefix": prefix}
        if self._gcs_credentials_path:
            reader_kwargs["service_account_key_path"] = self._gcs_credentials_path

        try:
            reader = GCSReader(**reader_kwargs)
            documents: list[Document] = reader.load_data()
        except (BadRequestError, ConnectorError):
            raise
        except Exception as exc:
            raise ConnectorError(
                detail=f"Failed to read documents from gs://{bucket}/{prefix}: {exc}"
            ) from exc

        logger.info(
            "gcs_documents_loaded",
            bucket=bucket,
            prefix=prefix,
            count=len(documents),
        )
        yield from documents

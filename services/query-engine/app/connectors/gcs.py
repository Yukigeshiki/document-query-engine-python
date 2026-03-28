"""Google Cloud Storage document connector."""

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog
from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]
from llama_index.core import Document, SimpleDirectoryReader

from app.connectors import SUPPORTED_EXTENSIONS
from app.connectors.base import BaseConnector
from app.core.errors import BadRequestError, ConnectorError

logger = structlog.stdlib.get_logger(__name__)


class GCSConnector(BaseConnector):
    """Load documents from a Google Cloud Storage bucket."""

    def __init__(self, gcs_bucket: str, gcs_client: gcs_storage.Client) -> None:
        """Initialize with bucket name and shared GCS client."""
        self._gcs_bucket = gcs_bucket
        self._gcs_client = gcs_client

    def load_documents(self, config: dict[str, Any]) -> Iterator[Document]:
        """
        Yield documents from GCS.

        Downloads blobs to a temp directory, then reads them with
        SimpleDirectoryReader. This avoids gcsfs reliability issues.

        Config keys:
            bucket (str): GCS bucket name. Falls back to default from Settings.
            prefix (str): Object key prefix to filter by. Default "".
        """
        bucket_name = config.get("bucket") or self._gcs_bucket
        if not bucket_name:
            raise BadRequestError(
                detail="GCS connector requires 'bucket' in config or GCS_BUCKET env var"
            )

        prefix = str(config.get("prefix", ""))

        try:
            bucket = self._gcs_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))

            if not blobs:
                logger.info("gcs_no_blobs_found", bucket=bucket_name, prefix=prefix)
                return

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                downloaded = 0

                for blob in blobs:
                    if blob.name.endswith("/"):
                        continue
                    # Preserve directory structure to avoid overwrites
                    # when blobs in different folders share the same filename
                    local_file = tmp_path / blob.name
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                    blob.download_to_filename(str(local_file))
                    downloaded += 1

                if downloaded == 0:
                    logger.info("gcs_no_files_downloaded", bucket=bucket_name, prefix=prefix)
                    return

                reader = SimpleDirectoryReader(
                    input_dir=str(tmp_path),
                    recursive=True,
                    required_exts=SUPPORTED_EXTENSIONS,
                )

                documents = reader.load_data()

                logger.info(
                    "gcs_documents_loaded",
                    bucket=bucket_name,
                    prefix=prefix,
                    blobs=downloaded,
                    documents=len(documents),
                )
                yield from documents

        except (BadRequestError, ConnectorError):
            raise
        except Exception as exc:
            raise ConnectorError(
                detail=f"Failed to read documents from gs://{bucket_name}/{prefix}: {exc}"
            ) from exc

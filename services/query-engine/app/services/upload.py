"""Upload service for saving files to GCS."""

import asyncio
import os
import uuid
from typing import Any

import structlog
from fastapi import UploadFile
from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]

from app.connectors import SUPPORTED_EXTENSIONS
from app.core.errors import BadRequestError, ConnectorError
from app.models.knowledge_graph import SourceType

logger = structlog.stdlib.get_logger(__name__)
UPLOADS_SUBDIR = "uploads"
CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


class UploadService:
    """Saves uploaded files to GCS and returns connector config."""

    def __init__(self, gcs_bucket: str, gcs_client: gcs_storage.Client) -> None:
        self._gcs_bucket = gcs_bucket
        self._gcs_client = gcs_client
        if not self._gcs_bucket:
            raise ValueError("GCS_BUCKET must be configured for uploads")

    async def save(self, file: UploadFile) -> tuple[SourceType, dict[str, Any]]:
        """
        Save an uploaded file to GCS and return the connector config for ingestion.

        Reads the file in chunks to enforce a 20MB size limit,
        then uploads to GCS in a thread executor.

        Returns (source_type, config) suitable for ingest_source_task.
        """
        raw_filename = file.filename or "document"
        filename = os.path.basename(raw_filename)
        ext = os.path.splitext(filename)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise BadRequestError(
                detail=f"Unsupported file type '{ext}'. Supported: {supported}"
            )

        upload_id = str(uuid.uuid4())
        gcs_path = f"{UPLOADS_SUBDIR}/{upload_id}/{filename}"

        # Read with size check, then upload in executor
        chunks: list[bytes] = []
        total_size = 0
        while chunk := await file.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                raise BadRequestError(
                    detail=f"File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB"
                )
            chunks.append(chunk)

        content = b"".join(chunks)
        loop = asyncio.get_running_loop()

        def _upload() -> None:
            bucket = self._gcs_client.bucket(self._gcs_bucket)
            blob = bucket.blob(gcs_path)
            blob.upload_from_string(content)

        try:
            await loop.run_in_executor(None, _upload)
        except (BadRequestError, ConnectorError):
            raise
        except Exception as exc:
            raise ConnectorError(
                detail=f"Failed to upload to GCS: {exc}"
            ) from exc

        logger.info(
            "file_saved_to_gcs",
            upload_id=upload_id,
            bucket=self._gcs_bucket,
            path=gcs_path,
            size=total_size,
        )
        return SourceType.GCS, {
            "bucket": self._gcs_bucket,
            "prefix": f"{UPLOADS_SUBDIR}/{upload_id}/",
        }

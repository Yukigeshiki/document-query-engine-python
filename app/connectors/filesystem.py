"""Filesystem document connector using LlamaIndex SimpleDirectoryReader."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog
from llama_index.core import Document, SimpleDirectoryReader

from app.connectors.base import BaseConnector
from app.core.errors import BadRequestError, ConnectorError

logger = structlog.stdlib.get_logger(__name__)

SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".txt"]
ALLOWED_BASE_DIR = Path.home() / "query-engine-data"


class FilesystemConnector(BaseConnector):
    """Load documents from a local filesystem directory."""

    def load_documents(self, config: dict[str, Any]) -> Iterator[Document]:
        """
        Yield documents from the configured path.

        The path must resolve to a location within ~/query-engine-data.

        Config keys:
            path (str): Directory path to read from. Required.
            recursive (bool): Whether to read subdirectories. Default False.
        """
        dir_path = config.get("path")
        if not dir_path:
            raise BadRequestError(
                detail="Filesystem connector requires 'path' in config"
            )

        path = Path(str(dir_path)).resolve()

        if not path.is_relative_to(ALLOWED_BASE_DIR):
            raise BadRequestError(
                detail=f"Path must be within {ALLOWED_BASE_DIR}"
            )

        if not path.exists() or not path.is_dir():
            raise BadRequestError(detail=f"Directory does not exist: {path}")

        recursive = bool(config.get("recursive", False))

        try:
            reader = SimpleDirectoryReader(
                input_dir=str(path),
                recursive=recursive,
                required_exts=SUPPORTED_EXTENSIONS,
            )
        except (BadRequestError, ConnectorError):
            raise
        except Exception as exc:
            raise ConnectorError(
                detail=f"Failed to read documents from {path}: {exc}"
            ) from exc

        logger.info("filesystem_loading_documents", path=str(path))
        for file_docs in reader.iter_data():
            yield from file_docs

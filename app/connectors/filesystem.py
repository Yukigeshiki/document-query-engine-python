"""Filesystem document connector using LlamaIndex SimpleDirectoryReader."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog
from llama_index.core import Document, SimpleDirectoryReader

from app.connectors import SUPPORTED_EXTENSIONS
from app.connectors.base import BaseConnector
from app.core.errors import BadRequestError, ConnectorError

logger = structlog.stdlib.get_logger(__name__)


class FilesystemConnector(BaseConnector):
    """Load documents from a local filesystem directory."""

    def __init__(self, data_dir: Path) -> None:
        """Initialize with the allowed base directory."""
        self._data_dir = data_dir

    def load_documents(self, config: dict[str, Any]) -> Iterator[Document]:
        """
        Yield documents from the configured path.

        The path must resolve to a location within the configured data directory.

        Config keys:
            path (str): Directory path to read from. Required.
            recursive (bool): Whether to read subdirectories. Default False.
        """
        dir_path = config.get("path")
        if not dir_path:
            raise BadRequestError(
                detail="Filesystem connector requires 'path' in config"
            )

        raw_path = Path(str(dir_path))

        # Resolve relative paths against data_dir so that workers with
        # different DATA_DIR values can find uploaded files
        if not raw_path.is_absolute():
            path = (self._data_dir / raw_path).resolve()
        else:
            path = raw_path.resolve()

        if not path.is_relative_to(self._data_dir):
            raise BadRequestError(
                detail=f"Path must be within {self._data_dir}"
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

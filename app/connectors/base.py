"""Base connector protocol for document sources."""

import abc
from collections.abc import Iterator
from typing import Any

from llama_index.core import Document


class BaseConnector(abc.ABC):
    """
    Abstract base class for document source connectors.

    Each connector accepts a configuration dict and yields
    LlamaIndex Document objects. Implementations are synchronous
    — async wrapping happens in the ingestion pipeline.
    """

    @abc.abstractmethod
    def load_documents(self, config: dict[str, Any]) -> Iterator[Document]:
        """Yield documents from the source."""
        ...

"""Connector registry: maps source types to connector instances."""

from app.connectors.base import BaseConnector
from app.core.errors import BadRequestError
from app.models.knowledge_graph import SourceType


class ConnectorRegistry:
    """Registry of document source connectors."""

    def __init__(self) -> None:
        self._connectors: dict[SourceType, BaseConnector] = {}

    def register(self, source_type: SourceType, connector: BaseConnector) -> None:
        """Register a connector for the given source type."""
        self._connectors[source_type] = connector

    def get(self, source_type: SourceType) -> BaseConnector:
        """
        Retrieve a registered connector by source type.

        Raises BadRequestError if the source type is unknown.
        """
        connector = self._connectors.get(source_type)
        if connector is None:
            available = ", ".join(sorted(st.value for st in self._connectors)) or "(none)"
            raise BadRequestError(
                detail=f"Unknown source type '{source_type}'. Available: {available}"
            )
        return connector

    def registered_types(self) -> list[SourceType]:
        """Return all registered source type names."""
        return sorted(self._connectors.keys())


# Default instance used by the application
default_registry = ConnectorRegistry()

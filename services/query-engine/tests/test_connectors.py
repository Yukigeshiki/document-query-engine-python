"""Tests for document connectors and registry."""

from unittest.mock import MagicMock, patch

import pytest

from app.connectors.gcs import GCSConnector
from app.connectors.registry import ConnectorRegistry
from app.core.errors import BadRequestError
from app.models.knowledge_graph import SourceType


class TestRegistry:
    """Tests for the connector registry."""

    def test_register_and_get_connector(self) -> None:
        """Verify a connector can be registered and retrieved."""
        registry = ConnectorRegistry()
        connector = MagicMock()
        registry.register(SourceType.GCS, connector)
        assert registry.get(SourceType.GCS) is connector

    def test_get_unknown_connector_raises(self) -> None:
        """Verify BadRequestError for unknown source type."""
        registry = ConnectorRegistry()
        with pytest.raises(BadRequestError, match="Unknown source type"):
            registry.get(SourceType.GCS)

    def test_registered_types(self) -> None:
        """Verify listing registered source types."""
        registry = ConnectorRegistry()
        registry.register(SourceType.GCS, MagicMock())
        assert registry.registered_types() == [SourceType.GCS]


class TestGCSConnector:
    """Tests for the GCS connector."""

    @patch("app.connectors.gcs.SimpleDirectoryReader")
    def test_loads_documents(self, mock_reader_cls: MagicMock) -> None:
        """Verify loading documents from GCS via download-to-temp."""
        mock_blob = MagicMock()
        mock_blob.name = "docs/report.txt"
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader_cls.return_value.load_data.return_value = [mock_doc]

        connector = GCSConnector(gcs_bucket="my-bucket", gcs_client=mock_client)
        docs = list(connector.load_documents({"prefix": "docs/"}))

        assert len(docs) == 1
        mock_client.bucket.assert_called_once_with("my-bucket")
        mock_bucket.list_blobs.assert_called_once_with(prefix="docs/")
        mock_blob.download_to_filename.assert_called_once()

    @patch("app.connectors.gcs.SimpleDirectoryReader")
    def test_attaches_stable_source_path(self, mock_reader_cls: MagicMock) -> None:
        """Verify each loaded Document gets a stable source_path metadata key.

        The source_path must survive temp-dir changes so retries can derive
        the same doc_id and remain idempotent.
        """
        mock_blob = MagicMock()
        mock_blob.name = "uploads/abc-123/report.pdf"
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        mock_doc = MagicMock()

        # SimpleDirectoryReader sets file_path to the absolute temp-dir path.
        # We use a side_effect on load_data so we can read the actual temp path
        # the connector chose and simulate the reader's behavior accurately.
        captured_input_dir: dict[str, str] = {}

        def fake_init(input_dir: str, **_: object) -> MagicMock:
            captured_input_dir["path"] = input_dir
            return mock_reader_cls.return_value

        mock_reader_cls.side_effect = fake_init

        def fake_load_data() -> list[MagicMock]:
            mock_doc.metadata = {
                "file_path": f"{captured_input_dir['path']}/uploads/abc-123/report.pdf",
            }
            return [mock_doc]

        mock_reader_cls.return_value.load_data.side_effect = fake_load_data

        connector = GCSConnector(gcs_bucket="my-bucket", gcs_client=mock_client)
        docs = list(connector.load_documents({"prefix": "uploads/abc-123/"}))

        assert len(docs) == 1
        assert docs[0].metadata["source_path"] == "gs://my-bucket/uploads/abc-123/report.pdf"

    def test_missing_bucket_raises(self) -> None:
        """Verify BadRequestError when no bucket is configured."""
        connector = GCSConnector(gcs_bucket="", gcs_client=MagicMock())
        with pytest.raises(BadRequestError, match="requires 'bucket'"):
            list(connector.load_documents({}))

    @patch("app.connectors.gcs.SimpleDirectoryReader")
    def test_config_bucket_overrides_default(self, mock_reader_cls: MagicMock) -> None:
        """Verify per-request bucket overrides the default."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        connector = GCSConnector(gcs_bucket="default-bucket", gcs_client=mock_client)
        list(connector.load_documents({"bucket": "override-bucket"}))

        mock_client.bucket.assert_called_once_with("override-bucket")

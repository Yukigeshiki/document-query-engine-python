"""Tests for document connectors and registry."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.connectors.filesystem import FilesystemConnector
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
        registry.register(SourceType.FILESYSTEM, connector)
        assert registry.get(SourceType.FILESYSTEM) is connector

    def test_get_unknown_connector_raises(self) -> None:
        """Verify BadRequestError for unknown source type."""
        registry = ConnectorRegistry()
        with pytest.raises(BadRequestError, match="Unknown source type"):
            registry.get(SourceType.FILESYSTEM)

    def test_registered_types(self) -> None:
        """Verify listing registered source types."""
        registry = ConnectorRegistry()
        registry.register(SourceType.GCS, MagicMock())
        registry.register(SourceType.FILESYSTEM, MagicMock())
        assert registry.registered_types() == [SourceType.FILESYSTEM, SourceType.GCS]


class TestFilesystemConnector:
    """Tests for the filesystem connector."""

    def test_loads_txt_documents(self, tmp_path: Path) -> None:
        """Verify loading .txt files from a directory."""
        subdir = tmp_path / "docs"
        subdir.mkdir()
        (subdir / "test.txt").write_text("Hello world")
        connector = FilesystemConnector(data_dir=tmp_path)
        docs = list(connector.load_documents({"path": str(subdir)}))
        assert len(docs) == 1
        assert "Hello world" in docs[0].get_content()

    def test_missing_path_raises(self, tmp_path: Path) -> None:
        """Verify BadRequestError when path is missing."""
        connector = FilesystemConnector(data_dir=tmp_path)
        with pytest.raises(BadRequestError, match="requires 'path'"):
            list(connector.load_documents({}))

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        """Verify BadRequestError for nonexistent directory."""
        connector = FilesystemConnector(data_dir=tmp_path)
        with pytest.raises(BadRequestError, match="does not exist"):
            list(connector.load_documents({"path": str(tmp_path / "nonexistent")}))

    def test_loads_documents_with_relative_path(self, tmp_path: Path) -> None:
        """Verify loading documents when path is relative to data_dir."""
        subdir = tmp_path / "uploads" / "abc-123"
        subdir.mkdir(parents=True)
        (subdir / "test.txt").write_text("Relative path test")
        connector = FilesystemConnector(data_dir=tmp_path)
        docs = list(connector.load_documents({"path": "uploads/abc-123"}))
        assert len(docs) == 1
        assert "Relative path test" in docs[0].get_content()

    def test_path_outside_allowed_dir_raises(self, tmp_path: Path) -> None:
        """Verify BadRequestError for path outside allowed directory."""
        connector = FilesystemConnector(data_dir=tmp_path)
        with pytest.raises(BadRequestError, match="must be within"):
            list(connector.load_documents({"path": "/etc"}))


class TestGCSConnector:
    """Tests for the GCS connector."""

    @patch("app.connectors.gcs.SimpleDirectoryReader")
    @patch("app.connectors.gcs.gcs_storage")
    def test_loads_documents(self, mock_gcs: MagicMock, mock_reader_cls: MagicMock) -> None:
        """Verify loading documents from GCS via download-to-temp."""
        mock_blob = MagicMock()
        mock_blob.name = "docs/report.txt"
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_gcs.Client.return_value.bucket.return_value = mock_bucket

        mock_doc = MagicMock()
        mock_reader_cls.return_value.load_data.return_value = [mock_doc]

        connector = GCSConnector(gcs_bucket="my-bucket")
        docs = list(connector.load_documents({"prefix": "docs/"}))

        assert len(docs) == 1
        mock_gcs.Client.return_value.bucket.assert_called_once_with("my-bucket")
        mock_bucket.list_blobs.assert_called_once_with(prefix="docs/")
        mock_blob.download_to_filename.assert_called_once()

    def test_missing_bucket_raises(self) -> None:
        """Verify BadRequestError when no bucket is configured."""
        connector = GCSConnector()
        with pytest.raises(BadRequestError, match="requires 'bucket'"):
            list(connector.load_documents({}))

    @patch("app.connectors.gcs.SimpleDirectoryReader")
    @patch("app.connectors.gcs.gcs_storage")
    def test_config_bucket_overrides_default(self, mock_gcs: MagicMock, mock_reader_cls: MagicMock) -> None:
        """Verify per-request bucket overrides the default."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []
        mock_gcs.Client.return_value.bucket.return_value = mock_bucket

        connector = GCSConnector(gcs_bucket="default-bucket")
        list(connector.load_documents({"bucket": "override-bucket"}))

        mock_gcs.Client.return_value.bucket.assert_called_once_with("override-bucket")

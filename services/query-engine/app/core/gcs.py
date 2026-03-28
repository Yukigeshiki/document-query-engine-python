"""Singleton GCS client factory."""

import json

from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]

from app.core.config import Settings

# NOTE: This lazy singleton is safe because the API server is single-threaded
# async and the Celery worker runs with concurrency=1. If worker concurrency
# is ever increased, this must be replaced with thread-safe init.
_client: gcs_storage.Client | None = None


def get_gcs_client(config: Settings) -> gcs_storage.Client:
    """Return a shared GCS client, creating it on first call."""
    global _client
    if _client is None:
        if config.gcs_credentials_json:
            try:
                credentials = json.loads(config.gcs_credentials_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"GCS_CREDENTIALS_JSON contains invalid JSON: {exc}"
                ) from exc
            _client = gcs_storage.Client.from_service_account_info(credentials)
        else:
            _client = gcs_storage.Client()
    return _client

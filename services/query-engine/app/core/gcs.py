"""Singleton GCS client factory."""

import json
from typing import Any

from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]

from app.core.config import Settings

# Lazy per-process singleton. Safe under FastAPI (single-threaded async) and
# Celery's prefork pool (each worker process has its own copy of this global).
_client: Any = None


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

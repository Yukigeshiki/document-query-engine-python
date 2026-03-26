"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings populated from environment variables and .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "agent-query-engine"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "info"

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    cors_origins: list[str] = ["*"]

    # OpenAI
    openai_api_key: str = ""

    # LlamaIndex
    llm_model: str = ""
    llm_temperature: float = 0
    embedding_model: str = ""
    max_triplets_per_chunk: int = 10
    chunk_size: int = 1024

    # Neo4j
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""
    neo4j_database: str = ""
    neo4j_enabled: bool = True

    # PostgreSQL / pgvector
    postgres_uri: str = ""
    postgres_enabled: bool = True
    embed_dim: int = 1536
    vector_top_k: int = 10

    # Data directory (shared between API and worker)
    data_dir: str = ""

    # Document connectors
    gcs_bucket: str = ""
    gcs_credentials_path: str = ""

    # Uploads
    upload_storage: str = ""

    # Celery
    celery_broker_url: str = ""


settings = Settings()

"""Application configuration using pydantic-settings."""
from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised, validated application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "AI Migration Platform"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── API Server ───────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── LLM Providers ────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    openai_api_key: str = Field(..., description="OpenAI API key for validation")
    primary_model: str = "claude-sonnet-4-5"
    validation_model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.1

    # ── Storage Paths ─────────────────────────────────────────
    data_dir: Path = Path("./data")
    repos_dir: Path = Path("./repos")
    output_dir: Path = Path("./output")
    graph_persist_path: Path = Path("./data/graph.pkl")
    duckdb_path: Path = Path("./data/migration.duckdb")
    chroma_persist_dir: Path = Path("./data/chroma")
    cache_dir: Path = Path("./data/cache")
    checkpoint_path: Path = Path("./data/checkpoints.pkl")

    # ── RAG ───────────────────────────────────────────────────
    max_chunk_tokens: int = 512
    chunk_overlap_tokens: int = 64
    retrieval_top_k: int = 6
    max_context_tokens: int = 6000
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072   # text-embedding-3-large=3072, text-embedding-3-small/ada-002=1536

    # ── Processing ───────────────────────────────────────────
    parser_max_workers: int = 20
    codegen_max_workers: int = 8
    llm_retry_attempts: int = 3
    llm_retry_wait_seconds: int = 2

    @field_validator("data_dir", "repos_dir", "output_dir", mode="before")
    @classmethod
    def create_dirs(cls, v: str | Path) -> Path:
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return singleton settings instance (cached)."""
    return Settings()  # type: ignore[call-arg]

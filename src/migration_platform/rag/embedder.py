"""Embedding service wrapping OpenAI text-embedding-3-large."""
from __future__ import annotations
import hashlib
from typing import Any
import tiktoken
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from migration_platform.config.settings import get_settings
from migration_platform.core.logging import get_logger

logger = get_logger(__name__)


class Embedder:
    """Stateless embedding service with token counting and caching."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self._tokenizer = tiktoken.get_encoding("cl100k_base")
        logger.info("Embedder initialised", model=self._model)

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text))

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        tokens = self._tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._tokenizer.decode(tokens[:max_tokens])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        response = self._client.embeddings.create(
            input=text, model=self._model
        )
        return response.data[0].embedding

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (up to 2048 per request)."""
        if not texts:
            return []
        # OpenAI allows max 2048 items per batch — use the full limit
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), 2048):
            batch = texts[i : i + 2048]
            response = self._client.embeddings.create(
                input=batch, model=self._model
            )
            all_embeddings.extend([r.embedding for r in response.data])
        logger.debug("Embedded batch", count=len(texts))
        return all_embeddings

"""diskcache-based cache — replaces Redis, zero server required."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
import diskcache
from migration_platform.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL = 86_400  # 24 hours


class CacheStore:
    """
    Local disk-backed cache. Thread-safe, no server required.
    Works with Celery workers via shared filesystem.
    """

    def __init__(self, cache_dir: str | Path = "./data/cache") -> None:
        self._cache = diskcache.Cache(str(cache_dir))
        logger.info("CacheStore initialised", dir=str(cache_dir))

    # ── LLM Response Cache ────────────────────────────────────
    def get_llm_response(self, prompt: str) -> str | None:
        key = f"llm:{self._hash(prompt)}"
        return self._cache.get(key)

    def set_llm_response(self, prompt: str, response: str, ttl: int = _DEFAULT_TTL) -> None:
        key = f"llm:{self._hash(prompt)}"
        self._cache.set(key, response, expire=ttl)

    # ── Task Status ───────────────────────────────────────────
    def set_task_status(self, task_id: str, status: str) -> None:
        self._cache.set(f"task:{task_id}", status, expire=3600)

    def get_task_status(self, task_id: str) -> str:
        return self._cache.get(f"task:{task_id}", default="unknown")

    # ── Arbitrary Key-Value ───────────────────────────────────
    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default=default)

    def set(self, key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
        self._cache.set(key, value, expire=ttl)

    def delete(self, key: str) -> None:
        self._cache.delete(key)

    def clear_migration(self, migration_id: str) -> None:
        """Remove all cached data for a migration run."""
        prefix = f"migration:{migration_id}:"
        for key in list(self._cache.iterkeys()):
            if isinstance(key, str) and key.startswith(prefix):
                self._cache.delete(key)

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def close(self) -> None:
        self._cache.close()

"""
Global pytest configuration and shared fixtures.

All fixtures that spin up in-memory stores are defined here
so every test module can reuse them without repetition.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.vector_store import VectorStore
from migration_platform.storage.cache_store import CacheStore
from migration_platform.storage.state_store import StateStore


# ── Shared store fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def migration_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def state_store() -> StateStore:
    """Fresh in-memory DuckDB per test — no disk writes."""
    return StateStore(db_path=":memory:")


@pytest.fixture
def graph_store(tmp_path: Path) -> GraphStore:
    """Fresh NetworkX graph per test, persisted in tmp_path."""
    return GraphStore(persist_path=tmp_path / "test_graph.pkl")


@pytest.fixture
def vector_store() -> VectorStore:
    """Fresh ChromaDB EphemeralClient per test — no disk writes."""
    return VectorStore()


@pytest.fixture
def cache_store(tmp_path: Path) -> CacheStore:
    """Fresh diskcache per test."""
    return CacheStore(cache_dir=tmp_path / "test_cache")


# ── Tiny dummy embedding helper ───────────────────────────────────────────────

def make_embedding(seed: int = 0, dim: int = 10) -> list[float]:
    """Deterministic unit-test embedding — no OpenAI call needed."""
    return [float((seed + i) % 10) / 10.0 for i in range(dim)]
